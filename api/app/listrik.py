"""Logika kalkulator listrik (Electric Calculator): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import math
import re
from typing import Any

# Batas operasional
MAX_INPUT_CHARS = 24
MAX_VALUE = 1e12
MAX_ITEMS = 50

# Catatan jujur yang disertakan di hasil
CATATAN_JUJUR = (
    "Hasil ini merupakan perhitungan matematis ideal. Tagihan listrik sebenarnya bisa berbeda "
    "karena adanya biaya beban (abonemen), Pajak Penerangan Jalan (PPJ), dan penyesuaian tarif berkala. "
    "Tarif per kWh harus disesuaikan dengan golongan tarif listrik masing-masing (nilai awal yang "
    "disediakan hanya sebagai contoh)."
)

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NILAI_KURANG = "NILAI_KURANG"
TERLALU_BANYAK_NILAI = "TERLALU_BANYAK_NILAI"
DIVIDE_BY_ZERO = "DIVIDE_BY_ZERO"
OUT_OF_RANGE = "OUT_OF_RANGE"
NOT_A_NUMBER = "NOT_A_NUMBER"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
LIST_KOSONG = "LIST_KOSONG"
TOO_MANY_ITEMS = "TOO_MANY_ITEMS"
UNSUPPORTED_JENIS = "UNSUPPORTED_JENIS"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class ListrikError(ValueError):
    """Galat operasional kalkulator listrik dengan kode galat dan status HTTP."""

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
        "value": "ohm",
        "label": "Hukum Ohm (V / I / R)",
        "desc": "Hitung tegangan (V), arus (I), hambatan (R), dan daya (P). Isi dua nilai, kosongkan satu.",
        "contoh": {"tegangan": "220", "arus": "5", "hambatan": ""},
    },
    {
        "value": "daya",
        "label": "Perkiraan pemakaian dan biaya",
        "desc": "Hitung konsumsi kWh dan perkiraan biaya listrik per hari, bulan, dan tahun.",
        "contoh": {
            "daya_alat": "350",
            "jam_per_hari": "8",
            "jumlah_alat": "2",
            "hari": "30",
            "tarif": "1444.7",
        },
    },
    {
        "value": "hambatan",
        "label": "Hambatan total rangkaian (seri / paralel)",
        "desc": "Hitung hambatan pengganti dari beberapa resistor yang dirangkai seri atau paralel.",
        "contoh": {
            "jenis": "seri",
            "daftar": "100\n220\n470",
        },
    },
]


def format_angka(n: float | int) -> str:
    """Format angka sesuai aturan standar Indonesia.

    - n == 0 -> "0"
    - abs(n) >= 1e15 atau abs(n) < 1e-6 -> notasi eksponen gaya Indonesia.
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


def format_rupiah(n: float | int) -> str:
    """Format angka menjadi teks rupiah Indonesia dengan simbol Rp."""
    return f"Rp {format_angka(n)}"


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
        raise ListrikError(NOT_A_NUMBER, "Nilai harus berupa angka yang valid.", 400)

    has_dot = "." in s
    has_comma = "," in s

    if has_dot and has_comma:
        last_dot = s.rfind(".")
        last_comma = s.rfind(",")
        if last_comma > last_dot:
            # Titik pemisah ribuan, koma pemisah desimal (mis. 1.444,7)
            int_part = s[:last_comma].replace(".", "")
            dec_part = s[last_comma + 1 :]
        else:
            # Koma pemisah ribuan, titik pemisah desimal (mis. 1,444.7)
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
        raise ListrikError(NOT_A_NUMBER, "Nilai harus berupa angka yang valid.", 400)

    return val


