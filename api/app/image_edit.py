"""Logika edit gambar (Image Editor) — fungsi murni, tanpa HTTP, mudah diuji.

Modul ini tidak bergantung pada FastAPI/HTTP. Semua validasi (magic bytes,
dimensi, ukuran byte, putar, balik, rasio, patokan, orientasi, format, kualitas)
diproses di sini.

Prinsip:
* Semua pemrosesan di memori (io.BytesIO). Tidak ada berkas ditulis ke disk.
* Format masukan diperiksa dari magic bytes, bukan ekstensi atau MIME klien.
* Nama dan isi berkas pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageOps

# --- Batas operasional ------------------------------------------------------
MAX_FILES = 1
MAX_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_PIXELS = 40_000_000
CHUNK_SIZE = 1024 * 1024

# --- Format dan kualitas ----------------------------------------------------
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

RATIOS: dict[str, tuple[int, int] | None] = {
    "bebas": None,
    "1:1": (1, 1),
    "4:5": (4, 5),
    "5:4": (5, 4),
    "16:9": (16, 9),
    "9:16": (9, 16),
    "3:2": (3, 2),
    "2:3": (2, 3),
}

ANCHORS: tuple[str, ...] = ("tengah", "atas", "bawah", "kiri", "kanan")
FLIP_OPTIONS: tuple[str, ...] = ("tidak", "horizontal", "vertikal")
ROTATE_OPTIONS: tuple[int, ...] = (0, 90, 180, 270)

# --- Magic bytes penanda format masukan -------------------------------------
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
RIFF_MAGIC = b"RIFF"
WEBP_MAGIC = b"WEBP"

# --- Kode error stabil ------------------------------------------------------
NOT_IMAGE = "NOT_IMAGE"
EMPTY_FILE = "EMPTY_FILE"
INVALID_REQUEST = "INVALID_REQUEST"
UNSUPPORTED_ROTATE = "UNSUPPORTED_ROTATE"
UNSUPPORTED_FLIP = "UNSUPPORTED_FLIP"
UNSUPPORTED_RATIO = "UNSUPPORTED_RATIO"
UNSUPPORTED_ANCHOR = "UNSUPPORTED_ANCHOR"
INVALID_BOOLEAN = "INVALID_BOOLEAN"
UNSUPPORTED_TARGET = "UNSUPPORTED_TARGET"
INVALID_QUALITY = "INVALID_QUALITY"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
TOO_MANY_PIXELS = "TOO_MANY_PIXELS"
IMAGE_UNREADABLE = "IMAGE_UNREADABLE"


class ImageEditError(Exception):
    """Kesalahan edit gambar dengan kode error dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons JSON standar: {"error": {"code": ..., "message": ...}}."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class EditResult:
    """Hasil edit gambar di memori."""

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


def check_total_size(total_bytes: int) -> None:
    """Validasi ukuran berkas tidak melebihi MAX_BYTES."""
    if total_bytes > MAX_BYTES:
        limit_mb = MAX_BYTES // (1024 * 1024)
        raise ImageEditError(
            PAYLOAD_TOO_LARGE,
            f"Ukuran berkas melebihi batas {limit_mb} MB. Perkecil atau ubah ukuran gambar dulu.",
            413,
        )


def normalize_rotate(value: int | str | None) -> int:
    """Normalisasi nilai rotasi (0, 90, 180, 270). Bawaan 0."""
    if value is None:
        return 0
    if isinstance(value, str):
        val_str = value.strip()
        if not val_str:
            return 0
        try:
            val_int = int(val_str)
        except ValueError:
            raise ImageEditError(
                UNSUPPORTED_ROTATE,
                "Pilihan rotasi tidak didukung. Pilih 0, 90, 180, atau 270.",
                400,
            )
    elif isinstance(value, int):
        val_int = value
    else:
        try:
            val_int = int(value)
        except (ValueError, TypeError):
            raise ImageEditError(
                UNSUPPORTED_ROTATE,
                "Pilihan rotasi tidak didukung. Pilih 0, 90, 180, atau 270.",
                400,
            )

    if val_int not in ROTATE_OPTIONS:
        raise ImageEditError(
            UNSUPPORTED_ROTATE,
            "Pilihan rotasi tidak didukung. Pilih 0, 90, 180, atau 270.",
            400,
        )
    return val_int


def normalize_flip(value: str | None) -> str:
    """Normalisasi pilihan balik (tidak, horizontal, vertikal). Bawaan tidak."""
    if value is None or not value.strip():
        return "tidak"
    val = value.strip().lower()
    if val not in FLIP_OPTIONS:
        raise ImageEditError(
            UNSUPPORTED_FLIP,
            "Pilihan balik tidak didukung. Pilih tidak, horizontal, atau vertikal.",
            400,
        )
    return val


