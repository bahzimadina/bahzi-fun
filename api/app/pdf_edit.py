"""Logika penyuntingan halaman PDF: fungsi murni di memori, tanpa HTTP.

Alat menyunting halaman PDF: putar, hapus, susun ulang, dan lihat info.
Semua pemrosesan di memori (io.BytesIO). Tidak ada berkas yang ditulis ke disk.
Nama berkas pengguna dan isinya tidak dicatat ke log.
Privasi: log hanya mencatat angka (mode, halaman asal/hasil/affected, durasi).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pymupdf

# --- Batas yang berlaku -----------------------------------------------------
MAX_FILE_BYTES = 25 * 1024 * 1024   # 25 MB, 1 berkas (26214400 bytes)
MAX_PAGES = 300                      # Maksimum halaman PDF masukan
ANGLES = (90, 180, 270)
VALID_ANGLES = (90, 180, 270, -90, -180, -270)
TIMEOUT_SECONDS = 30

# --- Konstanta format & magic bytes ------------------------------------------
PDF_MAGIC = b"%PDF-"
MAGIC_SCAN_WINDOW = 1024

MODES = (
    {"id": "info", "label": "Lihat info"},
    {"id": "putar", "label": "Putar halaman"},
    {"id": "hapus", "label": "Hapus halaman"},
    {"id": "urutkan", "label": "Susun ulang urutan"},
)
MODE_IDS = tuple(m["id"] for m in MODES)

# --- Catatan jujur layanan ---------------------------------------------------
NOTES = [
    "Tulisan di dalam halaman tidak bisa diubah, ini hanya mengatur halaman.",
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
ERR_UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
ERR_INVALID_PAGES = "INVALID_PAGES"
ERR_NO_PAGES_LEFT = "NO_PAGES_LEFT"
ERR_INVALID_ANGLE = "INVALID_ANGLE"


class PdfEditError(Exception):
    """Kesalahan penyuntingan PDF yang dipetakan ke kode dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict:
        """Bentuk respons error yang dipakai layanan: {"error": {...}}."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class PdfEditResult:
    """Hasil penyuntingan PDF biner (semua di memori)."""

    data: bytes
    source_pages: int
    result_pages: int
    affected_pages: int
    output_name: str = "editor-pdf.pdf"
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
        raise PdfEditError(
            ERR_PAYLOAD_TOO_LARGE,
            f"Ukuran berkas melebihi batas {MAX_FILE_BYTES // (1024 * 1024)} MB.",
            413,
        )


def _open_doc(data: bytes) -> pymupdf.Document:
    """Buka PDF di memori; lempar error bila kosong, rusak, atau terkunci."""
    if data is None:
        raise PdfEditError(ERR_NO_FILE, "Tidak ada berkas yang dikirim.", 400)
    if len(data) == 0:
        raise PdfEditError(ERR_EMPTY_FILE, "Berkas kosong.", 400)
    check_size(len(data))
    if not is_pdf_bytes(data):
        raise PdfEditError(ERR_NOT_PDF, "Berkas bukan dokumen PDF yang sah.", 400)

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PdfEditError(
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
            raise PdfEditError(
                ERR_PDF_ENCRYPTED,
                "Berkas terproteksi kata sandi. Buka proteksinya sebelum diedit.",
                422,
            )
    elif getattr(doc, "is_encrypted", False):
        try:
            unlocked = doc.authenticate("")
        except Exception:
            unlocked = 0
        if not unlocked:
            doc.close()
            raise PdfEditError(
                ERR_PDF_ENCRYPTED,
                "Berkas terproteksi kata sandi. Buka proteksinya sebelum diedit.",
                422,
            )

    try:
        count = len(doc)
    except Exception as exc:
        doc.close()
        raise PdfEditError(
            ERR_PDF_UNREADABLE,
            "Berkas rusak: daftar halaman tidak bisa dibaca.",
            422,
        ) from exc

    if count <= 0:
        doc.close()
        raise PdfEditError(
            ERR_PDF_UNREADABLE,
            "Dokumen PDF tidak memiliki halaman yang bisa dibaca.",
            422,
        )

    if count > MAX_PAGES:
        doc.close()
        raise PdfEditError(
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
        "modes": [dict(m) for m in MODES],
        "angles": list(ANGLES),
        "timeout_seconds": TIMEOUT_SECONDS,
        "notes": list(NOTES),
        "processed_on": "server",
    }


def get_pdf_info(data: bytes) -> dict:
    """Ekstrak informasi metadata PDF untuk mode info."""
    doc = _open_doc(data)
    try:
        page_count = len(doc)
        page_sizes = [
            {"width": round(doc[i].rect.width, 2), "height": round(doc[i].rect.height, 2)}
            for i in range(min(page_count, 10))
        ]
        rotations = [doc[i].rotation for i in range(page_count)]
        return {
            "page_count": page_count,
            "encrypted": False,
            "page_sizes": page_sizes,
            "rotation": rotations,
        }
    finally:
        doc.close()


def parse_angle(angle_val: int | str | None) -> int:
    """Validasi dan normalisasi nilai sudut rotasi (90, 180, 270 atau -90, -180, -270)."""
    if angle_val is None:
        return 90
    if isinstance(angle_val, bool):
        raise PdfEditError(
            ERR_INVALID_ANGLE,
            "Sudut putar tidak valid. Pilih 90, 180, atau 270 derajat.",
            400,
        )
    if isinstance(angle_val, int):
        num = angle_val
    elif isinstance(angle_val, str):
        s = angle_val.strip()
        if not s:
            return 90
        try:
            num = int(s)
        except ValueError:
            raise PdfEditError(
                ERR_INVALID_ANGLE,
                "Sudut putar tidak valid. Pilih 90, 180, atau 270 derajat.",
                400,
            )
    else:
        raise PdfEditError(
            ERR_INVALID_ANGLE,
            "Sudut putar tidak valid. Pilih 90, 180, atau 270 derajat.",
            400,
        )

    if num not in VALID_ANGLES:
        raise PdfEditError(
            ERR_INVALID_ANGLE,
            "Sudut putar tidak valid. Pilih 90, 180, atau 270 derajat.",
            400,
        )
    return num


def parse_page_range(expr: str | None, page_count: int, required: bool = True) -> list[int]:
    """Parse ekspresi rentang halaman 1-based (mis. '2', '1-3', '1,3,5-7')."""
    if expr is None or not expr.strip():
        if not required:
            return list(range(1, page_count + 1))
        raise PdfEditError(ERR_INVALID_PAGES, "Rentang halaman wajib diisi.", 400)

    parts = expr.split(",")
    selected: set[int] = set()

    for raw_part in parts:
        part = raw_part.strip()
        if not part:
            raise PdfEditError(ERR_INVALID_PAGES, "Format rentang halaman tidak valid.", 400)
        if "-" in part:
            sub = part.split("-")
            if len(sub) != 2:
                raise PdfEditError(ERR_INVALID_PAGES, "Format rentang halaman tidak valid.", 400)
            start_str, end_str = sub[0].strip(), sub[1].strip()
            if not start_str.isdigit() or not end_str.isdigit():
                raise PdfEditError(ERR_INVALID_PAGES, "Nomor halaman pada rentang harus berupa angka.", 400)
            start, end = int(start_str), int(end_str)
            if start < 1 or end < 1 or start > page_count or end > page_count or start > end:
                raise PdfEditError(ERR_INVALID_PAGES, "Nomor rentang halaman di luar batas dokumen.", 400)
            for p in range(start, end + 1):
                selected.add(p)
        else:
            if not part.isdigit():
                raise PdfEditError(ERR_INVALID_PAGES, "Nomor halaman harus berupa angka.", 400)
            num = int(part)
            if num < 1 or num > page_count:
                raise PdfEditError(ERR_INVALID_PAGES, "Nomor halaman di luar batas dokumen.", 400)
            selected.add(num)

    if not selected:
        raise PdfEditError(ERR_INVALID_PAGES, "Tidak ada halaman yang dipilih.", 400)

    return sorted(selected)


def parse_order(expr: str | None, page_count: int) -> list[int]:
    """Parse urutan halaman lengkap untuk mode urutkan (mis. '3,1,2')."""
    if expr is None or not expr.strip():
        raise PdfEditError(ERR_INVALID_PAGES, "Urutan halaman wajib diisi.", 400)

    parts = expr.split(",")
    ordered: list[int] = []

    for raw_part in parts:
        part = raw_part.strip()
        if not part or not part.isdigit():
            raise PdfEditError(ERR_INVALID_PAGES, "Urutan halaman harus berupa angka yang dipisahkan koma.", 400)
        num = int(part)
        if num < 1 or num > page_count:
            raise PdfEditError(ERR_INVALID_PAGES, "Nomor halaman pada urutan di luar batas dokumen.", 400)
        ordered.append(num)

    if len(ordered) != page_count or set(ordered) != set(range(1, page_count + 1)):
        raise PdfEditError(
            ERR_INVALID_PAGES,
            "Urutan halaman harus memuat setiap halaman dari 1 sampai "
            f"{page_count} tepat satu kali tanpa duplikat.",
            400,
        )

    return ordered


def edit_pdf(
    data: bytes,
    mode: str,
    pages: str | None = None,
    order: str | None = None,
    angle: int | str | None = None,
) -> PdfEditResult | dict:
    """Fungsi utama penyuntingan halaman PDF: info, putar, hapus, atau urutkan."""
    if not mode or not isinstance(mode, str):
        raise PdfEditError(ERR_UNSUPPORTED_MODE, "Mode penyuntingan wajib diisi.", 400)

    clean_mode = mode.strip().lower()
    if clean_mode not in MODE_IDS:
        raise PdfEditError(
            ERR_UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak didukung. Pilih 'info', 'putar', 'hapus', atau 'urutkan'.",
            400,
        )

    if clean_mode == "info":
        return get_pdf_info(data)

    doc = _open_doc(data)
    try:
        source_pages = len(doc)

        if clean_mode == "putar":
            ang = parse_angle(angle)
            pages_to_rotate = parse_page_range(pages, source_pages, required=False)
            for p in pages_to_rotate:
                page_idx = p - 1
                page = doc[page_idx]
                new_rotation = (page.rotation + ang) % 360
                page.set_rotation(new_rotation)

            buf = io.BytesIO()
            doc.save(buf)
            return PdfEditResult(
                data=buf.getvalue(),
                source_pages=source_pages,
                result_pages=source_pages,
                affected_pages=len(pages_to_rotate),
            )

        elif clean_mode == "hapus":
            pages_to_delete = set(parse_page_range(pages, source_pages, required=True))
            if len(pages_to_delete) >= source_pages:
                raise PdfEditError(
                    ERR_NO_PAGES_LEFT,
                    "Semua halaman tidak bisa dihapus, sisakan minimal satu.",
                    400,
                )

            keep_indices = [i for i in range(source_pages) if (i + 1) not in pages_to_delete]
            doc.select(keep_indices)

            buf = io.BytesIO()
            doc.save(buf)
            return PdfEditResult(
                data=buf.getvalue(),
                source_pages=source_pages,
                result_pages=len(keep_indices),
                affected_pages=len(pages_to_delete),
            )

        elif clean_mode == "urutkan":
            order_list = parse_order(order, source_pages)
            order_indices = [p - 1 for p in order_list]
            affected_count = sum(1 for i, p in enumerate(order_list) if p != (i + 1))
            doc.select(order_indices)

            buf = io.BytesIO()
            doc.save(buf)
            return PdfEditResult(
                data=buf.getvalue(),
                source_pages=source_pages,
                result_pages=source_pages,
                affected_pages=affected_count,
            )

        else:
            raise PdfEditError(ERR_UNSUPPORTED_MODE, f"Mode '{mode}' tidak didukung.", 400)
    finally:
        doc.close()
