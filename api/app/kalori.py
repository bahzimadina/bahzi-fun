"""Logika hitung kalori & berat badan ideal: fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Isian pengguna tidak dicatat ke log.

Rumus:
  BMR Mifflin-St Jeor:
    pria = 10*berat + 6.25*tinggi - 5*umur + 5
    wanita = 10*berat + 6.25*tinggi - 5*umur - 161
  Faktor aktivitas:
    duduk 1.2, ringan 1.375, sedang 1.55, berat 1.725, sangat_berat 1.9
  TDEE = BMR * faktor
  Laju:
    pelan 0.25 kg/minggu, sedang 0.5, cepat 0.75. 1 kg lemak ~ 7700 kkal.
    selisih harian = kg_per_minggu * 7700 / 7  (pelan 275, sedang 550, cepat 825 kkal)
    target "turun" -> kalori = TDEE - selisih ; "naik" -> TDEE + selisih ; "tetap" -> TDEE
  IMT = berat / (tinggi_m ** 2), dibulatkan 2 desimal
  Kategori IMT memakai batas Asia-Pasifik (dipakai di Indonesia):
    < 18.5 kurang ; 18.5..22.9 normal ; 23..24.9 kelebihan ; 25..29.9 obesitas ; >= 30 obesitas berat
  Berat ideal: rentang berat untuk IMT 18.5 sampai 22.9:
    min = 18.5*(tinggi_m**2), maks = 22.9*(tinggi_m**2), dibulatkan 1 desimal.
  Perkiraan waktu:
    bila target "turun" dan berat sekarang > batas atas ideal, atau target "naik" dan berat < batas
    bawah ideal, hitung minggu = selisih_kg / kg_per_minggu, dibulatkan ke ATAS (bilangan bulat), dan
    sediakan juga teks rentang bulan (mis. "sekitar 3 sampai 4 bulan"). Selain itu null.
  Pengaman:
    kalori harian hasil tidak boleh di bawah 1.200 kkal. Bila hasil < 1.200, naikkan ke 1.200 dan
    laporkan "dibatasi": true + pesan jujur bahwa angka dinaikkan ke batas aman umum dan sebaiknya
    konsultasi ke ahli gizi.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

# Batas operasional kalkulator kalori
MIN_UMUR = 15
MAX_UMUR = 100

MIN_TINGGI = 120.0  # cm
MAX_TINGGI = 230.0  # cm

MIN_BERAT = 30.0  # kg
MAX_BERAT = 300.0  # kg

MIN_KALORI_AMAN = 1200
MAX_BODY_BYTES = 65536  # 64 KB

JENIS_KELAMIN_LIST = ("pria", "wanita")
AKTIVITAS_FAKTOR: dict[str, float] = {
    "duduk": 1.2,
    "ringan": 1.375,
    "sedang": 1.55,
    "berat": 1.725,
    "sangat_berat": 1.9,
}
TARGET_LIST = ("turun", "tetap", "naik")
LAJU_KG_PER_MINGGU: dict[str, float] = {
    "pelan": 0.25,
    "sedang": 0.5,
    "cepat": 0.75,
}
LAJU_SELISIH_HARIAN: dict[str, int] = {
    "pelan": 275,
    "sedang": 550,
    "cepat": 825,
}

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
UNSUPPORTED_JENIS_KELAMIN = "UNSUPPORTED_JENIS_KELAMIN"
UNSUPPORTED_AKTIVITAS = "UNSUPPORTED_AKTIVITAS"
UNSUPPORTED_TARGET = "UNSUPPORTED_TARGET"
UNSUPPORTED_LAJU = "UNSUPPORTED_LAJU"
INVALID_NUMBER = "INVALID_NUMBER"
OUT_OF_RANGE = "OUT_OF_RANGE"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class KaloriError(ValueError):
    """Galat operasional hitung kalori dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat terstandar."""
        err = {"code": self.code, "message": self.message}
        return {"error": err, "detail": err}


def round_half_up(val: int | float | Decimal | str, decimals: int = 0) -> float | int:
    """Membulatkan angka setengah ke atas (ROUND_HALF_UP) menggunakan Decimal."""
    d = Decimal(str(val))
    if decimals == 0:
        return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    exp = Decimal(10) ** -decimals
    return float(d.quantize(exp, rounding=ROUND_HALF_UP))


def format_angka_id(val: int | float, max_desimal: int = 1) -> str:
    """Format angka gaya Indonesia: titik untuk ribuan, koma untuk desimal."""
    if isinstance(val, int) and not isinstance(val, bool):
        is_neg = val < 0
        bulat_str = f"{abs(val):,}".replace(",", ".")
        return f"-{bulat_str}" if is_neg else bulat_str

    num = float(val)
    is_neg = num < 0
    formatted = f"{abs(num):.{max_desimal}f}"
    parts = formatted.split(".")
    bulat = int(parts[0])
    bulat_str = f"{bulat:,}".replace(",", ".")
    if len(parts) > 1:
        desimal = parts[1].rstrip("0")
        res = f"{bulat_str},{desimal}" if desimal else bulat_str
    else:
        res = bulat_str
    return f"-{res}" if is_neg else res


def parse_jenis_kelamin(val: Any) -> str:
    """Validasi dan parsing jenis kelamin (pria | wanita)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        raise KaloriError(INVALID_REQUEST, "Field 'jenis_kelamin' wajib diisi.", 400)
    s = str(val).strip().lower()
    if s not in JENIS_KELAMIN_LIST:
        raise KaloriError(
            UNSUPPORTED_JENIS_KELAMIN,
            f"Jenis kelamin '{val}' tidak didukung. Pilihan: {', '.join(JENIS_KELAMIN_LIST)}.",
            400,
        )
    return s


