"""Kalkulator tagihan listrik rumah: perkirakan pemakaian kWh dan rupiah tagihan listrik per bulan.

Docstring modul:
Hitungan memakai 30 hari per bulan dan tarif yang dimasukkan pengunjung.
Ini perkiraan pemakaian listrik rumah tangga berdasarkan daya dan durasi alat,
bukan tagihan resmi dari penyedia listrik.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import json
import math
from typing import Any

# Batas operasional & konstanta
MAX_ALAT = 30
WATT_MIN = 1
WATT_MAX = 100_000
JAM_MAX = 24
JUMLAH_MAX = 50
TARIF_MIN = 100
TARIF_MAX = 5_000
TOKEN_MIN = 1_000
TOKEN_MAX = 10_000_000
HARI_PER_BULAN = 30
NAMA_MAX = 40

GOLONGAN: dict[str, dict[str, Any]] = {
    "900-subsidi": {"label": "900 VA rumah tangga (subsidi)", "tarif": 605.0},
    "1300": {"label": "1300 VA rumah tangga", "tarif": 1444.7},
    "2200": {"label": "2200 VA rumah tangga", "tarif": 1444.7},
    "3500": {"label": "3500–5500 VA rumah tangga", "tarif": 1699.53},
    "sendiri": {"label": "Isi tarif sendiri", "tarif": None},
}

CATATAN = (
    "Hitungan memakai 30 hari per bulan dan tarif yang kamu masukkan. "
    "Tarif listrik tiap golongan bisa berbeda dan bisa berubah, jadi cocokkan dengan tagihan atau struk token listrikmu."
)

# Kode galat stabil
INVALID_ALAT = "INVALID_ALAT"
NO_ALAT = "NO_ALAT"
TOO_MANY_ALAT = "TOO_MANY_ALAT"
INVALID_WATT = "INVALID_WATT"
INVALID_JAM = "INVALID_JAM"
INVALID_JUMLAH = "INVALID_JUMLAH"
INVALID_GOLONGAN = "INVALID_GOLONGAN"
INVALID_TARIF = "INVALID_TARIF"
INVALID_TOKEN = "INVALID_TOKEN"


class TagihanListrikError(ValueError):
    """Galat operasional kalkulator tagihan listrik dengan kode galat dan status HTTP."""

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
    """Mengembalikan batas operasional dan daftar golongan tarif."""
    return {
        "max_alat": MAX_ALAT,
        "watt_min": WATT_MIN,
        "watt_max": WATT_MAX,
        "jam_max": JAM_MAX,
        "jumlah_max": JUMLAH_MAX,
        "tarif_min": TARIF_MIN,
        "tarif_max": TARIF_MAX,
        "token_min": TOKEN_MIN,
        "token_max": TOKEN_MAX,
        "hari_per_bulan": HARI_PER_BULAN,
        "nama_max": NAMA_MAX,
        "golongan": [
            {"kode": k, "label": v["label"], "tarif": v["tarif"]}
            for k, v in GOLONGAN.items()
        ],
    }


def _parse_decimal_value(val: Any) -> Decimal | None:
    """Konversi input float/int/str (termasuk koma desimal) ke Decimal."""
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float, Decimal)):
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return Decimal(str(val))
    if isinstance(val, str):
        s = val.strip().replace(" ", "")
        if not s:
            return None
        if s.lower().startswith("rp"):
            s = s[2:].strip()
        if "," in s and "." in s:
            # Contoh "1.500,50" -> titik ribuan, koma desimal
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        try:
            d = Decimal(s)
            if d.is_nan() or d.is_infinite():
                return None
            return d
        except Exception:
            return None
    return None


def hitung(
    alat: str | list[Any] | None,
    golongan: str | None = None,
    tarif: int | float | str | None = None,
    token: int | float | str | None = None,
) -> dict[str, Any]:
    """Hitung perkiraan tagihan listrik rumah dari daftar peralatan."""
    # 1. Parsing dan validasi `alat`
    if isinstance(alat, str):
        try:
            raw_list = json.loads(alat)
        except Exception:
            raise TagihanListrikError(
                INVALID_ALAT,
                "Daftar peralatan tidak terbaca. Muat ulang halaman lalu isi lagi.",
                400,
            )
    elif isinstance(alat, list):
        raw_list = alat
    else:
        raise TagihanListrikError(
            NO_ALAT,
            "Isi minimal satu peralatan dulu.",
            400,
        )

    if not isinstance(raw_list, list) or len(raw_list) == 0:
        raise TagihanListrikError(
            NO_ALAT,
            "Isi minimal satu peralatan dulu.",
            400,
        )

    if len(raw_list) > MAX_ALAT:
        raise TagihanListrikError(
            TOO_MANY_ALAT,
            f"Maksimal {MAX_ALAT} peralatan sekali hitung.",
            400,
        )

    # 2. Parsing tiap item alat
    parsed_items: list[dict[str, Any]] = []
    for i, item in enumerate(raw_list):
        if not isinstance(item, dict):
            raise TagihanListrikError(
                INVALID_ALAT,
                "Daftar peralatan tidak terbaca. Muat ulang halaman lalu isi lagi.",
                400,
            )

        # Nama alat
        raw_nama = item.get("nama")
        if raw_nama is None or (isinstance(raw_nama, str) and not raw_nama.strip()):
            nama = f"Alat {i + 1}"
        else:
            cleaned = " ".join(str(raw_nama).strip().split())
            nama = cleaned[:NAMA_MAX] if cleaned else f"Alat {i + 1}"

        # Watt
        raw_watt = item.get("watt")
        if raw_watt is None or (isinstance(raw_watt, str) and not raw_watt.strip()):
            raise TagihanListrikError(
                INVALID_WATT,
                f'Daya alat "{nama}" harus antara 1 dan 100.000 watt.',
                400,
            )
        watt_dec = _parse_decimal_value(raw_watt)
        if watt_dec is None or watt_dec < WATT_MIN or watt_dec > WATT_MAX:
            raise TagihanListrikError(
                INVALID_WATT,
                f'Daya alat "{nama}" harus antara 1 dan 100.000 watt.',
                400,
            )

        # Jam
        raw_jam = item.get("jam")
        if raw_jam is None or (isinstance(raw_jam, str) and not raw_jam.strip()):
            raise TagihanListrikError(
                INVALID_JAM,
                f'Jam pemakaian "{nama}" harus antara 0 dan 24 jam.',
                400,
            )
        jam_dec = _parse_decimal_value(raw_jam)
        if jam_dec is None or jam_dec < 0 or jam_dec > JAM_MAX:
            raise TagihanListrikError(
                INVALID_JAM,
                f'Jam pemakaian "{nama}" harus antara 0 dan 24 jam.',
                400,
            )

        # Jumlah unit (opsional, default 1, int 1..50)
        raw_jumlah = item.get("jumlah")
        if raw_jumlah is None or (isinstance(raw_jumlah, str) and not str(raw_jumlah).strip()):
            jumlah_int = 1
        elif isinstance(raw_jumlah, bool):
            raise TagihanListrikError(
                INVALID_JUMLAH,
                f'Jumlah unit "{nama}" harus antara 1 dan 50.',
                400,
            )
        else:
            try:
                # Memastikan bilangan bulat (bukan 1.5)
                f_val = float(str(raw_jumlah).strip().replace(",", "."))
                if not f_val.is_integer():
                    raise ValueError
                jumlah_int = int(f_val)
            except Exception:
                raise TagihanListrikError(
                    INVALID_JUMLAH,
                    f'Jumlah unit "{nama}" harus antara 1 dan 50.',
                    400,
                )
            if jumlah_int < 1 or jumlah_int > JUMLAH_MAX:
                raise TagihanListrikError(
                    INVALID_JUMLAH,
                    f'Jumlah unit "{nama}" harus antara 1 dan 50.',
                    400,
                )

        parsed_items.append(
            {
                "nama": nama,
                "watt": watt_dec,
                "jam": jam_dec,
                "jumlah": jumlah_int,
            }
        )

    # 3. Validasi golongan dan tarif
    if golongan is None or (isinstance(golongan, str) and not golongan.strip()):
        gol_str = "1300"
    else:
        gol_str = str(golongan).strip()

    tarif_is_empty = tarif is None or (isinstance(tarif, str) and not str(tarif).strip())

    if not tarif_is_empty:
        tarif_dec = _parse_decimal_value(tarif)
        if tarif_dec is None or tarif_dec < TARIF_MIN or tarif_dec > TARIF_MAX:
            raise TagihanListrikError(
                INVALID_TARIF,
                "Tarif harus antara Rp100 dan Rp5.000 per kWh.",
                400,
            )
        tarif_val = tarif_dec
    else:
        # Tarif kosong
        if gol_str not in GOLONGAN:
            raise TagihanListrikError(
                INVALID_GOLONGAN,
                "Golongan tarif tidak dikenal.",
                400,
            )
        if gol_str == "sendiri":
            raise TagihanListrikError(
                INVALID_TARIF,
                "Isi tarif per kWh dulu, atau pilih golongan tarif.",
                400,
            )
        tarif_val = Decimal(str(GOLONGAN[gol_str]["tarif"]))

    # 4. Validasi token (opsional)
    token_is_empty = token is None or (isinstance(token, str) and not str(token).strip())
    token_nominal: int | None = None
    if not token_is_empty:
        token_dec = _parse_decimal_value(token)
        if token_dec is None or token_dec < TOKEN_MIN or token_dec > TOKEN_MAX:
            raise TagihanListrikError(
                INVALID_TOKEN,
                "Nominal token harus antara Rp1.000 dan Rp10.000.000.",
                400,
            )
        token_nominal = int(token_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    # 5. Perhitungan per alat & total
    total_wh_hari = Decimal("0")
    calc_list: list[dict[str, Any]] = []

    for item in parsed_items:
        wh_hari = item["watt"] * item["jam"] * Decimal(item["jumlah"])
        kwh_bulan = wh_hari * Decimal(HARI_PER_BULAN) / Decimal(1000)
        total_wh_hari += wh_hari
        calc_list.append(
            {
                "nama": item["nama"],
                "watt": item["watt"],
                "jam": item["jam"],
                "jumlah": item["jumlah"],
                "wh_hari": wh_hari,
                "kwh_bulan": kwh_bulan,
            }
        )

    kwh_bulan_total = total_wh_hari * Decimal(HARI_PER_BULAN) / Decimal(1000)
    kwh_hari_total = total_wh_hari / Decimal(1000)

    rupiah_bulan = int((kwh_bulan_total * tarif_val).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    rupiah_hari = int((kwh_hari_total * tarif_val).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    rupiah_tahun = int(rupiah_bulan * 12)

    rincian: list[dict[str, Any]] = []
    for item in calc_list:
        kwh_b = item["kwh_bulan"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rp_b = int((item["kwh_bulan"] * tarif_val).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if kwh_bulan_total > 0:
            persen = float((item["kwh_bulan"] / kwh_bulan_total * Decimal(100)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        else:
            persen = 0.0

        rincian.append(
            {
                "nama": item["nama"],
                "watt": float(item["watt"]),
                "jam": float(item["jam"]),
                "jumlah": item["jumlah"],
                "kwh_bulan": float(kwh_b),
                "rupiah_bulan": rp_b,
                "persen": persen,
            }
        )

    terbesar: dict[str, Any] | None = None
    if kwh_bulan_total > 0 and rupiah_bulan > 0:
        max_item = max(rincian, key=lambda x: (x["rupiah_bulan"], x["kwh_bulan"]))
        terbesar = {
            "nama": max_item["nama"],
            "rupiah_bulan": max_item["rupiah_bulan"],
            "persen": max_item["persen"],
        }

    token_dict: dict[str, Any] | None = None
    if token_nominal is not None:
        token_kwh = float((Decimal(token_nominal) / tarif_val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        if rupiah_bulan == 0:
            token_hari = 0.0
        else:
            per_hari_rp = Decimal(rupiah_bulan) / Decimal(HARI_PER_BULAN)
            token_hari = float((Decimal(token_nominal) / per_hari_rp).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))

        token_dict = {
            "nominal": token_nominal,
            "kwh": token_kwh,
            "hari": token_hari,
        }

    return {
        "ok": True,
        "jumlah_alat": len(rincian),
        "tarif": float(tarif_val),
        "golongan": gol_str,
        "kwh_hari": float(kwh_hari_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "kwh_bulan": float(kwh_bulan_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "rupiah_hari": rupiah_hari,
        "rupiah_bulan": rupiah_bulan,
        "rupiah_tahun": rupiah_tahun,
        "rincian": rincian,
        "terbesar": terbesar,
        "token": token_dict,
        "catatan": CATATAN,
    }
