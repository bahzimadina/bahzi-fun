"""Kalkulator upah lembur: hitung perkiraan upah lembur dari gaji sebulan.

Dasar perhitungan: Peraturan Pemerintah (PP) No. 35 Tahun 2021 tentang PKWT,
Alih Daya, Waktu Kerja dan Waktu Istirahat, dan Pemutusan Hubungan Kerja.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori.
"""

from __future__ import annotations

import math
from typing import Any

# Batas operasional & konstanta
UPAH_SEJAM_PEMBAGI = 173
MIN_UPAH = 100_000
MAX_UPAH = 1_000_000_000
MAX_JAM_KERJA = 4
MAX_JAM_LIBUR = 12
LANGKAH_JAM = 0.5

CATATAN = (
    "Hitungan memakai upah sejam = upah sebulan / 173. "
    "Uang makan lembur, potongan, dan pajak tidak dihitung di sini."
)

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
INVALID_WAGE = "INVALID_WAGE"
UNSUPPORTED_DAY = "UNSUPPORTED_DAY"
INVALID_WORKWEEK = "INVALID_WORKWEEK"
INVALID_HOURS = "INVALID_HOURS"
TOO_MANY_HOURS = "TOO_MANY_HOURS"


class LemburError(ValueError):
    """Galat operasional kalkulator upah lembur dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        err = {"code": self.code, "message": self.message}
        return {
            "ok": False,
            "kode": self.code,
            "pesan": self.message,
            "error": err,
            "detail": err,
        }


def limits_payload() -> dict[str, Any]:
    """Mengembalikan batas operasional dan konstanta kalkulator lembur."""
    return {
        "upah_min": MIN_UPAH,
        "upah_max": MAX_UPAH,
        "jam_kerja_max": MAX_JAM_KERJA,
        "jam_libur_max": MAX_JAM_LIBUR,
        "langkah_jam": LANGKAH_JAM,
        "hari_kerja_mingguan": [5, 6],
        "jenis_hari": ["kerja", "libur"],
        "pembagi_upah_sejam": UPAH_SEJAM_PEMBAGI,
    }


def hitung(
    upah_bulanan: int | float | str | None,
    jenis_hari: str | None,
    jam_lembur: int | float | str | None,
    hari_kerja_mingguan: int | str | None = "5",
) -> dict[str, Any]:
    """Hitung perkiraan upah lembur berdasarkan PP 35/2021."""
    # 1. Validasi field wajib ada
    if upah_bulanan is None or (isinstance(upah_bulanan, str) and not upah_bulanan.strip()):
        raise LemburError(INVALID_REQUEST, "Field 'upah_bulanan' wajib diisi.", 400)
    if jenis_hari is None or (isinstance(jenis_hari, str) and not jenis_hari.strip()):
        raise LemburError(INVALID_REQUEST, "Field 'jenis_hari' wajib diisi.", 400)
    if jam_lembur is None or (isinstance(jam_lembur, str) and not jam_lembur.strip()):
        raise LemburError(INVALID_REQUEST, "Field 'jam_lembur' wajib diisi.", 400)

    # 2. Parsing dan validasi upah_bulanan
    if isinstance(upah_bulanan, bool):
        raise LemburError(
            INVALID_WAGE,
            "Upah bulanan harus angka antara Rp100.000 dan Rp1.000.000.000.",
            400,
        )

    if isinstance(upah_bulanan, (int, float)):
        if isinstance(upah_bulanan, float) and (math.isnan(upah_bulanan) or math.isinf(upah_bulanan)):
            raise LemburError(
                INVALID_WAGE,
                "Upah bulanan harus angka antara Rp100.000 dan Rp1.000.000.000.",
                400,
            )
        upah_val = int(round(upah_bulanan))
    elif isinstance(upah_bulanan, str):
        s = upah_bulanan.strip().replace(" ", "")
        if s.lower().startswith("rp"):
            s = s[2:].strip()
        if "," in s and "." in s:
            s = s.replace(".", "").split(",")[0]
        elif "." in s:
            parts = s.split(".")
            if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
                s = "".join(parts)
        elif "," in s:
            s = s.split(",")[0]

        try:
            upah_val = int(float(s))
        except (ValueError, TypeError):
            raise LemburError(
                INVALID_WAGE,
                "Upah bulanan harus angka antara Rp100.000 dan Rp1.000.000.000.",
                400,
            )
    else:
        raise LemburError(
            INVALID_WAGE,
            "Upah bulanan harus angka antara Rp100.000 dan Rp1.000.000.000.",
            400,
        )

    if upah_val < MIN_UPAH or upah_val > MAX_UPAH:
        raise LemburError(
            INVALID_WAGE,
            "Upah bulanan harus angka antara Rp100.000 dan Rp1.000.000.000.",
            400,
        )

    # 3. Validasi jenis_hari
    jenis_str = str(jenis_hari).strip().lower()
    if jenis_str not in ("kerja", "libur"):
        raise LemburError(UNSUPPORTED_DAY, "Jenis hari harus 'kerja' atau 'libur'.", 400)

    # 4. Validasi hari_kerja_mingguan (hanya dipakai saat libur, diabaikan saat kerja)
    if jenis_str == "libur":
        if hari_kerja_mingguan is None or (
            isinstance(hari_kerja_mingguan, str) and not hari_kerja_mingguan.strip()
        ):
            hkm_int = 5
        elif isinstance(hari_kerja_mingguan, bool):
            raise LemburError(INVALID_WORKWEEK, "Jumlah hari kerja seminggu harus 5 atau 6.", 400)
        else:
            try:
                hkm_int = int(hari_kerja_mingguan)
            except (ValueError, TypeError):
                raise LemburError(INVALID_WORKWEEK, "Jumlah hari kerja seminggu harus 5 atau 6.", 400)
            if hkm_int not in (5, 6):
                raise LemburError(INVALID_WORKWEEK, "Jumlah hari kerja seminggu harus 5 atau 6.", 400)
    else:
        # Saat jenis_hari == "kerja", abaikan nilainya
        try:
            val = int(hari_kerja_mingguan) if hari_kerja_mingguan is not None else 5
            hkm_int = val if val in (5, 6) else 5
        except Exception:
            hkm_int = 5

    # 5. Parsing dan validasi jam_lembur
    if isinstance(jam_lembur, bool):
        raise LemburError(INVALID_HOURS, "Isi jumlah jam lembur, kelipatan 0,5.", 400)

    try:
        if isinstance(jam_lembur, str):
            jam_str = jam_lembur.strip().replace(",", ".")
            jam_val = float(jam_str)
        else:
            jam_val = float(jam_lembur)
    except (ValueError, TypeError):
        raise LemburError(INVALID_HOURS, "Isi jumlah jam lembur, kelipatan 0,5.", 400)

    if math.isnan(jam_val) or math.isinf(jam_val) or jam_val <= 0:
        raise LemburError(INVALID_HOURS, "Isi jumlah jam lembur, kelipatan 0,5.", 400)

    if abs(jam_val * 2 - round(jam_val * 2)) > 1e-6:
        raise LemburError(INVALID_HOURS, "Isi jumlah jam lembur, kelipatan 0,5.", 400)

    jam_val = round(jam_val * 2) / 2.0

    if jenis_str == "kerja":
        if jam_val > MAX_JAM_KERJA:
            raise LemburError(
                TOO_MANY_HOURS,
                "Lembur pada hari kerja lazimnya paling banyak 4 jam sehari.",
                400,
            )
    else:
        if jam_val > MAX_JAM_LIBUR:
            raise LemburError(
                TOO_MANY_HOURS,
                f"Lembur pada hari libur paling banyak {MAX_JAM_LIBUR} jam sehari.",
                400,
            )

    # 6. Hitung upah sejam dan rincian per jam
    upah_sejam_raw = upah_val / UPAH_SEJAM_PEMBAGI
    upah_sejam = round(upah_sejam_raw, 2)

    num_blocks = math.ceil(jam_val)
    rincian: list[dict[str, Any]] = []

    for jam_ke in range(1, num_blocks + 1):
        durasi = 0.5 if (jam_ke == num_blocks and (jam_val % 1 != 0)) else 1.0

        if jenis_str == "kerja":
            pengali = 1.5 if jam_ke == 1 else 2.0
        else:
            if hkm_int == 6:
                if jam_ke <= 7:
                    pengali = 2.0
                elif jam_ke == 8:
                    pengali = 3.0
                else:
                    pengali = 4.0
            else:
                if jam_ke <= 8:
                    pengali = 2.0
                elif jam_ke == 9:
                    pengali = 3.0
                else:
                    pengali = 4.0

        upah_jam = round(durasi * pengali * upah_sejam_raw)
        rincian.append(
            {
                "jam_ke": jam_ke,
                "pengali": pengali,
                "upah": upah_jam,
            }
        )

    # 7. Total dan persentase
    total_upah_lembur = sum(item["upah"] for item in rincian)
    total_diterima = upah_val + total_upah_lembur
    persen_tambahan = round((total_upah_lembur / upah_val) * 100, 2)

    return {
        "upah_bulanan": upah_val,
        "upah_sejam": upah_sejam,
        "jenis_hari": jenis_str,
        "jam_lembur": jam_val,
        "hari_kerja_mingguan": hkm_int,
        "rincian": rincian,
        "total_upah_lembur": total_upah_lembur,
        "total_diterima": total_diterima,
        "persen_tambahan": persen_tambahan,
        "catatan": CATATAN,
    }
