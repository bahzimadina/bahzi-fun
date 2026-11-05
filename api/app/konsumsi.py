"""Logika kalkulator konsumsi acara: fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import math
import re
from typing import Any

# Batas operasional
MIN_TAMU = 1
MAX_TAMU = 5000
DEFAULT_TAMU = 100

MIN_CADANGAN = 0
MAX_CADANGAN = 50
DEFAULT_CADANGAN = 10

MAX_PORSI = 10000

MIN_HARGA = 0
MAX_HARGA = 1_000_000

MAX_BODY_BYTES = 64 * 1024

# Pilihan mode
MODES = ("nasi_kotak", "prasmanan", "snack")

# Pilihan jenis lauk prasmanan
JENIS_LAUK = ("ayam", "ikan", "daging", "telur")
DEFAULT_LAUK = "ayam"

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
UNSUPPORTED_LAUK = "UNSUPPORTED_LAUK"
INVALID_NUMBER = "INVALID_NUMBER"
OUT_OF_RANGE = "OUT_OF_RANGE"
INVALID_CADANGAN = "INVALID_CADANGAN"
PORSI_TOO_LARGE = "PORSI_TOO_LARGE"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class KonsumsiError(ValueError):
    """Galat operasional kalkulator konsumsi dengan kode galat dan status HTTP."""

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


def format_angka_id(val: int | float | Decimal, max_desimal: int = 2) -> str:
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


def parse_tamu(val: Any) -> int:
    """Validasi dan parsing jumlah tamu (1..5000 orang)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        raise KonsumsiError(INVALID_REQUEST, "Jumlah tamu wajib diisi.", 400)

    if isinstance(val, bool):
        raise KonsumsiError(INVALID_NUMBER, "Jumlah tamu harus berupa bilangan bulat.", 400)

    if isinstance(val, (int, float)):
        if isinstance(val, float) and not val.is_integer():
            raise KonsumsiError(INVALID_NUMBER, "Jumlah tamu harus berupa bilangan bulat.", 400)
        num = int(val)
    elif isinstance(val, str):
        cleaned = val.strip()
        if not re.fullmatch(r"^\d+$", cleaned):
            if re.fullmatch(r"^-\d+$", cleaned):
                raise KonsumsiError(
                    OUT_OF_RANGE,
                    f"Jumlah tamu harus antara {format_angka_id(MIN_TAMU)} dan {format_angka_id(MAX_TAMU)} orang.",
                    400,
                )
            raise KonsumsiError(INVALID_NUMBER, "Jumlah tamu harus berupa bilangan bulat positif.", 400)
        try:
            num = int(cleaned)
        except ValueError:
            raise KonsumsiError(INVALID_NUMBER, "Jumlah tamu tidak valid.", 400)
    else:
        raise KonsumsiError(INVALID_REQUEST, "Jumlah tamu harus berupa bilangan bulat.", 400)

    if num < MIN_TAMU or num > MAX_TAMU:
        raise KonsumsiError(
            OUT_OF_RANGE,
            f"Jumlah tamu harus antara {format_angka_id(MIN_TAMU)} dan {format_angka_id(MAX_TAMU)} orang.",
            400,
        )

    return num


