"""Logika tanda air pada foto (Watermark) — fungsi murni di memori, tanpa HTTP, mudah diuji.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak menulis ke disk.
Semua validasi (magic bytes, batas ukuran, dimensi, teks, mode, posisi,
ukuran teks, opasitas, warna, sudut rotasi, dan format keluaran) diproses di sini.

Prinsip:
* Semua pemrosesan di memori (io.BytesIO). Tidak ada berkas ditulis ke disk.
* Format masukan diperiksa dari magic bytes, bukan ekstensi atau MIME klien.
* Nama dan isi berkas/teks pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import math
import os
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

# --- Batas operasional ------------------------------------------------------
MAX_FILES = 1
MAX_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_PIXELS = 40_000_000
MAX_SIDE = 8000
CHUNK_SIZE = 1024 * 1024

TEXT_MIN_LEN = 1
TEXT_MAX_LEN = 60

SIZE_MIN = 2.0
SIZE_MAX = 30.0
DEFAULT_SIZE = 7.0

OPACITY_MIN = 5.0
OPACITY_MAX = 100.0
DEFAULT_OPACITY = 45.0

ANGLE_MIN = -90.0
ANGLE_MAX = 90.0

VALID_MODES = ("single", "tile")
VALID_POSITIONS = ("tl", "tc", "tr", "ml", "mc", "mr", "bl", "bc", "br")
VALID_COLORS = ("light", "dark")
VALID_FORMATS = ("jpeg", "png")

# --- Magic bytes penanda format masukan -------------------------------------
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
RIFF_MAGIC = b"RIFF"
WEBP_MAGIC = b"WEBP"

# Format gambar umum lainnya untuk membedakan bukan_gambar vs format_tidak_didukung
GIF_MAGICS = (b"GIF87a", b"GIF89a")
BMP_MAGIC = b"BM"
TIFF_MAGICS = (b"II*\x00", b"MM\x00*")

# --- Kode error stabil ------------------------------------------------------
ERR_BERKAS_KOSONG = "berkas_kosong"
ERR_BUKAN_GAMBAR = "bukan_gambar"
ERR_FORMAT_TIDAK_DIDUKUNG = "format_tidak_didukung"
ERR_TERLALU_BESAR = "terlalu_besar"
ERR_DIMENSI_TERLALU_BESAR = "dimensi_terlalu_besar"
ERR_TEKS_KOSONG = "teks_kosong"
ERR_TEKS_TERLALU_PANJANG = "teks_terlalu_panjang"
ERR_PARAMETER_TIDAK_VALID = "parameter_tidak_valid"
ERR_GAGAL_PROSES = "gagal_proses"


class WatermarkError(Exception):
    """Kesalahan pemrosesan tanda air dengan kode galat stabil dan status HTTP."""

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
class WatermarkResult:
    """Hasil pemrosesan tanda air di memori."""

    data: bytes
    format: str
    width: int
    height: int
    output_bytes: int
    filename: str


def detect_watermark_format(data: bytes) -> str | None:
    """Deteksi format gambar yang didukung dari magic bytes (JPEG, PNG, WebP)."""
    if not data or len(data) < 3:
        return None
    if data.startswith(JPEG_MAGIC):
        return "jpeg"
    if data.startswith(PNG_MAGIC):
        return "png"
    if len(data) >= 12 and data.startswith(RIFF_MAGIC) and data[8:12] == WEBP_MAGIC:
        return "webp"
    return None


def is_unsupported_image_magic(data: bytes) -> bool:
    """True bila data memiliki penanda berkas gambar lain yang tidak didukung (mis. GIF, BMP, TIFF)."""
    if not data or len(data) < 2:
        return False
    if data.startswith(BMP_MAGIC):
        return True
    if len(data) >= 6 and (data.startswith(GIF_MAGICS[0]) or data.startswith(GIF_MAGICS[1])):
        return True
    if len(data) >= 4 and (data.startswith(TIFF_MAGICS[0]) or data.startswith(TIFF_MAGICS[1])):
        return True
    return False


def watermark_limits_payload() -> dict[str, Any]:
    """Informasi batas operasional tanda air untuk endpoint /api/watermark/limits."""
    return {
        "max_bytes": MAX_BYTES,
        "max_side": MAX_SIDE,
        "max_pixels": MAX_PIXELS,
        "text_max": TEXT_MAX_LEN,
        "formats": ["jpeg", "png", "webp"],
        "modes": list(VALID_MODES),
        "positions": list(VALID_POSITIONS),
        "size": {"min": int(SIZE_MIN), "max": int(SIZE_MAX)},
        "opacity": {"min": int(OPACITY_MIN), "max": int(OPACITY_MAX)},
        "angle": {"min": int(ANGLE_MIN), "max": int(ANGLE_MAX)},
    }


def normalize_text(text: Any) -> str:
    """Validasi dan normalisasi teks tanda air (1..60 karakter setelah trim)."""
    if text is None:
        raise WatermarkError(ERR_TEKS_KOSONG, "Teks tanda air wajib diisi.", 422)
    val = str(text).strip()
    if not val:
        raise WatermarkError(ERR_TEKS_KOSONG, "Teks tanda air tidak boleh kosong.", 422)
    if len(val) > TEXT_MAX_LEN:
        raise WatermarkError(
            ERR_TEKS_TERLALU_PANJANG,
            f"Teks tanda air terlalu panjang (maksimal {TEXT_MAX_LEN} karakter).",
            422,
        )
    return val


def normalize_mode(mode: Any) -> str:
    """Normalisasi mode tanda air ('single' atau 'tile'). Default 'single'."""
    if mode is None:
        return "single"
    val = str(mode).strip().lower()
    if val not in VALID_MODES:
        raise WatermarkError(
            ERR_PARAMETER_TIDAK_VALID,
            "Mode tanda air tidak valid. Pilihan yang tersedia: single, tile.",
            422,
        )
    return val


def normalize_position(position: Any) -> str:
    """Normalisasi posisi untuk mode single (tl, tc, tr, ml, mc, mr, bl, bc, br). Default 'br'."""
    if position is None:
        return "br"
    val = str(position).strip().lower()
    if val not in VALID_POSITIONS:
        raise WatermarkError(
            ERR_PARAMETER_TIDAK_VALID,
            f"Posisi tanda air tidak valid. Pilihan: {', '.join(VALID_POSITIONS)}.",
            422,
        )
    return val


def normalize_size(size: Any) -> float:
    """Normalisasi ukuran teks dalam persen lebar gambar (2..30). Default 7."""
    if size is None:
        return DEFAULT_SIZE
    try:
        val = float(size)
    except (ValueError, TypeError):
        raise WatermarkError(
            ERR_PARAMETER_TIDAK_VALID,
            f"Ukuran teks harus berupa angka antara {int(SIZE_MIN)} sampai {int(SIZE_MAX)}%.",
            422,
        )
    if val < SIZE_MIN or val > SIZE_MAX:
        raise WatermarkError(
            ERR_PARAMETER_TIDAK_VALID,
            f"Ukuran teks ({val:g}%) di luar rentang {int(SIZE_MIN)} sampai {int(SIZE_MAX)}%.",
            422,
        )
    return val


def normalize_opacity(opacity: Any) -> int:
    """Normalisasi opasitas teks (5..100). Default 45."""
    if opacity is None:
        return int(DEFAULT_OPACITY)
    try:
        val = float(opacity)
    except (ValueError, TypeError):
        raise WatermarkError(
            ERR_PARAMETER_TIDAK_VALID,
            f"Opasitas harus berupa angka antara {int(OPACITY_MIN)} sampai {int(OPACITY_MAX)}%.",
            422,
        )
    if val < OPACITY_MIN or val > OPACITY_MAX:
        raise WatermarkError(
            ERR_PARAMETER_TIDAK_VALID,
            f"Opasitas ({val:g}%) di luar rentang {int(OPACITY_MIN)} sampai {int(OPACITY_MAX)}%.",
            422,
        )
    return int(round(val))


def normalize_color(color: Any) -> str:
    """Normalisasi warna teks ('light' atau 'dark'). Default 'light'."""
    if color is None:
        return "light"
    val = str(color).strip().lower()
    if val not in VALID_COLORS:
        raise WatermarkError(
            ERR_PARAMETER_TIDAK_VALID,
            "Warna tanda air tidak valid. Pilihan: light (terang) atau dark (gelap).",
            422,
        )
    return val


def normalize_angle(angle: Any, mode: str) -> float:
    """Normalisasi sudut rotasi (-90..90). Default 0 untuk single, 30 untuk tile bila kosong."""
    if angle is None or (isinstance(angle, str) and angle.strip() == ""):
        return 30.0 if mode == "tile" else 0.0
    try:
        val = float(angle)
    except (ValueError, TypeError):
        raise WatermarkError(
            ERR_PARAMETER_TIDAK_VALID,
            f"Sudut rotasi harus berupa angka antara {int(ANGLE_MIN)} sampai {int(ANGLE_MAX)} derajat.",
            422,
        )
    if val < ANGLE_MIN or val > ANGLE_MAX:
        raise WatermarkError(
            ERR_PARAMETER_TIDAK_VALID,
            f"Sudut rotasi ({val:g}°) di luar rentang {int(ANGLE_MIN)} sampai {int(ANGLE_MAX)} derajat.",
            422,
        )
    return val


def normalize_format(fmt: Any) -> str:
    """Normalisasi format hasil ('jpeg' atau 'png'). Default 'jpeg'."""
    if fmt is None:
        return "jpeg"
    val = str(fmt).strip().lower()
    if val == "jpg":
        val = "jpeg"
    if val not in VALID_FORMATS:
        raise WatermarkError(
            ERR_PARAMETER_TIDAK_VALID,
            "Format keluaran tidak valid. Pilihan: jpeg atau png.",
            422,
        )
    return val


def _angka(n: int) -> str:
    """Format bilangan dengan pemisah ribuan gaya Indonesia (8.000)."""
    return f"{n:,}".replace(",", ".")


def _get_font(size_px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Muat font TTF sistem yang tersedia, atau fallback ke font default Pillow bawaan."""
    candidate_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for p in candidate_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size=size_px)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size_px)
    except TypeError:
        return ImageFont.load_default()


