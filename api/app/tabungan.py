"""Logika simulasi tabungan: fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai masukan uang pengguna tidak dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal
import math
import re
from typing import Any

# Batas operasional simulasi tabungan
MIN_SETORAN_AWAL = 0  # Rp 0
MAX_SETORAN_AWAL = 10_000_000_000  # Rp 10 miliar

MIN_SETORAN_BULANAN = 0  # Rp 0
MAX_SETORAN_BULANAN = 500_000_000  # Rp 500 juta

MIN_BUNGA_TAHUNAN = 0.0  # 0%
MAX_BUNGA_TAHUNAN = 30.0  # 30% per tahun

MIN_LAMA_TAHUN = 1  # 1 tahun
MAX_LAMA_TAHUN = 60  # 60 tahun

MIN_TARGET = 1_000_000  # Rp 1 juta
MAX_TARGET = 100_000_000_000  # Rp 100 miliar

MAX_BULAN = 720  # 60 tahun
MAX_BODY_BYTES = 65536  # 64 KB

# Pilihan mode
MODES = ("hasil", "setoran", "lama")

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
INVALID_NUMBER = "INVALID_NUMBER"
OUT_OF_RANGE = "OUT_OF_RANGE"
TARGET_UNREACHABLE = "TARGET_UNREACHABLE"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class TabunganError(ValueError):
    """Galat operasional simulasi tabungan dengan kode galat dan status HTTP."""

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


def format_angka_id(val: int | float | Decimal, max_desimal: int = 2) -> str:
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


def parse_mode(val: Any) -> str:
    """Validasi dan parsing mode kalkulasi (hasil, setoran, lama)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        raise TabunganError(INVALID_REQUEST, "Field 'mode' wajib diisi.", 400)
    s = str(val).strip().lower()
    if s not in MODES:
        raise TabunganError(
            UNSUPPORTED_MODE,
            f"Mode '{val}' tidak didukung. Pilihan: {', '.join(MODES)}.",
            400,
        )
    return s


