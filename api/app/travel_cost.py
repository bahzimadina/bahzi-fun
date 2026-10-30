"""Logika kalkulator hitung biaya perjalanan: fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import re
from typing import Any

# Batas operasional
MIN_JARAK = Decimal("0.1")
MAX_JARAK = Decimal("20000")

MIN_KONSUMSI = Decimal("1")
MAX_KONSUMSI = Decimal("100")
DEFAULT_KONSUMSI = Decimal("12")

MIN_HARGA_BBM = Decimal("1000")
MAX_HARGA_BBM = Decimal("100000")

MIN_PENUMPANG = 1
MAX_PENUMPANG = 50
DEFAULT_PENUMPANG = 1

MIN_BIAYA_LAIN = Decimal("0")
MAX_BIAYA_LAIN = Decimal("100000000")
DEFAULT_BIAYA_LAIN = Decimal("0")

MAX_INPUT_LENGTH = 40
MAX_BODY_BYTES = 64 * 1024

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
INVALID_NUMBER = "INVALID_NUMBER"
INVALID_JARAK = "INVALID_JARAK"
INVALID_KONSUMSI = "INVALID_KONSUMSI"
INVALID_HARGA = "INVALID_HARGA"
INVALID_PENUMPANG = "INVALID_PENUMPANG"
INVALID_BIAYA_LAIN = "INVALID_BIAYA_LAIN"
INVALID_BOOLEAN = "INVALID_BOOLEAN"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class TravelCostError(ValueError):
    """Galat operasional kalkulator biaya perjalanan dengan kode galat dan status HTTP."""

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


def parse_jarak(val: Any) -> Decimal:
    """Validasi dan parsing jarak perjalanan dalam kilometer (0,1 .. 20.000)."""
    if val is None:
        raise TravelCostError(
            INVALID_JARAK,
            "Field 'jarak' wajib diisi. Masukkan jarak antara 0,1 hingga 20.000 km.",
            400,
        )

    if isinstance(val, bool):
        raise TravelCostError(
            INVALID_JARAK,
            "Nilai 'jarak' harus berupa angka, bukan boolean.",
            400,
        )

    if isinstance(val, (int, float, Decimal)):
        s = str(val).strip()
    elif isinstance(val, str):
        s = val.strip()
    else:
        raise TravelCostError(
            INVALID_REQUEST,
            "Field 'jarak' harus berupa string atau angka.",
            400,
        )

    if not s:
        raise TravelCostError(
            INVALID_JARAK,
            "Field 'jarak' tidak boleh kosong. Masukkan jarak antara 0,1 hingga 20.000 km.",
            400,
        )

    if len(s) > MAX_INPUT_LENGTH:
        raise TravelCostError(
            INVALID_NUMBER,
            "Masukan 'jarak' melebihi batas 40 karakter.",
            400,
        )

    if "," in s:
        s_clean = s.replace(".", "").replace(" ", "").replace(",", ".")
    else:
        if re.fullmatch(r"^\d{1,2}\.\d{3}$", s):
            s_clean = s.replace(".", "")
        else:
            s_clean = s.replace(" ", "")

    if not re.fullmatch(r"^\d+(\.\d+)?$", s_clean):
        raise TravelCostError(
            INVALID_JARAK,
            "Nilai 'jarak' harus berupa angka positif yang valid. Contoh: 120 atau 12,5.",
            400,
        )

    try:
        num = Decimal(s_clean)
    except Exception:
        raise TravelCostError(
            INVALID_JARAK,
            "Nilai 'jarak' tidak dapat dibaca sebagai angka.",
            400,
        )

    if num < MIN_JARAK or num > MAX_JARAK:
        raise TravelCostError(
            INVALID_JARAK,
            "Nilai 'jarak' harus bernilai antara 0,1 hingga 20.000 km.",
            400,
        )

    return num


def parse_pulang_pergi(val: Any) -> bool:
    """Validasi dan parsing flag pulang-pergi (bawaan False)."""
    if val is None:
        return False

    if isinstance(val, bool):
        return val

    s = str(val).strip().lower()
    if not s:
        return False

    if len(s) > MAX_INPUT_LENGTH:
        raise TravelCostError(
            INVALID_NUMBER,
            "Masukan 'pulang_pergi' melebihi batas 40 karakter.",
            400,
        )

    if s in ("true", "1"):
        return True
    if s in ("false", "0"):
        return False

    raise TravelCostError(
        INVALID_BOOLEAN,
        "Field 'pulang_pergi' harus bernilai 'true' atau 'false'.",
        400,
    )


def parse_konsumsi(val: Any) -> Decimal:
    """Validasi dan parsing konsumsi BBM (1 .. 100 km/liter)."""
    if val is None:
        raise TravelCostError(
            INVALID_KONSUMSI,
            "Field 'konsumsi' wajib diisi. Masukkan konsumsi BBM antara 1 hingga 100 km/liter.",
            400,
        )

    if isinstance(val, bool):
        raise TravelCostError(
            INVALID_KONSUMSI,
            "Nilai 'konsumsi' harus berupa angka, bukan boolean.",
            400,
        )

    if isinstance(val, (int, float, Decimal)):
        s = str(val).strip()
    elif isinstance(val, str):
        s = val.strip()
    else:
        raise TravelCostError(
            INVALID_REQUEST,
            "Field 'konsumsi' harus berupa string atau angka.",
            400,
        )

    if not s:
        raise TravelCostError(
            INVALID_KONSUMSI,
            "Field 'konsumsi' tidak boleh kosong. Masukkan konsumsi BBM antara 1 hingga 100 km/liter.",
            400,
        )

    if len(s) > MAX_INPUT_LENGTH:
        raise TravelCostError(
            INVALID_NUMBER,
            "Masukan 'konsumsi' melebihi batas 40 karakter.",
            400,
        )

    s_clean = s.replace(" ", "").replace(",", ".")

    if not re.fullmatch(r"^\d+(\.\d+)?$", s_clean):
        raise TravelCostError(
            INVALID_KONSUMSI,
            "Nilai 'konsumsi' harus berupa angka positif yang valid. Contoh: 12 atau 12,5.",
            400,
        )

    try:
        num = Decimal(s_clean)
    except Exception:
        raise TravelCostError(
            INVALID_KONSUMSI,
            "Nilai 'konsumsi' tidak dapat dibaca sebagai angka.",
            400,
        )

    if num < MIN_KONSUMSI or num > MAX_KONSUMSI:
        raise TravelCostError(
            INVALID_KONSUMSI,
            "Nilai 'konsumsi' harus bernilai antara 1 hingga 100 km per liter.",
            400,
        )

    return num


def parse_harga_bbm(val: Any) -> Decimal:
    """Validasi dan parsing harga BBM per liter (1.000 .. 100.000 rupiah)."""
    if val is None:
        raise TravelCostError(
            INVALID_HARGA,
            "Field 'harga_bbm' wajib diisi. Masukkan harga BBM antara Rp 1.000 hingga Rp 100.000 per liter.",
            400,
        )

    if isinstance(val, bool):
        raise TravelCostError(
            INVALID_HARGA,
            "Nilai 'harga_bbm' harus berupa angka rupiah, bukan boolean.",
            400,
        )

    if isinstance(val, (int, float, Decimal)):
        s = str(val).strip()
    elif isinstance(val, str):
        s = val.strip()
    else:
        raise TravelCostError(
            INVALID_REQUEST,
            "Field 'harga_bbm' harus berupa string atau angka.",
            400,
        )

    if not s:
        raise TravelCostError(
            INVALID_HARGA,
            "Field 'harga_bbm' tidak boleh kosong. Masukkan harga BBM antara Rp 1.000 hingga Rp 100.000 per liter.",
            400,
        )

    if len(s) > MAX_INPUT_LENGTH:
        raise TravelCostError(
            INVALID_NUMBER,
            "Masukan 'harga_bbm' melebihi batas 40 karakter.",
            400,
        )

    s_clean = s.replace(".", "").replace(" ", "").replace(",", ".")

    if not re.fullmatch(r"^\d+(\.\d+)?$", s_clean):
        raise TravelCostError(
            INVALID_HARGA,
            "Nilai 'harga_bbm' harus berupa angka rupiah positif yang valid. Contoh: 10000 atau 10.000.",
            400,
        )

    try:
        num = Decimal(s_clean)
    except Exception:
        raise TravelCostError(
            INVALID_HARGA,
            "Nilai 'harga_bbm' tidak dapat dibaca sebagai angka.",
            400,
        )

    if num < MIN_HARGA_BBM or num > MAX_HARGA_BBM:
        raise TravelCostError(
            INVALID_HARGA,
            "Harga BBM harus bernilai antara Rp 1.000 hingga Rp 100.000 per liter.",
            400,
        )

    return num


def parse_penumpang(val: Any) -> int:
    """Validasi dan parsing jumlah penumpang (1 .. 50 orang, bawaan 1)."""
    if val is None:
        return DEFAULT_PENUMPANG

    if isinstance(val, bool):
        raise TravelCostError(
            INVALID_PENUMPANG,
            "Jumlah penumpang harus berupa bilangan bulat antara 1 hingga 50 orang.",
            400,
        )

    if isinstance(val, int):
        num = val
    elif isinstance(val, (float, Decimal)):
        if val % 1 != 0:
            raise TravelCostError(
                INVALID_PENUMPANG,
                "Jumlah penumpang harus berupa bilangan bulat antara 1 hingga 50 orang.",
                400,
            )
        num = int(val)
    elif isinstance(val, str):
        s = val.strip()
        if not s:
            return DEFAULT_PENUMPANG
        if len(s) > MAX_INPUT_LENGTH:
            raise TravelCostError(
                INVALID_NUMBER,
                "Masukan 'penumpang' melebihi batas 40 karakter.",
                400,
            )
        if not re.fullmatch(r"^\d+$", s):
            raise TravelCostError(
                INVALID_PENUMPANG,
                "Jumlah penumpang harus berupa bilangan bulat antara 1 hingga 50 orang.",
                400,
            )
        try:
            num = int(s)
        except ValueError:
            raise TravelCostError(
                INVALID_PENUMPANG,
                "Jumlah penumpang harus berupa bilangan bulat antara 1 hingga 50 orang.",
                400,
            )
    else:
        raise TravelCostError(
            INVALID_REQUEST,
            "Field 'penumpang' harus berupa bilangan bulat.",
            400,
        )

    if num < MIN_PENUMPANG or num > MAX_PENUMPANG:
        raise TravelCostError(
            INVALID_PENUMPANG,
            "Jumlah penumpang harus bernilai antara 1 hingga 50 orang.",
            400,
        )

    return num


def parse_biaya_lain(val: Any) -> Decimal:
    """Validasi dan parsing biaya lain seperti tol, parkir, dan makan (0 .. 100.000.000 rupiah, bawaan 0)."""
    if val is None:
        return DEFAULT_BIAYA_LAIN

    if isinstance(val, bool):
        raise TravelCostError(
            INVALID_BIAYA_LAIN,
            "Nilai 'biaya_lain' harus berupa angka rupiah.",
            400,
        )

    if isinstance(val, (int, float, Decimal)):
        s = str(val).strip()
    elif isinstance(val, str):
        s = val.strip()
    else:
        raise TravelCostError(
            INVALID_REQUEST,
            "Field 'biaya_lain' harus berupa string atau angka.",
            400,
        )

    if not s:
        return DEFAULT_BIAYA_LAIN

    if len(s) > MAX_INPUT_LENGTH:
        raise TravelCostError(
            INVALID_NUMBER,
            "Masukan 'biaya_lain' melebihi batas 40 karakter.",
            400,
        )

    if s.startswith("-"):
        raise TravelCostError(
            INVALID_BIAYA_LAIN,
            "Biaya lain tidak boleh bernilai negatif.",
            400,
        )

    s_clean = s.replace(".", "").replace(" ", "").replace(",", ".")

    if not re.fullmatch(r"^\d+(\.\d+)?$", s_clean):
        raise TravelCostError(
            INVALID_BIAYA_LAIN,
            "Nilai 'biaya_lain' harus berupa angka rupiah yang valid. Contoh: 50000 atau 50.000.",
            400,
        )

    try:
        num = Decimal(s_clean)
    except Exception:
        raise TravelCostError(
            INVALID_BIAYA_LAIN,
            "Nilai 'biaya_lain' tidak dapat dibaca sebagai angka.",
            400,
        )

    if num < MIN_BIAYA_LAIN or num > MAX_BIAYA_LAIN:
        raise TravelCostError(
            INVALID_BIAYA_LAIN,
            "Biaya lain harus bernilai antara Rp 0 hingga Rp 100.000.000.",
            400,
        )

    return num


def hitung_biaya_perjalanan(
    jarak: Any,
    pulang_pergi: Any = False,
    konsumsi: Any = None,
    harga_bbm: Any = None,
    penumpang: Any = 1,
    biaya_lain: Any = 0,
) -> dict[str, Any]:
    """Hitung perkiraan biaya BBM, total biaya perjalanan, dan patungan per orang murni di memori."""
    d_jarak = parse_jarak(jarak)
    is_pp = parse_pulang_pergi(pulang_pergi)
    d_konsumsi = parse_konsumsi(konsumsi)
    d_harga_bbm = parse_harga_bbm(harga_bbm)
    int_penumpang = parse_penumpang(penumpang)
    d_biaya_lain = parse_biaya_lain(biaya_lain)

    # Jarak satu arah & total
    d_jarak_satu_arah = d_jarak
    d_jarak_total_raw = (d_jarak * Decimal(2)) if is_pp else d_jarak
    d_jarak_total = d_jarak_total_raw.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    # Konsumsi bahan bakar dalam liter (2 desimal)
    d_liter = (d_jarak_total / d_konsumsi).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Biaya BBM rupiah penuh (ROUND_HALF_UP)
    d_biaya_bbm = (d_liter * d_harga_bbm).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    # Biaya lain tidak dikali dua, dibulatkan ke rupiah penuh
    d_biaya_lain_rounded = d_biaya_lain.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    # Total biaya perjalanan
    d_total_biaya = d_biaya_bbm + d_biaya_lain_rounded

    # Biaya per orang dibulatkan ke atas (ROUND_CEILING)
    d_biaya_per_orang = (d_total_biaya / Decimal(int_penumpang)).to_integral_value(rounding=ROUND_CEILING)

    # Biaya per kilometer dibulatkan ke rupiah penuh (ROUND_HALF_UP)
    d_biaya_per_km = (d_total_biaya / d_jarak_total).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    # Tabel simulasi patungan 1 sampai 6 penumpang (masing-masing dibulatkan ke atas)
    tabel_patungan: list[dict[str, int]] = []
    for p in range(1, 7):
        bpo = int((d_total_biaya / Decimal(p)).to_integral_value(rounding=ROUND_CEILING))
        tabel_patungan.append({"penumpang": p, "biaya_per_orang": bpo})

    catatan = [
        "Ini perkiraan bahan bakar saja. Belum termasuk penyusutan kendaraan, servis, asuransi, dan biaya tak terduga.",
        "Biaya lain (tol, parkir, makan) dihitung satu kali untuk seluruh perjalanan, tidak ikut dikali dua.",
        "Patungan dibulatkan ke atas supaya uang yang terkumpul tidak kurang dari perkiraan biaya.",
    ]

    return {
        "jarak_total": float(d_jarak_total),
        "liter": float(d_liter),
        "biaya_bbm": int(d_biaya_bbm),
        "biaya_lain": int(d_biaya_lain_rounded),
        "total_biaya": int(d_total_biaya),
        "biaya_per_orang": int(d_biaya_per_orang),
        "biaya_per_km": int(d_biaya_per_km),
        "penumpang": int_penumpang,
        "pulang_pergi": is_pp,
        "rincian": {
            "jarak_satu_arah": float(d_jarak_satu_arah.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
            "konsumsi": float(d_konsumsi),
            "harga_bbm": int(d_harga_bbm.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "biaya_lain": int(d_biaya_lain_rounded),
        },
        "tabel_patungan": tabel_patungan,
        "catatan": catatan,
    }


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional kalkulator biaya perjalanan."""
    return {
        "batas": {
            "jarak": {"min": 0.1, "max": 20000, "satuan": "km"},
            "konsumsi": {"min": 1, "max": 100, "bawaan": 12, "satuan": "km/liter"},
            "harga_bbm": {"min": 1000, "max": 100000, "satuan": "rupiah"},
            "penumpang": {"min": 1, "max": 50, "bawaan": 1, "satuan": "orang"},
            "biaya_lain": {"min": 0, "max": 100000000, "bawaan": 0, "satuan": "rupiah"},
        },
        "pulang_pergi": {"bawaan": False},
        "contoh": {
            "jarak": 122,
            "pulang_pergi": True,
            "konsumsi": 12,
            "harga_bbm": 10000,
            "penumpang": 2,
            "biaya_lain": 50000,
        },
        "processed_on": "server",
        "note": "Perhitungan dilakukan di memori, nilai masukan tidak pernah disimpan ke disk atau dicatat ke log.",
    }
