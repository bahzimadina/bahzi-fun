"""Logika filter dan efek gambar (Image Filter) — fungsi murni, tanpa HTTP, mudah diuji.

Modul ini tidak bergantung pada FastAPI/HTTP. Semua validasi (magic bytes,
dimensi, ukuran byte, suasana, penyetelan, format, kualitas) diproses di sini.

Prinsip:
* Semua pemrosesan di memori (io.BytesIO). Tidak ada berkas ditulis ke disk.
* Format masukan diperiksa dari magic bytes, bukan ekstensi atau MIME klien.
* Nama dan isi berkas pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

# --- Batas operasional ------------------------------------------------------
MAX_FILES = 1
MAX_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_PIXELS = 40_000_000
MAX_SIDE = 12_000
CHUNK_SIZE = 1024 * 1024

# --- Format dan target ------------------------------------------------------
TARGETS: dict[str, str] = {
    "jpeg": ".jpg",
    "png": ".png",
    "webp": ".webp",
}

TARGET_LABELS: dict[str, str] = {
    "jpeg": "JPEG",
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
QUALITY_DEFAULT = 90

# --- Pilihan suasana (preset) -----------------------------------------------
PRESETS: list[dict[str, str]] = [
    {"id": "asli", "label": "Asli"},
    {"id": "hitam-putih", "label": "Hitam putih"},
    {"id": "sepia", "label": "Sepia"},
    {"id": "pudar", "label": "Pudar"},
    {"id": "hangat", "label": "Hangat"},
    {"id": "dingin", "label": "Dingin"},
]

PRESET_IDS: tuple[str, ...] = tuple(p["id"] for p in PRESETS)

# --- Rentang penyetelan -----------------------------------------------------
ADJUSTMENTS: dict[str, dict[str, float]] = {
    "kecerahan": {"min": -50.0, "max": 50.0, "default": 0.0, "step": 1.0},
    "kontras": {"min": -50.0, "max": 50.0, "default": 0.0, "step": 1.0},
    "saturasi": {"min": -50.0, "max": 50.0, "default": 0.0, "step": 1.0},
    "blur": {"min": 0.0, "max": 10.0, "default": 0.0, "step": 0.5},
    "vignette": {"min": 0.0, "max": 100.0, "default": 0.0, "step": 1.0},
}

SEPIA_MATRIX = (
    0.393, 0.769, 0.189, 0,
    0.349, 0.686, 0.168, 0,
    0.272, 0.534, 0.131, 0,
)

# --- Magic bytes penanda format masukan -------------------------------------
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
RIFF_MAGIC = b"RIFF"
WEBP_MAGIC = b"WEBP"

# --- Kode error stabil ------------------------------------------------------
INVALID_REQUEST = "INVALID_REQUEST"
NO_FILE = "NO_FILE"
UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
EMPTY_FILE = "EMPTY_FILE"
DAMAGED_IMAGE = "DAMAGED_IMAGE"
TOO_LARGE = "TOO_LARGE"
TOO_MANY_PIXELS = "TOO_MANY_PIXELS"
SIDE_TOO_LARGE = "SIDE_TOO_LARGE"
UNSUPPORTED_PRESET = "UNSUPPORTED_PRESET"
INVALID_NUMBER = "INVALID_NUMBER"
OUT_OF_RANGE = "OUT_OF_RANGE"
UNSUPPORTED_TARGET = "UNSUPPORTED_TARGET"
INVALID_QUALITY = "INVALID_QUALITY"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class FilterError(Exception):
    """Kesalahan filter gambar dengan kode error dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons JSON standar: {"error": {"code": ..., "message": ...}}."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class FilterResult:
    """Hasil filter gambar di memori."""

    data: bytes
    output_format: str
    input_format: str
    width: int
    height: int


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
        raise FilterError(
            TOO_LARGE,
            f"Ukuran berkas melebihi batas {limit_mb} MB. Perkecil atau kompres gambar terlebih dahulu.",
            413,
        )


