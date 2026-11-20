"""Kalkulator kapasitas AC ruangan: perkirakan kebutuhan BTU dan ukuran PK AC.

Docstring modul:
Hitungan memakai patokan umum 500 BTU per meter persegi untuk tinggi plafon standar 2,8 m.
Ini perkiraan kasar berdasarkan ukuran ruangan, tinggi plafon, jumlah orang,
perangkat elektronik penghasil panas, dan paparan sinar matahari.
Bukan pengganti survei teknisi pendingin udara (HVAC).

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori.
"""

from __future__ import annotations

import math
from typing import Any

# Batas operasional & konstanta
PANJANG_MIN = 1.0
PANJANG_MAX = 30.0
LEBAR_MIN = 1.0
LEBAR_MAX = 30.0
TINGGI_MIN = 2.0
TINGGI_MAX = 5.0
TINGGI_DEFAULT = 2.8

ORANG_MIN = 1
ORANG_MAX = 50
ORANG_DEFAULT = 2

PERANGKAT_MIN = 0
PERANGKAT_MAX = 20
PERANGKAT_DEFAULT = 0

PATOKAN_BTU_PER_M2 = 500

MATAHARI_PILIHAN = ["teduh", "sedang", "terkena matahari langsung"]

FAKTOR_MATAHARI: dict[str, float] = {
    "teduh": 1.0,
    "sedang": 1.05,
    "kena matahari langsung": 1.10,
    "terkena matahari langsung": 1.10,
}

PILIHAN_PK: list[dict[str, Any]] = [
    {"pk": "1/2 PK", "kapasitas_btu": 5000},
    {"pk": "3/4 PK", "kapasitas_btu": 7000},
    {"pk": "1 PK", "kapasitas_btu": 9000},
    {"pk": "1 1/4 PK", "kapasitas_btu": 11000},
    {"pk": "1 1/2 PK", "kapasitas_btu": 12000},
    {"pk": "2 PK", "kapasitas_btu": 18000},
    {"pk": "2 1/2 PK", "kapasitas_btu": 24000},
]

PESAN_JUJUR = (
    "Ini perkiraan kasar memakai patokan umum 500 BTU per meter persegi untuk plafon 2,8 m. "
    "Hasil bisa berbeda karena insulasi atap, jendela kaca, arah matahari, dan jumlah orang. "
    "Ukuran PK mengikuti ukuran AC yang umum dijual di Indonesia."
)

CATATAN_LEBIH_DARI_MAKS = (
    "lebih dari 2 1/2 PK, sebaiknya dua unit AC atau konsultasi ke teknisi"
)

# Kode galat stabil
INPUT_TIDAK_VALID = "input_tidak_valid"
DI_LUAR_RENTANG = "di_luar_rentang"
MATAHARI_TIDAK_DIKENAL = "matahari_tidak_dikenal"
BODY_BUKAN_JSON = "body_bukan_json"


class AcError(ValueError):
    """Galat operasional kalkulator AC dengan kode galat dan status HTTP."""

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
    """Mengembalikan batas operasional dan pilihan PK AC."""
    return {
        "panjang": {"min": int(PANJANG_MIN), "max": int(PANJANG_MAX)},
        "lebar": {"min": int(LEBAR_MIN), "max": int(LEBAR_MAX)},
        "tinggi": {"min": int(TINGGI_MIN), "max": int(TINGGI_MAX), "default": TINGGI_DEFAULT},
        "orang": {"min": ORANG_MIN, "max": ORANG_MAX, "default": ORANG_DEFAULT},
        "perangkat": {"min": PERANGKAT_MIN, "max": PERANGKAT_MAX, "default": PERANGKAT_DEFAULT},
        "matahari": list(MATAHARI_PILIHAN),
        "patokan_btu_per_m2": PATOKAN_BTU_PER_M2,
        "pilihan_pk": [dict(p) for p in PILIHAN_PK],
    }


def _parse_float(val: Any) -> float | None:
    """Konversi input ke float yang valid. Menolak boolean, NaN, dan inf."""
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)
    if isinstance(val, str):
        s = val.strip().replace(" ", "").replace(",", ".")
        if not s:
            return None
        try:
            f = float(s)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        except ValueError:
            return None
    return None


