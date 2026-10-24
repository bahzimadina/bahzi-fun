"""Logika kompres gambar (Image Compress) — fungsi murni di memori, tanpa HTTP, mudah diuji.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak menulis ke disk.
Semua validasi (magic bytes, dimensi, ukuran byte, target ukuran, format) diproses di sini.

Prinsip:
* Semua pemrosesan di memori (io.BytesIO). Tidak ada berkas ditulis ke disk.
* Format masukan diperiksa dari magic bytes, bukan ekstensi atau MIME klien.
* Nama dan isi berkas pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import math
from typing import Any

from PIL import Image, ImageOps

# --- Batas operasional ------------------------------------------------------
MAX_FILES = 1
MAX_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_PIXELS = 40_000_000
MAX_SIDE = 12_000
CHUNK_SIZE = 1024 * 1024

TARGET_KB_MIN = 10
TARGET_KB_MAX = 5000
TARGET_KB_DEFAULT = 200
TARGET_SHORTCUTS = [100, 200, 500, 1000]

SCALES: tuple[float, ...] = (1.0, 0.85, 0.7, 0.55, 0.45, 0.35, 0.25, 0.15)
QUALITY_MIN = 5
QUALITY_MAX = 95
DEFAULT_FORMAT = "jpeg"
SUPPORTED_FORMATS: tuple[str, ...] = ("jpeg", "webp")

MIME_TYPES: dict[str, str] = {
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}

EXTENSIONS: dict[str, str] = {
    "jpeg": ".jpg",
    "webp": ".webp",
}

# --- Magic bytes penanda format masukan -------------------------------------
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
RIFF_MAGIC = b"RIFF"
WEBP_MAGIC = b"WEBP"

# --- Kode error stabil ------------------------------------------------------
INVALID_REQUEST = "INVALID_REQUEST"
NO_FILE = "NO_FILE"
EMPTY_FILE = "EMPTY_FILE"
UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
DAMAGED_IMAGE = "DAMAGED_IMAGE"
TOO_LARGE = "TOO_LARGE"
TOO_MANY_PIXELS = "TOO_MANY_PIXELS"
SIDE_TOO_LARGE = "SIDE_TOO_LARGE"
INVALID_TARGET = "INVALID_TARGET"
TARGET_OUT_OF_RANGE = "TARGET_OUT_OF_RANGE"
UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
TARGET_UNREACHABLE = "TARGET_UNREACHABLE"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class CompressError(Exception):
    """Kesalahan kompresi gambar dengan kode galat stabil dan status HTTP."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        min_kb: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code
        self.min_kb = min_kb

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar OmniTools: {"error": {"code": ..., "message": ...}}."""
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.min_kb is not None:
            err["min_kb"] = self.min_kb
        return {"error": err}


@dataclass(frozen=True)
class CompressResult:
    """Hasil kompresi gambar di memori."""

    data: bytes
    output_format: str
    input_format: str
    width: int
    height: int
    output_kb: int
    quality: int
    scale: float
    already_small: bool


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


def check_total_size(total_bytes: int) -> None:
    """Validasi ukuran berkas tidak melebihi MAX_BYTES."""
    if total_bytes > MAX_BYTES:
        limit_mb = MAX_BYTES // (1024 * 1024)
        raise CompressError(
            TOO_LARGE,
            f"Ukuran berkas melebihi batas {limit_mb} MB. Perkecil atau potong gambar terlebih dahulu.",
            413,
        )


def normalize_target_kb(value: Any) -> int:
    """Normalisasi target ukuran dalam KB (10..5000), membulatkan desimal."""
    if value is None:
        return TARGET_KB_DEFAULT

    if isinstance(value, bool):
        raise CompressError(
            INVALID_TARGET,
            "Target ukuran harus berupa angka.",
            400,
        )

    if isinstance(value, (int, float)):
        val_float = float(value)
    elif isinstance(value, str):
        val_str = value.strip().replace(",", ".")
        if not val_str:
            return TARGET_KB_DEFAULT
        try:
            val_float = float(val_str)
        except ValueError:
            raise CompressError(
                INVALID_TARGET,
                "Target ukuran harus berupa angka.",
                400,
            )
    else:
        try:
            val_float = float(value)
        except (ValueError, TypeError):
            raise CompressError(
                INVALID_TARGET,
                "Target ukuran harus berupa angka.",
                400,
            )

    val_int = int(math.floor(val_float + 0.5))
    if val_int < TARGET_KB_MIN or val_int > TARGET_KB_MAX:
        raise CompressError(
            TARGET_OUT_OF_RANGE,
            f"Target ukuran ({val_int} KB) di luar rentang {TARGET_KB_MIN} sampai {TARGET_KB_MAX} KB.",
            400,
        )
    return val_int


def normalize_format(value: str | None) -> str:
    """Normalisasi pilihan format kompresi (jpeg atau webp). Bawaan 'jpeg'."""
    if value is None or not str(value).strip():
        return DEFAULT_FORMAT
    val = str(value).strip().lower()
    if val == "jpg":
        val = "jpeg"
    if val not in SUPPORTED_FORMATS:
        formats_str = ", ".join(SUPPORTED_FORMATS)
        raise CompressError(
            UNSUPPORTED_FORMAT,
            f"Format '{value}' tidak didukung. Pilihan yang tersedia: {formats_str}.",
            400,
        )
    return val


def _encode_image(img: Image.Image, out_format: str, quality: int) -> bytes:
    """Simpan gambar ke buffer memori dengan format dan kualitas tertentu."""
    buf = io.BytesIO()
    if out_format == "jpeg":
        img.save(buf, format="JPEG", quality=quality, optimize=True)
    elif out_format == "webp":
        img.save(buf, format="WEBP", quality=quality, optimize=True)
    return buf.getvalue()


def compress_image(
    payload: bytes,
    target_kb: int | float | str = 200,
    format: str = "jpeg",
) -> CompressResult:
    """Kompres gambar di memori agar ukurannya di bawah target_kb."""
    if not payload:
        raise CompressError(EMPTY_FILE, "Berkas gambar kosong (0 byte).", 400)

    check_total_size(len(payload))

    input_format = detect_format(payload)
    if not input_format:
        raise CompressError(
            UNSUPPORTED_FILE,
            "Berkas bukan gambar yang didukung. Hanya menerima PNG, JPEG, atau WebP.",
            400,
        )

    norm_target_kb = normalize_target_kb(target_kb)
    target_bytes = norm_target_kb * 1024
    norm_format = normalize_format(format)

    # 1) Buka gambar & periksa batas sebelum decode penuh
    try:
        img = Image.open(io.BytesIO(payload))
    except Exception as exc:
        raise CompressError(
            DAMAGED_IMAGE,
            "Berkas gambar rusak atau tidak bisa dibaca.",
            422,
        ) from exc

    orig_w, orig_h = img.size
    if orig_w > MAX_SIDE or orig_h > MAX_SIDE:
        raise CompressError(
            SIDE_TOO_LARGE,
            f"Sisi gambar ({orig_w} × {orig_h}) melebihi batas {MAX_SIDE:,} piksel.",
            413,
        )

    if orig_w * orig_h > MAX_PIXELS:
        raise CompressError(
            TOO_MANY_PIXELS,
            f"Ukuran gambar {orig_w} × {orig_h} ({orig_w * orig_h:,} piksel) melebihi batas {MAX_PIXELS:,} piksel.",
            413,
        )

    # 2) Bila berkas asli sudah <= target, kembalikan apa adanya
    if len(payload) <= target_bytes:
        return CompressResult(
            data=payload,
            output_format=input_format,
            input_format=input_format,
            width=orig_w,
            height=orig_h,
            output_kb=int(math.ceil(len(payload) / 1024)),
            quality=100,
            scale=1.0,
            already_small=True,
        )

    # 3) Decode penuh berkas gambar
    try:
        img.load()
    except Image.DecompressionBombError as exc:
        raise CompressError(
            TOO_MANY_PIXELS,
            "Ukuran gambar terlalu besar untuk didekompresi.",
            413,
        ) from exc
    except Exception as exc:
        raise CompressError(
            DAMAGED_IMAGE,
            "Berkas gambar rusak atau tidak bisa dibaca.",
            422,
        ) from exc

    # 4) Hormati orientasi EXIF
    try:
        transposed = ImageOps.exif_transpose(img)
        if transposed is not None:
            img = transposed
    except Exception:
        pass

    curr_w, curr_h = img.size

    # 5) Ratakan transparansi jika perlu
    if norm_format == "jpeg":
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            white_bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            img = Image.alpha_composite(white_bg, rgba).convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")
    elif norm_format == "webp":
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            if img.mode != "RGBA":
                img = img.convert("RGBA")
        elif img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

    # 6) Tangga skala dan pencarian biner kualitas
    min_achieved_bytes: int = 1 << 60

    for scale in SCALES:
        if scale == 1.0:
            scaled_img = img
        else:
            new_w = max(1, int(round(curr_w * scale)))
            new_h = max(1, int(round(curr_h * scale)))
            scaled_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Cek kualitas terendah terlebih dahulu untuk memangkas iterasi yang mustahil
        data_qmin = _encode_image(scaled_img, norm_format, QUALITY_MIN)
        size_qmin = len(data_qmin)
        if size_qmin < min_achieved_bytes:
            min_achieved_bytes = size_qmin

        if size_qmin > target_bytes:
            # Bahkan di kualitas minimum skala ini masih melebihi target
            continue

        # Cek apakah kualitas tertinggi langsung muat
        data_qmax = _encode_image(scaled_img, norm_format, QUALITY_MAX)
        size_qmax = len(data_qmax)
        if size_qmax < min_achieved_bytes:
            min_achieved_bytes = size_qmax

        if size_qmax <= target_bytes:
            return CompressResult(
                data=data_qmax,
                output_format=norm_format,
                input_format=input_format,
                width=scaled_img.width,
                height=scaled_img.height,
                output_kb=int(math.ceil(size_qmax / 1024)),
                quality=QUALITY_MAX,
                scale=scale,
                already_small=False,
            )

        # Binary search kualitas antara QUALITY_MIN dan QUALITY_MAX
        best_q = QUALITY_MIN
        best_data = data_qmin
        low = QUALITY_MIN + 1
        high = QUALITY_MAX - 1

        while low <= high:
            mid = (low + high) // 2
            test_data = _encode_image(scaled_img, norm_format, mid)
            test_size = len(test_data)
            if test_size < min_achieved_bytes:
                min_achieved_bytes = test_size

            if test_size <= target_bytes:
                best_q = mid
                best_data = test_data
                low = mid + 1
            else:
                high = mid - 1

        return CompressResult(
            data=best_data,
            output_format=norm_format,
            input_format=input_format,
            width=scaled_img.width,
            height=scaled_img.height,
            output_kb=int(math.ceil(len(best_data) / 1024)),
            quality=best_q,
            scale=scale,
            already_small=False,
        )

    # 7) Tidak ada kombinasi yang muat sampai skala terkecil
    min_kb = max(norm_target_kb + 1, int(math.ceil(min_achieved_bytes / 1024)))
    raise CompressError(
        TARGET_UNREACHABLE,
        f"Target {norm_target_kb} KB terlalu kecil untuk gambar ini. Ukuran terkecil yang bisa dicapai adalah {min_kb} KB.",
        422,
        min_kb=min_kb,
    )


def limits_payload() -> dict[str, Any]:
    """Payload batas dan opsi untuk Image Compress."""
    return {
        "max_mb": MAX_BYTES // (1024 * 1024),
        "max_files": MAX_FILES,
        "max_pixels": MAX_PIXELS,
        "max_side": MAX_SIDE,
        "target_kb": {
            "min": TARGET_KB_MIN,
            "max": TARGET_KB_MAX,
            "default": TARGET_KB_DEFAULT,
            "shortcuts": TARGET_SHORTCUTS,
        },
        "formats": list(SUPPORTED_FORMATS),
    }