def apply_watermark(
    payload: bytes,
    text: Any,
    mode: Any = "single",
    position: Any = "br",
    size: Any = DEFAULT_SIZE,
    opacity: Any = DEFAULT_OPACITY,
    color: Any = "light",
    angle: Any = None,
    format: Any = "jpeg",
) -> WatermarkResult:
    """Beri tanda air pada foto di memori."""
    if not payload:
        raise WatermarkError(ERR_BERKAS_KOSONG, "Berkas gambar kosong (0 byte).", 400)

    if len(payload) > MAX_BYTES:
        raise WatermarkError(
            ERR_TERLALU_BESAR,
            f"Ukuran berkas melebihi batas {MAX_BYTES // (1024 * 1024)} MB. Perkecil foto terlebih dahulu.",
            413,
        )

    detected = detect_watermark_format(payload)
    if not detected:
        if is_unsupported_image_magic(payload):
            raise WatermarkError(
                ERR_FORMAT_TIDAK_DIDUKUNG,
                "Format gambar tidak didukung. Gunakan JPG, PNG, atau WebP.",
                400,
            )
        raise WatermarkError(
            ERR_BUKAN_GAMBAR,
            "Berkas bukan gambar yang didukung. Hanya menerima JPG, PNG, atau WebP.",
            400,
        )

    # Validasi parameter
    norm_text = normalize_text(text)
    norm_mode = normalize_mode(mode)
    norm_position = normalize_position(position)
    norm_size = normalize_size(size)
    norm_opacity = normalize_opacity(opacity)
    norm_color = normalize_color(color)
    norm_angle = normalize_angle(angle, norm_mode)
    norm_format = normalize_format(format)

    # 1) Buka gambar & periksa dimensi sebelum decode penuh
    try:
        img = Image.open(io.BytesIO(payload))
    except Exception as exc:
        raise WatermarkError(
            ERR_BUKAN_GAMBAR,
            "Berkas gambar rusak atau tidak bisa dibaca.",
            400,
        ) from exc

    raw_w, raw_h = img.size
    if raw_w > MAX_SIDE or raw_h > MAX_SIDE:
        raise WatermarkError(
            ERR_DIMENSI_TERLALU_BESAR,
            f"Sisi gambar ({raw_w} × {raw_h}) melebihi batas {_angka(MAX_SIDE)} piksel.",
            413,
        )

    if raw_w * raw_h > MAX_PIXELS:
        raise WatermarkError(
            ERR_DIMENSI_TERLALU_BESAR,
            f"Ukuran gambar {raw_w} × {raw_h} ({_angka(raw_w * raw_h)} piksel) melebihi batas {_angka(MAX_PIXELS)} piksel.",
            413,
        )

    # 2) Decode penuh
    try:
        img.load()
    except Image.DecompressionBombError as exc:
        raise WatermarkError(
            ERR_DIMENSI_TERLALU_BESAR,
            "Ukuran gambar terlalu besar untuk diproses.",
            413,
        ) from exc
    except Exception as exc:
        raise WatermarkError(
            ERR_BUKAN_GAMBAR,
            "Berkas gambar rusak saat diproses.",
            400,
        ) from exc

    # Orientasi EXIF disesuaikan secara fisik
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    img_w, img_h = img.size
    original_mode = img.mode

    # Hitung ukuran font, stroke, dan warna
    font_size_px = max(10, int(round(img_w * (norm_size / 100.0))))
    stroke_width = max(1, int(round(font_size_px / 18.0)))
    alpha = max(0, min(255, int(round(255.0 * (norm_opacity / 100.0)))))

    if norm_color == "light":
        fill_color = (255, 255, 255, alpha)
        stroke_color = (0, 0, 0, alpha)
    else:
        fill_color = (0, 0, 0, alpha)
        stroke_color = (255, 255, 255, alpha)

    font = _get_font(font_size_px)

    # Ukur dimensi teks
    dummy = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    d_measure = ImageDraw.Draw(dummy)
    bbox = d_measure.textbbox((0, 0), norm_text, font=font, stroke_width=stroke_width)
    left, top, right, bottom = bbox
    text_w = max(1, right - left)
    text_h = max(1, bottom - top)

    # Cetak teks ke layer transparan mandiri dengan padding agar stroke tidak terpotong
    pad = stroke_width + 4
    stamp_w = text_w + pad * 2
    stamp_h = text_h + pad * 2
    stamp = Image.new("RGBA", (stamp_w, stamp_h), (0, 0, 0, 0))
    d_stamp = ImageDraw.Draw(stamp)
    d_stamp.text(
        (pad - left, pad - top),
        norm_text,
        font=font,
        fill=fill_color,
        stroke_width=stroke_width,
        stroke_fill=stroke_color,
    )

    # Putar teks jika angle != 0
    if norm_angle != 0.0:
        rot_stamp = stamp.rotate(norm_angle, resample=Image.Resampling.BICUBIC, expand=True)
    else:
        rot_stamp = stamp

    rot_w, rot_h = rot_stamp.size

    # Layer overlay seukuran gambar asli
    overlay = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))

    # Kecilkan stamp secara proporsional bila tidak muat dalam batas gambar (margin min 4 px, 3% lebar gambar)
    margin = max(4, int(round(img_w * 0.03)))
    batas_w = max(1, img_w - 2 * margin)
    batas_h = max(1, img_h - 2 * margin)
    faktor = min(1.0, batas_w / max(1, rot_w), batas_h / max(1, rot_h))
    if faktor < 1.0:
        new_w = max(1, int(rot_w * faktor))
        new_h = max(1, int(rot_h * faktor))
        rot_stamp = rot_stamp.resize((new_w, new_h), Image.Resampling.LANCZOS)
        rot_w, rot_h = rot_stamp.size

    if norm_mode == "single":
        # Posisi horizontal
        if norm_position in ("tl", "ml", "bl"):
            x = margin
        elif norm_position in ("tc", "mc", "bc"):
            x = (img_w - rot_w) // 2
        else:  # tr, mr, br
            x = img_w - margin - rot_w

        # Posisi vertikal
        if norm_position in ("tl", "tc", "tr"):
            y = margin
        elif norm_position in ("ml", "mc", "mr"):
            y = (img_h - rot_h) // 2
        else:  # bl, bc, br
            y = img_h - margin - rot_h

        # Klip dengan max/min sebagai jaring pengaman agar posisi selalu >= margin dan x+rot_w <= img_w-margin
        max_x = max(margin, img_w - margin - rot_w)
        x = max(margin, min(x, max_x))
        max_y = max(margin, img_h - margin - rot_h)
        y = max(margin, min(y, max_y))

        overlay.paste(rot_stamp, (x, y), rot_stamp)

    else:  # tile
        gap_x = max(20, int(round(rot_w * 0.25)))
        gap_y = max(20, int(round(rot_h * 0.4)))
        step_x = max(1, rot_w + gap_x)
        step_y = max(1, rot_h + gap_y)

        y = -rot_h
        row = 0
        while y < img_h + rot_h:
            x_offset = (step_x // 2) if (row % 2 == 1) else 0
            x = -rot_w + x_offset
            while x < img_w + rot_w:
                overlay.paste(rot_stamp, (x, y), rot_stamp)
                x += step_x
            y += step_y
            row += 1

    # Gabungkan overlay dengan gambar dasar
    if img.mode != "RGBA":
        base_rgba = img.convert("RGBA")
    else:
        base_rgba = img

    result_rgba = Image.alpha_composite(base_rgba, overlay)

    # Simpan hasil sesuai format yang diminta tanpa metadata EXIF
    buf = io.BytesIO()
    if norm_format == "jpeg":
        # JPEG tidak mendukung transparansi, lekatkan ke latar putih jika ada saluran alfa
        rgb_img = Image.new("RGB", result_rgba.size, (255, 255, 255))
        rgb_img.paste(result_rgba, mask=result_rgba.split()[3])
        rgb_img.save(buf, format="JPEG", quality=90, optimize=True)
        out_filename = "tanda-air.jpg"
    else:  # png
        if original_mode == "RGB":
            out_png = result_rgba.convert("RGB")
        else:
            out_png = result_rgba
        out_png.save(buf, format="PNG", optimize=True)
        out_filename = "tanda-air.png"

    output_bytes = buf.getvalue()

    return WatermarkResult(
        data=output_bytes,
        format=norm_format,
        width=img_w,
        height=img_h,
        output_bytes=len(output_bytes),
        filename=out_filename,
    )