def _parse_int(val: Any) -> int | None:
    """Konversi input ke integer yang valid. Menolak boolean, float tak bulat, NaN, dan inf."""
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val) or not val.is_integer():
            return None
        return int(val)
    if isinstance(val, str):
        s = val.strip().replace(" ", "").replace(",", ".")
        if not s:
            return None
        try:
            f = float(s)
            if math.isnan(f) or math.isinf(f) or not f.is_integer():
                return None
            return int(f)
        except ValueError:
            return None
    return None


def hitung(
    panjang: Any = None,
    lebar: Any = None,
    tinggi: Any = None,
    orang: Any = None,
    perangkat: Any = None,
    matahari: Any = None,
    *,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hitung kapasitas pendinginan AC ruangan berdasarkan ukuran ruangan dan beban panas."""
    if isinstance(panjang, dict) and data is None:
        data = panjang
        panjang = None

    if data is not None:
        if not isinstance(data, dict):
            raise AcError(BODY_BUKAN_JSON, "Permintaan harus berupa objek JSON.", 400)
        panjang = data.get("panjang")
        lebar = data.get("lebar")
        tinggi = data.get("tinggi")
        orang = data.get("orang")
        perangkat = data.get("perangkat")
        matahari = data.get("matahari")

    # 1. Validasi panjang
    if panjang is None or (isinstance(panjang, str) and not panjang.strip()):
        raise AcError(
            INPUT_TIDAK_VALID,
            "Panjang ruangan wajib diisi dengan angka.",
            400,
        )
    p_val = _parse_float(panjang)
    if p_val is None:
        raise AcError(
            INPUT_TIDAK_VALID,
            "Panjang ruangan harus berupa angka.",
            400,
        )
    if p_val < PANJANG_MIN or p_val > PANJANG_MAX:
        raise AcError(
            DI_LUAR_RENTANG,
            f"Panjang ruangan harus antara {int(PANJANG_MIN)} dan {int(PANJANG_MAX)} meter.",
            400,
        )

    # 2. Validasi lebar
    if lebar is None or (isinstance(lebar, str) and not lebar.strip()):
        raise AcError(
            INPUT_TIDAK_VALID,
            "Lebar ruangan wajib diisi dengan angka.",
            400,
        )
    l_val = _parse_float(lebar)
    if l_val is None:
        raise AcError(
            INPUT_TIDAK_VALID,
            "Lebar ruangan harus berupa angka.",
            400,
        )
    if l_val < LEBAR_MIN or l_val > LEBAR_MAX:
        raise AcError(
            DI_LUAR_RENTANG,
            f"Lebar ruangan harus antara {int(LEBAR_MIN)} dan {int(LEBAR_MAX)} meter.",
            400,
        )

    # 3. Validasi tinggi plafon (opsional, bawaan 2.8 m)
    if tinggi is None or (isinstance(tinggi, str) and not tinggi.strip()):
        t_val = TINGGI_DEFAULT
    else:
        t_val_parsed = _parse_float(tinggi)
        if t_val_parsed is None:
            raise AcError(
                INPUT_TIDAK_VALID,
                "Tinggi plafon harus berupa angka.",
                400,
            )
        if t_val_parsed < TINGGI_MIN or t_val_parsed > TINGGI_MAX:
            raise AcError(
                DI_LUAR_RENTANG,
                f"Tinggi plafon harus antara {int(TINGGI_MIN)} dan {int(TINGGI_MAX)} meter.",
                400,
            )
        t_val = t_val_parsed

    # 4. Validasi jumlah orang (opsional, bawaan 2 orang)
    if orang is None or (isinstance(orang, str) and not orang.strip()):
        o_val = ORANG_DEFAULT
    else:
        o_val_parsed = _parse_int(orang)
        if o_val_parsed is None:
            raise AcError(
                INPUT_TIDAK_VALID,
                "Jumlah orang harus berupa angka bulat.",
                400,
            )
        if o_val_parsed < ORANG_MIN or o_val_parsed > ORANG_MAX:
            raise AcError(
                DI_LUAR_RENTANG,
                f"Jumlah orang harus antara {ORANG_MIN} dan {ORANG_MAX} orang.",
                400,
            )
        o_val = o_val_parsed

    # 5. Validasi jumlah perangkat (opsional, bawaan 0 unit)
    if perangkat is None or (isinstance(perangkat, str) and not perangkat.strip()):
        pr_val = PERANGKAT_DEFAULT
    else:
        pr_val_parsed = _parse_int(perangkat)
        if pr_val_parsed is None:
            raise AcError(
                INPUT_TIDAK_VALID,
                "Jumlah perangkat harus berupa angka bulat.",
                400,
            )
        if pr_val_parsed < PERANGKAT_MIN or pr_val_parsed > PERANGKAT_MAX:
            raise AcError(
                DI_LUAR_RENTANG,
                f"Jumlah perangkat harus antara {PERANGKAT_MIN} dan {PERANGKAT_MAX} unit.",
                400,
            )
        pr_val = pr_val_parsed

    # 6. Validasi kondisi matahari
    if matahari is None or (isinstance(matahari, str) and not matahari.strip()):
        m_key = "teduh"
    else:
        m_key = str(matahari).strip().lower()
        if m_key not in FAKTOR_MATAHARI:
            raise AcError(
                MATAHARI_TIDAK_DIKENAL,
                "Kondisi sinar matahari tidak dikenal. Pilih teduh, sedang, atau terkena matahari langsung.",
                400,
            )

    faktor = FAKTOR_MATAHARI[m_key]

    # --- RUMUS HITUNG ---
    # 1. luas = panjang x lebar
    luas = p_val * l_val
    volume = luas * t_val

    # 2. btu_dasar = luas x 500 x (tinggi / 2.8)
    btu_dasar_calc = luas * PATOKAN_BTU_PER_M2 * (t_val / 2.8)
    btu_dasar_int = int(round(btu_dasar_calc))

    # 3. tambahan_orang = max(0, orang - 2) x 400
    tambahan_orang = max(0, o_val - 2) * 400

    # 4. tambahan_perangkat = perangkat x 400
    tambahan_perangkat = pr_val * 400

    # 5. btu_mentah = (btu_dasar + tambahan_orang + tambahan_perangkat) x faktor_matahari
    btu_mentah = (btu_dasar_calc + tambahan_orang + tambahan_perangkat) * faktor

    # 6. btu = bulatkan ke atas ke kelipatan 500
    # Menggunakan round(..., 6) untuk menghindari ketidakakuratan floating-point
    btu = int(math.ceil(round(btu_mentah, 6) / 500.0) * 500)

    # 7. Rekomendasi ukuran: bandingkan dengan daftar kapasitas AC yang umum dijual di Indonesia
    matched_pk: str | None = None
    for item in PILIHAN_PK:
        if item["kapasitas_btu"] >= btu:
            matched_pk = str(item["pk"])
            break

    if matched_pk is not None:
        pk: str | None = matched_pk
        pk_label: str = matched_pk
        catatan_pk: str | None = None
    else:
        pk = None
        pk_label = "lebih dari 2 1/2 PK"
        catatan_pk = CATATAN_LEBIH_DARI_MAKS

    # 8. Daftar semua ukuran dengan tanda cukup / kurang
    pilihan: list[dict[str, Any]] = [
        {
            "pk": item["pk"],
            "kapasitas_btu": item["kapasitas_btu"],
            "cukup": item["kapasitas_btu"] >= btu,
        }
        for item in PILIHAN_PK
    ]

    return {
        "luas_m2": round(luas, 2),
        "volume_m3": round(volume, 2),
        "btu": btu,
        "pk": pk,
        "pk_label": pk_label,
        "catatan_pk": catatan_pk,
        "rincian": {
            "btu_dasar": btu_dasar_int,
            "tambahan_orang": tambahan_orang,
            "tambahan_perangkat": tambahan_perangkat,
            "faktor_matahari": faktor,
        },
        "pilihan": pilihan,
        "pesan": PESAN_JUJUR,
    }
