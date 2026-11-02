"""Logika perhitungan waktu sholat harian: fungsi murni di memori.

Modul ini menghitung waktu sholat (Subuh, Terbit, Dzuhur, Ashar, Maghrib, Isya)
berdasarkan hisab astronomis posisi matahari tanpa memanggil layanan luar dan
tanpa koneksi internet.

PENTING SOAL KETEPATAN:
Perhitungan dalam modul ini berbasis rumus astronomi matahari. Hasil hisab dapat
berbeda 1–2 menit dari jadwal resmi Kementerian Agama Republik Indonesia atau
jadwal masjid setempat karena perbedaan pembulatan, elevasi lokal, dan hisab
rukyat kontemporer. Jadwal dan kumandang adzan di masjid setempat tetap menjadi
acuan utama ibadah.

Modul ini murni pustaka standar Python, tidak bergantung pada FastAPI/HTTP,
tidak melakukan I/O disk, dan tidak mencatat koordinat maupun tanggal pengguna ke log.
"""

from __future__ import annotations

import datetime
import math
import re
from typing import Any

from .hijriah import NAMA_BULAN_HIJRIAH, jd_ke_hijriah, masehi_ke_jd

# Batas operasional alat jadwal sholat
MAX_BODY_BYTES = 65536  # 64 KB
MIN_TANGGAL = datetime.date(2000, 1, 1)
MAX_TANGGAL = datetime.date(2100, 12, 31)
MIN_LINTANG = -90.0
MAX_LINTANG = 90.0
MIN_BUJUR = -180.0
MAX_BUJUR = 180.0
MIN_ZONA = 6.0
MAX_ZONA = 10.0

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
INVALID_TANGGAL = "INVALID_TANGGAL"
TANGGAL_DI_LUAR_RENTANG = "TANGGAL_DI_LUAR_RENTANG"
INVALID_KOORDINAT = "INVALID_KOORDINAT"
UNSUPPORTED_METODE = "UNSUPPORTED_METODE"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"

