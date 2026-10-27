"""Logika pas foto (Pas Foto) — fungsi murni di memori, tanpa HTTP, mudah diuji.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak menulis ke disk.
Semua validasi (magic bytes, dimensi, ukuran byte, ukuran pas foto, dpi, fokus,
dan batas KB) diproses di sini.

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
MAX_BYTES = 20 * 1024 * 1024  # 20 MB
MAX_PIXELS = 40_000_000
MAX_SIDE = 12_000
CHUNK_SIZE = 1024 * 1024

MAX_KB_MIN = 10
MAX_KB_MAX = 5000

SUPPORTED_SIZES: dict[str, tuple[float, float]] = {
    "2x3": (2.0, 3.0),
    "3x4": (3.0, 4.0),
    "4x6": (4.0, 6.0),
}
SUPPORTED_DPIS: tuple[int, ...] = (300, 600)
DEFAULT_DPI = 300
SUPPORTED_FOCUS: tuple[str, ...] = ("atas", "tengah", "bawah")
DEFAULT_FOCUS = "atas"

QUALITY_START = 95
QUALITY_MIN = 30
QUALITY_STEP = 5

# --- Magic bytes penanda format masukan -------------------------------------
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
RIFF_MAGIC = b"RIFF"
WEBP_MAGIC = b"WEBP"

# --- Kode error stabil ------------------------------------------------------
INVALID_REQUEST = "INVALID_REQUEST"
NO_FILE = "NO_FILE"
EMPTY_FILE = "EMPTY_FILE"
TOO_MANY_FILES = "TOO_MANY_FILES"
UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
DAMAGED_IMAGE = "DAMAGED_IMAGE"
UNSUPPORTED_SIZE = "UNSUPPORTED_SIZE"
INVALID_DPI = "INVALID_DPI"
INVALID_FOCUS = "INVALID_FOCUS"
INVALID_MAX_KB = "INVALID_MAX_KB"
TOO_LARGE = "TOO_LARGE"
TOO_MANY_PIXELS = "TOO_MANY_PIXELS"
SIDE_TOO_LARGE = "SIDE_TOO_LARGE"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class PasFotoError(Exception):
    """Kesalahan pembuatan pas foto dengan kode galat stabil dan status HTTP."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar OmniTools: {"error": {"code": ..., "message": ...}}."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class PasFotoResult:
    """Hasil pas foto di memori."""

    data: bytes
    size: str
    cm: str
    dpi: int
    width: int
    height: int
    output_bytes: int
    output_kb: int
    quality: int
    diperbesar: bool
    batas_terpenuhi: bool


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
    """Validasi ukuran berkas tidak melebihi MAX_BYTES (20 MB)."""
    if total_bytes > MAX_BYTES:
        raise PasFotoError(
            TOO_LARGE,
            "Ukuran berkas melebihi batas 20 MB. Perkecil gambar terlebih dahulu.",
            413,
        )


def normalize_size(value: Any) -> str:
    """Normalisasi pilihan ukuran (2x3, 3x4, 4x6). Bawaan '3x4'."""
    if value is None:
        return "3x4"
    val = str(value).strip().lower()
    if val not in SUPPORTED_SIZES:
        raise PasFotoError(
            UNSUPPORTED_SIZE,
            "Ukuran pas foto tidak valid. Pilihan yang tersedia: 2x3, 3x4, 4x6.",
            400,
        )
    return val


def normalize_dpi(value: Any) -> int:
    """Normalisasi pilihan DPI (300 atau 600). Bawaan 300."""
    if value is None:
        return DEFAULT_DPI
    try:
        val = int(value)
    except (ValueError, TypeError):
        raise PasFotoError(
            INVALID_DPI,
            "Pilihan DPI tidak valid. Hanya menerima 300 atau 600.",
            400,
        )
    if val not in SUPPORTED_DPIS:
        raise PasFotoError(
            INVALID_DPI,
            "Pilihan DPI tidak valid. Hanya menerima 300 atau 600.",
            400,
        )
    return val


def normalize_focus(value: Any) -> str:
    """Normalisasi fokus potongan (atas, tengah, bawah). Bawaan 'atas'."""
    if value is None:
        return DEFAULT_FOCUS
    val = str(value).strip().lower()
    if val not in SUPPORTED_FOCUS:
        raise PasFotoError(
            INVALID_FOCUS,
            "Fokus potongan tidak valid. Pilihan yang tersedia: atas, tengah, bawah.",
            400,
        )
    return val