def parse_number(value: Any, field_name: str = "angka") -> float:
    """Validasi dan parsing teks angka dari pengguna ke float."""
    if value is None:
        raise ListrikError(INVALID_REQUEST, f"Field '{field_name}' wajib diisi.", 400)

    if not isinstance(value, str):
        raise ListrikError(INVALID_REQUEST, f"Field '{field_name}' harus berupa teks string.", 400)

    cleaned = value.strip()
    if not cleaned:
        raise ListrikError(INVALID_REQUEST, f"Field '{field_name}' wajib diisi.", 400)

    if len(cleaned) > MAX_INPUT_CHARS:
        raise ListrikError(
            OUT_OF_RANGE,
            f"Panjang masukan '{field_name}' ({len(cleaned)} karakter) melebihi batas {MAX_INPUT_CHARS} karakter.",
            400,
        )

    digit_count = sum(1 for c in cleaned if c.isdigit())
    if digit_count == 0:
        raise ListrikError(NOT_A_NUMBER, f"Nilai '{field_name}' harus berupa angka yang valid.", 400)

    if not re.fullmatch(r"[\s\d.,+\-eE]+", cleaned):
        raise ListrikError(NOT_A_NUMBER, f"Nilai '{field_name}' harus berupa angka yang valid.", 400)

    s = re.sub(r"\s+", "", cleaned)

    if "e" in s.lower():
        parts = re.split(r"[eE]", s)
        if len(parts) != 2:
            raise ListrikError(NOT_A_NUMBER, f"Format angka eksponen '{field_name}' tidak valid.", 400)
        mantissa_str, exp_str = parts[0], parts[1]
        if not re.fullmatch(r"[+\-]?\d+", exp_str):
            raise ListrikError(NOT_A_NUMBER, "Eksponen harus berupa bilangan bulat.", 400)
        try:
            exp_val = int(exp_str)
        except ValueError:
            raise ListrikError(NOT_A_NUMBER, "Eksponen tidak valid.", 400)
        mantissa_val = _parse_simple_number(mantissa_str)
        try:
            num = mantissa_val * (10.0 ** exp_val)
        except OverflowError:
            raise ListrikError(OUT_OF_RANGE, f"Nilai '{field_name}' melebihi batas maksimum.", 400)
    else:
        num = _parse_simple_number(s)

    if math.isnan(num) or math.isinf(num):
        raise ListrikError(NOT_A_NUMBER, f"Nilai '{field_name}' bukan angka yang valid.", 400)

    return num