def parse_umur(val: Any) -> int:
    """Validasi dan parsing umur (15 .. 100 tahun)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        raise KaloriError(INVALID_REQUEST, "Field 'umur' wajib diisi.", 400)

    if isinstance(val, bool):
        raise KaloriError(INVALID_NUMBER, "Umur harus berupa bilangan bulat.", 400)

    if isinstance(val, (int, float)):
        if isinstance(val, float) and not val.is_integer():
            raise KaloriError(INVALID_NUMBER, "Umur harus berupa bilangan bulat.", 400)
        num = int(val)
    elif isinstance(val, str):
        s = val.strip()
        if s.startswith("-"):
            s_clean = s[1:].replace(".", "").replace(" ", "")
            if s_clean.isdigit():
                raise KaloriError(
                    OUT_OF_RANGE,
                    f"Umur harus antara {format_angka_id(MIN_UMUR)} dan {format_angka_id(MAX_UMUR)} tahun.",
                    400,
                )
            raise KaloriError(INVALID_NUMBER, "Umur harus berupa bilangan bulat.", 400)

        s_clean = s.replace(".", "").replace(" ", "")
        if not s_clean.isdigit():
            raise KaloriError(INVALID_NUMBER, "Umur harus berupa bilangan bulat.", 400)
        try:
            num = int(s_clean)
        except ValueError:
            raise KaloriError(INVALID_NUMBER, "Umur tidak valid.", 400)
    else:
        raise KaloriError(INVALID_NUMBER, "Umur harus berupa bilangan bulat.", 400)

    if num < MIN_UMUR or num > MAX_UMUR:
        raise KaloriError(
            OUT_OF_RANGE,
            f"Umur harus antara {format_angka_id(MIN_UMUR)} dan {format_angka_id(MAX_UMUR)} tahun.",
            400,
        )
    return num


def parse_tinggi(val: Any) -> float:
    """Validasi dan parsing tinggi badan dalam cm (120 .. 230). Menerima koma atau titik."""
    if val is None or (isinstance(val, str) and not val.strip()):
        raise KaloriError(INVALID_REQUEST, "Field 'tinggi' wajib diisi.", 400)

    if isinstance(val, bool):
        raise KaloriError(INVALID_NUMBER, "Tinggi badan harus berupa angka.", 400)

    if isinstance(val, (int, float)):
        num = float(val)
    elif isinstance(val, str):
        s = val.strip().replace(",", ".")
        if not re.fullmatch(r"^[+-]?\d+(?:\.\d+)?$", s):
            raise KaloriError(INVALID_NUMBER, "Tinggi badan harus berupa angka valid.", 400)
        try:
            num = float(s)
        except ValueError:
            raise KaloriError(INVALID_NUMBER, "Tinggi badan tidak valid.", 400)
    else:
        raise KaloriError(INVALID_NUMBER, "Tinggi badan harus berupa angka.", 400)

    if num < MIN_TINGGI or num > MAX_TINGGI:
        raise KaloriError(
            OUT_OF_RANGE,
            f"Tinggi badan harus antara {format_angka_id(MIN_TINGGI)} dan {format_angka_id(MAX_TINGGI)} cm.",
            400,
        )
    return num


def parse_berat(val: Any) -> float:
    """Validasi dan parsing berat badan dalam kg (30 .. 300). Menerima koma atau titik."""
    if val is None or (isinstance(val, str) and not val.strip()):
        raise KaloriError(INVALID_REQUEST, "Field 'berat' wajib diisi.", 400)

    if isinstance(val, bool):
        raise KaloriError(INVALID_NUMBER, "Berat badan harus berupa angka.", 400)

    if isinstance(val, (int, float)):
        num = float(val)
    elif isinstance(val, str):
        s = val.strip().replace(",", ".")
        if not re.fullmatch(r"^[+-]?\d+(?:\.\d+)?$", s):
            raise KaloriError(INVALID_NUMBER, "Berat badan harus berupa angka valid.", 400)
        try:
            num = float(s)
        except ValueError:
            raise KaloriError(INVALID_NUMBER, "Berat badan tidak valid.", 400)
    else:
        raise KaloriError(INVALID_NUMBER, "Berat badan harus berupa angka.", 400)

    if num < MIN_BERAT or num > MAX_BERAT:
        raise KaloriError(
            OUT_OF_RANGE,
            f"Berat badan harus antara {format_angka_id(MIN_BERAT)} dan {format_angka_id(MAX_BERAT)} kg.",
            400,
        )
    return num


def parse_aktivitas(val: Any) -> str:
    """Validasi dan parsing aktivitas harian."""
    if val is None or (isinstance(val, str) and not val.strip()):
        raise KaloriError(INVALID_REQUEST, "Field 'aktivitas' wajib diisi.", 400)
    s = str(val).strip().lower()
    if s not in AKTIVITAS_FAKTOR:
        raise KaloriError(
            UNSUPPORTED_AKTIVITAS,
            f"Tingkat aktivitas '{val}' tidak didukung. Pilihan: {', '.join(AKTIVITAS_FAKTOR.keys())}.",
            400,
        )
    return s


def parse_target(val: Any) -> str:
    """Validasi dan parsing target (turun | tetap | naik). Bawaan 'tetap'."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return "tetap"
    s = str(val).strip().lower()
    if s not in TARGET_LIST:
        raise KaloriError(
            UNSUPPORTED_TARGET,
            f"Target '{val}' tidak didukung. Pilihan: {', '.join(TARGET_LIST)}.",
            400,
        )
    return s


