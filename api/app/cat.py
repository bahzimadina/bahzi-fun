"""Logika kalkulator kebutuhan cat dinding: fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
import math
import re
from typing import Any

# Batas operasional
MIN_PANJANG_M = 0.5
MAX_PANJANG_M = 50.0
MIN_LEBAR_M = 0.5
MAX_LEBAR_M = 50.0
MIN_TINGGI_M = 1.0
MAX_TINGGI_M = 10.0
MIN_LUAS_M2 = 1.0
MAX_LUAS_M2 = 2000.0

MIN_BUKAAN = 0
MAX_BUKAAN = 20
LUAS_PINTU_M2 = 1.8
LUAS_JENDELA_M2 = 1.2

MIN_LAPIS = 1
MAX_LAPIS = 3
DEFAULT_LAPIS = 2

MIN_DAYA_SEBAR = 6.0
MAX_DAYA_SEBAR = 14.0
DEFAULT_DAYA_SEBAR = 10.0

KEMASAN_STANDAR: list[float] = [2.5, 5.0, 20.0]
DEFAULT_KEMASAN = 5.0
MIN_KEMASAN_KUSTOM = 0.5
MAX_KEMASAN_KUSTOM = 50.0

MIN_HARGA = 0
MAX_HARGA = 100000000

MAX_BODY_BYTES = 64 * 1024

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
INVALID_NUMBER = "INVALID_NUMBER"
OUT_OF_RANGE = "OUT_OF_RANGE"
INVALID_LAPIS = "INVALID_LAPIS"
INVALID_DAYA_SEBAR = "INVALID_DAYA_SEBAR"
INVALID_KEMASAN = "INVALID_KEMASAN"
INVALID_HARGA = "INVALID_HARGA"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class CatError(ValueError):
    """Galat operasional kalkulator cat dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        err = {"code": self.code, "message": self.message}
        return {"error": err, "detail": err}


def parse_decimal_number(
    val: Any,
    field_name: str,
    min_val: float | None = None,
    max_val: float | None = None,
) -> float:
    """Validasi dan konversi nilai angka desimal ke float.

    Mendukung string dengan tanda desimal titik atau koma, serta nilai numeric (int/float).
    """
    if val is None:
        raise CatError(INVALID_REQUEST, f"Field '{field_name}' wajib diisi.", 400)

    if isinstance(val, bool):
        raise CatError(INVALID_NUMBER, f"Nilai '{field_name}' harus berupa angka valid.", 400)

    if isinstance(val, (int, float)):
        num = float(val)
        if math.isnan(num) or math.isinf(num):
            raise CatError(INVALID_NUMBER, f"Nilai '{field_name}' bukan angka yang valid.", 400)
    elif isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            raise CatError(INVALID_NUMBER, f"Nilai '{field_name}' tidak boleh kosong.", 400)

        dot_count = cleaned.count(".")
        comma_count = cleaned.count(",")
        if (dot_count + comma_count) > 1:
            raise CatError(
                INVALID_NUMBER,
                f"Format angka '{field_name}' tidak valid. Gunakan satu tanda titik atau koma desimal.",
                400,
            )

        normalized = cleaned.replace(",", ".")
        if not re.fullmatch(r"^\d+(\.\d+)?$", normalized):
            raise CatError(
                INVALID_NUMBER,
                f"Nilai '{field_name}' harus berupa angka positif yang valid.",
                400,
            )

        try:
            num = float(normalized)
        except ValueError:
            raise CatError(INVALID_NUMBER, f"Nilai '{field_name}' tidak dapat dibaca sebagai angka.", 400)

        if math.isnan(num) or math.isinf(num):
            raise CatError(INVALID_NUMBER, f"Nilai '{field_name}' bukan angka yang valid.", 400)
    else:
        raise CatError(INVALID_REQUEST, f"Field '{field_name}' harus berupa teks string atau angka.", 400)

    if min_val is not None and max_val is not None:
        if num < min_val or num > max_val:
            raise CatError(
                OUT_OF_RANGE,
                f"Nilai '{field_name}' ({num}) harus antara {min_val} hingga {max_val}.",
                400,
            )

    return num


