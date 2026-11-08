"""Logika penomoran halaman PDF: fungsi murni di memori, tanpa HTTP.

Menambahkan nomor halaman ke dokumen PDF (ditempel di atas halaman) dengan
pilihan posisi, format, nomor awal, ukuran huruf, dan rentang halaman.
Semua pemrosesan di memori (io.BytesIO). Tidak ada berkas yang ditulis ke disk.
Nama berkas pengguna dan isinya tidak dicatat ke log.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pymupdf

# --- Batas yang berlaku -----------------------------------------------------
MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB, 1 berkas (26214400 bytes)
MAX_PAGES = 300                     # Maksimum halaman dokumen PDF
TIMEOUT_SECONDS = 30

# --- Konstanta format & magic bytes ------------------------------------------
PDF_MAGIC = b"%PDF-"
MAGIC_SCAN_WINDOW = 1024

POSITIONS = (
    {"id": "bawah-tengah", "label": "Bawah tengah"},
    {"id": "bawah-kanan", "label": "Bawah kanan"},
    {"id": "bawah-kiri", "label": "Bawah kiri"},
    {"id": "atas-tengah", "label": "Atas tengah"},
    {"id": "atas-kanan", "label": "Atas kanan"},
    {"id": "atas-kiri", "label": "Atas kiri"},
)
POSITION_IDS = tuple(p["id"] for p in POSITIONS)

FORMATS = (
    {"id": "angka", "label": "Angka saja (contoh: 7)"},
    {"id": "angka_total", "label": "Angka dari total (contoh: 7 / 24)"},
    {"id": "halaman_dari", "label": "Halaman X dari Y (contoh: Halaman 7 dari 24)"},
)
FORMAT_IDS = tuple(f["id"] for f in FORMATS)

DEFAULT_POSITION = "bawah-tengah"
DEFAULT_FORMAT = "angka"
DEFAULT_START = 1
DEFAULT_SIZE = 11
MIN_START = 1
MAX_START = 99999
MIN_SIZE = 8
MAX_SIZE = 24

# --- Catatan jujur layanan ---------------------------------------------------
NOTES = [
    "Nomor halaman ditempel di atas isi halaman yang ada. Jika dokumen sudah memiliki nomor halaman, nomor baru bisa bertumpuk.",
    "Hasil terbaik dari PDF yang tidak terkunci. PDF yang dilindungi kata sandi belum didukung.",
    "Maksimal 300 halaman dan 25 MB per berkas.",
    "Berkas diproses di layanan lalu langsung dihapus, tidak disimpan.",
]

# --- Kode error --------------------------------------------------------------
ERR_NO_FILE = "NO_FILE"
ERR_EMPTY_FILE = "EMPTY_FILE"
ERR_NOT_PDF = "NOT_PDF"
ERR_PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
ERR_TOO_MANY_PAGES = "TOO_MANY_PAGES"
ERR_PDF_UNREADABLE = "PDF_UNREADABLE"
ERR_PDF_ENCRYPTED = "PDF_ENCRYPTED"
ERR_INVALID_POSITION = "INVALID_POSITION"
ERR_INVALID_FORMAT = "INVALID_FORMAT"
ERR_INVALID_START = "INVALID_START"
ERR_INVALID_SIZE = "INVALID_SIZE"
ERR_INVALID_PAGES = "INVALID_PAGES"
ERR_NO_PAGES_SELECTED = "NO_PAGES_SELECTED"


class PdfPageNumbersError(Exception):
    """Kesalahan penomoran halaman PDF yang dipetakan ke kode dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict:
        """Bentuk respons error yang dipakai layanan: {"error": {...}}."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class PdfPageNumbersResult:
    """Hasil penomoran PDF biner (semua di memori)."""

    data: bytes
    total_pages: int
    numbered_pages: int
    start_number: int
    output_name: str = "pdf-bernomor.pdf"
    mime_type: str = "application/pdf"


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
        raise PdfPageNumbersError(
            ERR_PAYLOAD_TOO_LARGE,
            f"Ukuran berkas melebihi batas {MAX_FILE_BYTES // (1024 * 1024)} MB.",
            413,
        )


def _open_doc(data: bytes) -> pymupdf.Document:
    """Buka PDF di memori; lempar error bila kosong, rusak, atau terkunci."""
    if data is None:
        raise PdfPageNumbersError(ERR_NO_FILE, "Tidak ada berkas yang dikirim.", 400)
    if len(data) == 0:
        raise PdfPageNumbersError(ERR_EMPTY_FILE, "Berkas kosong.", 400)
    check_size(len(data))
    if not is_pdf_bytes(data):
        raise PdfPageNumbersError(ERR_NOT_PDF, "Berkas bukan dokumen PDF yang sah.", 400)

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PdfPageNumbersError(
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
            raise PdfPageNumbersError(
                ERR_PDF_ENCRYPTED,
                "Berkas terproteksi kata sandi. Buka proteksinya sebelum diberi nomor.",
                422,
            )
    elif getattr(doc, "is_encrypted", False):
        try:
            unlocked = doc.authenticate("")
        except Exception:
            unlocked = 0
        if not unlocked:
            doc.close()
            raise PdfPageNumbersError(
                ERR_PDF_ENCRYPTED,
                "Berkas terproteksi kata sandi. Buka proteksinya sebelum diberi nomor.",
                422,
            )

    try:
        count = len(doc)
    except Exception as exc:
        doc.close()
        raise PdfPageNumbersError(
            ERR_PDF_UNREADABLE,
            "Berkas rusak: daftar halaman tidak bisa dibaca.",
            422,
        ) from exc

    if count <= 0:
        doc.close()
        raise PdfPageNumbersError(
            ERR_PDF_UNREADABLE,
            "Dokumen PDF tidak memiliki halaman yang bisa dibaca.",
            422,
        )

    if count > MAX_PAGES:
        doc.close()
        raise PdfPageNumbersError(
            ERR_TOO_MANY_PAGES,
            f"Jumlah halaman ({count}) melebihi batas {MAX_PAGES} halaman.",
            413,
        )

    return doc


def limits_payload() -> dict:
    """Payload batas yang dikembalikan endpoint limits."""
    return {
        "max_bytes": MAX_FILE_BYTES,
        "max_mb": MAX_FILE_BYTES // (1024 * 1024),
        "max_pages": MAX_PAGES,
        "default_position": DEFAULT_POSITION,
        "default_format": DEFAULT_FORMAT,
        "default_start": DEFAULT_START,
        "default_size": DEFAULT_SIZE,
        "min_start": MIN_START,
        "max_start": MAX_START,
        "min_size": MIN_SIZE,
        "max_size": MAX_SIZE,
        "positions": [dict(p) for p in POSITIONS],
        "formats": [dict(f) for f in FORMATS],
        "timeout_seconds": TIMEOUT_SECONDS,
        "notes": list(NOTES),
        "processed_on": "server",
    }


def parse_position(position_val: str | None) -> str:
    """Validasi posisi nomor halaman."""
    if position_val is None:
        return DEFAULT_POSITION
    if not isinstance(position_val, str):
        raise PdfPageNumbersError(
            ERR_INVALID_POSITION,
            "Posisi nomor halaman tidak valid. Pilih 'bawah-tengah', 'bawah-kanan', 'bawah-kiri', 'atas-tengah', 'atas-kanan', atau 'atas-kiri'.",
            400,
        )
    pos = position_val.strip().lower()
    if not pos:
        return DEFAULT_POSITION
    if pos not in POSITION_IDS:
        raise PdfPageNumbersError(
            ERR_INVALID_POSITION,
            "Posisi nomor halaman tidak valid. Pilih 'bawah-tengah', 'bawah-kanan', 'bawah-kiri', 'atas-tengah', 'atas-kanan', atau 'atas-kiri'.",
            400,
        )
    return pos


def parse_format(format_val: str | None) -> str:
    """Validasi format tampilan nomor halaman."""
    if format_val is None:
        return DEFAULT_FORMAT
    if not isinstance(format_val, str):
        raise PdfPageNumbersError(
            ERR_INVALID_FORMAT,
            "Format nomor halaman tidak valid. Pilih 'angka', 'angka_total', atau 'halaman_dari'.",
            400,
        )
    fmt = format_val.strip().lower()
    if not fmt:
        return DEFAULT_FORMAT
    if fmt not in FORMAT_IDS:
        raise PdfPageNumbersError(
            ERR_INVALID_FORMAT,
            "Format nomor halaman tidak valid. Pilih 'angka', 'angka_total', atau 'halaman_dari'.",
            400,
        )
    return fmt


def parse_start(start_val: int | str | None) -> int:
    """Validasi nomor awal (1..99999)."""
    if start_val is None:
        return DEFAULT_START
    if isinstance(start_val, bool):
        raise PdfPageNumbersError(
            ERR_INVALID_START,
            "Nomor awal halaman harus berupa bilangan bulat antara 1 sampai 99999.",
            400,
        )
    if isinstance(start_val, int):
        num = start_val
    elif isinstance(start_val, str):
        s = start_val.strip()
        if not s:
            return DEFAULT_START
        try:
            num = int(s)
        except ValueError:
            raise PdfPageNumbersError(
                ERR_INVALID_START,
                "Nomor awal halaman harus berupa bilangan bulat antara 1 sampai 99999.",
                400,
            )
    else:
        raise PdfPageNumbersError(
            ERR_INVALID_START,
            "Nomor awal halaman harus berupa bilangan bulat antara 1 sampai 99999.",
            400,
        )

    if num < MIN_START or num > MAX_START:
        raise PdfPageNumbersError(
            ERR_INVALID_START,
            f"Nomor awal halaman harus berupa bilangan bulat antara {MIN_START} sampai {MAX_START}.",
            400,
        )
    return num


def parse_size(size_val: float | int | str | None) -> float:
    """Validasi ukuran huruf (8..24 pt)."""
    if size_val is None:
        return float(DEFAULT_SIZE)
    if isinstance(size_val, bool):
        raise PdfPageNumbersError(
            ERR_INVALID_SIZE,
            "Ukuran huruf harus berupa angka antara 8 sampai 24 pt.",
            400,
        )
    if isinstance(size_val, (int, float)):
        val = float(size_val)
    elif isinstance(size_val, str):
        s = size_val.strip()
        if not s:
            return float(DEFAULT_SIZE)
        try:
            val = float(s)
        except ValueError:
            raise PdfPageNumbersError(
                ERR_INVALID_SIZE,
                "Ukuran huruf harus berupa angka antara 8 sampai 24 pt.",
                400,
            )
    else:
        raise PdfPageNumbersError(
            ERR_INVALID_SIZE,
            "Ukuran huruf harus berupa angka antara 8 sampai 24 pt.",
            400,
        )

    if val < MIN_SIZE or val > MAX_SIZE:
        raise PdfPageNumbersError(
            ERR_INVALID_SIZE,
            f"Ukuran huruf harus berupa angka antara {MIN_SIZE} sampai {MAX_SIZE} pt.",
            400,
        )
    return val


def parse_pages(pages_val: str | None, total_pages: int) -> list[int]:
    """Parse ekspresi rentang halaman 1-based (mis. '1-5,8').

    Jika None atau string kosong, kembalikan semua halaman.
    """
    if pages_val is None:
        return list(range(1, total_pages + 1))
    if not isinstance(pages_val, str):
        raise PdfPageNumbersError(
            ERR_INVALID_PAGES,
            "Format rentang halaman tidak valid.",
            400,
        )

    expr = pages_val.strip()
    if not expr:
        return list(range(1, total_pages + 1))

    parts = expr.split(",")
    selected: set[int] = set()

    for raw_part in parts:
        part = raw_part.strip()
        if not part:
            raise PdfPageNumbersError(
                ERR_INVALID_PAGES,
                "Format rentang halaman tidak valid.",
                400,
            )
        if "-" in part:
            sub = part.split("-")
            if len(sub) != 2:
                raise PdfPageNumbersError(
                    ERR_INVALID_PAGES,
                    "Format rentang halaman tidak valid.",
                    400,
                )
            start_str, end_str = sub[0].strip(), sub[1].strip()
            if not start_str.isdigit() or not end_str.isdigit():
                raise PdfPageNumbersError(
                    ERR_INVALID_PAGES,
                    "Nomor halaman pada rentang harus berupa angka.",
                    400,
                )
            p_start, p_end = int(start_str), int(end_str)
            if p_start < 1 or p_end < 1 or p_start > total_pages or p_end > total_pages or p_start > p_end:
                raise PdfPageNumbersError(
                    ERR_INVALID_PAGES,
                    "Nomor rentang halaman di luar batas dokumen.",
                    400,
                )
            for p in range(p_start, p_end + 1):
                selected.add(p)
        else:
            if not part.isdigit():
                raise PdfPageNumbersError(
                    ERR_INVALID_PAGES,
                    "Nomor halaman harus berupa angka.",
                    400,
                )
            num = int(part)
            if num < 1 or num > total_pages:
                raise PdfPageNumbersError(
                    ERR_INVALID_PAGES,
                    "Nomor halaman di luar batas dokumen.",
                    400,
                )
            selected.add(num)

    if not selected:
        raise PdfPageNumbersError(
            ERR_NO_PAGES_SELECTED,
            "Tidak ada halaman yang dipilih untuk diberi nomor.",
            400,
        )

    return sorted(selected)


def _calc_text_point(rect: pymupdf.Rect, text: str, position: str, size: float) -> pymupdf.Point:
    """Hitung titik koordinat (x, baseline y) penempatan nomor halaman."""
    w, h = rect.width, rect.height
    shortest = min(w, h)

    # Margin proporsional 4-5% sisi terpendek, min 18 pt, maks 40 pt
    # Jika halaman kecil (< 100 pt), kecilkan margin agar tetap pas
    if shortest < 100.0:
        margin = max(2.0, shortest * 0.045)
    else:
        margin = min(40.0, max(18.0, shortest * 0.045))

    tw = pymupdf.get_text_length(text, fontname="helv", fontsize=size)

    # Koordinat X horizontal
    if "kiri" in position:
        x = rect.x0 + margin
    elif "kanan" in position:
        x = max(rect.x0, rect.x1 - margin - tw)
    else:  # tengah
        x = max(rect.x0, rect.x0 + (w - tw) / 2.0)

    # Koordinat Y vertikal (baseline untuk insert_text)
    if position.startswith("atas"):
        y = rect.y0 + margin + size * 0.8
    else:  # bawah
        y = rect.y1 - margin

    return pymupdf.Point(x, y)


def add_page_numbers(
    data: bytes,
    position: str | None = None,
    format_val: str | None = None,
    start: int | str | None = None,
    size: float | int | str | None = None,
    pages: str | None = None,
) -> PdfPageNumbersResult:
    """Tambahkan nomor halaman pada dokumen PDF di memori."""
    pos = parse_position(position)
    fmt = parse_format(format_val)
    start_num = parse_start(start)
    font_size = parse_size(size)

    doc = _open_doc(data)
    try:
        total_pages = len(doc)
        selected_pages = parse_pages(pages, total_pages)

        # Tempel nomor halaman pada tiap halaman yang dipilih
        for idx, page_num in enumerate(selected_pages):
            page_idx = page_num - 1
            page = doc[page_idx]
            current_num = start_num + idx

            if fmt == "angka":
                text = str(current_num)
            elif fmt == "angka_total":
                text = f"{current_num} / {total_pages}"
            elif fmt == "halaman_dari":
                text = f"Halaman {current_num} dari {total_pages}"
            else:
                text = str(current_num)

            pt = _calc_text_point(page.rect, text, pos, font_size)
            page.insert_text(
                pt,
                text,
                fontname="helv",
                fontsize=font_size,
                color=(0.15, 0.15, 0.15),
            )

        buf = io.BytesIO()
        doc.save(buf)
        output_bytes = buf.getvalue()

        return PdfPageNumbersResult(
            data=output_bytes,
            total_pages=total_pages,
            numbered_pages=len(selected_pages),
            start_number=start_num,
        )
    finally:
        doc.close()