def parse_laju(val: Any) -> str:
    """Validasi dan parsing laju perubahan berat badan (pelan | sedang | cepat). Bawaan 'sedang'."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return "sedang"
    s = str(val).strip().lower()
    if s not in LAJU_KG_PER_MINGGU:
        raise KaloriError(
            UNSUPPORTED_LAJU,
            f"Laju '{val}' tidak didukung. Pilihan: {', '.join(LAJU_KG_PER_MINGGU.keys())}.",
            400,
        )
    return s


def hitung_kalori(
    jenis_kelamin: Any,
    umur: Any,
    tinggi: Any,
    berat: Any,
    aktivitas: Any,
    target: Any = "tetap",
    laju: Any = "sedang",
) -> dict[str, Any]:
    """Menghitung kebutuhan kalori harian dan analisis berat ideal di memori."""
    jk = parse_jenis_kelamin(jenis_kelamin)
    u = parse_umur(umur)
    t = parse_tinggi(tinggi)
    b = parse_berat(berat)
    akt = parse_aktivitas(aktivitas)
    tgt = parse_target(target)
    lj = parse_laju(laju)

    # 1. BMR Mifflin-St Jeor
    if jk == "pria":
        bmr_raw = 10.0 * b + 6.25 * t - 5.0 * u + 5.0
    else:
        bmr_raw = 10.0 * b + 6.25 * t - 5.0 * u - 161.0

    akt_faktor = AKTIVITAS_FAKTOR[akt]
    tdee_raw = bmr_raw * akt_faktor

    # 2. Laju & Selisih Kalori Harian
    if tgt == "tetap":
        kg_per_minggu = None
        selisih_harian = 0
        kalori_raw = tdee_raw
    else:
        kg_per_minggu = LAJU_KG_PER_MINGGU[lj]
        selisih_harian = LAJU_SELISIH_HARIAN[lj]
        if tgt == "turun":
            kalori_raw = tdee_raw - selisih_harian
        else:  # naik
            kalori_raw = tdee_raw + selisih_harian

    kalori_target = int(round_half_up(kalori_raw))
    dibatasi = False
    if kalori_target < MIN_KALORI_AMAN:
        kalori_target = MIN_KALORI_AMAN
        dibatasi = True

    # 3. IMT & Kategori Batas Asia-Pasifik
    tinggi_m = t / 100.0
    imt = round_half_up(b / (tinggi_m ** 2), 2)

    if imt < 18.5:
        imt_kategori = "kurang"
    elif imt < 23.0:
        imt_kategori = "normal"
    elif imt < 25.0:
        imt_kategori = "kelebihan"
    elif imt < 30.0:
        imt_kategori = "obesitas"
    else:
        imt_kategori = "obesitas berat"

    # 4. Rentang Berat Ideal Asia-Pasifik (IMT 18.5 .. 22.9)
    berat_ideal_min = round_half_up(18.5 * (tinggi_m ** 2), 1)
    berat_ideal_maks = round_half_up(22.9 * (tinggi_m ** 2), 1)
    berat_sekarang = round_half_up(b, 1)

    if berat_sekarang < berat_ideal_min:
        selisih_berat_ke_ideal = round_half_up(berat_ideal_min - berat_sekarang, 1)
    elif berat_sekarang > berat_ideal_maks:
        selisih_berat_ke_ideal = round_half_up(berat_sekarang - berat_ideal_maks, 1)
    else:
        selisih_berat_ke_ideal = None

    # 5. Perkiraan Waktu (minggu & rentang bulan)
    perkiraan_minggu = None
    perkiraan_bulan_teks = None

    if tgt == "turun" and berat_sekarang > berat_ideal_maks and kg_per_minggu:
        selisih_kg = round_half_up(berat_sekarang - berat_ideal_maks, 1)
        minggu = int(math.ceil(selisih_kg / kg_per_minggu))
        perkiraan_minggu = minggu
    elif tgt == "naik" and berat_sekarang < berat_ideal_min and kg_per_minggu:
        selisih_kg = round_half_up(berat_ideal_min - berat_sekarang, 1)
        minggu = int(math.ceil(selisih_kg / kg_per_minggu))
        perkiraan_minggu = minggu

    if perkiraan_minggu is not None:
        if perkiraan_minggu < 4:
            perkiraan_bulan_teks = "kurang dari 1 bulan"
        else:
            b_min = int(perkiraan_minggu / 4.33)
            b_max = int(math.ceil(perkiraan_minggu / 4.0))
            if b_min < 1:
                b_min = 1
            if b_min == b_max:
                perkiraan_bulan_teks = f"sekitar {b_min} bulan"
            else:
                perkiraan_bulan_teks = f"sekitar {b_min} sampai {b_max} bulan"

    # 6. Catatan Kejujuran & Medis
    catatan: list[str] = [
        "Perkiraan kebutuhan kalori dan rentang berat ideal dihitung memakai rumus Mifflin-St Jeor dan batas IMT Asia-Pasifik.",
        "Hasil ini adalah estimasi umum dan bukan nasihat medis. Tidak berlaku untuk ibu hamil atau menyusui. Remaja serta individu dengan kondisi khusus disarankan berkonsultasi langsung ke dokter atau ahli gizi.",
    ]
    if dibatasi:
        catatan.append(
            "Target kalori harian dinaikkan ke batas aman umum 1.200 kkal per hari. Asupan di bawah 1.200 kkal berisiko kekurangan nutrisi penting dan sebaiknya hanya dijalankan di bawah pengawasan ahli gizi."
        )

    return {
        "bmr": int(round_half_up(bmr_raw)),
        "tdee": int(round_half_up(tdee_raw)),
        "kalori_target": kalori_target,
        "selisih_harian": selisih_harian,
        "imt": imt,
        "imt_kategori": imt_kategori,
        "berat_ideal_min": berat_ideal_min,
        "berat_ideal_maks": berat_ideal_maks,
        "berat_sekarang": berat_sekarang,
        "selisih_berat_ke_ideal": selisih_berat_ke_ideal,
        "perkiraan_minggu": perkiraan_minggu,
        "perkiraan_bulan_teks": perkiraan_bulan_teks,
        "dibatasi": dibatasi,
        "catatan": catatan,
        "aktivitas": akt,
        "aktivitas_faktor": akt_faktor,
        "target": tgt,
        "laju": lj,
        "kg_per_minggu": kg_per_minggu,
        "metode": "Mifflin-St Jeor",
        "batas_imt": "Asia-Pasifik",
    }


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional dan pilihan opsi kalkulator kalori."""
    return {
        "min_umur": MIN_UMUR,
        "max_umur": MAX_UMUR,
        "min_tinggi": MIN_TINGGI,
        "max_tinggi": MAX_TINGGI,
        "min_berat": MIN_BERAT,
        "max_berat": MAX_BERAT,
        "min_kalori_aman": MIN_KALORI_AMAN,
        "max_body_bytes": MAX_BODY_BYTES,
        "jenis_kelamin": [
            {"value": "pria", "label": "Pria"},
            {"value": "wanita", "label": "Wanita"},
        ],
        "aktivitas": [
            {"value": "duduk", "label": "Banyak duduk", "faktor": 1.2},
            {"value": "ringan", "label": "Ringan (olahraga 1-3x seminggu)", "faktor": 1.375},
            {"value": "sedang", "label": "Sedang (olahraga 3-5x seminggu)", "faktor": 1.55},
            {"value": "berat", "label": "Berat (olahraga 6-7x seminggu)", "faktor": 1.725},
            {"value": "sangat_berat", "label": "Sangat berat (kerja fisik berat)", "faktor": 1.9},
        ],
        "target": [
            {"value": "turun", "label": "Turunkan berat badan"},
            {"value": "tetap", "label": "Jaga berat badan saat ini"},
            {"value": "naik", "label": "Naikkan berat badan"},
        ],
        "laju": [
            {"value": "pelan", "label": "Pelan (0,25 kg/minggu)", "kg_per_minggu": 0.25, "selisih_kkal": 275},
            {"value": "sedang", "label": "Sedang (0,5 kg/minggu)", "kg_per_minggu": 0.5, "selisih_kkal": 550},
            {"value": "cepat", "label": "Cepat (0,75 kg/minggu)", "kg_per_minggu": 0.75, "selisih_kkal": 825},
        ],
        "metode": "Mifflin-St Jeor",
        "batas_imt": "Asia-Pasifik",
    }