def parse_cadangan(val: Any) -> int:
    """Validasi dan parsing persentase cadangan konsumsi (0..50%)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return DEFAULT_CADANGAN

    if isinstance(val, bool):
        raise KonsumsiError(INVALID_CADANGAN, "Persentase cadangan harus berupa bilangan bulat.", 400)

    if isinstance(val, (int, float)):
        if isinstance(val, float) and not val.is_integer():
            raise KonsumsiError(INVALID_CADANGAN, "Persentase cadangan harus berupa bilangan bulat.", 400)
        num = int(val)
    elif isinstance(val, str):
        s = val.strip()
        if not re.fullmatch(r"^\d+$", s):
            raise KonsumsiError(
                INVALID_CADANGAN,
                f"Persentase cadangan harus antara {MIN_CADANGAN} hingga {MAX_CADANGAN} persen.",
                400,
            )
        try:
            num = int(s)
        except ValueError:
            raise KonsumsiError(INVALID_CADANGAN, "Persentase cadangan tidak valid.", 400)
    else:
        raise KonsumsiError(INVALID_CADANGAN, "Persentase cadangan tidak valid.", 400)

    if num < MIN_CADANGAN or num > MAX_CADANGAN:
        raise KonsumsiError(
            INVALID_CADANGAN,
            f"Persentase cadangan harus antara {MIN_CADANGAN} hingga {MAX_CADANGAN} persen.",
            400,
        )

    return num


def parse_harga(val: Any, label: str = "Harga") -> int | None:
    """Validasi dan parsing harga rupiah (0..1.000.000). Mengembalikan None jika kosong."""
    if val is None:
        return None

    if isinstance(val, bool):
        raise KonsumsiError(INVALID_NUMBER, f"{label} harus berupa angka rupiah yang valid.", 400)

    if isinstance(val, (int, float)):
        if isinstance(val, float) and not val.is_integer():
            raise KonsumsiError(INVALID_NUMBER, f"{label} harus berupa bilangan bulat rupiah.", 400)
        num = int(val)
    elif isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        s_clean = s.replace(".", "").replace(",", "").replace(" ", "")
        if not re.fullmatch(r"^\d+$", s_clean):
            if re.fullmatch(r"^-\d+$", s_clean):
                raise KonsumsiError(
                    OUT_OF_RANGE,
                    f"{label} harus antara Rp {format_angka_id(MIN_HARGA)} dan Rp {format_angka_id(MAX_HARGA)}.",
                    400,
                )
            raise KonsumsiError(INVALID_NUMBER, f"{label} harus berupa angka rupiah yang valid.", 400)
        try:
            num = int(s_clean)
        except ValueError:
            raise KonsumsiError(INVALID_NUMBER, f"{label} tidak valid.", 400)
    else:
        raise KonsumsiError(INVALID_NUMBER, f"{label} tidak valid.", 400)

    if num < MIN_HARGA or num > MAX_HARGA:
        raise KonsumsiError(
            OUT_OF_RANGE,
            f"{label} harus antara Rp {format_angka_id(MIN_HARGA)} dan Rp {format_angka_id(MAX_HARGA)}.",
            400,
        )

    return num


def parse_jenis_lauk(val: Any) -> str:
    """Validasi jenis lauk untuk mode prasmanan (ayam, ikan, daging, telur)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return DEFAULT_LAUK

    if not isinstance(val, str):
        raise KonsumsiError(UNSUPPORTED_LAUK, "Pilihan jenis lauk tidak valid.", 400)

    s = val.strip().lower()
    if s not in JENIS_LAUK:
        daftar = ", ".join(JENIS_LAUK)
        raise KonsumsiError(
            UNSUPPORTED_LAUK,
            f"Jenis lauk '{val}' tidak didukung. Pilihan: {daftar}.",
            400,
        )

    return s


