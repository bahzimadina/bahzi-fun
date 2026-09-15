"""Logika penggabungan PDF — fungsi murni, tanpa HTTP, mudah diuji.

Modul ini sengaja tidak tahu apa-apa soal FastAPI/uvicorn/HTTP. Semua
aturannya (bentuk berkas, jumlah, ukuran, halaman) diperiksa di sini
sehingga bisa diuji langsung dari Python tanpa menjalankan server.

Prinsip:
* Semua pemrosesan **di memori** (`io.BytesIO`). Tidak ada berkas yang
  ditulis ke disk, tidak ada nama berkas pengguna yang dicatat.
* Hanya PDF asli yang diterima: diperiksa lewat **magic bytes** `%PDF-`,
  bukan lewat ekstensi atau MIME yang dikirim klien.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Sequence

from pypdf import PdfReader, PdfWriter

# --- Batas yang berlaku (dipakai juga oleh GET /api/pdf/merge/limits) --------
MAX_FILES = 10
MAX_TOTAL_BYTES = 25 * 1024 * 1024  # 25 MB untuk TOTAL semua berkas
MAX_TOTAL_PAGES = 200

# --- Konstanta format -------------------------------------------------------
PDF_MAGIC = b"%PDF-"
# Spesifikasi PDF mengizinkan byte lain sebelum header %PDF- (jarang, tapi sah).
MAGIC_SCAN_WINDOW = 1024

# Ukuran potongan saat membaca unggahan (streaming, hemat memori).
CHUNK_SIZE = 1024 * 1024

# --- Kode error (dipakai klien untuk membedakan sebab kegagalan) -------------
ERR_NO_FILES = "NO_FILES"
ERR_TOO_MANY_FILES = "TOO_MANY_FILES"
ERR_NOT_PDF = "NOT_PDF"
ERR_EMPTY_FILE = "EMPTY_FILE"
ERR_TOO_LARGE = "PAYLOAD_TOO_LARGE"
ERR_TOO_MANY_PAGES = "TOO_MANY_PAGES"
ERR_UNREADABLE = "PDF_UNREADABLE"
ERR_ENCRYPTED = "PDF_ENCRYPTED"


class PdfMergeError(Exception):
    """Kesalahan yang sudah dipetakan ke kode + status HTTP."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict:
        """Bentuk respons error yang dipakai API: {"error": {...}}."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class MergeResult:
    """Hasil penggabungan (semuanya di memori)."""

    data: bytes
    file_count: int
    page_count: int
    page_counts: tuple[int, ...]
    passthrough: bool  # True = 1 berkas, dikembalikan byte-identik


# --- Pemeriksaan dasar ------------------------------------------------------
def is_pdf_bytes(data: bytes) -> bool:
    """True bila byte benar-benar berawalan header PDF (`%PDF-`).

    Bukan sekadar cek ekstensi/MIME: berkas .txt yang dinamai .pdf akan
    gagal di sini.
    """
    if not data:
        return False
    if data.startswith(PDF_MAGIC):
        return True
    return PDF_MAGIC in data[:MAGIC_SCAN_WINDOW]


def check_file_count(count: int) -> None:
    """400 bila tidak ada berkas atau jumlahnya melebihi MAX_FILES."""
    if count <= 0:
        raise PdfMergeError(
            ERR_NO_FILES,
            "Tidak ada berkas yang dikirim. Sertakan minimal satu berkas PDF "
            "pada field 'files' (multipart/form-data).",
            400,
        )
    if count > MAX_FILES:
        raise PdfMergeError(
            ERR_TOO_MANY_FILES,
            f"Maksimum {MAX_FILES} berkas per penggabungan, dikirim {count} berkas.",
            400,
        )


def check_total_size(total_bytes: int) -> None:
    """413 bila total ukuran melebihi MAX_TOTAL_BYTES."""
    if total_bytes > MAX_TOTAL_BYTES:
        limit_mb = MAX_TOTAL_BYTES // (1024 * 1024)
        actual_mb = total_bytes / (1024 * 1024)
        raise PdfMergeError(
            ERR_TOO_LARGE,
            f"Total ukuran berkas {actual_mb:.1f} MB melebihi batas {limit_mb} MB.",
            413,
        )


# --- Pembacaan PDF ----------------------------------------------------------
def _open_reader(data: bytes, index: int) -> PdfReader:
    """Buka PDF dari memori; lempar 422 bila rusak atau terproteksi sandi."""
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except Exception as exc:  # pypdf melempar berbagai tipe untuk berkas rusak
        raise PdfMergeError(
            ERR_UNREADABLE,
            f"Berkas ke-{index} rusak atau tidak bisa dibaca sebagai PDF.",
            422,
        ) from exc

    if getattr(reader, "is_encrypted", False):
        try:
            unlocked = reader.decrypt("")
        except Exception:
            unlocked = 0
        if not unlocked:
            raise PdfMergeError(
                ERR_ENCRYPTED,
                f"Berkas ke-{index} terproteksi kata sandi. Lepas proteksinya "
                "sebelum digabung.",
                422,
            )
    return reader


def _count_pages(reader: PdfReader, index: int) -> int:
    """Jumlah halaman; 422 bila struktur halaman tidak terbaca."""
    try:
        pages = len(reader.pages)
    except Exception as exc:
        raise PdfMergeError(
            ERR_UNREADABLE,
            f"Berkas ke-{index} rusak: daftar halaman tidak bisa dibaca.",
            422,
        ) from exc
    if pages <= 0:
        raise PdfMergeError(
            ERR_UNREADABLE,
            f"Berkas ke-{index} tidak memiliki halaman yang bisa dibaca.",
            422,
        )
    return pages


# --- Fungsi utama -----------------------------------------------------------
def inspect_pdfs(payloads: Sequence[bytes]) -> tuple[int, tuple[int, ...], list[PdfReader]]:
    """Validasi semua berkas. Mengembalikan (total_halaman, halaman_per_berkas, readers).

    Dipakai oleh merge_pdfs() dan berguna untuk pengujian terpisah.
    """
    check_file_count(len(payloads))
    check_total_size(sum(len(p) for p in payloads))

    readers: list[PdfReader] = []
    page_counts: list[int] = []
    total_pages = 0

    for index, data in enumerate(payloads, start=1):
        if not data:
            raise PdfMergeError(ERR_EMPTY_FILE, f"Berkas ke-{index} kosong (0 byte).", 400)
        if not is_pdf_bytes(data):
            raise PdfMergeError(
                ERR_NOT_PDF,
                f"Berkas ke-{index} bukan PDF asli (header %PDF- tidak ditemukan). "
                "Hanya berkas PDF yang diperbolehkan.",
                400,
            )
        reader = _open_reader(data, index)
        pages = _count_pages(reader, index)
        total_pages += pages
        if total_pages > MAX_TOTAL_PAGES:
            raise PdfMergeError(
                ERR_TOO_MANY_PAGES,
                f"Total halaman melebihi batas {MAX_TOTAL_PAGES} halaman "
                f"(sudah {total_pages} halaman pada berkas ke-{index}).",
                413,
            )
        readers.append(reader)
        page_counts.append(pages)

    return total_pages, tuple(page_counts), readers


def merge_pdfs(payloads: Sequence[bytes]) -> MergeResult:
    """Gabungkan PDF sesuai urutan kiriman. Semua di memori.

    Kasus satu berkas: berkas dikembalikan **apa adanya** (byte-identik)
    setelah divalidasi, jadi tidak ada penulisan ulang yang tidak perlu.
    """
    total_pages, page_counts, readers = inspect_pdfs(payloads)

    if len(payloads) == 1:
        return MergeResult(
            data=payloads[0],
            file_count=1,
            page_count=total_pages,
            page_counts=page_counts,
            passthrough=True,
        )

    writer = PdfWriter()
    try:
        for reader in readers:
            for page in reader.pages:
                writer.add_page(page)
        buffer = io.BytesIO()
        writer.write(buffer)
    except PdfMergeError:
        raise
    except Exception as exc:
        raise PdfMergeError(
            ERR_UNREADABLE,
            "Penggabungan gagal: salah satu berkas rusak atau memakai fitur PDF "
            "yang tidak didukung.",
            422,
        ) from exc

    return MergeResult(
        data=buffer.getvalue(),
        file_count=len(payloads),
        page_count=total_pages,
        page_counts=page_counts,
        passthrough=False,
    )


def count_pages(payload: bytes) -> int:
    """Jumlah halaman satu PDF di memori (dipakai pengujian)."""
    data = payload if isinstance(payload, bytes) else bytes(payload)
    if not is_pdf_bytes(data):
        raise PdfMergeError(ERR_NOT_PDF, "Bukan PDF asli (header %PDF- tidak ada).", 400)
    return _count_pages(_open_reader(data, 1), 1)