def _parse_rupiah_int(val: Any, field_name: str, label: str, min_val: int, max_val: int) -> int:
    """Validasi dan parsing nominal rupiah bulat (toleran format titik/koma/spasi/Rp)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        raise TabunganError(INVALID_REQUEST, f"Field '{field_name}' wajib diisi.", 400)

    if isinstance(val, bool):
        raise TabunganError(INVALID_NUMBER, f"{label} harus berupa angka.", 400)

    if isinstance(val, (int, float)):
        if isinstance(val, float) and not val.is_integer():
            raise TabunganError(INVALID_NUMBER, f"{label} harus berupa bilangan bulat rupiah.", 400)
        num = int(val)
    elif isinstance(val, str):
        s = val.strip()
        if s.lower().startswith("rp"):
            s = s[2:].strip()

        # Deteksi nilai bertanda minus
        if s.startswith("-"):
            s_rest = s[1:].replace(".", "").replace(",", "").replace(" ", "")
            if s_rest.isdigit():
                raise TabunganError(
                    OUT_OF_RANGE,
                    f"{label} harus antara Rp {format_angka_id(min_val)} dan Rp {format_angka_id(max_val)}.",
                    400,
                )
            raise TabunganError(INVALID_NUMBER, f"{label} harus berupa angka rupiah yang valid.", 400)

        # Abaikan desimal nol di belakang koma (misal "10.000,00" atau "10000,0")
        if "," in s:
            parts = s.split(",")
            if len(parts) == 2 and parts[1] in ("0", "00", ""):
                s = parts[0]

        s_clean = s.replace(".", "").replace(",", "").replace(" ", "")
        if not s_clean.isdigit():
            raise TabunganError(INVALID_NUMBER, f"{label} harus berupa angka rupiah yang valid.", 400)

        try:
            num = int(s_clean)
        except ValueError:
            raise TabunganError(INVALID_NUMBER, f"{label} tidak valid.", 400)
    else:
        raise TabunganError(INVALID_NUMBER, f"{label} harus berupa angka rupiah.", 400)

    if num < min_val or num > max_val:
        raise TabunganError(
            OUT_OF_RANGE,
            f"{label} harus antara Rp {format_angka_id(min_val)} dan Rp {format_angka_id(max_val)}.",
            400,
        )

    return num


def parse_setoran_awal(val: Any) -> int:
    """Validasi dan parsing setoran awal (0 .. 10.000.000.000)."""
    return _parse_rupiah_int(val, "setoran_awal", "Setoran awal", MIN_SETORAN_AWAL, MAX_SETORAN_AWAL)


def parse_setoran_bulanan(val: Any) -> int:
    """Validasi dan parsing setoran bulanan (0 .. 500.000.000)."""
    return _parse_rupiah_int(val, "setoran_bulanan", "Setoran bulanan", MIN_SETORAN_BULANAN, MAX_SETORAN_BULANAN)


def parse_target(val: Any) -> int:
    """Validasi dan parsing target tabungan (1.000.000 .. 100.000.000.000)."""
    return _parse_rupiah_int(val, "target", "Target tabungan", MIN_TARGET, MAX_TARGET)


def parse_bunga_tahunan(val: Any) -> float:
    """Validasi dan parsing suku bunga tahunan (0 .. 30%). Menerima koma atau titik."""
    if val is None or (isinstance(val, str) and not val.strip()):
        raise TabunganError(INVALID_REQUEST, "Field 'bunga_tahunan' wajib diisi.", 400)

    if isinstance(val, bool):
        raise TabunganError(INVALID_NUMBER, "Bunga tahunan harus berupa angka.", 400)

    if isinstance(val, (int, float)):
        num = float(val)
    elif isinstance(val, str):
        s = val.strip().rstrip("%").strip().replace(",", ".")
        if not re.fullmatch(r"^[+-]?\d+(?:\.\d+)?$", s):
            raise TabunganError(INVALID_NUMBER, "Bunga tahunan harus berupa angka valid.", 400)
        try:
            num = float(s)
        except ValueError:
            raise TabunganError(INVALID_NUMBER, "Bunga tahunan tidak valid.", 400)
    else:
        raise TabunganError(INVALID_NUMBER, "Bunga tahunan harus berupa angka.", 400)

    if num < MIN_BUNGA_TAHUNAN or num > MAX_BUNGA_TAHUNAN:
        raise TabunganError(
            OUT_OF_RANGE,
            f"Bunga tahunan harus antara {format_angka_id(MIN_BUNGA_TAHUNAN)}% sampai {format_angka_id(MAX_BUNGA_TAHUNAN)}%.",
            400,
        )

    return num


def parse_lama_tahun(val: Any) -> int:
    """Validasi dan parsing lama tabungan dalam tahun (1 .. 60)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        raise TabunganError(INVALID_REQUEST, "Field 'lama_tahun' wajib diisi.", 400)

    if isinstance(val, bool):
        raise TabunganError(INVALID_NUMBER, "Lama tahun harus berupa bilangan bulat.", 400)

    if isinstance(val, (int, float)):
        if isinstance(val, float) and not val.is_integer():
            raise TabunganError(INVALID_NUMBER, "Lama tahun harus berupa bilangan bulat.", 400)
        num = int(val)
    elif isinstance(val, str):
        s = val.strip()
        if s.startswith("-"):
            if s[1:].isdigit():
                raise TabunganError(
                    OUT_OF_RANGE,
                    f"Lama tabungan harus antara {MIN_LAMA_TAHUN} sampai {MAX_LAMA_TAHUN} tahun.",
                    400,
                )
            raise TabunganError(INVALID_NUMBER, "Lama tahun harus berupa bilangan bulat.", 400)
        if not re.fullmatch(r"^\d+$", s):
            raise TabunganError(INVALID_NUMBER, "Lama tahun harus berupa bilangan bulat positif.", 400)
        try:
            num = int(s)
        except ValueError:
            raise TabunganError(INVALID_NUMBER, "Lama tahun tidak valid.", 400)
    else:
        raise TabunganError(INVALID_NUMBER, "Lama tahun harus berupa bilangan bulat.", 400)

    if num < MIN_LAMA_TAHUN or num > MAX_LAMA_TAHUN:
        raise TabunganError(
            OUT_OF_RANGE,
            f"Lama tabungan harus antara {MIN_LAMA_TAHUN} sampai {MAX_LAMA_TAHUN} tahun.",
            400,
        )

    return num


def _buat_tabel_tahunan(
    history_saldo: list[float],
    setoran_awal: int,
    setoran_bulanan: int,
    total_months: int,
) -> list[dict[str, int]]:
    """Membentuk baris tabel tahunan konsisten dari riwayat saldo per bulan."""
    if total_months <= 0 or not history_saldo:
        return []

    num_years = int(math.ceil(total_months / 12.0))
    tabel: list[dict[str, int]] = []
    prev_saldo = setoran_awal
    cum_setoran = 0

    for y in range(1, num_years + 1):
        end_m = min(y * 12, total_months)
        start_m = (y - 1) * 12
        m_in_y = end_m - start_m

        dep_y = m_in_y * setoran_bulanan
        cum_setoran += dep_y

        saldo_y = int(round(history_saldo[end_m - 1]))
        bunga_y = saldo_y - prev_saldo - dep_y
        bunga_cum = saldo_y - setoran_awal - cum_setoran

        tabel.append({
            "tahun": y,
            "saldo_akhir": saldo_y,
            "setoran_tahun_ini": dep_y,
            "bunga_tahun_ini": bunga_y,
            "bunga_kumulatif": bunga_cum,
        })
        prev_saldo = saldo_y

    return tabel


