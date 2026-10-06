"""Logika pemisahan PDF — fungsi murni, tanpa HTTP, mudah diuji.

Modul ini tidak bergantung pada FastAPI/uvicorn/HTTP. Semua validasi
(format berkas, ukuran, batas halaman, mode, rentang, dan potongan)
diperiksa di sini sehingga bisa diuji langsung dari Python tanpa server.

Prinsip:
* Semua pemrosesan di memori (io.BytesIO). Tidak ada berkas yang ditulis ke disk.
* Nama berkas pengunjung tidak disimpan atau dicatat ke log.
* Hanya PDF asli yang diterima (pemeriksaan magic bytes %PDF-).
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from typing import Sequence

from pypdf import PdfReader, PdfWriter

# --- Batas yang berlaku -----------------------------------------------------
MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB, satu berkas
MAX_PAGES = 300                    # Maksimum halaman PDF masukan

DEFAULT_CHUNK = 5
MIN_CHUNK = 1
MAX_CHUNK = 100

# --- Konstanta format -------------------------------------------------------
PDF_MAGIC = b"%PDF-"
MAGIC_SCAN_WINDOW = 1024

MODES = ("info", "per-halaman", "rentang", "setiap-n")

# --- Kode error --------------------------------------------------------------
ERR_NO_FILE = "NO_FILE"
ERR_EMPTY_FILE = "EMPTY_FILE"
ERR_NOT_PDF = "NOT_PDF"
ERR_PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
ERR_TOO_MANY_PAGES = "TOO_MANY_PAGES"
ERR_PDF_UNREADABLE = "PDF_UNREADABLE"
ERR_PDF_ENCRYPTED = "PDF_ENCRYPTED"
ERR_UNREADABLE = ERR_PDF_UNREADABLE
ERR_ENCRYPTED = ERR_PDF_ENCRYPTED
ERR_UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
ERR_INVALID_PAGES = "INVALID_PAGES"
ERR_INVALID_CHUNK = "INVALID_CHUNK"


class PdfSplitError(Exception):
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
class PdfInfo:
    """Informasi metadata PDF untuk mode info."""

    page_count: int
    size_bytes: int

    def to_dict(self) -> dict:
        return {
            "page_count": self.page_count,
            "size_bytes": self.size_bytes,
            "max_pages": MAX_PAGES,
        }


@dataclass(frozen=True)
class SplitResult:
    """Hasil pemisahan PDF (semua di memori)."""

    data: bytes
    output_kind: str  # "pdf" atau "zip"
    output_name: str  # "pisah-pdf.pdf" atau "pisah-pdf.zip"
    output_count: int
    source_pages: int
    result_pages: int
    first_page: int
    last_page: int


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
        raise PdfSplitError(
            ERR_PAYLOAD_TOO_LARGE,
            "Ukuran berkas melebihi batas 25 MB.",
            413,
        )


def _open_reader(data: bytes) -> PdfReader:
    """Buka PDF di memori; lempar 422 bila rusak atau terproteksi sandi."""
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except Exception as exc:
        raise PdfSplitError(
            ERR_PDF_UNREADABLE,
            "Berkas rusak atau tidak bisa dibaca sebagai PDF.",
            422,
        ) from exc

    if getattr(reader, "is_encrypted", False):
        try:
            unlocked = reader.decrypt("")
        except Exception:
            unlocked = 0
        if not unlocked:
            raise PdfSplitError(
                ERR_PDF_ENCRYPTED,
                "Berkas terproteksi kata sandi. Lepas proteksinya sebelum dipisah.",
                422,
            )
    return reader


def _count_pages(reader: PdfReader) -> int:
    """Hitung jumlah halaman dokumen; lempar 422 bila struktur tidak terbaca."""
    try:
        pages = len(reader.pages)
    except Exception as exc:
        raise PdfSplitError(
            ERR_PDF_UNREADABLE,
            "Berkas rusak: daftar halaman tidak bisa dibaca.",
            422,
        ) from exc
    if pages <= 0:
        raise PdfSplitError(
            ERR_PDF_UNREADABLE,
            "Berkas tidak memiliki halaman yang bisa dibaca.",
            422,
        )
    return pages


def parse_page_range(expr: str | None, page_count: int) -> list[int]:
    """Parse ekspresi rentang halaman (1-based, urut naik, tanpa duplikat).

    Menerima koma sebagai pemisah dan strip (-) untuk rentang, misal '1-3, 5'.
    Toleran terhadap spasi dan urutan masukan tak beraturan.
    """
    if expr is None or not expr.strip():
        raise PdfSplitError(ERR_INVALID_PAGES, "Rentang halaman wajib diisi.", 400)

    parts = expr.split(",")
    selected: set[int] = set()

    for raw_part in parts:
        part = raw_part.strip()
        if not part:
            raise PdfSplitError(ERR_INVALID_PAGES, "Format rentang halaman tidak valid.", 400)
        if "-" in part:
            sub = part.split("-")
            if len(sub) != 2:
                raise PdfSplitError(ERR_INVALID_PAGES, "Format rentang halaman tidak valid.", 400)
            start_str, end_str = sub[0].strip(), sub[1].strip()
            if not start_str.isdigit() or not end_str.isdigit():
                raise PdfSplitError(ERR_INVALID_PAGES, "Nomor halaman pada rentang harus berupa angka.", 400)
            start, end = int(start_str), int(end_str)
            if start < 1 or end < 1 or start > page_count or end > page_count or start > end:
                raise PdfSplitError(ERR_INVALID_PAGES, "Nomor rentang halaman di luar batas dokumen.", 400)
            for p in range(start, end + 1):
                selected.add(p)
        else:
            if not part.isdigit():
                raise PdfSplitError(ERR_INVALID_PAGES, "Nomor halaman harus berupa angka.", 400)
            num = int(part)
            if num < 1 or num > page_count:
                raise PdfSplitError(ERR_INVALID_PAGES, "Nomor halaman di luar batas dokumen.", 400)
            selected.add(num)

    if not selected:
        raise PdfSplitError(ERR_INVALID_PAGES, "Tidak ada halaman yang dipilih.", 400)

    return sorted(selected)


def _parse_chunk(chunk: int | str | None) -> int:
    """Validasi nilai potongan halaman N per berkas."""
    if chunk is None or (isinstance(chunk, str) and not chunk.strip()):
        return DEFAULT_CHUNK
    if isinstance(chunk, bool):
        raise PdfSplitError(ERR_INVALID_CHUNK, "Jumlah halaman per berkas harus berupa angka antara 1 sampai 100.", 400)
    if isinstance(chunk, int):
        val = chunk
    elif isinstance(chunk, str):
        val_str = chunk.strip()
        if not val_str.isdigit():
            raise PdfSplitError(ERR_INVALID_CHUNK, "Jumlah halaman per berkas harus berupa angka antara 1 sampai 100.", 400)
        val = int(val_str)
    else:
        raise PdfSplitError(ERR_INVALID_CHUNK, "Jumlah halaman per berkas harus berupa angka antara 1 sampai 100.", 400)

    if val < MIN_CHUNK or val > MAX_CHUNK:
        raise PdfSplitError(ERR_INVALID_CHUNK, f"Jumlah halaman per berkas harus antara {MIN_CHUNK} sampai {MAX_CHUNK}.", 400)
    return val


def _render_pdf(reader: PdfReader, page_indices: Sequence[int]) -> bytes:
    """Tulis halaman terpilih ke satu berkas PDF di memori."""
    writer = PdfWriter()
    try:
        for idx in page_indices:
            writer.add_page(reader.pages[idx])
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()
    except Exception as exc:
        raise PdfSplitError(
            ERR_PDF_UNREADABLE,
            "Pemisahan PDF gagal: berkas rusak atau memakai fitur yang tidak didukung.",
            422,
        ) from exc


def _create_zip(entries: list[tuple[str, bytes]]) -> bytes:
    """Kemas daftar berkas (nama, byte) ke dalam arsip ZIP di memori."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, file_bytes in entries:
            zf.writestr(name, file_bytes)
    return buf.getvalue()