def normalize_ratio(value: str | None) -> str:
    """Normalisasi rasio potong. Bawaan bebas."""
    if value is None or not value.strip():
        return "bebas"
    val = value.strip().lower()
    if val not in RATIOS:
        raise ImageEditError(
            UNSUPPORTED_RATIO,
            "Pilihan rasio tidak didukung. Pilih bebas, 1:1, 4:5, 5:4, 16:9, 9:16, 3:2, atau 2:3.",
            400,
        )
    return val


def normalize_anchor(value: str | None) -> str:
    """Normalisasi patokan pemotongan. Bawaan tengah."""
    if value is None or not value.strip():
        return "tengah"
    val = value.strip().lower()
    if val not in ANCHORS:
        raise ImageEditError(
            UNSUPPORTED_ANCHOR,
            "Pilihan patokan tidak didukung. Pilih tengah, atas, bawah, kiri, atau kanan.",
            400,
        )
    return val


def normalize_orientation(value: str | None) -> bool:
    """Normalisasi opsi orientasi EXIF (ya/tidak). Bawaan ya (True)."""
    if value is None or not value.strip():
        return True
    val = value.strip().lower()
    if val == "ya":
        return True
    if val == "tidak":
        return False
    raise ImageEditError(
        INVALID_BOOLEAN,
        "Pilihan orientasi harus 'ya' atau 'tidak'.",
        400,
    )


