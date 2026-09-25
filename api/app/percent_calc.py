"""Logika kalkulator persen (Percent Calculator): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import math
import re
from typing import Any

# Batas operasional
MAX_INPUT_CHARS = 40
MAX_ABS_VALUE = 1e15

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NO_VALUE = "NO_VALUE"
NOT_A_NUMBER = "NOT_A_NUMBER"
OUT_OF_RANGE = "OUT_OF_RANGE"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
DIVIDE_BY_ZERO = "DIVIDE_BY_ZERO"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class PercentCalcError(ValueError):
    """Galat operasional kalkulator persen dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


MODES: list[dict[str, Any]] = [
    {
        "value": "persen_dari",
        "label": "Berapa persen dari sebuah angka",
        "a_label": "Persen (%)",
        "b_label": "Angka",
        "hasil_satuan": "",
        "contoh": {"a": "20", "b": "150"},
    },
    {
        "value": "berapa_persen",
        "label": "Sebuah angka itu berapa persen dari angka lain",
        "a_label": "Bagian",
        "b_label": "Total",
        "hasil_satuan": "%",
        "contoh": {"a": "45", "b": "180"},
    },
    {
        "value": "perubahan",
        "label": "Naik atau turun berapa persen",
        "a_label": "Angka awal",
        "b_label": "Angka akhir",
        "hasil_satuan": "%",
        "contoh": {"a": "200", "b": "250"},
    },
    {
        "value": "tambah_persen",
        "label": "Angka ditambah persen",
        "a_label": "Persen (%)",
        "b_label": "Angka dasar",
        "hasil_satuan": "",
        "contoh": {"a": "10", "b": "150"},
    },
    {
        "value": "kurang_persen",
        "label": "Angka dikurangi persen (diskon)",
        "a_label": "Persen (%)",
        "b_label": "Angka dasar",
        "hasil_satuan": "",
        "contoh": {"a": "15", "b": "200"},
    },
]