def hitung_ohm(tegangan_raw: Any, arus_raw: Any, hambatan_raw: Any) -> dict[str, Any]:
    """Hitung hukum Ohm (V = I x R) dan daya (P = V x I).

    Pengunjung mengisi tepat dua dari tiga nilai; nilai yang kosong dihitung.
    """
    inputs = {
        "tegangan": tegangan_raw,
        "arus": arus_raw,
        "hambatan": hambatan_raw,
    }

    # Tentukan field mana yang terisi
    filled: dict[str, str] = {}
    for name, raw_val in inputs.items():
        if raw_val is not None and isinstance(raw_val, str) and raw_val.strip() != "":
            filled[name] = raw_val.strip()

    if len(filled) < 2:
        raise ListrikError(
            NILAI_KURANG,
            "Isi dua nilai dari tiga yang tersedia, biarkan satu kosong.",
            400,
        )
    if len(filled) > 2:
        raise ListrikError(
            TERLALU_BANYAK_NILAI,
            "Isi tepat dua nilai, kosongkan satu supaya dihitung.",
            400,
        )

    # Parsing dua nilai yang terisi
    parsed: dict[str, float] = {}
    for name, str_val in filled.items():
        val = parse_number(str_val, name)
        # Hambatan 0 atau arus 0 memicu DIVIDE_BY_ZERO
        if name in ("hambatan", "arus") and val == 0:
            raise ListrikError(
                DIVIDE_BY_ZERO,
                f"Nilai {name} tidak boleh 0 karena pembagian dengan nol tidak bisa dihitung.",
                400,
            )
        if name == "tegangan" and val == 0:
            raise ListrikError(
                OUT_OF_RANGE,
                "Nilai tegangan harus lebih besar dari 0 dan maksimal 1.000.000.000.000.",
                400,
            )
        if val < 0 or val > MAX_VALUE:
            raise ListrikError(
                OUT_OF_RANGE,
                f"Nilai {name} harus lebih besar dari 0 dan maksimal 1.000.000.000.000.",
                400,
            )
        parsed[name] = val

    # Hitung variabel yang kosong
    v_val: float
    i_val: float
    r_val: float
    dihitung: str
    dihitung_label: str
    dihitung_satuan: str
    langkah: list[str] = []

    if "tegangan" not in parsed:
        dihitung = "tegangan"
        dihitung_label = "Tegangan"
        dihitung_satuan = "V"
        i_val = parsed["arus"]
        r_val = parsed["hambatan"]
        try:
            v_val = i_val * r_val
        except OverflowError:
            raise ListrikError(OUT_OF_RANGE, "Hasil perhitungan tegangan melebihi batas.", 400)
        langkah.append(
            f"V = I x R = {format_angka(i_val)} x {format_angka(r_val)} = {format_angka(v_val)} V"
        )
    elif "arus" not in parsed:
        dihitung = "arus"
        dihitung_label = "Arus"
        dihitung_satuan = "A"
        v_val = parsed["tegangan"]
        r_val = parsed["hambatan"]
        if r_val == 0:
            raise ListrikError(DIVIDE_BY_ZERO, "Hambatan tidak boleh 0.", 400)
        try:
            i_val = v_val / r_val
        except OverflowError:
            raise ListrikError(OUT_OF_RANGE, "Hasil perhitungan arus melebihi batas.", 400)
        langkah.append(
            f"I = V / R = {format_angka(v_val)} / {format_angka(r_val)} = {format_angka(i_val)} A"
        )
    else:
        dihitung = "hambatan"
        dihitung_label = "Hambatan"
        dihitung_satuan = "Ω"
        v_val = parsed["tegangan"]
        i_val = parsed["arus"]
        if i_val == 0:
            raise ListrikError(DIVIDE_BY_ZERO, "Arus tidak boleh 0.", 400)
        try:
            r_val = v_val / i_val
        except OverflowError:
            raise ListrikError(OUT_OF_RANGE, "Hasil perhitungan hambatan melebihi batas.", 400)
        langkah.append(
            f"R = V / I = {format_angka(v_val)} / {format_angka(i_val)} = {format_angka(r_val)} Ω"
        )

    # Hitung daya listrik P = V x I
    try:
        p_val = v_val * i_val
    except OverflowError:
        raise ListrikError(OUT_OF_RANGE, "Hasil perhitungan daya melebihi batas.", 400)

    langkah.append(
        f"P = V x I = {format_angka(v_val)} x {format_angka(i_val)} = {format_angka(p_val)} W"
    )

    nilai_hitung = {
        "tegangan": v_val,
        "arus": i_val,
        "hambatan": r_val,
    }[dihitung]

    return {
        "mode": "ohm",
        "mode_label": "Hukum Ohm (V / I / R)",
        "dihitung": dihitung,
        "dihitung_label": dihitung_label,
        "hasil": {
            "variabel": dihitung,
            "label": dihitung_label,
            "nilai": nilai_hitung,
            "teks": format_angka(nilai_hitung),
            "satuan": dihitung_satuan,
        },
        "daya": {
            "variabel": "daya",
            "label": "Daya listrik",
            "nilai": p_val,
            "teks": format_angka(p_val),
            "satuan": "W",
        },
        "rincian": {
            "tegangan": {"nilai": v_val, "teks": format_angka(v_val), "satuan": "V"},
            "arus": {"nilai": i_val, "teks": format_angka(i_val), "satuan": "A"},
            "hambatan": {"nilai": r_val, "teks": format_angka(r_val), "satuan": "Ω"},
            "daya": {"nilai": p_val, "teks": format_angka(p_val), "satuan": "W"},
        },
        "langkah": langkah,
        "catatan_jujur": CATATAN_JUJUR,
    }


