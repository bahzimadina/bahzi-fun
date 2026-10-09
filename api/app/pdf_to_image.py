"""Logika konversi PDF ke gambar (PNG/JPG): fungsi murni, tanpa HTTP.

Semua validasi (format berkas, ukuran, batas halaman, DPI, kualitas JPEG,
dan batas piksel per halaman) diperiksa di sini sehingga bisa diuji langsung
dari Python tanpa server.

Prinsip:
* Semua pemrosesan di memori (io.BytesIO). Tidak ada berkas yang ditulis ke disk.
* Nama berkas pengunjung dan isinya tidak disimpan atau dicatat ke log.
* Privasi: log hanya mencatat angka (jumlah halaman, byte, format, dpi, durasi).
* Hanya PDF asli yang diterima (pemeriksaan magic bytes %PDF-).
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

import fitz
from PIL import Image

# --- Batas yang berlaku -----------------------------------------------------
MAX_FILE_BYTES = 25 * 1024 * 1024   # 25 MB, 1 berkas
MAX_PAGES = 50                      # Maksimum halaman PDF masukan
MIN_DPI = 72
MAX_DPI = 200
DEFAULT_DPI = 150

MIN_QUALITY = 30
MAX_QUALITY = 95
DEFAULT_QUALITY = 85                # Hanya untuk format JPG

MAX_PAGE_PIXELS = 40_000_000        # Maksimum piksel render per halaman
MAX_OUTPUT_BYTES = 80 * 1024 * 1024 # 80 MB total ukuran keluaran
FORMATS = ("png", "jpg")

# --- Konstanta format & magic bytes ------------------------------------------
PDF_MAGIC = b"%PDF-"
MAGIC_SCAN_WINDOW = 1024

# --- Kode error --------------------------------------------------------------
ERR_NO_FILE = "NO_FILE"
ERR_EMPTY_FILE = "EMPTY_FILE"
ERR_NOT_PDF = "NOT_PDF"
ERR_PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
ERR_TOO_MANY_PAGES = "TOO_MANY_PAGES"
ERR_PDF_UNREADABLE = "PDF_UNREADABLE"
ERR_PDF_ENCRYPTED = "PDF_ENCRYPTED"
ERR_PAGE_TOO_LARGE = "PAGE_TOO_LARGE"
ERR_OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"
ERR_UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
ERR_INVALID_DPI = "INVALID_DPI"
ERR_INVALID_QUALITY = "INVALID_QUALITY"
ERR_PDF_EMPTY = "PDF_EMPTY"


class PdfToImageError(Exception):
    """Kesalahan konversi PDF ke gambar yang dipetakan ke kode + status HTTP."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict:
        """Bentuk respons error yang dipakai API: {"error": {...}}."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class PdfToImageResult:
    """Hasil konversi PDF ke gambar (semua di memori)."""

    data: bytes
    output_kind: str  # "image" atau "zip"
    output_name: str
    mime_type: str
    format: str       # "png" atau "jpg"
    dpi: int
    quality: int | None
    page_count: int
    image_count: int
    size_bytes: int


def is_pdf_bytes(data: bytes) -> bool:
    """True bila byte diawali atau memuat header %PDF- dalam scan window."""
    if not data:
        return False
    if data.startswith(PDF_MAGIC):
        return True
    return PDF_MAGIC in data[:MAGIC_SCAN_WINDOW]


def check_size(n_bytes: int) -> None:
    """413 bila ukuran berkas melebihi batas 25 MB."""
    if n_bytes > MAX_FILE_BYTES:
        raise PdfToImageError(
            ERR_PAYLOAD_TOO_LARGE,
            f"Ukuran berkas melebihi batas {MAX_FILE_BYTES // (1024 * 1024)} MB.",
            413,
        )


def parse_format(fmt: str | None) -> str:
    """Validasi format keluaran: 'png' atau 'jpg'."""
    if fmt is None or not isinstance(fmt, str):
        raise PdfToImageError(
            ERR_UNSUPPORTED_FORMAT,
            "Format gambar tidak didukung. Pilih 'png' atau 'jpg'.",
            400,
        )
    clean = fmt.strip().lower()
    if clean == "jpeg":
        clean = "jpg"
    if clean not in FORMATS:
        raise PdfToImageError(
            ERR_UNSUPPORTED_FORMAT,
            f"Format '{fmt}' tidak didukung. Pilih 'png' atau 'jpg'.",
            400,
        )
    return clean


def parse_dpi(val: int | str | None) -> int:
    """Validasi nilai DPI rendering (72 sampai 200)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return DEFAULT_DPI
    if isinstance(val, bool):
        raise PdfToImageError(
            ERR_INVALID_DPI,
            f"Resolusi DPI harus berupa angka antara {MIN_DPI} sampai {MAX_DPI}.",
            400,
        )
    if isinstance(val, int):
        num = val
    elif isinstance(val, str):
        s = val.strip()
        if not (s.isdigit() or (s.startswith("+") and s[1:].isdigit())):
            raise PdfToImageError(
                ERR_INVALID_DPI,
                f"Resolusi DPI harus berupa angka antara {MIN_DPI} sampai {MAX_DPI}.",
                400,
            )
        num = int(s)
    else:
        raise PdfToImageError(
            ERR_INVALID_DPI,
            f"Resolusi DPI harus berupa angka antara {MIN_DPI} sampai {MAX_DPI}.",
            400,
        )

    if num < MIN_DPI or num > MAX_DPI:
        raise PdfToImageError(
            ERR_INVALID_DPI,
            f"Resolusi DPI harus berupa angka antara {MIN_DPI} sampai {MAX_DPI}.",
            400,
        )
    return num


