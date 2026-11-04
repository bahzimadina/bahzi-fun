"""Logika kalkulator kebutuhan cor beton: fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import math
import re
from typing import Any

# Batas operasional dimensi dan volume
MIN_PANJANG_M = 0.1
MAX_PANJANG_M = 500.0

MIN_LEBAR_M = 0.1
MAX_LEBAR_M = 500.0

MIN_TEBAL_PLAT_CM = 5.0
MAX_TEBAL_PLAT_CM = 100.0

MIN_LEBAR_BALOK_CM = 10.0
MAX_LEBAR_BALOK_CM = 100.0

MIN_TINGGI_BALOK_CM = 10.0
MAX_TINGGI_BALOK_CM = 200.0

MIN_JUMLAH_KOLOM = 1
MAX_JUMLAH_KOLOM = 500

MIN_TINGGI_KOLOM_M = 0.5
MAX_TINGGI_KOLOM_M = 20.0

MIN_LEBAR_KOLOM_CM = 10.0
MAX_LEBAR_KOLOM_CM = 100.0

MIN_TINGGI_KOLOM_CM = 10.0
MAX_TINGGI_KOLOM_CM = 100.0

MIN_VOLUME_M3 = 0.01
MAX_VOLUME_M3 = 2000.0

MIN_CADANGAN = 0
MAX_CADANGAN = 15
DEFAULT_CADANGAN = 5

MIN_KAPASITAS_TRUK = 3.0
MAX_KAPASITAS_TRUK = 12.0
DEFAULT_KAPASITAS_TRUK = 7.0

MIN_HARGA = 0
MAX_HARGA = 100_000_000

MAX_BODY_BYTES = 64 * 1024

# Konstanta material
SEMEN_KG_PER_SAK = 50
PASIR_KG_PER_M3 = 1400
KERIKIL_KG_PER_M3 = 1350

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
UNSUPPORTED_MUTU = "UNSUPPORTED_MUTU"
INVALID_NUMBER = "INVALID_NUMBER"
OUT_OF_RANGE = "OUT_OF_RANGE"
INVALID_CADANGAN = "INVALID_CADANGAN"
INVALID_HARGA = "INVALID_HARGA"
INVALID_KAPASITAS_TRUK = "INVALID_KAPASITAS_TRUK"
VOLUME_TOO_LARGE = "VOLUME_TOO_LARGE"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class CorBetonError(ValueError):
    """Galat operasional kalkulator cor beton dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        err = {"code": self.code, "message": self.message}
        return {"error": err, "detail": err}


TABEL_MUTU: dict[str, dict[str, Any]] = {
    "k175": {
        "kode": "k175",
        "label": "K-175",
        "semen_kg_per_m3": 326,
        "pasir_kg_per_m3": 760,
        "kerikil_kg_per_m3": 1029,
        "air_liter_per_m3": 215,
        "deskripsi": "Beton non-struktural, rabat lantai kerja, jalan setapak",
    },
    "k225": {
        "kode": "k225",
        "label": "K-225",
        "semen_kg_per_m3": 371,
        "pasir_kg_per_m3": 698,
        "kerikil_kg_per_m3": 1047,
        "air_liter_per_m3": 215,
        "deskripsi": "Standar rumah tinggal 1-2 lantai (sloof, kolom praktis, pelat dak)",
    },
    "k250": {
        "kode": "k250",
        "label": "K-250",
        "semen_kg_per_m3": 384,
        "pasir_kg_per_m3": 692,
        "kerikil_kg_per_m3": 1039,
        "air_liter_per_m3": 215,
        "deskripsi": "Konstruksi bertulang beban sedang, dak lantai jemur, balok gantung",
    },
    "k300": {
        "kode": "k300",
        "label": "K-300",
        "semen_kg_per_m3": 413,
        "pasir_kg_per_m3": 681,
        "kerikil_kg_per_m3": 1027,
        "air_liter_per_m3": 215,
        "deskripsi": "Struktur beban berat, ruko bertingkat, lantai gudang",
    },
}


def format_angka_id(val: int | float, max_desimal: int = 3) -> str:
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


