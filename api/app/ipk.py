"""Logika kalkulator IPK (Indeks Prestasi Kumulatif): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import json
import math
from typing import Any

# Batas operasional
MAX_COURSES = 60
MIN_SKS = 1
MAX_SKS = 30
MAX_TOTAL_SKS = 400
MAX_COURSE_NAME_CHARS = 80
MIN_TARGET = 0.0
MAX_TARGET = 4.0
MAX_BODY_BYTES = 65536  # 64 KB

# Skala bobot nilai huruf standar kampus Indonesia
GRADE_WEIGHTS: dict[str, Decimal] = {
    "A": Decimal("4.0"),
    "AB": Decimal("3.5"),
    "B": Decimal("3.0"),
    "BC": Decimal("2.5"),
    "C": Decimal("2.0"),
    "CD": Decimal("1.5"),
    "D": Decimal("1.0"),
    "E": Decimal("0.0"),
}

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NO_COURSES = "NO_COURSES"
TOO_MANY_COURSES = "TOO_MANY_COURSES"
INVALID_SKS = "INVALID_SKS"
INVALID_COURSE_NAME = "INVALID_COURSE_NAME"
UNSUPPORTED_GRADE = "UNSUPPORTED_GRADE"
TOTAL_SKS_TOO_LARGE = "TOTAL_SKS_TOO_LARGE"
INVALID_TARGET = "INVALID_TARGET"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class IpkError(ValueError):
    """Galat operasional kalkulator IPK dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


def get_predikat(ipk_dec: Decimal) -> str:
    """Tentukan predikat kelulusan berdasarkan IPK pembulatan 2 desimal."""
    if ipk_dec >= Decimal("3.51"):
        return "Dengan pujian"
    if ipk_dec >= Decimal("3.01"):
        return "Sangat memuaskan"
    if ipk_dec >= Decimal("2.76"):
        return "Memuaskan"
    if ipk_dec >= Decimal("2.00"):
        return "Cukup"
    return "Di bawah 2,00"


def parse_target(target: Any) -> Decimal | None:
    """Validasi dan parsing target IPK. Nilai antara 0 sampai 4."""
    if target is None:
        return None

    if isinstance(target, bool):
        raise IpkError(INVALID_TARGET, "Target IPK harus angka antara 0 sampai 4.", 400)

    if isinstance(target, (int, float, Decimal)):
        try:
            d = Decimal(str(target))
        except Exception:
            raise IpkError(INVALID_TARGET, "Target IPK harus angka antara 0 sampai 4.", 400)
    elif isinstance(target, str):
        s = target.strip()
        if not s:
            return None
        s_clean = s.replace(",", ".")
        try:
            d = Decimal(s_clean)
        except Exception:
            raise IpkError(INVALID_TARGET, "Target IPK harus angka antara 0 sampai 4.", 400)
    else:
        raise IpkError(INVALID_TARGET, "Target IPK harus angka antara 0 sampai 4.", 400)

    if d < Decimal("0") or d > Decimal("4"):
        raise IpkError(INVALID_TARGET, "Target IPK harus angka antara 0 sampai 4.", 400)

    return d


def parse_sks(raw_sks: Any) -> int:
    """Validasi dan parsing SKS per mata kuliah. Harus integer 1..30."""
    if raw_sks is None or isinstance(raw_sks, bool):
        raise IpkError(INVALID_SKS, "SKS harus bilangan bulat 1 sampai 30.", 400)

    if isinstance(raw_sks, int):
        val = raw_sks
    elif isinstance(raw_sks, str):
        s = raw_sks.strip()
        if not s or not s.isdigit():
            raise IpkError(INVALID_SKS, "SKS harus bilangan bulat 1 sampai 30.", 400)
        val = int(s)
    else:
        raise IpkError(INVALID_SKS, "SKS harus bilangan bulat 1 sampai 30.", 400)

    if val < MIN_SKS or val > MAX_SKS:
        raise IpkError(INVALID_SKS, "SKS harus bilangan bulat 1 sampai 30.", 400)

    return val


