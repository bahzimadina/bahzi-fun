"""Logika kalkulator kebutuhan bata dinding: fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import math
import re
from typing import Any

# Batas operasional
MIN_PANJANG_M = 0.1
MAX_PANJANG_M = 100.0
MIN_TINGGI_M = 0.1
MAX_TINGGI_M = 10.0
MIN_LUAS_M2 = 0.1
MAX_LUAS_M2 = 5000.0

MIN_CADANGAN = 0
MAX_CADANGAN = 30
DEFAULT_CADANGAN = 5

MIN_HARGA = 0
MAX_HARGA = 1_000_000_000

MAX_BATA = 1_000_000

MAX_BODY_BYTES = 64 * 1024

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
UNSUPPORTED_JENIS = "UNSUPPORTED_JENIS"
UNSUPPORTED_CAMPURAN = "UNSUPPORTED_CAMPURAN"
INVALID_NUMBER = "INVALID_NUMBER"
OUT_OF_RANGE = "OUT_OF_RANGE"
INVALID_BUKAAN = "INVALID_BUKAAN"
INVALID_CADANGAN = "INVALID_CADANGAN"
INVALID_HARGA = "INVALID_HARGA"
TOO_MANY_BATA = "TOO_MANY_BATA"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class BataError(ValueError):
    """Galat operasional kalkulator bata dengan kode galat dan status HTTP."""

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


TABEL_PATOKAN: dict[str, dict[str, Any]] = {
    "bata-merah": {
        "kode": "bata-merah",
        "label": "Bata merah",
        "ukuran": "23 x 11 x 5 cm",
        "bata_per_m2": 70,
        "bata_satuan": "buah",
        "perekat_jenis": "semen_pasir",
        "semen_berat_sak_kg": 50,
        "campuran": {
            "1:3": {"semen_sak_per_m2": 0.230, "semen_kg_per_m2": 11.5, "pasir_m3_per_m2": 0.043},
            "1:4": {"semen_sak_per_m2": 0.194, "semen_kg_per_m2": 9.7, "pasir_m3_per_m2": 0.047},
            "1:5": {"semen_sak_per_m2": 0.168, "semen_kg_per_m2": 8.4, "pasir_m3_per_m2": 0.050},
        },
        "keterangan": "Pasangan 1/2 bata, tebal spesi adukan 1 sampai 1,5 cm, semen sak 50 kg.",
    },
    "batako": {
        "kode": "batako",
        "label": "Batako",
        "ukuran": "40 x 20 x 10 cm",
        "bata_per_m2": 12.5,
        "bata_satuan": "buah",
        "perekat_jenis": "semen_pasir",
        "semen_berat_sak_kg": 50,
        "campuran": {
            "1:3": {"semen_sak_per_m2": 0.300, "semen_kg_per_m2": 15.0, "pasir_m3_per_m2": 0.045},
            "1:4": {"semen_sak_per_m2": 0.260, "semen_kg_per_m2": 13.0, "pasir_m3_per_m2": 0.048},
            "1:5": {"semen_sak_per_m2": 0.220, "semen_kg_per_m2": 11.0, "pasir_m3_per_m2": 0.051},
        },
        "keterangan": "Tebal spesi adukan 1 sampai 1,5 cm, semen sak 50 kg.",
    },
    "hebel-75": {
        "kode": "hebel-75",
        "label": "Bata ringan 7,5 cm",
        "ukuran": "60 x 20 x 7,5 cm",
        "bata_per_m2": 8.33,
        "bata_satuan": "buah",
        "perekat_jenis": "mortar",
        "mortar_sak_per_m2": 0.090,
        "mortar_berat_sak_kg": 40,
        "keterangan": "Tebal spesi perekat tipis 2 sampai 3 mm, mortar instan sak 40 kg.",
    },
    "hebel-100": {
        "kode": "hebel-100",
        "label": "Bata ringan 10 cm",
        "ukuran": "60 x 20 x 10 cm",
        "bata_per_m2": 8.33,
        "bata_satuan": "buah",
        "perekat_jenis": "mortar",
        "mortar_sak_per_m2": 0.100,
        "mortar_berat_sak_kg": 40,
        "keterangan": "Tebal spesi perekat tipis 2 sampai 3 mm, mortar instan sak 40 kg.",
    },
}


def parse_decimal_number(
    val: Any,
    label: str,
    min_val: float | None = None,
    max_val: float | None = None,
    satuan: str = "",
) -> float:
    """Validasi dan konversi nilai angka desimal ke float."""
    if val is None:
        raise BataError(INVALID_REQUEST, f"{label} wajib diisi.", 400)

    if isinstance(val, bool):
        raise BataError(INVALID_NUMBER, f"{label} harus berupa angka yang valid.", 400)

    if isinstance(val, (int, float)):
        num = float(val)
        if math.isnan(num) or math.isinf(num):
            raise BataError(INVALID_NUMBER, f"{label} bukan angka yang valid.", 400)
    elif isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            raise BataError(INVALID_NUMBER, f"{label} tidak boleh kosong.", 400)

        dot_count = cleaned.count(".")
        comma_count = cleaned.count(",")
        if (dot_count + comma_count) > 1:
            raise BataError(
                INVALID_NUMBER,
                f"Format angka {label.lower()} tidak valid. Gunakan satu tanda titik atau koma desimal.",
                400,
            )

        normalized = cleaned.replace(",", ".")
        if not re.fullmatch(r"^\d+(\.\d+)?$", normalized):
            raise BataError(
                INVALID_NUMBER,
                f"{label} harus berupa angka positif yang valid.",
                400,
            )

        try:
            num = float(normalized)
        except ValueError:
            raise BataError(INVALID_NUMBER, f"{label} tidak dapat dibaca sebagai angka.", 400)

        if math.isnan(num) or math.isinf(num):
            raise BataError(INVALID_NUMBER, f"{label} bukan angka yang valid.", 400)
    else:
        raise BataError(INVALID_REQUEST, f"{label} harus berupa teks angka atau bilangan.", 400)

    if min_val is not None and max_val is not None:
        if num < min_val or num > max_val:
            unit_str = f" {satuan}" if satuan else ""
            raise BataError(
                OUT_OF_RANGE,
                f"{label} ({num}{unit_str}) harus antara {min_val} hingga {max_val}{unit_str}.",
                400,
            )

    return num


def parse_cadangan(val: Any) -> int:
    """Validasi dan parsing persentase cadangan bata (0..30%)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return DEFAULT_CADANGAN

    if isinstance(val, bool):
        raise BataError(INVALID_CADANGAN, "Persentase cadangan harus berupa bilangan bulat.", 400)

    if isinstance(val, (int, float)):
        num = int(val)
        if num < MIN_CADANGAN or num > MAX_CADANGAN:
            raise BataError(
                INVALID_CADANGAN,
                f"Persentase cadangan harus antara {MIN_CADANGAN} hingga {MAX_CADANGAN} persen.",
                400,
            )
        return num

    s = str(val).strip()
    if s.startswith("-"):
        raise BataError(INVALID_CADANGAN, "Persentase cadangan tidak boleh bernilai negatif.", 400)

    if not re.fullmatch(r"^\d+$", s):
        raise BataError(
            INVALID_CADANGAN,
            f"Persentase cadangan harus berupa bilangan bulat antara {MIN_CADANGAN} hingga {MAX_CADANGAN} persen.",
            400,
        )

    try:
        num = int(s)
    except ValueError:
        raise BataError(INVALID_CADANGAN, "Persentase cadangan tidak valid.", 400)

    if num < MIN_CADANGAN or num > MAX_CADANGAN:
        raise BataError(
            INVALID_CADANGAN,
            f"Persentase cadangan harus antara {MIN_CADANGAN} hingga {MAX_CADANGAN} persen.",
            400,
        )

    return num


