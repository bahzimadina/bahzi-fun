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

from PIL import Image  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

from app import __version__  # noqa: E402
from app.image_convert import (  # noqa: E402
    EMPTY_FILE as IMG_EMPTY_FILE,
    IMAGE_TOO_LARGE as IMG_IMAGE_TOO_LARGE,
    IMAGE_UNREADABLE as IMG_IMAGE_UNREADABLE,
    INVALID_QUALITY as IMG_INVALID_QUALITY,
    MAX_BYTES as IMG_MAX_BYTES,
    MAX_FILES as IMG_MAX_FILES,
    MAX_PIXELS as IMG_MAX_PIXELS,
    NO_FILES as IMG_NO_FILES,
    NOT_IMAGE as IMG_NOT_IMAGE,
    PAYLOAD_TOO_LARGE as IMG_PAYLOAD_TOO_LARGE,
    QUALITY_DEFAULT as IMG_QUALITY_DEFAULT,
    QUALITY_MAX as IMG_QUALITY_MAX,
    QUALITY_MIN as IMG_QUALITY_MIN,
    TARGETS as IMG_TARGETS,
    TOO_MANY_FILES as IMG_TOO_MANY_FILES,
    UNSUPPORTED_TARGET as IMG_UNSUPPORTED_TARGET,
    ImageConvertError,
    check_file_count as check_image_file_count,
    check_total_size as check_image_total_size,
    convert_image,
    detect_format,
    is_supported_image,
    normalize_quality,
    normalize_target,
)
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
from app.word_count import (  # noqa: E402
    INVALID_REQUEST as WC_INVALID_REQUEST,
    MAX_BYTES as WC_MAX_BYTES,
    MAX_CHARS as WC_MAX_CHARS,
    NO_TEXT as WC_NO_TEXT,
    STOP_WORDS as WC_STOP_WORDS,
    TOO_LONG as WC_TOO_LONG,
    WordCountError,
    WordCountResult,
    count_text,
    validate_text,
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


def make_image(format: str = "PNG", size: tuple[int, int] = (60, 60), color: str = "blue", mode: str | None = None) -> bytes:
    """Buat berkas gambar uji di memori."""
    img_mode = mode or ("RGBA" if "A" in format.upper() else "RGB")
    img = Image.new(img_mode, size, color)
    buf = io.BytesIO()
    save_fmt = "JPEG" if format.upper() in ("JPG", "JPEG") else format.upper()
    img.save(buf, format=save_fmt)
    return buf.getvalue()


def expect_image_error(func, code: str, status: int) -> ImageConvertError:
    """Pastikan func() melempar ImageConvertError dengan kode + status yang tepat."""
    try:
        func()
    except ImageConvertError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar ImageConvertError {code}")


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


def expect_word_count_error(func, code: str, status: int) -> WordCountError:
    """Pastikan func() melempar WordCountError dengan kode + status yang tepat."""
    try:
        func()
    except WordCountError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar WordCountError {code}")



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


# --- Uji logika Image Converter ---------------------------------------------
def test_image_magic_bytes_detection() -> None:
    png_data = make_image("PNG")
    jpeg_data = make_image("JPEG")
    webp_data = make_image("WEBP")

    assert detect_format(png_data) == "png"
    assert detect_format(jpeg_data) == "jpeg"
    assert detect_format(webp_data) == "webp"
    assert is_supported_image(png_data) is True
    assert is_supported_image(jpeg_data) is True
    assert is_supported_image(webp_data) is True

    assert detect_format(b"") is None
    assert detect_format(b"bukan gambar") is None
    assert is_supported_image(b"bukan gambar") is False


def test_image_convert_png_ke_jpeg_sukses() -> None:
    png = make_image("PNG", size=(50, 50), color="green")
    result = convert_image(png, target="jpeg", quality=85)
    assert result.input_format == "png"
    assert result.output_format == "jpeg"
    assert result.width == 50
    assert result.height == 50
    assert result.data.startswith(b"\xff\xd8\xff")
    assert detect_format(result.data) == "jpeg"


def test_image_convert_jpeg_ke_webp_sukses() -> None:
    jpeg = make_image("JPEG", size=(40, 40), color="red")
    result = convert_image(jpeg, target="webp", quality=80)
    assert result.input_format == "jpeg"
    assert result.output_format == "webp"
    assert detect_format(result.data) == "webp"


def test_image_convert_png_ke_png_sukses() -> None:
    png = make_image("PNG", size=(30, 30), color="yellow")
    result = convert_image(png, target="png")
    assert result.input_format == "png"
    assert result.output_format == "png"
    assert detect_format(result.data) == "png"


def test_image_convert_format_target_sama_dengan_masukan() -> None:
    jpeg = make_image("JPEG", size=(35, 35), color="blue")
    result_jpeg = convert_image(jpeg, target="jpeg")
    assert result_jpeg.output_format == "jpeg"

    webp = make_image("WEBP", size=(35, 35), color="cyan")
    result_webp = convert_image(webp, target="webp")
    assert result_webp.output_format == "webp"


def test_image_convert_kualitas_rendah_lebih_kecil_dari_kualitas_tinggi() -> None:
    img = Image.new("RGB", (120, 120))
    pixels = img.load()
    for x in range(120):
        for y in range(120):
            pixels[x, y] = ((x * 7) % 256, (y * 11) % 256, ((x + y) * 13) % 256)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    png_bytes = buf.getvalue()

    res_q20 = convert_image(png_bytes, target="jpeg", quality=20)
    res_q95 = convert_image(png_bytes, target="jpeg", quality=95)
    assert len(res_q20.data) < len(res_q95.data), (
        f"Kualitas 20 ({len(res_q20.data)} bytes) harus lebih kecil dari 95 ({len(res_q95.data)} bytes)"
    )


def test_image_convert_alpha_ke_jpeg_latar_putih() -> None:
    img = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    png_transparent = buf.getvalue()

    result = convert_image(png_transparent, target="jpeg")
    assert result.output_format == "jpeg"
    out_img = Image.open(io.BytesIO(result.data))
    assert out_img.mode == "RGB"
    assert out_img.getpixel((0, 0)) == (255, 255, 255)


def test_image_convert_menolak_tanpa_berkas() -> None:
    expect_image_error(lambda: check_image_file_count(0), IMG_NO_FILES, 400)


def test_image_convert_menolak_dua_berkas() -> None:
    expect_image_error(lambda: check_image_file_count(2), IMG_TOO_MANY_FILES, 400)


def test_image_convert_menolak_berkas_kosong() -> None:
    expect_image_error(lambda: convert_image(b""), IMG_EMPTY_FILE, 400)


def test_image_convert_menolak_bukan_gambar() -> None:
    expect_image_error(lambda: convert_image(b"ini berkas teks yang dinamai gambar.png"), IMG_NOT_IMAGE, 400)


def test_image_convert_menolak_target_tidak_didukung() -> None:
    png = make_image("PNG")
    expect_image_error(lambda: convert_image(png, target="gif"), IMG_UNSUPPORTED_TARGET, 400)
    expect_image_error(lambda: convert_image(png, target="tiff"), IMG_UNSUPPORTED_TARGET, 400)


def test_image_convert_menolak_kualitas_tidak_valid() -> None:
    png = make_image("PNG")
    expect_image_error(lambda: convert_image(png, quality=0), IMG_INVALID_QUALITY, 400)
    expect_image_error(lambda: convert_image(png, quality=101), IMG_INVALID_QUALITY, 400)
    expect_image_error(lambda: convert_image(png, quality="abc"), IMG_INVALID_QUALITY, 400)


def test_image_convert_menolak_gambar_rusak() -> None:
    corrupted = b"\x89PNG\r\n\x1a\n" + b"xyz" * 50
    expect_image_error(lambda: convert_image(corrupted, target="jpeg"), IMG_IMAGE_UNREADABLE, 422)


def test_image_convert_menolak_ukuran_lewat_batas() -> None:
    expect_image_error(lambda: check_image_total_size(IMG_MAX_BYTES + 1), IMG_PAYLOAD_TOO_LARGE, 413)


# --- Uji logika Word Counter ------------------------------------------------
def test_word_count_logika_teks_normal() -> None:
    res = count_text("Halo dunia. Ini uji coba!")
    assert res.chars == 25
    assert res.chars_no_spaces == 21
    assert res.words == 5
    assert res.unique_words == 5
    assert res.sentences == 2
    assert res.paragraphs == 1
    assert res.lines == 1
    assert res.reading_minutes == 1
    assert res.speaking_minutes == 1
    assert res.longest_word == "dunia"
    # 'ini' dan 'uji' < 4 huruf, jadi tidak masuk top_words
    top_dict = {item["word"]: item["count"] for item in res.top_words}
    assert top_dict == {"halo": 1, "dunia": 1, "coba": 1}


def test_word_count_logika_paragraf_dan_baris() -> None:
    text = (
        "Paragraf pertama terdiri dari dua baris.\n"
        "Ini baris kedua pada paragraf pertama.\n\n"
        "Paragraf kedua hanya satu baris.\n\n\n"
        "Paragraf ketiga adalah penutup."
    )
    res = count_text(text)
    assert res.paragraphs == 3
    assert res.lines == 4
    assert res.sentences == 4


def test_word_count_logika_case_insensitive_dan_top_words() -> None:
    # "Kucing" ditulis dengan variasi kapital, stop words Indonesia ("dan", "di", "itu") diabaikan
    text = "Kucing makan ikan. kucing dan KUCING tidur di kasur itu! Ikan sangat lezat."
    res = count_text(text)
    assert res.words == 13
    # unique_words tidak peka huruf besar-kecil
    lower_set = {
        "kucing", "makan", "ikan", "dan", "tidur", "di", "kasur", "itu", "sangat", "lezat"
    }
    assert res.unique_words == len(lower_set)
    # top_words: 'kucing' 3 kali, 'ikan' 2 kali; stopword 'dan', 'di', 'itu' tidak muncul
    top_dict = {item["word"]: item["count"] for item in res.top_words}
    assert top_dict["kucing"] == 3
    assert top_dict["ikan"] == 2
    for sw in WC_STOP_WORDS:
        assert sw not in top_dict


def test_word_count_logika_waktu_baca_dan_bicara() -> None:
    # 250 kata: waktu baca ceil(250/200) = 2 menit, waktu bicara ceil(250/130) = 2 menit
    words_250 = " ".join(["kata"] * 250)
    res = count_text(words_250)
    assert res.words == 250
    assert res.reading_minutes == 2
    assert res.speaking_minutes == 2

    # 1 kata: minimal 1 menit
    res_one = count_text("Satu")
    assert res_one.words == 1
    assert res_one.reading_minutes == 1
    assert res_one.speaking_minutes == 1


def test_word_count_logika_kata_terpanjang_seri() -> None:
    # Bila ada beberapa kata dengan panjang sama, kata pertama yang ditemukan dipilih
    res = count_text("satu dua tiga")  # 'satu' dan 'tiga' sama-sama 4 huruf
    assert res.longest_word == "satu"


def test_word_count_logika_menolak_teks_kosong() -> None:
    expect_word_count_error(lambda: count_text(""), WC_NO_TEXT, 400)


def test_word_count_logika_menolak_hanya_spasi() -> None:
    expect_word_count_error(lambda: count_text("   \n\t  "), WC_NO_TEXT, 400)


def test_word_count_logika_menolak_terlalu_panjang() -> None:
    long_text = "a" * (WC_MAX_CHARS + 1)
    expect_word_count_error(lambda: count_text(long_text), WC_TOO_LONG, 413)


def test_word_count_logika_menolak_none() -> None:
    expect_word_count_error(lambda: count_text(None), WC_INVALID_REQUEST, 400)  # type: ignore[arg-type]



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


def test_http_image_convert_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/image/convert/limits")
    assert response.status_code == 200
    body = response.json()
    assert body["max_files"] == IMG_MAX_FILES
    assert body["max_bytes"] == IMG_MAX_BYTES
    assert body["max_total_mb"] == 15
    assert body["max_pixels"] == IMG_MAX_PIXELS
    assert body["targets"] == ["jpeg", "png", "webp"]
    assert body["target_labels"]["jpeg"] == "JPG"
    assert body["quality_min"] == 10
    assert body["quality_max"] == 100
    assert body["quality_default"] == 85
    assert response.headers["cache-control"] == "no-store"


def test_http_image_convert_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    png_data = make_image("PNG", size=(60, 60), color="magenta")
    response = client.post(
        "/api/image/convert",
        files=[("files", ("test.png", png_data, "image/png"))],
        data={"format": "jpeg", "quality": "80"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/jpeg")
    assert 'filename="hasil.jpg"' in response.headers["content-disposition"]
    assert response.headers["cache-control"].startswith("no-store")
    assert response.headers["x-input-format"] == "png"
    assert response.headers["x-output-format"] == "jpeg"
    assert response.headers["x-pixels"] == "3600"
    assert response.headers["x-total-bytes"] == str(len(response.content))
    assert "x-processing-ms" in response.headers
    assert response.content.startswith(b"\xff\xd8\xff")


def test_http_image_convert_tanpa_berkas_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/image/convert", files=[])
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_NO_FILES


def test_http_image_convert_dua_berkas_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    files = [
        ("files", ("a.png", make_image("PNG"), "image/png")),
        ("files", ("b.png", make_image("PNG"), "image/png")),
    ]
    response = client.post("/api/image/convert", files=files)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_TOO_MANY_FILES


def test_http_image_convert_bukan_gambar_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/image/convert",
        files=[("files", ("palsu.png", b"ini cuma teks", "image/png"))],
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_NOT_IMAGE


def test_http_image_convert_kualitas_tidak_valid_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/image/convert",
        files=[("files", ("test.png", make_image("PNG"), "image/png"))],
        data={"quality": "150"},
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_INVALID_QUALITY


def test_http_word_count_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/word-count/limits")
    assert response.status_code == 200
    body = response.json()
    assert body["processed_on"] == "server"
    assert body["max_chars"] == WC_MAX_CHARS
    assert body["max_bytes"] == WC_MAX_BYTES
    assert response.headers["cache-control"] == "no-store"


def test_http_word_count_teks_normal_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", data={"text": "Halo dunia. Ini uji coba!"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")

    # Respons sukses tidak memuat Cache-Control yang membolehkan cache
    cache = response.headers.get("cache-control", "")
    assert "no-store" in cache
    assert "no-cache" in cache
    assert response.headers.get("pragma") == "no-cache"

    # Header ringkas
    assert response.headers.get("x-char-count") == "25"
    assert response.headers.get("x-word-count") == "5"
    assert "x-processing-ms" in response.headers

    body = response.json()
    assert body["chars"] == 25
    assert body["chars_no_spaces"] == 21
    assert body["words"] == 5
    assert body["unique_words"] == 5
    assert body["sentences"] == 2
    assert body["paragraphs"] == 1
    assert body["lines"] == 1
    assert body["reading_minutes"] == 1
    assert body["speaking_minutes"] == 1
    assert body["longest_word"] == "dunia"


def test_http_word_count_paragraf_dan_baris() -> None:
    client = _test_client()
    if client is None:
        return
    text = (
        "Baris 1 paragraf 1\n"
        "Baris 2 paragraf 1\n\n"
        "Baris 3 paragraf 2\n\n\n"
        "Baris 4 paragraf 3"
    )
    response = client.post("/api/word-count", data={"text": text})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["paragraphs"] == 3
    assert body["lines"] == 4


def test_http_word_count_case_insensitive_dan_top_words() -> None:
    client = _test_client()
    if client is None:
        return
    text = "Mawar mawar MAWAR melati melati melati melati anggrek."
    response = client.post("/api/word-count", data={"text": text})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["unique_words"] == 3
    words = [item["word"] for item in body["top_words"]]
    assert words[0] == "melati"
    assert body["top_words"][0]["count"] == 4
    assert words[1] == "mawar"
    assert body["top_words"][1]["count"] == 3


def test_http_word_count_teks_kosong_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", data={"text": ""})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == WC_NO_TEXT


def test_http_word_count_teks_hanya_spasi_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", data={"text": "   \n\t  "})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == WC_NO_TEXT


def test_http_word_count_teks_terlalu_panjang_ditolak_413() -> None:
    client = _test_client()
    if client is None:
        return
    long_text = "x" * (WC_MAX_CHARS + 10)
    response = client.post("/api/word-count", data={"text": long_text})
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == WC_TOO_LONG


def test_http_word_count_bukan_multipart_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", json={"text": "Halo dunia"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == WC_INVALID_REQUEST


def test_http_word_count_field_text_hilang_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", data={})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] in (WC_INVALID_REQUEST, WC_NO_TEXT)


def test_http_word_count_cache_headers_tidak_membolehkan_cache() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", data={"text": "Uji cache header"})
    assert response.status_code == 200
    cache_control = response.headers.get("Cache-Control", "")
    assert "public" not in cache_control
    assert "max-age" not in cache_control
    assert "no-store" in cache_control
    assert "no-cache" in cache_control
    assert response.headers.get("Pragma") == "no-cache"



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

    # Word Count live lewat multipart/form-data
    boundary_wc = "----omnitoolswc"
    body_wc = (
        f"--{boundary_wc}\r\n"
        f'Content-Disposition: form-data; name="text"\r\n\r\n'
        f"Halo dunia. Ini uji coba!\r\n"
        f"--{boundary_wc}--\r\n"
    ).encode()
    req_wc = urllib.request.Request(
        base + "/api/word-count",
        data=body_wc,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary_wc}"},
    )
    with urllib.request.urlopen(req_wc, timeout=10) as resp:
        assert resp.status == 200
        wc_data = json.loads(resp.read().decode())
        assert wc_data["words"] == 5
        assert wc_data["chars"] == 25



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
