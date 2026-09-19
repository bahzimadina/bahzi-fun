"""Logika konversi format gambar — fungsi murni, tanpa HTTP, mudah diuji.

Modul ini tidak bergantung pada FastAPI/HTTP. Semua validasi (magic bytes,
dimensi, ukuran byte, format target, kualitas) diproses di sini.

Prinsip:
* Semua pemrosesan di memori (io.BytesIO). Tidak ada berkas ditulis ke disk.
* Format masukan diperiksa dari magic bytes, bukan ekstensi atau MIME klien.
* Nama dan isi berkas pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

import concurrent.futures
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from cairosvg.surface import PNGSurface, Tree, node_format
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

# --- Masukan SVG --------------------------------------------------------------
SVG_MIN_WIDTH = 16
SVG_MAX_WIDTH = 4000
SVG_DEFAULT_WIDTH = 1024
SVG_MAX_SIDE = 8000
SVG_RENDER_TIMEOUT = 20  # batas waktu render SVG dalam detik
SVG_NATIVE_SIZE_CAP = 20_000

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
INVALID_SVG = "INVALID_SVG"
UNSAFE_SVG = "UNSAFE_SVG"
SVG_RENDER_FAILED = "SVG_RENDER_FAILED"
INVALID_WIDTH = "INVALID_WIDTH"


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
    scaled_down: bool = False


_UNSAFE_SVG_MARKERS = (
    "<!doctype",
    "<!entity",
    "<script",
    "javascript:",
    "onload=",
    "onerror=",
    "<foreignobject",
)


def _looks_like_svg(data: bytes) -> bool:
    """Deteksi SVG dari isi berkas: buang BOM/spasi awal, cek `<?xml`/`<svg`, pastikan ada `<svg`."""
    if not data:
        return False
    sample = data[3:] if data.startswith(b"\xef\xbb\xbf") else data
    text = sample.decode("utf-8", errors="ignore")
    stripped = text.lstrip()
    lower_head = stripped[:512].lower()
    if not (lower_head.startswith("<?xml") or lower_head.startswith("<svg")):
        return False
    return "<svg" in text.lower()


def detect_format(data: bytes) -> str | None:
    """Deteksi format gambar dari magic bytes (PNG, JPEG, WebP) atau isi (SVG)."""
    if not data or len(data) < 3:
        return None
    if data.startswith(JPEG_MAGIC):
        return "jpeg"
    if data.startswith(PNG_MAGIC):
        return "png"
    if len(data) >= 12 and data.startswith(RIFF_MAGIC) and data[8:12] == WEBP_MAGIC:
        return "webp"
    if _looks_like_svg(data):
        return "svg"
    return None


def _check_svg_safety(payload: bytes) -> None:
    """Tolak SVG yang mengandung elemen berbahaya (DOCTYPE/entity/script/handler event)."""
    text_lower = payload.decode("utf-8", errors="ignore").lower()
    if any(marker in text_lower for marker in _UNSAFE_SVG_MARKERS):
        raise ImageConvertError(
            UNSAFE_SVG,
            "Berkas SVG ini berisi elemen yang tidak kami izinkan untuk diproses.",
            400,
        )


class _SvgExternalResourceBlocked(Exception):
    """Dilempar oleh url_fetcher SVG saat ada percobaan mengambil sumber daya eksternal."""


def _blocked_svg_url_fetcher(url: str, resource_type: str | None = None, **_kwargs: Any) -> bytes:
    """url_fetcher yang SELALU gagal — SVG tidak boleh mengambil apa pun dari luar."""
    raise _SvgExternalResourceBlocked(f"pengambilan sumber daya SVG diblokir: {resource_type}")


class _SvgDimensionSurface(PNGSurface):
    """Surface pembantu untuk mengukur dimensi intrinsik SVG tanpa alokasi raster penuh."""

    def __init__(self, tree: Tree, dpi: float = 96.0) -> None:
        self.dpi = dpi
        self.font_size = 12.0
        self.context_width: float | None = None
        self.context_height: float | None = None
        self.tree = tree
        self.width: float = 0.0
        self.height: float = 0.0
        self.viewbox: tuple[float, float, float, float] | None = None
        self.calculate_size()

    def calculate_size(self) -> tuple[float, float]:
        """Hitung ukuran intrinsik SVG dari root node tanpa rendering."""
        w, h, vb = node_format(self, self.tree)
        self.viewbox = vb
        self.width = float(w or 0.0)
        self.height = float(h or 0.0)
        return self.width, self.height


def _get_svg_intrinsic_dimensions(payload: bytes) -> tuple[float, float]:
    """Tentukan dimensi intrinsik SVG (width, height) lewat PNGSurface tanpa render piksel penuh."""
    try:
        tree = Tree(bytestring=payload, url_fetcher=_blocked_svg_url_fetcher)
    except _SvgExternalResourceBlocked as exc:
        raise ImageConvertError(
            UNSAFE_SVG,
            "Berkas SVG ini berisi elemen yang tidak kami izinkan untuk diproses.",
            400,
        ) from exc
    except ET.ParseError as exc:
        raise ImageConvertError(
            INVALID_SVG,
            "Berkas SVG rusak atau tidak bisa dibaca.",
            400,
        ) from exc
    except ImageConvertError:
        raise
    except Exception as exc:
        raise ImageConvertError(
            INVALID_SVG,
            "Berkas SVG rusak atau tidak bisa dibaca.",
            400,
        ) from exc

    try:
        surface = _SvgDimensionSurface(tree)
        w, h = surface.calculate_size()
    except Exception as exc:
        raise ImageConvertError(
            INVALID_SVG,
            "Gagal membaca dimensi SVG.",
            400,
        ) from exc

    has_explicit_w = "width" in tree
    has_explicit_h = "height" in tree
    vb = surface.viewbox

    if has_explicit_w and not has_explicit_h and vb and vb[2] > 0 and vb[3] > 0:
        h = w * (vb[3] / vb[2])
    elif has_explicit_h and not has_explicit_w and vb and vb[2] > 0 and vb[3] > 0:
        w = h * (vb[2] / vb[3])
    elif not has_explicit_w and not has_explicit_h and vb and vb[2] > 0 and vb[3] > 0:
        w, h = vb[2], vb[3]

    if w <= 0 and h <= 0:
        w, h = float(SVG_DEFAULT_WIDTH), float(SVG_DEFAULT_WIDTH)
    elif w <= 0:
        w = h if h > 0 else float(SVG_DEFAULT_WIDTH)
    elif h <= 0:
        h = w if w > 0 else float(SVG_DEFAULT_WIDTH)

    return max(1.0, float(w)), max(1.0, float(h))


def _render_svg_to_png_bytes(
    payload: bytes,
    output_width: int | None = None,
    output_height: int | None = None,
) -> bytes:
    """Render SVG ke PNG di memori lewat cairosvg, tanpa akses jaringan/berkas.

    Dibatasi batas waktu via ThreadPoolExecutor agar render patologis tidak memblokir server.
    """
    def _do_render() -> bytes:
        return PNGSurface.convert(
            bytestring=payload,
            output_width=output_width,
            output_height=output_height,
            url_fetcher=_blocked_svg_url_fetcher,
        )

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(_do_render)
        return future.result(timeout=SVG_RENDER_TIMEOUT)
    except TimeoutError as exc:
        raise ImageConvertError(
            SVG_RENDER_FAILED,
            "Proses render SVG melebihi batas waktu yang diizinkan.",
            422,
        ) from exc
    except _SvgExternalResourceBlocked as exc:
        raise ImageConvertError(
            UNSAFE_SVG,
            "Berkas SVG ini berisi elemen yang tidak kami izinkan untuk diproses.",
            400,
        ) from exc
    except ET.ParseError as exc:
        raise ImageConvertError(
            INVALID_SVG,
            "Berkas SVG rusak atau tidak bisa dibaca.",
            400,
        ) from exc
    except ImageConvertError:
        raise
    except Exception as exc:
        raise ImageConvertError(
            SVG_RENDER_FAILED,
            "Gagal merender berkas SVG ini.",
            422,
        ) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


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


def normalize_width(value: int | str | None) -> int | None:
    """Normalisasi field 'width' (lebar render SVG, px). None => pakai ukuran asli SVG."""
    if value is None:
        return None
    if isinstance(value, str):
        val_str = value.strip()
        if not val_str:
            return None
        try:
            val_int = int(val_str)
        except ValueError:
            raise ImageConvertError(
                INVALID_WIDTH,
                f"Lebar harus berupa angka bulat antara {SVG_MIN_WIDTH} dan {SVG_MAX_WIDTH} piksel.",
                400,
            )
    elif isinstance(value, int):
        val_int = value
    else:
        try:
            val_int = int(value)
        except (ValueError, TypeError):
            raise ImageConvertError(
                INVALID_WIDTH,
                f"Lebar harus berupa angka bulat antara {SVG_MIN_WIDTH} dan {SVG_MAX_WIDTH} piksel.",
                400,
            )

    if val_int < SVG_MIN_WIDTH or val_int > SVG_MAX_WIDTH:
        raise ImageConvertError(
            INVALID_WIDTH,
            f"Lebar {val_int} px di luar rentang {SVG_MIN_WIDTH} sampai {SVG_MAX_WIDTH} piksel.",
            400,
        )
    return val_int


def convert_image(
    payload: bytes,
    target: str = "jpeg",
    quality: int | str | None = None,
    width: int | str | None = None,
) -> ConvertResult:
    """Konversi gambar di memori ke format target. `width` hanya berlaku untuk masukan SVG."""
    if not payload:
        raise ImageConvertError(EMPTY_FILE, "Berkas gambar kosong (0 byte).", 400)

    check_total_size(len(payload))

    input_format = detect_format(payload)
    if not input_format:
        raise ImageConvertError(
            NOT_IMAGE,
            "Berkas bukan gambar yang didukung. Hanya menerima PNG, JPEG, WebP, atau SVG.",
            400,
        )

    norm_target = normalize_target(target)
    norm_quality = normalize_quality(quality)
    scaled_down = False

    if input_format == "svg":
        _check_svg_safety(payload)
        norm_width = normalize_width(width)
        intrinsic_w, intrinsic_h = _get_svg_intrinsic_dimensions(payload)

        # Tentukan target render awal:
        # a. kalau pengguna mengirim width -> pakai itu (sudah divalidasi 16-4000)
        # b. kalau tidak:
        #    - bila lebar intrinsik < SVG_DEFAULT_WIDTH (1024) -> gunakan SVG_DEFAULT_WIDTH
        #      sebagai batas minimum (tinggi proporsional mengikuti rasio intrinsik)
        #    - bila lebar intrinsik >= SVG_DEFAULT_WIDTH -> pakai ukuran aslinya
        if norm_width is not None:
            initial_w = float(norm_width)
            initial_h = max(1.0, initial_w * (intrinsic_h / intrinsic_w))
        elif intrinsic_w < SVG_DEFAULT_WIDTH:
            initial_w = float(SVG_DEFAULT_WIDTH)
            initial_h = max(1.0, initial_w * (intrinsic_h / intrinsic_w))
        else:
            initial_w = intrinsic_w
            initial_h = intrinsic_h

        # c. perkecil proporsional bila perlu agar memenuhi DUA batas:
        #    total piksel <= MAX_PIXELS dan sisi terpanjang <= SVG_MAX_SIDE
        scale = 1.0
        max_side = max(initial_w, initial_h)
        if max_side > SVG_MAX_SIDE:
            scale = min(scale, SVG_MAX_SIDE / max_side)

        if (initial_w * scale) * (initial_h * scale) > MAX_PIXELS:
            pixel_scale = (MAX_PIXELS / (initial_w * initial_h)) ** 0.5
            scale = min(scale, pixel_scale)

        if scale < 1.0:
            target_w = max(1, int(initial_w * scale))
            target_h = max(1, int(initial_h * scale))
            if target_w > SVG_MAX_SIDE:
                target_w = SVG_MAX_SIDE
            if target_h > SVG_MAX_SIDE:
                target_h = SVG_MAX_SIDE
            while target_w * target_h > MAX_PIXELS:
                if target_w >= target_h:
                    target_w -= 1
                else:
                    target_h -= 1
            scaled_down = True
        else:
            target_w = max(1, int(round(initial_w)))
            target_h = max(1, int(round(initial_h)))
            scaled_down = False

        png_bytes = _render_svg_to_png_bytes(payload, target_w, target_h)

        try:
            img = Image.open(io.BytesIO(png_bytes))
            img.load()
        except Exception as exc:
            raise ImageConvertError(
                SVG_RENDER_FAILED,
                "Gagal merender berkas SVG ini.",
                422,
            ) from exc

    else:
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

        width_px, height_px = img.size
        if width_px * height_px > MAX_PIXELS:
            raise ImageConvertError(
                IMAGE_TOO_LARGE,
                f"Ukuran gambar {width_px} × {height_px} ({width_px * height_px:,} piksel) melebihi batas {MAX_PIXELS:,} piksel.",
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
        scaled_down=scaled_down,
    )
