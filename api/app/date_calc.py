"""Logika kalkulator tanggal (Date Calculator): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
import re
from typing import Any

# Batas operasional
MAX_INPUT_CHARS = 40
MIN_YEAR = 1900
MAX_YEAR = 2100
MAX_AMOUNT = 100000

# Zona waktu WIB dengan offset tetap UTC+7 (tanpa pustaka zoneinfo)
WIB = timezone(timedelta(hours=7))

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = [
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
]

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NO_DATE = "NO_DATE"
INVALID_DATE = "INVALID_DATE"
OUT_OF_RANGE = "OUT_OF_RANGE"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
INVALID_AMOUNT = "INVALID_AMOUNT"
INVALID_UNIT = "INVALID_UNIT"
INVALID_DIRECTION = "INVALID_DIRECTION"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class DateCalcError(ValueError):
    """Galat operasional kalkulator tanggal dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


MODES: list[dict[str, Any]] = [
    {
        "value": "selisih",
        "label": "Selisih dua tanggal",
        "a_label": "Tanggal awal",
        "b_label": "Tanggal akhir",
        "butuh_jumlah": False,
        "butuh_unit": False,
        "contoh": {"a": "2026-01-01", "b": "2026-01-31"},
    },
    {
        "value": "tambah_kurang",
        "label": "Tambah atau kurangi tanggal",
        "a_label": "Tanggal acuan",
        "b_label": "",
        "butuh_jumlah": True,
        "butuh_unit": True,
        "contoh": {"a": "2026-01-31", "amount": "7", "unit": "hari", "direction": "maju"},
    },
    {
        "value": "hari_apa",
        "label": "Hari dan pekan sebuah tanggal",
        "a_label": "Tanggal",
        "b_label": "",
        "butuh_jumlah": False,
        "butuh_unit": False,
        "contoh": {"a": "2026-09-28"},
    },
    {
        "value": "usia",
        "label": "Usia dari tanggal lahir",
        "a_label": "Tanggal lahir",
        "b_label": "Tanggal acuan (kosong = hari ini)",
        "butuh_jumlah": False,
        "butuh_unit": False,
        "contoh": {"a": "1990-08-17", "b": ""},
    },
]

UNITS: list[dict[str, str]] = [
    {"value": "hari", "label": "Hari"},
    {"value": "minggu", "label": "Minggu"},
    {"value": "bulan", "label": "Bulan"},
    {"value": "tahun", "label": "Tahun"},
]

DIRECTIONS: list[dict[str, str]] = [
    {"value": "maju", "label": "Maju (tambah)"},
    {"value": "mundur", "label": "Mundur (kurang)"},
]