def parse_quality(val: int | str | None) -> int:
    """Validasi nilai kualitas JPEG (30 sampai 95)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return DEFAULT_QUALITY
    if isinstance(val, bool):
        raise PdfToImageError(
            ERR_INVALID_QUALITY,
            f"Kualitas JPEG harus berupa angka antara {MIN_QUALITY} sampai {MAX_QUALITY}.",
            400,
        )
    if isinstance(val, int):
        num = val
    elif isinstance(val, str):
        s = val.strip()
        if not (s.isdigit() or (s.startswith("+") and s[1:].isdigit())):
            raise PdfToImageError(
                ERR_INVALID_QUALITY,
                f"Kualitas JPEG harus berupa angka antara {MIN_QUALITY} sampai {MAX_QUALITY}.",
                400,
            )
        num = int(s)
    else:
        raise PdfToImageError(
            ERR_INVALID_QUALITY,
            f"Kualitas JPEG harus berupa angka antara {MIN_QUALITY} sampai {MAX_QUALITY}.",
            400,
        )

    if num < MIN_QUALITY or num > MAX_QUALITY:
        raise PdfToImageError(
            ERR_INVALID_QUALITY,
            f"Kualitas JPEG harus berupa angka antara {MIN_QUALITY} sampai {MAX_QUALITY}.",
            400,
        )
    return num


def _open_doc(data: bytes) -> fitz.Document:
    """Buka PDF di memori; lempar error bila kosong, rusak, atau terkunci."""
    if data is None:
        raise PdfToImageError(ERR_NO_FILE, "Tidak ada berkas yang dikirim.", 400)
    if len(data) == 0:
        raise PdfToImageError(ERR_EMPTY_FILE, "Berkas kosong.", 400)
    check_size(len(data))
    if not is_pdf_bytes(data):
        raise PdfToImageError(ERR_NOT_PDF, "Berkas bukan dokumen PDF yang sah.", 400)

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PdfToImageError(
            ERR_PDF_UNREADABLE,
            "Berkas rusak atau tidak bisa dibaca sebagai PDF.",
            422,
        ) from exc

    if getattr(doc, "needs_pass", False):
        try:
            unlocked = doc.authenticate("")
        except Exception:
            unlocked = 0
        if not unlocked:
            doc.close()
            raise PdfToImageError(
                ERR_PDF_ENCRYPTED,
                "Berkas terproteksi kata sandi. Buka proteksinya sebelum diubah ke gambar.",
                422,
            )
    elif getattr(doc, "is_encrypted", False):
        try:
            unlocked = doc.authenticate("")
        except Exception:
            unlocked = 0
        if not unlocked:
            doc.close()
            raise PdfToImageError(
                ERR_PDF_ENCRYPTED,
                "Berkas terproteksi kata sandi. Buka proteksinya sebelum diubah ke gambar.",
                422,
            )

    try:
        count = len(doc)
    except Exception as exc:
        doc.close()
        raise PdfToImageError(
            ERR_PDF_UNREADABLE,
            "Berkas rusak: daftar halaman tidak bisa dibaca.",
            422,
        ) from exc

    if count <= 0:
        doc.close()
        raise PdfToImageError(
            ERR_PDF_EMPTY,
            "Dokumen PDF tidak memiliki halaman yang bisa dibaca.",
            400,
        )

    if count > MAX_PAGES:
        doc.close()
        raise PdfToImageError(
            ERR_TOO_MANY_PAGES,
            f"Jumlah halaman ({count}) melebihi batas {MAX_PAGES} halaman.",
            413,
        )

    return doc


def limits_payload() -> dict:
    """Payload batas yang dikembalikan endpoint limits."""
    return {
        "max_file_bytes": MAX_FILE_BYTES,
        "max_file_mb": MAX_FILE_BYTES // (1024 * 1024),
        "max_pages": MAX_PAGES,
        "min_dpi": MIN_DPI,
        "max_dpi": MAX_DPI,
        "default_dpi": DEFAULT_DPI,
        "min_quality": MIN_QUALITY,
        "max_quality": MAX_QUALITY,
        "default_quality": DEFAULT_QUALITY,
        "formats": list(FORMATS),
        "max_output_bytes": MAX_OUTPUT_BYTES,
        "max_output_mb": MAX_OUTPUT_BYTES // (1024 * 1024),
        "max_page_pixels": MAX_PAGE_PIXELS,
        "processed_on": "server",
        "note": (
            "Berkas dikirim ke server, diproses langsung di memori, lalu dibuang setelah "
            "respons dikirim. Tidak ada berkas yang disimpan di disk."
        ),
    }


def pdf_to_image(
    data: bytes,
    format: str = "png",
    dpi: int | str | None = None,
    quality: int | str | None = None,
) -> PdfToImageResult:
    """Ubah setiap halaman berkas PDF menjadi gambar PNG atau JPG.

    Parameter:
        data: Byte isi berkas PDF.
        format: 'png' atau 'jpg'.
        dpi: Resolusi rendering (72-200, bawaan 150).
        quality: Kualitas JPEG (30-95, bawaan 85, hanya berlaku bila format jpg).
    """
    clean_fmt = parse_format(format)
    clean_dpi = parse_dpi(dpi)
    clean_quality: int | None = None
    if clean_fmt == "jpg":
        clean_quality = parse_quality(quality)

    doc = _open_doc(data)
    try:
        page_count = len(doc)
        images: list[bytes] = []
        total_output_bytes = 0

        for page_idx in range(page_count):
            try:
                page = doc.load_page(page_idx)
                pix = page.get_pixmap(dpi=clean_dpi)
            except Exception as exc:
                raise PdfToImageError(
                    ERR_PDF_UNREADABLE,
                    f"Gagal merender halaman {page_idx + 1} dari PDF.",
                    422,
                ) from exc

            # Cek batas piksel satu halaman
            if pix.width * pix.height > MAX_PAGE_PIXELS:
                raise PdfToImageError(
                    ERR_PAGE_TOO_LARGE,
                    f"Ukuran halaman {page_idx + 1} ({pix.width}x{pix.height} piksel) melebihi batas "
                    f"{MAX_PAGE_PIXELS // 1_000_000} juta piksel. Coba turunkan resolusi DPI.",
                    422,
                )

            try:
                if clean_fmt == "png":
                    img_bytes = pix.tobytes("png")
                else:  # jpg
                    if pix.alpha:
                        pix = fitz.Pixmap(pix, 0)
                    if pix.n != 3:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=clean_quality, optimize=True)
                    img_bytes = buf.getvalue()
            except Exception as exc:
                raise PdfToImageError(
                    ERR_PDF_UNREADABLE,
                    f"Gagal memproses gambar untuk halaman {page_idx + 1}.",
                    422,
                ) from exc

            total_output_bytes += len(img_bytes)
            if total_output_bytes > MAX_OUTPUT_BYTES:
                raise PdfToImageError(
                    ERR_OUTPUT_TOO_LARGE,
                    f"Total ukuran gambar hasil ({total_output_bytes // (1024 * 1024)} MB) melebihi batas "
                    f"{MAX_OUTPUT_BYTES // (1024 * 1024)} MB. Coba turunkan resolusi DPI atau gunakan format JPG.",
                    413,
                )

            images.append(img_bytes)

        if page_count == 1:
            output_name = f"halaman-1.{clean_fmt}"
            mime_type = "image/png" if clean_fmt == "png" else "image/jpeg"
            result_data = images[0]
            output_kind = "image"
        else:
            pad_width = max(2, len(str(page_count)))
            output_name = "halaman-pdf.zip"
            mime_type = "application/zip"
            output_kind = "zip"
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                for idx, img_bytes in enumerate(images):
                    entry_name = f"halaman-{str(idx + 1).zfill(pad_width)}.{clean_fmt}"
                    zf.writestr(entry_name, img_bytes)
            result_data = zip_buf.getvalue()

        return PdfToImageResult(
            data=result_data,
            output_kind=output_kind,
            output_name=output_name,
            mime_type=mime_type,
            format=clean_fmt,
            dpi=clean_dpi,
            quality=clean_quality,
            page_count=page_count,
            image_count=page_count,
            size_bytes=len(result_data),
        )
    finally:
        doc.close()