def parse_integer(
    val: Any,
    field_name: str,
    min_val: int,
    max_val: int,
    err_code: str = OUT_OF_RANGE,
    default: int | None = None,
) -> int:
    """Validasi dan parsing bilangan bulat positif dalam rentang tertentu."""
    if val is None or (isinstance(val, str) and not val.strip()):
        if default is not None:
            return default
        raise CatError(INVALID_REQUEST, f"Field '{field_name}' wajib diisi.", 400)

    if isinstance(val, bool):
        raise CatError(INVALID_NUMBER, f"Field '{field_name}' harus berupa bilangan bulat.", 400)

    if isinstance(val, int):
        num = val
    elif isinstance(val, float):
        if val.is_integer():
            num = int(val)
        else:
            raise CatError(
                INVALID_NUMBER,
                f"Field '{field_name}' harus berupa bilangan bulat.",
                400,
            )
    elif isinstance(val, str):
        s = val.strip()
        if not re.fullmatch(r"^\d+$", s):
            raise CatError(
                INVALID_NUMBER,
                f"Field '{field_name}' harus berupa bilangan bulat antara {min_val} hingga {max_val}.",
                400,
            )
        try:
            num = int(s)
        except ValueError:
            raise CatError(
                INVALID_NUMBER,
                f"Field '{field_name}' tidak dapat dibaca sebagai bilangan bulat.",
                400,
            )
    else:
        raise CatError(INVALID_REQUEST, f"Field '{field_name}' tidak valid.", 400)

    if num < min_val or num > max_val:
        raise CatError(
            err_code,
            f"Field '{field_name}' harus bernilai antara {min_val} hingga {max_val}.",
            400,
        )

    return num


def parse_lapis(val: Any) -> int:
    """Validasi jumlah lapisan cat (1..3, default 2)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return DEFAULT_LAPIS

    if isinstance(val, bool):
        raise CatError(INVALID_LAPIS, "Jumlah lapisan cat harus berupa bilangan bulat antara 1 hingga 3 lapis.", 400)

    try:
        num = parse_integer(val, "lapis", MIN_LAPIS, MAX_LAPIS, err_code=INVALID_LAPIS)
    except CatError as exc:
        if exc.code in (INVALID_NUMBER, OUT_OF_RANGE):
            raise CatError(
                INVALID_LAPIS,
                "Jumlah lapisan cat harus berupa bilangan bulat antara 1 hingga 3 lapis.",
                400,
            )
        raise
    return num


def parse_daya_sebar(val: Any) -> float:
    """Validasi daya sebar cat (6..14 m2/liter per lapis, default 10)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return DEFAULT_DAYA_SEBAR

    try:
        num = parse_decimal_number(val, "daya_sebar", min_val=MIN_DAYA_SEBAR, max_val=MAX_DAYA_SEBAR)
    except CatError as exc:
        raise CatError(
            INVALID_DAYA_SEBAR,
            f"Daya sebar cat harus antara {MIN_DAYA_SEBAR} hingga {MAX_DAYA_SEBAR} m²/liter per lapis.",
            400,
        )
    return num


