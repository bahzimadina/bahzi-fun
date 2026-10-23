"""Logika kalender Hijriah (konversi tanggal Hijriah <-> Masehi): fungsi murni di memori.

Modul ini menggunakan kalender Hijriah aritmetika (tabular, siklus 30 tahun;
tahun kabisat bila (11*y + 14) mod 30 < 11). Rumus acuan yang terbukti
(Calendrical Calculations, epoch Julian 1948439.5 untuk 1 Muharram 1 H = 16 Juli 622 M Julian).

PENTING SOAL KETEPATAN:
Perhitungan dalam modul ini berbasis kalender aritmetika (tabular matematis).
Hasilnya dapat berbeda 1 hari dari penetapan resmi pemerintah Republik Indonesia
(sidang isbat Kementerian Agama RI) atau otoritas keagamaan lain yang menetapkan
awal bulan berdasarkan rukyatul hilal (pengamatan bulan sabit) atau hisab kontemporer
(imkanur rukyat MABIMS). Modul ini bukan kalender resmi pemerintah.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Tanggal pengguna tidak dicatat ke log.
"""

from __future__ import annotations

import datetime
import math
from typing import Any

# Batas operasional alat kalender Hijriah
MIN_TAHUN_HIJRIAH = 1300
MAX_TAHUN_HIJRIAH = 1600
MIN_TANGGAL_MASEHI = "1900-01-01"
MAX_TANGGAL_MASEHI = "2100-12-31"
MAX_BODY_BYTES = 65536  # 64 KB

# Kode galat stabil (semua Bahasa Indonesia, tanpa menyebut kata API)
INVALID_REQUEST = "INVALID_REQUEST"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
INVALID_DATE = "INVALID_DATE"
OUT_OF_RANGE = "OUT_OF_RANGE"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"

# Nama bulan dalam Bahasa Indonesia
NAMA_BULAN_HIJRIAH: tuple[str, ...] = (
    "",
    "Muharram",
    "Safar",
    "Rabiul Awal",
    "Rabiul Akhir",
    "Jumadil Awal",
    "Jumadil Akhir",
    "Rajab",
    "Syaban",
    "Ramadhan",
    "Syawal",
    "Dzulkaidah",
    "Dzulhijjah",
)

NAMA_BULAN_MASEHI: tuple[str, ...] = (
    "",
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)

# Nama hari dalam Bahasa Indonesia (indeks 0 = Senin sesuai datetime.date.weekday())
NAMA_HARI: tuple[str, ...] = (
    "Senin",
    "Selasa",
    "Rabu",
    "Kamis",
    "Jumat",
    "Sabtu",
    "Minggu",
)

# Konstanta astronomis Julian Day
# 1 Muharram 1 H = 1948439.5 JD
HIJRIAH_EPOCH_JD = 1948439.5
# 0001-01-01 Masehi = toordinal() 1 -> JD 1721424.5
GREGORIAN_EPOCH_JD_OFFSET = 1721424.5


class HijriahError(ValueError):
    """Galat operasional alat kalender Hijriah dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat terstandar."""
        return {"error": {"code": self.code, "message": self.message}}


def is_kabisat_hijriah(tahun: int) -> bool:
    """Tentukan apakah tahun Hijriah merupakan tahun kabisat (siklus 30 tahun).

    Tahun kabisat bila (11 * tahun + 14) % 30 < 11.
    Tahun kabisat memiliki 355 hari dengan bulan Dzulhijjah berjumlah 30 hari.
    """
    return (11 * tahun + 14) % 30 < 11


def hari_dalam_bulan_hijriah(tahun: int, bulan: int) -> int:
    """Jumlah hari pada bulan Hijriah tertentu.

    Bulan ganjil 30 hari, bulan genap 29 hari, KECUALI bulan 12 (Dzulhijjah)
    pada tahun kabisat berjumlah 30 hari.
    """
    if bulan < 1 or bulan > 12:
        return 0
    if bulan == 12:
        return 30 if is_kabisat_hijriah(tahun) else 29
    return 30 if bulan % 2 == 1 else 29


def hijriah_ke_jd(y: int, m: int, d: int) -> float:
    """Konversi tanggal Hijriah ke Julian Day (JD).

    Rumus Calendrical Calculations:
    hijriah_ke_jd(y, m, d) = d + ceil(29.5*(m-1)) + (y-1)*354 + floor((3 + 11*y)/30) + 1948439.5 - 1
    """
    return (
        d
        + math.ceil(29.5 * (m - 1))
        + (y - 1) * 354
        + math.floor((3 + 11 * y) / 30)
        + HIJRIAH_EPOCH_JD
        - 1
    )