def parse_decimal_number(
    val: Any,
    label: str,
    min_val: float | None = None,
    max_val: float | None = None,
    satuan: str = "",
) -> float:
    """Validasi dan konversi nilai angka desimal ke float."""
    if val is None:
        raise CorBetonError(INVALID_REQUEST, f"{label} wajib diisi.", 400)

    if isinstance(val, bool):
        raise CorBetonError(INVALID_NUMBER, f"{label} harus berupa angka yang valid.", 400)

    if isinstance(val, (int, float)):
        num = float(val)
        if math.isnan(num) or math.isinf(num):
            raise CorBetonError(INVALID_NUMBER, f"{label} bukan angka yang valid.", 400)
    elif isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            raise CorBetonError(INVALID_NUMBER, f"{label} tidak boleh kosong.", 400)

        dot_count = cleaned.count(".")
        comma_count = cleaned.count(",")
        if (dot_count + comma_count) > 1:
            raise CorBetonError(
                INVALID_NUMBER,
                f"Format angka {label.lower()} tidak valid. Gunakan satu tanda titik atau koma desimal.",
                400,
            )

        normalized = cleaned.replace(",", ".")
        if not re.fullmatch(r"^\d+(\.\d+)?$", normalized):
            raise CorBetonError(
                INVALID_NUMBER,
                f"{label} harus berupa angka positif yang valid.",
                400,
            )

        try:
            num = float(normalized)
        except ValueError:
            raise CorBetonError(INVALID_NUMBER, f"{label} tidak dapat dibaca sebagai angka.", 400)

        if math.isnan(num) or math.isinf(num):
            raise CorBetonError(INVALID_NUMBER, f"{label} bukan angka yang valid.", 400)
    else:
        raise CorBetonError(INVALID_REQUEST, f"{label} harus berupa teks angka atau bilangan.", 400)

    if min_val is not None and max_val is not None:
        if num < min_val or num > max_val:
            unit_str = f" {satuan}" if satuan else ""
            min_str = format_angka_id(min_val)
            max_str = format_angka_id(max_val)
            raise CorBetonError(
                OUT_OF_RANGE,
                f"{label} harus antara {min_str} dan {max_str}{unit_str}.",
                400,
            )

    return num


def parse_integer_number(
    val: Any,
    label: str,
    min_val: int | None = None,
    max_val: int | None = None,
    satuan: str = "",
) -> int:
    """Validasi dan konversi nilai bilangan bulat."""
    if val is None:
        raise CorBetonError(INVALID_REQUEST, f"{label} wajib diisi.", 400)

    if isinstance(val, bool):
        raise CorBetonError(INVALID_NUMBER, f"{label} harus berupa bilangan bulat.", 400)

    if isinstance(val, (int, float)):
        if isinstance(val, float) and not val.is_integer():
            raise CorBetonError(INVALID_NUMBER, f"{label} harus berupa bilangan bulat.", 400)
        num = int(val)
    elif isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            raise CorBetonError(INVALID_NUMBER, f"{label} tidak boleh kosong.", 400)
        if not re.fullmatch(r"^\d+$", cleaned):
            raise CorBetonError(INVALID_NUMBER, f"{label} harus berupa bilangan bulat positif.", 400)
        try:
            num = int(cleaned)
        except ValueError:
            raise CorBetonError(INVALID_NUMBER, f"{label} tidak valid.", 400)
    else:
        raise CorBetonError(INVALID_REQUEST, f"{label} harus berupa teks angka bilangan bulat.", 400)

    if min_val is not None and max_val is not None:
        if num < min_val or num > max_val:
            unit_str = f" {satuan}" if satuan else ""
            min_str = format_angka_id(min_val)
            max_str = format_angka_id(max_val)
            raise CorBetonError(
                OUT_OF_RANGE,
                f"{label} harus antara {min_str} dan {max_str}{unit_str}.",
                400,
            )

    return num


