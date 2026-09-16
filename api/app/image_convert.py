"""Logika konversi format gambar — fungsi murni, tanpa HTTP, mudah diuji.

Modul ini tidak bergantung pada FastAPI/HTTP. Semua validasi (magic bytes,
dimensi, ukuran byte, format target, kualitas) diproses di sini.

Prinsip:
* Semua pemrosesan di memori (io.BytesIO). Tidak ada berkas ditulis ke disk.
* Format masukan diperiksa dari magic bytes, bukan ekstensi atau MIME klien.
* Nama dan isi berkas pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageOps

# --- Batas operasional ------------------------------------------------------
MAX_FILES = 1
MAX_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_PIXELS = 40_000_000
CHUNK_SIZE = 1024 * 1024  # 1 MB per potongan stream

# --- Format dan kualitas ----------------------------------------------------
TARGETS: dict[str, str] = {
    "jpeg": ".jpg",
    "png": ".png",
    "webp": ".webp",
}
TARGET_LABELS: dict[str, str] = {
    "jpeg": "JPG",
    "png": "PNG",
    "webp": "WebP",
}
MIME_TYPES: dict[str, str] = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}

QUALITY_MIN = 10
QUALITY_MAX = 100
QUALITY_DEFAULT = 85

# --- Magic bytes penanda format masukan -------------------------------------
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
RIFF_MAGIC = b"RIFF"
WEBP_MAGIC = b"WEBP"

# --- Kode error stabil ------------------------------------------------------
NO_FILES = "NO_FILES"
TOO_MANY_FILES = "TOO_MANY_FILES"
EMPTY_FILE = "EMPTY_FILE"
NOT_IMAGE = "NOT_IMAGE"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
UNSUPPORTED_TARGET = "UNSUPPORTED_TARGET"
INVALID_QUALITY = "INVALID_QUALITY"
IMAGE_UNREADABLE = "IMAGE_UNREADABLE"
IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"


class ImageConvertError(Exception):
    """Kesalahan konversi gambar dengan kode error dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons JSON standar: {"error": {"code": ..., "message": ...}}."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class ConvertResult:
    """Hasil konversi gambar di memori."""

    data: bytes
    input_format: str
    output_format: str
    width: int
    height: int
    input_bytes: int
    output_bytes: int


def detect_format(data: bytes) -> str | None:
    """Deteksi format gambar dari magic bytes (PNG, JPEG, WebP)."""
    if not data or len(data) < 3:
        return None
    if data.startswith(JPEG_MAGIC):
        return "jpeg"
    if data.startswith(PNG_MAGIC):
        return "png"
    if len(data) >= 12 and data.startswith(RIFF_MAGIC) and data[8:12] == WEBP_MAGIC:
        return "webp"
    return None


def is_supported_image(data: bytes) -> bool:
    """True bila format gambar didukung berdasarkan magic bytes."""
    return detect_format(data) is not None


def check_file_count(count: int) -> None:
    """Validasi jumlah berkas (tepat 1 berkas)."""
    if count <= 0:
        raise ImageConvertError(
            NO_FILES,
            "Tidak ada berkas yang dikirim. Sertakan satu berkas gambar pada field 'files'.",
            400,
        )
    if count > MAX_FILES:
        raise ImageConvertError(
            TOO_MANY_FILES,
            f"Maksimum {MAX_FILES} berkas per konversi, dikirim {count} berkas.",
            400,
        )


def check_total_size(total_bytes: int) -> None:
    """Validasi ukuran berkas tidak melebihi MAX_BYTES."""
    if total_bytes > MAX_BYTES:
        limit_mb = MAX_BYTES // (1024 * 1024)
        raise ImageConvertError(
            PAYLOAD_TOO_LARGE,
            f"Ukuran berkas melebihi batas {limit_mb} MB. Perkecil atau ubah ukuran gambar dulu.",
            413,
        )


def normalize_target(value: str | None) -> str:
    """Normalisasi nama format target dan pastikan didukung."""
    if not value or not value.strip():
        return "jpeg"
    val = value.strip().lower()
    if val == "jpg":
        val = "jpeg"
    if val not in TARGETS:
        raise ImageConvertError(
            UNSUPPORTED_TARGET,
            f"Format target '{value}' tidak didukung. Pilih jpeg, png, atau webp.",
            400,
        )
    return val