def normalize_target(value: str | None) -> str:
    """Normalisasi format target (tetap, jpeg, png, webp). Bawaan tetap."""
    if value is None or not value.strip():
        return "tetap"
    val = value.strip().lower()
    if val == "jpg":
        val = "jpeg"
    if val not in ("tetap", "jpeg", "png", "webp"):
        raise ImageEditError(
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
        val_str = value.strip()
        if not val_str:
            return QUALITY_DEFAULT
        try:
            val_int = int(val_str)
        except ValueError:
            raise ImageEditError(
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
            raise ImageEditError(
                INVALID_QUALITY,
                f"Kualitas harus berupa angka bulat antara {QUALITY_MIN} dan {QUALITY_MAX}.",
                400,
            )

    if val_int < QUALITY_MIN or val_int > QUALITY_MAX:
        raise ImageEditError(
            INVALID_QUALITY,
            f"Nilai kualitas {val_int} di luar rentang {QUALITY_MIN} sampai {QUALITY_MAX}.",
            400,
        )
    return val_int


def crop_to_ratio(img: Image.Image, ratio_str: str, anchor: str) -> Image.Image:
    """Potong gambar sebesar mungkin sesuai rasio dan patokan."""
    if ratio_str == "bebas" or ratio_str not in RATIOS or RATIOS[ratio_str] is None:
        return img

    rw, rh = RATIOS[ratio_str]
    w, h = img.size
    target_ratio = rw / rh
    current_ratio = w / h

    if abs(current_ratio - target_ratio) < 1e-7:
        return img

    if current_ratio > target_ratio:
        # Gambar lebih lebar dari rasio target -> kurangi lebar
        crop_h = h
        crop_w = max(1, min(w, int(math.floor(h * rw / rh))))
        diff_x = w - crop_w
        if anchor == "kiri":
            left = 0
        elif anchor == "kanan":
            left = diff_x
        else:
            left = diff_x // 2
        top = 0
    else:
        # Gambar lebih tinggi dari rasio target -> kurangi tinggi
        crop_w = w
        crop_h = max(1, min(h, int(math.floor(w * rh / rw))))
        diff_y = h - crop_h
        if anchor == "atas":
            top = 0
        elif anchor == "bawah":
            top = diff_y
        else:
            top = diff_y // 2
        left = 0

    left = max(0, min(left, w - crop_w))
    top = max(0, min(top, h - crop_h))
    right = left + crop_w
    bottom = top + crop_h

    return img.crop((left, top, right, bottom))


def edit_image(
    payload: bytes,
    putar: int | str | None = 0,
    balik: str | None = "tidak",
    rasio: str | None = "bebas",
    patokan: str | None = "tengah",
    orientasi: str | None = "ya",
    format: str | None = "tetap",
    kualitas: int | str | None = 90,
) -> EditResult:
    """Edit gambar di memori sesuai urutan operasi standar."""
    if not payload:
        raise ImageEditError(EMPTY_FILE, "Berkas gambar kosong (0 byte).", 400)

    check_total_size(len(payload))

    input_format = detect_format(payload)
    if not input_format:
        raise ImageEditError(
            NOT_IMAGE,
            "Berkas bukan gambar yang didukung. Hanya menerima PNG, JPEG, atau WebP.",
            400,
        )

    norm_rotate = normalize_rotate(putar)
    norm_flip = normalize_flip(balik)
    norm_ratio = normalize_ratio(rasio)
    norm_anchor = normalize_anchor(patokan)
    norm_orientation = normalize_orientation(orientasi)
    norm_target = normalize_target(format)
    norm_quality = normalize_quality(kualitas)

    try:
        img = Image.open(io.BytesIO(payload))
        img.load()
    except Image.DecompressionBombError as exc:
        raise ImageEditError(
            TOO_MANY_PIXELS,
            "Ukuran gambar terlalu besar untuk didekompresi.",
            413,
        ) from exc
    except Exception as exc:
        raise ImageEditError(
            IMAGE_UNREADABLE,
            "Berkas gambar rusak atau tidak bisa dibaca.",
            422,
        ) from exc

    width_px, height_px = img.size
    if width_px * height_px > MAX_PIXELS:
        raise ImageEditError(
            TOO_MANY_PIXELS,
            f"Ukuran gambar {width_px} × {height_px} ({width_px * height_px:,} piksel) melebihi batas {MAX_PIXELS:,} piksel.",
            413,
        )

    # URUTAN OPERASI:
    # 1) Perbaiki orientasi EXIF
    if norm_orientation:
        try:
            transposed = ImageOps.exif_transpose(img)
            if transposed is not None:
                img = transposed
        except Exception:
            pass

    # 2) Putar
    if norm_rotate == 90:
        img = img.transpose(Image.Transpose.ROTATE_270)
    elif norm_rotate == 180:
        img = img.transpose(Image.Transpose.ROTATE_180)
    elif norm_rotate == 270:
        img = img.transpose(Image.Transpose.ROTATE_90)

    # 3) Balik
    if norm_flip == "horizontal":
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    elif norm_flip == "vertikal":
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    # 4) Potong sesuai rasio & patokan
    img = crop_to_ratio(img, norm_ratio, norm_anchor)

    # 5) Tulis ke format tujuan
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

    except ImageEditError:
        raise
    except Exception as exc:
        raise ImageEditError(
            IMAGE_UNREADABLE,
            "Gagal memproses atau menyimpan hasil edit gambar.",
            422,
        ) from exc

    output_data = out_buffer.getvalue()

    return EditResult(
        data=output_data,
        input_format=input_format,
        output_format=effective_target,
        width=img.width,
        height=img.height,
        input_bytes=len(payload),
        output_bytes=len(output_data),
    )


def limits_payload() -> dict[str, Any]:
    """Payload batas dan opsi untuk Image Editor."""
    return {
        "max_files": MAX_FILES,
        "max_bytes": MAX_BYTES,
        "max_mb": MAX_BYTES // (1024 * 1024),
        "max_pixels": MAX_PIXELS,
        "inputs": ["png", "jpeg", "webp"],
        "accept": "image/png,image/jpeg,image/webp",
        "putar_options": [
            {"value": 0, "label": "Tidak diputar"},
            {"value": 90, "label": "90° ke kanan"},
            {"value": 180, "label": "180°"},
            {"value": 270, "label": "90° ke kiri"},
        ],
        "balik_options": [
            {"value": "tidak", "label": "Tidak"},
            {"value": "horizontal", "label": "Kiri-kanan"},
            {"value": "vertikal", "label": "Atas-bawah"},
        ],
        "rasio_options": [
            {"value": "bebas", "label": "Bebas"},
            {"value": "1:1", "label": "1:1"},
            {"value": "4:5", "label": "4:5"},
            {"value": "5:4", "label": "5:4"},
            {"value": "16:9", "label": "16:9"},
            {"value": "9:16", "label": "9:16"},
            {"value": "3:2", "label": "3:2"},
            {"value": "2:3", "label": "2:3"},
        ],
        "patokan_options": [
            {"value": "tengah", "label": "Tengah"},
            {"value": "atas", "label": "Atas"},
            {"value": "bawah", "label": "Bawah"},
            {"value": "kiri", "label": "Kiri"},
            {"value": "kanan", "label": "Kanan"},
        ],
        "orientasi_options": [
            {"value": "ya", "label": "Ya"},
            {"value": "tidak", "label": "Tidak"},
        ],
        "format_options": [
            {"value": "tetap", "label": "Sesuai berkas asal"},
            {"value": "jpeg", "label": "JPEG"},
            {"value": "png", "label": "PNG"},
            {"value": "webp", "label": "WebP"},
        ],
        "quality_min": QUALITY_MIN,
        "quality_max": QUALITY_MAX,
        "quality_default": QUALITY_DEFAULT,
        "quality_applies_to": ["jpeg", "webp"],
        "defaults": {
            "putar": 0,
            "balik": "tidak",
            "rasio": "bebas",
            "patokan": "tengah",
            "orientasi": "ya",
            "format": "tetap",
            "kualitas": QUALITY_DEFAULT,
        },
        "result_filename": "hasil-edit",
        "processed_on": "server",
        "note": (
            "Gambar dikirim ke server untuk diedit di memori, lalu dihapus "
            "setelah respons dikirim. Tidak ada berkas yang disimpan di disk."
        ),
    }