def parse_harga(val: Any, label: str = "Harga") -> int | None:
    """Validasi dan parsing harga rupiah (0..1.000.000.000). Mengembalikan None jika kosong."""
    if val is None:
        return None

    if isinstance(val, bool):
        raise BataError(INVALID_HARGA, f"{label} harus berupa bilangan bulat rupiah.", 400)

    if isinstance(val, (int, float)):
        if isinstance(val, float) and not val.is_integer():
            raise BataError(INVALID_HARGA, f"{label} harus berupa bilangan bulat rupiah.", 400)
        num = int(val)
        if num < 0:
            raise BataError(INVALID_HARGA, f"{label} tidak boleh bernilai negatif.", 400)
    elif isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        if s.startswith("-"):
            raise BataError(INVALID_HARGA, f"{label} tidak boleh bernilai negatif.", 400)
        s_clean = s.replace(".", "").replace(",", "").replace(" ", "")
        if not re.fullmatch(r"^\d+$", s_clean):
            raise BataError(
                INVALID_HARGA,
                f"{label} harus berupa bilangan bulat rupiah tanpa simbol atau huruf.",
                400,
            )
        try:
            num = int(s_clean)
        except ValueError:
            raise BataError(INVALID_HARGA, f"{label} tidak valid.", 400)
    else:
        raise BataError(INVALID_HARGA, f"{label} tidak valid.", 400)

    if num < MIN_HARGA or num > MAX_HARGA:
        raise BataError(
            INVALID_HARGA,
            f"{label} harus antara Rp {MIN_HARGA} hingga Rp {MAX_HARGA:,}.",
            400,
        )

    return num


