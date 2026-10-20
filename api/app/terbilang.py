"""Logika penulisan angka jadi kata (terbilang): fungsi murni di memori.

Modul ini tidak bergantung pada pustaka eksternal dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai masukan pengunjung tidak dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import re
from typing import Any

# Batas keras operasional alat terbilang
MAX_CHARS = 40
MAX_DECIMALS = 6
MAX_ABS_VALUE = Decimal("1000000000000000")  # 1 kuadriliun (10^15)
MAX_BODY_BYTES = 65536  # 64 KB

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
EMPTY_INPUT = "EMPTY_INPUT"
NOT_A_NUMBER = "NOT_A_NUMBER"
TOO_MANY_DECIMALS = "TOO_MANY_DECIMALS"
OUT_OF_RANGE = "OUT_OF_RANGE"
TOO_LONG = "TOO_LONG"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
INVALID_BOOLEAN = "INVALID_BOOLEAN"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"

SATUAN = ["", "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan"]
TINGKAT = ["", "ribu", "juta", "miliar", "triliun", "kuadriliun"]
DIGIT_WORDS = {
    "0": "nol",
    "1": "satu",
    "2": "dua",
    "3": "tiga",
    "4": "empat",
    "5": "lima",
    "6": "enam",
    "7": "tujuh",
    "8": "delapan",
    "9": "sembilan",
}


class TerbilangError(ValueError):
    """Galat operasional alat terbilang dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat terstandar."""
        return {"error": {"code": self.code, "message": self.message}}


def _tiga_digit(n: int) -> str:
    """Ubah bilangan 1..999 menjadi kata Bahasa Indonesia tanpa awalan se- pada tingkat ribuan."""
    parts: list[str] = []
    ratus = n // 100
    sisa = n % 100

    if ratus == 1:
        parts.append("seratus")
    elif ratus > 1:
        parts.append(f"{SATUAN[ratus]} ratus")

    if sisa == 10:
        parts.append("sepuluh")
    elif sisa == 11:
        parts.append("sebelas")
    elif 12 <= sisa <= 19:
        parts.append(f"{SATUAN[sisa - 10]} belas")
    elif sisa >= 20:
        puluh = sisa // 10
        sat = sisa % 10
        if sat:
            parts.append(f"{SATUAN[puluh]} puluh {SATUAN[sat]}")
        else:
            parts.append(f"{SATUAN[puluh]} puluh")
    elif sisa > 0:
        parts.append(SATUAN[sisa])

    return " ".join(parts)


def _bilangan_bulat_positif(n: int) -> str:
    """Ubah bilangan bulat non-negatif menjadi kata Bahasa Indonesia.
    
    Awalan 'se' hanya dipakai untuk seratus, seribu, sebelas, sepuluh.
    Untuk jutaan ke atas tetap memakai 'satu juta', 'satu miliar', dst.
    """
    if n == 0:
        return "nol"

    chunks: list[int] = []
    temp = n
    while temp > 0:
        chunks.append(temp % 1000)
        temp //= 1000

    words: list[str] = []
    for i in range(len(chunks) - 1, -1, -1):
        c = chunks[i]
        if c == 0:
            continue
        if i == 1 and c == 1:
            words.append("seribu")
        else:
            t_words = _tiga_digit(c)
            scale = TINGKAT[i]
            if scale:
                words.append(f"{t_words} {scale}")
            else:
                words.append(t_words)

    return " ".join(words)


def angka_ke_kata(nilai: Decimal, mode: str = "biasa", kapital: bool = False) -> str:
    """Konversi nilai Decimal menjadi kata Bahasa Indonesia.
    
    Mode:
      - 'biasa': angka umum, bagian desimal dibaca angka per angka ("koma tujuh lima").
      - 'rupiah': format keuangan ("rupiah", desimal dibaca sebagai sen).
    Kapital:
      - False: huruf kecil semua.
      - True: huruf pertama kata pertama berhuruf besar.
    """
    mode_clean = (mode or "biasa").strip().lower()
    if mode_clean not in ("biasa", "rupiah"):
        raise TerbilangError(
            UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak didukung. Pilih 'biasa' atau 'rupiah'.",
            400,
        )

    is_negative = nilai < 0
    abs_val = abs(nilai)

    if abs_val > MAX_ABS_VALUE:
        raise TerbilangError(
            OUT_OF_RANGE,
            "Nilai angka melebihi batas maksimum 1 kuadriliun (1.000.000.000.000.000).",
            400,
        )

    s_full = f"{abs_val:f}"
    if "." in s_full:
        int_str, dec_str = s_full.split(".", 1)
    else:
        int_str, dec_str = s_full, ""

    int_num = int(int_str)
    int_kata = _bilangan_bulat_positif(int_num)

    if mode_clean == "rupiah":
        # Desimal pada mode rupiah dihitung sebagai sen (1 rupiah = 100 sen)
        if dec_str:
            frac_dec = Decimal(f"0.{dec_str}")
            sen_val = int((frac_dec * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        else:
            sen_val = 0

        if sen_val > 0:
            sen_kata = _bilangan_bulat_positif(sen_val)
            kata = f"{int_kata} rupiah {sen_kata} sen"
        else:
            kata = f"{int_kata} rupiah"
    else:
        # Mode biasa: bagian desimal dibaca angka per angka, nol di ekor dibuang
        dec_str_trimmed = dec_str.rstrip("0")
        if dec_str_trimmed:
            dec_words = " ".join(DIGIT_WORDS[c] for c in dec_str_trimmed)
            kata = f"{int_kata} koma {dec_words}"
        else:
            kata = int_kata

    if is_negative:
        kata = f"minus {kata}"

    if kapital and kata:
        kata = kata[0].upper() + kata[1:]

    return kata


def parse_input(raw_angka: Any) -> tuple[Decimal, str]:
    """Validasi dan normalisasi masukan angka dari pengunjung."""
    if raw_angka is None:
        raise TerbilangError(INVALID_REQUEST, "Field 'angka' wajib disertakan.", 400)

    if isinstance(raw_angka, bool):
        raise TerbilangError(
            NOT_A_NUMBER,
            "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
            400,
        )

    if isinstance(raw_angka, (int, float, Decimal)):
        raw_str = str(raw_angka)
    elif isinstance(raw_angka, str):
        raw_str = raw_angka
    else:
        raise TerbilangError(
            NOT_A_NUMBER,
            "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
            400,
        )

    if not raw_str.strip():
        raise TerbilangError(
            EMPTY_INPUT,
            "Masukan angka masih kosong. Masukkan angka yang ingin diubah.",
            400,
        )

    if len(raw_str) > MAX_CHARS:
        raise TerbilangError(
            TOO_LONG,
            "Panjang masukan melebihi batas maksimum 40 karakter.",
            400,
        )

    s = raw_str.strip()

    # Hanya digit, pemisah titik/koma, minus, dan spasi
    if not re.fullmatch(r"[\s\d.,\-]+", s):
        raise TerbilangError(
            NOT_A_NUMBER,
            "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
            400,
        )

    sign = 1
    if s.startswith("-"):
        sign = -1
        s = s[1:].strip()

    if "-" in s:
        raise TerbilangError(
            NOT_A_NUMBER,
            "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
            400,
        )

    s = re.sub(r"\s+", "", s)
    if not s or not any(c.isdigit() for c in s):
        raise TerbilangError(
            NOT_A_NUMBER,
            "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
            400,
        )

    if any(p in s for p in ["..", ",,", ".,", ",."]):
        raise TerbilangError(
            NOT_A_NUMBER,
            "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
            400,
        )

    if s.endswith(".") or s.endswith(","):
        raise TerbilangError(
            NOT_A_NUMBER,
            "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
            400,
        )

    if s.startswith(".") or s.startswith(","):
        s = "0" + s

    has_dot = "." in s
    has_comma = "," in s

    if has_dot and has_comma:
        last_dot = s.rfind(".")
        last_comma = s.rfind(",")
        if last_comma > last_dot:
            int_part_raw = s[:last_comma]
            dec_part = s[last_comma + 1:]
            dot_parts = int_part_raw.split(".")
            if any(len(p) != 3 for p in dot_parts[1:]):
                raise TerbilangError(
                    NOT_A_NUMBER,
                    "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
                    400,
                )
            int_part = "".join(dot_parts)
        else:
            int_part_raw = s[:last_dot]
            dec_part = s[last_dot + 1:]
            comma_parts = int_part_raw.split(",")
            if any(len(p) != 3 for p in comma_parts[1:]):
                raise TerbilangError(
                    NOT_A_NUMBER,
                    "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
                    400,
                )
            int_part = "".join(comma_parts)

        if "." in dec_part or "," in dec_part or not dec_part.isdigit() or not int_part.isdigit():
            raise TerbilangError(
                NOT_A_NUMBER,
                "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
                400,
            )
        s_norm = f"{int_part}.{dec_part}"
    elif has_comma:
        if s.count(",") > 1:
            comma_parts = s.split(",")
            if any(len(p) != 3 for p in comma_parts[1:]):
                raise TerbilangError(
                    NOT_A_NUMBER,
                    "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
                    400,
                )
            int_part = "".join(comma_parts)
            dec_part = ""
            s_norm = int_part
        else:
            int_part, dec_part = s.split(",")
            if not int_part.isdigit() or not dec_part.isdigit():
                raise TerbilangError(
                    NOT_A_NUMBER,
                    "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
                    400,
                )
            s_norm = f"{int_part}.{dec_part}"
    elif has_dot:
        if s.count(".") > 1:
            dot_parts = s.split(".")
            if any(len(p) != 3 for p in dot_parts[1:]):
                raise TerbilangError(
                    NOT_A_NUMBER,
                    "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
                    400,
                )
            int_part = "".join(dot_parts)
            dec_part = ""
            s_norm = int_part
        else:
            int_part, dec_part = s.split(".")
            if not int_part.isdigit() or not dec_part.isdigit():
                raise TerbilangError(
                    NOT_A_NUMBER,
                    "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
                    400,
                )
            if len(dec_part) == 3:
                # Satu titik diikuti tepat 3 digit dianggap pemisah ribuan, bukan desimal
                int_part = int_part + dec_part
                dec_part = ""
                s_norm = int_part
            else:
                s_norm = f"{int_part}.{dec_part}"
    else:
        if not s.isdigit():
            raise TerbilangError(
                NOT_A_NUMBER,
                "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
                400,
            )
        int_part = s
        dec_part = ""
        s_norm = int_part

    if dec_part and len(dec_part) > MAX_DECIMALS:
        raise TerbilangError(
            TOO_MANY_DECIMALS,
            "Jumlah digit desimal melebihi batas maksimum 6 digit.",
            400,
        )

    try:
        val = Decimal(s_norm) * sign
    except Exception:
        raise TerbilangError(
            NOT_A_NUMBER,
            "Masukan harus berupa angka yang valid. Contoh: 1250000, 1.250.000, atau 12,75.",
            400,
        )

    if abs(val) > MAX_ABS_VALUE:
        raise TerbilangError(
            OUT_OF_RANGE,
            "Nilai angka melebihi batas maksimum 1 kuadriliun (1.000.000.000.000.000).",
            400,
        )

    normalized_str = f"{val:f}"
    return val, normalized_str


def parse_boolean(val: Any) -> bool:
    """Validasi dan parsing nilai boolean untuk parameter 'kapital'."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        if val in (0, 1):
            return bool(val)
        raise TerbilangError(INVALID_BOOLEAN, "Field 'kapital' harus bernilai boolean (true atau false).", 400)
    if isinstance(val, str):
        v = val.strip().lower()
        if v in ("true", "1", "ya"):
            return True
        if v in ("false", "0", "tidak", ""):
            return False
        raise TerbilangError(INVALID_BOOLEAN, "Field 'kapital' harus bernilai boolean (true atau false).", 400)
    raise TerbilangError(INVALID_BOOLEAN, "Field 'kapital' harus bernilai boolean (true atau false).", 400)