def normalize_suasana(value: str | None) -> str:
    """Normalisasi pilihan suasana gambar. Bawaan 'asli'."""
    if value is None or not str(value).strip():
        return "asli"
    val = str(value).strip().lower()
    if val not in PRESET_IDS:
        presets_str = ", ".join(PRESET_IDS)
        raise FilterError(
            UNSUPPORTED_PRESET,
            f"Suasana '{value}' tidak didukung. Pilihan yang tersedia: {presets_str}.",
            400,
        )
    return val


def normalize_adjustment(name: str, value: int | float | str | None) -> float:
    """Normalisasi angka penyetelan dengan titik atau koma desimal."""
    meta = ADJUSTMENTS[name]
    if value is None:
        return meta["default"]
    if isinstance(value, (int, float)):
        val_float = float(value)
    elif isinstance(value, str):
        val_str = value.strip().replace(",", ".")
        if not val_str:
            return meta["default"]
        try:
            val_float = float(val_str)
        except ValueError:
            raise FilterError(
                INVALID_NUMBER,
                f"Nilai {name} harus berupa angka.",
                400,
            )
    else:
        try:
            val_float = float(value)
        except (ValueError, TypeError):
            raise FilterError(
                INVALID_NUMBER,
                f"Nilai {name} harus berupa angka.",
                400,
            )

    min_val = meta["min"]
    max_val = meta["max"]
    if val_float < min_val or val_float > max_val:
        raise FilterError(
            OUT_OF_RANGE,
            f"Nilai {name} ({val_float:g}) di luar rentang {min_val:g} sampai {max_val:g}.",
            400,
        )
    return val_float


def normalize_target(value: str | None) -> str:
    """Normalisasi format target (tetap, jpeg, png, webp). Bawaan 'tetap'."""
    if value is None or not str(value).strip():
        return "tetap"
    val = str(value).strip().lower()
    if val == "jpg":
        val = "jpeg"
    if val not in ("tetap", "jpeg", "png", "webp"):
        raise FilterError(
            UNSUPPORTED_TARGET,
            f"Format target '{value}' tidak didukung. Pilih tetap, jpeg, png, atau webp.",
            400,
        )
    return val