def hitung_konsumsi(
    mode: Any = "nasi_kotak",
    tamu: Any = None,
    cadangan: Any = DEFAULT_CADANGAN,
    harga_porsi: Any = None,
    jenis_lauk: Any = DEFAULT_LAUK,
    harga_beras: Any = None,
    harga_lauk: Any = None,
    harga_sayur: Any = None,
    harga_tahu_tempe: Any = None,
    harga_minyak: Any = None,
    harga_air: Any = None,
    harga_perlengkapan: Any = None,
) -> dict[str, Any]:
    """Hitung kebutuhan konsumsi acara di memori."""
    if mode is None:
        raise KonsumsiError(INVALID_REQUEST, "Mode perhitungan konsumsi wajib dipilih.", 400)
    if not isinstance(mode, str):
        raise KonsumsiError(INVALID_REQUEST, "Mode perhitungan harus berupa teks string.", 400)

    mode_norm = mode.strip().lower()
    if mode_norm not in MODES:
        daftar_mode = ", ".join(MODES)
        raise KonsumsiError(
            UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak didukung. Pilihan: {daftar_mode}.",
            400,
        )

    tamu_int = parse_tamu(tamu)
    cadangan_int = parse_cadangan(cadangan)

    # Perhitungan porsi
    d_tamu = Decimal(str(tamu_int))
    d_cad = Decimal(str(cadangan_int))
    d_porsi = (d_tamu * (Decimal("1") + d_cad / Decimal("100"))).to_integral_value(rounding=ROUND_CEILING)
    porsi = int(d_porsi)

    if porsi > MAX_PORSI:
        raise KonsumsiError(
            PORSI_TOO_LARGE,
            f"Jumlah porsi ({format_angka_id(porsi)}) melebihi batas maksimal {format_angka_id(MAX_PORSI)} porsi.",
            413,
        )

    catatan = "Patokan ini perkiraan umum untuk acara di Indonesia. Jumlah sebenarnya tergantung menu, porsi makan tamu, dan kebiasaan setempat. Tambahkan cadangan bila tamu sulit dipastikan."

    if mode_norm == "nasi_kotak":
        kotak = porsi
        air_botol = porsi
        air_dus = math.ceil(porsi / 24)

        ringkas = [
            {"label": "Porsi siap", "nilai": str(porsi), "satuan": "porsi"},
            {"label": "Air mineral", "nilai": str(air_dus), "satuan": "dus"},
        ]

        rincian = [
            {"nama": "Nasi kotak", "jumlah": kotak, "satuan": "kotak", "kelompok": "konsumsi"},
            {"nama": "Air mineral 600 ml", "jumlah": air_botol, "satuan": "botol", "kelompok": "minuman"},
            {"nama": "Air mineral dus (isi 24)", "jumlah": air_dus, "satuan": "dus", "kelompok": "minuman"},
        ]

        patokan = [
            "1 kotak nasi per porsi siap saji",
            "1 botol air mineral 600 ml per porsi (1 dus isi 24 botol)",
        ]

        h_porsi = parse_harga(harga_porsi, "Harga per kotak nasi")
        h_air = parse_harga(harga_air, "Harga air mineral per dus")

        biaya_items: list[dict[str, Any]] = []
        total_biaya = Decimal("0")

        if h_porsi is not None:
            sub_porsi = Decimal(str(kotak)) * Decimal(str(h_porsi))
            total_biaya += sub_porsi
            biaya_items.append({
                "nama": "Nasi kotak",
                "keterangan": f"{format_angka_id(kotak)} kotak x Rp {format_angka_id(h_porsi)}",
                "subtotal": int(sub_porsi),
            })

        if h_air is not None:
            sub_air = Decimal(str(air_dus)) * Decimal(str(h_air))
            total_biaya += sub_air
            biaya_items.append({
                "nama": "Air mineral dus",
                "keterangan": f"{format_angka_id(air_dus)} dus x Rp {format_angka_id(h_air)}",
                "subtotal": int(sub_air),
            })

        if biaya_items:
            per_tamu = int((total_biaya / Decimal(str(tamu_int))).to_integral_value(rounding=ROUND_HALF_UP))
            lengkap = (h_porsi is not None and h_air is not None)
            biaya: dict[str, Any] | None = {
                "total": int(total_biaya),
                "per_tamu": per_tamu,
                "lengkap": lengkap,
                "rincian": biaya_items,
            }
        else:
            biaya = None

        return {
            "mode": mode_norm,
            "tamu": tamu_int,
            "cadangan_persen": cadangan_int,
            "porsi": porsi,
            "ringkas": ringkas,
            "rincian": rincian,
            "biaya": biaya,
            "patokan": patokan,
            "catatan": catatan,
        }

    elif mode_norm == "snack":
        kotak = porsi

        ringkas = [
            {"label": "Porsi siap", "nilai": str(porsi), "satuan": "porsi"},
        ]

        rincian = [
            {"nama": "Snack box", "jumlah": kotak, "satuan": "kotak", "kelompok": "konsumsi"},
        ]

        patokan = [
            "1 kotak snack per porsi (berisi 2-3 kue dan air mineral kemasan)",
        ]

        h_porsi = parse_harga(harga_porsi, "Harga per kotak snack")

        if h_porsi is not None:
            sub = Decimal(str(kotak)) * Decimal(str(h_porsi))
            per_tamu = int((sub / Decimal(str(tamu_int))).to_integral_value(rounding=ROUND_HALF_UP))
            biaya = {
                "total": int(sub),
                "per_tamu": per_tamu,
                "lengkap": True,
                "rincian": [
                    {
                        "nama": "Snack box",
                        "keterangan": f"{format_angka_id(kotak)} kotak x Rp {format_angka_id(h_porsi)}",
                        "subtotal": int(sub),
                    }
                ],
            }
        else:
            biaya = None

        return {
            "mode": mode_norm,
            "tamu": tamu_int,
            "cadangan_persen": cadangan_int,
            "porsi": porsi,
            "ringkas": ringkas,
            "rincian": rincian,
            "biaya": biaya,
            "patokan": patokan,
            "catatan": catatan,
        }

    else:  # prasmanan
        lauk_jenis = parse_jenis_lauk(jenis_lauk)
        d_p = Decimal(str(porsi))

        beras_kg = float((d_p * Decimal("0.090")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        if lauk_jenis == "telur":
            lauk_jumlah: int | float = porsi
            lauk_satuan = "butir"
            lauk_nama = "Telur ayam"
            lauk_patokan = "Telur 1 butir per porsi"
        else:
            lauk_jumlah = float((d_p * Decimal("0.100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            lauk_satuan = "kg"
            label_map = {"ayam": "Daging ayam", "ikan": "Ikan", "daging": "Daging sapi"}
            lauk_nama = f"Lauk ({label_map.get(lauk_jenis, lauk_jenis.title())})"
            lauk_patokan = "Lauk hewani 100 gram per porsi"

        tahu_tempe_kg = float((d_p * Decimal("0.050")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        sayur_kg = float((d_p * Decimal("0.070")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        minyak_liter = float((d_p * Decimal("0.012")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        air_botol = math.ceil((porsi * 400) / 600)
        air_dus = math.ceil(air_botol / 24)

        piring = math.ceil(porsi * 1.2)
        gelas = math.ceil(porsi * 1.2)
        sendok = math.ceil(porsi * 1.2)

        ringkas = [
            {"label": "Porsi siap", "nilai": str(porsi), "satuan": "porsi"},
            {"label": "Air mineral", "nilai": str(air_dus), "satuan": "dus"},
            {"label": "Piring & sendok", "nilai": str(piring), "satuan": "set"},
        ]

        rincian = [
            {"nama": "Beras", "jumlah": beras_kg, "satuan": "kg", "kelompok": "bahan"},
            {"nama": lauk_nama, "jumlah": lauk_jumlah, "satuan": lauk_satuan, "kelompok": "bahan"},
            {"nama": "Tahu & tempe", "jumlah": tahu_tempe_kg, "satuan": "kg", "kelompok": "bahan"},
            {"nama": "Sayuran", "jumlah": sayur_kg, "satuan": "kg", "kelompok": "bahan"},
            {"nama": "Minyak goreng", "jumlah": minyak_liter, "satuan": "liter", "kelompok": "bahan"},
            {"nama": "Air mineral 600 ml", "jumlah": air_botol, "satuan": "botol", "kelompok": "bahan"},
            {"nama": "Air mineral dus (isi 24)", "jumlah": air_dus, "satuan": "dus", "kelompok": "bahan"},
            {"nama": "Piring", "jumlah": piring, "satuan": "buah", "kelompok": "perlengkapan"},
            {"nama": "Gelas", "jumlah": gelas, "satuan": "buah", "kelompok": "perlengkapan"},
            {"nama": "Sendok", "jumlah": sendok, "satuan": "buah", "kelompok": "perlengkapan"},
        ]

        patokan = [
            "Beras 90 gram per porsi",
            lauk_patokan,
            "Tahu/tempe 50 gram per porsi",
            "Sayur 70 gram per porsi",
            "Minyak goreng 12 ml per porsi",
            "Air minum 400 ml per porsi",
            "Piring 1,2 buah, gelas 1,2 buah, sendok 1,2 buah (dibulatkan ke atas)",
        ]

        h_beras = parse_harga(harga_beras, "Harga beras")
        h_lauk = parse_harga(harga_lauk, "Harga lauk")
        h_sayur = parse_harga(harga_sayur, "Harga sayur")
        h_tahu_tempe = parse_harga(harga_tahu_tempe, "Harga tahu/tempe")
        h_minyak = parse_harga(harga_minyak, "Harga minyak goreng")
        h_air = parse_harga(harga_air, "Harga air mineral")
        h_perlengkapan = parse_harga(harga_perlengkapan, "Harga perlengkapan")

        all_prices = [h_beras, h_lauk, h_sayur, h_tahu_tempe, h_minyak, h_air, h_perlengkapan]
        filled_count = sum(1 for p in all_prices if p is not None)

        if filled_count == 0:
            biaya = None
        else:
            biaya_items = []
            total_biaya = Decimal("0")

            if h_beras is not None:
                sub = (Decimal(str(beras_kg)) * Decimal(str(h_beras))).to_integral_value(rounding=ROUND_HALF_UP)
                total_biaya += sub
                biaya_items.append({
                    "nama": "Beras",
                    "keterangan": f"{format_angka_id(beras_kg)} kg x Rp {format_angka_id(h_beras)}",
                    "subtotal": int(sub),
                })

            if h_lauk is not None:
                sub = (Decimal(str(lauk_jumlah)) * Decimal(str(h_lauk))).to_integral_value(rounding=ROUND_HALF_UP)
                total_biaya += sub
                satuan_ket = "butir" if lauk_jenis == "telur" else "kg"
                biaya_items.append({
                    "nama": lauk_nama,
                    "keterangan": f"{format_angka_id(lauk_jumlah)} {satuan_ket} x Rp {format_angka_id(h_lauk)}",
                    "subtotal": int(sub),
                })

            if h_tahu_tempe is not None:
                sub = (Decimal(str(tahu_tempe_kg)) * Decimal(str(h_tahu_tempe))).to_integral_value(rounding=ROUND_HALF_UP)
                total_biaya += sub
                biaya_items.append({
                    "nama": "Tahu & tempe",
                    "keterangan": f"{format_angka_id(tahu_tempe_kg)} kg x Rp {format_angka_id(h_tahu_tempe)}",
                    "subtotal": int(sub),
                })

            if h_sayur is not None:
                sub = (Decimal(str(sayur_kg)) * Decimal(str(h_sayur))).to_integral_value(rounding=ROUND_HALF_UP)
                total_biaya += sub
                biaya_items.append({
                    "nama": "Sayuran",
                    "keterangan": f"{format_angka_id(sayur_kg)} kg x Rp {format_angka_id(h_sayur)}",
                    "subtotal": int(sub),
                })

            if h_minyak is not None:
                sub = (Decimal(str(minyak_liter)) * Decimal(str(h_minyak))).to_integral_value(rounding=ROUND_HALF_UP)
                total_biaya += sub
                biaya_items.append({
                    "nama": "Minyak goreng",
                    "keterangan": f"{format_angka_id(minyak_liter)} liter x Rp {format_angka_id(h_minyak)}",
                    "subtotal": int(sub),
                })

            if h_air is not None:
                sub = (Decimal(str(air_dus)) * Decimal(str(h_air))).to_integral_value(rounding=ROUND_HALF_UP)
                total_biaya += sub
                biaya_items.append({
                    "nama": "Air mineral dus",
                    "keterangan": f"{format_angka_id(air_dus)} dus x Rp {format_angka_id(h_air)}",
                    "subtotal": int(sub),
                })

            if h_perlengkapan is not None:
                sub = (Decimal(str(porsi)) * Decimal(str(h_perlengkapan))).to_integral_value(rounding=ROUND_HALF_UP)
                total_biaya += sub
                biaya_items.append({
                    "nama": "Perlengkapan makan",
                    "keterangan": f"{format_angka_id(porsi)} porsi x Rp {format_angka_id(h_perlengkapan)}",
                    "subtotal": int(sub),
                })

            per_tamu = int((total_biaya / Decimal(str(tamu_int))).to_integral_value(rounding=ROUND_HALF_UP))
            lengkap = (filled_count == 7)
            biaya = {
                "total": int(total_biaya),
                "per_tamu": per_tamu,
                "lengkap": lengkap,
                "rincian": biaya_items,
            }

        return {
            "mode": mode_norm,
            "tamu": tamu_int,
            "cadangan_persen": cadangan_int,
            "porsi": porsi,
            "ringkas": ringkas,
            "rincian": rincian,
            "biaya": biaya,
            "patokan": patokan,
            "catatan": catatan,
        }


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional, pilihan mode, jenis lauk, dan patokan porsi."""
    return {
        "modes": [
            {
                "value": "nasi_kotak",
                "label": "Nasi kotak",
                "deskripsi": "Pesan nasi kotak jadi + air mineral botol.",
            },
            {
                "value": "prasmanan",
                "label": "Prasmanan",
                "deskripsi": "Masak sendiri bahan mentah (beras, lauk, sayur, perlengkapan).",
            },
            {
                "value": "snack",
                "label": "Snack box",
                "deskripsi": "Kotak kue ringan untuk rapat atau pembuka acara.",
            },
        ],
        "jenis_lauk": [
            {"value": "ayam", "label": "Ayam (100 gram/porsi)"},
            {"value": "ikan", "label": "Ikan (100 gram/porsi)"},
            {"value": "daging", "label": "Daging sapi (100 gram/porsi)"},
            {"value": "telur", "label": "Telur (1 butir/porsi)"},
        ],
        "batas_angka": {
            "tamu": {"min": MIN_TAMU, "max": MAX_TAMU, "bawaan": DEFAULT_TAMU, "satuan": "orang"},
            "cadangan": {"min": MIN_CADANGAN, "max": MAX_CADANGAN, "bawaan": DEFAULT_CADANGAN, "satuan": "%"},
            "porsi_max": MAX_PORSI,
            "harga": {"min": MIN_HARGA, "max": MAX_HARGA, "satuan": "rupiah"},
        },
        "patokan": [
            "Beras 90 gram per porsi",
            "Lauk hewani 100 gram per porsi (atau telur 1 butir)",
            "Tahu/tempe 50 gram per porsi",
            "Sayur 70 gram per porsi",
            "Minyak goreng 12 ml per porsi",
            "Air minum 400 ml per porsi",
            "Piring 1,2 buah, gelas 1,2 buah, sendok 1,2 buah (dibulatkan ke atas)",
            "Nasi kotak & snack 1 kotak per porsi",
        ],
        "max_body_bytes": MAX_BODY_BYTES,
        "processed_on": "server",
    }
