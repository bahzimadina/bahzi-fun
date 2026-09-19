"""Logika pembacaan teks dari gambar & PDF (OCR): fungsi murni, tanpa HTTP, mudah diuji.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Teks pengguna tidak pernah dicatat ke log.

Format berkas yang didukung:
* PDF (%PDF-)
* PNG (\x89PNG\r\n\x1a\n)
* JPEG (\xff\xd8\xff)
* WebP (RIFF....WEBP)
* TIFF (II*\x00 atau MM\x00*)

Batas operasional:
* Maks 20 MB per berkas
* PDF maks 15 halaman
* Batas waktu 120 detik (2 menit)
* Bahasa yang didukung: Indonesia (ind), Inggris (eng), Campuran (ind+eng)
"""

from __future__ import annotations

import io
import math
import time
from dataclasses import dataclass
from typing import Any

from PIL import Image
import pymupdf as fitz
import pytesseract

CHUNK_SIZE = 1 << 20  # 1 MB
MAX_BYTES = 20 * 1024 * 1024  # 20 MB
MAX_PAGES = 15
TIME_LIMIT_SECONDS = 120
RENDER_DPI = 250
MAX_RENDER_PIXELS = 25_000_000
DEFAULT_LANG = "ind+eng"

LANGUAGES: dict[str, str] = {
    "ind": "Indonesia",
    "eng": "Inggris",
    "ind+eng": "Campuran",
}
LANGS: list[str] = list(LANGUAGES.keys())

# Kode galat stabil
NO_FILE = "NO_FILE"
EMPTY_FILE = "EMPTY_FILE"
TOO_LARGE = "TOO_LARGE"
UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
TOO_MANY_PAGES = "TOO_MANY_PAGES"
DAMAGED_FILE = "DAMAGED_FILE"
INVALID_LANG = "INVALID_LANG"
OCR_TIMEOUT = "OCR_TIMEOUT"
OCR_FAILED = "OCR_FAILED"
BUSY = "BUSY"


class OcrError(Exception):
    """Kesalahan OCR dengan kode error dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons JSON standar: {"error": {"code": ..., "message": ...}}."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class OcrResult:
    """Hasil pembacaan teks dari gambar atau dokumen PDF."""

    text: str
    pages: int
    language: str
    source: str
    chars: int
    empty: bool
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        """Konversi hasil ke format dictionary JSON."""
        return {
            "text": self.text,
            "pages": self.pages,
            "language": self.language,
            "source": self.source,
            "chars": self.chars,
            "empty": self.empty,
            "duration_ms": self.duration_ms,
        }


def detect_file_type(data: bytes) -> str | None:
    """Deteksi jenis berkas dari magic bytes. Mengembalikan 'pdf', 'image', atau None."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image"
    if data.startswith(b"\xff\xd8\xff"):
        return "image"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image"
    if data.startswith(b"II*\x00") or data.startswith(b"MM\x00*"):
        return "image"
    return None


