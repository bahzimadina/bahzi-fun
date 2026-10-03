"""Logika konverter zona waktu: fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

import datetime
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Batas operasional
MAX_ZONES = 8
MIN_YEAR = 1900
MAX_YEAR = 2100
MAX_BYTES = 64 * 1024
DEFAULT_START_HOUR = 6
DEFAULT_END_HOUR = 22
WORK_START_HOUR = 8
WORK_END_HOUR = 18

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
INVALID_ZONE = "INVALID_ZONE"
TOO_MANY_ZONES = "TOO_MANY_ZONES"
INVALID_DATE = "INVALID_DATE"
INVALID_TIME = "INVALID_TIME"
INVALID_RANGE = "INVALID_RANGE"
OUT_OF_RANGE = "OUT_OF_RANGE"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"

MODES = ["titik", "banding", "cocok"]


class TimezoneError(ValueError):
    """Galat operasional konversi zona waktu dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


class _ZoneList(list):
    """List zona waktu dengan dukungan pencarian id seperti dictionary."""

    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, str):
            for z in self:
                if z["id"] == item:
                    return z
            raise KeyError(item)
        return super().__getitem__(item)

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, str):
            return any(z["id"] == item for z in self)
        return super().__contains__(item)

    def get(self, item: str, default: Any = None) -> Any:
        if isinstance(item, str):
            for z in self:
                if z["id"] == item:
                    return z
            return default
        return default


ZONES = _ZoneList([
    {"id": "wib", "iana": "Asia/Jakarta", "label": "WIB (Jakarta)"},
    {"id": "wita", "iana": "Asia/Makassar", "label": "WITA (Makassar, Bali)"},
    {"id": "wit", "iana": "Asia/Jayapura", "label": "WIT (Jayapura)"},
    {"id": "singapura", "iana": "Asia/Singapore", "label": "Singapura"},
    {"id": "bangkok", "iana": "Asia/Bangkok", "label": "Bangkok"},
    {"id": "tokyo", "iana": "Asia/Tokyo", "label": "Tokyo"},
    {"id": "seoul", "iana": "Asia/Seoul", "label": "Seoul"},
    {"id": "shanghai", "iana": "Asia/Shanghai", "label": "Shanghai"},
    {"id": "hongkong", "iana": "Asia/Hong_Kong", "label": "Hong Kong"},
    {"id": "delhi", "iana": "Asia/Kolkata", "label": "New Delhi"},
    {"id": "dubai", "iana": "Asia/Dubai", "label": "Dubai"},
    {"id": "mekkah", "iana": "Asia/Riyadh", "label": "Mekkah / Arab Saudi"},
    {"id": "kairo", "iana": "Africa/Cairo", "label": "Kairo"},
    {"id": "istanbul", "iana": "Europe/Istanbul", "label": "Istanbul"},
    {"id": "london", "iana": "Europe/London", "label": "London"},
    {"id": "paris", "iana": "Europe/Paris", "label": "Paris"},
    {"id": "berlin", "iana": "Europe/Berlin", "label": "Berlin"},
    {"id": "newyork", "iana": "America/New_York", "label": "New York"},
    {"id": "losangeles", "iana": "America/Los_Angeles", "label": "Los Angeles"},
    {"id": "saopaulo", "iana": "America/Sao_Paulo", "label": "Sao Paulo"},
    {"id": "sydney", "iana": "Australia/Sydney", "label": "Sydney"},
    {"id": "auckland", "iana": "Pacific/Auckland", "label": "Auckland"},
])

ZONE_MAP = {z["id"]: z for z in ZONES}

