"""Kalkulator kehamilan: perkiraan hari perkiraan lahir (HPL) dan usia kehamilan dari HPHT.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Data tanggal tidak pernah disimpan di disk.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any

try:
    from zoneinfo import ZoneInfo
    JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
except Exception:
    from datetime import timezone
    JAKARTA_TZ = timezone(timedelta(hours=7))

# Batas operasional
MIN_SIKLUS = 21
MAX_SIKLUS = 40
DEFAULT_SIKLUS = 28
MAX_USIA_MINGGU = 45

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
INVALID_DATE = "INVALID_DATE"
FUTURE_DATE = "FUTURE_DATE"
TOO_OLD = "TOO_OLD"
INVALID_CYCLE = "INVALID_CYCLE"

HARI = [
    "Senin",
    "Selasa",
    "Rabu",
    "Kamis",
    "Jumat",
    "Sabtu",
    "Minggu",
]

BULAN = [
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
]


class KehamilanError(ValueError):
    """Galat operasional kalkulator kehamilan dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


def limits_payload() -> dict[str, Any]:
    """Mengembalikan batas operasional dan nilai bawaan kalkulator kehamilan."""
    return {
        "min_siklus": MIN_SIKLUS,
        "max_siklus": MAX_SIKLUS,
        "default_siklus": DEFAULT_SIKLUS,
        "max_usia_minggu": MAX_USIA_MINGGU,
        "zona_waktu": "Asia/Jakarta",
        "catatan": (
            "Perkiraan memakai rumus Naegele dari HPHT, bukan pengganti pemeriksaan dokter atau USG. "
            "Hasil terbaik bila tanggal HPHT diingat dengan tepat."
        ),
    }


def hitung(
    hpht: str | None,
    siklus: int | str | None = 28,
    tanggal: str | None = None,
) -> dict[str, Any]:
    """Hitung perkiraan hari lahir (HPL) dan usia kehamilan dari HPHT."""
    if hpht is None or (isinstance(hpht, str) and not hpht.strip()):
        raise KehamilanError(
            INVALID_REQUEST,
            "Field 'hpht' wajib diisi. Masukkan tanggal hari pertama haid terakhir (HPHT).",
            400,
        )

    hpht_str = str(hpht).strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", hpht_str):
        raise KehamilanError(
            INVALID_DATE,
            "Format tanggal HPHT tidak valid. Gunakan format YYYY-MM-DD (misalnya 2026-05-01).",
            400,
        )

    try:
        hpht_dt = datetime.strptime(hpht_str, "%Y-%m-%d").date()
    except ValueError:
        raise KehamilanError(
            INVALID_DATE,
            "Tanggal HPHT tidak valid atau tidak ada di kalender. Gunakan format YYYY-MM-DD.",
            400,
        )

    # Validasi siklus
    if siklus is None or (isinstance(siklus, str) and siklus.strip() == ""):
        siklus_int = DEFAULT_SIKLUS
    elif isinstance(siklus, bool):
        raise KehamilanError(
            INVALID_CYCLE,
            "Panjang siklus haid harus berupa bilangan bulat antara 21 sampai 40 hari.",
            400,
        )
    else:
        if isinstance(siklus, str) and "." in siklus:
            raise KehamilanError(
                INVALID_CYCLE,
                "Panjang siklus haid harus berupa bilangan bulat antara 21 sampai 40 hari.",
                400,
            )
        try:
            siklus_int = int(siklus)
        except (ValueError, TypeError):
            raise KehamilanError(
                INVALID_CYCLE,
                "Panjang siklus haid harus berupa bilangan bulat antara 21 sampai 40 hari.",
                400,
            )
        if siklus_int < MIN_SIKLUS or siklus_int > MAX_SIKLUS:
            raise KehamilanError(
                INVALID_CYCLE,
                f"Panjang siklus haid harus antara {MIN_SIKLUS} sampai {MAX_SIKLUS} hari.",
                400,
            )

    # Validasi tanggal acuan
    if tanggal is None or (isinstance(tanggal, str) and not tanggal.strip()):
        ref_dt = datetime.now(JAKARTA_TZ).date()
    else:
        ref_str = str(tanggal).strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", ref_str):
            raise KehamilanError(
                INVALID_DATE,
                "Format tanggal acuan tidak valid. Gunakan format YYYY-MM-DD.",
                400,
            )
        try:
            ref_dt = datetime.strptime(ref_str, "%Y-%m-%d").date()
        except ValueError:
            raise KehamilanError(
                INVALID_DATE,
                "Tanggal acuan tidak valid atau tidak ada di kalender. Gunakan format YYYY-MM-DD.",
                400,
            )

    if hpht_dt > ref_dt:
        raise KehamilanError(
            FUTURE_DATE,
            "Tanggal HPHT tidak boleh di masa depan (setelah tanggal acuan).",
            400,
        )

    total_hari = (ref_dt - hpht_dt).days
    usia_minggu = total_hari // 7
    usia_hari = total_hari % 7

    if usia_minggu > MAX_USIA_MINGGU:
        raise KehamilanError(
            TOO_OLD,
            f"Usia kehamilan ({usia_minggu} minggu) melebihi batas maksimal {MAX_USIA_MINGGU} minggu.",
            400,
        )

    usia_teks = f"{usia_minggu} minggu {usia_hari} hari"

    if usia_minggu < 14:
        trimester = 1
        trimester_label = "Trimester pertama"
    elif usia_minggu < 28:
        trimester = 2
        trimester_label = "Trimester kedua"
    else:
        trimester = 3
        trimester_label = "Trimester ketiga"

    hpl_dt = hpht_dt + timedelta(days=280 + (siklus_int - 28))
    hpl_hari = HARI[hpl_dt.weekday()]
    hpl_bulan = BULAN[hpl_dt.month]
    hpl_teks = f"{hpl_hari}, {hpl_dt.day} {hpl_bulan} {hpl_dt.year}"

    sisa_hari = (hpl_dt - ref_dt).days
    if sisa_hari > 0:
        sisa_teks = f"{sisa_hari} hari lagi"
    elif sisa_hari == 0:
        sisa_teks = "Hari ini perkiraan lahir"
    else:
        sisa_teks = f"Lewat {abs(sisa_hari)} hari"

    cukup_bulan_mulai_dt = hpl_dt - timedelta(days=21)   # 37 minggu
    cukup_bulan_selesai_dt = hpl_dt + timedelta(days=14) # 42 minggu

    persen_raw = (total_hari / 280) * 100
    persen_clamped = max(0.0, min(100.0, persen_raw))
    persen = round(persen_clamped, 1)

    catatan = "Perkiraan memakai rumus Naegele dari HPHT, bukan pengganti pemeriksaan dokter atau USG."

    return {
        "hpht": hpht_dt.isoformat(),
        "tanggal_acuan": ref_dt.isoformat(),
        "siklus": siklus_int,
        "usia_minggu": usia_minggu,
        "usia_hari": usia_hari,
        "usia_teks": usia_teks,
        "total_hari": total_hari,
        "trimester": trimester,
        "trimester_label": trimester_label,
        "hpl": hpl_dt.isoformat(),
        "hpl_teks": hpl_teks,
        "sisa_hari": sisa_hari,
        "sisa_teks": sisa_teks,
        "cukup_bulan_mulai": cukup_bulan_mulai_dt.isoformat(),
        "cukup_bulan_selesai": cukup_bulan_selesai_dt.isoformat(),
        "persen": persen,
        "catatan": catatan,
    }