# Nama hari dan bulan Masehi dalam Bahasa Indonesia
NAMA_HARI: tuple[str, ...] = (
    "Senin",
    "Selasa",
    "Rabu",
    "Kamis",
    "Jumat",
    "Sabtu",
    "Minggu",
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

# Catatan jujur mengenai akurasi hisab astronomis
CATATAN_JUJUR = (
    "Waktu sholat dihitung secara mandiri berdasarkan posisi astronomis matahari. "
    "Hasil hisab ini dapat berbeda 1–2 menit dari jadwal resmi Kementerian Agama RI "
    "atau jadwal masjid setempat karena perbedaan pembulatan dan metode hisab. "
    "Jadwal dan kumandang adzan di masjid setempat tetap menjadi acuan utama."
)

# Daftar 44 kota bawaan Indonesia (koordinat patokan tetap)
KOTA: tuple[dict[str, Any], ...] = (
    {"nama": "Banda Aceh", "lintang": 5.5483, "bujur": 95.3238, "zona": 7},
    {"nama": "Medan", "lintang": 3.5952, "bujur": 98.6722, "zona": 7},
    {"nama": "Padang", "lintang": -0.9471, "bujur": 100.4172, "zona": 7},
    {"nama": "Pekanbaru", "lintang": 0.5071, "bujur": 101.4478, "zona": 7},
    {"nama": "Jambi", "lintang": -1.6101, "bujur": 103.6131, "zona": 7},
    {"nama": "Palembang", "lintang": -2.9761, "bujur": 104.7754, "zona": 7},
    {"nama": "Bengkulu", "lintang": -3.8004, "bujur": 102.2655, "zona": 7},
    {"nama": "Bandar Lampung", "lintang": -5.4292, "bujur": 105.2610, "zona": 7},
    {"nama": "Pangkal Pinang", "lintang": -2.1316, "bujur": 106.1169, "zona": 7},
    {"nama": "Batam", "lintang": 1.0456, "bujur": 104.0305, "zona": 7},
    {"nama": "Tanjung Pinang", "lintang": 0.9186, "bujur": 104.4666, "zona": 7},
    {"nama": "Jakarta", "lintang": -6.2088, "bujur": 106.8456, "zona": 7},
    {"nama": "Bogor", "lintang": -6.5971, "bujur": 106.8060, "zona": 7},
    {"nama": "Depok", "lintang": -6.4025, "bujur": 106.7942, "zona": 7},
    {"nama": "Tangerang", "lintang": -6.1781, "bujur": 106.6300, "zona": 7},
    {"nama": "Bekasi", "lintang": -6.2383, "bujur": 106.9756, "zona": 7},
    {"nama": "Bandung", "lintang": -6.9175, "bujur": 107.6191, "zona": 7},
    {"nama": "Cimahi", "lintang": -6.8722, "bujur": 107.5425, "zona": 7},
    {"nama": "Tasikmalaya", "lintang": -7.3274, "bujur": 108.2207, "zona": 7},
    {"nama": "Cirebon", "lintang": -6.7320, "bujur": 108.5523, "zona": 7},
    {"nama": "Semarang", "lintang": -6.9932, "bujur": 110.4203, "zona": 7},
    {"nama": "Solo (Surakarta)", "lintang": -7.5755, "bujur": 110.8243, "zona": 7},
    {"nama": "Yogyakarta", "lintang": -7.7956, "bujur": 110.3695, "zona": 7},
    {"nama": "Surabaya", "lintang": -7.2575, "bujur": 112.7521, "zona": 7},
    {"nama": "Malang", "lintang": -7.9666, "bujur": 112.6326, "zona": 7},
    {"nama": "Kediri", "lintang": -7.8480, "bujur": 112.0178, "zona": 7},
    {"nama": "Denpasar", "lintang": -8.6705, "bujur": 115.2126, "zona": 8},
    {"nama": "Mataram", "lintang": -8.5833, "bujur": 116.1167, "zona": 8},
    {"nama": "Pontianak", "lintang": -0.0263, "bujur": 109.3425, "zona": 7},
    {"nama": "Banjarmasin", "lintang": -3.3186, "bujur": 114.5944, "zona": 8},
    {"nama": "Samarinda", "lintang": -0.5017, "bujur": 117.1536, "zona": 8},
    {"nama": "Balikpapan", "lintang": -1.2379, "bujur": 116.8529, "zona": 8},
    {"nama": "Palangka Raya", "lintang": -2.2080, "bujur": 113.9165, "zona": 7},
    {"nama": "Makassar", "lintang": -5.1477, "bujur": 119.4327, "zona": 8},
    {"nama": "Palu", "lintang": -0.8917, "bujur": 119.8707, "zona": 8},
    {"nama": "Kendari", "lintang": -3.9450, "bujur": 122.4989, "zona": 8},
    {"nama": "Manado", "lintang": 1.4748, "bujur": 124.8421, "zona": 8},
    {"nama": "Gorontalo", "lintang": 0.5435, "bujur": 123.0568, "zona": 8},
    {"nama": "Ambon", "lintang": -3.6954, "bujur": 128.1814, "zona": 9},
    {"nama": "Ternate", "lintang": 0.7900, "bujur": 127.3800, "zona": 9},
    {"nama": "Jayapura", "lintang": -2.5916, "bujur": 140.6690, "zona": 9},
    {"nama": "Sorong", "lintang": -0.8762, "bujur": 131.2558, "zona": 9},
    {"nama": "Manokwari", "lintang": -0.8615, "bujur": 134.0620, "zona": 9},
    {"nama": "Kupang", "lintang": -10.1772, "bujur": 123.6070, "zona": 8},
)

# Konfigurasi metode hisab yang didukung
METODE: dict[str, dict[str, Any]] = {
    "kemenag": {
        "id": "kemenag",
        "nama": "Kemenag RI",
        "sudut_subuh": 20.0,
        "sudut_isya": 18.0,
        "ihtiyat_menit": 2,
        "keterangan": "Standar Kementerian Agama Republik Indonesia (Subuh 20°, Isya 18°, ihtiyat 2 menit).",
    },
    "mwl": {
        "id": "mwl",
        "nama": "Standar dunia (MWL)",
        "sudut_subuh": 18.0,
        "sudut_isya": 17.0,
        "ihtiyat_menit": 0,
        "keterangan": "Muslim World League (Subuh 18°, Isya 17°, ihtiyat 0).",
    },
    "ummalqura": {
        "id": "ummalqura",
        "nama": "Umm al-Qura",
        "sudut_subuh": 18.5,
        "sudut_isya": None,
        "ihtiyat_menit": 0,
        "keterangan": "Umm al-Qura Makkah (Subuh 18,5°, Isya 90 menit setelah Maghrib, ihtiyat 0).",
    },
    "egypt": {
        "id": "egypt",
        "nama": "Mesir",
        "sudut_subuh": 19.5,
        "sudut_isya": 17.5,
        "ihtiyat_menit": 0,
        "keterangan": "Egyptian General Authority of Survey (Subuh 19,5°, Isya 17,5°, ihtiyat 0).",
    },
}


class SholatError(Exception):
    """Galat operasional alat jadwal sholat dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat terstandar."""
        return {
            "ok": False,
            "error": {"code": self.code, "message": self.message},
        }


def get_zona_label(zona: float | int) -> str:
    """Label zona waktu Indonesia atau penanda UTC."""
    if zona == 7 or zona == 7.0:
        return "WIB"
    if zona == 8 or zona == 8.0:
        return "WITA"
    if zona == 9 or zona == 9.0:
        return "WIT"
    sign = "+" if zona >= 0 else "-"
    val = int(zona) if int(zona) == zona else zona
    return f"UTC{sign}{val}"


def _cari_kota(nama: str) -> dict[str, Any] | None:
    """Cari kota berdasarkan nama (toleran huruf besar-kecil dan alias Surakarta)."""
    target = nama.strip().lower()
    if not target:
        return None
    for k in KOTA:
        k_nama = k["nama"].lower()
        if target == k_nama:
            return k
        # Penanganan khusus alias Surakarta / Solo
        if target in ("surakarta", "solo", "solo (surakarta)") and "surakarta" in k_nama:
            return k
    return None


def _format_jam(hours: float) -> str:
    """Format nilai jam desimal menjadi string 'HH:MM' (24 jam, dinormalkan)."""
    total_minutes = int(round(hours * 60.0))
    total_minutes = total_minutes % (24 * 60)
    hh = total_minutes // 60
    mm = total_minutes % 60
    return f"{hh:02d}:{mm:02d}"


def _parse_float_field(val: Any, field_name: str, min_val: float, max_val: float) -> float:
    """Validasi dan parsing bilangan riil untuk koordinat lintang, bujur, dan zona."""
    if val is None:
        raise SholatError(INVALID_KOORDINAT, f"Field '{field_name}' wajib disertakan.", 400)
    try:
        f = float(val)
    except (ValueError, TypeError):
        raise SholatError(INVALID_KOORDINAT, f"Field '{field_name}' harus berupa bilangan riil.", 400)
    if math.isnan(f) or math.isinf(f):
        raise SholatError(INVALID_KOORDINAT, f"Field '{field_name}' tidak valid.", 400)
    if f < min_val or f > max_val:
        raise SholatError(
            INVALID_KOORDINAT,
            f"Field '{field_name}' harus berada di antara {min_val} sampai {max_val}.",
            400,
        )
    return f


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi dan batasan untuk alat jadwal sholat."""
    now_wib = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).date()
    return {
        "kota": list(KOTA),
        "metode": list(METODE.values()),
        "hari_ini": now_wib.isoformat(),
        "lokasi_sendiri": True,
        "catatan": CATATAN_JUJUR,
    }


def hitung_jadwal(payload: Any) -> dict[str, Any]:
    """Hitung 6 waktu sholat harian murni di memori berdasarkan hisab astronomi."""
    if not isinstance(payload, dict):
        raise SholatError(INVALID_REQUEST, "Permintaan harus berupa objek JSON.", 400)

    # 1. Validasi tanggal
    if "tanggal" in payload and payload["tanggal"] is None:
        raise SholatError(INVALID_TANGGAL, "Tanggal tidak boleh bernilai null.", 400)

    raw_tanggal = payload.get("tanggal")
    if raw_tanggal is None or (isinstance(raw_tanggal, str) and not raw_tanggal.strip()):
        # Bawaan: hari ini dalam zona WIB
        dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).date()
    else:
        if not isinstance(raw_tanggal, str):
            raise SholatError(INVALID_TANGGAL, "Format tanggal harus berupa teks YYYY-MM-DD.", 400)
        tanggal_str = raw_tanggal.strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", tanggal_str):
            raise SholatError(
                INVALID_TANGGAL,
                f"Format tanggal '{tanggal_str}' tidak valid. Gunakan format YYYY-MM-DD.",
                400,
            )
        parts = tanggal_str.split("-")
        try:
            dt = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            raise SholatError(
                INVALID_TANGGAL,
                f"Tanggal '{tanggal_str}' tidak valid dalam kalender.",
                400,
            )
        if dt < MIN_TANGGAL or dt > MAX_TANGGAL:
            raise SholatError(
                TANGGAL_DI_LUAR_RENTANG,
                f"Tanggal harus berada dalam rentang tahun {MIN_TANGGAL.year} sampai {MAX_TANGGAL.year}.",
                400,
            )

    # 2. Validasi metode perhitungan
    metode_key = payload.get("metode")
    if metode_key is None or (isinstance(metode_key, str) and not metode_key.strip()):
        metode_key = "kemenag"
    elif not isinstance(metode_key, str):
        raise SholatError(UNSUPPORTED_METODE, "Field 'metode' harus berupa teks.", 400)
    else:
        metode_key = metode_key.strip().lower()

    if metode_key not in METODE:
        raise SholatError(UNSUPPORTED_METODE, f"Metode perhitungan '{metode_key}' tidak didukung.", 400)

    metode_cfg = METODE[metode_key]

    # 3. Validasi kota atau koordinat manual
    raw_kota = payload.get("kota")
    kota_dict: dict[str, Any] | None = None
    has_coords = "lintang" in payload or "bujur" in payload or "zona" in payload

    if raw_kota is not None and isinstance(raw_kota, str) and raw_kota.strip():
        nama_kota = raw_kota.strip()
        kota_dict = _cari_kota(nama_kota)
        if kota_dict is None and not has_coords:
            raise SholatError(
                INVALID_KOORDINAT,
                f"Kota '{nama_kota}' tidak ditemukan dalam daftar bawaan.",
                400,
            )

    if kota_dict is not None and not has_coords:
        nama_tampil = kota_dict["nama"]
        lintang = float(kota_dict["lintang"])
        bujur = float(kota_dict["bujur"])
        zona = float(kota_dict["zona"])
    else:
        # Masukan koordinat manual
        lintang = _parse_float_field(payload.get("lintang"), "lintang", MIN_LINTANG, MAX_LINTANG)
        bujur = _parse_float_field(payload.get("bujur"), "bujur", MIN_BUJUR, MAX_BUJUR)
        zona = _parse_float_field(payload.get("zona"), "zona", MIN_ZONA, MAX_ZONA)
        nama_tampil = (
            raw_kota.strip()
            if (raw_kota and isinstance(raw_kota, str) and raw_kota.strip() not in ("custom", "manual", "lokasi_sendiri"))
            else f"Koordinat ({lintang:.4f}, {bujur:.4f})"
        )

    # 4. Hisab astronomi matahari (NOAA / Meeus)
    jd = masehi_ke_jd(dt.year, dt.month, dt.day)
    n = dt.timetuple().tm_yday
    # Sudut pecahan tahun gamma pada tengah hari
    gamma = 2.0 * math.pi / 365.0 * (n - 1)

    # Persamaan waktu (equation of time) dalam satuan menit
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )

    # Deklinasi matahari dalam radian
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2.0 * gamma)
        + 0.000907 * math.sin(2.0 * gamma)
        - 0.002697 * math.cos(3.0 * gamma)
        + 0.00148 * math.sin(3.0 * gamma)
    )

    lat_rad = math.radians(lintang)

    # Dzuhur astronomis pada bujur setempat
    dzuhur_astronomi = 12.0 + zona - (bujur / 15.0) - (eqtime / 60.0)

    # Fungsi pembantu sudut waktu H dari sudut ketinggian matahari
    def hitung_sudut_waktu(alt_deg: float) -> float | None:
        alt_rad = math.radians(alt_deg)
        denom = math.cos(lat_rad) * math.cos(decl)
        if abs(denom) < 1e-9:
            return None
        cos_h = (math.sin(alt_rad) - math.sin(lat_rad) * math.sin(decl)) / denom
        if cos_h < -1.0 or cos_h > 1.0:
            return None
        return math.degrees(math.acos(cos_h))

    catatan_hasil = CATATAN_JUJUR
    peringatan_kutub: list[str] = []

    ihtiyat = float(metode_cfg["ihtiyat_menit"]) / 60.0

    # a. Syuruq dan Terbenam (sudut -0.833° untuk refraksi atmosfer dan semidiameter matahari)
    h_matahari = hitung_sudut_waktu(-0.833)

    if h_matahari is None:
        syuruq_jam: str | None = None
        maghrib_jam: str | None = None
        peringatan_kutub.append("matahari tidak terbit/terbenam pada tanggal tersebut")
    else:
        syuruq_astronomi = dzuhur_astronomi - (h_matahari / 15.0)
        terbenam_astronomi = dzuhur_astronomi + (h_matahari / 15.0)
        # Syuruq (Terbit) tidak ditambah ihtiyat
        syuruq_jam = _format_jam(syuruq_astronomi)
        # Maghrib ditambah ihtiyat
        maghrib_jam = _format_jam(terbenam_astronomi + ihtiyat)

    # b. Subuh
    sudut_subuh = float(metode_cfg["sudut_subuh"])
    h_subuh = hitung_sudut_waktu(-sudut_subuh)
    if h_subuh is None:
        subuh_jam: str | None = None
        peringatan_kutub.append("waktu fajar tidak terbit pada tanggal tersebut")
    else:
        subuh_astronomi = dzuhur_astronomi - (h_subuh / 15.0)
        subuh_jam = _format_jam(subuh_astronomi + ihtiyat)

    # c. Dzuhur
    dzuhur_jam = _format_jam(dzuhur_astronomi + ihtiyat)

    # d. Ashar (Syafi'i: bayangan 1 kali panjang benda + bayangan tengah hari)
    alt_ashar_rad = math.atan(1.0 / (1.0 + math.tan(abs(lat_rad - decl))))
    denom_ashar = math.cos(lat_rad) * math.cos(decl)
    if abs(denom_ashar) < 1e-9:
        h_ashar = None
    else:
        cos_h_ashar = (math.sin(alt_ashar_rad) - math.sin(lat_rad) * math.sin(decl)) / denom_ashar
        if cos_h_ashar < -1.0 or cos_h_ashar > 1.0:
            h_ashar = None
        else:
            h_ashar = math.degrees(math.acos(cos_h_ashar))

    if h_ashar is None:
        ashar_jam: str | None = None
        peringatan_kutub.append("waktu ashar tidak terjadi pada tanggal tersebut")
    else:
        ashar_astronomi = dzuhur_astronomi + (h_ashar / 15.0)
        ashar_jam = _format_jam(ashar_astronomi + ihtiyat)

    # e. Isya
    if metode_key == "ummalqura":
        # Umm al-Qura: Isya tepat 90 menit setelah Maghrib
        if maghrib_jam is not None:
            m_parts = maghrib_jam.split(":")
            m_tot = int(m_parts[0]) * 60 + int(m_parts[1])
            isya_tot = (m_tot + 90) % (24 * 60)
            isya_jam: str | None = f"{isya_tot // 60:02d}:{isya_tot % 60:02d}"
        else:
            isya_jam = None
    else:
        sudut_isya = float(metode_cfg["sudut_isya"])
        h_isya = hitung_sudut_waktu(-sudut_isya)
        if h_isya is None:
            isya_jam = None
            peringatan_kutub.append("waktu isya tidak terjadi pada tanggal tersebut")
        else:
            isya_astronomi = dzuhur_astronomi + (h_isya / 15.0)
            isya_jam = _format_jam(isya_astronomi + ihtiyat)

    if peringatan_kutub:
        catatan_hasil += " Catatan: " + "; ".join(peringatan_kutub) + "."

    # 5. Tanggal Hijriah (impor rumus dari hijriah.py)
    hy, hm, hd = jd_ke_hijriah(jd)
    hijriah_teks = f"{hd} {NAMA_BULAN_HIJRIAH[hm]} {hy} H"
    hijriah_dict = {
        "hari": hd,
        "bulan": hm,
        "bulan_nama": NAMA_BULAN_HIJRIAH[hm],
        "tahun": hy,
        "teks": hijriah_teks,
    }

    # 6. Format tanggal Masehi teks
    hari_nama = NAMA_HARI[dt.weekday()]
    bulan_masehi_nama = NAMA_BULAN_MASEHI[dt.month]
    tanggal_masehi_teks = f"{hari_nama}, {dt.day} {bulan_masehi_nama} {dt.year}"

    # 7. Susunan 6 waktu sholat berurutan
    waktu_list = [
        {"kunci": "subuh", "nama": "Subuh", "jam": subuh_jam},
        {"kunci": "syuruq", "nama": "Terbit", "jam": syuruq_jam},
        {"kunci": "dzuhur", "nama": "Dzuhur", "jam": dzuhur_jam},
        {"kunci": "ashar", "nama": "Ashar", "jam": ashar_jam},
        {"kunci": "maghrib", "nama": "Maghrib", "jam": maghrib_jam},
        {"kunci": "isya", "nama": "Isya", "jam": isya_jam},
    ]

    return {
        "kota": {
            "nama": nama_tampil,
            "lintang": lintang,
            "bujur": bujur,
            "zona": zona,
            "zona_label": get_zona_label(zona),
        },
        "tanggal": {
            "nilai": dt.isoformat(),
            "teks": tanggal_masehi_teks,
        },
        "tanggal_hijriah": hijriah_dict,
        "metode": {
            "id": metode_cfg["id"],
            "nama": metode_cfg["nama"],
            "ihtiyat_menit": metode_cfg["ihtiyat_menit"],
        },
        "waktu": waktu_list,
        "catatan": catatan_hasil,
    }