FALLBACK_OFFSETS: dict[str, tuple[int, str, str]] = {
    "wib": (420, "UTC+07:00", "WIB"),
    "wita": (480, "UTC+08:00", "WITA"),
    "wit": (540, "UTC+09:00", "WIT"),
    "singapura": (480, "UTC+08:00", "+08"),
    "bangkok": (420, "UTC+07:00", "+07"),
    "tokyo": (540, "UTC+09:00", "JST"),
    "seoul": (540, "UTC+09:00", "KST"),
    "shanghai": (480, "UTC+08:00", "CST"),
    "hongkong": (480, "UTC+08:00", "HKT"),
    "delhi": (330, "UTC+05:30", "IST"),
    "dubai": (240, "UTC+04:00", "+04"),
    "mekkah": (180, "UTC+03:00", "+03"),
    "kairo": (120, "UTC+02:00", "EET"),
    "istanbul": (180, "UTC+03:00", "+03"),
    "london": (0, "UTC+00:00", "GMT"),
    "paris": (60, "UTC+01:00", "CET"),
    "berlin": (60, "UTC+01:00", "CET"),
    "newyork": (-300, "UTC-05:00", "EST"),
    "losangeles": (-480, "UTC-08:00", "PST"),
    "saopaulo": (-180, "UTC-03:00", "-03"),
    "sydney": (600, "UTC+10:00", "AEST"),
    "auckland": (720, "UTC+12:00", "NZST"),
}

NAMA_BULAN_PENDEK = [
    "", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
    "Jul", "Agu", "Sep", "Okt", "Nov", "Des"
]


def _format_offset(offset_min: int) -> str:
    sign = "+" if offset_min >= 0 else "-"
    abs_min = abs(offset_min)
    h = abs_min // 60
    m = abs_min % 60
    return f"UTC{sign}{h:02d}:{m:02d}"


def _format_waktu(dt: datetime.datetime) -> str:
    return f"{dt.day:02d} {NAMA_BULAN_PENDEK[dt.month]} {dt.year}, {dt.strftime('%H:%M')}"


def _get_tz(zid: str, iana: str) -> tuple[datetime.tzinfo, bool, str]:
    try:
        return ZoneInfo(iana), False, ""
    except (ZoneInfoNotFoundError, Exception):
        offset_min, _, _ = FALLBACK_OFFSETS.get(zid, (0, "UTC+00:00", "UTC"))
        tz = datetime.timezone(datetime.timedelta(minutes=offset_min))
        catatan = "Data zona waktu menggunakan offset tetap karena database zona waktu sistem tidak ditemukan."
        return tz, True, catatan


def _parse_date(tanggal_str: Any) -> datetime.date:
    if not isinstance(tanggal_str, str):
        raise TimezoneError(INVALID_DATE, "Format tanggal tidak valid. Gunakan format YYYY-MM-DD.", 400)
    cleaned = tanggal_str.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        raise TimezoneError(INVALID_DATE, "Format tanggal tidak valid. Gunakan format YYYY-MM-DD.", 400)
    try:
        d = datetime.date.fromisoformat(cleaned)
    except ValueError:
        raise TimezoneError(INVALID_DATE, "Format tanggal tidak valid. Gunakan format YYYY-MM-DD.", 400)
    if d.year < MIN_YEAR or d.year > MAX_YEAR:
        raise TimezoneError(OUT_OF_RANGE, f"Tahun harus berada dalam rentang {MIN_YEAR} sampai {MAX_YEAR}.", 400)
    return d


def _parse_time(jam_str: Any) -> tuple[int, int]:
    if not isinstance(jam_str, str):
        raise TimezoneError(INVALID_TIME, "Format jam tidak valid. Gunakan format HH:MM.", 400)
    cleaned = jam_str.strip()
    if not re.fullmatch(r"\d{1,2}:\d{2}", cleaned):
        raise TimezoneError(INVALID_TIME, "Format jam tidak valid. Gunakan format HH:MM.", 400)
    parts = cleaned.split(":")
    h = int(parts[0])
    m = int(parts[1])
    if h < 0 or h > 23 or m < 0 or m > 59:
        raise TimezoneError(INVALID_TIME, "Format jam tidak valid. Gunakan format HH:MM (00:00 sampai 23:59).", 400)
    return h, m


def _nama_kota(label: str) -> str:
    if "(" in label and ")" in label:
        return label.split("(", 1)[1].split(")", 1)[0].split(",", 1)[0].strip()
    if "/" in label:
        return label.split("/", 1)[0].strip()
    return label.strip()