def normalize_quality(value: int | str | None) -> int:
    """Normalisasi nilai kualitas untuk JPEG/WebP (10-100). Bawaan 90."""
    if value is None:
        return QUALITY_DEFAULT
    if isinstance(value, str):
        val_str = value.strip().replace(",", ".")
        if not val_str:
            return QUALITY_DEFAULT
        try:
            val_float = float(val_str)
            val_int = int(val_float)
            if val_float != val_int:
                raise ValueError
        except ValueError:
            raise FilterError(
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
            raise FilterError(
                INVALID_QUALITY,
                f"Kualitas harus berupa angka bulat antara {QUALITY_MIN} dan {QUALITY_MAX}.",
                400,
            )

    if val_int < QUALITY_MIN or val_int > QUALITY_MAX:
        raise FilterError(
            INVALID_QUALITY,
            f"Nilai kualitas {val_int} di luar rentang {QUALITY_MIN} sampai {QUALITY_MAX}.",
            400,
        )
    return val_int


def filter_image(
    payload: bytes,
    suasana: str = "asli",
    kecerahan: str | float | int = "0",
    kontras: str | float | int = "0",
    saturasi: str | float | int = "0",
    blur: str | float | int = "0",
    vignette: str | float | int = "0",
    format: str = "tetap",
    kualitas: str | int = "90",
) -> FilterResult:
    """Filter dan sesuaikan gambar di memori sesuai urutan operasi standar."""
    if not payload:
        raise FilterError(EMPTY_FILE, "Berkas gambar kosong (0 byte).", 400)

    check_total_size(len(payload))

    input_format = detect_format(payload)
    if not input_format:
        raise FilterError(
            UNSUPPORTED_FILE,
            "Berkas bukan gambar yang didukung. Hanya menerima PNG, JPEG, atau WebP.",
            400,
        )

    norm_suasana = normalize_suasana(suasana)
    norm_kecerahan = normalize_adjustment("kecerahan", kecerahan)
    norm_kontras = normalize_adjustment("kontras", kontras)
    norm_saturasi = normalize_adjustment("saturasi", saturasi)
    norm_blur = normalize_adjustment("blur", blur)
    norm_vignette = normalize_adjustment("vignette", vignette)
    norm_target = normalize_target(format)
    norm_quality = normalize_quality(kualitas)

    # 1) Buka gambar & periksa batas sebelum proses berat
    try:
        img = Image.open(io.BytesIO(payload))
    except Exception as exc:
        raise FilterError(
            DAMAGED_IMAGE,
            "Berkas gambar rusak atau tidak bisa dibaca.",
            422,
        ) from exc

    width_px, height_px = img.size
    if width_px > MAX_SIDE or height_px > MAX_SIDE:
        raise FilterError(
            SIDE_TOO_LARGE,
            f"Sisi gambar ({width_px} × {height_px}) melebihi batas {MAX_SIDE:,} piksel.",
            413,
        )

    if width_px * height_px > MAX_PIXELS:
        raise FilterError(
            TOO_MANY_PIXELS,
            f"Ukuran gambar {width_px} × {height_px} ({width_px * height_px:,} piksel) melebihi batas {MAX_PIXELS:,} piksel.",
            413,
        )

    try:
        img.load()
    except Image.DecompressionBombError as exc:
        raise FilterError(
            TOO_MANY_PIXELS,
            "Ukuran gambar terlalu besar untuk didekompresi.",
            413,
        ) from exc
    except Exception as exc:
        raise FilterError(
            DAMAGED_IMAGE,
            "Berkas gambar rusak atau tidak bisa dibaca.",
            422,
        ) from exc

    # 2) Hormati orientasi EXIF
    try:
        transposed = ImageOps.exif_transpose(img)
        if transposed is not None:
            img = transposed
    except Exception:
        pass

    # 3) Suasana
    if norm_suasana == "hitam-putih":
        if img.mode == "RGBA":
            r, g, b, a = img.split()
            gray = img.convert("L")
            img = Image.merge("RGBA", (gray, gray, gray, a))
        else:
            img = img.convert("L").convert("RGB")

    elif norm_suasana == "sepia":
        if img.mode == "RGBA":
            r, g, b, a = img.split()
            rgb = Image.merge("RGB", (r, g, b)).convert("RGB", SEPIA_MATRIX)
            r2, g2, b2 = rgb.split()
            img = Image.merge("RGBA", (r2, g2, b2, a))
        else:
            img = img.convert("RGB").convert("RGB", SEPIA_MATRIX)

    elif norm_suasana == "pudar":
        # turunkan kontras dan saturasi, lalu campur sedikit abu-abu hangat terang
        if img.mode == "RGBA":
            r, g, b, a = img.split()
            rgb = Image.merge("RGB", (r, g, b))
            rgb = ImageEnhance.Contrast(rgb).enhance(0.85)
            rgb = ImageEnhance.Color(rgb).enhance(0.75)
            overlay = Image.new("RGB", rgb.size, (240, 235, 220))
            rgb = Image.blend(rgb, overlay, 0.15)
            r2, g2, b2 = rgb.split()
            img = Image.merge("RGBA", (r2, g2, b2, a))
        else:
            rgb = img.convert("RGB")
            rgb = ImageEnhance.Contrast(rgb).enhance(0.85)
            rgb = ImageEnhance.Color(rgb).enhance(0.75)
            overlay = Image.new("RGB", rgb.size, (240, 235, 220))
            img = Image.blend(rgb, overlay, 0.15)

    elif norm_suasana == "hangat":
        # naikkan kanal merah sedikit, turunkan biru sedikit
        if img.mode == "RGBA":
            r, g, b, a = img.split()
            r = r.point(lambda i: min(255, int(i * 1.1)))
            b = b.point(lambda i: max(0, int(i * 0.9)))
            img = Image.merge("RGBA", (r, g, b, a))
        else:
            rgb = img.convert("RGB")
            r, g, b = rgb.split()
            r = r.point(lambda i: min(255, int(i * 1.1)))
            b = b.point(lambda i: max(0, int(i * 0.9)))
            img = Image.merge("RGB", (r, g, b))

    elif norm_suasana == "dingin":
        # kebalikannya: turunkan merah sedikit, naikkan biru sedikit
        if img.mode == "RGBA":
            r, g, b, a = img.split()
            r = r.point(lambda i: max(0, int(i * 0.9)))
            b = b.point(lambda i: min(255, int(i * 1.1)))
            img = Image.merge("RGBA", (r, g, b, a))
        else:
            rgb = img.convert("RGB")
            r, g, b = rgb.split()
            r = r.point(lambda i: max(0, int(i * 0.9)))
            b = b.point(lambda i: min(255, int(i * 1.1)))
            img = Image.merge("RGB", (r, g, b))

    # 4) Kecerahan (-50..50) -> faktor 1 + nilai/100
    if norm_kecerahan != 0.0:
        factor = 1.0 + (norm_kecerahan / 100.0)
        img = ImageEnhance.Brightness(img).enhance(factor)

    # 5) Kontras (-50..50) -> faktor 1 + nilai/100
    if norm_kontras != 0.0:
        factor = 1.0 + (norm_kontras / 100.0)
        img = ImageEnhance.Contrast(img).enhance(factor)

    # 6) Saturasi (-50..50) -> faktor 1 + nilai/100
    if norm_saturasi != 0.0:
        factor = 1.0 + (norm_saturasi / 100.0)
        img = ImageEnhance.Color(img).enhance(factor)

    # 7) Blur (0..10) -> ImageFilter.GaussianBlur radius nilai/2
    if norm_blur > 0.0:
        img = img.filter(ImageFilter.GaussianBlur(radius=norm_blur / 2.0))

    # 8) Vignette (0..100) -> topeng radial halus, composite dengan versi gelap
    if norm_vignette > 0.0:
        v_factor = norm_vignette / 100.0
        dark = ImageEnhance.Brightness(img).enhance(max(0.0, 1.0 - v_factor * 0.85))
        mask = Image.radial_gradient("L").resize(img.size, Image.Resampling.BILINEAR)
        if v_factor < 1.0:
            mask = mask.point(lambda p: int(p * v_factor))
        img = Image.composite(dark, img, mask)

    # 9) Tulis ke format tujuan
    effective_target = input_format if norm_target == "tetap" else norm_target

    out_buffer = io.BytesIO()
    try:
        if effective_target == "jpeg":
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                rgba = img.convert("RGBA")
                white_bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                img = Image.alpha_composite(white_bg, rgba).convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.save(out_buffer, format="JPEG", quality=norm_quality, optimize=True)

        elif effective_target == "png":
            if img.mode not in ("RGB", "RGBA", "L", "LA", "P", "1"):
                img = img.convert("RGBA" if "A" in img.mode else "RGB")
            img.save(out_buffer, format="PNG", optimize=True)

        elif effective_target == "webp":
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
            elif img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            img.save(out_buffer, format="WEBP", quality=norm_quality, optimize=True)

    except FilterError:
        raise
    except Exception as exc:
        raise FilterError(
            DAMAGED_IMAGE,
            "Gagal memproses atau menyimpan hasil filter gambar.",
            422,
        ) from exc

    output_data = out_buffer.getvalue()

    return FilterResult(
        data=output_data,
        output_format=effective_target,
        input_format=input_format,
        width=img.width,
        height=img.height,
    )


def limits_payload() -> dict[str, Any]:
    """Payload batas dan opsi untuk Image Filter."""
    return {
        "max_mb": MAX_BYTES // (1024 * 1024),
        "max_files": MAX_FILES,
        "max_pixels": MAX_PIXELS,
        "max_side": MAX_SIDE,
        "formats": ["png", "jpeg", "webp"],
        "targets": ["tetap", "jpeg", "png", "webp"],
        "presets": PRESETS,
        "adjustments": ADJUSTMENTS,
        "quality": {
            "min": QUALITY_MIN,
            "max": QUALITY_MAX,
            "default": QUALITY_DEFAULT,
        },
    }
