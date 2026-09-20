"""OmniTools API — aplikasi HTTP (FastAPI) untuk alat-alat OmniTools bahzi.fun.

Alat pertama yang benar-benar jalan: **Merge PDF**
(`POST /api/pdf/merge`).

Prinsip operasional:
* Semua pemrosesan di memori — tidak ada berkas yang ditulis ke disk.
* Log hanya berisi metadata (jumlah berkas, total byte, durasi). Nama berkas
  pengguna dan isinya tidak pernah dicatat.
* Respons PDF selalu `Cache-Control: no-store` supaya hasil tidak nyangkut
  di cache browser/proxy.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from . import __version__
from .image_convert import (
    CHUNK_SIZE as IMG_CHUNK_SIZE,
    MAX_BYTES as IMG_MAX_BYTES,
    MAX_FILES as IMG_MAX_FILES,
    MAX_PIXELS as IMG_MAX_PIXELS,
    MIME_TYPES as IMG_MIME_TYPES,
    QUALITY_DEFAULT as IMG_QUALITY_DEFAULT,
    QUALITY_MAX as IMG_QUALITY_MAX,
    QUALITY_MIN as IMG_QUALITY_MIN,
    SVG_DEFAULT_WIDTH as IMG_SVG_DEFAULT_WIDTH,
    SVG_MAX_WIDTH as IMG_SVG_MAX_WIDTH,
    TARGET_LABELS as IMG_TARGET_LABELS,
    TARGETS as IMG_TARGETS,
    ImageConvertError,
    check_file_count as check_image_file_count,
    check_total_size as check_image_total_size,
    convert_image,
    normalize_quality,
    normalize_target,
)
from .pdf_merge import (
    CHUNK_SIZE,
    ERR_TOO_LARGE,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    MAX_TOTAL_PAGES,
    PdfMergeError,
    check_file_count,
    check_total_size,
    merge_pdfs,
)
from .case_convert import (
    CHUNK_SIZE as CC_CHUNK_SIZE,
    MAX_BYTES as CC_MAX_BYTES,
    MAX_CHARS as CC_MAX_CHARS,
    MODE_ORDER as CC_MODE_ORDER,
    MODES as CC_MODES,
    NO_TEXT as CC_NO_TEXT,
    TOO_LONG as CC_TOO_LONG,
    UNSUPPORTED_MODE as CC_UNSUPPORTED_MODE,
    INVALID_REQUEST as CC_INVALID_REQUEST,
    CaseConvertError,
    convert_case,
)
from .word_count import (
    CHUNK_SIZE as WC_CHUNK_SIZE,
    ENTRY_LIMIT as WC_ENTRY_LIMIT,
    MAX_BYTES as WC_MAX_BYTES,
    MAX_CHARS as WC_MAX_CHARS,
    NO_TEXT as WC_NO_TEXT,
    TOO_LONG as WC_TOO_LONG,
    INVALID_REQUEST as WC_INVALID_REQUEST,
    WordCountError,
    count_text,
)
from .ocr import (
    CHUNK_SIZE as OCR_CHUNK_SIZE,
    LANGS as OCR_LANGS,
    LANGUAGES as OCR_LANGUAGES,
    MAX_BYTES as OCR_MAX_BYTES,
    MAX_PAGES as OCR_MAX_PAGES,
    TIME_LIMIT_SECONDS as OCR_TIME_LIMIT_SECONDS,
    TOO_LARGE as OCR_TOO_LARGE,
    OcrError,
    run_ocr,
)
from .base64_tool import (
    CHUNK_SIZE as B64_CHUNK_SIZE,
    MAX_BYTES as B64_MAX_BYTES,
    MAX_CHARS as B64_MAX_CHARS,
    MODES as B64_MODES,
    VARIANTS as B64_VARIANTS,
    WRAP_OPTIONS as B64_WRAP_OPTIONS,
    INVALID_BASE64 as B64_INVALID_BASE64,
    INVALID_REQUEST as B64_INVALID_REQUEST,
    INVALID_VARIANT as B64_INVALID_VARIANT,
    INVALID_WRAP as B64_INVALID_WRAP,
    NO_TEXT as B64_NO_TEXT,
    NOT_TEXT as B64_NOT_TEXT,
    TOO_LONG as B64_TOO_LONG,
    UNSUPPORTED_MODE as B64_UNSUPPORTED_MODE,
    Base64Result,
    Base64ToolError,
    convert_base64,
)

SERVICE_NAME = "omnitools-api"
OUTPUT_FILENAME = "gabungan.pdf"

# Slack untuk overhead multipart saat memeriksa header Content-Length.
CONTENT_LENGTH_SLACK = 1024 * 1024

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("omnitools.api")

app = FastAPI(
    title="OmniTools API",
    version=__version__,
    description=(
        "API server untuk alat OmniTools (bahzi.fun). Alat aktif: Merge PDF, "
        "Image Converter, Word Counter, Case Converter. Berkas dan teks diproses di memori dan tidak disimpan."
    ),
)

# --- CORS opsional -----------------------------------------------------------
# Default MATI (front-end memanggil same-origin lewat /api/...). Nyalakan hanya
# bila front-end dilayani dari origin lain, mis.
#   OMNITOOLS_CORS_ORIGINS=https://bahzi.fun,https://www.bahzi.fun
_cors_origins = [o.strip() for o in os.getenv("OMNITOOLS_CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[
            "X-File-Count",
            "X-Page-Count",
            "X-Total-Bytes",
            "X-Processing-Ms",
            "X-Input-Format",
            "X-Output-Format",
            "X-Pixels",
            "X-Scaled-Down",
            "X-Char-Count",
            "X-Word-Count",
            "X-Case-Mode",
            "X-Ocr-Lang",
            "X-Base64-Mode",
            "X-Output-Length",
        ],
    )

# Batasi satu proses OCR sekaligus di tingkat modul
_ocr_semaphore = threading.Semaphore(1)


# --- Handler error -----------------------------------------------------------
@app.exception_handler(PdfMergeError)
async def handle_pdf_error(request: Request, exc: PdfMergeError) -> JSONResponse:
    """Error yang sudah terklasifikasi → JSON rapi + status HTTP tepat."""
    logger.warning("ditolak: code=%s status=%s path=%s", exc.code, exc.status_code, request.url.path)
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(ImageConvertError)
async def handle_image_error(request: Request, exc: ImageConvertError) -> JSONResponse:
    """Error konversi gambar yang sudah terklasifikasi → JSON rapi + status HTTP tepat."""
    logger.warning("konversi ditolak: code=%s status=%s path=%s", exc.code, exc.status_code, request.url.path)
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(WordCountError)
async def handle_word_count_error(request: Request, exc: WordCountError) -> JSONResponse:
    """Error hitung kata yang sudah terklasifikasi → JSON rapi + status HTTP tepat."""
    logger.warning("hitung kata ditolak: code=%s status=%s path=%s", exc.code, exc.status_code, request.url.path)
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(CaseConvertError)
async def handle_case_convert_error(request: Request, exc: CaseConvertError) -> JSONResponse:
    """Error ubah huruf yang sudah terklasifikasi → JSON rapi + status HTTP tepat."""
    logger.warning("ubah huruf ditolak: code=%s status=%s path=%s", exc.code, exc.status_code, request.url.path)
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(OcrError)
async def handle_ocr_error(request: Request, exc: OcrError) -> JSONResponse:
    """Error OCR yang sudah terklasifikasi → JSON rapi + status HTTP tepat."""
    logger.warning("ambil teks ditolak: code=%s status=%s path=%s", exc.code, exc.status_code, request.url.path)
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(Base64ToolError)
async def handle_base64_error(request: Request, exc: Base64ToolError) -> JSONResponse:
    """Error base64 yang sudah terklasifikasi -> JSON rapi + status HTTP tepat."""
    logger.warning("ubah base64 ditolak: code=%s status=%s path=%s", exc.code, exc.status_code, request.url.path)
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Request malformed (mis. body bukan multipart) → 400 dengan format sama."""
    logger.warning("permintaan tidak valid: path=%s", request.url.path)
    if request.url.path.startswith("/api/ocr"):
        msg = "Permintaan tidak valid. Kirim multipart/form-data dengan field 'file' berisi gambar atau PDF."
    elif request.url.path.startswith("/api/base64"):
        msg = "Permintaan tidak valid. Kirim multipart/form-data dengan field 'text' dan 'mode'."
    elif request.url.path.startswith("/api/case"):
        msg = "Permintaan tidak valid. Kirim multipart/form-data dengan field 'text' dan 'mode'."
    elif request.url.path.startswith("/api/word-count"):
        msg = "Permintaan tidak valid. Kirim multipart/form-data dengan field teks bernama 'text'."
    elif request.url.path.startswith("/api/image/convert"):
        msg = "Permintaan tidak valid. Kirim multipart/form-data dengan field 'files' berisi berkas gambar."
    else:
        msg = (
            "Permintaan tidak valid. Kirim multipart/form-data dengan satu "
            "atau lebih field bernama 'files' berisi berkas PDF."
        )
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "INVALID_REQUEST",
                "message": msg,
            }
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Jaring pengaman terakhir — tetap balas JSON, tanpa membocorkan detail."""
    logger.exception("error tak terduga: path=%s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Terjadi kesalahan di server saat memproses permintaan.",
            }
        },
    )


@app.middleware("http")
async def log_request_duration(request: Request, call_next):
    """Catat method, path, status, dan durasi — tanpa isi/nama berkas."""
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "%s %s -> %s (%.1f ms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# --- Utilitas -----------------------------------------------------------------
async def _read_capped(upload: UploadFile, remaining_budget: int) -> bytes:
    """Baca unggahan sepotong-sepotong, batalkan lebih awal bila lewat batas."""
    if remaining_budget <= 0:
        check_total_size(MAX_TOTAL_BYTES + 1)  # memicu 413 yang konsisten

    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await upload.read(CHUNK_SIZE)
        if not chunk:
            break
        size += len(chunk)
        if size > remaining_budget:
            check_total_size(MAX_TOTAL_BYTES + 1)  # memicu 413 yang konsisten
        chunks.append(chunk)
    return b"".join(chunks)


def _reject_oversized_content_length(request: Request) -> None:
    """Tolak lebih awal (413) bila header Content-Length sudah jelas kelebihan."""
    raw = request.headers.get("content-length")
    if not raw:
        return
    try:
        declared = int(raw)
    except ValueError:
        return
    if declared > MAX_TOTAL_BYTES + CONTENT_LENGTH_SLACK:
        check_total_size(declared - CONTENT_LENGTH_SLACK)


async def _read_capped_image(upload: UploadFile, remaining_budget: int) -> bytes:
    """Baca unggahan gambar sepotong-sepotong, tolak bila lewat batas."""
    if remaining_budget <= 0:
        check_image_total_size(IMG_MAX_BYTES + 1)

    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await upload.read(IMG_CHUNK_SIZE)
        if not chunk:
            break
        size += len(chunk)
        if size > remaining_budget:
            check_image_total_size(IMG_MAX_BYTES + 1)
        chunks.append(chunk)
    return b"".join(chunks)


def _reject_oversized_image_content_length(request: Request) -> None:
    """Tolak lebih awal bila Content-Length sudah jelas melebihi batas gambar."""
    raw = request.headers.get("content-length")
    if not raw:
        return
    try:
        declared = int(raw)
    except ValueError:
        return
    if declared > IMG_MAX_BYTES + CONTENT_LENGTH_SLACK:
        check_image_total_size(declared - CONTENT_LENGTH_SLACK)


def _limits_payload() -> dict:
    return {
        "max_files": MAX_FILES,
        "max_total_bytes": MAX_TOTAL_BYTES,
        "max_total_mb": MAX_TOTAL_BYTES // (1024 * 1024),
        "max_pages": MAX_TOTAL_PAGES,
        "accept": "application/pdf",
        "result_filename": OUTPUT_FILENAME,
        "processed_on": "server",
        "note": (
            "Berkas dikirim ke server ini, digabung di memori, lalu dibuang setelah "
            "respons dikirim. Tidak ada berkas yang disimpan di disk."
        ),
    }


def _image_convert_limits_payload() -> dict:
    return {
        "max_files": IMG_MAX_FILES,
        "max_bytes": IMG_MAX_BYTES,
        "max_total_mb": IMG_MAX_BYTES // (1024 * 1024),
        "max_pixels": IMG_MAX_PIXELS,
        "targets": list(IMG_TARGETS.keys()),
        "target_labels": IMG_TARGET_LABELS,
        "quality_min": IMG_QUALITY_MIN,
        "quality_max": IMG_QUALITY_MAX,
        "quality_default": IMG_QUALITY_DEFAULT,
        "quality_applies_to": ["jpeg", "webp"],
        "inputs": ["png", "jpeg", "webp", "svg"],
        "svgMaxWidth": IMG_SVG_MAX_WIDTH,
        "svgDefaultWidth": IMG_SVG_DEFAULT_WIDTH,
        "accept": "image/png,image/jpeg,image/webp,image/svg+xml",
        "result_filename": "hasil",
        "processed_on": "server",
        "note": (
            "Gambar dikirim ke server untuk dikonversi di memori, lalu dihapus "
            "setelah respons dikirim. Tidak ada berkas yang disimpan di disk."
        ),
    }


def _reject_oversized_word_count_content_length(request: Request) -> None:
    """Tolak lebih awal bila Content-Length sudah jelas melebihi batas teks."""
    raw = request.headers.get("content-length")
    if not raw:
        return
    try:
        declared = int(raw)
    except ValueError:
        return
    if declared > WC_MAX_BYTES + CONTENT_LENGTH_SLACK:
        raise WordCountError(
            WC_TOO_LONG,
            f"Ukuran permintaan melebihi batas {WC_MAX_BYTES // (1024 * 1024)} MB.",
            413,
        )


def _word_count_limits_payload() -> dict:
    return {
        "max_chars": WC_MAX_CHARS,
        "max_bytes": WC_MAX_BYTES,
        "max_mb": WC_MAX_BYTES // (1024 * 1024),
        "processed_on": "server",
        "note": (
            "Teks dikirim ke server untuk dihitung di memori, lalu dibuang setelah "
            "selesai. Tidak ada teks yang disimpan di disk."
        ),
    }


def _reject_oversized_case_content_length(request: Request) -> None:
    """Tolak lebih awal bila Content-Length sudah jelas melebihi batas teks."""
    raw = request.headers.get("content-length")
    if not raw:
        return
    try:
        declared = int(raw)
    except ValueError:
        return
    if declared > CC_MAX_BYTES + CONTENT_LENGTH_SLACK:
        raise CaseConvertError(
            CC_TOO_LONG,
            "Ukuran permintaan melebihi batas 1 MB.",
            413,
        )


def _case_convert_limits_payload() -> dict:
    return {
        "max_chars": CC_MAX_CHARS,
        "max_bytes": CC_MAX_BYTES,
        "max_mb": CC_MAX_BYTES // (1024 * 1024),
        "modes": CC_MODE_ORDER,
        "mode_labels": CC_MODES,
        "processed_on": "server",
        "note": (
            "Teks dikirim ke server untuk diubah di memori, lalu dibuang setelah "
            "selesai. Tidak ada teks yang disimpan di disk."
        ),
    }


def _reject_oversized_base64_content_length(request: Request) -> None:
    """Tolak lebih awal bila Content-Length sudah jelas melebihi batas teks."""
    raw = request.headers.get("content-length")
    if not raw:
        return
    try:
        declared = int(raw)
    except ValueError:
        return
    if declared > B64_MAX_BYTES + CONTENT_LENGTH_SLACK:
        raise Base64ToolError(
            B64_TOO_LONG,
            "Ukuran permintaan melebihi batas 1 MB.",
            413,
        )


def _base64_limits_payload() -> dict:
    return {
        "max_chars": B64_MAX_CHARS,
        "max_bytes": B64_MAX_BYTES,
        "max_mb": B64_MAX_BYTES // (1024 * 1024),
        "modes": [{"value": k, "label": v} for k, v in B64_MODES.items()],
        "variants": [{"value": k, "label": v} for k, v in B64_VARIANTS.items()],
        "wrap_options": [
            {"value": 0, "label": "Tanpa pembungkusan"},
            {"value": 64, "label": "64 karakter per baris"},
            {"value": 76, "label": "76 karakter per baris"},
        ],
        "decode_accepts": [
            "spasi dan baris baru diabaikan",
            "tanda samadengan di akhir boleh tidak ada",
            "awalan data:...;base64, diabaikan",
            "alfabet aman tautan (- dan _) ikut diterima",
        ],
        "processed_on": "server",
        "note": (
            "Teks dikirim ke server untuk diproses di memori, lalu dibuang setelah "
            "selesai. Tidak ada teks yang disimpan di disk."
        ),
    }




# --- Endpoint -----------------------------------------------------------------
@app.get("/health")
async def health() -> dict:
    """Health check untuk gateway / container healthcheck."""
    return {"status": "ok", "service": SERVICE_NAME, "version": __version__}


@app.get("/api/pdf/merge/limits")
async def pdf_merge_limits() -> JSONResponse:
    """Batas yang berlaku untuk Merge PDF — dipakai front-end untuk menampilkan aturan."""
    return JSONResponse(content=_limits_payload(), headers={"Cache-Control": "no-store"})


@app.post("/api/pdf/merge")
async def pdf_merge(request: Request, files: list[UploadFile] = File(default=[])):
    """Gabungkan beberapa PDF (urut sesuai urutan kiriman) → satu PDF.

    Respons: `application/pdf`, `Content-Disposition: attachment; filename="gabungan.pdf"`.
    Header tambahan: `X-File-Count`, `X-Page-Count`, `X-Total-Bytes`, `X-Processing-Ms`.
    """
    started = time.perf_counter()

    uploads = [f for f in files if f is not None]
    check_file_count(len(uploads))
    _reject_oversized_content_length(request)

    payloads: list[bytes] = []
    read_total = 0
    for upload in uploads:
        data = await _read_capped(upload, MAX_TOTAL_BYTES - read_total)
        read_total += len(data)
        payloads.append(data)

    total_bytes = sum(len(p) for p in payloads)
    check_total_size(total_bytes)

    result = merge_pdfs(payloads)
    duration_ms = (time.perf_counter() - started) * 1000

    logger.info(
        "merge selesai: berkas=%d total_byte=%d halaman=%d passthrough=%s durasi=%.0fms",
        result.file_count,
        total_bytes,
        result.page_count,
        result.passthrough,
        duration_ms,
    )

    headers = {
        "Content-Disposition": f'attachment; filename="{OUTPUT_FILENAME}"',
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
        "X-File-Count": str(result.file_count),
        "X-Page-Count": str(result.page_count),
        "X-Total-Bytes": str(len(result.data)),
        "X-Processing-Ms": f"{duration_ms:.0f}",
        "X-Pdf-Passthrough": "true" if result.passthrough else "false",
    }
    return Response(content=result.data, media_type="application/pdf", headers=headers)


@app.get("/api/image/convert/limits")
async def image_convert_limits() -> JSONResponse:
    """Batas yang berlaku untuk Image Converter."""
    return JSONResponse(content=_image_convert_limits_payload(), headers={"Cache-Control": "no-store"})


@app.post("/api/image/convert")
async def image_convert(
    request: Request,
    files: list[UploadFile] = File(default=[]),
    format: str = Form(default="jpeg"),
    quality: str | None = Form(default=None),
    width: str | None = Form(default=None),
):
    """Konversi satu gambar antar format (PNG/JPEG/WebP/SVG ⇒ PNG/JPEG/WebP).

    Field `width` (px) opsional dan hanya berlaku untuk masukan SVG.

    Respons: binary gambar, Content-Type sesuai format output,
    Content-Disposition: attachment; filename="hasil.<ext>".
    """
    started = time.perf_counter()

    uploads = [f for f in files if f is not None]
    check_image_file_count(len(uploads))
    _reject_oversized_image_content_length(request)

    payload = await _read_capped_image(uploads[0], IMG_MAX_BYTES)
    check_image_total_size(len(payload))

    norm_target = normalize_target(format)
    norm_quality = normalize_quality(quality)

    result = convert_image(payload, target=norm_target, quality=norm_quality, width=width)
    duration_ms = (time.perf_counter() - started) * 1000

    logger.info(
        "konversi selesai: in=%s out=%s piksel=%d byte=%d durasi=%.0fms",
        result.input_format,
        result.output_format,
        result.width * result.height,
        len(result.data),
        duration_ms,
    )

    ext = IMG_TARGETS[result.output_format].lstrip(".")
    media_type = IMG_MIME_TYPES[result.output_format]

    headers = {
        "Content-Disposition": f'attachment; filename="hasil.{ext}"',
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
        "X-Input-Format": result.input_format,
        "X-Output-Format": result.output_format,
        "X-Pixels": str(result.width * result.height),
        "X-Total-Bytes": str(len(result.data)),
        "X-Processing-Ms": f"{duration_ms:.0f}",
        "X-Scaled-Down": "true" if result.scaled_down else "false",
    }
    return Response(content=result.data, media_type=media_type, headers=headers)


@app.get("/api/word-count/limits")
async def word_count_limits() -> JSONResponse:
    """Batas yang berlaku untuk Word Counter."""
    return JSONResponse(content=_word_count_limits_payload(), headers={"Cache-Control": "no-store"})


@app.post("/api/word-count")
async def word_count(
    request: Request,
    text: str = Form(default=None),
):
    """Hitung kata, karakter, kalimat, dan perkiraan waktu baca di memori.

    Menerima multipart/form-data dengan field `text`.
    Respons: JSON application/json.
    Header: Cache-Control: no-store, no-cache, must-revalidate + Pragma: no-cache,
            X-Char-Count, X-Word-Count, X-Processing-Ms.
    """
    started = time.perf_counter()

    _reject_oversized_word_count_content_length(request)

    if text is None:
        form = await request.form()
        if "text" in form:
            text = ""
        else:
            raise WordCountError(WC_INVALID_REQUEST, "Field teks 'text' wajib disertakan.", 400)

    result = count_text(text)
    duration_ms = (time.perf_counter() - started) * 1000

    logger.info(
        "hitung kata selesai: kata=%d karakter=%d durasi=%.0fms",
        result.words,
        result.chars,
        duration_ms,
    )

    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
        "X-Char-Count": str(result.chars),
        "X-Word-Count": str(result.words),
        "X-Processing-Ms": f"{duration_ms:.0f}",
    }
    return JSONResponse(content=result.to_dict(), headers=headers)


@app.get("/api/case/limits")
async def case_convert_limits() -> JSONResponse:
    """Batas yang berlaku untuk Case Converter."""
    return JSONResponse(content=_case_convert_limits_payload(), headers={"Cache-Control": "no-store"})


@app.post("/api/case")
async def case_convert_endpoint(
    request: Request,
    text: str = Form(default=None),
    mode: str = Form(default=None),
):
    """Ubah format huruf teks di memori sesuai mode yang dipilih.

    Menerima multipart/form-data dengan field `text` dan `mode`.
    Respons: JSON application/json.
    Header: Cache-Control: no-store, no-cache, must-revalidate + Pragma: no-cache,
            X-Case-Mode, X-Char-Count, X-Processing-Ms.
    """
    started = time.perf_counter()

    _reject_oversized_case_content_length(request)

    if text is None or mode is None:
        form = await request.form()
        if text is None and "text" in form:
            text = ""
        if mode is None and "mode" in form:
            mode = ""

    result = convert_case(text, mode)
    duration_ms = (time.perf_counter() - started) * 1000

    logger.info(
        "ubah huruf selesai: mode=%s chars_in=%d chars_out=%d durasi=%.0fms",
        result.mode,
        result.chars_in,
        result.chars_out,
        duration_ms,
    )

    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
        "X-Case-Mode": result.mode,
        "X-Char-Count": str(result.chars_out),
        "X-Processing-Ms": f"{duration_ms:.0f}",
    }
    return JSONResponse(content=result.to_dict(), headers=headers)


@app.get("/api/ocr/limits")
async def ocr_limits() -> JSONResponse:
    """Batas yang berlaku untuk OCR."""
    return JSONResponse(
        content={
            "max_bytes": OCR_MAX_BYTES,
            "max_pages": OCR_MAX_PAGES,
            "languages": [{"value": k, "label": v} for k, v in OCR_LANGUAGES.items()],
            "time_limit_seconds": OCR_TIME_LIMIT_SECONDS,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/ocr")
async def ocr_endpoint(
    request: Request,
    file: UploadFile = File(...),
    lang: str = Form(default=None),
):
    """Ambil teks dari gambar atau dokumen PDF di memori.

    Menerima multipart/form-data dengan field `file` dan opsional `lang`.
    Respons: JSON application/json.
    Header: Cache-Control: no-store, no-cache, must-revalidate + Pragma: no-cache,
            X-Page-Count, X-Char-Count, X-Processing-Ms, X-Ocr-Lang.
    """
    raw_cl = request.headers.get("content-length")
    if raw_cl:
        try:
            declared = int(raw_cl)
            if declared > OCR_MAX_BYTES + CONTENT_LENGTH_SLACK:
                raise OcrError(OCR_TOO_LARGE, "Ukuran berkas lebih dari 20 MB.", 413)
        except ValueError:
            pass

    chunks: list[bytes] = []
    total_bytes = 0
    while True:
        chunk = await file.read(OCR_CHUNK_SIZE)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > OCR_MAX_BYTES:
            raise OcrError(OCR_TOO_LARGE, "Ukuran berkas lebih dari 20 MB.", 413)
        chunks.append(chunk)

    data = b"".join(chunks)
    if len(data) == 0:
        raise OcrError("EMPTY_FILE", "Berkasnya kosong.", 400)

    if not _ocr_semaphore.acquire(blocking=False):
        raise OcrError("BUSY", "Masih ada proses lain yang sedang berjalan. Coba lagi sebentar.", 429)

    try:
        result = await run_in_threadpool(run_ocr, data, lang)
    finally:
        _ocr_semaphore.release()

    logger.info(
        "ambil teks selesai: pages=%d chars=%d durasi=%dms lang=%s",
        result.pages,
        result.chars,
        result.duration_ms,
        result.language,
    )

    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
        "X-Page-Count": str(result.pages),
        "X-Char-Count": str(result.chars),
        "X-Processing-Ms": str(result.duration_ms),
        "X-Ocr-Lang": result.language,
    }
    return JSONResponse(content=result.to_dict(), headers=headers)


@app.get("/api/base64/limits")
async def base64_limits() -> JSONResponse:
    """Batas yang berlaku untuk Base64."""
    return JSONResponse(content=_base64_limits_payload(), headers={"Cache-Control": "no-store"})


@app.post("/api/base64")
async def base64_endpoint(
    request: Request,
    text: str = Form(default=None),
    mode: str = Form(default=None),
    variant: str | None = Form(default=None),
    wrap: str | None = Form(default=None),
):
    """Ubah teks jadi Base64 atau sebaliknya di memori.

    Menerima multipart/form-data dengan field `text`, `mode`, serta opsional `variant` dan `wrap`.
    Respons: JSON application/json.
    Header: Cache-Control: no-store, no-cache, must-revalidate + Pragma: no-cache,
            X-Base64-Mode, X-Output-Length, X-Processing-Ms.
    """
    started = time.perf_counter()

    _reject_oversized_base64_content_length(request)

    if text is None or mode is None:
        form = await request.form()
        if text is None and "text" in form:
            text = ""
        if mode is None and "mode" in form:
            mode = ""

    result = convert_base64(text, mode, variant=variant, wrap=wrap)
    duration_ms = (time.perf_counter() - started) * 1000

    logger.info(
        "base64 selesai: mode=%s variant=%s wrap=%d chars_in=%d chars_out=%d durasi=%.0fms",
        result.mode,
        result.variant,
        result.wrap,
        result.chars_in,
        result.chars_out,
        duration_ms,
    )

    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
        "X-Base64-Mode": result.mode,
        "X-Output-Length": str(result.chars_out),
        "X-Processing-Ms": f"{duration_ms:.0f}",
    }
    return JSONResponse(content=result.to_dict(), headers=headers)


@app.get("/")
async def root() -> dict:
    """Info singkat service (bukan halaman web)."""
    return {
        "service": SERVICE_NAME,
        "version": __version__,
        "docs": "/docs",
        "tools": ["pdf-merge", "image-convert", "word-count", "case-convert", "ocr", "base64"],
    }