def normalize_quality(value: int | str | None) -> int:
    """Normalisasi nilai kualitas untuk JPEG/WebP (10-100)."""
    if value is None:
        return QUALITY_DEFAULT
    if isinstance(value, str):
        val_str = value.strip()
        if not val_str:
            return QUALITY_DEFAULT
        try:
            val_int = int(val_str)
        except ValueError:
            raise ImageConvertError(
                INVALID_QUALITY,
                f"Kualitas harus berupa angka bulat antara {QUALITY_MIN} dan {QUALITY_MAX}.",
                400,
            )
    elif isinstance(value, int):
        val_int = value
    else:
        try:
            val_int = int(value)
        except (ValueError, TypeError):
            raise ImageConvertError(
                INVALID_QUALITY,
                f"Kualitas harus berupa angka bulat antara {QUALITY_MIN} dan {QUALITY_MAX}.",
                400,
            )

    if val_int < QUALITY_MIN or val_int > QUALITY_MAX:
        raise ImageConvertError(
            INVALID_QUALITY,
            f"Nilai kualitas {val_int} di luar rentang {QUALITY_MIN} sampai {QUALITY_MAX}.",
            400,
        )
    return val_int


def convert_image(
    payload: bytes,
    target: str = "jpeg",
    quality: int | str | None = None,
) -> ConvertResult:
    """Konversi gambar di memori ke format target."""
    if not payload:
        raise ImageConvertError(EMPTY_FILE, "Berkas gambar kosong (0 byte).", 400)

    check_total_size(len(payload))

    input_format = detect_format(payload)
    if not input_format:
        raise ImageConvertError(
            NOT_IMAGE,
            "Berkas bukan gambar yang didukung. Hanya menerima PNG, JPEG, atau WebP.",
            400,
        )

    norm_target = normalize_target(target)
    norm_quality = normalize_quality(quality)

    try:
        img = Image.open(io.BytesIO(payload))
        img.load()
    except Image.DecompressionBombError as exc:
        raise ImageConvertError(
            IMAGE_TOO_LARGE,
            "Ukuran gambar terlalu besar untuk didekompresi.",
            413,
        ) from exc
    except Exception as exc:
        raise ImageConvertError(
            IMAGE_UNREADABLE,
            "Berkas gambar rusak atau tidak bisa dibaca.",
            422,
        ) from exc

    width, height = img.size
    if width * height > MAX_PIXELS:
        raise ImageConvertError(
            IMAGE_TOO_LARGE,
            f"Ukuran gambar {width} × {height} ({width * height:,} piksel) melebihi batas {MAX_PIXELS:,} piksel.",
            413,
        )

    # Sesuaikan orientasi jika foto memiliki metadata EXIF rotasi
    try:
        transposed = ImageOps.exif_transpose(img)
        if transposed is not None:
            img = transposed
    except Exception:
        pass

    out_buffer = io.BytesIO()

    try:
        if norm_target == "jpeg":
            # JPEG tidak mendukung transparansi, ratakan ke latar putih
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                rgba = img.convert("RGBA")
                white_bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                img = Image.alpha_composite(white_bg, rgba).convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.save(out_buffer, format="JPEG", quality=norm_quality, optimize=True)

        elif norm_target == "png":
            # Format PNG tidak memakai parameter quality
            if img.mode not in ("RGB", "RGBA", "L", "LA", "P", "1"):
                img = img.convert("RGBA" if "A" in img.mode else "RGB")
            img.save(out_buffer, format="PNG", optimize=True)

        elif norm_target == "webp":
            # WebP mendukung transparansi, pertahankan kanal alpha
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
            elif img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            img.save(out_buffer, format="WEBP", quality=norm_quality, optimize=True)

    except ImageConvertError:
        raise
    except Exception as exc:
        raise ImageConvertError(
            IMAGE_UNREADABLE,
            "Gagal memproses atau menyimpan hasil konversi gambar.",
            422,
        ) from exc

    output_data = out_buffer.getvalue()

    return ConvertResult(
        data=output_data,
        input_format=input_format,
        output_format=norm_target,
        width=img.width,
        height=img.height,
        input_bytes=len(payload),
        output_bytes=len(output_data),
    )
