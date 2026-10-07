"""Logika kompresi PDF: fungsi murni, tanpa HTTP, mudah diuji.

Modul ini tidak bergantung pada FastAPI/uvicorn/HTTP. Semua validasi
(format berkas, ukuran, batas halaman, mode, DPI, dan kualitas JPEG)
diperiksa di sini sehingga bisa diuji langsung dari Python tanpa server.

Prinsip:
* Semua pemrosesan di memori (io.BytesIO). Tidak ada berkas yang ditulis ke disk.
* Nama berkas pengunjung tidak disimpan atau dicatat ke log.
* Hanya PDF asli yang diterima (pemeriksaan magic bytes %PDF-).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import fitz

# --- Batas yang berlaku -----------------------------------------------------
MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB, satu berkas
MAX_PAGES = 300                    # Maksimum halaman PDF masukan

MIN_DPI = 72
MAX_DPI = 200
DEFAULT_DPI = 110

MIN_QUALITY = 30
MAX_QUALITY = 95
DEFAULT_QUALITY = 60

# --- Konstanta format & mode ------------------------------------------------
PDF_MAGIC = b"%PDF-"
MAGIC_SCAN_WINDOW = 1024

MODES = ("ringan", "sedang", "kuat")

# --- Kode error --------------------------------------------------------------
ERR_NO_FILE = "NO_FILE"
ERR_EMPTY_FILE = "EMPTY_FILE"
ERR_NOT_PDF = "NOT_PDF"
ERR_PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
ERR_TOO_MANY_PAGES = "TOO_MANY_PAGES"
ERR_PDF_UNREADABLE = "PDF_UNREADABLE"
ERR_PDF_ENCRYPTED = "PDF_ENCRYPTED"
ERR_UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
ERR_INVALID_DPI = "INVALID_DPI"
ERR_INVALID_QUALITY = "INVALID_QUALITY"


class PdfCompressError(Exception):
    """Kesalahan kompresi PDF yang sudah dipetakan ke kode + status HTTP."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict:
        """Bentuk respons error yang dipakai API: {"error": {...}}."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class PdfInfo:
    """Informasi metadata PDF."""

    page_count: int
    size_bytes: int

    def to_dict(self) -> dict:
        return {
            "page_count": self.page_count,
            "size_bytes": self.size_bytes,
            "max_pages": MAX_PAGES,
        }


@dataclass(frozen=True)
class CompressResult:
    """Hasil kompresi PDF (semua di memori)."""

    data: bytes
    size_before: int
    size_after: int
    page_count: int
    mode: str
    keep_text: bool
    used_original: bool
    notes: list[str]


# --- Pemeriksaan format & batas ----------------------------------------------
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
        raise PdfCompressError(
            ERR_PAYLOAD_TOO_LARGE,
            "Ukuran berkas melebihi batas 25 MB.",
            413,
        )


def parse_dpi(val: int | str | None) -> int:
    """Validasi nilai DPI untuk rendering mode kuat (72 sampai 200)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return DEFAULT_DPI
    if isinstance(val, bool):
        raise PdfCompressError(
            ERR_INVALID_DPI,
            f"DPI harus berupa angka antara {MIN_DPI} sampai {MAX_DPI}.",
            400,
        )
    if isinstance(val, int):
        num = val
    elif isinstance(val, str):
        s = val.strip()
        if not (s.isdigit() or (s.startswith("+") and s[1:].isdigit())):
            raise PdfCompressError(
                ERR_INVALID_DPI,
                f"DPI harus berupa angka antara {MIN_DPI} sampai {MAX_DPI}.",
                400,
            )
        num = int(s)
    else:
        raise PdfCompressError(
            ERR_INVALID_DPI,
            f"DPI harus berupa angka antara {MIN_DPI} sampai {MAX_DPI}.",
            400,
        )

    if num < MIN_DPI or num > MAX_DPI:
        raise PdfCompressError(
            ERR_INVALID_DPI,
            f"DPI harus berupa angka antara {MIN_DPI} sampai {MAX_DPI}.",
            400,
        )
    return num