def jd_ke_hijriah(jd: float) -> tuple[int, int, int]:
    """Invers dari hijriah_ke_jd: konversi Julian Day (JD) ke tanggal Hijriah (y, m, d).

    Menggunakan inversi analitis siklus 30 tahun lalu penyesuaian eksak tanpa menebak.
    """
    days = math.floor(jd - HIJRIAH_EPOCH_JD)
    # Perkiraan tahun awal berbasis rata-rata panjang tahun 10631 / 30 hari
    y = math.floor((30 * days + 10646) / 10631)
    # Pastikan tahun tepat dengan membandingkan batas awal tahun
    while jd < hijriah_ke_jd(y, 1, 1):
        y -= 1
    while jd >= hijriah_ke_jd(y + 1, 1, 1):
        y += 1

    # Cari bulan dengan iterasi batas bulan 1..12
    m = 1
    while m < 12 and jd >= hijriah_ke_jd(y, m + 1, 1):
        m += 1

    # Hari adalah selisih eksak ditambah 1
    d = int(round(jd - hijriah_ke_jd(y, m, 1))) + 1
    return y, m, d


def masehi_ke_jd(y: int, m: int, d: int) -> float:
    """Konversi tanggal Masehi ke Julian Day menggunakan datetime.date.toordinal()."""
    return datetime.date(y, m, d).toordinal() + GREGORIAN_EPOCH_JD_OFFSET


def jd_ke_masehi(jd: float) -> tuple[int, int, int]:
    """Konversi Julian Day ke tanggal Masehi (y, m, d) menggunakan datetime.date.fromordinal()."""
    ordinal = int(round(jd - GREGORIAN_EPOCH_JD_OFFSET))
    dt = datetime.date.fromordinal(ordinal)
    return dt.year, dt.month, dt.day


def parse_int_field(val: Any, field_name: str) -> int:
    """Validasi dan parsing integer untuk field formulir."""
    if val is None:
        raise HijriahError(INVALID_REQUEST, f"Field '{field_name}' wajib disertakan.", 400)
    s = str(val).strip()
    if not s:
        raise HijriahError(INVALID_REQUEST, f"Field '{field_name}' tidak boleh kosong.", 400)
    if not s.isdigit() and not (s.startswith("-") and s[1:].isdigit()):
        raise HijriahError(INVALID_DATE, f"Field '{field_name}' harus berupa bilangan bulat.", 400)
    return int(s)


def parse_tanggal_masehi(val: Any) -> datetime.date:
    """Validasi dan parsing tanggal Masehi (YYYY-MM-DD atau DD-MM-YYYY)."""
    if val is None:
        raise HijriahError(INVALID_REQUEST, "Field 'tanggal_masehi' wajib disertakan.", 400)
    s = str(val).strip()
    if not s:
        raise HijriahError(INVALID_REQUEST, "Field 'tanggal_masehi' tidak boleh kosong.", 400)

    sep = "-" if "-" in s else ("/" if "/" in s else None)
    if not sep:
        raise HijriahError(
            INVALID_DATE,
            "Format tanggal Masehi tidak valid. Gunakan format YYYY-MM-DD.",
            400,
        )

    parts = s.split(sep)
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise HijriahError(
            INVALID_DATE,
            "Format tanggal Masehi tidak valid. Gunakan format YYYY-MM-DD.",
            400,
        )

    if len(parts[0]) == 4:
        # YYYY-MM-DD
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
    elif len(parts[2]) == 4:
        # DD-MM-YYYY
        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
    else:
        raise HijriahError(
            INVALID_DATE,
            "Format tanggal Masehi tidak valid. Gunakan tahun 4 digit.",
            400,
        )

    # Validasi keberadaan tanggal di kalender Gregorius
    try:
        dt = datetime.date(y, m, d)
    except ValueError:
        raise HijriahError(
            INVALID_DATE,
            f"Tanggal Masehi '{s}' tidak ada dalam kalender.",
            400,
        )

    # Validasi batas rentang operasional 1900-01-01 .. 2100-12-31
    min_date = datetime.date(1900, 1, 1)
    max_date = datetime.date(2100, 12, 31)
    if dt < min_date or dt > max_date:
        raise HijriahError(
            OUT_OF_RANGE,
            "Tanggal Masehi harus antara 1900-01-01 sampai 2100-12-31.",
            400,
        )

    return dt


