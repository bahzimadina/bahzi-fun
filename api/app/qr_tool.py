"""Logika pembuat kode QR dan barcode Code 128 di memori.

Modul ini tidak bergantung pada FastAPI dan tidak melakukan I/O disk.
Semua gambar diproses di memori lalu dibuang. Teks pengguna tidak pernah dicatat.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

import barcode
from barcode.errors import BarcodeError
from barcode.writer import ImageWriter
from PIL import Image
import qrcode
from qrcode.constants import (
    ERROR_CORRECT_H,
    ERROR_CORRECT_L,
    ERROR_CORRECT_M,
    ERROR_CORRECT_Q,
)

# Batas operasional alat
MAX_CHARS_QR = 1200
MAX_CHARS_BARCODE = 80
MAX_BYTES = 16384
DEFAULT_SIZE = 512
DEFAULT_MODE = "qr"
DEFAULT_CORRECTION = "M"
UKURAN_LIST = (256, 384, 512, 768, 1024)
MODES = ("qr", "barcode")

# Pemetaan tingkat ketahanan koreksi galat kode QR
CORRECTION_MAP = {
    "L": ERROR_CORRECT_L,
    "M": ERROR_CORRECT_M,
    "Q": ERROR_CORRECT_Q,
    "H": ERROR_CORRECT_H,
}

# Kode galat stabil
NO_TEXT = "NO_TEXT"
TEXT_TOO_LONG = "TEXT_TOO_LONG"
INVALID_SIZE = "INVALID_SIZE"
UNSUPPORTED_KIND = "UNSUPPORTED_KIND"
INVALID_CORRECTION = "INVALID_CORRECTION"
NOT_ENCODABLE = "NOT_ENCODABLE"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
INVALID_REQUEST = "INVALID_REQUEST"


class QrToolError(ValueError):
    """Galat operasional pembuat kode QR dan barcode."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class QrResult:
    """Hasil pembuatan gambar kode QR atau barcode."""

    content: bytes
    mode: str
    pixels: str
    bytes_count: int


def validate_params(
    mode: Any,
    teks: Any,
    ukuran: Any = DEFAULT_SIZE,
    koreksi: Any = DEFAULT_CORRECTION,
) -> tuple[str, str, int, str]:
    """Validasi parameter masukan sesuai batasan operasional."""
    # Pastikan mode dikenal sebelum memvalidasi panjang teks
    mode_str = str(mode).strip().lower() if mode is not None else DEFAULT_MODE
    if mode_str not in MODES:
        raise QrToolError(UNSUPPORTED_KIND, "Jenis kode tidak dikenal.", 400)

    # Validasi keberadaan teks
    if teks is None:
        raise QrToolError(NO_TEXT, "Isi dulu teks yang mau dijadikan kode.", 400)

    if not isinstance(teks, str):
        raise QrToolError(INVALID_REQUEST, "Field 'teks' harus berupa string.", 400)

    clean_teks = teks.strip()
    if not clean_teks:
        raise QrToolError(NO_TEXT, "Isi dulu teks yang mau dijadikan kode.", 400)

    # Batasi panjang teks berdasarkan mode aktif
    if mode_str == "qr" and len(clean_teks) > MAX_CHARS_QR:
        raise QrToolError(
            TEXT_TOO_LONG,
            "Teksnya kepanjangan. Maksimal 1.200 karakter untuk kode QR dan 80 karakter untuk barcode.",
            400,
        )
    if mode_str == "barcode" and len(clean_teks) > MAX_CHARS_BARCODE:
        raise QrToolError(
            TEXT_TOO_LONG,
            "Teksnya kepanjangan. Maksimal 1.200 karakter untuk kode QR dan 80 karakter untuk barcode.",
            400,
        )

    # Validasi pilihan ukuran piksel
    if ukuran is None or ukuran == "":
        clean_ukuran = DEFAULT_SIZE
    else:
        try:
            clean_ukuran = int(ukuran)
        except (ValueError, TypeError):
            raise QrToolError(
                INVALID_SIZE,
                "Ukuran gambar tidak dikenal. Pilih salah satu ukuran yang tersedia.",
                400,
            )
        if clean_ukuran not in UKURAN_LIST:
            raise QrToolError(
                INVALID_SIZE,
                "Ukuran gambar tidak dikenal. Pilih salah satu ukuran yang tersedia.",
                400,
            )

    # Validasi tingkat ketahanan kode QR
    clean_koreksi = DEFAULT_CORRECTION
    if mode_str == "qr":
        raw_koreksi = str(koreksi).strip().upper() if koreksi is not None else DEFAULT_CORRECTION
        if raw_koreksi not in CORRECTION_MAP:
            raise QrToolError(
                INVALID_CORRECTION,
                "Tingkat ketahanan kode QR tidak dikenal.",
                400,
            )
        clean_koreksi = raw_koreksi

    return mode_str, clean_teks, clean_ukuran, clean_koreksi