def parse_date(value: Any, field_name: str = "tanggal") -> date:
    """Validasi dan parsing string tanggal ke objek datetime.date.

    Aturan pembacaan tanggal:
    - Spasi ujung dibuang. Masukan kosong -> NO_DATE 400.
    - Panjang lebih dari MAX_INPUT_CHARS -> OUT_OF_RANGE 413.
    - Pemisah harus seragam: pakai '-' semua atau '/' semua. Campur -> INVALID_DATE 400.
    - Tiga bagian, urutan ditentukan:
      kalau bagian pertama 4 digit -> tahun dulu (YYYY-MM-DD);
      selain itu hari dulu (DD-MM-YYYY).
      Tahun 2 digit -> INVALID_DATE 400 (jangan menebak abad).
    - Bulan dan hari harus bilangan bulat 1-2 digit; selain itu INVALID_DATE 400.
    - Tanggal harus tanggal kalender yang benar (termasuk tahun kabisat) lewat datetime.date(y, m, d);
      kalau tidak valid -> INVALID_DATE 400.
    - Tahun di luar MIN_YEAR..MAX_YEAR -> OUT_OF_RANGE 413 dengan pesan yang menyebut rentang 1900 sampai 2100.
    """
    if value is None:
        raise DateCalcError(NO_DATE, f"Tanggal '{field_name}' wajib diisi.", 400)

    if not isinstance(value, str):
        raise DateCalcError(INVALID_REQUEST, f"Field '{field_name}' harus berupa teks string.", 400)

    cleaned = value.strip()
    if not cleaned:
        raise DateCalcError(NO_DATE, f"Tanggal '{field_name}' wajib diisi.", 400)

    if len(cleaned) > MAX_INPUT_CHARS:
        raise DateCalcError(
            OUT_OF_RANGE,
            f"Panjang masukan ({len(cleaned)} karakter) melebihi batas {MAX_INPUT_CHARS} karakter.",
            413,
        )

    has_dash = "-" in cleaned
    has_slash = "/" in cleaned

    if has_dash and has_slash:
        raise DateCalcError(
            INVALID_DATE,
            "Format pemisah tanggal tidak seragam. Gunakan '-' semua atau '/' semua.",
            400,
        )

    if not has_dash and not has_slash:
        raise DateCalcError(
            INVALID_DATE,
            "Format tanggal tidak valid. Gunakan pemisah '-' atau '/'.",
            400,
        )

    sep = "-" if has_dash else "/"
    parts = cleaned.split(sep)
    if len(parts) != 3:
        raise DateCalcError(
            INVALID_DATE,
            "Format tanggal harus terdiri dari 3 bagian: tahun, bulan, dan hari.",
            400,
        )

    if not all(p.isdigit() for p in parts):
        raise DateCalcError(
            INVALID_DATE,
            "Bagian tanggal harus berupa bilangan bulat positif.",
            400,
        )

    p0, p1, p2 = parts

    if len(p0) == 4:
        # Format YYYY-MM-DD
        year_str = p0
        month_str = p1
        day_str = p2
        if not (1 <= len(month_str) <= 2 and 1 <= len(day_str) <= 2):
            raise DateCalcError(
                INVALID_DATE,
                "Bulan dan hari harus berupa bilangan 1-2 digit.",
                400,
            )
    else:
        # Format DD-MM-YYYY
        if len(p2) == 2:
            raise DateCalcError(
                INVALID_DATE,
                "Tahun harus ditulis lengkap 4 digit (jangan gunakan 2 digit).",
                400,
            )
        if len(p2) != 4:
            raise DateCalcError(
                INVALID_DATE,
                "Format tahun harus 4 digit.",
                400,
            )
        if not (1 <= len(p0) <= 2 and 1 <= len(p1) <= 2):
            raise DateCalcError(
                INVALID_DATE,
                "Hari dan bulan harus berupa bilangan 1-2 digit.",
                400,
            )
        day_str = p0
        month_str = p1
        year_str = p2

    y = int(year_str)
    m = int(month_str)
    d = int(day_str)

    # Periksa batas rentang tahun sebelum memeriksa kalender
    if y < MIN_YEAR or y > MAX_YEAR:
        raise DateCalcError(
            OUT_OF_RANGE,
            f"Tahun {y} di luar rentang yang didukung ({MIN_YEAR} sampai {MAX_YEAR}).",
            413,
        )

    if m < 1 or m > 12:
        raise DateCalcError(
            INVALID_DATE,
            "Bulan harus antara 1 sampai 12.",
            400,
        )

    try:
        parsed_dt = date(y, m, d)
    except ValueError:
        raise DateCalcError(
            INVALID_DATE,
            "Tanggal tidak valid pada kalender.",
            400,
        )

    return parsed_dt


def add_months(d: date, n: int) -> date:
    """Tambah atau kurangi bulan dengan aturan penyesuaian akhir bulan.

    Jika tanggal sumber melebihi jumlah hari pada bulan tujuan,
    tanggal dipangkas ke hari terakhir bulan tujuan.
    Contoh:
    - 31 Januari 2026 + 1 bulan = 28 Februari 2026
    - 31 Januari 2024 + 1 bulan = 29 Februari 2024 (kabisat)
    - 31 Maret 2026 - 1 bulan = 28 Februari 2026
    - 29 Februari 2024 + 1 tahun (12 bulan) = 28 Februari 2025
    """
    total_months = (d.year * 12 + d.month - 1) + n
    new_year = total_months // 12
    new_month = total_months % 12 + 1
    max_days = calendar.monthrange(new_year, new_month)[1]
    new_day = min(d.day, max_days)
    return date(new_year, new_month, new_day)


