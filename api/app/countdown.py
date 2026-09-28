"""Logika hitung mundur (Countdown Timer): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

# Batas operasional
MAX_INPUT_CHARS = 40
MIN_YEAR = 1900
MAX_YEAR = 2100
MAX_AMOUNT = 100000
MAX_BYTES = 65536
DEFAULT_JAM = "00:00"

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

# Satuan durasi
SATUAN: list[dict[str, Any]] = [
    {"id": "menit", "label": "Menit", "detik": 60},
    {"id": "jam", "label": "Jam", "detik": 3600},
    {"id": "hari", "label": "Hari", "detik": 86400},
    {"id": "minggu", "label": "Minggu", "detik": 604800},
]
SATUAN_MAP = {s["id"]: s["detik"] for s in SATUAN}

# Mode yang didukung
MODES: list[dict[str, Any]] = [
    {"id": "ke_momen", "label": "Hitung mundur ke waktu tertentu", "butuh": ["tanggal", "jam"]},
    {"id": "dari_durasi", "label": "Timer dari sekarang (durasi)", "butuh": ["jumlah", "satuan"]},
]

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NO_DATE = "NO_DATE"
INVALID_DATE = "INVALID_DATE"
OUT_OF_RANGE = "OUT_OF_RANGE"
INVALID_TIME = "INVALID_TIME"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
INVALID_AMOUNT = "INVALID_AMOUNT"
INVALID_UNIT = "INVALID_UNIT"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class CountdownError(ValueError):
    """Galat operasional hitung mundur dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