def hitung_daya(
    daya_alat_raw: Any,
    jam_per_hari_raw: Any,
    jumlah_alat_raw: Any,
    hari_raw: Any,
    tarif_raw: Any,
) -> dict[str, Any]:
    """Hitung perkiraan konsumsi energi (kWh) dan biaya listrik."""
    daya_alat = parse_number(daya_alat_raw, "daya_alat")
    jam_per_hari = parse_number(jam_per_hari_raw, "jam_per_hari")
    jumlah_alat_num = parse_number(jumlah_alat_raw, "jumlah_alat")
    hari_num = parse_number(hari_raw, "hari")
    tarif = parse_number(tarif_raw, "tarif")

    if daya_alat < 0.1 or daya_alat > 100000:
        raise ListrikError(
            OUT_OF_RANGE,
            "Daya alat harus antara 0,1 hingga 100.000 Watt.",
            400,
        )

    if jam_per_hari < 0.1 or jam_per_hari > 24:
        raise ListrikError(
            OUT_OF_RANGE,
            "Jam pemakaian per hari harus antara 0,1 hingga 24 jam.",
            400,
        )

    if not jumlah_alat_num.is_integer() or not (1 <= int(jumlah_alat_num) <= 1000):
        raise ListrikError(
            OUT_OF_RANGE,
            "Jumlah alat harus berupa bilangan bulat antara 1 hingga 1.000.",
            400,
        )
    jumlah_alat = int(jumlah_alat_num)

    if not hari_num.is_integer() or not (1 <= int(hari_num) <= 366):
        raise ListrikError(
            OUT_OF_RANGE,
            "Jumlah hari harus berupa bilangan bulat antara 1 hingga 366 hari.",
            400,
        )
    hari = int(hari_num)

    if tarif < 0 or tarif > 100000:
        raise ListrikError(
            OUT_OF_RANGE,
            "Tarif listrik harus antara 0 hingga 100.000 Rp/kWh.",
            400,
        )

    # Rumus utama:
    # kwh = daya_alat x jam_per_hari x jumlah_alat x hari / 1000
    kwh_per_hari = (daya_alat * jam_per_hari * jumlah_alat) / 1000.0
    kwh = kwh_per_hari * hari
    biaya = kwh * tarif

    # Turunan:
    biaya_per_hari = kwh_per_hari * tarif
    biaya_per_bulan = kwh_per_hari * 30.0 * tarif
    biaya_per_tahun = kwh_per_hari * 365.0 * tarif

    langkah = [
        f"Konsumsi energi per hari = {format_angka(daya_alat)} W x {format_angka(jam_per_hari)} jam x {jumlah_alat} alat / 1.000 = {format_angka(kwh_per_hari)} kWh/hari",
        f"Total energi ({hari} hari) = {format_angka(kwh_per_hari)} kWh x {hari} hari = {format_angka(kwh)} kWh",
        f"Total perkiraan biaya = {format_angka(kwh)} kWh x {format_rupiah(tarif)}/kWh = {format_rupiah(biaya)}",
        f"Perkiraan per hari: {format_rupiah(biaya_per_hari)} | per bulan (30 hari): {format_rupiah(biaya_per_bulan)} | per tahun (365 hari): {format_rupiah(biaya_per_tahun)}",
    ]

    return {
        "mode": "daya",
        "mode_label": "Perkiraan pemakaian dan biaya",
        "hasil": {
            "kwh": {
                "nilai": kwh,
                "teks": format_angka(kwh),
                "satuan": "kWh",
            },
            "biaya": {
                "nilai": biaya,
                "teks": format_rupiah(biaya),
                "satuan": "Rp",
            },
        },
        "turunan": {
            "kwh_per_hari": {
                "nilai": kwh_per_hari,
                "teks": format_angka(kwh_per_hari),
                "satuan": "kWh",
            },
            "biaya_per_hari": {
                "nilai": biaya_per_hari,
                "teks": format_rupiah(biaya_per_hari),
                "satuan": "Rp",
            },
            "biaya_per_bulan": {
                "nilai": biaya_per_bulan,
                "teks": format_rupiah(biaya_per_bulan),
                "satuan": "Rp",
            },
            "biaya_per_tahun": {
                "nilai": biaya_per_tahun,
                "teks": format_rupiah(biaya_per_tahun),
                "satuan": "Rp",
            },
        },
        "masukan": {
            "daya_alat": format_angka(daya_alat),
            "jam_per_hari": format_angka(jam_per_hari),
            "jumlah_alat": str(jumlah_alat),
            "hari": str(hari),
            "tarif": format_angka(tarif),
        },
        "langkah": langkah,
        "catatan_jujur": CATATAN_JUJUR,
    }


