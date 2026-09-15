"""Uji otomatis OmniTools API — Merge PDF.

Bisa dijalankan dua cara:

1. Skrip mandiri (tanpa pytest, tanpa dependensi tambahan):
       cd api && python3 test_api.py
   Menguji logika murni (pdf_merge) + endpoint HTTP via TestClient bila `httpx`
   tersedia + endpoint HTTP langsung bila env OMNITOOLS_API_URL diisi.

2. Sebagai pytest biasa:
       cd api && python3 -m pytest test_api.py -v

Keluar dengan status 1 bila ada uji yang gagal.
"""

from __future__ import annotations

import io
import json
import os
import sys
import traceback
import urllib.error
import urllib.request
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from pypdf import PdfReader, PdfWriter  # noqa: E402

from app import __version__  # noqa: E402
from app.pdf_merge import (  # noqa: E402
    ERR_EMPTY_FILE,
    ERR_ENCRYPTED,
    ERR_NOT_PDF,
    ERR_NO_FILES,
    ERR_TOO_LARGE,
    ERR_TOO_MANY_FILES,
    ERR_TOO_MANY_PAGES,
    ERR_UNREADABLE,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    MAX_TOTAL_PAGES,
    PdfMergeError,
    check_total_size,
    is_pdf_bytes,
    merge_pdfs,
)

SKIPPED: list[str] = []


