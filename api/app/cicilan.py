"""Logika simulasi cicilan pinjaman (anuitas dan bunga tetap): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nominal uang pengguna tidak dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, getcontext
import re
from typing import Any

# Tetapkan presisi aritmetika Decimal yang cukup tinggi untuk perhitungan tenor panjang
getcontext().prec = 28

# Batas operasional alat simulasi cicilan
MIN_POKOK = 100000  # Rp 100 ribu
MAX_POKOK = 100000000000  # Rp 100 miliar
MIN_BUNGA = 0  # 0%
MAX_BUNGA = 100  # 100% per tahun
MIN_TENOR = 1  # 1 bulan
MAX_TENOR = 360  # 30 tahun (360 bulan)
MAX_BODY_BYTES = 65536  # 64 KB

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NOT_A_NUMBER = "NOT_A_NUMBER"
OUT_OF_RANGE = "OUT_OF_RANGE"
UNSUPPORTED_METHOD = "UNSUPPORTED_METHOD"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"

METODE_PILIHAN = ("anuitas", "flat")


class CicilanError(ValueError):
    """Galat operasional alat simulasi cicilan dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat terstandar."""
        return {"error": {"code": self.code, "message": self.message}}


def parse_pokok(value: Any) -> Decimal:
    """Validasi dan parsing pokok pinjaman.

    Membuang titik, spasi, dan koma (pemisah ribuan gaya Indonesia).
    Sisa harus digit saja dalam rentang MIN_POKOK..MAX_POKOK.
    """
    if value is None:
        raise CicilanError(INVALID_REQUEST, "Field 'pokok' wajib disertakan.", 400)

    if isinstance(value, bool):
        raise CicilanError(NOT_A_NUMBER, "Pokok pinjaman harus berupa angka.", 400)

    s = str(value).strip()
    if not s:
        raise CicilanError(INVALID_REQUEST, "Pokok pinjaman tidak boleh kosong.", 400)

    # Deteksi nilai negatif sebelum membuang karakter
    if s.startswith("-"):
        s_rest = s[1:].replace(".", "").replace(",", "").replace(" ", "")
        if s_rest.isdigit():
            raise CicilanError(
                OUT_OF_RANGE,
                "Pokok pinjaman harus antara Rp 100.000 sampai Rp 100.000.000.000.",
                400,
            )
        raise CicilanError(NOT_A_NUMBER, "Pokok pinjaman harus berupa angka.", 400)

    # Bersihkan pemisah ribuan gaya Indonesia
    s_clean = s.replace(".", "").replace(",", "").replace(" ", "")
    if not s_clean.isdigit():
        raise CicilanError(NOT_A_NUMBER, "Pokok pinjaman harus berupa angka.", 400)

    val = Decimal(s_clean)
    if val < MIN_POKOK or val > MAX_POKOK:
        raise CicilanError(
            OUT_OF_RANGE,
            "Pokok pinjaman harus antara Rp 100.000 sampai Rp 100.000.000.000.",
            400,
        )

    return val


def parse_bunga(value: Any) -> Decimal:
    """Validasi dan parsing suku bunga tahunan.

    Menerima koma atau titik sebagai pemisah desimal, maksimal 4 desimal.
    Rentang yang diizinkan: 0..100 persen.
    """
    if value is None:
        raise CicilanError(INVALID_REQUEST, "Field 'bunga' wajib disertakan.", 400)

    if isinstance(value, bool):
        raise CicilanError(NOT_A_NUMBER, "Suku bunga harus berupa angka.", 400)

    s = str(value).strip()
    if not s:
        raise CicilanError(INVALID_REQUEST, "Suku bunga tidak boleh kosong.", 400)

    # Hapus simbol % bila ada dan ganti koma desimal ke titik
    s = s.rstrip("%").strip().replace(",", ".")

    # Cek pola angka (bisa bertanda minus, integer atau desimal titik)
    if not re.fullmatch(r"^[+-]?\d+(?:\.\d+)?$", s):
        raise CicilanError(NOT_A_NUMBER, "Suku bunga harus berupa angka.", 400)

    if "." in s:
        dec_part = s.split(".")[1]
        if len(dec_part) > 4:
            raise CicilanError(
                OUT_OF_RANGE,
                "Suku bunga maksimal memiliki 4 angka di belakang koma.",
                400,
            )

    try:
        val = Decimal(s)
    except Exception:
        raise CicilanError(NOT_A_NUMBER, "Suku bunga harus berupa angka.", 400)

    if val < MIN_BUNGA or val > MAX_BUNGA:
        raise CicilanError(
            OUT_OF_RANGE,
            "Suku bunga tahunan harus antara 0% sampai 100%.",
            400,
        )

    return val


def parse_tenor(value: Any) -> int:
    """Validasi dan parsing tenor pinjaman dalam satuan bulan.

    Harus berupa bilangan bulat antara MIN_TENOR (1) sampai MAX_TENOR (360).
    """
    if value is None:
        raise CicilanError(INVALID_REQUEST, "Field 'tenor' wajib disertakan.", 400)

    if isinstance(value, bool):
        raise CicilanError(NOT_A_NUMBER, "Tenor pinjaman harus berupa bilangan bulat.", 400)

    s = str(value).strip()
    if not s:
        raise CicilanError(INVALID_REQUEST, "Tenor pinjaman tidak boleh kosong.", 400)

    if s.startswith("-"):
        if s[1:].isdigit():
            raise CicilanError(
                OUT_OF_RANGE,
                "Tenor pinjaman harus antara 1 sampai 360 bulan.",
                400,
            )
        raise CicilanError(NOT_A_NUMBER, "Tenor pinjaman harus berupa bilangan bulat.", 400)

    if not s.isdigit():
        raise CicilanError(NOT_A_NUMBER, "Tenor pinjaman harus berupa bilangan bulat.", 400)

    val = int(s)
    if val < MIN_TENOR or val > MAX_TENOR:
        raise CicilanError(
            OUT_OF_RANGE,
            "Tenor pinjaman harus antara 1 sampai 360 bulan.",
            400,
        )

    return val


def parse_metode(value: Any) -> str:
    """Validasi metode perhitungan cicilan ('anuitas' atau 'flat')."""
    if value is None:
        raise CicilanError(INVALID_REQUEST, "Field 'metode' wajib disertakan.", 400)

    s = str(value).strip().lower()
    if not s:
        raise CicilanError(INVALID_REQUEST, "Field 'metode' tidak boleh kosong.", 400)

    if s not in METODE_PILIHAN:
        raise CicilanError(
            UNSUPPORTED_METHOD,
            f"Metode '{value}' tidak didukung. Pilih 'anuitas' atau 'flat'.",
            400,
        )

    return s


def hitung_cicilan(
    pokok: Any,
    bunga: Any,
    tenor: Any,
    metode: Any = "anuitas",
) -> dict[str, Any]:
    """Hitung simulasi cicilan pinjaman murni di memori.

    Mengembalikan ringkasan cicilan serta jadwal pembayaran per bulan.
    Semua nominal uang dikembalikan sebagai string 2 desimal.
    """
    p = parse_pokok(pokok)
    b = parse_bunga(bunga)
    t = parse_tenor(tenor)
    m = parse_metode(metode)

    jadwal: list[dict[str, Any]] = []

    if m == "anuitas":
        # Suku bunga per bulan
        i = b / Decimal("100") / Decimal("12")

        if i == Decimal("0"):
            angsuran = (p / Decimal(t)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            # Rumus anuitas: pokok * i / (1 - (1 + i)**-tenor)
            angsuran = (p * i / (Decimal("1") - (Decimal("1") + i) ** -t)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        sisa = p
        for bulan in range(1, t + 1):
            if bulan == t:
                # Pada bulan terakhir: sesuaikan pokok dengan sisa utang sebelumnya
                pokok_bulan = sisa
                bunga_bulan = (sisa * i).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                angsuran_bulan = pokok_bulan + bunga_bulan
                sisa = Decimal("0.00")
            else:
                bunga_bulan = (sisa * i).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                pokok_bulan = angsuran - bunga_bulan
                sisa = sisa - pokok_bulan
                angsuran_bulan = angsuran

            jadwal.append({
                "bulan": bulan,
                "angsuran": f"{angsuran_bulan:.2f}",
                "bunga": f"{bunga_bulan:.2f}",
                "pokok": f"{pokok_bulan:.2f}",
                "sisa": f"{sisa:.2f}",
            })

        total_bunga = sum(Decimal(row["bunga"]) for row in jadwal)
        total_bayar = p + total_bunga

    else:
        # Rumus bunga tetap (flat)
        total_bunga = (p * b / Decimal("100") * Decimal(t) / Decimal("12")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total_bayar = p + total_bunga
        angsuran = (total_bayar / Decimal(t)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        bunga_bulan_dasar = (total_bunga / Decimal(t)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        sisa = p
        for bulan in range(1, t + 1):
            if bulan == t:
                # Pada bulan terakhir: sisipkan sisa pembulatan bunga & pokok agar total jadwal pas dengan ringkasan
                bunga_m = total_bunga - bunga_bulan_dasar * (t - 1)
                pokok_m = sisa
                angsuran_m = pokok_m + bunga_m
                sisa = Decimal("0.00")
            else:
                bunga_m = bunga_bulan_dasar
                pokok_m = angsuran - bunga_m
                angsuran_m = angsuran
                sisa = sisa - pokok_m

            jadwal.append({
                "bulan": bulan,
                "angsuran": f"{angsuran_m:.2f}",
                "bunga": f"{bunga_m:.2f}",
                "pokok": f"{pokok_m:.2f}",
                "sisa": f"{sisa:.2f}",
            })

    # Format bunga tahunan bersih tanpa nol tak perlu
    bunga_str = f"{b:.4f}".rstrip("0").rstrip(".") if "." in f"{b:.4f}" else str(b)
    if not bunga_str:
        bunga_str = "0"

    return {
        "metode": m,
        "pokok": f"{p:.2f}",
        "bunga_tahunan": bunga_str,
        "tenor_bulan": t,
        "angsuran_per_bulan": f"{angsuran:.2f}",
        "total_bunga": f"{total_bunga:.2f}",
        "total_bayar": f"{total_bayar:.2f}",
        "jadwal": jadwal,
    }


def limits_payload() -> dict[str, Any]:
    """Batas operasional dan konfigurasi untuk GET /api/cicilan/limits."""
    return {
        "min_pokok": MIN_POKOK,
        "max_pokok": MAX_POKOK,
        "min_bunga": MIN_BUNGA,
        "max_bunga": MAX_BUNGA,
        "min_tenor": MIN_TENOR,
        "max_tenor": MAX_TENOR,
        "max_body_bytes": MAX_BODY_BYTES,
        "metode_didukung": [
            {"value": "anuitas", "label": "Anuitas (angsuran tetap, porsi bunga menurun)"},
            {"value": "flat", "label": "Bunga tetap (dihitung dari pokok awal)"},
        ],
        "default_metode": "anuitas",
        "contoh": {
            "pokok": "50.000.000",
            "bunga": "6,5",
            "tenor": 36,
            "metode": "anuitas",
        },
        "catatan": "Perkiraan saja. Belum termasuk biaya admin, provisi, asuransi, dan denda. Bukan penawaran resmi dari bank.",
    }