def hitung_hambatan(daftar_raw: Any, jenis_raw: Any) -> dict[str, Any]:
    """Hitung hambatan total rangkaian (seri atau paralel)."""
    if daftar_raw is None or not isinstance(daftar_raw, str):
        raise ListrikError(LIST_KOSONG, "Daftar nilai hambatan tidak boleh kosong.", 400)

    if jenis_raw is None or not isinstance(jenis_raw, str) or not jenis_raw.strip():
        raise ListrikError(
            UNSUPPORTED_JENIS,
            "Pilih jenis rangkaian: 'seri' atau 'paralel'.",
            400,
        )

    jenis = jenis_raw.strip().lower()
    if jenis not in ("seri", "paralel"):
        raise ListrikError(
            UNSUPPORTED_JENIS,
            f"Jenis rangkaian '{jenis_raw}' tidak didukung. Pilih 'seri' atau 'paralel'.",
            400,
        )

    raw_lines = [line.strip() for line in daftar_raw.splitlines() if line.strip()]
    if not raw_lines:
        raise ListrikError(LIST_KOSONG, "Daftar nilai hambatan tidak boleh kosong.", 400)

    if len(raw_lines) > MAX_ITEMS:
        raise ListrikError(
            TOO_MANY_ITEMS,
            f"Maksimal {MAX_ITEMS} nilai hambatan dalam satu perhitungan.",
            413,
        )

    values: list[float] = []
    for idx, line in enumerate(raw_lines):
        val = parse_number(line, f"hambatan baris ke-{idx + 1}")
        if val == 0:
            raise ListrikError(
                DIVIDE_BY_ZERO,
                f"Nilai hambatan pada baris ke-{idx + 1} tidak boleh 0.",
                400,
            )
        if val < 0 or val > MAX_VALUE:
            raise ListrikError(
                OUT_OF_RANGE,
                f"Nilai hambatan pada baris ke-{idx + 1} harus lebih besar dari 0 dan maksimal 1.000.000.000.000 Ω.",
                400,
            )
        values.append(val)

    total: float
    langkah: list[str] = []

    if jenis == "seri":
        try:
            total = sum(values)
        except OverflowError:
            raise ListrikError(OUT_OF_RANGE, "Total hambatan seri melebihi batas.", 400)

        sym_str = " + ".join(f"R{i+1}" for i in range(len(values)))
        if len(values) <= 6:
            val_str = " + ".join(format_angka(v) for v in values)
            langkah.append(f"R_total = {sym_str}")
            langkah.append(f"R_total = {val_str} = {format_angka(total)} Ω")
        else:
            val_head = " + ".join(format_angka(v) for v in values[:3])
            langkah.append(f"R_total = {sym_str}")
            langkah.append(f"R_total = {val_head} + ... = {format_angka(total)} Ω")

    else:  # paralel
        try:
            inv_sum = sum(1.0 / v for v in values)
        except OverflowError:
            raise ListrikError(OUT_OF_RANGE, "Perhitungan paralel melebihi batas.", 400)

        if inv_sum == 0:
            raise ListrikError(DIVIDE_BY_ZERO, "Pembagian dengan nol pada rangkaian paralel.", 400)

        try:
            total = 1.0 / inv_sum
        except OverflowError:
            raise ListrikError(OUT_OF_RANGE, "Total hambatan paralel melebihi batas.", 400)

        sym_str = " + ".join(f"1/R{i+1}" for i in range(len(values)))
        if len(values) <= 6:
            val_str = " + ".join(f"1/{format_angka(v)}" for v in values)
            langkah.append(f"1 / R_total = {sym_str}")
            langkah.append(f"1 / R_total = {val_str}")
        else:
            val_head = " + ".join(f"1/{format_angka(v)}" for v in values[:3])
            langkah.append(f"1 / R_total = {sym_str}")
            langkah.append(f"1 / R_total = {val_head} + ...")

        langkah.append(f"1 / R_total = {format_angka(inv_sum)}")
        langkah.append(f"R_total = 1 / {format_angka(inv_sum)} = {format_angka(total)} Ω")

    return {
        "mode": "hambatan",
        "mode_label": f"Hambatan total rangkaian ({jenis})",
        "jenis": jenis,
        "jumlah_komponen": len(values),
        "hasil": {
            "label": f"Hambatan total ({jenis})",
            "nilai": total,
            "teks": format_angka(total),
            "satuan": "Ω",
        },
        "komponen": [
            {"nomor": i + 1, "nilai": v, "teks": format_angka(v), "satuan": "Ω"}
            for i, v in enumerate(values)
        ],
        "langkah": langkah,
        "catatan_jujur": CATATAN_JUJUR,
    }


