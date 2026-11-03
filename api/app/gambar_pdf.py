"""Logika konversi gambar ke dokumen PDF: fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak menulis ke disk.
Semua validasi format, batas berkas, dimensi, perataan margin, dan penyusunan
halaman PDF dilakukan langsung di memori.
"""

from __future__ import annotations

import io
from typing import Any, Sequence

from PIL import Image, ImageOps
import fitz

# Batas operasional
MAX_FILES = 20
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_TOTAL_BYTES = 40 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_SIDE = 3500
JPEG_QUALITY = 88
CHUNK_SIZE = 1024 * 1024

# Magic bytes gambar masukan
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
RIFF_MAGIC = b"RIFF"
WEBP_MAGIC = b"WEBP"

# Kode galat stabil
NO_FILES = "NO_FILES"
TOO_MANY_FILES = "TOO_MANY_FILES"
EMPTY_FILE = "EMPTY_FILE"
UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
TOO_LARGE = "TOO_LARGE"
TOTAL_TOO_LARGE = "TOTAL_TOO_LARGE"
DAMAGED_IMAGE = "DAMAGED_IMAGE"
UNSUPPORTED_PAGE_SIZE = "UNSUPPORTED_PAGE_SIZE"
UNSUPPORTED_ORIENTATION = "UNSUPPORTED_ORIENTATION"
INVALID_MARGIN = "INVALID_MARGIN"
INVALID_REQUEST = "INVALID_REQUEST"
BUSY = "BUSY"