# --- Fungsi publik utama -----------------------------------------------------
def inspect_pdf(data: bytes) -> PdfInfo:
    """Validasi PDF dan kembalikan jumlah halaman serta ukuran berkas."""
    if data is None:
        raise PdfSplitError(ERR_NO_FILE, "Tidak ada berkas yang dikirim.", 400)
    if len(data) == 0:
        raise PdfSplitError(ERR_EMPTY_FILE, "Berkas PDF kosong (0 byte).", 400)
    check_size(len(data))
    if not is_pdf_bytes(data):
        raise PdfSplitError(
            ERR_NOT_PDF,
            "Berkas bukan PDF asli (header %PDF- tidak ditemukan). Hanya berkas PDF yang diperbolehkan.",
            400,
        )

    reader = _open_reader(data)
    pages = _count_pages(reader)
    if pages > MAX_PAGES:
        raise PdfSplitError(
            ERR_TOO_MANY_PAGES,
            "Jumlah halaman melebihi batas 300 halaman.",
            413,
        )
    return PdfInfo(page_count=pages, size_bytes=len(data))


def split_pdf(
    data: bytes,
    mode: str,
    pages: str | None = None,
    chunk: int | str | None = None,
) -> SplitResult | PdfInfo:
    """Pisah dokumen PDF sesuai mode yang dipilih. Semua pemrosesan di memori."""
    if not mode or mode not in MODES:
        raise PdfSplitError(
            ERR_UNSUPPORTED_MODE,
            "Mode pemisahan tidak didukung. Pilih salah satu mode yang tersedia.",
            400,
        )

    if mode == "info":
        return inspect_pdf(data)

    if data is None:
        raise PdfSplitError(ERR_NO_FILE, "Tidak ada berkas yang dikirim.", 400)
    if len(data) == 0:
        raise PdfSplitError(ERR_EMPTY_FILE, "Berkas PDF kosong (0 byte).", 400)
    check_size(len(data))
    if not is_pdf_bytes(data):
        raise PdfSplitError(
            ERR_NOT_PDF,
            "Berkas bukan PDF asli (header %PDF- tidak ditemukan). Hanya berkas PDF yang diperbolehkan.",
            400,
        )

    reader = _open_reader(data)
    total_pages = _count_pages(reader)
    if total_pages > MAX_PAGES:
        raise PdfSplitError(
            ERR_TOO_MANY_PAGES,
            "Jumlah halaman melebihi batas 300 halaman.",
            413,
        )

    if mode == "per-halaman":
        if total_pages == 1:
            pdf_bytes = _render_pdf(reader, [0])
            return SplitResult(
                data=pdf_bytes,
                output_kind="pdf",
                output_name="pisah-pdf.pdf",
                output_count=1,
                source_pages=1,
                result_pages=1,
                first_page=1,
                last_page=1,
            )

        entries: list[tuple[str, bytes]] = []
        for idx in range(total_pages):
            pdf_bytes = _render_pdf(reader, [idx])
            entries.append((f"halaman-{idx + 1:02d}.pdf", pdf_bytes))
        zip_bytes = _create_zip(entries)
        return SplitResult(
            data=zip_bytes,
            output_kind="zip",
            output_name="pisah-pdf.zip",
            output_count=len(entries),
            source_pages=total_pages,
            result_pages=total_pages,
            first_page=1,
            last_page=total_pages,
        )

    if mode == "rentang":
        selected_pages = parse_page_range(pages, total_pages)
        indices = [p - 1 for p in selected_pages]
        pdf_bytes = _render_pdf(reader, indices)
        return SplitResult(
            data=pdf_bytes,
            output_kind="pdf",
            output_name="pisah-pdf.pdf",
            output_count=1,
            source_pages=total_pages,
            result_pages=len(selected_pages),
            first_page=min(selected_pages),
            last_page=max(selected_pages),
        )

    if mode == "setiap-n":
        chunk_val = _parse_chunk(chunk)
        chunks: list[list[int]] = []
        for start_idx in range(0, total_pages, chunk_val):
            end_idx = min(start_idx + chunk_val, total_pages)
            chunks.append(list(range(start_idx, end_idx)))

        if len(chunks) == 1:
            pdf_bytes = _render_pdf(reader, chunks[0])
            return SplitResult(
                data=pdf_bytes,
                output_kind="pdf",
                output_name="pisah-pdf.pdf",
                output_count=1,
                source_pages=total_pages,
                result_pages=total_pages,
                first_page=1,
                last_page=total_pages,
            )

        entries = []
        for i, p_indices in enumerate(chunks, start=1):
            pdf_bytes = _render_pdf(reader, p_indices)
            entries.append((f"bagian-{i:02d}.pdf", pdf_bytes))
        zip_bytes = _create_zip(entries)
        return SplitResult(
            data=zip_bytes,
            output_kind="zip",
            output_name="pisah-pdf.zip",
            output_count=len(entries),
            source_pages=total_pages,
            result_pages=total_pages,
            first_page=1,
            last_page=total_pages,
        )

    raise PdfSplitError(
        ERR_UNSUPPORTED_MODE,
        "Mode pemisahan tidak didukung. Pilih salah satu mode yang tersedia.",
        400,
    )