# --- Pembantu ----------------------------------------------------------------
def make_pdf(pages: int, label: str = "") -> bytes:
    """PDF uji di memori dengan jumlah halaman tertentu."""
    writer = PdfWriter()
    for index in range(pages):
        writer.add_blank_page(width=200, height=200)
    if label:
        writer.add_metadata({"/Title": label})
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_encrypted_pdf(pages: int = 1, password: str = "rahasia") -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    writer.encrypt(password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def page_count(data: bytes) -> int:
    return len(PdfReader(io.BytesIO(data)).pages)


def expect_error(func, code: str, status: int) -> PdfMergeError:
    """Pastikan func() melempar PdfMergeError dengan kode + status yang tepat."""
    try:
        func()
    except PdfMergeError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar PdfMergeError {code}")


# --- Uji logika murni --------------------------------------------------------
def test_magic_bytes_menerima_pdf_asli_menolak_palsu() -> None:
    assert is_pdf_bytes(make_pdf(1)) is True
    assert is_pdf_bytes(b"") is False
    assert is_pdf_bytes(b"ini file txt yang dinamai .pdf") is False
    assert is_pdf_bytes(b"%PDF-1.4\n") is True  # header saja: format benar, isi nanti dinilai


def test_merge_dua_dan_tiga_halaman_menjadi_lima() -> None:
    a = make_pdf(2, "A")
    b = make_pdf(3, "B")
    result = merge_pdfs([a, b])
    assert result.file_count == 2
    assert result.page_count == 5, f"total halaman {result.page_count}, diharapkan 5"
    assert result.page_counts == (2, 3)
    assert result.passthrough is False
    assert page_count(result.data) == 5
    assert result.data.startswith(b"%PDF-")


def test_urutan_berkas_diikuti() -> None:
    """Urutan kiriman menentukan urutan halaman (2+3 vs 3+2)."""
    a = make_pdf(2)
    b = make_pdf(3)
    assert merge_pdfs([a, b]).page_counts == (2, 3)
    assert merge_pdfs([b, a]).page_counts == (3, 2)


def test_satu_berkas_dikembalikan_apa_adanya() -> None:
    a = make_pdf(4)
    result = merge_pdfs([a])
    assert result.passthrough is True
    assert result.data == a, "berkas tunggal harus byte-identik"
    assert result.page_count == 4


def test_menolak_bukan_pdf() -> None:
    expect_error(lambda: merge_pdfs([b"bukan pdf sama sekali"]), ERR_NOT_PDF, 400)


def test_menolak_berkas_kosong() -> None:
    expect_error(lambda: merge_pdfs([b""]), ERR_EMPTY_FILE, 400)


def test_menolak_tanpa_berkas() -> None:
    expect_error(lambda: merge_pdfs([]), ERR_NO_FILES, 400)


def test_menolak_lebih_dari_sepuluh_berkas() -> None:
    payloads = [make_pdf(1) for _ in range(MAX_FILES + 1)]
    expect_error(lambda: merge_pdfs(payloads), ERR_TOO_MANY_FILES, 400)


def test_sepuluh_berkas_masih_diterima() -> None:
    payloads = [make_pdf(1) for _ in range(MAX_FILES)]
    result = merge_pdfs(payloads)
    assert result.file_count == MAX_FILES
    assert result.page_count == MAX_FILES


def test_menolak_total_ukuran_lewat_batas() -> None:
    check_total_size(MAX_TOTAL_BYTES)  # tepat di batas: boleh
    expect_error(lambda: check_total_size(MAX_TOTAL_BYTES + 1), ERR_TOO_LARGE, 413)
    besar = b"%PDF-1.4\n" + b"0" * (MAX_TOTAL_BYTES + 1024)
    expect_error(lambda: merge_pdfs([besar]), ERR_TOO_LARGE, 413)


def test_menolak_lebih_dari_dua_ratus_halaman() -> None:
    banyak = make_pdf(MAX_TOTAL_PAGES + 1)
    expect_error(lambda: merge_pdfs([banyak]), ERR_TOO_MANY_PAGES, 413)


def test_menolak_pdf_rusak() -> None:
    rusak = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog\n" + b"x" * 200
    expect_error(lambda: merge_pdfs([rusak]), ERR_UNREADABLE, 422)


def test_menolak_pdf_terproteksi_sandi() -> None:
    expect_error(lambda: merge_pdfs([make_encrypted_pdf(1)]), ERR_ENCRYPTED, 422)


# --- Uji HTTP lewat TestClient (butuh httpx) ---------------------------------
def _test_client():
    try:
        from fastapi.testclient import TestClient
        from app.main import app
    except Exception as exc:  # httpx belum terpasang, dsb.
        SKIPPED.append(f"uji HTTP TestClient dilewati: {exc}")
        return None
    return TestClient(app)


def test_http_health() -> None:
    client = _test_client()
    if client is None:
        return
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "omnitools-api"
    assert body["version"] == __version__


def test_http_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/pdf/merge/limits")
    assert response.status_code == 200
    body = response.json()
    assert body["max_files"] == MAX_FILES
    assert body["max_total_mb"] == 25
    assert body["max_pages"] == MAX_TOTAL_PAGES
    assert response.headers["cache-control"] == "no-store"


def test_http_merge_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/pdf/merge",
        files=[
            ("files", ("a.pdf", make_pdf(2), "application/pdf")),
            ("files", ("b.pdf", make_pdf(3), "application/pdf")),
        ],
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert 'filename="gabungan.pdf"' in response.headers["content-disposition"]
    assert response.headers["cache-control"].startswith("no-store")
    assert response.headers["x-page-count"] == "5"
    assert response.headers["x-file-count"] == "2"
    assert page_count(response.content) == 5


def test_http_merge_txt_dinamai_pdf_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/pdf/merge",
        files=[("files", ("palsu.pdf", b"ini bukan pdf", "application/pdf"))],
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == ERR_NOT_PDF
    assert body["error"]["message"]


def test_http_merge_sebelas_berkas_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    files = [("files", (f"f{i}.pdf", make_pdf(1), "application/pdf")) for i in range(MAX_FILES + 1)]
    response = client.post("/api/pdf/merge", files=files)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == ERR_TOO_MANY_FILES


def test_http_merge_tanpa_berkas_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/pdf/merge", files=[])
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "NO_FILES"


# --- Uji HTTP ke server yang benar-benar jalan ------------------------------
def test_http_live_jika_env_diisi() -> None:
    """Jalankan hanya bila OMNITOOLS_API_URL diisi, mis. http://127.0.0.1:8077."""
    base = os.getenv("OMNITOOLS_API_URL", "").rstrip("/")
    if not base:
        SKIPPED.append("uji live dilewati: OMNITOOLS_API_URL tidak diisi")
        return

    with urllib.request.urlopen(base + "/health", timeout=10) as response:
        assert response.status == 200
        assert json.loads(response.read())["status"] == "ok"

    # Merge 2 + 3 halaman lewat multipart/form-data sungguhan.
    boundary = "----omnitoolsuji"
    parts: list[bytes] = []
    for name, payload in (("a.pdf", make_pdf(2)), ("b.pdf", make_pdf(3))):
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="files"; filename="{name}"\r\n'
                "Content-Type: application/pdf\r\n\r\n"
            ).encode()
            + payload
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    request = urllib.request.Request(
        base + "/api/pdf/merge",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            disposition = response.headers.get("Content-Disposition", "")
            cache = response.headers.get("Cache-Control", "")
            pages_header = response.headers.get("X-Page-Count", "")
            data = response.read()
    except urllib.error.HTTPError as exc:
        raise AssertionError(f"merge live gagal: HTTP {exc.code} {exc.read()[:200]!r}") from exc

    assert status == 200
    assert content_type.startswith("application/pdf"), content_type
    assert 'filename="gabungan.pdf"' in disposition, disposition
    assert cache.startswith("no-store"), cache
    assert pages_header == "5", pages_header
    assert page_count(data) == 5


# --- Runner mandiri ---------------------------------------------------------
def main() -> int:
    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    passed = 0
    failures: list[tuple[str, str]] = []

    print(f"OmniTools API — uji Merge PDF (versi {__version__}, python {sys.version.split()[0]})")
    print(f"Pemeriksaan akan dijalankan: {len(tests)}\n")

    for name, func in tests:
        try:
            func()
        except Exception:
            failures.append((name, traceback.format_exc()))
            print(f"GAGAL  {name}")
        else:
            passed += 1
            print(f"LULUS  {name}")

    for note in SKIPPED:
        print(f"LEWAT  {note}")

    print(f"\nRingkasan: {passed} lulus, {len(failures)} gagal, {len(SKIPPED)} dilewati")

    for name, detail in failures:
        print(f"\n--- detail kegagalan: {name} ---")
        print(detail)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