def parse_nama(raw_nama: Any) -> str:
    """Validasi dan pangkas nama mata kuliah (opsional, maks 80 karakter)."""
    if raw_nama is None:
        return ""
    if isinstance(raw_nama, (dict, list)):
        raise IpkError(INVALID_REQUEST, "Format nama mata kuliah tidak valid.", 400)
    s = str(raw_nama).strip()
    if len(s) > MAX_COURSE_NAME_CHARS:
        raise IpkError(INVALID_COURSE_NAME, "Nama mata kuliah maksimal 80 karakter.", 400)
    return s


def parse_grade(raw_grade: Any) -> tuple[str, Decimal]:
    """Validasi nilai huruf dan kembalikan nilai seragam huruf besar serta bobotnya."""
    if raw_grade is None or not isinstance(raw_grade, str):
        raise IpkError(UNSUPPORTED_GRADE, "Nilai yang dikenal: A, AB, B, BC, C, CD, D, E.", 400)
    grade = raw_grade.strip().upper()
    if grade not in GRADE_WEIGHTS:
        raise IpkError(UNSUPPORTED_GRADE, "Nilai yang dikenal: A, AB, B, BC, C, CD, D, E.", 400)
    return grade, GRADE_WEIGHTS[grade]


def compute_ipk(courses: Any, target: Any = None) -> dict[str, Any]:
    """Hitung IPK dari daftar mata kuliah, dan hitung target jika diberikan."""
    if courses is None or not isinstance(courses, list):
        raise IpkError(
            INVALID_REQUEST,
            "Bentuk permintaan tidak valid. 'courses' harus berupa array JSON.",
            400,
        )

    if len(courses) == 0:
        raise IpkError(
            NO_COURSES,
            "Tambahkan minimal satu mata kuliah dengan SKS dan nilai.",
            400,
        )

    if len(courses) > MAX_COURSES:
        raise IpkError(
            TOO_MANY_COURSES,
            "Maksimal 60 mata kuliah dalam satu perhitungan.",
            400,
        )

    total_sks = 0
    total_mutu_dec = Decimal("0.0")
    distribusi: dict[str, int] = {k: 0 for k in GRADE_WEIGHTS}
    rincian: list[dict[str, Any]] = []

    for item in courses:
        if not isinstance(item, dict):
            raise IpkError(
                INVALID_REQUEST,
                "Tiap baris mata kuliah harus berupa objek.",
                400,
            )
        nama = parse_nama(item.get("nama"))
        sks = parse_sks(item.get("sks"))
        grade, bobot_dec = parse_grade(item.get("nilai"))

        mutu_dec = Decimal(sks) * bobot_dec
        total_sks += sks
        total_mutu_dec += mutu_dec
        distribusi[grade] += 1

        rincian.append({
            "nama": nama,
            "sks": sks,
            "nilai": grade,
            "bobot": float(bobot_dec),
            "mutu": float(mutu_dec),
        })

    if total_sks > MAX_TOTAL_SKS:
        raise IpkError(
            TOTAL_SKS_TOO_LARGE,
            "Total SKS tidak boleh melebihi 400.",
            400,
        )

    total_sks_dec = Decimal(total_sks)
    ipk_exact = total_mutu_dec / total_sks_dec
    ipk_dec = ipk_exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    ipk_float = float(ipk_dec)
    ipk_teks = f"{ipk_dec:.2f}".replace(".", ",")
    predikat = get_predikat(ipk_dec)

    # Perhitungan target IPK (jika diminta)
    target_dec = parse_target(target)
    target_dict: dict[str, Any] | None = None

    if target_dec is not None:
        target_float = float(target_dec)
        target_teks = f"{target_dec:.2f}".replace(".", ",")

        if ipk_dec >= target_dec:
            if ipk_dec > target_dec:
                pesan = f"IPK sekarang {ipk_teks}, sudah di atas target {target_teks}."
            else:
                pesan = f"IPK sekarang {ipk_teks}, sudah mencapai target {target_teks}."
            target_dict = {
                "diminta": target_float,
                "sks_a_dibutuhkan": 0,
                "ipk_setelah": ipk_float,
                "sudah_tercapai": True,
                "tidak_mungkin": False,
                "pesan": pesan,
            }
        elif target_dec == Decimal("4") or target_dec == Decimal("4.0"):
            # Target 4.00 hanya bisa bila semua nilai A, tidak bisa dikejar jika sudah ada non-A
            target_dict = {
                "diminta": target_float,
                "sks_a_dibutuhkan": None,
                "ipk_setelah": None,
                "sudah_tercapai": False,
                "tidak_mungkin": True,
                "pesan": "IPK 4,00 hanya bisa diraih bila semua nilai A, jadi target itu tidak bisa dikejar dengan menambah mata kuliah baru.",
            }
        else:
            # Rumus: x = ceil((target*total_sks - total_mutu) / (4 - target)) untuk target < 4
            pembilang = (target_dec * total_sks_dec) - total_mutu_dec
            penyebut = Decimal("4") - target_dec
            raw_x = pembilang / penyebut
            sks_a = int(math.ceil(float(raw_x)))
            if sks_a < 0:
                sks_a = 0

            max_sisa_sks = MAX_TOTAL_SKS - total_sks
            if sks_a > max_sisa_sks:
                target_dict = {
                    "diminta": target_float,
                    "sks_a_dibutuhkan": sks_a,
                    "ipk_setelah": None,
                    "sudah_tercapai": False,
                    "tidak_mungkin": True,
                    "pesan": f"Butuh tambahan {sks_a} SKS bernilai A, melebihi batas sisa total SKS ({max_sisa_sks} SKS).",
                }
            else:
                mutu_setelah_dec = total_mutu_dec + Decimal(sks_a) * Decimal("4")
                sks_setelah_dec = total_sks_dec + Decimal(sks_a)
                ipk_setelah_dec = (mutu_setelah_dec / sks_setelah_dec).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                ipk_setelah_float = float(ipk_setelah_dec)
                ipk_setelah_teks = f"{ipk_setelah_dec:.2f}".replace(".", ",")
                pesan = f"Butuh tambahan minimal {sks_a} SKS bernilai A untuk mencapai target {target_teks} (proyeksi IPK: {ipk_setelah_teks})."
                target_dict = {
                    "diminta": target_float,
                    "sks_a_dibutuhkan": sks_a,
                    "ipk_setelah": ipk_setelah_float,
                    "sudah_tercapai": False,
                    "tidak_mungkin": False,
                    "pesan": pesan,
                }

    res: dict[str, Any] = {
        "ipk": ipk_float,
        "ipk_teks": ipk_teks,
        "total_sks": total_sks,
        "total_mutu": float(total_mutu_dec),
        "jumlah_mk": len(courses),
        "predikat": predikat,
        "distribusi": distribusi,
        "rincian": rincian,
        "catatan_predikat": "Ambang predikat kelulusan dapat berbeda sesuai ketentuan masing-masing perguruan tinggi.",
    }
    if target_dict is not None:
        res["target"] = target_dict

    return res


def limits_payload() -> dict[str, Any]:
    """Mengembalikan batas operasional dan konfigurasi kalkulator IPK."""
    return {
        "max_courses": MAX_COURSES,
        "sks_per_course": {"min": MIN_SKS, "max": MAX_SKS},
        "max_total_sks": MAX_TOTAL_SKS,
        "grades": [
            {"value": grade, "weight": float(weight)}
            for grade, weight in GRADE_WEIGHTS.items()
        ],
        "target": {"min": MIN_TARGET, "max": MAX_TARGET},
        "predikat": [
            {"min": 3.51, "max": 4.00, "label": "Dengan pujian"},
            {"min": 3.01, "max": 3.50, "label": "Sangat memuaskan"},
            {"min": 2.76, "max": 3.00, "label": "Memuaskan"},
            {"min": 2.00, "max": 2.75, "label": "Cukup"},
            {"min": 0.00, "max": 1.99, "label": "Di bawah 2,00"},
        ],
        "catatan": "Nilai diproses di memori server lalu dibuang, tidak disimpan di disk.",
        "processed_on": "server",
    }