class GambarPdfError(Exception):
    """Galat operasional gambar ke PDF dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message}}


PAGE_SIZES_MM: dict[str, tuple[float, float]] = {
    "a4": (210.0, 297.0),
    "f4": (215.0, 330.0),
    "letter": (216.0, 279.0),
}

PAGE_SIZES = [
    {"id": "a4", "label": "A4 (210 x 297 mm)"},
    {"id": "f4", "label": "F4 (215 x 330 mm)"},
    {"id": "letter", "label": "Letter (216 x 279 mm)"},
    {"id": "auto", "label": "Otomatis (ikut ukuran gambar)"},
]

ORIENTATIONS = [
    {"id": "auto", "label": "Otomatis"},
    {"id": "tegak", "label": "Tegak"},
    {"id": "mendatar", "label": "Mendatar"},
]

VALID_PAGE_SIZES = {"a4", "f4", "letter", "auto"}
VALID_ORIENTATIONS = {"auto", "tegak", "mendatar"}
VALID_MARGINS = (0, 5, 10, 15, 20)


def is_supported_image(data: bytes) -> bool:
    """Deteksi dukungan gambar JPG, PNG, atau WebP dari byte awal."""
    if not data or len(data) < 3:
        return False
    if data.startswith(JPEG_MAGIC):
        return True
    if data.startswith(b"\x89PNG"):
        return True
    if len(data) >= 12 and data.startswith(RIFF_MAGIC) and data[8:12] == WEBP_MAGIC:
        return True
    return False


def normalize_params(
    ukuran: str | None,
    orientasi: str | None,
    margin: int | str | None,
) -> tuple[str, str, int]:
    """Validasi dan normalisasi parameter konfigurasi halaman."""
    if ukuran is None or not str(ukuran).strip():
        u = "a4"
    else:
        u = str(ukuran).strip().lower()
    if u not in VALID_PAGE_SIZES:
        raise GambarPdfError(
            UNSUPPORTED_PAGE_SIZE,
            "Ukuran halaman tidak didukung. Pilih A4, F4, Letter, atau Auto.",
            400,
        )

    if orientasi is None or not str(orientasi).strip():
        o = "auto"
    else:
        o = str(orientasi).strip().lower()
    if o not in VALID_ORIENTATIONS:
        raise GambarPdfError(
            UNSUPPORTED_ORIENTATION,
            "Orientasi halaman tidak didukung. Pilih auto, tegak, atau mendatar.",
            400,
        )

    if margin is None:
        m = 10
    else:
        try:
            m = int(str(margin).strip())
        except (ValueError, TypeError) as exc:
            raise GambarPdfError(
                INVALID_MARGIN,
                "Margin halaman harus 0, 5, 10, 15, atau 20 mm.",
                400,
            ) from exc
    if m not in VALID_MARGINS:
        raise GambarPdfError(
            INVALID_MARGIN,
            "Margin halaman harus 0, 5, 10, 15, atau 20 mm.",
            400,
        )

    return u, o, m


def limits_payload() -> dict[str, Any]:
    """Ringkasan batasan alat untuk kebutuhan front-end."""
    return {
        "max_files": MAX_FILES,
        "max_file_mb": MAX_FILE_BYTES // (1024 * 1024),
        "max_total_mb": MAX_TOTAL_BYTES // (1024 * 1024),
        "max_pixels": MAX_PIXELS,
        "max_side": MAX_SIDE,
        "page_sizes": PAGE_SIZES,
        "orientations": ORIENTATIONS,
        "margins": list(VALID_MARGINS),
        "default": {
            "ukuran": "a4",
            "orientasi": "auto",
            "margin": 10,
        },
    }


def buat_pdf(
    berkas: Sequence[tuple[bytes, str] | bytes],
    ukuran: str = "a4",
    orientasi: str = "auto",
    margin: int = 10,
) -> tuple[bytes, dict[str, int]]:
    """Susun daftar gambar menjadi satu dokumen PDF di memori."""
    u, o, m = normalize_params(ukuran, orientasi, margin)

    if not berkas:
        raise GambarPdfError(NO_FILES, "Pilih dulu gambar yang mau dijadikan PDF.", 400)
    if len(berkas) > MAX_FILES:
        raise GambarPdfError(TOO_MANY_FILES, "Paling banyak 20 gambar sekali jalan.", 400)

    total_bytes = 0
    extracted: list[bytes] = []
    for item in berkas:
        data = item[0] if isinstance(item, tuple) else item
        if not data or len(data) == 0:
            raise GambarPdfError(EMPTY_FILE, "Ada berkas yang kosong. Pilih gambar lain.", 400)
        if len(data) > MAX_FILE_BYTES:
            raise GambarPdfError(TOO_LARGE, "Satu gambar paling besar 15 MB.", 413)
        if not is_supported_image(data):
            raise GambarPdfError(UNSUPPORTED_FILE, "Hanya gambar JPG, PNG, atau WebP yang bisa dipakai.", 400)
        total_bytes += len(data)
        if total_bytes > MAX_TOTAL_BYTES:
            raise GambarPdfError(TOTAL_TOO_LARGE, "Total semua gambar paling besar 40 MB. Kurangi dulu jumlahnya.", 413)
        extracted.append(data)

    pt_per_mm = 72.0 / 25.4
    margin_pt = m * pt_per_mm
    diperkecil_count = 0

    doc = fitz.open()

    for data in extracted:
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception as exc:
            doc.close()
            raise GambarPdfError(DAMAGED_IMAGE, "Gambar ini tidak bisa dibaca. Coba gambar lain.", 422) from exc

        if img.width * img.height > MAX_PIXELS:
            doc.close()
            raise GambarPdfError(DAMAGED_IMAGE, "Dimensi gambar terlalu besar untuk diproses.", 422)

        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        w, h = img.size
        max_side = max(w, h)
        if max_side > MAX_SIDE:
            scale = MAX_SIDE / max_side
            new_w = max(1, round(w * scale))
            new_h = max(1, round(h * scale))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            w, h = img.size
            diperkecil_count += 1

        has_alpha_or_palette = (
            img.mode in ("RGBA", "LA", "PA", "P")
            or ("transparency" in img.info)
        )
        stream_io = io.BytesIO()
        if has_alpha_or_palette:
            img.save(stream_io, format="PNG")
        else:
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(stream_io, format="JPEG", quality=JPEG_QUALITY)
        stream_bytes = stream_io.getvalue()

        if u == "auto":
            img_pt_w = w * 72.0 / 96.0
            img_pt_h = h * 72.0 / 96.0
            max_img_pt = max(img_pt_w, img_pt_h)
            if max_img_pt > 842.0:
                scale_pt = 842.0 / max_img_pt
                img_pt_w *= scale_pt
                img_pt_h *= scale_pt

            if o == "tegak":
                if img_pt_w > img_pt_h:
                    page_w = min(img_pt_w, img_pt_h) + 2 * margin_pt
                    page_h = max(img_pt_w, img_pt_h) + 2 * margin_pt
                else:
                    page_w = img_pt_w + 2 * margin_pt
                    page_h = img_pt_h + 2 * margin_pt
            elif o == "mendatar":
                if img_pt_h > img_pt_w:
                    page_w = max(img_pt_w, img_pt_h) + 2 * margin_pt
                    page_h = min(img_pt_w, img_pt_h) + 2 * margin_pt
                else:
                    page_w = img_pt_w + 2 * margin_pt
                    page_h = img_pt_h + 2 * margin_pt
            else:
                page_w = img_pt_w + 2 * margin_pt
                page_h = img_pt_h + 2 * margin_pt
        else:
            base_w_mm, base_h_mm = PAGE_SIZES_MM[u]
            base_w_pt = base_w_mm * pt_per_mm
            base_h_pt = base_h_mm * pt_per_mm
            dim_kecil = min(base_w_pt, base_h_pt)
            dim_besar = max(base_w_pt, base_h_pt)

            if o == "auto":
                if w > h:
                    page_w, page_h = dim_besar, dim_kecil
                else:
                    page_w, page_h = dim_kecil, dim_besar
            elif o == "tegak":
                page_w, page_h = dim_kecil, dim_besar
            else:
                page_w, page_h = dim_besar, dim_kecil

        avail_x = margin_pt
        avail_y = margin_pt
        avail_w = max(1.0, page_w - 2 * margin_pt)
        avail_h = max(1.0, page_h - 2 * margin_pt)

        img_aspect = w / h
        avail_aspect = avail_w / avail_h

        if img_aspect > avail_aspect:
            draw_w = avail_w
            draw_h = avail_w / img_aspect
        else:
            draw_h = avail_h
            draw_w = avail_h * img_aspect

        draw_x = avail_x + (avail_w - draw_w) / 2.0
        draw_y = avail_y + (avail_h - draw_h) / 2.0
        rect = fitz.Rect(draw_x, draw_y, draw_x + draw_w, draw_y + draw_h)

        page = doc.new_page(width=page_w, height=page_h)
        page.insert_image(rect, stream=stream_bytes)

    pdf_bytes = doc.tobytes()
    doc.close()

    ringkasan = {
        "halaman": len(extracted),
        "gambar": len(extracted),
        "diperkecil": diperkecil_count,
        "sumber_bytes": total_bytes,
        "hasil_bytes": len(pdf_bytes),
    }
    return pdf_bytes, ringkasan