def hitung_hari_kerja_dan_akhir_pekan(d_min: date, d_max: date) -> tuple[int, int]:
    """Hitung jumlah hari kerja (Senin-Jumat) dan akhir pekan (Sabtu-Minggu) inklusif."""
    total_days = (d_max - d_min).days + 1
    full_weeks = total_days // 7
    rem_days = total_days % 7
    work_days = full_weeks * 5
    weekend_days = full_weeks * 2
    for i in range(rem_days):
        current_day = d_min + timedelta(days=full_weeks * 7 + i)
        if current_day.weekday() < 5:
            work_days += 1
        else:
            weekend_days += 1
    return work_days, weekend_days


def hitung_tahun_bulan_hari(d_start: date, d_end: date) -> tuple[dict[str, int], int, int]:
    """Hitung selisih dalam tahun-bulan-hari, serta bulan penuh + sisa hari.

    Mengembalikan: (tahun_bulan_hari, bulan_penuh, sisa_hari_bulan)
    """
    if d_start == d_end:
        return {"tahun": 0, "bulan": 0, "hari": 0}, 0, 0

    # 1. Hitung bulan penuh
    m = 0
    while add_months(d_start, m + 1) <= d_end:
        m += 1
    bulan_penuh = m
    checkpoint_bulan = add_months(d_start, bulan_penuh)
    sisa_hari_bulan = (d_end - checkpoint_bulan).days

    # 2. Hitung tahun, bulan, hari
    y = 0
    while add_months(d_start, (y + 1) * 12) <= d_end:
        y += 1
    after_years = add_months(d_start, y * 12)

    rem_m = 0
    while add_months(after_years, rem_m + 1) <= d_end:
        rem_m += 1
    after_months = add_months(after_years, rem_m)
    rem_d = (d_end - after_months).days

    return {"tahun": y, "bulan": rem_m, "hari": rem_d}, bulan_penuh, sisa_hari_bulan


def format_date_id(d: date) -> str:
    """Format tanggal Indonesia singkat: '28 September 2026'."""
    return f"{d.day} {BULAN[d.month - 1]} {d.year}"


def format_date_long_id(d: date) -> str:
    """Format tanggal panjang Indonesia: 'Senin, 28 September 2026'."""
    return f"{HARI[d.weekday()]}, {d.day} {BULAN[d.month - 1]} {d.year}"