def hitung_tanggal_penting(tahun_hijriah: int) -> list[dict[str, str]]:
    """Daftar 4 tanggal penting pada tahun Hijriah tertentu beserta padanan Masehi-nya."""
    acara = [
        ("1 Muharram (Tahun Baru Hijriah)", 1, 1),
        ("12 Rabiul Awal (Maulid Nabi)", 3, 12),
        ("1 Ramadhan", 9, 1),
        ("10 Dzulhijjah (Idul Adha)", 12, 10),
    ]
    hasil: list[dict[str, str]] = []
    for nama, m, d in acara:
        jd = hijriah_ke_jd(tahun_hijriah, m, d)
        gy, gm, gd = jd_ke_masehi(jd)
        dt = datetime.date(gy, gm, gd)
        hari = NAMA_HARI[dt.weekday()]
        masehi_teks = f"{dt.day} {NAMA_BULAN_MASEHI[dt.month]} {dt.year}"
        hijriah_teks = f"{d} {NAMA_BULAN_HIJRIAH[m]} {tahun_hijriah} H"
        hasil.append(
            {
                "nama": nama,
                "hijriah": hijriah_teks,
                "masehi": masehi_teks,
                "hari": hari,
            }
        )
    return hasil


def konversi(
    mode: Any,
    hari: Any = None,
    bulan: Any = None,
    tahun: Any = None,
    tanggal_masehi: Any = None,
    **extra: Any,
) -> dict[str, Any]:
    """Konversi tanggal Hijriah <-> Masehi murni di memori.

    Mode yang didukung:
    - 'ke_masehi': butuh hari, bulan, tahun (Hijriah)
    - 'ke_hijriah': butuh tanggal_masehi (YYYY-MM-DD)
    """
    if extra:
        first_key = next(iter(extra.keys()))
        raise HijriahError(INVALID_REQUEST, f"Field '{first_key}' tidak dikenal.", 400)

    if mode is None:
        raise HijriahError(INVALID_REQUEST, "Field 'mode' wajib disertakan.", 400)

    mode_str = str(mode).strip()
    if not mode_str:
        raise HijriahError(INVALID_REQUEST, "Field 'mode' tidak boleh kosong.", 400)

    if mode_str not in ("ke_masehi", "ke_hijriah"):
        raise HijriahError(
            UNSUPPORTED_MODE,
            "Mode tidak didukung. Pilih 'ke_masehi' atau 'ke_hijriah'.",
            400,
        )

    if mode_str == "ke_masehi":
        # Tolak campuran mode
        if tanggal_masehi is not None and str(tanggal_masehi).strip() != "":
            raise HijriahError(
                INVALID_REQUEST,
                "Mode 'ke_masehi' tidak boleh menyertakan field 'tanggal_masehi'.",
                400,
            )

        if hari is None or bulan is None or tahun is None:
            raise HijriahError(
                INVALID_REQUEST,
                "Field 'hari', 'bulan', dan 'tahun' wajib disertakan untuk mode ke_masehi.",
                400,
            )

        hari_str = str(hari).strip()
        bulan_str = str(bulan).strip()
        tahun_str = str(tahun).strip()
        if not hari_str or not bulan_str or not tahun_str:
            raise HijriahError(
                INVALID_REQUEST,
                "Field 'hari', 'bulan', dan 'tahun' tidak boleh kosong.",
                400,
            )

        y = parse_int_field(tahun_str, "tahun")
        m = parse_int_field(bulan_str, "bulan")
        d = parse_int_field(hari_str, "hari")

        # Batas tahun Hijriah: 1300..1600
        if y < MIN_TAHUN_HIJRIAH or y > MAX_TAHUN_HIJRIAH:
            raise HijriahError(
                OUT_OF_RANGE,
                f"Tahun Hijriah harus antara {MIN_TAHUN_HIJRIAH} sampai {MAX_TAHUN_HIJRIAH} H.",
                400,
            )

        if m < 1 or m > 12:
            raise HijriahError(
                INVALID_DATE,
                "Bulan Hijriah harus antara 1 sampai 12.",
                400,
            )

        max_hari = hari_dalam_bulan_hijriah(y, m)
        if d < 1 or d > max_hari:
            bulan_nama = NAMA_BULAN_HIJRIAH[m]
            raise HijriahError(
                INVALID_DATE,
                f"Tanggal {d} tidak ada pada bulan {bulan_nama} tahun {y} H (maksimal {max_hari} hari).",
                400,
            )

        jd = hijriah_ke_jd(y, m, d)
        gy, gm, gd = jd_ke_masehi(jd)
        dt_masehi = datetime.date(gy, gm, gd)

        hari_dalam_tahun = math.ceil(29.5 * (m - 1)) + d
        hari_nama = NAMA_HARI[dt_masehi.weekday()]
        hari_angka = dt_masehi.isoweekday()  # Senin = 1 .. Jumat = 5 .. Minggu = 7

        hijriah_dict = {
            "hari": d,
            "bulan": m,
            "bulan_nama": NAMA_BULAN_HIJRIAH[m],
            "tahun": y,
            "teks": f"{d} {NAMA_BULAN_HIJRIAH[m]} {y} H",
            "hari_dalam_tahun": hari_dalam_tahun,
        }
        masehi_dict = {
            "tanggal": dt_masehi.isoformat(),
            "hari": hari_nama,
            "hari_angka": hari_angka,
            "bulan": dt_masehi.month,
            "bulan_nama": NAMA_BULAN_MASEHI[dt_masehi.month],
            "tahun": dt_masehi.year,
            "teks": f"{dt_masehi.day} {NAMA_BULAN_MASEHI[dt_masehi.month]} {dt_masehi.year}",
        }

        return {
            "mode": "ke_masehi",
            "hijriah": hijriah_dict,
            "masehi": masehi_dict,
            "tanggal_penting": hitung_tanggal_penting(y),
        }

    else:
        # mode_str == "ke_hijriah"
        # Tolak campuran mode
        if (
            (hari is not None and str(hari).strip() != "")
            or (bulan is not None and str(bulan).strip() != "")
            or (tahun is not None and str(tahun).strip() != "")
        ):
            raise HijriahError(
                INVALID_REQUEST,
                "Mode 'ke_hijriah' tidak boleh menyertakan field 'hari', 'bulan', atau 'tahun'.",
                400,
            )

        dt_masehi = parse_tanggal_masehi(tanggal_masehi)
        jd = masehi_ke_jd(dt_masehi.year, dt_masehi.month, dt_masehi.day)
        hy, hm, hd = jd_ke_hijriah(jd)

        hari_dalam_tahun = math.ceil(29.5 * (hm - 1)) + hd
        hari_nama = NAMA_HARI[dt_masehi.weekday()]
        hari_angka = dt_masehi.isoweekday()

        hijriah_dict = {
            "hari": hd,
            "bulan": hm,
            "bulan_nama": NAMA_BULAN_HIJRIAH[hm],
            "tahun": hy,
            "teks": f"{hd} {NAMA_BULAN_HIJRIAH[hm]} {hy} H",
            "hari_dalam_tahun": hari_dalam_tahun,
        }
        masehi_dict = {
            "tanggal": dt_masehi.isoformat(),
            "hari": hari_nama,
            "hari_angka": hari_angka,
            "bulan": dt_masehi.month,
            "bulan_nama": NAMA_BULAN_MASEHI[dt_masehi.month],
            "tahun": dt_masehi.year,
            "teks": f"{dt_masehi.day} {NAMA_BULAN_MASEHI[dt_masehi.month]} {dt_masehi.year}",
        }

        return {
            "mode": "ke_hijriah",
            "hijriah": hijriah_dict,
            "masehi": masehi_dict,
            "tanggal_penting": hitung_tanggal_penting(hy),
        }