def hitung_listrik(mode: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Titik masuk murni kalkulator listrik berdasarkan mode."""
    if mode is None or not isinstance(mode, str) or not mode.strip():
        raise ListrikError(INVALID_REQUEST, "Field 'mode' wajib diisi.", 400)

    mode_norm = mode.strip().lower()
    valid_modes = [m["value"] for m in MODES]
    if mode_norm not in valid_modes:
        modes_str = ", ".join(valid_modes)
        raise ListrikError(
            UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak didukung. Pilih salah satu: {modes_str}.",
            400,
        )

    if mode_norm == "ohm":
        return hitung_ohm(
            tegangan_raw=data.get("tegangan"),
            arus_raw=data.get("arus"),
            hambatan_raw=data.get("hambatan"),
        )
    elif mode_norm == "daya":
        return hitung_daya(
            daya_alat_raw=data.get("daya_alat"),
            jam_per_hari_raw=data.get("jam_per_hari"),
            jumlah_alat_raw=data.get("jumlah_alat"),
            hari_raw=data.get("hari"),
            tarif_raw=data.get("tarif"),
        )
    elif mode_norm == "hambatan":
        return hitung_hambatan(
            daftar_raw=data.get("daftar"),
            jenis_raw=data.get("jenis"),
        )
    else:
        raise ListrikError(UNSUPPORTED_MODE, f"Mode '{mode}' tidak didukung.", 400)


def limits_payload() -> dict[str, Any]:
    """Mengembalikan batas operasional dan konfigurasi kalkulator listrik."""
    return {
        "max_input_chars": MAX_INPUT_CHARS,
        "max_value": MAX_VALUE,
        "max_items": MAX_ITEMS,
        "modes": [
            {
                "value": m["value"],
                "label": m["label"],
                "desc": m["desc"],
                "contoh": dict(m["contoh"]),
            }
            for m in MODES
        ],
        "processed_on": "server",
        "note": "Nilai diproses di memori server lalu dibuang, tidak disimpan di disk.",
        "catatan_jujur": CATATAN_JUJUR,
    }