def _calc_geser(dt_tujuan: datetime.datetime, dt_acuan: datetime.datetime) -> tuple[int, str]:
    selisih_hari = (dt_tujuan.date() - dt_acuan.date()).days
    if selisih_hari < 0:
        return -1, "kemarin di zona tujuan"
    if selisih_hari > 0:
        return 1, "besok di zona tujuan"
    return 0, "tanggal sama"


def _calc_selisih(offset_tujuan: int, offset_acuan: int, label_tujuan: str, label_acuan: str) -> tuple[int, str]:
    diff_signed = offset_tujuan - offset_acuan
    abs_min = abs(diff_signed)
    kota_tujuan = _nama_kota(label_tujuan)
    kota_acuan = _nama_kota(label_acuan)

    if abs_min == 0:
        return 0, f"Waktu di {kota_tujuan} sama dengan {kota_acuan}"

    h = abs_min // 60
    m = abs_min % 60
    if h > 0 and m > 0:
        durasi = f"{h} jam {m} menit"
    elif h > 0:
        durasi = f"{h} jam"
    else:
        durasi = f"{m} menit"

    if diff_signed < 0:
        teks = f"{kota_tujuan} {durasi} lebih lambat dari {kota_acuan}"
    else:
        teks = f"{kota_tujuan} {durasi} lebih cepat dari {kota_acuan}"

    return abs_min, teks


def _cek_jam_kerja(hour: int) -> tuple[bool, str]:
    if WORK_START_HOUR <= hour < WORK_END_HOUR:
        return True, "jam kerja"
    if hour < WORK_START_HOUR:
        return False, "di luar jam kerja (dini hari)"
    return False, "di luar jam kerja (malam)"


