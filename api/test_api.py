"""Uji otomatis OmniTools API — Merge PDF.

Bisa dijalankan dua cara:

1. Skrip mandiri (tanpa pytest, tanpa dependensi tambahan):
       cd api && python3 test_api.py
   Menguji logika murni (pdf_merge) + endpoint HTTP via TestClient bila `httpx`
   tersedia + endpoint HTTP langsung bila env OMNITOOLS_API_URL diisi.

2. Sebagai pytest biasa:
       cd api && python3 -m pytest test_api.py -v

Keluar dengan status 1 bila ada uji yang gagal.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from PIL import Image, ImageDraw  # noqa: E402
import pymupdf  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

from app import __version__  # noqa: E402
from app.image_convert import (  # noqa: E402
    EMPTY_FILE as IMG_EMPTY_FILE,
    IMAGE_TOO_LARGE as IMG_IMAGE_TOO_LARGE,
    IMAGE_UNREADABLE as IMG_IMAGE_UNREADABLE,
    INVALID_QUALITY as IMG_INVALID_QUALITY,
    INVALID_SVG as IMG_INVALID_SVG,
    INVALID_WIDTH as IMG_INVALID_WIDTH,
    MAX_BYTES as IMG_MAX_BYTES,
    MAX_FILES as IMG_MAX_FILES,
    MAX_PIXELS as IMG_MAX_PIXELS,
    NO_FILES as IMG_NO_FILES,
    NOT_IMAGE as IMG_NOT_IMAGE,
    PAYLOAD_TOO_LARGE as IMG_PAYLOAD_TOO_LARGE,
    QUALITY_DEFAULT as IMG_QUALITY_DEFAULT,
    QUALITY_MAX as IMG_QUALITY_MAX,
    QUALITY_MIN as IMG_QUALITY_MIN,
    SVG_DEFAULT_WIDTH as IMG_SVG_DEFAULT_WIDTH,
    SVG_MAX_SIDE as IMG_SVG_MAX_SIDE,
    SVG_MAX_WIDTH as IMG_SVG_MAX_WIDTH,
    TARGETS as IMG_TARGETS,
    TOO_MANY_FILES as IMG_TOO_MANY_FILES,
    UNSAFE_SVG as IMG_UNSAFE_SVG,
    UNSUPPORTED_TARGET as IMG_UNSUPPORTED_TARGET,
    ImageConvertError,
    check_file_count as check_image_file_count,
    check_total_size as check_image_total_size,
    convert_image,
    detect_format,
    is_supported_image,
    normalize_quality,
    normalize_target,
)
from app.pdf_merge import (  # noqa: E402
    ERR_EMPTY_FILE,
    ERR_ENCRYPTED,
    ERR_NOT_PDF,
    ERR_NO_FILES,
    ERR_TOO_LARGE,
    ERR_TOO_MANY_FILES,
    ERR_TOO_MANY_PAGES,
    ERR_UNREADABLE,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    MAX_TOTAL_PAGES,
    PdfMergeError,
    check_total_size,
    is_pdf_bytes,
    merge_pdfs,
)
from app.word_count import (  # noqa: E402
    INVALID_REQUEST as WC_INVALID_REQUEST,
    MAX_BYTES as WC_MAX_BYTES,
    MAX_CHARS as WC_MAX_CHARS,
    NO_TEXT as WC_NO_TEXT,
    STOP_WORDS as WC_STOP_WORDS,
    TOO_LONG as WC_TOO_LONG,
    WordCountError,
    WordCountResult,
    count_text,
    validate_text,
)
from app.case_convert import (  # noqa: E402
    CHUNK_SIZE as CC_CHUNK_SIZE,
    INVALID_REQUEST as CC_INVALID_REQUEST,
    MAX_BYTES as CC_MAX_BYTES,
    MAX_CHARS as CC_MAX_CHARS,
    MODE_ORDER as CC_MODE_ORDER,
    MODES as CC_MODES,
    NO_TEXT as CC_NO_TEXT,
    TOO_LONG as CC_TOO_LONG,
    UNSUPPORTED_MODE as CC_UNSUPPORTED_MODE,
    CaseConvertError,
    CaseConvertResult,
    convert_case,
    normalize_mode,
    validate_text as validate_case_text,
)
from app.ocr import (  # noqa: E402
    BUSY as OCR_BUSY,
    DAMAGED_FILE as OCR_DAMAGED_FILE,
    DEFAULT_LANG as OCR_DEFAULT_LANG,
    EMPTY_FILE as OCR_EMPTY_FILE,
    INVALID_LANG as OCR_INVALID_LANG,
    LANGUAGES as OCR_LANGUAGES,
    LANGS as OCR_LANGS,
    MAX_BYTES as OCR_MAX_BYTES,
    MAX_PAGES as OCR_MAX_PAGES,
    NO_FILE as OCR_NO_FILE,
    OCR_FAILED,
    OCR_TIMEOUT,
    TIME_LIMIT_SECONDS as OCR_TIME_LIMIT_SECONDS,
    TOO_LARGE as OCR_TOO_LARGE,
    TOO_MANY_PAGES as OCR_TOO_MANY_PAGES,
    UNSUPPORTED_FILE as OCR_UNSUPPORTED_FILE,
    OcrError,
    OcrResult,
    run_ocr,
)
from app.base64_tool import (  # noqa: E402
    CHUNK_SIZE as B64_CHUNK_SIZE,
    INVALID_BASE64 as B64_INVALID_BASE64,
    INVALID_REQUEST as B64_INVALID_REQUEST,
    INVALID_VARIANT as B64_INVALID_VARIANT,
    INVALID_WRAP as B64_INVALID_WRAP,
    MAX_BYTES as B64_MAX_BYTES,
    MAX_CHARS as B64_MAX_CHARS,
    MODES as B64_MODES,
    NO_TEXT as B64_NO_TEXT,
    NOT_TEXT as B64_NOT_TEXT,
    TOO_LONG as B64_TOO_LONG,
    UNSUPPORTED_MODE as B64_UNSUPPORTED_MODE,
    VARIANTS as B64_VARIANTS,
    WRAP_OPTIONS as B64_WRAP_OPTIONS,
    Base64Result,
    Base64ToolError,
    convert_base64,
    normalize_mode as normalize_base64_mode,
    normalize_variant as normalize_base64_variant,
    normalize_wrap as normalize_base64_wrap,
    validate_text as validate_base64_text,
)

SKIPPED: list[str] = []


# --- Pembantu ----------------------------------------------------------------
def make_pdf(pages: int, label: str = "") -> bytes:
    """PDF uji di memori dengan jumlah halaman tertentu."""
    writer = PdfWriter()
    for index in range(pages):
        writer.add_blank_page(width=200, height=200)
    if label:
        writer.add_metadata({"/Title": label})
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_encrypted_pdf(pages: int = 1, password: str = "rahasia") -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    writer.encrypt(password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def page_count(data: bytes) -> int:
    return len(PdfReader(io.BytesIO(data)).pages)


def make_image(format: str = "PNG", size: tuple[int, int] = (60, 60), color: str = "blue", mode: str | None = None) -> bytes:
    """Buat berkas gambar uji di memori."""
    img_mode = mode or ("RGBA" if "A" in format.upper() else "RGB")
    img = Image.new(img_mode, size, color)
    buf = io.BytesIO()
    save_fmt = "JPEG" if format.upper() in ("JPG", "JPEG") else format.upper()
    img.save(buf, format=save_fmt)
    return buf.getvalue()


def make_svg(width: int | None = 200, height: int | None = 100) -> bytes:
    """SVG uji dengan gradasi + teks. Tanpa width/height bila argumen None."""
    dims = ""
    if width is not None and height is not None:
        dims = f' width="{width}" height="{height}"'
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"{dims} viewBox="0 0 200 100">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="red"/>
      <stop offset="100%" stop-color="blue"/>
    </linearGradient>
  </defs>
  <rect width="200" height="100" fill="url(#g)"/>
  <text x="10" y="50" font-size="20" fill="white">Hi</text>
</svg>""".encode("utf-8")