def parse_cadangan(val: Any) -> int:
    """Validasi dan parsing persentase cadangan cor beton (0..15%)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return DEFAULT_CADANGAN

    if isinstance(val, bool):
        raise CorBetonError(INVALID_CADANGAN, "Persentase cadangan harus berupa bilangan bulat.", 400)

    if isinstance(val, (int, float)):
        if isinstance(val, float) and not val.is_integer():
            raise CorBetonError(INVALID_CADANGAN, "Persentase cadangan harus berupa bilangan bulat.", 400)
        num = int(val)
    elif isinstance(val, str):
        s = val.strip()
        if s.startswith("-"):
            raise CorBetonError(INVALID_CADANGAN, "Persentase cadangan tidak boleh bernilai negatif.", 400)
        if not re.fullmatch(r"^\d+$", s):
            raise CorBetonError(
                INVALID_CADANGAN,
                f"Persentase cadangan harus berupa bilangan bulat antara {MIN_CADANGAN} hingga {MAX_CADANGAN} persen.",
                400,
            )
        try:
            num = int(s)
        except ValueError:
            raise CorBetonError(INVALID_CADANGAN, "Persentase cadangan tidak valid.", 400)
    else:
        raise CorBetonError(INVALID_CADANGAN, "Persentase cadangan tidak valid.", 400)

    if num < MIN_CADANGAN or num > MAX_CADANGAN:
        raise CorBetonError(
            INVALID_CADANGAN,
            f"Persentase cadangan harus antara {MIN_CADANGAN} hingga {MAX_CADANGAN} persen.",
            400,
        )

    return num


def parse_kapasitas_truk(val: Any) -> float:
    """Validasi dan parsing kapasitas truk mixer readymix (3..12 m3)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return DEFAULT_KAPASITAS_TRUK

    if isinstance(val, bool):
        raise CorBetonError(INVALID_KAPASITAS_TRUK, "Kapasitas truk mixer harus berupa angka yang valid.", 400)

    if isinstance(val, (int, float)):
        num = float(val)
    elif isinstance(val, str):
        s = val.strip().replace(",", ".")
        if not re.fullmatch(r"^\d+(\.\d+)?$", s):
            min_kap = format_angka_id(MIN_KAPASITAS_TRUK)
            max_kap = format_angka_id(MAX_KAPASITAS_TRUK)
            raise CorBetonError(
                INVALID_KAPASITAS_TRUK,
                f"Kapasitas truk mixer harus berupa angka antara {min_kap} hingga {max_kap} m³.",
                400,
            )
        try:
            num = float(s)
        except ValueError:
            raise CorBetonError(INVALID_KAPASITAS_TRUK, "Kapasitas truk mixer tidak valid.", 400)
    else:
        raise CorBetonError(INVALID_KAPASITAS_TRUK, "Kapasitas truk mixer tidak valid.", 400)

    if num < MIN_KAPASITAS_TRUK or num > MAX_KAPASITAS_TRUK:
        min_kap = format_angka_id(MIN_KAPASITAS_TRUK)
        max_kap = format_angka_id(MAX_KAPASITAS_TRUK)
        raise CorBetonError(
            INVALID_KAPASITAS_TRUK,
            f"Kapasitas truk mixer harus antara {min_kap} hingga {max_kap} m³.",
            400,
        )

    return num


def parse_harga(val: Any, label: str = "Harga") -> int | None:
    """Validasi dan parsing harga rupiah (0..100.000.000). Mengembalikan None jika kosong."""
    if val is None:
        return None

    if isinstance(val, bool):
        raise CorBetonError(INVALID_HARGA, f"{label} harus berupa bilangan bulat rupiah.", 400)

    if isinstance(val, (int, float)):
        if isinstance(val, float) and not val.is_integer():
            raise CorBetonError(INVALID_HARGA, f"{label} harus berupa bilangan bulat rupiah.", 400)
        num = int(val)
        if num < 0:
            raise CorBetonError(INVALID_HARGA, f"{label} tidak boleh bernilai negatif.", 400)
    elif isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        if s.startswith("-"):
            raise CorBetonError(INVALID_HARGA, f"{label} tidak boleh bernilai negatif.", 400)
        s_clean = s.replace(".", "").replace(",", "").replace(" ", "")
        if not re.fullmatch(r"^\d+$", s_clean):
            raise CorBetonError(
                INVALID_HARGA,
                f"{label} harus berupa bilangan bulat rupiah tanpa simbol atau huruf.",
                400,
            )
        try:
            num = int(s_clean)
        except ValueError:
            raise CorBetonError(INVALID_HARGA, f"{label} tidak valid.", 400)
    else:
        raise CorBetonError(INVALID_HARGA, f"{label} tidak valid.", 400)

    if num < MIN_HARGA or num > MAX_HARGA:
        raise CorBetonError(
            INVALID_HARGA,
            f"{label} harus antara Rp {format_angka_id(MIN_HARGA)} hingga Rp {format_angka_id(MAX_HARGA)}.",
            400,
        )

    return num