def run_ocr(data: bytes, lang: str | None = None) -> OcrResult:
    """Jalankan OCR pada berkas biner gambar atau PDF di memori."""
    started = time.monotonic()
    deadline = started + TIME_LIMIT_SECONDS

    if not data or len(data) == 0:
        raise OcrError(EMPTY_FILE, "Berkasnya kosong.", 400)
    if len(data) > MAX_BYTES:
        raise OcrError(TOO_LARGE, "Ukuran berkas lebih dari 20 MB.", 413)

    if lang is not None and lang != "":
        if lang not in LANGUAGES:
            raise OcrError(INVALID_LANG, "Pilihan bahasanya tidak dikenal.", 400)
        selected_lang = lang
    else:
        selected_lang = DEFAULT_LANG

    source_kind = detect_file_type(data)
    if source_kind is None:
        raise OcrError(
            UNSUPPORTED_FILE,
            "Format berkas belum didukung. Pakai JPG, PNG, WebP, TIFF, atau PDF.",
            400,
        )

    if source_kind == "pdf":
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise OcrError(DAMAGED_FILE, "Berkasnya tidak bisa dibaca. Coba berkas lain.", 422) from exc

        try:
            page_count = len(doc)
            if page_count == 0:
                raise OcrError(DAMAGED_FILE, "Berkasnya tidak bisa dibaca. Coba berkas lain.", 422)
            if page_count > MAX_PAGES:
                raise OcrError(TOO_MANY_PAGES, "PDF-nya lebih dari 15 halaman.", 413)

            page_texts: list[str] = []
            for page_idx in range(page_count):
                remaining = deadline - time.monotonic()
                if remaining <= 1.0:
                    raise OcrError(
                        OCR_TIMEOUT,
                        "Waktunya lebih dari 2 menit. Coba berkas yang lebih kecil atau lebih sedikit halaman.",
                        504,
                    )
                tess_timeout = max(1, int(remaining))

                page = None
                pix = None
                img = None
                try:
                    page = doc.load_page(page_idx)
                    rect = page.rect
                    base_w = rect.width
                    base_h = rect.height
                    if base_w <= 0 or base_h <= 0:
                        page_texts.append("")
                        continue

                    scale = RENDER_DPI / 72.0
                    if (base_w * scale) * (base_h * scale) > MAX_RENDER_PIXELS:
                        scale = math.sqrt(MAX_RENDER_PIXELS / (base_w * base_h))

                    mat = fitz.Matrix(scale, scale)
                    pix = page.get_pixmap(matrix=mat, alpha=False)

                    if pix.n == 1:
                        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
                    elif pix.n == 3:
                        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
                    elif pix.n == 4:
                        img = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples).convert("L")
                    else:
                        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
                except Exception as exc:
                    raise OcrError(DAMAGED_FILE, "Berkasnya tidak bisa dibaca. Coba berkas lain.", 422) from exc

                try:
                    txt = pytesseract.image_to_string(
                        img,
                        lang=selected_lang,
                        timeout=tess_timeout,
                        config="--oem 1 --psm 3",
                    )
                except RuntimeError as exc:
                    if "timeout" in str(exc).lower():
                        raise OcrError(
                            OCR_TIMEOUT,
                            "Waktunya lebih dari 2 menit. Coba berkas yang lebih kecil atau lebih sedikit halaman.",
                            504,
                        ) from exc
                    raise OcrError(
                        OCR_FAILED,
                        "Teksnya gagal diambil. Coba berkas lain atau pilihan bahasa lain.",
                        422,
                    ) from exc
                except Exception as exc:
                    if "timeout" in str(exc).lower():
                        raise OcrError(
                            OCR_TIMEOUT,
                            "Waktunya lebih dari 2 menit. Coba berkas yang lebih kecil atau lebih sedikit halaman.",
                            504,
                        ) from exc
                    raise OcrError(
                        OCR_FAILED,
                        "Teksnya gagal diambil. Coba berkas lain atau pilihan bahasa lain.",
                        422,
                    ) from exc
                finally:
                    if img is not None:
                        del img
                    if pix is not None:
                        del pix
                    if page is not None:
                        del page

                page_texts.append(txt)
        finally:
            doc.close()

        if page_count > 1:
            parts: list[str] = []
            for i, pt in enumerate(page_texts, start=1):
                c = pt.strip()
                if c:
                    parts.append(f"=== Halaman {i} ===\n{c}")
                else:
                    parts.append(f"=== Halaman {i} ===")
            all_blank = all(len(pt.strip()) == 0 for pt in page_texts)
            if all_blank:
                combined_text = ""
            else:
                combined_text = "\n\n".join(parts).strip()
        else:
            combined_text = page_texts[0].strip() if page_texts else ""

        duration_ms = int(round((time.monotonic() - started) * 1000))
        chars = len(combined_text)
        empty = (chars == 0)

        return OcrResult(
            text=combined_text,
            pages=page_count,
            language=selected_lang,
            source="pdf",
            chars=chars,
            empty=empty,
            duration_ms=duration_ms,
        )

    else:
        remaining = deadline - time.monotonic()
        if remaining <= 1.0:
            raise OcrError(
                OCR_TIMEOUT,
                "Waktunya lebih dari 2 menit. Coba berkas yang lebih kecil atau lebih sedikit halaman.",
                504,
            )
        tess_timeout = max(1, int(remaining))

        try:
            with Image.open(io.BytesIO(data)) as raw_img:
                img = raw_img.convert("L")
                img.load()
        except Exception as exc:
            raise OcrError(DAMAGED_FILE, "Berkasnya tidak bisa dibaca. Coba berkas lain.", 422) from exc

        try:
            txt = pytesseract.image_to_string(
                img,
                lang=selected_lang,
                timeout=tess_timeout,
                config="--oem 1 --psm 3",
            )
        except RuntimeError as exc:
            if "timeout" in str(exc).lower():
                raise OcrError(
                    OCR_TIMEOUT,
                    "Waktunya lebih dari 2 menit. Coba berkas yang lebih kecil atau lebih sedikit halaman.",
                    504,
                ) from exc
            raise OcrError(
                OCR_FAILED,
                "Teksnya gagal diambil. Coba berkas lain atau pilihan bahasa lain.",
                422,
            ) from exc
        except Exception as exc:
            if "timeout" in str(exc).lower():
                raise OcrError(
                    OCR_TIMEOUT,
                    "Waktunya lebih dari 2 menit. Coba berkas yang lebih kecil atau lebih sedikit halaman.",
                    504,
                ) from exc
            raise OcrError(
                OCR_FAILED,
                "Teksnya gagal diambil. Coba berkas lain atau pilihan bahasa lain.",
                422,
            ) from exc
        finally:
            del img

        combined_text = txt.strip()
        duration_ms = int(round((time.monotonic() - started) * 1000))
        chars = len(combined_text)
        empty = (chars == 0)

        return OcrResult(
            text=combined_text,
            pages=1,
            language=selected_lang,
            source="image",
            chars=chars,
            empty=empty,
            duration_ms=duration_ms,
        )