def compute_date(
    mode: Any,
    a: Any = None,
    b: Any = None,
    amount: Any = None,
    unit: Any = None,
    direction: Any = None,
) -> dict[str, Any]:
    """Hitung tanggal murni di memori berdasarkan mode pilihan."""
    if mode is None:
        raise DateCalcError(INVALID_REQUEST, "Field 'mode' wajib diisi.", 400)

    if not isinstance(mode, str):
        raise DateCalcError(INVALID_REQUEST, "Field 'mode' harus berupa teks string.", 400)

    mode_norm = mode.strip()
    mode_obj = next((m for m in MODES if m["value"] == mode_norm), None)
    if not mode_obj:
        valid_modes = ", ".join(m["value"] for m in MODES)
        raise DateCalcError(
            UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak didukung. Pilih salah satu: {valid_modes}.",
            400,
        )

    if mode_norm == "selisih":
        if a is None or (isinstance(a, str) and not a.strip()):
            raise DateCalcError(NO_DATE, "Tanggal awal ('a') wajib diisi.", 400)
        if b is None or (isinstance(b, str) and not b.strip()):
            raise DateCalcError(NO_DATE, "Tanggal akhir ('b') wajib diisi.", 400)

        dt_a = parse_date(a, "a")
        dt_b = parse_date(b, "b")

        delta_days = (dt_b - dt_a).days
        hari_abs = abs(delta_days)
        minggu = hari_abs // 7
        hari_sisa = hari_abs % 7

        d_min = min(dt_a, dt_b)
        d_max = max(dt_a, dt_b)

        tbh, bulan_penuh, hari_sisa_bulan = hitung_tahun_bulan_hari(d_min, d_max)
        work_days, weekend_days = hitung_hari_kerja_dan_akhir_pekan(d_min, d_max)

        if delta_days == 0:
            kalimat = f"Kedua tanggal sama ({format_date_id(dt_a)}). Selisihnya 0 hari."
        elif delta_days > 0:
            w_text = (
                f"{minggu} minggu {hari_sisa} hari"
                if minggu > 0 and hari_sisa > 0
                else (f"{minggu} minggu" if minggu > 0 else f"{hari_sisa} hari")
            )
            kalimat = f"Dari {format_date_id(dt_a)} sampai {format_date_id(dt_b)} berjarak {hari_abs} hari ({w_text})."
        else:
            w_text = (
                f"{minggu} minggu {hari_sisa} hari"
                if minggu > 0 and hari_sisa > 0
                else (f"{minggu} minggu" if minggu > 0 else f"{hari_sisa} hari")
            )
            kalimat = f"Dari {format_date_id(dt_a)} mundur ke {format_date_id(dt_b)} berjarak {delta_days} hari ({w_text})."

        rumus = f"{dt_b.isoformat()} - {dt_a.isoformat()} = {delta_days} hari"
        catatan = "Hari kerja dihitung dari hari Senin sampai Jumat, belum memperhitungkan hari libur nasional."

        rincian = [
            {"label": "Selisih hari (bertanda)", "nilai": f"{delta_days} hari"},
            {"label": "Jarak mutlak", "nilai": f"{hari_abs} hari"},
            {"label": "Format minggu", "nilai": f"{minggu} minggu {hari_sisa} hari"},
            {"label": "Format bulan", "nilai": f"{bulan_penuh} bulan {hari_sisa_bulan} hari"},
            {"label": "Format tahun", "nilai": f"{tbh['tahun']} tahun {tbh['bulan']} bulan {tbh['hari']} hari"},
            {"label": "Hari kerja (Senin-Jumat)", "nilai": f"{work_days} hari"},
            {"label": "Akhir pekan (Sabtu-Minggu)", "nilai": f"{weekend_days} hari"},
        ]

        return {
            "mode": "selisih",
            "mode_label": mode_obj["label"],
            "masukan": {
                "a": dt_a.isoformat(),
                "b": dt_b.isoformat(),
                "a_label": mode_obj["a_label"],
                "b_label": mode_obj["b_label"],
            },
            "hari": delta_days,
            "hari_abs": hari_abs,
            "minggu": minggu,
            "hari_sisa": hari_sisa,
            "bulan_penuh": bulan_penuh,
            "hari_sisa_bulan": hari_sisa_bulan,
            "tahun_bulan_hari": tbh,
            "hari_kerja": work_days,
            "akhir_pekan": weekend_days,
            "kalimat": kalimat,
            "rumus": rumus,
            "catatan": catatan,
            "rincian": rincian,
            "hasil": {
                "nilai": delta_days,
                "nilai_abs": hari_abs,
                "teks": str(hari_abs),
                "satuan": "hari",
            },
        }

    elif mode_norm == "tambah_kurang":
        if a is None or (isinstance(a, str) and not a.strip()):
            raise DateCalcError(NO_DATE, "Tanggal acuan ('a') wajib diisi.", 400)
        dt = parse_date(a, "a")

        if amount is None or (isinstance(amount, str) and not amount.strip()):
            raise DateCalcError(INVALID_REQUEST, "Field 'amount' wajib diisi untuk mode tambah/kurang.", 400)
        if isinstance(amount, str):
            amt_str = amount.strip()
            if not re.fullmatch(r"[+\-]?\d+", amt_str):
                raise DateCalcError(INVALID_AMOUNT, "Jumlah harus berupa bilangan bulat.", 400)
            try:
                amt = int(amt_str)
            except ValueError:
                raise DateCalcError(INVALID_AMOUNT, "Jumlah harus berupa bilangan bulat.", 400)
        elif isinstance(amount, int) and not isinstance(amount, bool):
            amt = amount
        else:
            raise DateCalcError(INVALID_AMOUNT, "Jumlah harus berupa bilangan bulat.", 400)

        if amt < 0:
            raise DateCalcError(INVALID_AMOUNT, "Jumlah tidak boleh negatif. Gunakan pilihan arah maju atau mundur.", 400)
        if amt > MAX_AMOUNT:
            raise DateCalcError(OUT_OF_RANGE, f"Jumlah ({amt}) melebihi batas maksimum {MAX_AMOUNT}.", 413)

        if unit is None or (isinstance(unit, str) and not unit.strip()):
            raise DateCalcError(INVALID_REQUEST, "Field 'unit' wajib diisi.", 400)
        unit_norm = str(unit).strip().lower()
        valid_unit_values = [u["value"] for u in UNITS]
        if unit_norm not in valid_unit_values:
            raise DateCalcError(
                INVALID_UNIT,
                f"Satuan '{unit}' tidak didukung. Pilih salah satu: {', '.join(valid_unit_values)}.",
                400,
            )

        if direction is None or (isinstance(direction, str) and not direction.strip()):
            direction_norm = "maju"
        else:
            direction_norm = str(direction).strip().lower()
        valid_direction_values = [d["value"] for d in DIRECTIONS]
        if direction_norm not in valid_direction_values:
            raise DateCalcError(
                INVALID_DIRECTION,
                f"Arah '{direction}' tidak didukung. Pilih salah satu: {', '.join(valid_direction_values)}.",
                400,
            )

        sign = 1 if direction_norm == "maju" else -1
        if unit_norm == "hari":
            target_dt = dt + timedelta(days=sign * amt)
        elif unit_norm == "minggu":
            target_dt = dt + timedelta(days=sign * amt * 7)
        elif unit_norm == "bulan":
            target_dt = add_months(dt, sign * amt)
        elif unit_norm == "tahun":
            target_dt = add_months(dt, sign * amt * 12)

        if target_dt.year < MIN_YEAR or target_dt.year > MAX_YEAR:
            raise DateCalcError(
                OUT_OF_RANGE,
                f"Hasil tanggal ({target_dt.year}) berada di luar rentang {MIN_YEAR} sampai {MAX_YEAR}.",
                413,
            )

        selisih_hari = abs((target_dt - dt).days)
        op_kata = "ditambah" if direction_norm == "maju" else "dikurangi"
        hari_hasil = HARI[target_dt.weekday()]
        tanggal_hasil_str = target_dt.isoformat()
        tgl_panjang = format_date_long_id(target_dt)

        kalimat = f"{format_date_id(dt)} {op_kata} {amt} {unit_norm} menjadi {tgl_panjang}."
        sign_sym = "+" if direction_norm == "maju" else "-"
        rumus = f"{dt.isoformat()} {sign_sym} {amt} {unit_norm} = {tanggal_hasil_str}"

        rincian = [
            {"label": "Tanggal hasil", "nilai": tanggal_hasil_str},
            {"label": "Hari", "nilai": hari_hasil},
            {"label": "Format panjang", "nilai": tgl_panjang},
            {"label": "Jarak selisih", "nilai": f"{selisih_hari} hari"},
            {"label": "Arah perhitungan", "nilai": "Maju" if direction_norm == "maju" else "Mundur"},
        ]

        return {
            "mode": "tambah_kurang",
            "mode_label": mode_obj["label"],
            "masukan": {
                "a": dt.isoformat(),
                "amount": amt,
                "unit": unit_norm,
                "direction": direction_norm,
                "a_label": mode_obj["a_label"],
            },
            "tanggal_hasil": tanggal_hasil_str,
            "tanggal_hasil_panjang": tgl_panjang,
            "hari_hasil": hari_hasil,
            "selisih_hari": selisih_hari,
            "kalimat": kalimat,
            "rumus": rumus,
            "rincian": rincian,
            "hasil": {
                "nilai": tanggal_hasil_str,
                "teks": tanggal_hasil_str,
                "satuan": hari_hasil,
            },
        }

    elif mode_norm == "hari_apa":
        if a is None or (isinstance(a, str) and not a.strip()):
            raise DateCalcError(NO_DATE, "Tanggal ('a') wajib diisi.", 400)
        dt = parse_date(a, "a")

        hari_nama = HARI[dt.weekday()]
        is_akhir_pekan = dt.weekday() in (5, 6)
        tgl_panjang = format_date_long_id(dt)
        hari_ke = (dt - date(dt.year, 1, 1)).days + 1
        sisa_hari = (date(dt.year, 12, 31) - dt).days
        jml_hari_bulan = calendar.monthrange(dt.year, dt.month)[1]
        pekan_iso = dt.isocalendar()[1]

        tipe_hari = "akhir pekan" if is_akhir_pekan else "hari kerja"
        kalimat = f"{tgl_panjang} adalah hari {hari_nama} ({tipe_hari}), pekan ke-{pekan_iso}, hari ke-{hari_ke} dalam tahun {dt.year}."

        rincian = [
            {"label": "Nama hari", "nilai": hari_nama},
            {"label": "Tanggal panjang", "nilai": tgl_panjang},
            {"label": "Status pekan", "nilai": "Akhir pekan (libur)" if is_akhir_pekan else "Hari kerja"},
            {
                "label": "Hari ke (dalam setahun)",
                "nilai": f"Hari ke-{hari_ke} dari {366 if calendar.isleap(dt.year) else 365}",
            },
            {"label": "Sisa hari sampai 31 Desember", "nilai": f"{sisa_hari} hari"},
            {"label": "Jumlah hari di bulan ini", "nilai": f"{jml_hari_bulan} hari"},
            {"label": "Nomor pekan ISO", "nilai": f"Pekan ke-{pekan_iso}"},
        ]

        return {
            "mode": "hari_apa",
            "mode_label": mode_obj["label"],
            "masukan": {
                "a": dt.isoformat(),
                "a_label": mode_obj["a_label"],
            },
            "hari": hari_nama,
            "akhir_pekan": is_akhir_pekan,
            "tanggal_panjang": tgl_panjang,
            "hari_ke_tahun": hari_ke,
            "sisa_hari_tahun": sisa_hari,
            "jumlah_hari_bulan": jml_hari_bulan,
            "pekan_iso": pekan_iso,
            "kalimat": kalimat,
            "rincian": rincian,
            "hasil": {
                "nilai": hari_nama,
                "teks": hari_nama,
                "satuan": "",
            },
        }

    elif mode_norm == "usia":
        if a is None or (isinstance(a, str) and not a.strip()):
            raise DateCalcError(NO_DATE, "Tanggal lahir ('a') wajib diisi.", 400)
        dt_a = parse_date(a, "a")

        if b is None or (isinstance(b, str) and not b.strip()):
            dt_b = datetime.now(WIB).date()
        else:
            dt_b = parse_date(b, "b")

        if dt_b < dt_a:
            raise DateCalcError(
                INVALID_DATE,
                "Tanggal acuan tidak boleh lebih awal dari tanggal lahir.",
                400,
            )

        tbh, _, _ = hitung_tahun_bulan_hari(dt_a, dt_b)
        total_hari = (dt_b - dt_a).days
        total_pekan = total_hari // 7

        bday_this_year = add_months(dt_a, (dt_b.year - dt_a.year) * 12)
        if bday_this_year == dt_b:
            ultah = {
                "tanggal": bday_this_year.isoformat(),
                "hari": HARI[bday_this_year.weekday()],
                "berapa_hari_lagi": "Hari ini",
            }
        elif bday_this_year > dt_b:
            days_left = (bday_this_year - dt_b).days
            ultah = {
                "tanggal": bday_this_year.isoformat(),
                "hari": HARI[bday_this_year.weekday()],
                "berapa_hari_lagi": f"{days_left} hari lagi",
            }
        else:
            next_bday = add_months(dt_a, (dt_b.year - dt_a.year + 1) * 12)
            days_left = (next_bday - dt_b).days
            ultah = {
                "tanggal": next_bday.isoformat(),
                "hari": HARI[next_bday.weekday()],
                "berapa_hari_lagi": f"{days_left} hari lagi",
            }

        years = tbh["tahun"]
        months = tbh["bulan"]
        days = tbh["hari"]

        if ultah["berapa_hari_lagi"] == "Hari ini":
            kalimat = f"Usia pada {format_date_id(dt_b)} adalah {years} tahun (sedang berulang tahun hari ini!)."
        else:
            parts = []
            if years > 0:
                parts.append(f"{years} tahun")
            if months > 0:
                parts.append(f"{months} bulan")
            if days > 0 or not parts:
                parts.append(f"{days} hari")
            age_str = " ".join(parts)
            tot_str = f"{total_hari:,}".replace(",", ".")
            kalimat = f"Usia pada {format_date_id(dt_b)} adalah {age_str} (total {tot_str} hari)."

        rincian = [
            {"label": "Usia", "nilai": f"{years} tahun {months} bulan {days} hari"},
            {"label": "Total hari", "nilai": f"{total_hari:,} hari".replace(",", ".")},
            {"label": "Total pekan", "nilai": f"{total_pekan:,} pekan".replace(",", ".")},
            {"label": "Tanggal lahir", "nilai": format_date_long_id(dt_a)},
            {"label": "Tanggal acuan", "nilai": format_date_long_id(dt_b)},
            {
                "label": "Ulang tahun berikutnya",
                "nilai": f"{ultah['tanggal']} ({ultah['hari']}) - {ultah['berapa_hari_lagi']}",
            },
        ]

        return {
            "mode": "usia",
            "mode_label": mode_obj["label"],
            "masukan": {
                "a": dt_a.isoformat(),
                "b": dt_b.isoformat(),
                "a_label": mode_obj["a_label"],
                "b_label": mode_obj["b_label"],
            },
            "tahun_bulan_hari": tbh,
            "total_hari": total_hari,
            "total_pekan": total_pekan,
            "ulang_tahun_berikutnya": ultah,
            "kalimat": kalimat,
            "rincian": rincian,
            "hasil": {
                "nilai": years,
                "teks": str(years),
                "satuan": "tahun",
            },
        }

    else:
        raise DateCalcError(UNSUPPORTED_MODE, f"Mode '{mode}' tidak didukung.", 400)


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional dan daftar mode kalkulator tanggal."""
    today_wib = datetime.now(WIB).date().isoformat()
    return {
        "max_input_chars": MAX_INPUT_CHARS,
        "min_year": MIN_YEAR,
        "max_year": MAX_YEAR,
        "modes": [
            {
                "value": m["value"],
                "label": m["label"],
                "a_label": m["a_label"],
                "b_label": m["b_label"],
                "butuh_jumlah": m["butuh_jumlah"],
                "butuh_unit": m["butuh_unit"],
                "contoh": dict(m["contoh"]),
            }
            for m in MODES
        ],
        "units": [dict(u) for u in UNITS],
        "directions": [dict(d) for d in DIRECTIONS],
        "today": today_wib,
        "processed_on": "server",
        "note": "Perhitungan dilakukan di memori lalu dibuang, tidak disimpan di disk.",
    }