def hitung_cor_beton(
    mode: Any = "plat",
    panjang: Any = None,
    lebar: Any = None,
    tinggi: Any = None,
    jumlah: Any = None,
    volume: Any = None,
    mutu: Any = "k225",
    cadangan: Any = DEFAULT_CADANGAN,
    harga_semen: Any = None,
    harga_pasir: Any = None,
    harga_kerikil: Any = None,
    harga_readymix: Any = None,
    kapasitas_truk: Any = DEFAULT_KAPASITAS_TRUK,
) -> dict[str, Any]:
    """Hitung kebutuhan cor beton, bahan, truk readymix, dan estimasi biaya murni di memori."""
    if mode is None:
        raise CorBetonError(INVALID_REQUEST, "Mode perhitungan cor beton wajib dipilih.", 400)
    if not isinstance(mode, str):
        raise CorBetonError(INVALID_REQUEST, "Mode perhitungan harus berupa teks string.", 400)

    mode_norm = mode.strip().lower()
    if mode_norm not in ("plat", "balok", "kolom", "volume"):
        raise CorBetonError(
            UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak didukung. Pilihan: plat, balok, kolom, atau volume.",
            400,
        )

    if mutu is None or (isinstance(mutu, str) and not mutu.strip()):
        mutu_norm = "k225"
    elif isinstance(mutu, str):
        mutu_norm = mutu.strip().lower()
    else:
        raise CorBetonError(UNSUPPORTED_MUTU, "Pilihan mutu beton tidak valid.", 400)

    if mutu_norm not in TABEL_MUTU:
        daftar_mutu = ", ".join(TABEL_MUTU.keys())
        raise CorBetonError(
            UNSUPPORTED_MUTU,
            f"Mutu beton '{mutu}' tidak didukung. Pilihan: {daftar_mutu}.",
            400,
        )

    info_mutu = TABEL_MUTU[mutu_norm]

    # Parsing dimensi per mode
    dimensi: dict[str, Any] = {}
    if mode_norm == "plat":
        p_m = parse_decimal_number(panjang, "Panjang pelat", MIN_PANJANG_M, MAX_PANJANG_M, "m")
        l_m = parse_decimal_number(lebar, "Lebar pelat", MIN_LEBAR_M, MAX_LEBAR_M, "m")
        t_cm = parse_decimal_number(tinggi, "Tebal pelat", MIN_TEBAL_PLAT_CM, MAX_TEBAL_PLAT_CM, "cm")
        dimensi = {
            "panjang_m": int(p_m) if p_m.is_integer() else p_m,
            "lebar_m": int(l_m) if l_m.is_integer() else l_m,
            "tebal_cm": int(t_cm) if t_cm.is_integer() else t_cm,
        }
        d_p = Decimal(str(p_m))
        d_l = Decimal(str(l_m))
        d_t = Decimal(str(t_cm)) / Decimal("100")
        d_vol_kotor = d_p * d_l * d_t

    elif mode_norm == "balok":
        p_m = parse_decimal_number(panjang, "Panjang balok", MIN_PANJANG_M, MAX_PANJANG_M, "m")
        l_cm = parse_decimal_number(lebar, "Lebar penampang balok", MIN_LEBAR_BALOK_CM, MAX_LEBAR_BALOK_CM, "cm")
        t_cm = parse_decimal_number(tinggi, "Tinggi penampang balok", MIN_TINGGI_BALOK_CM, MAX_TINGGI_BALOK_CM, "cm")
        dimensi = {
            "panjang_m": int(p_m) if p_m.is_integer() else p_m,
            "lebar_cm": int(l_cm) if l_cm.is_integer() else l_cm,
            "tinggi_cm": int(t_cm) if t_cm.is_integer() else t_cm,
        }
        d_p = Decimal(str(p_m))
        d_l = Decimal(str(l_cm)) / Decimal("100")
        d_t = Decimal(str(t_cm)) / Decimal("100")
        d_vol_kotor = d_p * d_l * d_t

    elif mode_norm == "kolom":
        jml = parse_integer_number(jumlah, "Jumlah kolom", MIN_JUMLAH_KOLOM, MAX_JUMLAH_KOLOM, "buah")
        p_m = parse_decimal_number(panjang, "Tinggi kolom", MIN_TINGGI_KOLOM_M, MAX_TINGGI_KOLOM_M, "m")
        l_cm = parse_decimal_number(lebar, "Lebar penampang kolom", MIN_LEBAR_KOLOM_CM, MAX_LEBAR_KOLOM_CM, "cm")
        t_cm = parse_decimal_number(tinggi, "Tinggi penampang kolom", MIN_TINGGI_KOLOM_CM, MAX_TINGGI_KOLOM_CM, "cm")
        dimensi = {
            "jumlah": jml,
            "panjang_m": int(p_m) if p_m.is_integer() else p_m,
            "lebar_cm": int(l_cm) if l_cm.is_integer() else l_cm,
            "tinggi_cm": int(t_cm) if t_cm.is_integer() else t_cm,
        }
        d_jml = Decimal(str(jml))
        d_p = Decimal(str(p_m))
        d_l = Decimal(str(l_cm)) / Decimal("100")
        d_t = Decimal(str(t_cm)) / Decimal("100")
        d_vol_kotor = d_jml * d_p * d_l * d_t

    else:  # volume
        vol_m3 = parse_decimal_number(volume, "Volume beton", MIN_VOLUME_M3, MAX_VOLUME_M3, "m³")
        dimensi = {
            "volume_m3": int(vol_m3) if vol_m3.is_integer() else vol_m3,
        }
        d_vol_kotor = Decimal(str(vol_m3))

    cadangan_persen = parse_cadangan(cadangan)
    kap_truk = parse_kapasitas_truk(kapasitas_truk)

    # Volume kotor dibulatkan ke float yang rapi
    volume_kotor_m3 = float(d_vol_kotor.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))
    if volume_kotor_m3.is_integer():
        volume_kotor_m3 = float(int(volume_kotor_m3))

    # Volume akhir dengan cadangan
    d_cadangan = Decimal(str(cadangan_persen)) / Decimal("100")
    d_vol_m3 = (d_vol_kotor * (Decimal("1") + d_cadangan)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    volume_m3 = float(d_vol_m3)

    if volume_m3 > MAX_VOLUME_M3:
        vol_str = format_angka_id(volume_m3, 3)
        max_vol_str = format_angka_id(MAX_VOLUME_M3)
        raise CorBetonError(
            VOLUME_TOO_LARGE,
            f"Volume beton setelah cadangan ({vol_str} m³) melebihi batas maksimum {max_vol_str} m³. Periksa kembali ukuran pekerjaan.",
            413,
        )

    # Perhitungan bahan adonan manual
    d_semen_per_m3 = Decimal(str(info_mutu["semen_kg_per_m3"]))
    d_semen_kg = d_vol_m3 * d_semen_per_m3
    semen_kg = float(d_semen_kg.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    semen_sak = int((d_semen_kg / Decimal(str(SEMEN_KG_PER_SAK))).to_integral_value(rounding=ROUND_CEILING))

    d_pasir_per_m3 = Decimal(str(info_mutu["pasir_kg_per_m3"]))
    d_pasir_m3 = ((d_vol_m3 * d_pasir_per_m3) / Decimal(str(PASIR_KG_PER_M3))).quantize(
        Decimal("0.01"), rounding=ROUND_CEILING
    )
    pasir_m3 = float(d_pasir_m3)

    d_kerikil_per_m3 = Decimal(str(info_mutu["kerikil_kg_per_m3"]))
    d_kerikil_m3 = ((d_vol_m3 * d_kerikil_per_m3) / Decimal(str(KERIKIL_KG_PER_M3))).quantize(
        Decimal("0.01"), rounding=ROUND_CEILING
    )
    kerikil_m3 = float(d_kerikil_m3)

    d_air_per_m3 = Decimal(str(info_mutu["air_liter_per_m3"]))
    d_air_liter = (d_vol_m3 * d_air_per_m3).to_integral_value(rounding=ROUND_CEILING)
    air_liter = int(d_air_liter)

    bahan = {
        "semen_kg": semen_kg,
        "semen_sak": semen_sak,
        "pasir_m3": pasir_m3,
        "kerikil_m3": kerikil_m3,
        "air_liter": air_liter,
    }

    # Perhitungan truk readymix
    d_kap_truk = Decimal(str(kap_truk))
    truk = int((d_vol_m3 / d_kap_truk).to_integral_value(rounding=ROUND_CEILING))
    d_sisa = (Decimal(str(truk)) * d_kap_truk - d_vol_m3).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sisa_kapasitas_m3 = float(d_sisa)

    readymix = {
        "kapasitas_truk_m3": int(kap_truk) if float(kap_truk).is_integer() else kap_truk,
        "truk": truk,
        "sisa_kapasitas_m3": sisa_kapasitas_m3,
    }

    # Perkiraan biaya
    h_semen = parse_harga(harga_semen, "Harga semen")
    h_pasir = parse_harga(harga_pasir, "Harga pasir")
    h_kerikil = parse_harga(harga_kerikil, "Harga kerikil")
    h_readymix = parse_harga(harga_readymix, "Harga readymix")

    biaya_adukan: int | None = None
    per_m3_adukan: int | None = None
    if h_semen is not None and h_pasir is not None and h_kerikil is not None:
        d_biaya_semen = Decimal(str(semen_sak)) * Decimal(str(h_semen))
        d_biaya_pasir = Decimal(str(pasir_m3)) * Decimal(str(h_pasir))
        d_biaya_kerikil = Decimal(str(kerikil_m3)) * Decimal(str(h_kerikil))
        d_total_adukan = (d_biaya_semen + d_biaya_pasir + d_biaya_kerikil).to_integral_value(rounding=ROUND_HALF_UP)
        biaya_adukan = int(d_total_adukan)
        if volume_m3 > 0:
            per_m3_adukan = int((d_total_adukan / d_vol_m3).to_integral_value(rounding=ROUND_HALF_UP))

    biaya_readymix: int | None = None
    per_m3_readymix: int | None = None
    if h_readymix is not None:
        d_total_readymix = (d_vol_m3 * Decimal(str(h_readymix))).to_integral_value(rounding=ROUND_HALF_UP)
        biaya_readymix = int(d_total_readymix)
        per_m3_readymix = h_readymix

    selisih: int | None = None
    if biaya_adukan is not None and biaya_readymix is not None:
        selisih = biaya_readymix - biaya_adukan

    biaya = {
        "adukan": biaya_adukan,
        "readymix": biaya_readymix,
        "selisih": selisih,
        "per_m3_adukan": per_m3_adukan,
        "per_m3_readymix": per_m3_readymix,
    }

    catatan = [
        "Hasil perhitungan adalah perkiraan material beton cor; kebutuhan besi tulangan, kawat bendrat, bekisting, dan upah tukang belum termasuk.",
        "Komposisi bahan mengacu pada patokan umum per 1 m³ beton dan dapat berbeda dengan kondisi agregat (kadar air pasir & kerikil) di lokasi proyek.",
        "Untuk pekerjaan struktural penting (fondasi cakar ayam, sloof, kolom utama, pelat lantai), selalu sesuaikan dengan gambar kerja teknis dan instruksi pengawas.",
    ]

    return {
        "mode": mode_norm,
        "mutu": {
            "kode": info_mutu["kode"],
            "label": info_mutu["label"],
            "semen_kg_per_m3": info_mutu["semen_kg_per_m3"],
            "pasir_kg_per_m3": info_mutu["pasir_kg_per_m3"],
            "kerikil_kg_per_m3": info_mutu["kerikil_kg_per_m3"],
            "air_liter_per_m3": info_mutu["air_liter_per_m3"],
        },
        "dimensi": dimensi,
        "volume_kotor_m3": volume_kotor_m3,
        "cadangan_persen": cadangan_persen,
        "volume_m3": volume_m3,
        "bahan": bahan,
        "readymix": readymix,
        "biaya": biaya,
        "catatan": catatan,
    }


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional, pilihan mutu beton, dan konstanta bahan."""
    return {
        "modes": [
            {
                "value": "plat",
                "label": "Pelat lantai",
                "fields": ["panjang", "lebar", "tinggi"],
                "satuan": {"panjang": "m", "lebar": "m", "tinggi": "cm (tebal pelat)"},
            },
            {
                "value": "balok",
                "label": "Balok",
                "fields": ["panjang", "lebar", "tinggi"],
                "satuan": {"panjang": "m (total panjang)", "lebar": "cm (penampang)", "tinggi": "cm (penampang)"},
            },
            {
                "value": "kolom",
                "label": "Kolom",
                "fields": ["jumlah", "panjang", "lebar", "tinggi"],
                "satuan": {"jumlah": "buah", "panjang": "m (tinggi kolom)", "lebar": "cm (penampang)", "tinggi": "cm (penampang)"},
            },
            {
                "value": "volume",
                "label": "Volume jadi",
                "fields": ["volume"],
                "satuan": {"volume": "m³"},
            },
        ],
        "mutu_pilihan": [
            {
                "kode": k,
                "label": v["label"],
                "semen_kg_per_m3": v["semen_kg_per_m3"],
                "pasir_kg_per_m3": v["pasir_kg_per_m3"],
                "kerikil_kg_per_m3": v["kerikil_kg_per_m3"],
                "air_liter_per_m3": v["air_liter_per_m3"],
                "deskripsi": v["deskripsi"],
            }
            for k, v in TABEL_MUTU.items()
        ],
        "cadangan": {
            "min": MIN_CADANGAN,
            "max": MAX_CADANGAN,
            "bawaan": DEFAULT_CADANGAN,
            "satuan": "%",
        },
        "kapasitas_truk": {
            "min": MIN_KAPASITAS_TRUK,
            "max": MAX_KAPASITAS_TRUK,
            "bawaan": DEFAULT_KAPASITAS_TRUK,
            "satuan": "m³",
        },
        "batas_angka": {
            "panjang_m": {"min": MIN_PANJANG_M, "max": MAX_PANJANG_M, "satuan": "m"},
            "lebar_m": {"min": MIN_LEBAR_M, "max": MAX_LEBAR_M, "satuan": "m"},
            "tebal_plat_cm": {"min": MIN_TEBAL_PLAT_CM, "max": MAX_TEBAL_PLAT_CM, "satuan": "cm"},
            "lebar_balok_cm": {"min": MIN_LEBAR_BALOK_CM, "max": MAX_LEBAR_BALOK_CM, "satuan": "cm"},
            "tinggi_balok_cm": {"min": MIN_TINGGI_BALOK_CM, "max": MAX_TINGGI_BALOK_CM, "satuan": "cm"},
            "jumlah_kolom": {"min": MIN_JUMLAH_KOLOM, "max": MAX_JUMLAH_KOLOM, "satuan": "buah"},
            "tinggi_kolom_m": {"min": MIN_TINGGI_KOLOM_M, "max": MAX_TINGGI_KOLOM_M, "satuan": "m"},
            "lebar_kolom_cm": {"min": MIN_LEBAR_KOLOM_CM, "max": MAX_LEBAR_KOLOM_CM, "satuan": "cm"},
            "tinggi_kolom_cm": {"min": MIN_TINGGI_KOLOM_CM, "max": MAX_TINGGI_KOLOM_CM, "satuan": "cm"},
            "volume_m3": {"min": MIN_VOLUME_M3, "max": MAX_VOLUME_M3, "satuan": "m³"},
            "harga": {"min": MIN_HARGA, "max": MAX_HARGA, "satuan": "rupiah"},
        },
        "konstanta": {
            "semen_kg_per_sak": SEMEN_KG_PER_SAK,
            "pasir_kg_per_m3": PASIR_KG_PER_M3,
            "kerikil_kg_per_m3": KERIKIL_KG_PER_M3,
        },
        "max_body_bytes": MAX_BODY_BYTES,
        "processed_on": "server",
        "note": "Perhitungan bahan beton mengacu pada patokan proporsi umum, bukan acuan SNI resmi proyek skala besar. Besi beton, bekisting, dan upah kerja belum termasuk.",
    }