def normalize_max_kb(value: Any) -> int | None:
    """Normalisasi batas ukuran berkas opsional dalam KB (10..5000), kosong/0 = tanpa batas."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise PasFotoError(
            INVALID_MAX_KB,
            "Batas ukuran berkas (KB) harus antara 10 sampai 5000 KB.",
            400,
        )
    if isinstance(value, (int, float)):
        val_float = float(value)
    elif isinstance(value, str):
        val_str = value.strip().replace(",", ".")
        if not val_str or val_str == "0":
            return None
        try:
            val_float = float(val_str)
        except ValueError:
            raise PasFotoError(
                INVALID_MAX_KB,
                "Batas ukuran berkas (KB) harus antara 10 sampai 5000 KB.",
                400,
            )
    else:
        try:
            val_float = float(value)
        except (ValueError, TypeError):
            raise PasFotoError(
                INVALID_MAX_KB,
                "Batas ukuran berkas (KB) harus antara 10 sampai 5000 KB.",
                400,
            )

    val_int = int(math.floor(val_float + 0.5))
    if val_int == 0:
        return None
    if val_int < MAX_KB_MIN or val_int > MAX_KB_MAX:
        raise PasFotoError(
            INVALID_MAX_KB,
            f"Batas ukuran berkas ({val_int} KB) di luar rentang {MAX_KB_MIN} sampai {MAX_KB_MAX} KB.",
            400,
        )
    return val_int


def calculate_pixels(cm_width: float, cm_height: float, dpi: int) -> tuple[int, int]:
    """Hitung dimensi piksel dari ukuran cm dan dpi: round(cm / 2.54 * dpi)."""
    target_w = int(round(cm_width / 2.54 * dpi))
    target_h = int(round(cm_height / 2.54 * dpi))
    return target_w, target_h


def _encode_jpeg(img: Image.Image, quality: int, dpi: int) -> bytes:
    """Simpan gambar ke format JPEG dengan dpi disematkan, tanpa menyalin EXIF asli."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, dpi=(dpi, dpi), optimize=True)
    return buf.getvalue()


