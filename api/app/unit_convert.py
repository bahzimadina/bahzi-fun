"""Logika konversi satuan (Unit Converter): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import math
import re
from typing import Any

# Batas operasional
MAX_VALUE = 1e15
MAX_INPUT_CHARS = 40
MAX_DIGITS = 200

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NO_VALUE = "NO_VALUE"
NOT_A_NUMBER = "NOT_A_NUMBER"
OUT_OF_RANGE = "OUT_OF_RANGE"
UNSUPPORTED_CATEGORY = "UNSUPPORTED_CATEGORY"
UNSUPPORTED_UNIT = "UNSUPPORTED_UNIT"


class UnitConvertError(ValueError):
    """Galat operasional konversi satuan dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


# Definisi kategori dan satuan berurutan
CATEGORIES: dict[str, dict[str, Any]] = {
    "panjang": {
        "id": "panjang",
        "nama": "Panjang",
        "units": [
            {"value": "mm", "kode": "mm", "label": "Milimeter", "simbol": "mm", "factor": 0.001},
            {"value": "cm", "kode": "cm", "label": "Sentimeter", "simbol": "cm", "factor": 0.01},
            {"value": "m", "kode": "m", "label": "Meter", "simbol": "m", "factor": 1.0},
            {"value": "km", "kode": "km", "label": "Kilometer", "simbol": "km", "factor": 1000.0},
            {"value": "inci", "kode": "inci", "label": "Inci", "simbol": "in", "factor": 0.0254},
            {"value": "kaki", "kode": "kaki", "label": "Kaki", "simbol": "ft", "factor": 0.3048},
            {"value": "yard", "kode": "yard", "label": "Yard", "simbol": "yd", "factor": 0.9144},
            {"value": "mil", "kode": "mil", "label": "Mil", "simbol": "mil", "factor": 1609.344},
        ],
    },
    "massa": {
        "id": "massa",
        "nama": "Berat",
        "units": [
            {"value": "mg", "kode": "mg", "label": "Miligram", "simbol": "mg", "factor": 0.001},
            {"value": "g", "kode": "g", "label": "Gram", "simbol": "g", "factor": 1.0},
            {"value": "kg", "kode": "kg", "label": "Kilogram", "simbol": "kg", "factor": 1000.0},
            {"value": "ton", "kode": "ton", "label": "Ton", "simbol": "ton", "factor": 1000000.0},
            {"value": "pon", "kode": "pon", "label": "Pon", "simbol": "pon", "factor": 453.59237},
            {"value": "ons", "kode": "ons", "label": "Ons", "simbol": "ons", "factor": 100.0},
        ],
    },
    "suhu": {
        "id": "suhu",
        "nama": "Suhu",
        "units": [
            {"value": "celsius", "kode": "celsius", "label": "Celsius", "simbol": "°C"},
            {"value": "fahrenheit", "kode": "fahrenheit", "label": "Fahrenheit", "simbol": "°F"},
            {"value": "kelvin", "kode": "kelvin", "label": "Kelvin", "simbol": "K"},
            {"value": "reamur", "kode": "reamur", "label": "Reamur", "simbol": "°R"},
        ],
    },
    "luas": {
        "id": "luas",
        "nama": "Luas",
        "units": [
            {"value": "cm2", "kode": "cm2", "label": "Sentimeter persegi", "simbol": "cm²", "factor": 0.0001},
            {"value": "m2", "kode": "m2", "label": "Meter persegi", "simbol": "m²", "factor": 1.0},
            {"value": "are", "kode": "are", "label": "Are", "simbol": "are", "factor": 100.0},
            {"value": "hektar", "kode": "hektar", "label": "Hektar", "simbol": "ha", "factor": 10000.0},
            {"value": "km2", "kode": "km2", "label": "Kilometer persegi", "simbol": "km²", "factor": 1000000.0},
            {"value": "kaki2", "kode": "kaki2", "label": "Kaki persegi", "simbol": "ft²", "factor": 0.09290304},
            {"value": "acre", "kode": "acre", "label": "Acre", "simbol": "acre", "factor": 4046.8564224},
        ],
    },
    "volume": {
        "id": "volume",
        "nama": "Volume",
        "units": [
            {"value": "ml", "kode": "ml", "label": "Mililiter", "simbol": "ml", "factor": 0.001},
            {"value": "l", "kode": "l", "label": "Liter", "simbol": "l", "factor": 1.0},
            {"value": "m3", "kode": "m3", "label": "Meter kubik", "simbol": "m³", "factor": 1000.0},
            {"value": "cm3", "kode": "cm3", "label": "Sentimeter kubik", "simbol": "cm³", "factor": 0.001},
            {"value": "galon", "kode": "galon", "label": "Galon (AS)", "simbol": "gal", "factor": 3.785411784},
            {"value": "cup", "kode": "cup", "label": "Cangkir (AS)", "simbol": "cup", "factor": 0.2365882365},
        ],
    },
    "kecepatan": {
        "id": "kecepatan",
        "nama": "Kecepatan",
        "units": [
            {"value": "ms", "kode": "ms", "label": "Meter per detik", "simbol": "m/s", "factor": 1.0},
            {"value": "kmjam", "kode": "kmjam", "label": "Kilometer per jam", "simbol": "km/jam", "factor": 0.2777777777777778},
            {"value": "mph", "kode": "mph", "label": "Mil per jam", "simbol": "mph", "factor": 0.44704},
            {"value": "knot", "kode": "knot", "label": "Knot", "simbol": "knot", "factor": 0.5144444444444445},
        ],
    },
    "waktu": {
        "id": "waktu",
        "nama": "Waktu",
        "units": [
            {"value": "detik", "kode": "detik", "label": "Detik", "simbol": "detik", "factor": 1.0},
            {"value": "menit", "kode": "menit", "label": "Menit", "simbol": "menit", "factor": 60.0},
            {"value": "jam", "kode": "jam", "label": "Jam", "simbol": "jam", "factor": 3600.0},
            {"value": "hari", "kode": "hari", "label": "Hari", "simbol": "hari", "factor": 86400.0},
            {"value": "minggu", "kode": "minggu", "label": "Minggu", "simbol": "minggu", "factor": 604800.0},
            {"value": "bulan", "kode": "bulan", "label": "Bulan (30 hari)", "simbol": "bulan", "factor": 2592000.0},
            {"value": "tahun", "kode": "tahun", "label": "Tahun (365 hari)", "simbol": "tahun", "factor": 31536000.0},
        ],
    },
    "data": {
        "id": "data",
        "nama": "Data",
        "units": [
            {"value": "byte", "kode": "byte", "label": "Byte", "simbol": "B", "factor": 1.0},
            {"value": "kb", "kode": "kb", "label": "Kilobyte", "simbol": "KB", "factor": 1000.0},
            {"value": "mb", "kode": "mb", "label": "Megabyte", "simbol": "MB", "factor": 1000000.0},
            {"value": "gb", "kode": "gb", "label": "Gigabyte", "simbol": "GB", "factor": 1000000000.0},
            {"value": "tb", "kode": "tb", "label": "Terabyte", "simbol": "TB", "factor": 1000000000000.0},
            {"value": "kib", "kode": "kib", "label": "Kibibyte", "simbol": "KiB", "factor": 1024.0},
            {"value": "mib", "kode": "mib", "label": "Mebibyte", "simbol": "MiB", "factor": 1048576.0},
            {"value": "gib", "kode": "gib", "label": "Gibibyte", "simbol": "GiB", "factor": 1073741824.0},
            {"value": "tib", "kode": "tib", "label": "Tebibyte", "simbol": "TiB", "factor": 1099511627776.0},
        ],
    },
}