def limits_payload() -> dict[str, Any]:
    """Batas operasional dan metadata konfigurasi untuk GET /api/hijriah/limits."""
    daftar_bulan = [
        {"nomor": i, "nama": NAMA_BULAN_HIJRIAH[i]} for i in range(1, 13)
    ]
    return {
        "min_tahun_hijriah": MIN_TAHUN_HIJRIAH,
        "max_tahun_hijriah": MAX_TAHUN_HIJRIAH,
        "min_tanggal_masehi": MIN_TANGGAL_MASEHI,
        "max_tanggal_masehi": MAX_TANGGAL_MASEHI,
        "max_body_bytes": MAX_BODY_BYTES,
        "daftar_bulan": daftar_bulan,
        "mode_didukung": [
            {"value": "ke_masehi", "label": "Hijriah ke Masehi"},
            {"value": "ke_hijriah", "label": "Masehi ke Hijriah"},
        ],
        "default_mode": "ke_masehi",
        "catatan": (
            "Perhitungan kalender Hijriah berbasis aritmetika (tabular matematis). "
            "Bisa berbeda 1 hari dari penetapan resmi pemerintah (sidang isbat Kementerian Agama RI) "
            "yang memakai rukyatul hilal atau hisab kontemporer. "
            "Contoh beda nyata: 1 Ramadhan 1447 H ditetapkan pemerintah 19 Februari 2026, sedangkan hitungan aritmetika memberi 18 Februari 2026."
        ),
        "ringkasan_batas": f"Tahun Hijriah {MIN_TAHUN_HIJRIAH}–{MAX_TAHUN_HIJRIAH} H; tanggal Masehi yang bisa dimasukkan 1900–2100",
    }