def parse_date(value: Any, field_name: str = "tanggal") -> date:
    """Validasi dan parsing string tanggal ke objek datetime.date.

    Aturan pembacaan tanggal:
    - Spasi ujung dibuang. Masukan kosong -> NO_DATE 400.
    - Panjang lebih dari MAX_INPUT_CHARS -> OUT_OF_RANGE 400.
    - Pemisah harus seragam: pakai '-' semua atau '/' semua. Campur -> INVALID_DATE 400.
    - Tiga bagian, urutan ditentukan:
      kalau bagian pertama 4 digit -> tahun dulu (YYYY-MM-DD);
      selain itu hari dulu (DD-MM-YYYY).
      Tahun 2 digit -> INVALID_DATE 400 (jangan menebak abad).
    - Bulan dan hari harus bilangan bulat 1-2 digit; selain itu INVALID_DATE 400.
    - Tanggal harus tanggal kalender yang benar (termasuk tahun kabisat) lewat datetime.date(y, m, d);
      kalau tidak valid -> INVALID_DATE 400.
    - Tahun di luar MIN_YEAR..MAX_YEAR -> OUT_OF_RANGE 400 dengan pesan rentang 1900 sampai 2100.
    """
    if value is None:
        raise CountdownError(NO_DATE, f"Tanggal '{field_name}' wajib diisi.", 400)

    if not isinstance(value, str):
        raise CountdownError(INVALID_REQUEST, f"Field '{field_name}' harus berupa teks string.", 400)

    cleaned = value.strip()
    if not cleaned:
        raise CountdownError(NO_DATE, f"Tanggal '{field_name}' wajib diisi.", 400)

    if len(cleaned) > MAX_INPUT_CHARS:
        raise CountdownError(
            OUT_OF_RANGE,
            f"Panjang masukan ({len(cleaned)} karakter) melebihi batas {MAX_INPUT_CHARS} karakter.",
            400,
        )

    has_dash = "-" in cleaned
    has_slash = "/" in cleaned

    if has_dash and has_slash:
        raise CountdownError(
            INVALID_DATE,
            "Format pemisah tanggal tidak seragam. Gunakan '-' semua atau '/' semua.",
            400,
        )

    if not has_dash and not has_slash:
        raise CountdownError(
            INVALID_DATE,
            "Format tanggal tidak valid. Gunakan pemisah '-' atau '/'.",
            400,
        )

    sep = "-" if has_dash else "/"
    parts = cleaned.split(sep)
    if len(parts) != 3:
        raise CountdownError(
            INVALID_DATE,
            "Format tanggal harus terdiri dari 3 bagian: tahun, bulan, dan hari.",
            400,
        )

    if not all(p.isdigit() for p in parts):
        raise CountdownError(
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
            raise CountdownError(
                INVALID_DATE,
                "Bulan dan hari harus berupa bilangan 1-2 digit.",
                400,
            )
    else:
        # Format DD-MM-YYYY
        if len(p2) == 2:
            raise CountdownError(
                INVALID_DATE,
                "Tahun harus ditulis lengkap 4 digit (jangan gunakan 2 digit).",
                400,
            )
        if len(p2) != 4:
            raise CountdownError(
                INVALID_DATE,
                "Format tahun harus 4 digit.",
                400,
            )
        if not (1 <= len(p0) <= 2 and 1 <= len(p1) <= 2):
            raise CountdownError(
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
        raise CountdownError(
            OUT_OF_RANGE,
            f"Tahun {y} di luar rentang yang didukung ({MIN_YEAR} sampai {MAX_YEAR}).",
            400,
        )

    if m < 1 or m > 12:
        raise CountdownError(
            INVALID_DATE,
            "Bulan harus antara 1 sampai 12.",
            400,
        )

    try:
        parsed_dt = date(y, m, d)
    except ValueError:
        raise CountdownError(
            INVALID_DATE,
            "Tanggal tidak valid pada kalender.",
            400,
        )

    return parsed_dt


def parse_time(value: Any, default: str = DEFAULT_JAM) -> tuple[int, int, str]:
    """Validasi dan parsing format jam 'HH:MM'.

    Format harus tepat HH:MM (dua digit jam 00..23 dan dua digit menit 00..59).
    Jika value None atau string kosong setelah strip -> gunakan default '00:00'.
    Mengembalikan tuple: (hour, minute, formatted_str).
    """
    if value is None:
        t_str = default
    elif not isinstance(value, str):
        raise CountdownError(INVALID_REQUEST, "Field 'jam' harus berupa teks string.", 400)
    else:
        cleaned = value.strip()
        if not cleaned:
            t_str = default
        else:
            if len(cleaned) > MAX_INPUT_CHARS:
                raise CountdownError(
                    OUT_OF_RANGE,
                    f"Panjang masukan jam melebihi batas {MAX_INPUT_CHARS} karakter.",
                    400,
                )
            t_str = cleaned

    parts = t_str.split(":")
    if len(parts) != 2:
        raise CountdownError(
            INVALID_TIME,
            "Format jam tidak valid. Gunakan format 'HH:MM' (contoh: 07:00).",
            400,
        )

    h_str, m_str = parts
    # Harus tepat 2 digit jam dan 2 digit menit (mis. "6:5" ditolak)
    if len(h_str) != 2 or len(m_str) != 2 or not h_str.isdigit() or not m_str.isdigit():
        raise CountdownError(
            INVALID_TIME,
            "Format jam harus 2 digit jam dan 2 digit menit 'HH:MM' (00:00 sampai 23:59).",
            400,
        )

    hour = int(h_str)
    minute = int(m_str)

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise CountdownError(
            INVALID_TIME,
            f"Jam '{t_str}' tidak valid. Jam harus antara 00:00 sampai 23:59.",
            400,
        )

    return hour, minute, f"{hour:02d}:{minute:02d}"


def parse_amount(value: Any) -> int:
    """Validasi jumlah durasi: bilangan bulat antara 0 sampai MAX_AMOUNT (100000)."""
    if value is None:
        raise CountdownError(INVALID_REQUEST, "Field 'jumlah' wajib diisi untuk mode durasi.", 400)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        num = value
    elif isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise CountdownError(INVALID_REQUEST, "Field 'jumlah' tidak boleh kosong.", 400)
        if len(cleaned) > MAX_INPUT_CHARS:
            raise CountdownError(
                OUT_OF_RANGE,
                f"Panjang masukan jumlah melebihi batas {MAX_INPUT_CHARS} karakter.",
                400,
            )
        try:
            if "." in cleaned or "," in cleaned:
                raise ValueError
            num = int(cleaned)
        except ValueError:
            raise CountdownError(
                INVALID_AMOUNT,
                "Jumlah harus berupa bilangan bulat antara 0 sampai 100000.",
                400,
            )
    else:
        raise CountdownError(INVALID_REQUEST, "Field 'jumlah' tidak valid.", 400)

    if not isinstance(num, int):
        raise CountdownError(
            INVALID_AMOUNT,
            "Jumlah harus berupa bilangan bulat antara 0 sampai 100000.",
            400,
        )

    if num < 0 or num > MAX_AMOUNT:
        raise CountdownError(
            INVALID_AMOUNT,
            f"Jumlah {num} di luar rentang 0 sampai {MAX_AMOUNT}.",
            400,
        )

    return num


def parse_unit(value: Any) -> tuple[str, int]:
    """Validasi satuan durasi: salah satu dari menit, jam, hari, minggu."""
    if value is None:
        raise CountdownError(INVALID_REQUEST, "Field 'satuan' wajib diisi untuk mode durasi.", 400)

    if not isinstance(value, str):
        raise CountdownError(INVALID_REQUEST, "Field 'satuan' harus berupa teks string.", 400)

    unit = value.strip().lower()
    if unit not in SATUAN_MAP:
        valid_units = ", ".join(SATUAN_MAP.keys())
        raise CountdownError(
            INVALID_UNIT,
            f"Satuan '{value}' tidak dikenali. Pilih salah satu: {valid_units}.",
            400,
        )

    return unit, SATUAN_MAP[unit]


def _format_compact_duration(d: int, h: int, m: int, s: int) -> str:
    """Format durasi ringkas dalam bahasa Indonesia (mis. '94 hari 5 menit', '2 hari')."""
    parts = []
    if d > 0:
        parts.append(f"{d} hari")
    if h > 0:
        parts.append(f"{h} jam")
    if m > 0:
        parts.append(f"{m} menit")
    if s > 0 and d == 0:
        parts.append(f"{s} detik")
    if not parts:
        if s > 0:
            parts.append(f"{s} detik")
    return " ".join(parts[:2]) if len(parts) > 2 else " ".join(parts)


def compute_countdown(
    mode: Any,
    tanggal: Any = None,
    jam: Any = None,
    jumlah: Any = None,
    satuan: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Hitung mundur murni di memori berdasarkan mode pilihan."""
    if mode is None:
        raise CountdownError(INVALID_REQUEST, "Field 'mode' wajib diisi.", 400)

    if not isinstance(mode, str):
        raise CountdownError(INVALID_REQUEST, "Field 'mode' harus berupa teks string.", 400)

    mode_norm = mode.strip()
    valid_mode_ids = [m["id"] for m in MODES]
    if mode_norm not in valid_mode_ids:
        raise CountdownError(
            UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak dikenali. Pilih salah satu: {', '.join(valid_mode_ids)}.",
            400,
        )

    # Waktu acuan server WIB (detik dan mikrodetik dipotong ke 0)
    if now is None:
        raw_now = datetime.now(WIB)
    else:
        if now.tzinfo is None:
            raw_now = now.replace(tzinfo=WIB)
        else:
            raw_now = now.astimezone(WIB)
    server_now = raw_now.replace(second=0, microsecond=0)

    durasi_detik = 0

    if mode_norm == "ke_momen":
        target_date = parse_date(tanggal, "tanggal")
        hour, minute, _ = parse_time(jam, DEFAULT_JAM)
        target = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour,
            minute,
            0,
            tzinfo=WIB,
        )
    elif mode_norm == "dari_durasi":
        amt = parse_amount(jumlah)
        _, unit_seconds = parse_unit(satuan)
        durasi_detik = amt * unit_seconds
        target = server_now + timedelta(seconds=durasi_detik)
        if target.year > MAX_YEAR:
            raise CountdownError(
                OUT_OF_RANGE,
                f"Target tahun {target.year} di luar rentang yang didukung (maksimal {MAX_YEAR}).",
                400,
            )
    else:
        raise CountdownError(UNSUPPORTED_MODE, f"Mode '{mode_norm}' tidak dikenali.", 400)

    target_tanggal = target.strftime("%Y-%m-%d")
    target_jam = target.strftime("%H:%M")
    target_hari = HARI[target.weekday()]
    target_tanggal_teks = f"{target.day} {BULAN[target.month - 1]} {target.year}"
    target_label = f"{target_hari}, {target_tanggal_teks}, {target_jam} WIB"

    diff_seconds = int((target - server_now).total_seconds())

    if diff_seconds < 0:
        lewat = True
        sisa_detik = 0
        lewat_detik = -diff_seconds
        l_hari = lewat_detik // 86400
        rem = lewat_detik % 86400
        l_jam = rem // 3600
        rem = rem % 3600
        l_menit = rem // 60
        l_detik = rem % 60
        dur_lewat_str = _format_compact_duration(l_hari, l_jam, l_menit, l_detik)
        sisa_teks = f"sudah lewat {dur_lewat_str}"
        catatan = (
            f"Waktu ini sudah lewat {dur_lewat_str}. Dihitung dari waktu server WIB sebagai titik awal; "
            "hitungan berdetak di peramban dan wajar bila bergeser beberapa detik bila jam perangkat berbeda."
        )
        hari = 0
        jam_part = 0
        menit = 0
        detik = 0
        total_jam = 0
        total_menit = 0
    elif diff_seconds == 0:
        lewat = False
        sisa_detik = 0
        lewat_detik = 0
        sisa_teks = "kurang dari 1 detik lagi"
        catatan = (
            "Dihitung dari waktu server WIB sebagai titik awal; "
            "hitungan berdetak di peramban dan wajar bila bergeser beberapa detik bila jam perangkat berbeda."
        )
        hari = 0
        jam_part = 0
        menit = 0
        detik = 0
        total_jam = 0
        total_menit = 0
    else:
        lewat = False
        sisa_detik = diff_seconds
        lewat_detik = 0
        hari = sisa_detik // 86400
        rem = sisa_detik % 86400
        jam_part = rem // 3600
        rem = rem % 3600
        menit = rem // 60
        detik = rem % 60
        total_jam = sisa_detik // 3600
        total_menit = sisa_detik // 60
        dur_sisa_str = _format_compact_duration(hari, jam_part, menit, detik)
        sisa_teks = f"{dur_sisa_str} lagi"
        catatan = (
            "Dihitung dari waktu server WIB sebagai titik awal; "
            "hitungan berdetak di peramban dan wajar bila bergeser beberapa detik bila jam perangkat berbeda."
        )

    return {
        "mode": mode_norm,
        "zona": "WIB (UTC+7)",
        "server_now": server_now.isoformat(),
        "target": target.isoformat(),
        "target_tanggal": target_tanggal,
        "target_jam": target_jam,
        "target_hari": target_hari,
        "target_tanggal_teks": target_tanggal_teks,
        "target_label": target_label,
        "lewat": lewat,
        "sisa_detik": sisa_detik,
        "lewat_detik": lewat_detik,
        "hari": hari,
        "jam": jam_part,
        "menit": menit,
        "detik": detik,
        "total_jam": total_jam,
        "total_menit": total_menit,
        "sisa_teks": sisa_teks,
        "durasi_detik": durasi_detik,
        "catatan": catatan,
    }


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional dan daftar mode hitung mundur."""
    return {
        "tool": "countdown",
        "zona": "WIB (UTC+7)",
        "min_year": MIN_YEAR,
        "max_year": MAX_YEAR,
        "max_input_chars": MAX_INPUT_CHARS,
        "max_bytes": MAX_BYTES,
        "default_jam": DEFAULT_JAM,
        "modes": [
            {"id": "ke_momen", "label": "Hitung mundur ke waktu tertentu", "butuh": ["tanggal", "jam"]},
            {"id": "dari_durasi", "label": "Timer dari sekarang (durasi)", "butuh": ["jumlah", "satuan"]},
        ],
        "satuan": [
            {"id": "menit", "label": "Menit", "detik": 60},
            {"id": "jam", "label": "Jam", "detik": 3600},
            {"id": "hari", "label": "Hari", "detik": 86400},
            {"id": "minggu", "label": "Minggu", "detik": 604800},
        ],
    }