def format_angka(n: float) -> str:
    """Format angka sesuai aturan standar Indonesia.

    - n == 0 -> "0"
    - abs(n) >= 1e15 atau abs(n) < 1e-9 -> notasi eksponen bentuk "1,23457e+18"
      (6 angka penting, koma sebagai pemisah desimal, tanda + / - pada eksponen).
    - selain itu: bulatkan ke maksimum 6 angka di belakang koma, buang nol ekor dan koma
      yang jadi menggantung (mis. 200.0 -> "200", 2.5 -> "2,5", 0.000001 -> "0,000001",
      333.333333333 -> "333,333333").
    - pemisah ribuan titik, pemisah desimal koma (gaya Indonesia).
    - Tanda minus untuk nilai negatif. Jangan pernah menghasilkan "-0".
    """
    if n == 0 or abs(n) == 0.0:
        return "0"

    sign = "-" if n < 0 else ""
    abs_n = abs(n)

    if abs_n >= 1e15 or abs_n < 1e-9:
        s = f"{abs_n:.5e}".replace(".", ",")
        return f"{sign}{s}"

    d = Decimal(repr(abs_n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    formatted = f"{d:.6f}"
    int_part, dec_part = formatted.split(".")
    dec_part = dec_part.rstrip("0")
    int_formatted = f"{int(int_part):,}".replace(",", ".")

    if int_formatted == "0" and not dec_part:
        s = f"{abs_n:.5e}".replace(".", ",")
        return f"{sign}{s}"

    if dec_part:
        return f"{sign}{int_formatted},{dec_part}"
    return f"{sign}{int_formatted}"


def _parse_simple_number(s: str) -> float:
    """Parse string angka tanpa notasi eksponen e/E."""
    sign = 1.0
    if s.startswith("-"):
        sign = -1.0
        s = s[1:]
    elif s.startswith("+"):
        s = s[1:]

    if not s or sum(1 for c in s if c.isdigit()) == 0:
        raise UnitConvertError(NOT_A_NUMBER, "Nilai harus berupa angka yang valid.", 400)

    has_dot = "." in s
    has_comma = "," in s

    if has_dot and has_comma:
        last_dot = s.rfind(".")
        last_comma = s.rfind(",")
        if last_comma > last_dot:
            # Titik pemisah ribuan, koma pemisah desimal
            int_part = s[:last_comma].replace(".", "")
            dec_part = s[last_comma + 1 :]
        else:
            # Koma pemisah ribuan, titik pemisah desimal
            int_part = s[:last_dot].replace(",", "")
            dec_part = s[last_dot + 1 :]
        s_norm = f"{int_part}.{dec_part}"
    elif has_comma:
        if s.count(",") > 1:
            s_norm = s.replace(",", "")
        else:
            s_norm = s.replace(",", ".")
    elif has_dot:
        if s.count(".") > 1:
            s_norm = s.replace(".", "")
        else:
            s_norm = s
    else:
        s_norm = s

    try:
        val = float(s_norm) * sign
    except ValueError:
        raise UnitConvertError(NOT_A_NUMBER, "Nilai harus berupa angka yang valid.", 400)

    return val


def parse_value(value: Any) -> float:
    """Validasi dan parsing string angka dari pengguna ke float."""
    if value is None:
        raise UnitConvertError(INVALID_REQUEST, "Field 'value' wajib diisi.", 400)

    if not isinstance(value, str):
        raise UnitConvertError(INVALID_REQUEST, "Field 'value' harus berupa teks string.", 400)

    cleaned = value.strip()
    if not cleaned:
        raise UnitConvertError(NO_VALUE, "Nilai angka wajib diisi.", 400)

    if len(cleaned) > MAX_INPUT_CHARS:
        raise UnitConvertError(
            OUT_OF_RANGE,
            f"Panjang masukan ({len(cleaned)} karakter) melebihi batas {MAX_INPUT_CHARS} karakter.",
            413,
        )

    digit_count = sum(1 for c in cleaned if c.isdigit())
    if digit_count > MAX_DIGITS:
        raise UnitConvertError(
            OUT_OF_RANGE,
            f"Jumlah digit ({digit_count}) melebihi batas {MAX_DIGITS} digit.",
            413,
        )

    if digit_count == 0:
        raise UnitConvertError(NOT_A_NUMBER, "Nilai harus berupa angka yang valid.", 400)

    # Hanya karakter angka, tanda hubung, plus, spasi, titik, koma, e/E yang diizinkan
    if not re.fullmatch(r"[\s\d.,+\-eE]+", cleaned):
        raise UnitConvertError(NOT_A_NUMBER, "Nilai harus berupa angka yang valid.", 400)

    # Buang semua spasi (pemisah ribuan gaya spasi)
    s = re.sub(r"\s+", "", cleaned)

    if "e" in s.lower():
        parts = re.split(r"[eE]", s)
        if len(parts) != 2:
            raise UnitConvertError(NOT_A_NUMBER, "Format angka eksponen tidak valid.", 400)
        mantissa_str, exp_str = parts[0], parts[1]
        if not re.fullmatch(r"[+\-]?\d+", exp_str):
            raise UnitConvertError(NOT_A_NUMBER, "Eksponen harus berupa bilangan bulat.", 400)
        try:
            exp_val = int(exp_str)
        except ValueError:
            raise UnitConvertError(NOT_A_NUMBER, "Eksponen tidak valid.", 400)
        mantissa_val = _parse_simple_number(mantissa_str)
        try:
            num = mantissa_val * (10.0 ** exp_val)
        except OverflowError:
            raise UnitConvertError(OUT_OF_RANGE, "Nilai melebihi batas maksimum 1e15.", 413)
    else:
        num = _parse_simple_number(s)

    if math.isnan(num) or math.isinf(num):
        raise UnitConvertError(NOT_A_NUMBER, "Nilai bukan angka yang valid.", 400)

    if abs(num) > MAX_VALUE:
        raise UnitConvertError(
            OUT_OF_RANGE,
            "Nilai melebihi batas maksimum 1.000.000.000.000.000 (1e15).",
            413,
        )

    return num


def _celsius_to_suhu(c: float, unit_code: str) -> float:
    """Konversi dari derajat Celsius ke satuan suhu tujuan."""
    if unit_code == "celsius":
        return c
    if unit_code == "fahrenheit":
        return c * 9.0 / 5.0 + 32.0
    if unit_code == "kelvin":
        return c + 273.15
    if unit_code == "reamur":
        return c * 4.0 / 5.0
    raise UnitConvertError(UNSUPPORTED_UNIT, f"Satuan suhu '{unit_code}' tidak didukung.", 400)


def _suhu_to_celsius(val: float, unit_code: str) -> float:
    """Konversi dari satuan suhu asal ke derajat Celsius."""
    if unit_code == "celsius":
        return val
    if unit_code == "fahrenheit":
        return (val - 32.0) * 5.0 / 9.0
    if unit_code == "kelvin":
        return val - 273.15
    if unit_code == "reamur":
        return val * 5.0 / 4.0
    raise UnitConvertError(UNSUPPORTED_UNIT, f"Satuan suhu '{unit_code}' tidak didukung.", 400)


def convert(value: Any, category: Any, from_unit: Any, to_unit: Any) -> dict[str, Any]:
    """Konversi nilai antar satuan dalam satu kategori."""
    if category is None or from_unit is None or to_unit is None:
        raise UnitConvertError(
            INVALID_REQUEST,
            "Field 'value', 'category', 'from', dan 'to' wajib diisi.",
            400,
        )

    if not isinstance(category, str) or not isinstance(from_unit, str) or not isinstance(to_unit, str):
        raise UnitConvertError(
            INVALID_REQUEST,
            "Field 'category', 'from', dan 'to' harus berupa teks string.",
            400,
        )

    cat_norm = category.strip().lower()
    if cat_norm == "berat":
        cat_norm = "massa"

    if cat_norm not in CATEGORIES:
        raise UnitConvertError(
            UNSUPPORTED_CATEGORY,
            f"Kategori '{category}' tidak didukung. Pilih: {', '.join(CATEGORIES.keys())}.",
            400,
        )

    cat_info = CATEGORIES[cat_norm]
    unit_map = {u["kode"]: u for u in cat_info["units"]}

    from_norm = from_unit.strip().lower()
    to_norm = to_unit.strip().lower()

    if from_norm not in unit_map or to_norm not in unit_map:
        raise UnitConvertError(
            UNSUPPORTED_UNIT,
            f"Satuan tidak didukung dalam kategori '{cat_info['nama']}'.",
            400,
        )

    from_obj = unit_map[from_norm]
    to_obj = unit_map[to_norm]

    nilai_masuk = parse_value(value)

    if cat_norm == "suhu":
        celsius_val = _suhu_to_celsius(nilai_masuk, from_norm)
        hasil = _celsius_to_suhu(celsius_val, to_norm)
        laju = _celsius_to_suhu(_suhu_to_celsius(1.0, from_norm), to_norm)
        catatan = "Konversi suhu menggunakan rumus pergeseran skala, bukan sekadar faktor kelipatan tetap."

        semua = []
        for u in cat_info["units"]:
            u_val = _celsius_to_suhu(celsius_val, u["kode"])
            semua.append({
                "kode": u["kode"],
                "label": u["label"],
                "simbol": u["simbol"],
                "nilai": u_val,
                "teks": format_angka(u_val),
            })
    else:
        # Basis perkalian faktor
        base_val = nilai_masuk * from_obj["factor"]
        hasil = base_val / to_obj["factor"]
        laju = from_obj["factor"] / to_obj["factor"]
        catatan = ""

        semua = []
        for u in cat_info["units"]:
            u_val = base_val / u["factor"]
            semua.append({
                "kode": u["kode"],
                "label": u["label"],
                "simbol": u["simbol"],
                "nilai": u_val,
                "teks": format_angka(u_val),
            })

    hasil_teks = format_angka(hasil)
    laju_teks = format_angka(laju)

    return {
        "kategori": {"id": cat_info["id"], "nama": cat_info["nama"]},
        "dari": {"kode": from_obj["kode"], "label": from_obj["label"], "simbol": from_obj["simbol"]},
        "ke": {"kode": to_obj["kode"], "label": to_obj["label"], "simbol": to_obj["simbol"]},
        "nilai_masuk": nilai_masuk,
        "hasil": hasil,
        "hasil_teks": hasil_teks,
        "laju": laju,
        "laju_teks": laju_teks,
        "semua": semua,
        "catatan": catatan,
    }