def hitung_terbilang(angka: Any, mode: str = "biasa", kapital: Any = False) -> dict[str, Any]:
    """Hitung kata terbilang dari angka yang diberikan."""
    val, normalized_str = parse_input(angka)
    mode_clean = (mode or "biasa").strip().lower()
    if mode_clean not in ("biasa", "rupiah"):
        raise TerbilangError(
            UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak didukung. Pilih 'biasa' atau 'rupiah'.",
            400,
        )
    kapital_bool = parse_boolean(kapital)

    hasil_kata = angka_ke_kata(val, mode=mode_clean, kapital=kapital_bool)
    words = hasil_kata.split() if hasil_kata else []

    return {
        "angka": normalized_str,
        "kata": hasil_kata,
        "mode": mode_clean,
        "jumlah_kata": len(words),
        "jumlah_karakter": len(hasil_kata),
        "kapital": kapital_bool,
    }


def limits_payload() -> dict[str, Any]:
    """Konfigurasi batas operasional dan contoh masukan untuk alat terbilang."""
    return {
        "max_chars": MAX_CHARS,
        "max_digits": 16,
        "max_value": int(MAX_ABS_VALUE),
        "max_decimals": MAX_DECIMALS,
        "max_body_bytes": MAX_BODY_BYTES,
        "maks_digit": 16,
        "maks_nilai": int(MAX_ABS_VALUE),
        "maks_desimal": MAX_DECIMALS,
        "modes": [
            {"value": "biasa", "label": "Angka biasa"},
            {"value": "rupiah", "label": "Uang rupiah"},
        ],
        "mode_didukung": ["biasa", "rupiah"],
        "default_mode": "biasa",
        "default_kapital": False,
        "contoh_masukan": ["0", "1250000", "1.250.500,50", "12,75", "-2500"],
        "examples": ["0", "1250000", "1.250.500,50", "12,75", "-2500"],
        "processed_on": "server",
        "note": "Angka diproses di memori lalu dibuang, tidak disimpan di disk.",
    }
