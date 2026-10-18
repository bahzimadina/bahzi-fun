"""Logika kalkulator zakat (Zakat Calculator): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import math
import re
from typing import Any

# Batas operasional dan ketentuan dasar zakat
NISAB_EMAS_GRAM = 85
PERSEN_ZAKAT = Decimal("2.5")
BERAS_KG_PER_JIWA = Decimal("2.5")
MAX_ABS_VALUE = 1e15
MAX_BODY_BYTES = 8192

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
MISSING_FIELD = "MISSING_FIELD"
NOT_A_NUMBER = "NOT_A_NUMBER"
NEGATIVE_VALUE = "NEGATIVE_VALUE"
OUT_OF_RANGE = "OUT_OF_RANGE"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"

CATATAN_TEKS = (
    "Perkiraan bantu hitung, bukan fatwa. "
    "Nisab memakai harga yang kamu masukkan sendiri. "
    "Aturan zakat bisa berbeda antar lembaga amil, jadi tanyakan ke amil atau ustadz setempat."
)


class ZakatError(ValueError):
    """Galat operasional kalkulator zakat dengan kode galat dan status HTTP."""

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
        "value": "penghasilan",
        "label": "Zakat penghasilan (tiap bulan)",
        "field": ["penghasilan", "bonus", "emas"],
        "fields": ["penghasilan", "bonus", "emas"],
    },
    {
        "value": "mal",
        "label": "Zakat harta simpanan",
        "field": ["harta", "utang", "emas", "haul"],
        "fields": ["harta", "utang", "emas", "haul"],
    },
    {
        "value": "fitrah",
        "label": "Zakat fitrah",
        "field": ["jiwa", "harga_beras"],
        "fields": ["jiwa", "harga_beras"],
    },
]


def format_rupiah(val: int | Decimal) -> str:
    """Format angka integer ke teks mata uang Rupiah standar Indonesia."""
    n = int(Decimal(str(val)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    formatted = f"{n:,}".replace(",", ".")
    return f"Rp {formatted}"


def parse_decimal(
    value: Any,
    field_name: str,
    required: bool = True,
    default: Decimal | None = None,
) -> Decimal:
    """Validasi dan parsing angka dari pengguna ke Decimal.

    Menerima integer, float, Decimal, dan string dengan pemisah desimal koma atau titik.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ZakatError(MISSING_FIELD, f"Field '{field_name}' wajib diisi.", 400)
        return default if default is not None else Decimal("0")

    if isinstance(value, bool):
        raise ZakatError(NOT_A_NUMBER, f"Field '{field_name}' harus berupa angka yang valid.", 400)

    if isinstance(value, (int, float, Decimal)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise ZakatError(NOT_A_NUMBER, f"Field '{field_name}' harus berupa angka yang valid.", 400)
        d = Decimal(str(value))
    elif isinstance(value, str):
        cleaned = value.strip()
        if len(cleaned) > 50:
            raise ZakatError(
                OUT_OF_RANGE,
                f"Nilai '{field_name}' melebihi batas panjang karakter.",
                413,
            )

        if not re.fullmatch(r"[\s\d.,+\-]+", cleaned):
            raise ZakatError(NOT_A_NUMBER, f"Field '{field_name}' harus berupa angka yang valid.", 400)

        s = re.sub(r"\s+", "", cleaned)
        sign = 1
        if s.startswith("-"):
            sign = -1
            s = s[1:]
        elif s.startswith("+"):
            s = s[1:]

        if not s or not any(c.isdigit() for c in s):
            raise ZakatError(NOT_A_NUMBER, f"Field '{field_name}' harus berupa angka yang valid.", 400)

        has_dot = "." in s
        has_comma = "," in s

        if has_dot and has_comma:
            last_dot = s.rfind(".")
            last_comma = s.rfind(",")
            if last_comma > last_dot:
                int_part = s[:last_comma].replace(".", "")
                dec_part = s[last_comma + 1 :]
            else:
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
            d = Decimal(s_norm) * sign
        except Exception:
            raise ZakatError(NOT_A_NUMBER, f"Field '{field_name}' harus berupa angka yang valid.", 400)
    else:
        raise ZakatError(NOT_A_NUMBER, f"Field '{field_name}' harus berupa angka yang valid.", 400)

    if d < 0:
        raise ZakatError(NEGATIVE_VALUE, f"Field '{field_name}' tidak boleh bernilai negatif.", 400)

    if d > Decimal(str(MAX_ABS_VALUE)):
        raise ZakatError(
            OUT_OF_RANGE,
            f"Field '{field_name}' melebihi batas maksimum 1.000.000.000.000.000 (1e15).",
            413,
        )

    return d


def compute_zakat(data: Any) -> dict[str, Any]:
    """Hitung zakat murni di memori berdasarkan mode pilihan."""
    if not isinstance(data, dict):
        raise ZakatError(INVALID_REQUEST, "Permintaan harus berupa objek JSON.", 400)

    raw_mode = data.get("mode")
    if raw_mode is None or (isinstance(raw_mode, str) and not raw_mode.strip()):
        raise ZakatError(MISSING_FIELD, "Field 'mode' wajib diisi.", 400)

    if not isinstance(raw_mode, str):
        raise ZakatError(UNSUPPORTED_MODE, "Mode perhitungan tidak didukung.", 400)

    mode = raw_mode.strip()
    if mode not in ("penghasilan", "mal", "fitrah"):
        raise ZakatError(
            UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak didukung. Pilih 'penghasilan', 'mal', atau 'fitrah'.",
            400,
        )

    if mode == "penghasilan":
        penghasilan = parse_decimal(data.get("penghasilan"), "penghasilan", required=True)
        bonus = parse_decimal(data.get("bonus"), "bonus", required=False, default=Decimal("0"))
        emas = parse_decimal(data.get("emas"), "emas", required=True)

        if emas <= 0:
            raise ZakatError(OUT_OF_RANGE, "Harga emas harus lebih besar dari 0.", 400)

        total = penghasilan + bonus
        nisab_bulanan = (Decimal(NISAB_EMAS_GRAM) * emas) / Decimal(12)
        wajib = total >= nisab_bulanan

        if wajib:
            zakat = int(((total * PERSEN_ZAKAT) / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        else:
            zakat = 0

        nisab_int = int(nisab_bulanan.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        ringkasan: list[dict[str, str]] = [
            {"label": "Penghasilan bruto per bulan", "nilai": format_rupiah(penghasilan)},
        ]
        if bonus > 0:
            ringkasan.append({"label": "Bonus atau pendapatan lain", "nilai": format_rupiah(bonus)})
            ringkasan.append({"label": "Total penghasilan per bulan", "nilai": format_rupiah(total)})
        ringkasan.extend([
            {"label": "Nisab per bulan (85 g emas / 12)", "nilai": format_rupiah(nisab_int)},
            {"label": "Status", "nilai": "Sudah mencapai nisab" if wajib else "Belum mencapai nisab"},
        ])

        return {
            "mode": "penghasilan",
            "wajib": wajib,
            "zakat": zakat,
            "nisab": nisab_int,
            "satuan": "Rp",
            "ringkasan": ringkasan,
            "catatan": CATATAN_TEKS,
        }

    elif mode == "mal":
        harta = parse_decimal(data.get("harta"), "harta", required=True)
        utang = parse_decimal(data.get("utang"), "utang", required=False, default=Decimal("0"))
        emas = parse_decimal(data.get("emas"), "emas", required=True)

        if emas <= 0:
            raise ZakatError(OUT_OF_RANGE, "Harga emas harus lebih besar dari 0.", 400)

        if "haul" not in data or data["haul"] is None:
            raise ZakatError(MISSING_FIELD, "Field 'haul' wajib diisi.", 400)

        raw_haul = data["haul"]
        if isinstance(raw_haul, bool):
            haul = raw_haul
        elif isinstance(raw_haul, (int, float)) and raw_haul in (0, 1):
            haul = bool(raw_haul)
        elif isinstance(raw_haul, str):
            h_clean = raw_haul.strip().lower()
            if h_clean in ("true", "1", "ya"):
                haul = True
            elif h_clean in ("false", "0", "tidak"):
                haul = False
            else:
                raise ZakatError(INVALID_REQUEST, "Field 'haul' harus bernilai boolean (true atau false).", 400)
        else:
            raise ZakatError(INVALID_REQUEST, "Field 'haul' harus bernilai boolean (true atau false).", 400)

        bersih = max(harta - utang, Decimal("0"))
        nisab = Decimal(NISAB_EMAS_GRAM) * emas
        nisab_int = int(nisab.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        wajib = haul and (bersih >= nisab)

        if wajib:
            zakat = int(((bersih * PERSEN_ZAKAT) / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        else:
            zakat = 0

        ringkasan = [
            {"label": "Total harta simpanan", "nilai": format_rupiah(harta)},
        ]
        if utang > 0:
            ringkasan.append({"label": "Utang jatuh tempo", "nilai": format_rupiah(utang)})
        ringkasan.extend([
            {"label": "Harta bersih", "nilai": format_rupiah(bersih)},
            {"label": "Nisab (85 g emas)", "nilai": format_rupiah(nisab_int)},
            {"label": "Kepemilikan satu tahun (haul)", "nilai": "Sudah genap 1 tahun" if haul else "Belum genap 1 tahun"},
            {
                "label": "Status",
                "nilai": (
                    "Sudah mencapai nisab dan haul"
                    if wajib
                    else ("Belum mencapai haul (1 tahun)" if (bersih >= nisab and not haul) else "Belum mencapai nisab")
                ),
            },
        ])

        return {
            "mode": "mal",
            "wajib": wajib,
            "zakat": zakat,
            "nisab": nisab_int,
            "satuan": "Rp",
            "ringkasan": ringkasan,
            "catatan": CATATAN_TEKS,
        }

    else:  # mode == "fitrah"
        if "jiwa" not in data or data["jiwa"] is None or (isinstance(data["jiwa"], str) and not data["jiwa"].strip()):
            raise ZakatError(MISSING_FIELD, "Field 'jiwa' wajib diisi.", 400)

        val_jiwa = data["jiwa"]
        if isinstance(val_jiwa, bool):
            raise ZakatError(NOT_A_NUMBER, "Field 'jiwa' harus berupa angka yang valid.", 400)

        d_jiwa = parse_decimal(val_jiwa, "jiwa", required=True)
        if d_jiwa != int(d_jiwa):
            raise ZakatError(OUT_OF_RANGE, "Jumlah jiwa harus berupa bilangan bulat.", 400)

        jiwa_int = int(d_jiwa)
        if jiwa_int < 1 or jiwa_int > 50:
            raise ZakatError(OUT_OF_RANGE, "Jumlah jiwa harus berada dalam rentang 1 sampai 50.", 400)

        harga_beras = parse_decimal(data.get("harga_beras"), "harga_beras", required=True)
        if harga_beras <= 0:
            raise ZakatError(OUT_OF_RANGE, "Harga beras harus lebih besar dari 0.", 400)

        beras_kg = BERAS_KG_PER_JIWA * Decimal(jiwa_int)
        uang = beras_kg * harga_beras
        uang_int = int(uang.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        wajib = True
        zakat = uang_int

        beras_kg_val = int(beras_kg) if beras_kg == int(beras_kg) else float(beras_kg)
        beras_kg_str = str(beras_kg_val).replace(".", ",")

        ringkasan = [
            {"label": "Jumlah jiwa", "nilai": f"{jiwa_int} orang"},
            {"label": "Kebutuhan beras (2,5 kg per jiwa)", "nilai": f"{beras_kg_str} kg"},
            {"label": "Harga beras per kg", "nilai": format_rupiah(harga_beras)},
            {"label": "Total beras zakat fitrah", "nilai": f"{beras_kg_str} kg beras"},
            {"label": "Total zakat fitrah (uang)", "nilai": format_rupiah(uang_int)},
            {"label": "Status", "nilai": "Wajib ditunaikan sebelum salat Idulfitri"},
        ]

        return {
            "mode": "fitrah",
            "wajib": wajib,
            "zakat": zakat,
            "uang": uang_int,
            "beras_kg": beras_kg_val,
            "nisab": 0,
            "satuan": "Rp",
            "ringkasan": ringkasan,
            "catatan": CATATAN_TEKS,
        }


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional dan daftar mode kalkulator zakat."""
    return {
        "modes": [
            {
                "value": m["value"],
                "label": m["label"],
                "field": list(m["field"]),
                "fields": list(m["fields"]),
            }
            for m in MODES
        ],
        "nisab_emas_gram": NISAB_EMAS_GRAM,
        "persen_zakat": float(PERSEN_ZAKAT),
        "beras_kg_per_jiwa": float(BERAS_KG_PER_JIWA),
        "max_abs_value": MAX_ABS_VALUE,
        "max_body_bytes": MAX_BODY_BYTES,
        "processed_on": "server",
        "note": "Angka diproses di memori lalu dibuang, tidak disimpan di disk.",
    }