def make_ocr_png(text: str = "KUCING OREN") -> bytes:
    """Buat berkas PNG uji berisi teks jelas (font bawaan, kontras tinggi)."""
    img = Image.new("RGB", (400, 120), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((30, 40), text, fill="black")
    img_large = img.resize((800, 240), Image.Resampling.NEAREST)
    buf = io.BytesIO()
    img_large.save(buf, format="PNG")
    return buf.getvalue()


def make_ocr_pdf(page1_text: str = "SURAT SATU", page2_text: str = "BERKAS DUA") -> bytes:
    """Buat dokumen PDF uji 2 halaman dengan PyMuPDF berisi teks berbeda per halaman."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=300, height=100)
    p1.insert_text((30, 50), page1_text, fontsize=24, color=(0, 0, 0))
    p2 = doc.new_page(width=300, height=100)
    p2.insert_text((30, 50), page2_text, fontsize=24, color=(0, 0, 0))
    data = doc.tobytes()
    doc.close()
    return data


def make_many_page_pdf(pages: int = 16) -> bytes:
    """Buat dokumen PDF dengan sejumlah halaman tertentu."""
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=200, height=200)
    data = doc.tobytes()
    doc.close()
    return data



def expect_image_error(func, code: str, status: int) -> ImageConvertError:
    """Pastikan func() melempar ImageConvertError dengan kode + status yang tepat."""
    try:
        func()
    except ImageConvertError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar ImageConvertError {code}")


def expect_error(func, code: str, status: int) -> PdfMergeError:
    """Pastikan func() melempar PdfMergeError dengan kode + status yang tepat."""
    try:
        func()
    except PdfMergeError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar PdfMergeError {code}")


def expect_word_count_error(func, code: str, status: int) -> WordCountError:
    """Pastikan func() melempar WordCountError dengan kode + status yang tepat."""
    try:
        func()
    except WordCountError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar WordCountError {code}")


def expect_case_convert_error(func, code: str, status: int) -> CaseConvertError:
    """Pastikan func() melempar CaseConvertError dengan kode + status yang tepat."""
    try:
        func()
    except CaseConvertError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar CaseConvertError {code}")


def expect_base64_error(func, code: str, status: int) -> Base64ToolError:
    """Pastikan func() melempar Base64ToolError dengan kode dan status yang tepat."""
    try:
        func()
    except Base64ToolError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar Base64ToolError {code}")




# --- Uji logika murni --------------------------------------------------------
def test_magic_bytes_menerima_pdf_asli_menolak_palsu() -> None:
    assert is_pdf_bytes(make_pdf(1)) is True
    assert is_pdf_bytes(b"") is False
    assert is_pdf_bytes(b"ini file txt yang dinamai .pdf") is False
    assert is_pdf_bytes(b"%PDF-1.4\n") is True  # header saja: format benar, isi nanti dinilai


def test_merge_dua_dan_tiga_halaman_menjadi_lima() -> None:
    a = make_pdf(2, "A")
    b = make_pdf(3, "B")
    result = merge_pdfs([a, b])
    assert result.file_count == 2
    assert result.page_count == 5, f"total halaman {result.page_count}, diharapkan 5"
    assert result.page_counts == (2, 3)
    assert result.passthrough is False
    assert page_count(result.data) == 5
    assert result.data.startswith(b"%PDF-")


def test_urutan_berkas_diikuti() -> None:
    """Urutan kiriman menentukan urutan halaman (2+3 vs 3+2)."""
    a = make_pdf(2)
    b = make_pdf(3)
    assert merge_pdfs([a, b]).page_counts == (2, 3)
    assert merge_pdfs([b, a]).page_counts == (3, 2)


def test_satu_berkas_dikembalikan_apa_adanya() -> None:
    a = make_pdf(4)
    result = merge_pdfs([a])
    assert result.passthrough is True
    assert result.data == a, "berkas tunggal harus byte-identik"
    assert result.page_count == 4


def test_menolak_bukan_pdf() -> None:
    expect_error(lambda: merge_pdfs([b"bukan pdf sama sekali"]), ERR_NOT_PDF, 400)


def test_menolak_berkas_kosong() -> None:
    expect_error(lambda: merge_pdfs([b""]), ERR_EMPTY_FILE, 400)


def test_menolak_tanpa_berkas() -> None:
    expect_error(lambda: merge_pdfs([]), ERR_NO_FILES, 400)


def test_menolak_lebih_dari_sepuluh_berkas() -> None:
    payloads = [make_pdf(1) for _ in range(MAX_FILES + 1)]
    expect_error(lambda: merge_pdfs(payloads), ERR_TOO_MANY_FILES, 400)


def test_sepuluh_berkas_masih_diterima() -> None:
    payloads = [make_pdf(1) for _ in range(MAX_FILES)]
    result = merge_pdfs(payloads)
    assert result.file_count == MAX_FILES
    assert result.page_count == MAX_FILES


def test_menolak_total_ukuran_lewat_batas() -> None:
    check_total_size(MAX_TOTAL_BYTES)  # tepat di batas: boleh
    expect_error(lambda: check_total_size(MAX_TOTAL_BYTES + 1), ERR_TOO_LARGE, 413)
    besar = b"%PDF-1.4\n" + b"0" * (MAX_TOTAL_BYTES + 1024)
    expect_error(lambda: merge_pdfs([besar]), ERR_TOO_LARGE, 413)


def test_menolak_lebih_dari_dua_ratus_halaman() -> None:
    banyak = make_pdf(MAX_TOTAL_PAGES + 1)
    expect_error(lambda: merge_pdfs([banyak]), ERR_TOO_MANY_PAGES, 413)


def test_menolak_pdf_rusak() -> None:
    rusak = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog\n" + b"x" * 200
    expect_error(lambda: merge_pdfs([rusak]), ERR_UNREADABLE, 422)


def test_menolak_pdf_terproteksi_sandi() -> None:
    expect_error(lambda: merge_pdfs([make_encrypted_pdf(1)]), ERR_ENCRYPTED, 422)


# --- Uji logika Image Converter ---------------------------------------------
def test_image_magic_bytes_detection() -> None:
    png_data = make_image("PNG")
    jpeg_data = make_image("JPEG")
    webp_data = make_image("WEBP")

    assert detect_format(png_data) == "png"
    assert detect_format(jpeg_data) == "jpeg"
    assert detect_format(webp_data) == "webp"
    assert is_supported_image(png_data) is True
    assert is_supported_image(jpeg_data) is True
    assert is_supported_image(webp_data) is True

    assert detect_format(b"") is None
    assert detect_format(b"bukan gambar") is None
    assert is_supported_image(b"bukan gambar") is False


def test_image_convert_png_ke_jpeg_sukses() -> None:
    png = make_image("PNG", size=(50, 50), color="green")
    result = convert_image(png, target="jpeg", quality=85)
    assert result.input_format == "png"
    assert result.output_format == "jpeg"
    assert result.width == 50
    assert result.height == 50
    assert result.data.startswith(b"\xff\xd8\xff")
    assert detect_format(result.data) == "jpeg"


def test_image_convert_jpeg_ke_webp_sukses() -> None:
    jpeg = make_image("JPEG", size=(40, 40), color="red")
    result = convert_image(jpeg, target="webp", quality=80)
    assert result.input_format == "jpeg"
    assert result.output_format == "webp"
    assert detect_format(result.data) == "webp"


def test_image_convert_png_ke_png_sukses() -> None:
    png = make_image("PNG", size=(30, 30), color="yellow")
    result = convert_image(png, target="png")
    assert result.input_format == "png"
    assert result.output_format == "png"
    assert detect_format(result.data) == "png"


def test_image_convert_format_target_sama_dengan_masukan() -> None:
    jpeg = make_image("JPEG", size=(35, 35), color="blue")
    result_jpeg = convert_image(jpeg, target="jpeg")
    assert result_jpeg.output_format == "jpeg"

    webp = make_image("WEBP", size=(35, 35), color="cyan")
    result_webp = convert_image(webp, target="webp")
    assert result_webp.output_format == "webp"


def test_image_convert_kualitas_rendah_lebih_kecil_dari_kualitas_tinggi() -> None:
    img = Image.new("RGB", (120, 120))
    pixels = img.load()
    for x in range(120):
        for y in range(120):
            pixels[x, y] = ((x * 7) % 256, (y * 11) % 256, ((x + y) * 13) % 256)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    png_bytes = buf.getvalue()

    res_q20 = convert_image(png_bytes, target="jpeg", quality=20)
    res_q95 = convert_image(png_bytes, target="jpeg", quality=95)
    assert len(res_q20.data) < len(res_q95.data), (
        f"Kualitas 20 ({len(res_q20.data)} bytes) harus lebih kecil dari 95 ({len(res_q95.data)} bytes)"
    )


def test_image_convert_alpha_ke_jpeg_latar_putih() -> None:
    img = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    png_transparent = buf.getvalue()

    result = convert_image(png_transparent, target="jpeg")
    assert result.output_format == "jpeg"
    out_img = Image.open(io.BytesIO(result.data))
    assert out_img.mode == "RGB"
    assert out_img.getpixel((0, 0)) == (255, 255, 255)


def test_image_convert_menolak_tanpa_berkas() -> None:
    expect_image_error(lambda: check_image_file_count(0), IMG_NO_FILES, 400)


def test_image_convert_menolak_dua_berkas() -> None:
    expect_image_error(lambda: check_image_file_count(2), IMG_TOO_MANY_FILES, 400)


def test_image_convert_menolak_berkas_kosong() -> None:
    expect_image_error(lambda: convert_image(b""), IMG_EMPTY_FILE, 400)


def test_image_convert_menolak_bukan_gambar() -> None:
    expect_image_error(lambda: convert_image(b"ini berkas teks yang dinamai gambar.png"), IMG_NOT_IMAGE, 400)


def test_image_convert_menolak_target_tidak_didukung() -> None:
    png = make_image("PNG")
    expect_image_error(lambda: convert_image(png, target="gif"), IMG_UNSUPPORTED_TARGET, 400)
    expect_image_error(lambda: convert_image(png, target="tiff"), IMG_UNSUPPORTED_TARGET, 400)


def test_image_convert_menolak_kualitas_tidak_valid() -> None:
    png = make_image("PNG")
    expect_image_error(lambda: convert_image(png, quality=0), IMG_INVALID_QUALITY, 400)
    expect_image_error(lambda: convert_image(png, quality=101), IMG_INVALID_QUALITY, 400)
    expect_image_error(lambda: convert_image(png, quality="abc"), IMG_INVALID_QUALITY, 400)


def test_image_convert_menolak_gambar_rusak() -> None:
    corrupted = b"\x89PNG\r\n\x1a\n" + b"xyz" * 50
    expect_image_error(lambda: convert_image(corrupted, target="jpeg"), IMG_IMAGE_UNREADABLE, 422)


def test_image_convert_menolak_ukuran_lewat_batas() -> None:
    expect_image_error(lambda: check_image_total_size(IMG_MAX_BYTES + 1), IMG_PAYLOAD_TOO_LARGE, 413)


def test_image_convert_svg_20000x20000_diperkecil() -> None:
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="20000" height="20000">'
        b'<rect width="20000" height="20000" fill="blue"/>'
        b'</svg>'
    )
    res = convert_image(svg, target="png")
    assert res.scaled_down is True
    assert res.width * res.height <= IMG_MAX_PIXELS
    assert max(res.width, res.height) <= IMG_SVG_MAX_SIDE


def test_image_convert_svg_ekstrem_400000x1_diperkecil() -> None:
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="400000" height="1">'
        b'<rect width="400000" height="1" fill="red"/>'
        b'</svg>'
    )
    res = convert_image(svg, target="png")
    assert res.scaled_down is True
    assert max(res.width, res.height) <= IMG_SVG_MAX_SIDE
    assert res.width * res.height <= IMG_MAX_PIXELS


def test_image_convert_svg_viewbox_200x100_tanpa_width() -> None:
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">'
        b'<rect width="200" height="100" fill="green"/>'
        b'</svg>'
    )
    res = convert_image(svg, target="png")
    assert res.scaled_down is False
    assert (res.width, res.height) == (1024, 512)


def test_image_convert_svg_1500x800_tanpa_width() -> None:
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="800">'
        b'<rect width="1500" height="800" fill="blue"/>'
        b'</svg>'
    )
    res = convert_image(svg, target="png")
    assert res.scaled_down is False
    assert (res.width, res.height) == (1500, 800)


def test_image_convert_svg_24x24_viewbox_saja() -> None:
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<circle cx="12" cy="12" r="10" fill="red"/>'
        b'</svg>'
    )
    res = convert_image(svg, target="png")
    assert res.scaled_down is False
    assert (res.width, res.height) == (1024, 1024)


def test_image_convert_svg_600x300_tanpa_width() -> None:
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300">'
        b'<rect width="600" height="300" fill="green"/>'
        b'</svg>'
    )
    res = convert_image(svg, target="png")
    assert res.scaled_down is False
    assert (res.width, res.height) == (1024, 512)


def test_image_convert_svg_600x300_width_400() -> None:
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300">'
        b'<rect width="600" height="300" fill="green"/>'
        b'</svg>'
    )
    res = convert_image(svg, target="png", width=400)
    assert res.scaled_down is False
    assert (res.width, res.height) == (400, 200)


# --- Uji logika Word Counter ------------------------------------------------
def test_word_count_logika_teks_normal() -> None:
    res = count_text("Halo dunia. Ini uji coba!")
    assert res.chars == 25
    assert res.chars_no_spaces == 21
    assert res.words == 5
    assert res.unique_words == 5
    assert res.sentences == 2
    assert res.paragraphs == 1
    assert res.lines == 1
    assert res.reading_minutes == 1
    assert res.speaking_minutes == 1
    assert res.longest_word == "dunia"
    # 'ini' dan 'uji' < 4 huruf, jadi tidak masuk top_words
    top_dict = {item["word"]: item["count"] for item in res.top_words}
    assert top_dict == {"halo": 1, "dunia": 1, "coba": 1}


def test_word_count_logika_paragraf_dan_baris() -> None:
    text = (
        "Paragraf pertama terdiri dari dua baris.\n"
        "Ini baris kedua pada paragraf pertama.\n\n"
        "Paragraf kedua hanya satu baris.\n\n\n"
        "Paragraf ketiga adalah penutup."
    )
    res = count_text(text)
    assert res.paragraphs == 3
    assert res.lines == 4
    assert res.sentences == 4


def test_word_count_logika_case_insensitive_dan_top_words() -> None:
    # "Kucing" ditulis dengan variasi kapital, stop words Indonesia ("dan", "di", "itu") diabaikan
    text = "Kucing makan ikan. kucing dan KUCING tidur di kasur itu! Ikan sangat lezat."
    res = count_text(text)
    assert res.words == 13
    # unique_words tidak peka huruf besar-kecil
    lower_set = {
        "kucing", "makan", "ikan", "dan", "tidur", "di", "kasur", "itu", "sangat", "lezat"
    }
    assert res.unique_words == len(lower_set)
    # top_words: 'kucing' 3 kali, 'ikan' 2 kali; stopword 'dan', 'di', 'itu' tidak muncul
    top_dict = {item["word"]: item["count"] for item in res.top_words}
    assert top_dict["kucing"] == 3
    assert top_dict["ikan"] == 2
    for sw in WC_STOP_WORDS:
        assert sw not in top_dict


def test_word_count_logika_waktu_baca_dan_bicara() -> None:
    # 250 kata: waktu baca ceil(250/200) = 2 menit, waktu bicara ceil(250/130) = 2 menit
    words_250 = " ".join(["kata"] * 250)
    res = count_text(words_250)
    assert res.words == 250
    assert res.reading_minutes == 2
    assert res.speaking_minutes == 2

    # 1 kata: minimal 1 menit
    res_one = count_text("Satu")
    assert res_one.words == 1
    assert res_one.reading_minutes == 1
    assert res_one.speaking_minutes == 1


def test_word_count_logika_kata_terpanjang_seri() -> None:
    # Bila ada beberapa kata dengan panjang sama, kata pertama yang ditemukan dipilih
    res = count_text("satu dua tiga")  # 'satu' dan 'tiga' sama-sama 4 huruf
    assert res.longest_word == "satu"


def test_word_count_logika_menolak_teks_kosong() -> None:
    expect_word_count_error(lambda: count_text(""), WC_NO_TEXT, 400)


def test_word_count_logika_menolak_hanya_spasi() -> None:
    expect_word_count_error(lambda: count_text("   \n\t  "), WC_NO_TEXT, 400)


def test_word_count_logika_menolak_terlalu_panjang() -> None:
    long_text = "a" * (WC_MAX_CHARS + 1)
    expect_word_count_error(lambda: count_text(long_text), WC_TOO_LONG, 413)


def test_word_count_logika_menolak_none() -> None:
    expect_word_count_error(lambda: count_text(None), WC_INVALID_REQUEST, 400)  # type: ignore[arg-type]


def test_case_convert_logika_semua_mode() -> None:
    # Uji 10 mode menghasilkan keluaran yang benar sesuai spesifikasi
    assert convert_case("halo dunia", "upper").text == "HALO DUNIA"
    assert convert_case("HALO DUNIA", "lower").text == "halo dunia"
    assert convert_case("halo dunia don't stop dua-tiga", "title").text == "Halo Dunia Don't Stop Dua-tiga"
    assert convert_case("halo dunia. apa kabar? baik! tentu saja.\nbaris baru", "sentence").text == (
        "Halo dunia. Apa kabar? Baik! Tentu saja.\nBaris baru"
    )
    assert convert_case("Halo Dunia 123", "inverse").text == "hALO dUNIA 123"
    assert convert_case("abcd", "alternating").text == "aBcD"
    assert convert_case("a b c d", "alternating").text == "a B c D"
    assert convert_case("halo dunia", "camel").text == "haloDunia"
    assert convert_case("halo dunia", "snake").text == "halo_dunia"
    assert convert_case("halo dunia", "kebab").text == "halo-dunia"
    assert convert_case("Halo, Dunia! 2x", "slug").text == "halo-dunia-2x"


def test_case_convert_logika_changed() -> None:
    res_unchanged = convert_case("halo dunia", "lower")
    assert res_unchanged.changed is False
    res_changed = convert_case("halo dunia", "upper")
    assert res_changed.changed is True


def test_case_convert_logika_menolak_teks_kosong() -> None:
    expect_case_convert_error(lambda: convert_case("", "upper"), CC_NO_TEXT, 400)


def test_case_convert_logika_menolak_hanya_spasi() -> None:
    expect_case_convert_error(lambda: convert_case("   \n\t  ", "upper"), CC_NO_TEXT, 400)


def test_case_convert_logika_menolak_terlalu_panjang() -> None:
    long_text = "a" * (CC_MAX_CHARS + 1)
    expect_case_convert_error(lambda: convert_case(long_text, "upper"), CC_TOO_LONG, 413)


def test_case_convert_logika_menolak_none_text() -> None:
    expect_case_convert_error(lambda: convert_case(None, "upper"), CC_INVALID_REQUEST, 400)


def test_case_convert_logika_mode_tidak_valid() -> None:
    expect_case_convert_error(lambda: convert_case("halo", None), CC_INVALID_REQUEST, 400)
    expect_case_convert_error(lambda: convert_case("halo", ""), CC_INVALID_REQUEST, 400)
    expect_case_convert_error(lambda: convert_case("halo", "mode_palsu"), CC_UNSUPPORTED_MODE, 400)


def test_base64_logika_encode_biasa() -> None:
    import base64
    text = "Halo, dunia!"
    res = convert_base64(text, "encode")
    expected = base64.b64encode(text.encode("utf-8")).decode("ascii")
    assert res.text == expected
    assert res.mode == "encode"
    assert res.variant == "standard"
    assert res.wrap == 0
    assert res.chars_in == len(text)
    assert res.bytes_in == len(text.encode("utf-8"))
    assert res.chars_out == len(expected)
    assert res.bytes_out == len(expected.encode("utf-8"))
    assert res.changed is True


def test_base64_logika_encode_aksen_dan_emoji() -> None:
    import base64
    text = "Halo dunia! 🌟 café & résumé ☕"
    res = convert_base64(text, "encode")
    expected = base64.b64encode(text.encode("utf-8")).decode("ascii")
    assert res.text == expected


def test_base64_logika_urlsafe_encode() -> None:
    import base64
    text = ">>> ??? ~~~"
    res_std = convert_base64(text, "encode", variant="standard")
    res_url = convert_base64(text, "encode", variant="urlsafe")
    expected_url = base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")
    assert res_url.text == expected_url
    assert "+" in res_std.text or "/" in res_std.text
    assert "-" in res_url.text or "_" in res_url.text
    assert "+" not in res_url.text and "/" not in res_url.text


def test_base64_logika_wrap_76() -> None:
    import base64
    text = "Kalimat panjang yang menghasilkan Base64 lebih dari 76 karakter untuk memastikan pemotongan baris tepat."
    res = convert_base64(text, "encode", wrap=76)
    lines = res.text.split("\n")
    assert len(lines) > 1
    for line in lines:
        assert len(line) <= 76
    expected_full = base64.b64encode(text.encode("utf-8")).decode("ascii")
    assert "".join(lines) == expected_full


def test_base64_logika_wrap_64() -> None:
    text = "Kalimat panjang yang menghasilkan Base64 lebih dari 64 karakter untuk verifikasi."
    res = convert_base64(text, "encode", wrap=64)
    lines = res.text.split("\n")
    assert len(lines) > 1
    for line in lines:
        assert len(line) <= 64


def test_base64_logika_decode_bolak_balik() -> None:
    samples = [
        "Halo, dunia!",
        "Selamat pagi, apa kabar?",
        "Teks berbaris satu\nbaris dua\nbaris tiga",
        "Emoji test 🚀🔥🌈",
    ]
    for sample in samples:
        enc = convert_base64(sample, "encode")
        dec = convert_base64(enc.text, "decode")
        assert dec.text == sample
        assert dec.mode == "decode"
        assert dec.chars_out == len(sample)


def test_base64_logika_decode_toleran() -> None:
    import base64
    text = "Halo, dunia!"
    raw_b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")

    # Data URI prefix
    data_uri = f"data:text/plain;base64,{raw_b64}"
    assert convert_base64(data_uri, "decode").text == text

    # Whitespace dan baris baru
    with_spaces = f" \n\t {raw_b64[:4]} \n {raw_b64[4:]} \t\n "
    assert convert_base64(with_spaces, "decode").text == text

    # Padding hilang
    unpadded = raw_b64.rstrip("=")
    assert convert_base64(unpadded, "decode").text == text

    # Kombinasi data URI, spasi, dan tanpa padding
    combo = f" data:text/plain;base64, \n {unpadded} \t\n "
    assert convert_base64(combo, "decode").text == text


def test_base64_logika_decode_urlsafe_alfabet() -> None:
    text = ">>> ??? ~~~"
    enc_url = convert_base64(text, "encode", variant="urlsafe")
    assert ("-" in enc_url.text) or ("_" in enc_url.text)
    dec = convert_base64(enc_url.text, "decode")
    assert dec.text == text


def test_base64_logika_menolak_teks_kosong_dan_spasi() -> None:
    expect_base64_error(lambda: convert_base64("", "encode"), B64_NO_TEXT, 400)
    expect_base64_error(lambda: convert_base64("   \n\t  ", "encode"), B64_NO_TEXT, 400)
    expect_base64_error(lambda: convert_base64("", "decode"), B64_NO_TEXT, 400)
    expect_base64_error(lambda: convert_base64("data:text/plain;base64,", "decode"), B64_NO_TEXT, 400)


def test_base64_logika_menolak_none_text() -> None:
    expect_base64_error(lambda: convert_base64(None, "encode"), B64_INVALID_REQUEST, 400)
    expect_base64_error(lambda: convert_base64(None, "decode"), B64_INVALID_REQUEST, 400)


def test_base64_logika_menolak_invalid_base64() -> None:
    # Karakter di luar alfabet Base64
    expect_base64_error(lambda: convert_base64("Halo Dunia!", "decode"), B64_INVALID_BASE64, 400)
    # Panjang mustahil (sisa 1 karakter)
    expect_base64_error(lambda: convert_base64("A", "decode"), B64_INVALID_BASE64, 400)
    expect_base64_error(lambda: convert_base64("AAAAA", "decode"), B64_INVALID_BASE64, 400)
    # Samadengan di tengah atau salah posisi
    expect_base64_error(lambda: convert_base64("AA=A", "decode"), B64_INVALID_BASE64, 400)
    expect_base64_error(lambda: convert_base64("AAAA=", "decode"), B64_INVALID_BASE64, 400)


def test_base64_logika_mode_dan_opsi_tidak_valid() -> None:
    expect_base64_error(lambda: convert_base64("halo", None), B64_INVALID_REQUEST, 400)
    expect_base64_error(lambda: convert_base64("halo", ""), B64_INVALID_REQUEST, 400)
    expect_base64_error(lambda: convert_base64("halo", "mode_palsu"), B64_UNSUPPORTED_MODE, 400)
    expect_base64_error(lambda: convert_base64("halo", "encode", variant="invalid_var"), B64_INVALID_VARIANT, 400)
    expect_base64_error(lambda: convert_base64("halo", "encode", wrap=50), B64_INVALID_WRAP, 400)


def test_base64_logika_menolak_terlalu_panjang() -> None:
    long_text = "a" * (B64_MAX_CHARS + 1)
    expect_base64_error(lambda: convert_base64(long_text, "encode"), B64_TOO_LONG, 413)


def test_base64_logika_menolak_data_biner_bukan_teks() -> None:
    import base64
    binary_bytes = bytes(range(256))
    binary_b64 = base64.b64encode(binary_bytes).decode("ascii")
    expect_base64_error(lambda: convert_base64(binary_b64, "decode"), B64_NOT_TEXT, 400)




# --- Uji HTTP lewat TestClient (butuh httpx) ---------------------------------
def _test_client():
    try:
        from fastapi.testclient import TestClient
        from app.main import app
    except Exception as exc:  # httpx belum terpasang, dsb.
        SKIPPED.append(f"uji HTTP TestClient dilewati: {exc}")
        return None
    return TestClient(app)


def test_http_health() -> None:
    client = _test_client()
    if client is None:
        return
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "omnitools-api"
    assert body["version"] == __version__


def test_http_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/pdf/merge/limits")
    assert response.status_code == 200
    body = response.json()
    assert body["max_files"] == MAX_FILES
    assert body["max_total_mb"] == 25
    assert body["max_pages"] == MAX_TOTAL_PAGES
    assert response.headers["cache-control"] == "no-store"


def test_http_merge_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/pdf/merge",
        files=[
            ("files", ("a.pdf", make_pdf(2), "application/pdf")),
            ("files", ("b.pdf", make_pdf(3), "application/pdf")),
        ],
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert 'filename="gabungan.pdf"' in response.headers["content-disposition"]
    assert response.headers["cache-control"].startswith("no-store")
    assert response.headers["x-page-count"] == "5"
    assert response.headers["x-file-count"] == "2"
    assert page_count(response.content) == 5


def test_http_merge_txt_dinamai_pdf_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/pdf/merge",
        files=[("files", ("palsu.pdf", b"ini bukan pdf", "application/pdf"))],
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == ERR_NOT_PDF
    assert body["error"]["message"]


def test_http_merge_sebelas_berkas_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    files = [("files", (f"f{i}.pdf", make_pdf(1), "application/pdf")) for i in range(MAX_FILES + 1)]
    response = client.post("/api/pdf/merge", files=files)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == ERR_TOO_MANY_FILES


def test_http_merge_tanpa_berkas_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/pdf/merge", files=[])
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "NO_FILES"


def test_http_image_convert_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/image/convert/limits")
    assert response.status_code == 200
    body = response.json()
    assert body["max_files"] == IMG_MAX_FILES
    assert body["max_bytes"] == IMG_MAX_BYTES
    assert body["max_total_mb"] == 15
    assert body["max_pixels"] == IMG_MAX_PIXELS
    assert body["targets"] == ["jpeg", "png", "webp"]
    assert body["target_labels"]["jpeg"] == "JPG"
    assert body["quality_min"] == 10
    assert body["quality_max"] == 100
    assert body["quality_default"] == 85
    assert "svg" in body["inputs"]
    assert body["svgMaxWidth"] == IMG_SVG_MAX_WIDTH
    assert body["svgDefaultWidth"] == IMG_SVG_DEFAULT_WIDTH
    assert response.headers["cache-control"] == "no-store"


def test_http_image_convert_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    png_data = make_image("PNG", size=(60, 60), color="magenta")
    response = client.post(
        "/api/image/convert",
        files=[("files", ("test.png", png_data, "image/png"))],
        data={"format": "jpeg", "quality": "80"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/jpeg")
    assert 'filename="hasil.jpg"' in response.headers["content-disposition"]
    assert response.headers["cache-control"].startswith("no-store")
    assert response.headers["x-input-format"] == "png"
    assert response.headers["x-output-format"] == "jpeg"
    assert response.headers["x-pixels"] == "3600"
    assert response.headers["x-total-bytes"] == str(len(response.content))
    assert "x-processing-ms" in response.headers
    assert response.content.startswith(b"\xff\xd8\xff")


def test_http_image_convert_tanpa_berkas_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/image/convert", files=[])
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_NO_FILES


def test_http_image_convert_dua_berkas_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    files = [
        ("files", ("a.png", make_image("PNG"), "image/png")),
        ("files", ("b.png", make_image("PNG"), "image/png")),
    ]
    response = client.post("/api/image/convert", files=files)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_TOO_MANY_FILES


def test_http_image_convert_bukan_gambar_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/image/convert",
        files=[("files", ("palsu.png", b"ini cuma teks", "image/png"))],
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_NOT_IMAGE


def test_http_image_convert_kualitas_tidak_valid_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/image/convert",
        files=[("files", ("test.png", make_image("PNG"), "image/png"))],
        data={"quality": "150"},
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_INVALID_QUALITY


def test_http_image_convert_svg_ke_png_ukuran_asli() -> None:
    client = _test_client()
    if client is None:
        return
    svg = make_svg(width=1500, height=800)
    response = client.post(
        "/api/image/convert",
        files=[("files", ("test.svg", svg, "image/svg+xml"))],
        data={"format": "png"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-input-format"] == "svg"
    assert response.headers["x-output-format"] == "png"
    assert response.headers["x-pixels"] == str(1500 * 800)
    out_img = Image.open(io.BytesIO(response.content))
    assert out_img.size == (1500, 800)


def test_http_image_convert_svg_dengan_width_kustom() -> None:
    client = _test_client()
    if client is None:
        return
    svg = make_svg(width=200, height=100)
    response = client.post(
        "/api/image/convert",
        files=[("files", ("test.svg", svg, "image/svg+xml"))],
        data={"format": "png", "width": "400"},
    )
    assert response.status_code == 200, response.text
    out_img = Image.open(io.BytesIO(response.content))
    assert out_img.size == (400, 200)


def test_http_image_convert_svg_ke_jpg_dan_webp() -> None:
    client = _test_client()
    if client is None:
        return
    svg = make_svg(width=60, height=60)

    resp_jpg = client.post(
        "/api/image/convert",
        files=[("files", ("test.svg", svg, "image/svg+xml"))],
        data={"format": "jpeg"},
    )
    assert resp_jpg.status_code == 200, resp_jpg.text
    assert resp_jpg.headers["content-type"].startswith("image/jpeg")
    out_jpg = Image.open(io.BytesIO(resp_jpg.content))
    assert out_jpg.mode == "RGB"

    resp_jpg2 = client.post(
        "/api/image/convert",
        files=[("files", ("test.svg", svg, "image/svg+xml"))],
        data={"format": "jpg"},
    )
    assert resp_jpg2.status_code == 200, resp_jpg2.text
    assert resp_jpg2.headers["content-type"].startswith("image/jpeg")

    resp_webp = client.post(
        "/api/image/convert",
        files=[("files", ("test.svg", svg, "image/svg+xml"))],
        data={"format": "webp"},
    )
    assert resp_webp.status_code == 200, resp_webp.text
    assert resp_webp.headers["content-type"].startswith("image/webp")
    assert detect_format(resp_webp.content) == "webp"


def test_http_image_convert_svg_berbahaya_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    svg_doctype = (
        b'<?xml version="1.0"?><!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
        b'"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("evil.svg", svg_doctype, "image/svg+xml"))],
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_UNSAFE_SVG

    svg_script = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
        b"<script>alert(1)</script></svg>"
    )
    response2 = client.post(
        "/api/image/convert",
        files=[("files", ("evil2.svg", svg_script, "image/svg+xml"))],
    )
    assert response2.status_code == 400, response2.text
    assert response2.json()["error"]["code"] == IMG_UNSAFE_SVG


def test_http_image_convert_svg_xlink_href_eksternal_ditolak() -> None:
    client = _test_client()
    if client is None:
        return
    svg_href = (
        b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        b'width="50" height="50"><image xlink:href="http://example.com/x.png" '
        b'width="50" height="50"/></svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("href.svg", svg_href, "image/svg+xml"))],
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_UNSAFE_SVG


def test_http_image_convert_svg_rusak_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    svg_rusak = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">terpotong'
    response = client.post(
        "/api/image/convert",
        files=[("files", ("rusak.svg", svg_rusak, "image/svg+xml"))],
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_INVALID_SVG


def test_http_image_convert_width_tidak_valid_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    svg = make_svg(width=100, height=100)
    response = client.post(
        "/api/image/convert",
        files=[("files", ("test.svg", svg, "image/svg+xml"))],
        data={"format": "png", "width": "99999"},
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_INVALID_WIDTH


def test_http_image_convert_svg_20000x20000_diperkecil_waktu_wajar() -> None:
    client = _test_client()
    if client is None:
        return
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="20000" height="20000">\n'
        b'  <rect width="20000" height="20000" fill="blue"/>\n'
        b'</svg>'
    )
    t0 = time.perf_counter()
    response = client.post(
        "/api/image/convert",
        files=[("files", ("besar.svg", svg, "image/svg+xml"))],
        data={"format": "png"},
    )
    elapsed = time.perf_counter() - t0
    assert response.status_code == 200, response.text
    assert elapsed < 5.0, f"Waktu render terlalu lama: {elapsed:.2f} detik"
    assert response.headers["x-scaled-down"] == "true"
    out_img = Image.open(io.BytesIO(response.content))
    total_pixels = out_img.width * out_img.height
    assert total_pixels <= IMG_MAX_PIXELS, f"Piksel melebihi batas: {total_pixels}"
    assert max(out_img.width, out_img.height) <= IMG_SVG_MAX_SIDE


def test_http_image_convert_svg_ekstrem_400000x1_diperkecil() -> None:
    client = _test_client()
    if client is None:
        return
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="400000" height="1">\n'
        b'  <rect width="400000" height="1" fill="red"/>\n'
        b'</svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("gepeng.svg", svg, "image/svg+xml"))],
        data={"format": "png"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-scaled-down"] == "true"
    out_img = Image.open(io.BytesIO(response.content))
    assert max(out_img.width, out_img.height) <= IMG_SVG_MAX_SIDE
    assert out_img.width * out_img.height <= IMG_MAX_PIXELS


def test_http_image_convert_svg_viewbox_200x100_tanpa_width() -> None:
    client = _test_client()
    if client is None:
        return
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">\n'
        b'  <rect width="200" height="100" fill="green"/>\n'
        b'</svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("viewbox.svg", svg, "image/svg+xml"))],
        data={"format": "png"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-scaled-down"] == "false"
    out_img = Image.open(io.BytesIO(response.content))
    assert out_img.size == (1024, 512)


def test_http_image_convert_svg_1500x800_tanpa_width() -> None:
    client = _test_client()
    if client is None:
        return
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="800">\n'
        b'  <rect width="1500" height="800" fill="blue"/>\n'
        b'</svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("large.svg", svg, "image/svg+xml"))],
        data={"format": "png"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-scaled-down"] == "false"
    out_img = Image.open(io.BytesIO(response.content))
    assert out_img.size == (1500, 800)


def test_http_image_convert_svg_24x24_viewbox_saja() -> None:
    client = _test_client()
    if client is None:
        return
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">\n'
        b'  <circle cx="12" cy="12" r="10" fill="red"/>\n'
        b'</svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("icon.svg", svg, "image/svg+xml"))],
        data={"format": "png"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-scaled-down"] == "false"
    out_img = Image.open(io.BytesIO(response.content))
    assert out_img.size == (1024, 1024)


def test_http_image_convert_svg_600x300_tanpa_width_diperbesar() -> None:
    client = _test_client()
    if client is None:
        return
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300">\n'
        b'  <rect width="600" height="300" fill="green"/>\n'
        b'</svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("normal.svg", svg, "image/svg+xml"))],
        data={"format": "png"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-scaled-down"] == "false"
    out_img = Image.open(io.BytesIO(response.content))
    assert out_img.size == (1024, 512)


def test_http_image_convert_svg_600x300_dengan_width_400_proporsional() -> None:
    client = _test_client()
    if client is None:
        return
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300">\n'
        b'  <rect width="600" height="300" fill="green"/>\n'
        b'</svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("normal.svg", svg, "image/svg+xml"))],
        data={"format": "png", "width": "400"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-scaled-down"] == "false"
    out_img = Image.open(io.BytesIO(response.content))
    assert out_img.size == (400, 200)


def test_http_image_convert_regresi_format_lama_tetap_jalan() -> None:
    client = _test_client()
    if client is None:
        return

    png_data = make_image("PNG", size=(40, 30), color="teal")
    resp_png_jpg = client.post(
        "/api/image/convert",
        files=[("files", ("a.png", png_data, "image/png"))],
        data={"format": "jpeg"},
    )
    assert resp_png_jpg.status_code == 200, resp_png_jpg.text
    assert Image.open(io.BytesIO(resp_png_jpg.content)).size == (40, 30)

    resp_png_jpg2 = client.post(
        "/api/image/convert",
        files=[("files", ("a2.png", png_data, "image/png"))],
        data={"format": "jpg"},
    )
    assert resp_png_jpg2.status_code == 200, resp_png_jpg2.text
    assert Image.open(io.BytesIO(resp_png_jpg2.content)).size == (40, 30)

    resp_png_webp = client.post(
        "/api/image/convert",
        files=[("files", ("b.png", png_data, "image/png"))],
        data={"format": "webp"},
    )
    assert resp_png_webp.status_code == 200, resp_png_webp.text
    assert Image.open(io.BytesIO(resp_png_webp.content)).size == (40, 30)

    jpeg_data = make_image("JPEG", size=(25, 45), color="orange")
    resp_jpeg_png = client.post(
        "/api/image/convert",
        files=[("files", ("c.jpg", jpeg_data, "image/jpeg"))],
        data={"format": "png"},
    )
    assert resp_jpeg_png.status_code == 200, resp_jpeg_png.text
    assert Image.open(io.BytesIO(resp_jpeg_png.content)).size == (25, 45)

    webp_data = make_image("WEBP", size=(33, 22), color="purple")
    resp_webp_png = client.post(
        "/api/image/convert",
        files=[("files", ("d.webp", webp_data, "image/webp"))],
        data={"format": "png"},
    )
    assert resp_webp_png.status_code == 200, resp_webp_png.text
    assert Image.open(io.BytesIO(resp_webp_png.content)).size == (33, 22)


def test_http_word_count_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/word-count/limits")
    assert response.status_code == 200
    body = response.json()
    assert body["processed_on"] == "server"
    assert body["max_chars"] == WC_MAX_CHARS
    assert body["max_bytes"] == WC_MAX_BYTES
    assert response.headers["cache-control"] == "no-store"


def test_http_word_count_teks_normal_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", data={"text": "Halo dunia. Ini uji coba!"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")

    # Respons sukses tidak memuat Cache-Control yang membolehkan cache
    cache = response.headers.get("cache-control", "")
    assert "no-store" in cache
    assert "no-cache" in cache
    assert response.headers.get("pragma") == "no-cache"

    # Header ringkas
    assert response.headers.get("x-char-count") == "25"
    assert response.headers.get("x-word-count") == "5"
    assert "x-processing-ms" in response.headers

    body = response.json()
    assert body["chars"] == 25
    assert body["chars_no_spaces"] == 21
    assert body["words"] == 5
    assert body["unique_words"] == 5
    assert body["sentences"] == 2
    assert body["paragraphs"] == 1
    assert body["lines"] == 1
    assert body["reading_minutes"] == 1
    assert body["speaking_minutes"] == 1
    assert body["longest_word"] == "dunia"


def test_http_word_count_paragraf_dan_baris() -> None:
    client = _test_client()
    if client is None:
        return
    text = (
        "Baris 1 paragraf 1\n"
        "Baris 2 paragraf 1\n\n"
        "Baris 3 paragraf 2\n\n\n"
        "Baris 4 paragraf 3"
    )
    response = client.post("/api/word-count", data={"text": text})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["paragraphs"] == 3
    assert body["lines"] == 4


def test_http_word_count_case_insensitive_dan_top_words() -> None:
    client = _test_client()
    if client is None:
        return
    text = "Mawar mawar MAWAR melati melati melati melati anggrek."
    response = client.post("/api/word-count", data={"text": text})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["unique_words"] == 3
    words = [item["word"] for item in body["top_words"]]
    assert words[0] == "melati"
    assert body["top_words"][0]["count"] == 4
    assert words[1] == "mawar"
    assert body["top_words"][1]["count"] == 3


def test_http_word_count_teks_kosong_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", data={"text": ""})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == WC_NO_TEXT


def test_http_word_count_teks_hanya_spasi_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", data={"text": "   \n\t  "})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == WC_NO_TEXT


def test_http_word_count_teks_terlalu_panjang_ditolak_413() -> None:
    client = _test_client()
    if client is None:
        return
    long_text = "x" * (WC_MAX_CHARS + 10)
    response = client.post("/api/word-count", data={"text": long_text})
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == WC_TOO_LONG


def test_http_word_count_bukan_multipart_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", json={"text": "Halo dunia"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == WC_INVALID_REQUEST


def test_http_word_count_field_text_hilang_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", data={})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] in (WC_INVALID_REQUEST, WC_NO_TEXT)


def test_http_word_count_cache_headers_tidak_membolehkan_cache() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", data={"text": "Uji cache header"})
    assert response.status_code == 200
    cache_control = response.headers.get("Cache-Control", "")
    assert "public" not in cache_control
    assert "max-age" not in cache_control
    assert "no-store" in cache_control
    assert "no-cache" in cache_control
    assert response.headers.get("Pragma") == "no-cache"


def test_http_case_convert_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/case/limits")
    assert response.status_code == 200
    body = response.json()
    assert body["processed_on"] == "server"
    assert body["max_chars"] == CC_MAX_CHARS
    assert body["max_bytes"] == CC_MAX_BYTES
    assert body["modes"] == CC_MODE_ORDER
    assert body["mode_labels"] == CC_MODES
    assert response.headers["cache-control"] == "no-store"


def test_http_case_convert_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/case", data={"text": "halo dunia", "mode": "upper"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")

    # Header no-cache
    cache = response.headers.get("cache-control", "")
    assert "no-store" in cache
    assert "no-cache" in cache
    assert response.headers.get("pragma") == "no-cache"

    # Header metadata
    assert response.headers.get("x-case-mode") == "upper"
    assert response.headers.get("x-char-count") == "10"
    assert "x-processing-ms" in response.headers

    body = response.json()
    assert body["mode"] == "upper"
    assert body["text"] == "HALO DUNIA"
    assert body["chars_in"] == 10
    assert body["chars_out"] == 10
    assert body["words"] == 2
    assert body["changed"] is True


def test_http_case_convert_teks_kosong_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/case", data={"text": "", "mode": "upper"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == CC_NO_TEXT


def test_http_case_convert_teks_hanya_spasi_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/case", data={"text": "   \n\t  ", "mode": "upper"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == CC_NO_TEXT


def test_http_case_convert_mode_tidak_valid_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    # Mode tidak dikenal
    response = client.post("/api/case", data={"text": "halo", "mode": "tidak_ada"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == CC_UNSUPPORTED_MODE

    # Mode tidak disertakan
    response2 = client.post("/api/case", data={"text": "halo"})
    assert response2.status_code == 400, response2.text
    assert response2.json()["error"]["code"] == CC_INVALID_REQUEST


def test_http_case_convert_bukan_multipart_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/case", json={"text": "halo", "mode": "upper"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == CC_INVALID_REQUEST


def test_http_case_convert_teks_terlalu_panjang_ditolak_413() -> None:
    client = _test_client()
    if client is None:
        return
    long_text = "x" * (CC_MAX_CHARS + 10)
    response = client.post("/api/case", data={"text": long_text, "mode": "upper"})
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == CC_TOO_LONG


def test_http_base64_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/base64/limits")
    assert response.status_code == 200
    body = response.json()
    assert body["processed_on"] == "server"
    assert body["max_chars"] == B64_MAX_CHARS
    assert body["max_bytes"] == B64_MAX_BYTES
    assert isinstance(body["modes"], list)
    assert isinstance(body["variants"], list)
    assert isinstance(body["wrap_options"], list)
    assert isinstance(body["decode_accepts"], list)
    assert response.headers["cache-control"] == "no-store"


def test_http_base64_encode_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/base64", data={"text": "Halo, dunia!", "mode": "encode"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")

    cache = response.headers.get("cache-control", "")
    assert "no-store" in cache
    assert "no-cache" in cache
    assert response.headers.get("pragma") == "no-cache"

    assert response.headers.get("x-base64-mode") == "encode"
    assert "x-output-length" in response.headers
    assert "x-processing-ms" in response.headers

    body = response.json()
    assert body["mode"] == "encode"
    assert body["text"] == "SGFsbywgZHVuaWEh"
    assert body["chars_in"] == 12
    assert body["chars_out"] == 16
    assert body["changed"] is True


def test_http_base64_encode_urlsafe_dan_wrap() -> None:
    client = _test_client()
    if client is None:
        return
    text = "Kalimat panjang untuk menguji opsi urlsafe dan pembungkusan baris 76 karakter pada endpoint HTTP."
    response = client.post(
        "/api/base64",
        data={"text": text, "mode": "encode", "variant": "urlsafe", "wrap": "76"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["variant"] == "urlsafe"
    assert body["wrap"] == 76
    lines = body["text"].split("\n")
    assert len(lines) > 1
    for line in lines:
        assert len(line) <= 76


def test_http_base64_decode_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    b64_input = "  data:text/plain;base64,\n SGFsbywgZHVuaWEh \n "
    response = client.post("/api/base64", data={"text": b64_input, "mode": "decode"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "decode"
    assert body["text"] == "Halo, dunia!"
    assert response.headers.get("x-base64-mode") == "decode"


def test_http_base64_teks_kosong_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/base64", data={"text": "", "mode": "encode"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == B64_NO_TEXT


def test_http_base64_teks_hanya_spasi_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/base64", data={"text": "   \n\t  ", "mode": "encode"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == B64_NO_TEXT


def test_http_base64_mode_tidak_valid_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/base64", data={"text": "halo", "mode": "tidak_ada"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == B64_UNSUPPORTED_MODE

    response2 = client.post("/api/base64", data={"text": "halo"})
    assert response2.status_code == 400, response2.text
    assert response2.json()["error"]["code"] == B64_INVALID_REQUEST


def test_http_base64_bukan_multipart_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/base64", json={"text": "halo", "mode": "encode"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == B64_INVALID_REQUEST


def test_http_base64_teks_terlalu_panjang_ditolak_413() -> None:
    client = _test_client()
    if client is None:
        return
    long_text = "x" * (B64_MAX_CHARS + 10)
    response = client.post("/api/base64", data={"text": long_text, "mode": "encode"})
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == B64_TOO_LONG


def test_http_base64_invalid_base64_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/base64", data={"text": "Bukan base64 valid! @#$", "mode": "decode"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == B64_INVALID_BASE64


def test_http_base64_data_biner_ditolak_400() -> None:
    import base64
    client = _test_client()
    if client is None:
        return
    binary_b64 = base64.b64encode(bytes(range(256))).decode("ascii")
    response = client.post("/api/base64", data={"text": binary_b64, "mode": "decode"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == B64_NOT_TEXT


# --- Uji OCR (Ambil teks dari gambar & PDF) ---------------------------------
def test_ocr_logic_detect_file_type() -> None:
    from app.ocr import detect_file_type
    assert detect_file_type(b"%PDF-1.4") == "pdf"
    assert detect_file_type(b"\x89PNG\r\n\x1a\n...") == "image"
    assert detect_file_type(b"\xff\xd8\xff...") == "image"
    assert detect_file_type(b"RIFF\x00\x00\x00\x00WEBP...") == "image"
    assert detect_file_type(b"II*\x00...") == "image"
    assert detect_file_type(b"MM\x00*...") == "image"
    assert detect_file_type(b"bukan gambar atau pdf") is None


def test_ocr_logic_empty_data() -> None:
    try:
        run_ocr(b"")
    except OcrError as exc:
        assert exc.code == OCR_EMPTY_FILE
        assert exc.status_code == 400
    else:
        assert False, "Harus melempar OcrError"


def test_ocr_logic_unsupported_data() -> None:
    try:
        run_ocr(b"Hello World plain text")
    except OcrError as exc:
        assert exc.code == OCR_UNSUPPORTED_FILE
        assert exc.status_code == 400
    else:
        assert False, "Harus melempar OcrError"


def test_ocr_logic_invalid_lang() -> None:
    try:
        run_ocr(make_ocr_png("TES"), lang="invalid_lang")
    except OcrError as exc:
        assert exc.code == OCR_INVALID_LANG
        assert exc.status_code == 400
    else:
        assert False, "Harus melempar OcrError"


def test_http_ocr_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/ocr/limits")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["max_bytes"] == OCR_MAX_BYTES
    assert body["max_pages"] == OCR_MAX_PAGES
    assert body["time_limit_seconds"] == OCR_TIME_LIMIT_SECONDS
    assert "languages" in body
    assert any(lang["value"] == "ind" for lang in body["languages"])
    assert any(lang["value"] == "eng" for lang in body["languages"])
    assert any(lang["value"] == "ind+eng" for lang in body["languages"])
    assert response.headers["cache-control"] == "no-store"


def test_http_ocr_gambar_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    png_bytes = make_ocr_png("KUCING OREN")
    response = client.post(
        "/api/ocr",
        files=[("file", ("kucing.png", png_bytes, "image/png"))],
        data={"lang": "ind+eng"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    text_lower = body["text"].lower()
    assert "kucing" in text_lower or "oren" in text_lower
    assert body["pages"] == 1
    assert body["source"] == "image"
    assert body["empty"] is False
    assert body["chars"] > 0
    assert response.headers["x-page-count"] == "1"
    assert "x-char-count" in response.headers
    assert "x-processing-ms" in response.headers
    assert response.headers["x-ocr-lang"] == "ind+eng"
    assert "no-store" in response.headers["cache-control"]


def test_http_ocr_pdf_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    pdf_bytes = make_ocr_pdf("SURAT SATU", "BERKAS DUA")
    response = client.post(
        "/api/ocr",
        files=[("file", ("dokumen.pdf", pdf_bytes, "application/pdf"))],
        data={"lang": "ind+eng"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    text_lower = body["text"].lower()
    assert "surat" in text_lower or "satu" in text_lower
    assert "berkas" in text_lower or "dua" in text_lower
    assert body["pages"] == 2
    assert body["source"] == "pdf"
    assert body["empty"] is False
    assert "=== Halaman 1 ===" in body["text"]
    assert "=== Halaman 2 ===" in body["text"]
    assert response.headers["x-page-count"] == "2"


def test_http_ocr_tanpa_field_file_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/ocr", data={"lang": "ind"})
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "INVALID_REQUEST"


def test_http_ocr_berkas_kosong_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/ocr",
        files=[("file", ("kosong.png", b"", "image/png"))],
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == OCR_EMPTY_FILE


def test_http_ocr_berkas_teks_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/ocr",
        files=[("file", ("catatan.txt", b"Halo ini berkas teks biasa", "text/plain"))],
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == OCR_UNSUPPORTED_FILE


def test_http_ocr_berkas_terlalu_besar_ditolak_413() -> None:
    client = _test_client()
    if client is None:
        return
    large_payload = b"\x89PNG\r\n\x1a\n" + b"0" * (OCR_MAX_BYTES + 100)
    response = client.post(
        "/api/ocr",
        files=[("file", ("besar.png", large_payload, "image/png"))],
    )
    assert response.status_code == 413, response.text
    body = response.json()
    assert body["error"]["code"] == OCR_TOO_LARGE


def test_http_ocr_pdf_terlalu_banyak_halaman_ditolak_413() -> None:
    client = _test_client()
    if client is None:
        return
    pdf_bytes = make_many_page_pdf(OCR_MAX_PAGES + 1)
    response = client.post(
        "/api/ocr",
        files=[("file", ("dokumen_tebal.pdf", pdf_bytes, "application/pdf"))],
    )
    assert response.status_code == 413, response.text
    body = response.json()
    assert body["error"]["code"] == OCR_TOO_MANY_PAGES


def test_http_ocr_lang_tidak_dikenal_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    png_bytes = make_ocr_png("TES")
    response = client.post(
        "/api/ocr",
        files=[("file", ("tes.png", png_bytes, "image/png"))],
        data={"lang": "xx"},
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == OCR_INVALID_LANG


def test_http_ocr_pdf_rusak_ditolak_422() -> None:
    client = _test_client()
    if client is None:
        return
    corrupted_pdf = b"%PDF-1.7\n" + b"\x00" * 2000
    response = client.post(
        "/api/ocr",
        files=[("file", ("rusak.pdf", corrupted_pdf, "application/pdf"))],
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"]["code"] == OCR_DAMAGED_FILE
    assert body["error"]["code"] != "INTERNAL_ERROR"
    assert "tidak bisa dibaca" in body["error"]["message"].lower()




# --- Uji HTTP ke server yang benar-benar jalan ------------------------------
def test_http_live_jika_env_diisi() -> None:
    """Jalankan hanya bila OMNITOOLS_API_URL diisi, mis. http://127.0.0.1:8077."""
    base = os.getenv("OMNITOOLS_API_URL", "").rstrip("/")
    if not base:
        SKIPPED.append("uji live dilewati: OMNITOOLS_API_URL tidak diisi")
        return

    with urllib.request.urlopen(base + "/health", timeout=10) as response:
        assert response.status == 200
        assert json.loads(response.read())["status"] == "ok"

    # Merge 2 + 3 halaman lewat multipart/form-data sungguhan.
    boundary = "----omnitoolsuji"
    parts: list[bytes] = []
    for name, payload in (("a.pdf", make_pdf(2)), ("b.pdf", make_pdf(3))):
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="files"; filename="{name}"\r\n'
                "Content-Type: application/pdf\r\n\r\n"
            ).encode()
            + payload
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    request = urllib.request.Request(
        base + "/api/pdf/merge",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            disposition = response.headers.get("Content-Disposition", "")
            cache = response.headers.get("Cache-Control", "")
            pages_header = response.headers.get("X-Page-Count", "")
            data = response.read()
    except urllib.error.HTTPError as exc:
        raise AssertionError(f"merge live gagal: HTTP {exc.code} {exc.read()[:200]!r}") from exc

    assert status == 200
    assert content_type.startswith("application/pdf"), content_type
    assert 'filename="gabungan.pdf"' in disposition, disposition
    assert cache.startswith("no-store"), cache
    assert pages_header == "5", pages_header
    assert page_count(data) == 5

    # Word Count live lewat multipart/form-data
    boundary_wc = "----omnitoolswc"
    body_wc = (
        f"--{boundary_wc}\r\n"
        f'Content-Disposition: form-data; name="text"\r\n\r\n'
        f"Halo dunia. Ini uji coba!\r\n"
        f"--{boundary_wc}--\r\n"
    ).encode()
    req_wc = urllib.request.Request(
        base + "/api/word-count",
        data=body_wc,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary_wc}"},
    )
    with urllib.request.urlopen(req_wc, timeout=10) as resp:
        assert resp.status == 200
        wc_data = json.loads(resp.read().decode())
        assert wc_data["words"] == 5
        assert wc_data["chars"] == 25



# --- Runner mandiri ---------------------------------------------------------
def main() -> int:
    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    passed = 0
    failures: list[tuple[str, str]] = []

    print(f"OmniTools API — uji Merge PDF (versi {__version__}, python {sys.version.split()[0]})")
    print(f"Pemeriksaan akan dijalankan: {len(tests)}\n")

    for name, func in tests:
        try:
            func()
        except Exception:
            failures.append((name, traceback.format_exc()))
            print(f"GAGAL  {name}")
        else:
            passed += 1
            print(f"LULUS  {name}")

    for note in SKIPPED:
        print(f"LEWAT  {note}")

    print(f"\nRingkasan: {passed} lulus, {len(failures)} gagal, {len(SKIPPED)} dilewati")

    for name, detail in failures:
        print(f"\n--- detail kegagalan: {name} ---")
        print(detail)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