def _build_moment_dict(zid: str, dt_in_tz: datetime.datetime, is_fallback: bool, fallback_note: str) -> dict[str, Any]:
    z_info = ZONE_MAP[zid]
    offset_delta = dt_in_tz.utcoffset()
    offset_min = int(offset_delta.total_seconds() // 60) if offset_delta else 0
    offset_text = _format_offset(offset_min)
    singkatan = dt_in_tz.tzname() or FALLBACK_OFFSETS.get(zid, (0, "", "UTC"))[2] or offset_text

    dst_val = False if is_fallback else bool(dt_in_tz.dst() and dt_in_tz.dst() != datetime.timedelta(0))

    data: dict[str, Any] = {
        "zona": zid,
        "label": z_info["label"],
        "iana": z_info["iana"],
        "tanggal": dt_in_tz.date().isoformat(),
        "jam": dt_in_tz.strftime("%H:%M"),
        "waktu": _format_waktu(dt_in_tz),
        "offset_menit": offset_min,
        "offset_teks": offset_text,
        "singkatan": singkatan,
        "dst": dst_val,
    }
    if is_fallback and fallback_note:
        data["catatan"] = fallback_note
    return data


def proses_zona(
    mode: Any,
    tanggal: Any = None,
    jam: Any = None,
    dari: Any = None,
    ke: Any = None,
    zona: Any = None,
    jam_mulai: Any = None,
    jam_selesai: Any = None,
) -> dict[str, Any]:
    """Eksekusi konversi zona waktu sesuai mode yang dipilih."""
    if mode is None:
        raise TimezoneError(INVALID_REQUEST, "Field 'mode' wajib diisi.", 400)
    if not isinstance(mode, str):
        raise TimezoneError(INVALID_REQUEST, "Field 'mode' harus berupa teks string.", 400)

    mode_norm = mode.strip().lower()
    if mode_norm not in MODES:
        raise TimezoneError(UNSUPPORTED_MODE, f"Mode '{mode}' tidak didukung. Pilih: {', '.join(MODES)}.", 400)

    if mode_norm == "titik":
        if not tanggal or not jam or not dari or not ke:
            raise TimezoneError(
                INVALID_REQUEST,
                "Field 'tanggal', 'jam', 'dari', dan 'ke' wajib diisi untuk mode titik.",
                400,
            )
        if not isinstance(dari, str) or not isinstance(ke, str):
            raise TimezoneError(INVALID_REQUEST, "Field 'dari' dan 'ke' harus berupa teks.", 400)

        dari_norm = dari.strip().lower()
        ke_norm = ke.strip().lower()

        if dari_norm not in ZONE_MAP:
            raise TimezoneError(INVALID_ZONE, f"Zona waktu '{dari}' tidak dikenal.", 400)
        if ke_norm not in ZONE_MAP:
            raise TimezoneError(INVALID_ZONE, f"Zona waktu '{ke}' tidak dikenal.", 400)

        d = _parse_date(tanggal)
        h, m = _parse_time(jam)

        acuan_tz, acuan_fb, acuan_note = _get_tz(dari_norm, ZONE_MAP[dari_norm]["iana"])
        tujuan_tz, tujuan_fb, tujuan_note = _get_tz(ke_norm, ZONE_MAP[ke_norm]["iana"])

        dt_acuan = datetime.datetime(d.year, d.month, d.day, h, m, tzinfo=acuan_tz)
        dt_tujuan = dt_acuan.astimezone(tujuan_tz)

        acuan_dict = _build_moment_dict(dari_norm, dt_acuan, acuan_fb, acuan_note)
        tujuan_dict = _build_moment_dict(ke_norm, dt_tujuan, tujuan_fb, tujuan_note)

        selisih_menit, selisih_teks = _calc_selisih(
            tujuan_dict["offset_menit"],
            acuan_dict["offset_menit"],
            tujuan_dict["label"],
            acuan_dict["label"],
        )
        geser_hari, geser_teks = _calc_geser(dt_tujuan, dt_acuan)

        return {
            "mode": "titik",
            "acuan": acuan_dict,
            "tujuan": tujuan_dict,
            "selisih_menit": selisih_menit,
            "selisih_teks": selisih_teks,
            "geser_hari": geser_hari,
            "geser_teks": geser_teks,
        }

    if mode_norm == "banding":
        if not tanggal or not jam or not dari or not zona:
            raise TimezoneError(
                INVALID_REQUEST,
                "Field 'tanggal', 'jam', 'dari', dan 'zona' wajib diisi untuk mode banding.",
                400,
            )
        if not isinstance(dari, str) or not isinstance(zona, str):
            raise TimezoneError(INVALID_REQUEST, "Field 'dari' dan 'zona' harus berupa teks.", 400)

        dari_norm = dari.strip().lower()
        if dari_norm not in ZONE_MAP:
            raise TimezoneError(INVALID_ZONE, f"Zona waktu '{dari}' tidak dikenal.", 400)

        raw_zones = [z.strip().lower() for z in zona.split(",") if z.strip()]
        if not raw_zones:
            raise TimezoneError(INVALID_REQUEST, "Pilih minimal satu zona tujuan.", 400)
        if len(raw_zones) > MAX_ZONES:
            raise TimezoneError(
                TOO_MANY_ZONES,
                f"Jumlah zona ({len(raw_zones)}) melebihi batas maksimal {MAX_ZONES} zona.",
                400,
            )

        for zid in raw_zones:
            if zid not in ZONE_MAP:
                raise TimezoneError(INVALID_ZONE, f"Zona waktu '{zid}' tidak dikenal.", 400)

        d = _parse_date(tanggal)
        h, m = _parse_time(jam)

        acuan_tz, acuan_fb, acuan_note = _get_tz(dari_norm, ZONE_MAP[dari_norm]["iana"])
        dt_acuan = datetime.datetime(d.year, d.month, d.day, h, m, tzinfo=acuan_tz)
        acuan_dict = _build_moment_dict(dari_norm, dt_acuan, acuan_fb, acuan_note)

        daftar = []
        for zid in raw_zones:
            z_tz, z_fb, z_note = _get_tz(zid, ZONE_MAP[zid]["iana"])
            dt_z = dt_acuan.astimezone(z_tz)
            item = _build_moment_dict(zid, dt_z, z_fb, z_note)
            geser_hari, geser_teks = _calc_geser(dt_z, dt_acuan)
            jam_kerja, keterangan = _cek_jam_kerja(dt_z.hour)

            item["geser_hari"] = geser_hari
            item["geser_teks"] = geser_teks
            item["jam_kerja"] = jam_kerja
            item["keterangan"] = keterangan
            daftar.append(item)

        return {
            "mode": "banding",
            "acuan": acuan_dict,
            "daftar": daftar,
        }

    # mode_norm == "cocok"
    if not tanggal or not dari or not zona:
        raise TimezoneError(
            INVALID_REQUEST,
            "Field 'tanggal', 'dari', dan 'zona' wajib diisi untuk mode cocok.",
            400,
        )
    if not isinstance(dari, str) or not isinstance(zona, str):
        raise TimezoneError(INVALID_REQUEST, "Field 'dari' dan 'zona' harus berupa teks.", 400)

    dari_norm = dari.strip().lower()
    if dari_norm not in ZONE_MAP:
        raise TimezoneError(INVALID_ZONE, f"Zona waktu '{dari}' tidak dikenal.", 400)

    raw_zones = [z.strip().lower() for z in zona.split(",") if z.strip()]
    if not raw_zones:
        raise TimezoneError(INVALID_REQUEST, "Pilih minimal satu zona tujuan.", 400)
    if len(raw_zones) > MAX_ZONES:
        raise TimezoneError(
            TOO_MANY_ZONES,
            f"Jumlah zona ({len(raw_zones)}) melebihi batas maksimal {MAX_ZONES} zona.",
            400,
        )

    for zid in raw_zones:
        if zid not in ZONE_MAP:
            raise TimezoneError(INVALID_ZONE, f"Zona waktu '{zid}' tidak dikenal.", 400)

    # Validasi jam mulai dan jam selesai
    h_mulai = DEFAULT_START_HOUR
    h_selesai = DEFAULT_END_HOUR

    if jam_mulai is not None and str(jam_mulai).strip() != "":
        try:
            val_s = str(jam_mulai).strip()
            h_mulai = int(val_s.split(":")[0]) if ":" in val_s else int(val_s)
        except ValueError:
            raise TimezoneError(INVALID_RANGE, "Jam mulai harus berupa angka 0 sampai 23.", 400)

    if jam_selesai is not None and str(jam_selesai).strip() != "":
        try:
            val_s = str(jam_selesai).strip()
            h_selesai = int(val_s.split(":")[0]) if ":" in val_s else int(val_s)
        except ValueError:
            raise TimezoneError(INVALID_RANGE, "Jam selesai harus berupa angka 0 sampai 23.", 400)

    if h_mulai < 0 or h_mulai > 23 or h_selesai < 0 or h_selesai > 23:
        raise TimezoneError(INVALID_RANGE, "Jam mulai dan selesai harus berada dalam rentang 0 sampai 23.", 400)

    if h_mulai >= h_selesai:
        raise TimezoneError(INVALID_RANGE, "Jam mulai harus lebih awal dari jam selesai.", 400)

    d = _parse_date(tanggal)
    acuan_tz, acuan_fb, acuan_note = _get_tz(dari_norm, ZONE_MAP[dari_norm]["iana"])

    # Kumpulkan seluruh zona peserta (acuan + zona tujuan tanpa duplikasi acuan)
    semua_zona_ids = [dari_norm] + [z for z in raw_zones if z != dari_norm]
    total_peserta = len(semua_zona_ids)

    # Dapatkan tzinfo untuk setiap zona
    zone_tzs = {}
    for zid in semua_zona_ids:
        z_tz, _, _ = _get_tz(zid, ZONE_MAP[zid]["iana"])
        zone_tzs[zid] = z_tz

    rekomendasi = []
    for h in range(h_mulai, h_selesai + 1):
        dt_acuan_hour = datetime.datetime(d.year, d.month, d.day, h, 0, tzinfo=acuan_tz)
        jam_acuan_str = f"{h:02d}:00"
        singkatan_acuan = dt_acuan_hour.tzname() or FALLBACK_OFFSETS.get(dari_norm, (0, "", "UTC"))[2]
        jam_acuan_teks = f"{jam_acuan_str} {singkatan_acuan}".strip()

        detail = []
        cocok_count = 0
        for zid in semua_zona_ids:
            dt_z = dt_acuan_hour.astimezone(zone_tzs[zid])
            jk, ket = _cek_jam_kerja(dt_z.hour)
            if jk:
                cocok_count += 1
            detail.append({
                "zona": zid,
                "label": ZONE_MAP[zid]["label"],
                "jam": dt_z.strftime("%H:%M"),
                "tanggal": dt_z.date().isoformat(),
                "jam_kerja": jk,
                "keterangan": ket,
            })

        rekomendasi.append({
            "jam_acuan": jam_acuan_str,
            "jam_acuan_teks": jam_acuan_teks,
            "cocok": cocok_count,
            "total": total_peserta,
            "semua_jam_kerja": (cocok_count == total_peserta),
            "detail": detail,
            "_h": h,
        })

    # Urutkan: paling banyak masuk jam kerja, lalu jam paling awal
    rekomendasi.sort(key=lambda r: (-r["cocok"], r["_h"]))
    for r in rekomendasi:
        del r["_h"]

    dt_acuan_sample = datetime.datetime(d.year, d.month, d.day, 12, 0, tzinfo=acuan_tz)
    offset_delta = dt_acuan_sample.utcoffset()
    offset_min = int(offset_delta.total_seconds() // 60) if offset_delta else 0
    singkatan_acuan = dt_acuan_sample.tzname() or FALLBACK_OFFSETS.get(dari_norm, (0, "", "UTC"))[2]

    acuan_info = {
        "zona": dari_norm,
        "label": ZONE_MAP[dari_norm]["label"],
        "iana": ZONE_MAP[dari_norm]["iana"],
        "tanggal": d.isoformat(),
        "offset_teks": _format_offset(offset_min),
        "singkatan": singkatan_acuan,
    }

    return {
        "mode": "cocok",
        "acuan": acuan_info,
        "rentang": {
            "jam_mulai": f"{h_mulai:02d}:00",
            "jam_selesai": f"{h_selesai:02d}:00",
        },
        "rekomendasi": rekomendasi,
        "catatan": "Perhitungan jam kerja menggunakan standar 08:00 sampai 17:59 waktu setempat pada masing-masing zona.",
    }


def limits_payload() -> dict[str, Any]:
    """Mengembalikan batas operasional dan daftar zona untuk Konverter Zona Waktu."""
    return {
        "modes": [
            {"id": "titik", "label": "Konversi titik waktu", "desc": "Konversi satu momen waktu dari zona acuan ke zona tujuan"},
            {"id": "banding", "label": "Bandingkan beberapa kota", "desc": "Lihat jam yang sama di beberapa kota sekaligus"},
            {"id": "cocok", "label": "Cari jam rapat", "desc": "Cari jam kerja yang cocok antar zona waktu"},
        ],
        "zones": [dict(z) for z in ZONES],
        "max_zones": MAX_ZONES,
        "min_year": MIN_YEAR,
        "max_year": MAX_YEAR,
        "default_start_hour": DEFAULT_START_HOUR,
        "default_end_hour": DEFAULT_END_HOUR,
        "work_start_hour": WORK_START_HOUR,
        "work_end_hour": WORK_END_HOUR,
        "max_bytes": MAX_BYTES,
        "processed_on": "server",
        "subjudul": "Konversi titik waktu, bandingkan beberapa kota, atau cari jam rapat yang cocok",
        "subtitle": "Konversi titik waktu, bandingkan beberapa kota, atau cari jam rapat yang cocok",
        "note": "Perhitungan dilakukan di memori lalu dibuang, tidak disimpan di disk. Data zona waktu memakai data IANA yang tertanam di server.",
    }