def hitung_bata(
    mode: Any = "dimensi",
    panjang: Any = None,
    tinggi: Any = None,
    luas: Any = None,
    bukaan: Any = None,
    jenis: Any = "bata-merah",
    campuran: Any = "1:4",
    cadangan: Any = DEFAULT_CADANGAN,
    harga_bata: Any = None,
    harga_semen: Any = None,
    harga_pasir: Any = None,
    harga_mortar: Any = None,
) -> dict[str, Any]:
    """Hitung kebutuhan bata dinding, perekat, pasir, dan biaya murni di memori."""
    if mode is None:
        raise BataError(INVALID_REQUEST, "Mode perhitungan wajib dipilih.", 400)
    if not isinstance(mode, str):
        raise BataError(INVALID_REQUEST, "Mode perhitungan harus berupa teks string.", 400)

    mode_norm = mode.strip().lower()
    if mode_norm not in ("dimensi", "luas"):
        raise BataError(
            UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak didukung. Pilih 'dimensi' atau 'luas'.",
            400,
        )

    if jenis is None or not isinstance(jenis, str):
        jenis_norm = "bata-merah"
    else:
        jenis_norm = jenis.strip().lower()

    if jenis_norm not in TABEL_PATOKAN:
        daftar_jenis = ", ".join(TABEL_PATOKAN.keys())
        raise BataError(
            UNSUPPORTED_JENIS,
            f"Jenis bata '{jenis}' tidak didukung. Pilihan: {daftar_jenis}.",
            400,
        )

    info_jenis = TABEL_PATOKAN[jenis_norm]

    # Validasi campuran
    campuran_norm: str | None = None
    if info_jenis["perekat_jenis"] == "semen_pasir":
        if campuran is None or (isinstance(campuran, str) and not campuran.strip()):
            campuran_norm = "1:4"
        elif isinstance(campuran, str):
            campuran_norm = campuran.strip()
            if campuran_norm not in ("1:3", "1:4", "1:5"):
                raise BataError(
                    UNSUPPORTED_CAMPURAN,
                    f"Campuran adukan '{campuran}' tidak didukung. Pilihan: 1:3, 1:4, atau 1:5.",
                    400,
                )
        else:
            raise BataError(
                UNSUPPORTED_CAMPURAN,
                "Campuran adukan harus berupa teks seperti '1:4'.",
                400,
            )
    else:
        # Untuk hebel, campuran diabaikan (tetap diterima, jangan galat)
        campuran_norm = None

    # Dimensi & bukaan
    if mode_norm == "dimensi":
        p_m = parse_decimal_number(panjang, "Panjang dinding", MIN_PANJANG_M, MAX_PANJANG_M, "meter")
        t_m = parse_decimal_number(tinggi, "Tinggi dinding", MIN_TINGGI_M, MAX_TINGGI_M, "meter")
        luas_kotor_m2 = round(p_m * t_m, 2)
    else:
        luas_val = parse_decimal_number(luas, "Luas dinding", MIN_LUAS_M2, MAX_LUAS_M2, "m²")
        luas_kotor_m2 = round(luas_val, 2)

    if bukaan is None or (isinstance(bukaan, str) and not bukaan.strip()):
        bukaan_m2 = 0.0
    else:
        if (isinstance(bukaan, str) and bukaan.strip().startswith("-")) or (
            isinstance(bukaan, (int, float)) and bukaan < 0
        ):
            raise BataError(INVALID_BUKAAN, "Luas bukaan pintu dan jendela tidak boleh bernilai negatif.", 400)
        bukaan_m2 = parse_decimal_number(bukaan, "Luas bukaan")
        if bukaan_m2 < 0:
            raise BataError(INVALID_BUKAAN, "Luas bukaan pintu dan jendela tidak boleh bernilai negatif.", 400)
        bukaan_m2 = round(bukaan_m2, 2)

    if bukaan_m2 >= luas_kotor_m2:
        raise BataError(
            INVALID_BUKAAN,
            f"Luas bukaan ({bukaan_m2} m²) tidak boleh melebihi atau sama dengan luas kotor dinding ({luas_kotor_m2} m²).",
            400,
        )

    luas_dinding_m2 = round(luas_kotor_m2 - bukaan_m2, 2)
    if luas_dinding_m2 <= 0:
        raise BataError(
            INVALID_BUKAAN,
            "Luas dinding bersih setelah dikurangi bukaan harus lebih besar dari nol.",
            400,
        )

    cadangan_persen = parse_cadangan(cadangan)

    # Perhitungan jumlah bata
    d_luas = Decimal(str(luas_dinding_m2))
    bata_per_m2 = info_jenis["bata_per_m2"]
    d_bata_per_m2 = Decimal(str(bata_per_m2))

    bata_pasang = int((d_luas * d_bata_per_m2).to_integral_value(rounding=ROUND_CEILING))

    d_cadangan = Decimal(cadangan_persen) / Decimal("100")
    bata_cadangan_pasang = int((Decimal(bata_pasang) * d_cadangan).to_integral_value(rounding=ROUND_CEILING))

    bata_dibeli = bata_pasang + bata_cadangan_pasang

    if bata_dibeli > MAX_BATA or bata_pasang > MAX_BATA:
        raise BataError(
            TOO_MANY_BATA,
            f"Perkiraan kebutuhan bata ({bata_dibeli:,} buah) melebihi batas maksimum {MAX_BATA:,} buah. Periksa kembali ukuran dinding.",
            413,
        )

    # Perhitungan bahan perekat & pasir
    if info_jenis["perekat_jenis"] == "semen_pasir":
        info_camp = info_jenis["campuran"][campuran_norm]
        d_semen_kg_per_m2 = Decimal(str(info_camp["semen_kg_per_m2"]))
        d_semen_kg = d_luas * d_semen_kg_per_m2
        semen_kg = float(d_semen_kg.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        semen_sak = int((d_semen_kg / Decimal("50")).to_integral_value(rounding=ROUND_CEILING))
        semen_berat_sak_kg = 50

        d_pasir_per_m2 = Decimal(str(info_camp["pasir_m3_per_m2"]))
        d_pasir_m3 = (d_luas * d_pasir_per_m2).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
        pasir_m3 = float(d_pasir_m3)

        mortar_sak = None
        mortar_berat_sak_kg = None

        patokan = {
            "bata_per_m2": bata_per_m2,
            "semen_kg_per_m2": info_camp["semen_kg_per_m2"],
            "pasir_m3_per_m2": info_camp["pasir_m3_per_m2"],
            "sumber": "patokan umum pasangan dinding, tebal spesi 1 sampai 1,5 cm",
        }
    else:
        semen_kg = None
        semen_sak = None
        semen_berat_sak_kg = None
        pasir_m3 = None

        d_mortar_per_m2 = Decimal(str(info_jenis["mortar_sak_per_m2"]))
        mortar_sak = int((d_luas * d_mortar_per_m2).to_integral_value(rounding=ROUND_CEILING))
        mortar_berat_sak_kg = 40

        patokan = {
            "bata_per_m2": bata_per_m2,
            "mortar_sak_per_m2": info_jenis["mortar_sak_per_m2"],
            "sumber": "patokan umum pasangan dinding bata ringan, tebal spesi 2 sampai 3 mm",
        }

    # Perkiraan biaya
    h_bata = parse_harga(harga_bata, "Harga bata")
    h_semen = parse_harga(harga_semen, "Harga semen")
    h_pasir = parse_harga(harga_pasir, "Harga pasir")
    h_mortar = parse_harga(harga_mortar, "Harga mortar")

    if info_jenis["perekat_jenis"] == "semen_pasir":
        harga_diisi = [h for h in [h_bata, h_semen, h_pasir] if h is not None]
        if not harga_diisi:
            biaya: dict[str, Any] | None = None
        else:
            biaya_bata = (bata_dibeli * h_bata) if h_bata is not None else None
            biaya_ikat = (semen_sak * h_semen) if h_semen is not None else None
            biaya_pasir = (
                int((Decimal(str(pasir_m3)) * Decimal(h_pasir)).to_integral_value(rounding=ROUND_HALF_UP))
                if h_pasir is not None
                else None
            )
            komponen_aktif = [c for c in [biaya_bata, biaya_ikat, biaya_pasir] if c is not None]
            total = sum(komponen_aktif)
            per_m2 = int((Decimal(total) / d_luas).to_integral_value(rounding=ROUND_HALF_UP))
            lengkap = (h_bata is not None and h_semen is not None and h_pasir is not None)
            biaya = {
                "bata": biaya_bata,
                "ikat": biaya_ikat,
                "pasir": biaya_pasir,
                "total": total,
                "per_m2": per_m2,
                "lengkap": lengkap,
            }
    else:
        harga_diisi = [h for h in [h_bata, h_mortar] if h is not None]
        if not harga_diisi:
            biaya = None
        else:
            biaya_bata = (bata_dibeli * h_bata) if h_bata is not None else None
            biaya_ikat = (mortar_sak * h_mortar) if h_mortar is not None else None
            biaya_pasir = None
            komponen_aktif = [c for c in [biaya_bata, biaya_ikat] if c is not None]
            total = sum(komponen_aktif)
            per_m2 = int((Decimal(total) / d_luas).to_integral_value(rounding=ROUND_HALF_UP))
            lengkap = (h_bata is not None and h_mortar is not None)
            biaya = {
                "bata": biaya_bata,
                "ikat": biaya_ikat,
                "pasir": None,
                "total": total,
                "per_m2": per_m2,
                "lengkap": lengkap,
            }

    # Catatan informatif
    catatan: list[str] = []
    if cadangan_persen > 0:
        catatan.append(
            f"Cadangan {cadangan_persen}% ({bata_cadangan_pasang} buah) disiapkan untuk potongan sudut, pinggiran kusen, dan risiko bata pecah saat pemasangan."
        )
    else:
        catatan.append(
            "Perhitungan tanpa cadangan bata (0%). Sebaiknya siapkan cadangan 5% hingga 10% untuk potongan pinggir dan risiko pecah."
        )

    if bukaan_m2 > 0:
        catatan.append(
            f"Luas bukaan {bukaan_m2} m² (pintu/jendela) sudah dikurangkan dari luas kotor dinding."
        )

    if info_jenis["perekat_jenis"] == "mortar":
        catatan.append(
            "Bata ringan dipasang menggunakan perekat mortar instan tipis (spesi 2-3 mm, sak 40 kg), tanpa pasir."
        )
    else:
        catatan.append(
            f"Kebutuhan semen dan pasir dihitung dengan perbandingan adukan {campuran_norm} dan asumsi tebal spesi 1 sampai 1,5 cm."
        )

    catatan.append(
        "Hasil perhitungan adalah perkiraan matematis. Kebutuhan sebenarnya di lapangan bisa berbeda tergantung ukuran nyata bata di toko, kebiasaan tukang, dan ketebalan spesi adukan."
    )

    return {
        "mode": mode_norm,
        "jenis": jenis_norm,
        "jenis_label": info_jenis["label"],
        "campuran": campuran_norm,
        "luas_kotor_m2": luas_kotor_m2,
        "bukaan_m2": bukaan_m2,
        "luas_dinding_m2": luas_dinding_m2,
        "bata_per_m2": bata_per_m2,
        "bata_pasang": bata_pasang,
        "bata_cadangan_pasang": bata_cadangan_pasang,
        "bata_dibeli": bata_dibeli,
        "bata_satuan": "buah",
        "semen_kg": semen_kg,
        "semen_sak": semen_sak,
        "semen_berat_sak_kg": semen_berat_sak_kg,
        "pasir_m3": pasir_m3,
        "mortar_sak": mortar_sak,
        "mortar_berat_sak_kg": mortar_berat_sak_kg,
        "cadangan_persen": cadangan_persen,
        "biaya": biaya,
        "patokan": patokan,
        "catatan": catatan,
    }


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional, pilihan jenis bata, campuran, dan tabel patokan."""
    return {
        "modes": [
            {"value": "dimensi", "label": "Ukuran dinding (panjang x tinggi)"},
            {"value": "luas", "label": "Luas dinding (m²)"},
        ],
        "jenis_pilihan": [
            {
                "kode": "bata-merah",
                "label": "Bata merah (23 x 11 x 5 cm)",
                "ukuran": "23 x 11 x 5 cm",
                "bata_per_m2": 70,
                "satuan_perekat": "semen_pasir",
                "perekat_label": "Semen (sak 50 kg) & Pasir (m³)",
            },
            {
                "kode": "batako",
                "label": "Batako (40 x 20 x 10 cm)",
                "ukuran": "40 x 20 x 10 cm",
                "bata_per_m2": 12.5,
                "satuan_perekat": "semen_pasir",
                "perekat_label": "Semen (sak 50 kg) & Pasir (m³)",
            },
            {
                "kode": "hebel-75",
                "label": "Bata ringan 7,5 cm (60 x 20 x 7,5 cm)",
                "ukuran": "60 x 20 x 7,5 cm",
                "bata_per_m2": 8.33,
                "satuan_perekat": "mortar",
                "perekat_label": "Mortar instan (sak 40 kg)",
            },
            {
                "kode": "hebel-100",
                "label": "Bata ringan 10 cm (60 x 20 x 10 cm)",
                "ukuran": "60 x 20 x 10 cm",
                "bata_per_m2": 8.33,
                "satuan_perekat": "mortar",
                "perekat_label": "Mortar instan (sak 40 kg)",
            },
        ],
        "campuran_pilihan": [
            {"kode": "1:3", "label": "1 : 3 (kedap air / trasram)"},
            {"kode": "1:4", "label": "1 : 4 (standar dinding biasa)"},
            {"kode": "1:5", "label": "1 : 5 (ekonomis / pagar)"},
        ],
        "cadangan_bawaan": DEFAULT_CADANGAN,
        "rentang_cadangan": {
            "min": MIN_CADANGAN,
            "max": MAX_CADANGAN,
            "bawaan": DEFAULT_CADANGAN,
            "satuan": "%",
        },
        "rentang_harga": {
            "min": MIN_HARGA,
            "max": MAX_HARGA,
            "satuan": "rupiah",
        },
        "batas_dimensi": {
            "panjang_m": {"min": MIN_PANJANG_M, "max": MAX_PANJANG_M, "satuan": "m"},
            "tinggi_m": {"min": MIN_TINGGI_M, "max": MAX_TINGGI_M, "satuan": "m"},
            "luas_m2": {"min": MIN_LUAS_M2, "max": MAX_LUAS_M2, "satuan": "m²"},
        },
        "batas_bata": MAX_BATA,
        "tabel_patokan": TABEL_PATOKAN,
        "processed_on": "server",
        "note": "Angka diproses di memori lalu dibuang, tidak disimpan di disk.",
    }
