"""Logika kalkulator keramik lantai: fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
import math
import re
from typing import Any

# Batas operasional
MIN_PANJANG_M = 0.1
MAX_PANJANG_M = 100.0
MIN_LEBAR_M = 0.1
MAX_LEBAR_M = 100.0
MIN_LUAS_M2 = 0.1
MAX_LUAS_M2 = 2000.0

MIN_CUSTOM_CM = 5
MAX_CUSTOM_CM = 200

MIN_CADANGAN = 0
MAX_CADANGAN = 30
DEFAULT_CADANGAN = 5

MIN_ISI_DUS = 1
MAX_ISI_DUS = 60

MIN_HARGA_DUS = 0
MAX_HARGA_DUS = 100000000

MAX_KEPING = 200000

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
INVALID_NUMBER = "INVALID_NUMBER"
OUT_OF_RANGE = "OUT_OF_RANGE"
UNSUPPORTED_SIZE = "UNSUPPORTED_SIZE"
INVALID_CUSTOM_SIZE = "INVALID_CUSTOM_SIZE"
INVALID_CADANGAN = "INVALID_CADANGAN"
INVALID_ISI_DUS = "INVALID_ISI_DUS"
INVALID_HARGA = "INVALID_HARGA"
TOO_MANY_TILES = "TOO_MANY_TILES"


class KeramikError(ValueError):
    """Galat operasional kalkulator keramik dengan kode galat dan status HTTP."""

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


DAFTAR_UKURAN: list[dict[str, Any]] = [
    {"kode": "20x20", "label": "20 x 20 cm", "panjang_cm": 20, "lebar_cm": 20, "isi_dus": 25},
    {"kode": "25x25", "label": "25 x 25 cm", "panjang_cm": 25, "lebar_cm": 25, "isi_dus": 16},
    {"kode": "30x30", "label": "30 x 30 cm", "panjang_cm": 30, "lebar_cm": 30, "isi_dus": 11},
    {"kode": "40x40", "label": "40 x 40 cm", "panjang_cm": 40, "lebar_cm": 40, "isi_dus": 6},
    {"kode": "50x50", "label": "50 x 50 cm", "panjang_cm": 50, "lebar_cm": 50, "isi_dus": 4},
    {"kode": "60x60", "label": "60 x 60 cm", "panjang_cm": 60, "lebar_cm": 60, "isi_dus": 4},
    {"kode": "80x80", "label": "80 x 80 cm", "panjang_cm": 80, "lebar_cm": 80, "isi_dus": 3},
    {"kode": "30x60", "label": "30 x 60 cm", "panjang_cm": 30, "lebar_cm": 60, "isi_dus": 8},
    {"kode": "60x120", "label": "60 x 120 cm", "panjang_cm": 60, "lebar_cm": 120, "isi_dus": 2},
]

UKURAN_MAP: dict[str, dict[str, Any]] = {u["kode"]: u for u in DAFTAR_UKURAN}


def parse_decimal_number(val: Any, field_name: str) -> float:
    """Validasi dan konversi teks desimal meter atau m2 ke float.

    Hanya satu titik atau satu koma yang diizinkan sebagai tanda desimal.
    Spasi di tepi diabaikan.
    """
    if val is None:
        raise KeramikError(INVALID_REQUEST, f"Field '{field_name}' wajib diisi.", 400)

    if not isinstance(val, str):
        raise KeramikError(INVALID_REQUEST, f"Field '{field_name}' harus berupa teks string.", 400)

    cleaned = val.strip()
    if not cleaned:
        raise KeramikError(INVALID_NUMBER, f"Nilai '{field_name}' tidak boleh kosong.", 400)

    # Hanya titik atau koma sebagai tanda desimal
    dot_count = cleaned.count(".")
    comma_count = cleaned.count(",")
    if (dot_count + comma_count) > 1:
        raise KeramikError(
            INVALID_NUMBER,
            f"Format angka '{field_name}' tidak valid. Gunakan satu tanda titik atau koma desimal.",
            400,
        )

    normalized = cleaned.replace(",", ".")
    if not re.fullmatch(r"^\d+(\.\d+)?$", normalized):
        raise KeramikError(
            INVALID_NUMBER,
            f"Nilai '{field_name}' harus berupa angka positif yang valid.",
            400,
        )

    try:
        num = float(normalized)
    except ValueError:
        raise KeramikError(INVALID_NUMBER, f"Nilai '{field_name}' tidak dapat dibaca sebagai angka.", 400)

    if math.isnan(num) or math.isinf(num):
        raise KeramikError(INVALID_NUMBER, f"Nilai '{field_name}' bukan angka yang valid.", 400)

    return num


def parse_integer(
    val: Any,
    field_name: str,
    min_val: int,
    max_val: int,
    err_code: str,
) -> int:
    """Validasi dan parsing bilangan bulat positif dalam rentang tertentu."""
    if val is None:
        raise KeramikError(err_code, f"Field '{field_name}' wajib diisi.", 400)

    if isinstance(val, bool):
        raise KeramikError(err_code, f"Field '{field_name}' harus berupa bilangan bulat.", 400)

    s = str(val).strip()
    if not s:
        raise KeramikError(err_code, f"Field '{field_name}' tidak boleh kosong.", 400)

    # Cek apakah hanya memuat digit
    if not re.fullmatch(r"^\d+$", s):
        raise KeramikError(
            err_code,
            f"Field '{field_name}' harus berupa bilangan bulat antara {min_val} hingga {max_val}.",
            400,
        )

    try:
        num = int(s)
    except ValueError:
        raise KeramikError(
            err_code,
            f"Field '{field_name}' tidak dapat dibaca sebagai bilangan bulat.",
            400,
        )

    if num < min_val or num > max_val:
        raise KeramikError(
            err_code,
            f"Field '{field_name}' harus bernilai antara {min_val} hingga {max_val}.",
            400,
        )

    return num


def parse_harga(val: Any) -> int:
    """Validasi dan parsing harga rupiah per dus (0..100.000.000)."""
    if val is None:
        return 0

    if isinstance(val, bool):
        raise KeramikError(INVALID_HARGA, "Harga per dus harus berupa bilangan bulat rupiah.", 400)

    s = str(val).strip()
    if not s:
        return 0

    if s.startswith("-"):
        raise KeramikError(INVALID_HARGA, "Harga per dus tidak boleh bernilai negatif.", 400)

    # Bersihkan pemisah ribuan titik, koma, spasi bila ada
    s_clean = s.replace(".", "").replace(",", "").replace(" ", "")
    if not re.fullmatch(r"^\d+$", s_clean):
        raise KeramikError(
            INVALID_HARGA,
            "Harga per dus harus berupa bilangan bulat rupiah positif tanpa simbol atau huruf.",
            400,
        )

    try:
        num = int(s_clean)
    except ValueError:
        raise KeramikError(INVALID_HARGA, "Harga per dus tidak valid.", 400)

    if num < MIN_HARGA_DUS or num > MAX_HARGA_DUS:
        raise KeramikError(
            INVALID_HARGA,
            f"Harga per dus harus antara Rp {MIN_HARGA_DUS} hingga Rp {MAX_HARGA_DUS:,}.",
            400,
        )

    return num


def _ceil_div(numerator: Decimal, denominator: Decimal) -> int:
    """Pembagian pembulatan ke atas aman presisi menggunakan Decimal."""
    return int((numerator / denominator).to_integral_value(rounding=ROUND_CEILING))


def hitung_keramik(
    mode: Any,
    panjang: Any = None,
    lebar: Any = None,
    luas: Any = None,
    ukuran: Any = "40x40",
    ukuran_panjang: Any = None,
    ukuran_lebar: Any = None,
    cadangan: Any = DEFAULT_CADANGAN,
    isi_dus: Any = None,
    harga_dus: Any = None,
) -> dict[str, Any]:
    """Hitung kebutuhan keramik lantai murni di memori."""
    if mode is None:
        raise KeramikError(INVALID_REQUEST, "Field 'mode' wajib diisi.", 400)

    if not isinstance(mode, str):
        raise KeramikError(INVALID_REQUEST, "Field 'mode' harus berupa teks string.", 400)

    mode_norm = mode.strip().lower()
    if mode_norm not in ("ruangan", "luas"):
        raise KeramikError(
            UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak didukung. Pilih 'ruangan' atau 'luas'.",
            400,
        )

    # Validasi ukuran keramik
    if ukuran is None or not isinstance(ukuran, str):
        raise KeramikError(UNSUPPORTED_SIZE, "Pilih ukuran keramik yang tersedia atau 'kustom'.", 400)

    ukuran_norm = ukuran.strip().lower()
    if ukuran_norm != "kustom" and ukuran_norm not in UKURAN_MAP:
        daftar_str = ", ".join(UKURAN_MAP.keys())
        raise KeramikError(
            UNSUPPORTED_SIZE,
            f"Ukuran '{ukuran}' tidak didukung. Pilihan: {daftar_str}, atau 'kustom'.",
            400,
        )

    if ukuran_norm == "kustom":
        if ukuran_panjang is None or ukuran_lebar is None:
            raise KeramikError(
                INVALID_CUSTOM_SIZE,
                "Untuk ukuran kustom, 'ukuran_panjang' dan 'ukuran_lebar' wajib diisi.",
                400,
            )
        tile_w_cm = parse_integer(
            ukuran_panjang,
            "ukuran_panjang",
            MIN_CUSTOM_CM,
            MAX_CUSTOM_CM,
            INVALID_CUSTOM_SIZE,
        )
        tile_h_cm = parse_integer(
            ukuran_lebar,
            "ukuran_lebar",
            MIN_CUSTOM_CM,
            MAX_CUSTOM_CM,
            INVALID_CUSTOM_SIZE,
        )
        default_isi = None
    else:
        info_ukuran = UKURAN_MAP[ukuran_norm]
        tile_w_cm = info_ukuran["panjang_cm"]
        tile_h_cm = info_ukuran["lebar_cm"]
        default_isi = info_ukuran["isi_dus"]

    # Luas per keping dalam m2
    d_tile_w = Decimal(tile_w_cm)
    d_tile_h = Decimal(tile_h_cm)
    d_luas_keping = (d_tile_w * d_tile_h) / Decimal("10000")
    luas_keping_m2 = float(d_luas_keping)

    # Validasi cadangan
    if cadangan is None or (isinstance(cadangan, str) and not cadangan.strip()):
        cadangan_persen = DEFAULT_CADANGAN
    else:
        cadangan_persen = parse_integer(
            cadangan,
            "cadangan",
            MIN_CADANGAN,
            MAX_CADANGAN,
            INVALID_CADANGAN,
        )

    # Validasi isi dus
    if isi_dus is None or (isinstance(isi_dus, str) and not isi_dus.strip()):
        if default_isi is not None:
            isi_dus_final = default_isi
            isi_dus_perkiraan = False
        else:
            isi_dus_final = _ceil_div(Decimal("1"), d_luas_keping)
            isi_dus_perkiraan = True
    else:
        isi_dus_final = parse_integer(
            isi_dus,
            "isi_dus",
            MIN_ISI_DUS,
            MAX_ISI_DUS,
            INVALID_ISI_DUS,
        )
        isi_dus_perkiraan = False

    # Validasi harga dus
    harga_final = parse_harga(harga_dus)

    # Perhitungan berdasarkan mode
    kolom: int | None = None
    baris: int | None = None
    orientasi: str | None = None

    if mode_norm == "ruangan":
        p_m = parse_decimal_number(panjang, "panjang")
        l_m = parse_decimal_number(lebar, "lebar")

        if p_m < MIN_PANJANG_M or p_m > MAX_PANJANG_M:
            raise KeramikError(
                OUT_OF_RANGE,
                f"Panjang ruangan ({p_m} m) harus antara {MIN_PANJANG_M} hingga {MAX_PANJANG_M} meter.",
                400,
            )

        if l_m < MIN_LEBAR_M or l_m > MAX_LEBAR_M:
            raise KeramikError(
                OUT_OF_RANGE,
                f"Lebar ruangan ({l_m} m) harus antara {MIN_LEBAR_M} hingga {MAX_LEBAR_M} meter.",
                400,
            )

        d_panjang_cm = Decimal(str(p_m)) * Decimal("100")
        d_lebar_cm = Decimal(str(l_m)) * Decimal("100")

        # Orientasi 1: tile_w_cm searah panjang ruangan, tile_h_cm searah lebar
        kolom_1 = _ceil_div(d_panjang_cm, d_tile_w)
        baris_1 = _ceil_div(d_lebar_cm, d_tile_h)
        keping_1 = kolom_1 * baris_1

        # Orientasi 2: tile_h_cm searah panjang ruangan, tile_w_cm searah lebar
        kolom_2 = _ceil_div(d_panjang_cm, d_tile_h)
        baris_2 = _ceil_div(d_lebar_cm, d_tile_w)
        keping_2 = kolom_2 * baris_2

        if keping_1 <= keping_2:
            keping_dasar = keping_1
            kolom = kolom_1
            baris = baris_1
            orientasi = f"{tile_w_cm} cm searah panjang ruangan"
        else:
            keping_dasar = keping_2
            kolom = kolom_2
            baris = baris_2
            orientasi = f"{tile_h_cm} cm searah panjang ruangan"

        luas_m2 = round(p_m * l_m, 2)
        perkiraan_berbasis_luas = False

    else:  # mode_norm == "luas"
        luas_val = parse_decimal_number(luas, "luas")
        if luas_val < MIN_LUAS_M2 or luas_val > MAX_LUAS_M2:
            raise KeramikError(
                OUT_OF_RANGE,
                f"Luas lantai ({luas_val} m²) harus antara {MIN_LUAS_M2} hingga {MAX_LUAS_M2} meter persegi.",
                400,
            )

        d_luas = Decimal(str(luas_val))
        luas_m2 = round(luas_val, 2)
        keping_dasar = _ceil_div(d_luas, d_luas_keping)
        perkiraan_berbasis_luas = True
        orientasi = None

    # Batas maksimum keping
    if keping_dasar > MAX_KEPING:
        raise KeramikError(
            TOO_MANY_TILES,
            f"Kebutuhan dasar ({keping_dasar:,} keping) melebihi batas maksimum {MAX_KEPING:,} keping. Periksa kembali ukuran atau pilih ukuran keramik yang lebih besar.",
            413,
        )

    # Perhitungan lanjutan
    # keping_cadangan = ceil(keping_dasar * (1 + cadangan/100))
    d_keping_dasar = Decimal(keping_dasar)
    d_cadangan_multiplier = Decimal("1") + (Decimal(cadangan_persen) / Decimal("100"))
    keping_cadangan = _ceil_div(d_keping_dasar * d_cadangan_multiplier, Decimal("1"))

    # dus = ceil(keping_cadangan / isi_dus)
    dus = _ceil_div(Decimal(keping_cadangan), Decimal(isi_dus_final))

    # keping_dibeli = dus * isi_dus
    keping_dibeli = dus * isi_dus_final

    # sisa_keping = keping_dibeli - keping_dasar
    sisa_keping = keping_dibeli - keping_dasar

    # sisa_persen = sisa_keping / keping_dasar * 100 (1 desimal)
    sisa_persen = round((sisa_keping / keping_dasar) * 100.0, 1) if keping_dasar > 0 else 0.0

    # Perkiraan biaya
    if harga_final > 0:
        biaya_total: int | None = dus * harga_final
        biaya_per_m2: int | None = round(biaya_total / luas_m2) if luas_m2 > 0 else 0
        harga_dus_out: int | None = harga_final
    else:
        biaya_total = None
        biaya_per_m2 = None
        harga_dus_out = None

    # Catatan informatif
    catatan: list[str] = []
    if cadangan_persen > 0:
        catatan.append(
            f"Cadangan {cadangan_persen}% disiapkan untuk potongan sudut, tepi dinding, dan risiko keping pecah saat pemasangan."
        )
    else:
        catatan.append(
            "Perhitungan tanpa cadangan keping (0%). Sebaiknya siapkan cadangan untuk mengantisipasi potongan tepi dan risiko pecah."
        )

    if perkiraan_berbasis_luas:
        catatan.append(
            "Perhitungan berbasis perkiraan luas lantai tanpa denah ruangan. Kebutuhan potongan tepi sebenarnya bisa memerlukan keping tambahan."
        )

    if isi_dus_perkiraan:
        catatan.append(
            f"Isi per dus memakai perkiraan standar ({isi_dus_final} keping/dus). Pastikan memeriksa jumlah keping per kemasan merek yang kamu beli."
        )

    return {
        "mode": mode_norm,
        "luas_m2": luas_m2,
        "ukuran": {
            "panjang_cm": tile_w_cm,
            "lebar_cm": tile_h_cm,
            "luas_keping_m2": round(luas_keping_m2, 4),
        },
        "orientasi": orientasi,
        "perkiraan_berbasis_luas": perkiraan_berbasis_luas,
        "kolom": kolom,
        "baris": baris,
        "keping_dasar": keping_dasar,
        "cadangan_persen": cadangan_persen,
        "keping_cadangan": keping_cadangan,
        "isi_dus": isi_dus_final,
        "isi_dus_perkiraan": isi_dus_perkiraan,
        "dus": dus,
        "keping_dibeli": keping_dibeli,
        "sisa_keping": sisa_keping,
        "sisa_persen": sisa_persen,
        "harga_dus": harga_dus_out,
        "biaya_total": biaya_total,
        "biaya_per_m2": biaya_per_m2,
        "catatan": catatan,
    }


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional dan pilihan ukuran keramik."""
    return {
        "modes": [
            {"value": "ruangan", "label": "Ukuran ruangan (panjang x lebar)"},
            {"value": "luas", "label": "Luas lantai (m²)"},
        ],
        "ukuran_pilihan": [
            {
                "kode": u["kode"],
                "label": u["label"],
                "panjang_cm": u["panjang_cm"],
                "lebar_cm": u["lebar_cm"],
                "isi_dus": u["isi_dus"],
            }
            for u in DAFTAR_UKURAN
        ] + [
            {
                "kode": "kustom",
                "label": "Kustom (atur sendiri cm)",
                "panjang_cm": None,
                "lebar_cm": None,
                "isi_dus": None,
            }
        ],
        "rentang_cadangan": {
            "min": MIN_CADANGAN,
            "max": MAX_CADANGAN,
            "bawaan": DEFAULT_CADANGAN,
            "satuan": "%",
        },
        "rentang_isi_dus": {
            "min": MIN_ISI_DUS,
            "max": MAX_ISI_DUS,
            "satuan": "keping",
        },
        "rentang_harga_dus": {
            "min": MIN_HARGA_DUS,
            "max": MAX_HARGA_DUS,
            "satuan": "rupiah",
        },
        "batas_dimensi": {
            "panjang_m": {"min": MIN_PANJANG_M, "max": MAX_PANJANG_M, "satuan": "m"},
            "lebar_m": {"min": MIN_LEBAR_M, "max": MAX_LEBAR_M, "satuan": "m"},
            "luas_m2": {"min": MIN_LUAS_M2, "max": MAX_LUAS_M2, "satuan": "m²"},
            "kustom_cm": {"min": MIN_CUSTOM_CM, "max": MAX_CUSTOM_CM, "satuan": "cm"},
        },
        "batas_keping": MAX_KEPING,
        "processed_on": "server",
        "note": "Angka diproses di memori lalu dibuang, tidak disimpan di disk.",
    }