def _generate_qr(teks: str, ukuran: int, koreksi: str) -> tuple[bytes, str]:
    """Hasilkan gambar kode QR tajam di memori."""
    ec = CORRECTION_MAP[koreksi]
    qr = qrcode.QRCode(
        version=None,
        error_correction=ec,
        box_size=1,
        border=4,
    )
    qr.add_data(teks)
    qr.make(fit=True)
    raw = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    raw_w, raw_h = raw.size

    # Perbesar dengan faktor bulat menggunakan NEAREST agar modul tetap kotak tajam
    scale = max(1, ukuran // raw_w)
    scaled_w, scaled_h = raw_w * scale, raw_h * scale
    scaled = raw.resize((scaled_w, scaled_h), Image.Resampling.NEAREST)

    # Letakkan di tengah kanvas putih seukuran target
    canvas_size = max(ukuran, scaled_w)
    canvas = Image.new("RGB", (canvas_size, canvas_size), "white")
    ox = (canvas_size - scaled_w) // 2
    oy = (canvas_size - scaled_h) // 2
    canvas.paste(scaled, (ox, oy))

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue(), f"{canvas.width}x{canvas.height}"


def _generate_barcode(teks: str, ukuran: int) -> tuple[bytes, str]:
    """Hasilkan gambar barcode Code 128 tajam di memori."""
    buf = io.BytesIO()
    try:
        code = barcode.Code128(teks, writer=ImageWriter())
        code.write(buf)
    except (BarcodeError, ValueError):
        raise QrToolError(
            NOT_ENCODABLE,
            "Barcode Code 128 hanya bisa memuat huruf latin, angka, dan tanda baca dasar. Kode QR bisa memuat hampir semua teks.",
            400,
        )

    buf.seek(0)
    raw = Image.open(buf).copy()
    raw_w, raw_h = raw.size

    # Skala bilangan bulat dengan NEAREST bila kanvas lebih lebar dari barcode asli
    scale = max(1, ukuran // raw_w)
    if scale > 1 and (raw_h * scale) > int(ukuran * 0.8):
        scale = max(1, int(ukuran * 0.8) // raw_h)

    if scale > 1:
        scaled = raw.resize((raw_w * scale, raw_h * scale), Image.Resampling.NEAREST)
    else:
        scaled = raw

    # Kanvas proporsional dengan latar putih dan garis di tengah
    canvas_w = max(ukuran, scaled.width)
    canvas_h = max(scaled.height + 20, int(canvas_w * 0.4))

    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
    ox = (canvas_w - scaled.width) // 2
    oy = (canvas_h - scaled.height) // 2
    canvas.paste(scaled, (ox, oy))

    out_buf = io.BytesIO()
    canvas.save(out_buf, format="PNG")
    return out_buf.getvalue(), f"{canvas.width}x{canvas.height}"


def generate_code(
    mode: Any = DEFAULT_MODE,
    teks: Any = None,
    ukuran: Any = DEFAULT_SIZE,
    koreksi: Any = DEFAULT_CORRECTION,
) -> QrResult:
    """Buat gambar PNG kode QR atau barcode dari masukan pengguna."""
    clean_mode, clean_teks, clean_ukuran, clean_koreksi = validate_params(
        mode=mode,
        teks=teks,
        ukuran=ukuran,
        koreksi=koreksi,
    )

    if clean_mode == "barcode":
        content, pixels = _generate_barcode(clean_teks, clean_ukuran)
    else:
        content, pixels = _generate_qr(clean_teks, clean_ukuran, clean_koreksi)

    return QrResult(
        content=content,
        mode=clean_mode,
        pixels=pixels,
        bytes_count=len(content),
    )


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional untuk alat QR dan barcode."""
    return {
        "tool": "qr",
        "teks_maks_qr": MAX_CHARS_QR,
        "teks_maks_barcode": MAX_CHARS_BARCODE,
        "ukuran": list(UKURAN_LIST),
        "ukuran_bawaan": DEFAULT_SIZE,
        "mode": list(MODES),
        "jenis_barcode": ["Code 128"],
        "koreksi": [
            {"nilai": "L", "label": "Rendah, kode lebih longgar"},
            {"nilai": "M", "label": "Sedang, pilihan umum"},
            {"nilai": "Q", "label": "Tinggi, tetap terbaca bila agak kotor"},
            {"nilai": "H", "label": "Maksimal, paling tahan rusak"},
        ],
        "catatan": "Kode dibuat di memori lalu langsung dihapus, tidak disimpan.",
    }