def pas_foto(
    payload: bytes,
    size: str = "3x4",
    dpi: int | str = 300,
    fokus: str = "atas",
    max_kb: int | float | str | None = None,
) -> PasFotoResult:
    """Potong dan atur foto menjadi pas foto siap cetak di memori."""
    if not payload:
        raise PasFotoError(EMPTY_FILE, "Berkas gambar kosong (0 byte).", 400)

    check_total_size(len(payload))

    input_format = detect_format(payload)
    if not input_format:
        raise PasFotoError(
            UNSUPPORTED_FILE,
            "Berkas bukan gambar yang didukung. Hanya menerima JPG, PNG, atau WebP.",
            400,
        )

    norm_size = normalize_size(size)
    norm_dpi = normalize_dpi(dpi)
    norm_focus = normalize_focus(fokus)
    norm_max_kb = normalize_max_kb(max_kb)

    cm_w, cm_h = SUPPORTED_SIZES[norm_size]
    target_w, target_h = calculate_pixels(cm_w, cm_h, norm_dpi)

    # 1) Buka gambar & periksa batas sebelum decode penuh
    try:
        img = Image.open(io.BytesIO(payload))
    except Exception as exc:
        raise PasFotoError(
            DAMAGED_IMAGE,
            "Berkas gambar rusak atau tidak bisa dibaca.",
            422,
        ) from exc

    raw_w, raw_h = img.size
    if raw_w > MAX_SIDE or raw_h > MAX_SIDE:
        raise PasFotoError(
            SIDE_TOO_LARGE,
            f"Sisi gambar ({raw_w} × {raw_h}) melebihi batas {MAX_SIDE:,} piksel.",
            413,
        )

    if raw_w * raw_h > MAX_PIXELS:
        raise PasFotoError(
            TOO_MANY_PIXELS,
            f"Ukuran gambar {raw_w} × {raw_h} ({raw_w * raw_h:,} piksel) melebihi batas {MAX_PIXELS:,} piksel.",
            413,
        )

    # 2) Decode penuh berkas gambar
    try:
        img.load()
    except Image.DecompressionBombError as exc:
        raise PasFotoError(
            TOO_MANY_PIXELS,
            "Ukuran gambar terlalu besar untuk didekompresi.",
            413,
        ) from exc
    except Exception as exc:
        raise PasFotoError(
            DAMAGED_IMAGE,
            "Berkas gambar rusak atau tidak bisa dibaca.",
            422,
        ) from exc

    # 3) Hormati orientasi EXIF ponsel agar foto tidak miring
    try:
        transposed = ImageOps.exif_transpose(img)
        if transposed is not None:
            img = transposed
    except Exception:
        pass

    orig_w, orig_h = img.size

    # 4) Ratakan transparansi ke latar putih untuk JPEG
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        white_bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = Image.alpha_composite(white_bg, rgba).convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # 5) Skala "cover" ke rasio target lalu potong
    target_ratio = target_w / target_h
    orig_ratio = orig_w / orig_h

    if orig_ratio > target_ratio:
        # Gambar lebih lebar dari target -> potong horizontal (selalu tengah)
        crop_h = orig_h
        crop_w = int(round(orig_h * target_ratio))
        crop_w = min(crop_w, orig_w)
        left = (orig_w - crop_w) // 2
        top = 0
        right = left + crop_w
        bottom = orig_h
    else:
        # Gambar lebih tinggi dari target -> potong vertikal sesuai parameter fokus
        crop_w = orig_w
        crop_h = int(round(orig_w / target_ratio))
        crop_h = min(crop_h, orig_h)
        left = 0
        right = orig_w
        if norm_focus == "atas":
            top = 0
        elif norm_focus == "bawah":
            top = orig_h - crop_h
        else:  # tengah
            top = (orig_h - crop_h) // 2
        bottom = top + crop_h

    cropped = img.crop((left, top, right, bottom))

    # Cek apakah bagian yang dipotong lebih kecil dari dimensi target (perlu perbesaran/upscale)
    diperbesar = bool(crop_w < target_w or crop_h < target_h)

    # Ubah ukuran tepat ke target menggunakan filter LANCZOS
    result_img = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)

    # 6) Penyesuaian kualitas jika ada batas max_kb
    if norm_max_kb is None:
        best_quality = QUALITY_START
        out_data = _encode_jpeg(result_img, best_quality, norm_dpi)
        batas_terpenuhi = True
    else:
        target_bytes = norm_max_kb * 1024
        out_data = b""
        best_quality = QUALITY_MIN
        batas_terpenuhi = False

        for q in range(QUALITY_START, QUALITY_MIN - 1, -QUALITY_STEP):
            test_data = _encode_jpeg(result_img, q, norm_dpi)
            if len(test_data) <= target_bytes:
                out_data = test_data
                best_quality = q
                batas_terpenuhi = True
                break

        if not batas_terpenuhi:
            # Tetap kembalikan hasil terbaik di kualitas terendah
            out_data = _encode_jpeg(result_img, QUALITY_MIN, norm_dpi)
            best_quality = QUALITY_MIN
            batas_terpenuhi = False

    output_bytes = len(out_data)
    output_kb = int(math.ceil(output_bytes / 1024))
    cm_label = f"{cm_w:.1f}x{cm_h:.1f} cm"

    return PasFotoResult(
        data=out_data,
        size=norm_size,
        cm=cm_label,
        dpi=norm_dpi,
        width=target_w,
        height=target_h,
        output_bytes=output_bytes,
        output_kb=output_kb,
        quality=best_quality,
        diperbesar=diperbesar,
        batas_terpenuhi=batas_terpenuhi,
    )


def pas_foto_limits_payload() -> dict[str, Any]:
    """Payload batas dan opsi untuk Pas Foto."""
    sizes_info = []
    for s_id, (cw, ch) in SUPPORTED_SIZES.items():
        px_info: dict[str, dict[str, int]] = {}
        for d in SUPPORTED_DPIS:
            tw, th = calculate_pixels(cw, ch, d)
            px_info[str(d)] = {"width": tw, "height": th}
        sizes_info.append({
            "id": s_id,
            "label": f"{s_id} cm",
            "width_cm": cw,
            "height_cm": ch,
            "px": px_info,
        })

    return {
        "max_mb": MAX_BYTES // (1024 * 1024),
        "max_files": MAX_FILES,
        "max_pixels": MAX_PIXELS,
        "max_side": MAX_SIDE,
        "formats": ["jpeg", "png", "webp"],
        "sizes": sizes_info,
        "dpis": list(SUPPORTED_DPIS),
        "default_dpi": DEFAULT_DPI,
        "focuses": list(SUPPORTED_FOCUS),
        "default_focus": DEFAULT_FOCUS,
        "max_kb": {
            "min": MAX_KB_MIN,
            "max": MAX_KB_MAX,
        },
    }
