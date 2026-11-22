"""Kalkulator arah kiblat dan jarak ke Makkah: fungsi murni di memori.

Modul ini menghitung initial great-circle bearing dari lokasi pengguna ke Ka'bah
di Makkah (utara sejati) dan jarak garis lurus (lingkaran besar / haversine).
Daftar kota diambil dari data bawaan 44 kota pada modul sholat.

Modul ini murni pustaka standar Python, tidak bergantung pada FastAPI/HTTP,
tidak melakukan I/O disk, dan tidak mencatat koordinat pengguna ke log.
"""

from __future__ import annotations

import math
from typing import Any

from .sholat import KOTA

# Batas operasional & konstanta Ka'bah
KABAH_LINTANG = 21.4225
KABAH_BUJUR = 39.8262
RADIUS_BUMI_KM = 6371.0088

MIN_LINTANG = -90.0
MAX_LINTANG = 90.0
MIN_BUJUR = -180.0
MAX_BUJUR = 180.0
MAX_BODY_BYTES = 65536  # 64 KB

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
INVALID_KOORDINAT = "INVALID_KOORDINAT"
KOTA_TIDAK_DIKENAL = "KOTA_TIDAK_DIKENAL"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"

# 16 arah mata angin dalam Bahasa Indonesia
ARAH_MATA_ANGIN_16: tuple[str, ...] = (
    "utara",
    "utara timur laut",
    "timur laut",
    "timur timur laut",
    "timur",
    "timur tenggara",
    "tenggara",
    "selatan tenggara",
    "selatan",
    "selatan barat daya",
    "barat daya",
    "barat barat daya",
    "barat",
    "barat barat laut",
    "barat laut",
    "utara barat laut",
)

CATATAN_UTARA = (
    "Arah kiblat dihitung dari utara sejati (true north). "
    "Penggunaan kompas magnetik biasa di lapangan memerlukan penyesuaian sudut deklinasi setempat."
)

CATATAN_JUJUR = (
    "Perhitungan ini berbasis koordinat geografis terhadap utara sejati, bukan pembacaan kompas magnetik langsung. "
    "Di lapangan, kompas magnetik memerlukan penyesuaian sudut deklinasi setempat. "
    "Untuk masjid atau musala, ikuti penunjuk arah kiblat yang telah disepakati pengurus atau tim falak setempat."
)


class KiblatError(ValueError):
    """Galat operasional kalkulator kiblat dengan kode galat stabil dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar konsisten dengan alat lain."""
        err = {"code": self.code, "message": self.message}
        return {
            "ok": False,
            "kode": self.code,
            "pesan": self.message,
            "error": err,
            "detail": err,
        }


def _cari_kota(nama: str) -> dict[str, Any] | None:
    """Cari kota berdasarkan nama (tanpa memperhatikan huruf besar/kecil)."""
    target = nama.strip().lower()
    for k in KOTA:
        if k["nama"].lower() == target:
            return k
    return None


def _parse_koordinat(val: Any, nama_field: str, min_val: float, max_val: float) -> float:
    """Konversi nilai koordinat ke float dan validasi rentang."""
    if val is None or isinstance(val, bool):
        raise KiblatError(
            INVALID_KOORDINAT,
            f"Koordinat {nama_field} harus berupa angka.",
            400,
        )

    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            raise KiblatError(
                INVALID_KOORDINAT,
                f"Koordinat {nama_field} tidak valid.",
                400,
            )
        num = float(val)
    elif isinstance(val, str):
        s = val.strip().replace(" ", "").replace(",", ".")
        if not s:
            raise KiblatError(
                INVALID_KOORDINAT,
                f"Koordinat {nama_field} tidak boleh kosong.",
                400,
            )
        try:
            num = float(s)
        except ValueError:
            raise KiblatError(
                INVALID_KOORDINAT,
                f"Koordinat {nama_field} harus berupa angka.",
                400,
            )
        if math.isnan(num) or math.isinf(num):
            raise KiblatError(
                INVALID_KOORDINAT,
                f"Koordinat {nama_field} tidak valid.",
                400,
            )
    else:
        raise KiblatError(
            INVALID_KOORDINAT,
            f"Koordinat {nama_field} harus berupa angka.",
            400,
        )

    if num < min_val or num > max_val:
        raise KiblatError(
            INVALID_KOORDINAT,
            f"Koordinat {nama_field} harus berada di antara {min_val} dan {max_val}.",
            400,
        )
    return num