def hitung_tabungan(
    mode: Any,
    setoran_awal: Any = None,
    setoran_bulanan: Any = None,
    bunga_tahunan: Any = None,
    lama_tahun: Any = None,
    target: Any = None,
) -> dict[str, Any]:
    """Menghitung simulasi tabungan per bulan di memori sesuai mode."""
    mode_norm = parse_mode(mode)

    if mode_norm == "hasil":
        s_awal = parse_setoran_awal(setoran_awal)
        s_bulanan = parse_setoran_bulanan(setoran_bulanan)
        b_tahunan = parse_bunga_tahunan(bunga_tahunan)
        l_tahun = parse_lama_tahun(lama_tahun)

        if s_awal == 0 and s_bulanan == 0:
            raise TabunganError(
                INVALID_REQUEST,
                "Setoran awal dan setoran bulanan tidak boleh keduanya Rp 0.",
                400,
            )

        total_months = l_tahun * 12
        i = (b_tahunan / 100.0) / 12.0
        saldo = float(s_awal)
        history_saldo: list[float] = []

        for _ in range(total_months):
            saldo = saldo * (1.0 + i) + s_bulanan
            history_saldo.append(saldo)

        saldo_akhir = int(round(saldo))
        total_setoran = s_awal + total_months * s_bulanan
        total_bunga = saldo_akhir - total_setoran
        tabel = _buat_tabel_tahunan(history_saldo, s_awal, s_bulanan, total_months)

        return {
            "mode": "hasil",
            "saldo_akhir": saldo_akhir,
            "total_setoran": total_setoran,
            "total_bunga": total_bunga,
            "lama_bulan": total_months,
            "lama_tahun": l_tahun,
            "bunga_tahunan": round(b_tahunan, 4) if not b_tahunan.is_integer() else int(b_tahunan),
            "setoran_awal": s_awal,
            "setoran_bulanan": s_bulanan,
            "setoran_bulanan_disarankan": None,
            "target": None,
            "selisih_target": None,
            "bulan_ke_target": None,
            "tabel_tahunan": tabel,
            "asumsi": "Bunga dihitung berbunga-bulanan dan setoran masuk di akhir bulan.",
            "catatan": [
                "Pajak bunga dan biaya administrasi bank belum dihitung, jadi hasil nyata bisa sedikit berbeda."
            ],
            "batas": limits_payload(),
        }

    elif mode_norm == "setoran":
        tgt = parse_target(target)
        s_awal = parse_setoran_awal(setoran_awal)
        b_tahunan = parse_bunga_tahunan(bunga_tahunan)
        l_tahun = parse_lama_tahun(lama_tahun)

        n = l_tahun * 12
        i = (b_tahunan / 100.0) / 12.0

        if i == 0.0:
            pmt = (tgt - s_awal) / float(n)
        else:
            factor = (1.0 + i) ** n
            pmt = (tgt - s_awal * factor) * i / (factor - 1.0)

        if pmt <= 0:
            disarankan = 0
        else:
            disarankan = int(math.ceil(pmt / 1000.0) * 1000)

        # Simulasikan ulang dengan loop
        saldo = float(s_awal)
        for _ in range(n):
            saldo = saldo * (1.0 + i) + disarankan

        iterations = 0
        while int(round(saldo)) < tgt and iterations < 200 and disarankan > 0:
            disarankan += 1000
            iterations += 1
            saldo = float(s_awal)
            for _ in range(n):
                saldo = saldo * (1.0 + i) + disarankan

        # Catat riwayat saldo akhir
        history_saldo = []
        saldo = float(s_awal)
        for _ in range(n):
            saldo = saldo * (1.0 + i) + disarankan
            history_saldo.append(saldo)

        saldo_akhir = int(round(saldo))
        total_setoran = s_awal + n * disarankan
        total_bunga = saldo_akhir - total_setoran
        selisih_target = max(0, saldo_akhir - tgt)
        tabel = _buat_tabel_tahunan(history_saldo, s_awal, disarankan, n)

        return {
            "mode": "setoran",
            "saldo_akhir": saldo_akhir,
            "total_setoran": total_setoran,
            "total_bunga": total_bunga,
            "lama_bulan": n,
            "lama_tahun": l_tahun,
            "bunga_tahunan": round(b_tahunan, 4) if not b_tahunan.is_integer() else int(b_tahunan),
            "setoran_awal": s_awal,
            "setoran_bulanan": disarankan,
            "setoran_bulanan_disarankan": disarankan,
            "target": tgt,
            "selisih_target": selisih_target,
            "bulan_ke_target": None,
            "tabel_tahunan": tabel,
            "asumsi": "Bunga dihitung berbunga-bulanan dan setoran masuk di akhir bulan.",
            "catatan": [
                "Pajak bunga dan biaya administrasi bank belum dihitung, jadi hasil nyata bisa sedikit berbeda."
            ],
            "batas": limits_payload(),
        }

    else:  # mode_norm == "lama"
        tgt = parse_target(target)
        s_awal = parse_setoran_awal(setoran_awal)
        s_bulanan = parse_setoran_bulanan(setoran_bulanan)
        b_tahunan = parse_bunga_tahunan(bunga_tahunan)

        i = (b_tahunan / 100.0) / 12.0
        saldo = float(s_awal)
        history_saldo = []
        bulan = 0

        while int(round(saldo)) < tgt and bulan < MAX_BULAN:
            bulan += 1
            saldo = saldo * (1.0 + i) + s_bulanan
            history_saldo.append(saldo)

        if int(round(saldo)) < tgt:
            raise TabunganError(
                TARGET_UNREACHABLE,
                "Target tabungan tidak tercapai dalam batas waktu maksimal 60 tahun (720 bulan). "
                "Coba naikkan setoran bulanan atau setoran awal.",
                400,
            )

        bulan_ke_target = bulan
        saldo_akhir = int(round(saldo))
        total_setoran = s_awal + bulan_ke_target * s_bulanan
        total_bunga = saldo_akhir - total_setoran
        selisih_target = max(0, saldo_akhir - tgt)
        lama_tahun = int(math.ceil(bulan_ke_target / 12.0)) if bulan_ke_target > 0 else 0
        tabel = _buat_tabel_tahunan(history_saldo, s_awal, s_bulanan, bulan_ke_target)

        return {
            "mode": "lama",
            "saldo_akhir": saldo_akhir,
            "total_setoran": total_setoran,
            "total_bunga": total_bunga,
            "lama_bulan": bulan_ke_target,
            "lama_tahun": lama_tahun,
            "bunga_tahunan": round(b_tahunan, 4) if not b_tahunan.is_integer() else int(b_tahunan),
            "setoran_awal": s_awal,
            "setoran_bulanan": s_bulanan,
            "setoran_bulanan_disarankan": None,
            "target": tgt,
            "selisih_target": selisih_target,
            "bulan_ke_target": bulan_ke_target,
            "tabel_tahunan": tabel,
            "asumsi": "Bunga dihitung berbunga-bulanan dan setoran masuk di akhir bulan.",
            "catatan": [
                "Pajak bunga dan biaya administrasi bank belum dihitung, jadi hasil nyata bisa sedikit berbeda."
            ],
            "batas": limits_payload(),
        }


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional, pilihan mode, dan asumsi."""
    return {
        "modes": [
            {
                "value": "hasil",
                "label": "Hasil akhir tabungan",
                "deskripsi": "Hitung perkiraan saldo akhir dari setoran awal, setoran bulanan, bunga, dan jangka waktu.",
            },
            {
                "value": "setoran",
                "label": "Cari setoran bulanan",
                "deskripsi": "Hitung setoran bulanan yang diperlukan untuk mencapai target tabungan tertentu.",
            },
            {
                "value": "lama",
                "label": "Berapa lama sampai target",
                "deskripsi": "Hitung berapa bulan atau tahun yang dibutuhkan hingga target tabungan tercapai.",
            },
        ],
        "setoran_awal": {
            "min": MIN_SETORAN_AWAL,
            "max": MAX_SETORAN_AWAL,
            "satuan": "rupiah",
        },
        "setoran_bulanan": {
            "min": MIN_SETORAN_BULANAN,
            "max": MAX_SETORAN_BULANAN,
            "satuan": "rupiah",
        },
        "bunga_tahunan": {
            "min": MIN_BUNGA_TAHUNAN,
            "max": MAX_BUNGA_TAHUNAN,
            "satuan": "%",
        },
        "lama_tahun": {
            "min": MIN_LAMA_TAHUN,
            "max": MAX_LAMA_TAHUN,
            "satuan": "tahun",
        },
        "target": {
            "min": MIN_TARGET,
            "max": MAX_TARGET,
            "satuan": "rupiah",
        },
        "max_body_bytes": MAX_BODY_BYTES,
        "asumsi": "Bunga dihitung berbunga-bulanan dan setoran masuk di akhir bulan.",
    }