def format_angka(n: float) -> str:
    """Format angka sesuai aturan standar Indonesia.

    - n == 0 -> "0"
    - abs(n) >= 1e15 atau abs(n) < 1e-6 -> notasi eksponen gaya Indonesia
      (mis. "1,25e+18" atau "5e-07").
    - selain itu: bulatkan maksimum 6 angka di belakang koma, buang nol ekor,
      titik sebagai pemisah ribuan, koma sebagai desimal.
    - tanda minus untuk nilai negatif. Jangan pernah menghasilkan "-0".
    """
    if n == 0 or abs(n) == 0.0:
        return "0"

    sign = "-" if n < 0 else ""
    abs_n = abs(n)

    if abs_n >= 1e15 or abs_n < 1e-6:
        s = f"{abs_n:.6g}".replace(".", ",")
        return f"{sign}{s}"

    d = Decimal(repr(abs_n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    formatted = f"{d:.6f}"
    int_part, dec_part = formatted.split(".")
    dec_part = dec_part.rstrip("0")
    int_formatted = f"{int(int_part):,}".replace(",", ".")

    if int_formatted == "0" and not dec_part:
        s = f"{abs_n:.6g}".replace(".", ",")
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
        sign = 1.0
        s = s[1:]

    if not s or sum(1 for c in s if c.isdigit()) == 0:
        raise PercentCalcError(NOT_A_NUMBER, "Nilai harus berupa angka yang valid.", 400)

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
        raise PercentCalcError(NOT_A_NUMBER, "Nilai harus berupa angka yang valid.", 400)

    return val


def parse_number(value: Any, field_name: str = "angka") -> float:
    """Validasi dan parsing string angka dari pengguna ke float.

    Aturan pengenalan pemisah:
    - Ada dua jenis pemisah -> yang terakhir adalah tanda desimal, yang lain pemisah ribuan;
    - Hanya satu jenis pemisah tetapi lebih dari satu kemunculan -> semuanya pemisah ribuan ("1,2,3" = 123);
    - Hanya satu pemisah tunggal -> dibaca tanda desimal ("1.500" = 1,5 dan "1,500" = 1,5);
    """
    if value is None:
        raise PercentCalcError(INVALID_REQUEST, f"Field '{field_name}' wajib diisi.", 400)

    if not isinstance(value, str):
        raise PercentCalcError(INVALID_REQUEST, f"Field '{field_name}' harus berupa teks string.", 400)

    cleaned = value.strip()
    if not cleaned:
        raise PercentCalcError(NO_VALUE, f"Nilai '{field_name}' wajib diisi.", 400)

    if len(cleaned) > MAX_INPUT_CHARS:
        raise PercentCalcError(
            OUT_OF_RANGE,
            f"Panjang masukan ({len(cleaned)} karakter) melebihi batas {MAX_INPUT_CHARS} karakter.",
            413,
        )

    digit_count = sum(1 for c in cleaned if c.isdigit())
    if digit_count == 0:
        raise PercentCalcError(NOT_A_NUMBER, "Nilai harus berupa angka yang valid.", 400)

    if not re.fullmatch(r"[\s\d.,+\-eE]+", cleaned):
        raise PercentCalcError(NOT_A_NUMBER, "Nilai harus berupa angka yang valid.", 400)

    s = re.sub(r"\s+", "", cleaned)

    if "e" in s.lower():
        parts = re.split(r"[eE]", s)
        if len(parts) != 2:
            raise PercentCalcError(NOT_A_NUMBER, "Format angka eksponen tidak valid.", 400)
        mantissa_str, exp_str = parts[0], parts[1]
        if not re.fullmatch(r"[+\-]?\d+", exp_str):
            raise PercentCalcError(NOT_A_NUMBER, "Eksponen harus berupa bilangan bulat.", 400)
        try:
            exp_val = int(exp_str)
        except ValueError:
            raise PercentCalcError(NOT_A_NUMBER, "Eksponen tidak valid.", 400)
        mantissa_val = _parse_simple_number(mantissa_str)
        try:
            num = mantissa_val * (10.0 ** exp_val)
        except OverflowError:
            raise PercentCalcError(OUT_OF_RANGE, "Nilai melebihi batas maksimum 1.000.000.000.000.000 (1e15).", 413)
    else:
        num = _parse_simple_number(s)

    if math.isnan(num) or math.isinf(num):
        raise PercentCalcError(NOT_A_NUMBER, "Nilai bukan angka yang valid.", 400)

    if abs(num) > MAX_ABS_VALUE:
        raise PercentCalcError(
            OUT_OF_RANGE,
            "Nilai melebihi batas maksimum 1.000.000.000.000.000 (1e15).",
            413,
        )

    return num


def compute_percent(mode: Any, a: Any, b: Any) -> dict[str, Any]:
    """Hitung persentase murni di memori berdasarkan mode pilihan."""
    if mode is None or a is None or b is None:
        raise PercentCalcError(INVALID_REQUEST, "Field 'mode', 'a', dan 'b' wajib diisi.", 400)

    if not isinstance(mode, str) or not isinstance(a, str) or not isinstance(b, str):
        raise PercentCalcError(INVALID_REQUEST, "Field 'mode', 'a', dan 'b' harus berupa teks string.", 400)

    mode_norm = mode.strip()
    mode_obj = next((m for m in MODES if m["value"] == mode_norm), None)
    if not mode_obj:
        valid_modes = ", ".join(m["value"] for m in MODES)
        raise PercentCalcError(
            UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak didukung. Pilih salah satu: {valid_modes}.",
            400,
        )

    val_a = parse_number(a, mode_obj["a_label"])
    val_b = parse_number(b, mode_obj["b_label"])

    dec_a = Decimal(repr(val_a))
    dec_b = Decimal(repr(val_b))
    dec_100 = Decimal("100")

    if mode_norm == "persen_dari":
        dec_hasil = dec_a / dec_100 * dec_b
        hasil = float(dec_hasil)
        teks_a = format_angka(val_a)
        teks_b = format_angka(val_b)
        teks_hasil = format_angka(hasil)
        kalimat = f"{teks_a}% dari {teks_b} adalah {teks_hasil}."
        rumus = f"{teks_a} : 100 x {teks_b} = {teks_hasil}"

    elif mode_norm == "berapa_persen":
        if val_b == 0:
            raise PercentCalcError(
                DIVIDE_BY_ZERO,
                "Angka total tidak boleh 0 karena pembagian dengan nol tidak bisa dihitung.",
                422,
            )
        dec_hasil = dec_a / dec_b * dec_100
        hasil = float(dec_hasil)
        teks_a = format_angka(val_a)
        teks_b = format_angka(val_b)
        teks_hasil = format_angka(hasil)
        kalimat = f"{teks_a} adalah {teks_hasil}% dari {teks_b}."
        rumus = f"{teks_a} : {teks_b} x 100 = {teks_hasil}%"

    elif mode_norm == "perubahan":
        if val_a == 0:
            raise PercentCalcError(
                DIVIDE_BY_ZERO,
                "Angka awal tidak boleh 0 karena persentase perubahan dari 0 tidak bisa dihitung.",
                422,
            )
        dec_hasil = (dec_b - dec_a) / dec_a * dec_100
        hasil = float(dec_hasil)
        teks_a = format_angka(val_a)
        teks_b = format_angka(val_b)
        teks_hasil = format_angka(hasil)

        if hasil > 0:
            kalimat = f"Dari {teks_a} ke {teks_b} berarti naik {teks_hasil}%."
        elif hasil < 0:
            teks_abs = format_angka(abs(hasil))
            kalimat = f"Dari {teks_a} ke {teks_b} berarti turun {teks_abs}%."
        else:
            kalimat = f"Dari {teks_a} ke {teks_b} tidak ada perubahan (0%)."

        rumus = f"({teks_b} - {teks_a}) : {teks_a} x 100 = {teks_hasil}%"

    elif mode_norm == "tambah_persen":
        dec_hasil = dec_b * (Decimal("1") + dec_a / dec_100)
        hasil = float(dec_hasil)
        teks_a = format_angka(val_a)
        teks_b = format_angka(val_b)
        teks_hasil = format_angka(hasil)
        kalimat = f"{teks_b} ditambah {teks_a}% menjadi {teks_hasil}."
        rumus = f"{teks_b} x (1 + {teks_a} : 100) = {teks_hasil}"

    elif mode_norm == "kurang_persen":
        dec_hasil = dec_b * (Decimal("1") - dec_a / dec_100)
        hasil = float(dec_hasil)
        teks_a = format_angka(val_a)
        teks_b = format_angka(val_b)
        teks_hasil = format_angka(hasil)
        kalimat = f"{teks_b} dikurangi {teks_a}% menjadi {teks_hasil}."
        rumus = f"{teks_b} x (1 - {teks_a} : 100) = {teks_hasil}"

    else:
        raise PercentCalcError(UNSUPPORTED_MODE, f"Mode '{mode}' tidak didukung.", 400)

    return {
        "mode": mode_obj["value"],
        "mode_label": mode_obj["label"],
        "masukan": {
            "a": format_angka(val_a),
            "b": format_angka(val_b),
            "a_label": mode_obj["a_label"],
            "b_label": mode_obj["b_label"],
        },
        "hasil": {
            "nilai": hasil,
            "teks": teks_hasil,
            "satuan": mode_obj["hasil_satuan"],
        },
        "kalimat": kalimat,
        "rumus": rumus,
    }


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional dan daftar mode kalkulator persen."""
    return {
        "max_input_chars": MAX_INPUT_CHARS,
        "max_value": MAX_ABS_VALUE,
        "modes": [
            {
                "value": m["value"],
                "label": m["label"],
                "a_label": m["a_label"],
                "b_label": m["b_label"],
                "hasil_satuan": m["hasil_satuan"],
                "contoh": dict(m["contoh"]),
            }
            for m in MODES
        ],
        "processed_on": "server",
        "note": "Angka diproses di memori lalu dibuang, tidak disimpan di disk.",
    }