def dapatkan_mata_angin(bearing: float) -> str:
    """Tentukan nama 16 arah mata angin Bahasa Indonesia dari sudut derajat."""
    val = (bearing + 11.25) % 360.0
    idx = int(val // 22.5) % 16
    return ARAH_MATA_ANGIN_16[idx]


def hitung_arah_dan_jarak(lintang: float, bujur: float) -> tuple[float, str, int]:
    """Hitung bearing awal (lingkaran besar) dan jarak haversine ke Ka'bah."""
    # Jika lokasi berada tepat di Ka'bah
    if abs(lintang - KABAH_LINTANG) < 1e-7 and abs(bujur - KABAH_BUJUR) < 1e-7:
        return 0.0, "utara", 0

    lat_r = math.radians(lintang)
    lat_ka_r = math.radians(KABAH_LINTANG)
    d_lon = math.radians(KABAH_BUJUR - bujur)

    # Great-circle bearing: rumus atan2
    y = math.sin(d_lon) * math.cos(lat_ka_r)
    x = math.cos(lat_r) * math.sin(lat_ka_r) - math.sin(lat_r) * math.cos(lat_ka_r) * math.cos(d_lon)
    bearing = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0

    # Haversine distance
    d_lat = math.radians(KABAH_LINTANG - lintang)
    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(lat_r) * math.cos(lat_ka_r) * (math.sin(d_lon / 2.0) ** 2)
    )
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    jarak = RADIUS_BUMI_KM * c

    arah_derajat = round(bearing, 1)
    if arah_derajat >= 360.0:
        arah_derajat = 0.0

    mata_angin = dapatkan_mata_angin(bearing)
    jarak_km = int(round(jarak))

    return arah_derajat, mata_angin, jarak_km


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batasan dan daftar kota bawaan."""
    kota_list = sorted(
        [
            {
                "nama": k["nama"],
                "lintang": k["lintang"],
                "bujur": k["bujur"],
            }
            for k in KOTA
        ],
        key=lambda item: item["nama"],
    )
    return {
        "kota": kota_list,
        "rentang": {
            "lintang": {"min": MIN_LINTANG, "max": MAX_LINTANG},
            "bujur": {"min": MIN_BUJUR, "max": MAX_BUJUR},
        },
        "kabah": {
            "lintang": KABAH_LINTANG,
            "bujur": KABAH_BUJUR,
        },
        "catatan": CATATAN_JUJUR,
    }


def hitung_kiblat(payload: Any) -> dict[str, Any]:
    """Validasi dan hitung arah kiblat dan jarak ke Ka'bah di memori."""
    if not isinstance(payload, dict):
        raise KiblatError(
            INVALID_REQUEST,
            "Permintaan harus berupa objek JSON.",
            400,
        )

    raw_kota = payload.get("kota")
    has_lintang = "lintang" in payload and payload["lintang"] is not None and str(payload["lintang"]).strip() != ""
    has_bujur = "bujur" in payload and payload["bujur"] is not None and str(payload["bujur"]).strip() != ""

    has_kota = raw_kota is not None and isinstance(raw_kota, str) and raw_kota.strip() != ""

    if not has_kota and not has_lintang and not has_bujur:
        raise KiblatError(
            INVALID_REQUEST,
            "Permintaan harus menyertakan nama kota atau koordinat lintang dan bujur.",
            400,
        )

    if (has_lintang and not has_bujur) or (has_bujur and not has_lintang):
        if not has_kota:
            raise KiblatError(
                INVALID_KOORDINAT,
                "Koordinat lintang dan bujur harus diisi lengkap.",
                400,
            )

    kota_obj = None
    if has_kota:
        nama_input = raw_kota.strip()
        if nama_input.lower() not in ("custom", "manual", "koordinat sendiri", "lokasi sendiri"):
            kota_obj = _cari_kota(nama_input)
            if kota_obj is None and not (has_lintang and has_bujur):
                raise KiblatError(
                    KOTA_TIDAK_DIKENAL,
                    f"Kota '{nama_input}' tidak ditemukan dalam daftar bawaan.",
                    400,
                )

    if has_lintang and has_bujur:
        lintang = _parse_koordinat(payload["lintang"], "lintang", MIN_LINTANG, MAX_LINTANG)
        bujur = _parse_koordinat(payload["bujur"], "bujur", MIN_BUJUR, MAX_BUJUR)
        if (
            kota_obj is not None
            and abs(lintang - float(kota_obj["lintang"])) < 1e-5
            and abs(bujur - float(kota_obj["bujur"])) < 1e-5
        ):
            lokasi = kota_obj["nama"]
        else:
            lokasi = "koordinat sendiri"
    elif kota_obj is not None:
        lintang = float(kota_obj["lintang"])
        bujur = float(kota_obj["bujur"])
        lokasi = kota_obj["nama"]
    else:
        raise KiblatError(
            INVALID_REQUEST,
            "Permintaan harus menyertakan nama kota atau koordinat lintang dan bujur.",
            400,
        )

    arah_derajat, arah_mata_angin, jarak_km = hitung_arah_dan_jarak(lintang, bujur)

    return {
        "arah_derajat": arah_derajat,
        "arah_mata_angin": arah_mata_angin,
        "jarak_km": jarak_km,
        "lintang": round(lintang, 4),
        "bujur": round(bujur, 4),
        "lokasi": lokasi,
        "catatan_utara": CATATAN_UTARA,
    }