def parse_kemasan(kemasan: Any, kemasan_kustom: Any = None) -> tuple[float, bool]:
    """Validasi ukuran kemasan kaleng cat (2.5, 5, 20 atau kustom 0.5..50).

    Mengembalikan (kemasan_liter, is_kustom).
    """
    if kemasan is None or (isinstance(kemasan, str) and not kemasan.strip()):
        return DEFAULT_KEMASAN, False

    if isinstance(kemasan, str) and kemasan.strip().lower() == "kustom":
        if kemasan_kustom is None or (isinstance(kemasan_kustom, str) and not kemasan_kustom.strip()):
            raise CatError(
                INVALID_KEMASAN,
                "Untuk kemasan kustom, ukuran kemasan wajib diisi antara 0.5 hingga 50 liter.",
                400,
            )
        try:
            val_kustom = parse_decimal_number(
                kemasan_kustom,
                "kemasan_kustom",
                min_val=MIN_KEMASAN_KUSTOM,
                max_val=MAX_KEMASAN_KUSTOM,
            )
        except CatError:
            raise CatError(
                INVALID_KEMASAN,
                f"Ukuran kemasan kustom harus antara {MIN_KEMASAN_KUSTOM} hingga {MAX_KEMASAN_KUSTOM} liter.",
                400,
            )
        return val_kustom, True

    # Jika kemasan berupa string/angka standar atau angka kustom
    try:
        val_num = parse_decimal_number(kemasan, "kemasan")
    except CatError:
        raise CatError(
            INVALID_KEMASAN,
            "Pilihan kemasan tidak valid. Pilih 2.5, 5, 20 liter, atau kustom.",
            400,
        )

    # Cek apakah cocok dengan ukuran standar
    for std in KEMASAN_STANDAR:
        if abs(val_num - std) < 1e-6:
            return std, False

    # Jika angka lain diberikan langsung, cek apakah berada dalam rentang kustom yang diizinkan
    if MIN_KEMASAN_KUSTOM <= val_num <= MAX_KEMASAN_KUSTOM:
        return val_num, True

    raise CatError(
        INVALID_KEMASAN,
        f"Ukuran kemasan harus salah satu dari 2.5, 5, 20 liter, atau kustom antara {MIN_KEMASAN_KUSTOM} hingga {MAX_KEMASAN_KUSTOM} liter.",
        400,
    )


def parse_harga(val: Any) -> int | None:
    """Validasi dan parsing harga rupiah per kaleng (0..100.000.000)."""
    if val is None:
        return None

    if isinstance(val, bool):
        raise CatError(INVALID_HARGA, "Harga per kaleng harus berupa bilangan bulat rupiah.", 400)

    s = str(val).strip()
    if not s:
        return None

    if s.startswith("-"):
        raise CatError(INVALID_HARGA, "Harga per kaleng tidak boleh bernilai negatif.", 400)

    # Bersihkan pemisah ribuan titik, koma, spasi bila ada
    s_clean = s.replace(".", "").replace(",", "").replace(" ", "")
    if not re.fullmatch(r"^\d+$", s_clean):
        raise CatError(
            INVALID_HARGA,
            "Harga per kaleng harus berupa bilangan bulat rupiah positif tanpa simbol atau huruf.",
            400,
        )

    try:
        num = int(s_clean)
    except ValueError:
        raise CatError(INVALID_HARGA, "Harga per kaleng tidak valid.", 400)

    if num < MIN_HARGA or num > MAX_HARGA:
        raise CatError(
            INVALID_HARGA,
            f"Harga per kaleng harus antara Rp {MIN_HARGA} hingga Rp {MAX_HARGA:,}.",
            400,
        )

    return num