def parse_quality(val: int | str | None) -> int:
    """Validasi nilai kualitas JPEG untuk mode kuat (30 sampai 95)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return DEFAULT_QUALITY
    if isinstance(val, bool):
        raise PdfCompressError(
            ERR_INVALID_QUALITY,
            f"Kualitas JPEG harus berupa angka antara {MIN_QUALITY} sampai {MAX_QUALITY}.",
            400,
        )
    if isinstance(val, int):
        num = val
    elif isinstance(val, str):
        s = val.strip()
        if not (s.isdigit() or (s.startswith("+") and s[1:].isdigit())):
            raise PdfCompressError(
                ERR_INVALID_QUALITY,
                f"Kualitas JPEG harus berupa angka antara {MIN_QUALITY} sampai {MAX_QUALITY}.",
                400,
            )
        num = int(s)
    else:
        raise PdfCompressError(
            ERR_INVALID_QUALITY,
            f"Kualitas JPEG harus berupa angka antara {MIN_QUALITY} sampai {MAX_QUALITY}.",
            400,
        )

    if num < MIN_QUALITY or num > MAX_QUALITY:
        raise PdfCompressError(
            ERR_INVALID_QUALITY,
            f"Kualitas JPEG harus berupa angka antara {MIN_QUALITY} sampai {MAX_QUALITY}.",
            400,
        )
    return num


def _open_doc(data: bytes) -> fitz.Document:
    """Buka PDF di memori; lempar 422 bila rusak atau terproteksi sandi."""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PdfCompressError(
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
            raise PdfCompressError(
                ERR_PDF_ENCRYPTED,
                "Berkas terproteksi kata sandi. Lepas proteksinya sebelum dikompres.",
                422,
            )
    elif getattr(doc, "is_encrypted", False):
        try:
            unlocked = doc.authenticate("")
        except Exception:
            unlocked = 0
        if not unlocked:
            doc.close()
            raise PdfCompressError(
                ERR_PDF_ENCRYPTED,
                "Berkas terproteksi kata sandi. Lepas proteksinya sebelum dikompres.",
                422,
            )

    try:
        count = len(doc)
    except Exception as exc:
        doc.close()
        raise PdfCompressError(
            ERR_PDF_UNREADABLE,
            "Berkas rusak: daftar halaman tidak bisa dibaca.",
            422,
        ) from exc

    if count <= 0:
        doc.close()
        raise PdfCompressError(
            ERR_PDF_UNREADABLE,
            "Berkas tidak memiliki halaman yang bisa dibaca.",
            422,
        )

    if count > MAX_PAGES:
        doc.close()
        raise PdfCompressError(
            ERR_TOO_MANY_PAGES,
            "Jumlah halaman melebihi batas 300 halaman.",
            413,
        )

    return doc


# --- Fungsi publik utama -----------------------------------------------------
def inspect_pdf(data: bytes) -> PdfInfo:
    """Validasi PDF dan kembalikan jumlah halaman serta ukuran berkas."""
    if data is None:
        raise PdfCompressError(ERR_NO_FILE, "Tidak ada berkas yang dikirim.", 400)
    if len(data) == 0:
        raise PdfCompressError(ERR_EMPTY_FILE, "Berkas PDF kosong (0 byte).", 400)
    check_size(len(data))
    if not is_pdf_bytes(data):
        raise PdfCompressError(
            ERR_NOT_PDF,
            "Berkas bukan PDF asli (header %PDF- tidak ditemukan). Hanya berkas PDF yang diperbolehkan.",
            400,
        )

    doc = _open_doc(data)
    try:
        pages = len(doc)
        return PdfInfo(page_count=pages, size_bytes=len(data))
    finally:
        doc.close()


def compress_pdf(
    data: bytes,
    mode: str,
    dpi: int | str | None = None,
    quality: int | str | None = None,
) -> CompressResult:
    """Perkecil ukuran berkas PDF sesuai mode. Semua pemrosesan di memori."""
    if not mode or mode not in MODES:
        raise PdfCompressError(
            ERR_UNSUPPORTED_MODE,
            "Mode kompresi tidak didukung. Pilih 'ringan', 'sedang', atau 'kuat'.",
            400,
        )

    parsed_dpi = parse_dpi(dpi)
    parsed_quality = parse_quality(quality)

    if data is None:
        raise PdfCompressError(ERR_NO_FILE, "Tidak ada berkas yang dikirim.", 400)
    if len(data) == 0:
        raise PdfCompressError(ERR_EMPTY_FILE, "Berkas PDF kosong (0 byte).", 400)
    check_size(len(data))
    if not is_pdf_bytes(data):
        raise PdfCompressError(
            ERR_NOT_PDF,
            "Berkas bukan PDF asli (header %PDF- tidak ditemukan). Hanya berkas PDF yang diperbolehkan.",
            400,
        )

    doc = _open_doc(data)
    try:
        page_count = len(doc)
        notes: list[str] = []

        if mode == "ringan":
            keep_text = True
            try:
                doc.subset_fonts()
            except Exception:
                pass
            out = io.BytesIO()
            doc.save(
                out,
                garbage=4,
                deflate=True,
                deflate_images=True,
                deflate_fonts=True,
                clean=True,
            )
            res_bytes = out.getvalue()
            notes.append(
                "Mode ringan: struktur dokumen dirapikan dan font dibersihkan tanpa mengubah mutu atau keterbacaan teks."
            )

        elif mode == "sedang":
            keep_text = True
            try:
                doc.subset_fonts()
            except Exception:
                pass
            try:
                doc.rewrite_images(dpi_threshold=150, dpi_target=100, quality=75)
            except Exception:
                pass
            out = io.BytesIO()
            doc.save(
                out,
                garbage=4,
                deflate=True,
                deflate_images=True,
                deflate_fonts=True,
                clean=True,
            )
            res_bytes = out.getvalue()
            notes.append(
                "Mode sedang: resolusi gambar diturunkan secara seimbang tanpa mengubah teks sehingga tetap bisa dipilih dan dicari."
            )

        elif mode == "kuat":
            keep_text = False
            doc_baru = fitz.open()
            try:
                for page in doc:
                    pix = page.get_pixmap(dpi=parsed_dpi, alpha=False)
                    jpeg_bytes = pix.tobytes("jpeg", jpg_quality=parsed_quality)
                    page_w = (pix.width / parsed_dpi) * 72.0
                    page_h = (pix.height / parsed_dpi) * 72.0
                    new_page = doc_baru.new_page(width=page_w, height=page_h)
                    rect = fitz.Rect(0, 0, page_w, page_h)
                    new_page.insert_image(rect, stream=jpeg_bytes)
                out = io.BytesIO()
                doc_baru.save(out, garbage=4, deflate=True)
                res_bytes = out.getvalue()
            finally:
                doc_baru.close()
            notes.append(
                "Mode kuat: halaman diubah menjadi gambar (rasterisasi). Teks tidak dapat dicari atau disalin lagi. Mode ini paling cocok untuk dokumen hasil pindai (scan) atau foto."
            )
        else:
            raise PdfCompressError(
                ERR_UNSUPPORTED_MODE,
                "Mode kompresi tidak didukung. Pilih 'ringan', 'sedang', atau 'kuat'.",
                400,
            )

        used_original = False
        if len(res_bytes) >= len(data):
            res_bytes = data
            used_original = True
            notes.append(
                "Berkas aslinya sudah efisien, jadi hasil kompresi tidak lebih kecil. Kami kembalikan berkas asli Anda."
            )
            if mode == "kuat":
                notes.append(
                    "Rasterisasi tidak membuat berkas ini lebih kecil. Tingkat Sedang atau Ringan bisa dicoba sebagai perbandingan."
                )
        elif (len(data) - len(res_bytes)) * 100 / len(data) < 1:
            notes.append(
                "Penghematannya sangat kecil (di bawah 1 persen) karena berkas ini sudah cukup efisien. Coba tingkat Sedang atau Kuat bila ingin lebih ringan."
            )

        return CompressResult(
            data=res_bytes,
            size_before=len(data),
            size_after=len(res_bytes),
            page_count=page_count,
            mode=mode,
            keep_text=keep_text,
            used_original=used_original,
            notes=notes,
        )
    finally:
        doc.close()