def hitung_cat(
    mode: Any,
    panjang: Any = None,
    lebar: Any = None,
    tinggi: Any = None,
    luas_dinding: Any = None,
    pintu: Any = 0,
    jendela: Any = 0,
    lapis: Any = DEFAULT_LAPIS,
    daya_sebar: Any = DEFAULT_DAYA_SEBAR,
    kemasan: Any = DEFAULT_KEMASAN,
    kemasan_kustom: Any = None,
    harga: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Hitung kebutuhan cat dinding murni di memori."""
    if mode is None:
        raise CatError(INVALID_REQUEST, "Field 'mode' wajib diisi.", 400)

    if not isinstance(mode, str):
        raise CatError(INVALID_REQUEST, "Field 'mode' harus berupa teks string.", 400)

    mode_norm = mode.strip().lower()
    if mode_norm not in ("ruangan", "luas"):
        raise CatError(
            UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak didukung. Pilih 'ruangan' atau 'luas'.",
            400,
        )

    # Parsing parameter bersama
    lapis_val = parse_lapis(lapis)
    daya_sebar_val = parse_daya_sebar(daya_sebar)
    kemasan_liter, is_kustom = parse_kemasan(kemasan, kemasan_kustom)
    harga_val = parse_harga(harga)

    if mode_norm == "ruangan":
        p_m = parse_decimal_number(panjang, "panjang", MIN_PANJANG_M, MAX_PANJANG_M)
        l_m = parse_decimal_number(lebar, "lebar", MIN_LEBAR_M, MAX_LEBAR_M)
        t_m = parse_decimal_number(tinggi, "tinggi", MIN_TINGGI_M, MAX_TINGGI_M)

        pintu_val = parse_integer(pintu, "pintu", MIN_BUKAAN, MAX_BUKAAN, default=0)
        jendela_val = parse_integer(jendela, "jendela", MIN_BUKAAN, MAX_BUKAAN, default=0)

        d_panjang = Decimal(str(p_m))
        d_lebar = Decimal(str(l_m))
        d_tinggi = Decimal(str(t_m))

        # Keliling = 2 * (panjang + lebar)
        d_keliling = Decimal("2") * (d_panjang + d_lebar)
        # Luas kotor = keliling * tinggi
        d_luas_kotor = d_keliling * d_tinggi

        # Luas bukaan = pintu * 1.8 + jendela * 1.2
        d_luas_bukaan = (Decimal(pintu_val) * Decimal(str(LUAS_PINTU_M2))) + (
            Decimal(jendela_val) * Decimal(str(LUAS_JENDELA_M2))
        )

        # Luas dinding bersih = luas kotor - luas bukaan
        d_luas_dinding = d_luas_kotor - d_luas_bukaan

        if d_luas_dinding <= Decimal("0"):
            raise CatError(
                OUT_OF_RANGE,
                "Luas dinding setelah dikurangi bukaan pintu dan jendela harus lebih besar dari 0 m².",
                400,
            )

        if d_luas_dinding > Decimal(str(MAX_LUAS_M2)):
            raise CatError(
                OUT_OF_RANGE,
                f"Luas dinding ({float(d_luas_dinding):.2f} m²) melebihi batas maksimum {MAX_LUAS_M2:,} m².",
                400,
            )

        luas_kotor_m2 = round(float(d_luas_kotor), 2)
        luas_bukaan_m2 = round(float(d_luas_bukaan), 2)
        luas_dinding_m2 = round(float(d_luas_dinding), 2)

    else:  # mode_norm == "luas"
        luas_val = parse_decimal_number(luas_dinding, "luas_dinding", MIN_LUAS_M2, MAX_LUAS_M2)
        d_luas_dinding = Decimal(str(luas_val))
        luas_dinding_m2 = round(float(d_luas_dinding), 2)
        luas_kotor_m2 = luas_dinding_m2
        luas_bukaan_m2 = 0.0

    # Perhitungan liter cat
    d_daya_sebar = Decimal(str(daya_sebar_val))
    d_lapis = Decimal(lapis_val)
    d_kemasan = Decimal(str(kemasan_liter))

    # liter_per_lapis = luas_dinding / daya_sebar
    d_liter_per_lapis = d_luas_dinding / d_daya_sebar
    # liter_total = liter_per_lapis * lapis
    d_liter_total = d_liter_per_lapis * d_lapis

    # kaleng = ceil(liter_total / kemasan)
    kaleng = int((d_liter_total / d_kemasan).to_integral_value(rounding=ROUND_CEILING))
    if kaleng < 1:
        kaleng = 1

    d_liter_dibeli = Decimal(kaleng) * d_kemasan
    d_sisa_liter = d_liter_dibeli - d_liter_total
    if d_sisa_liter < Decimal("0"):
        d_sisa_liter = Decimal("0")

    # Pembulatan keluaran
    liter_per_lapis_out = round(float(d_liter_per_lapis), 1)
    liter_total_out = round(float(d_liter_total), 1)
    kemasan_liter_out = round(float(d_kemasan), 1)
    liter_dibeli_out = round(float(d_liter_dibeli), 1)
    sisa_liter_out = round(float(d_sisa_liter), 1)

    # Biaya
    if harga_val is not None:
        biaya_total = kaleng * harga_val
        biaya_per_m2 = round(biaya_total / luas_dinding_m2) if luas_dinding_m2 > 0 else 0
        harga_kaleng_out = harga_val
    else:
        biaya_total = None
        biaya_per_m2 = None
        harga_kaleng_out = None

    # Catatan informatif
    catatan = [
        "Daya sebar standar cat tembok 10–12 m²/liter per lapis tergantung merek, kekentalan cat, dan porositas dinding.",
        "Jumlah kaleng dibulatkan ke atas ke ukuran kemasan utuh terdekat.",
        "Perhitungan hanya mencakup dinding ruangan, belum termasuk plafon, lis, atau kusen pintu/jendela.",
    ]
    if mode_norm == "luas":
        catatan.append(
            "Perhitungan menggunakan luas dinding langsung tanpa memperhitungkan bukaan pintu atau jendela."
        )
    if is_kustom:
        catatan.append(
            f"Ukuran kemasan cat menggunakan nilai kustom ({kemasan_liter_out} liter)."
        )

    return {
        "mode": mode_norm,
        "luas_dinding_m2": luas_dinding_m2,
        "luas_kotor_m2": luas_kotor_m2,
        "luas_bukaan_m2": luas_bukaan_m2,
        "lapis": lapis_val,
        "daya_sebar": daya_sebar_val,
        "liter_per_lapis": liter_per_lapis_out,
        "liter_total": liter_total_out,
        "kemasan_liter": kemasan_liter_out,
        "kaleng": kaleng,
        "liter_dibeli": liter_dibeli_out,
        "sisa_liter": sisa_liter_out,
        "harga_kaleng": harga_kaleng_out,
        "biaya_total": biaya_total,
        "biaya_per_m2": biaya_per_m2,
        "catatan": catatan,
    }


def limits_payload() -> dict[str, Any]:
    """Mengembalikan batas operasional, pilihan kemasan, dan nilai bawaan kalkulator cat."""
    return {
        "modes": [
            {"value": "ruangan", "label": "Ukuran ruangan (panjang x lebar x tinggi)"},
            {"value": "luas", "label": "Luas dinding bersih (m²)"},
        ],
        "kemasan_pilihan": [
            {"kode": "2.5", "label": "2,5 Liter (kaleng kecil)", "liter": 2.5},
            {"kode": "5", "label": "5 Liter (galon)", "liter": 5.0},
            {"kode": "20", "label": "20 Liter (pail/ember besar)", "liter": 20.0},
            {"kode": "kustom", "label": "Kustom (atur sendiri liter)", "liter": None},
        ],
        "rentang_lapis": {
            "min": MIN_LAPIS,
            "max": MAX_LAPIS,
            "bawaan": DEFAULT_LAPIS,
            "satuan": "lapis",
        },
        "rentang_daya_sebar": {
            "min": MIN_DAYA_SEBAR,
            "max": MAX_DAYA_SEBAR,
            "bawaan": DEFAULT_DAYA_SEBAR,
            "satuan": "m²/liter",
        },
        "rentang_kemasan_kustom": {
            "min": MIN_KEMASAN_KUSTOM,
            "max": MAX_KEMASAN_KUSTOM,
            "satuan": "liter",
        },
        "rentang_harga": {
            "min": MIN_HARGA,
            "max": MAX_HARGA,
            "satuan": "rupiah",
        },
        "batas_dimensi": {
            "panjang_m": {"min": MIN_PANJANG_M, "max": MAX_PANJANG_M, "satuan": "m"},
            "lebar_m": {"min": MIN_LEBAR_M, "max": MAX_LEBAR_M, "satuan": "m"},
            "tinggi_m": {"min": MIN_TINGGI_M, "max": MAX_TINGGI_M, "satuan": "m"},
            "luas_dinding_m2": {"min": MIN_LUAS_M2, "max": MAX_LUAS_M2, "satuan": "m²"},
            "pintu": {"min": MIN_BUKAAN, "max": MAX_BUKAAN, "satuan": "unit"},
            "jendela": {"min": MIN_BUKAAN, "max": MAX_BUKAAN, "satuan": "unit"},
        },
        "max_body_bytes": MAX_BODY_BYTES,
        "processed_on": "server",
        "note": "Angka diproses di memori lalu dibuang, tidak disimpan di disk.",
    }
