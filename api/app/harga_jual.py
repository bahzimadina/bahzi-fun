"""Logika kalkulator hitung harga jual: fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import re
from typing import Any

# Batas operasional
MIN_MODAL = 1
MAX_MODAL = 1_000_000_000

MIN_BIAYA = 0
MAX_BIAYA = 1_000_000_000

MIN_POTONGAN = 0
MAX_POTONGAN = 40

MIN_TARGET_MARGIN = 0
MAX_TARGET_MARGIN = 95

MIN_TARGET_MARKUP = 0
MAX_TARGET_MARKUP = 1000

PILIHAN_PEMBULATAN = (0, 100, 500, 1000)
DEFAULT_PEMBULATAN = 100

MAX_INPUT_LENGTH = 40

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
INVALID_NUMBER = "INVALID_NUMBER"
INVALID_MODAL = "INVALID_MODAL"
INVALID_BIAYA = "INVALID_BIAYA"
INVALID_PLATFORM = "INVALID_PLATFORM"
INVALID_TARGET = "INVALID_TARGET"
INVALID_PEMBULATAN = "INVALID_PEMBULATAN"
TARGET_TOO_HIGH = "TARGET_TOO_HIGH"


class HargaJualError(ValueError):
    """Galat operasional kalkulator harga jual dengan kode galat dan status HTTP."""

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


def _ceil_kelipatan(nilai: Decimal, step_int: int) -> int:
    """Membulatkan nilai desimal ke atas ke kelipatan step_int.

    Jika step_int == 0, dibulatkan ke atas ke rupiah penuh (kelipatan 1).
    """
    step = Decimal(step_int) if step_int > 0 else Decimal(1)
    ratio = (nilai / step).to_integral_value(rounding=ROUND_CEILING)
    return int(ratio * step)


def parse_rupiah(
    val: Any,
    field_name: str,
    err_code: str,
    min_val: int,
    max_val: int,
    default: Decimal | None = None,
) -> Decimal:
    """Validasi dan parsing angka rupiah.

    Pemisah ribuan (titik dan spasi) dibuang, koma diperlakukan sebagai pemisah desimal.
    """
    if val is None:
        if default is not None:
            return default
        raise HargaJualError(err_code, f"Field '{field_name}' wajib diisi.", 400)

    if isinstance(val, (int, float, Decimal)):
        s = str(val).strip()
    elif isinstance(val, str):
        s = val.strip()
    else:
        raise HargaJualError(err_code, f"Field '{field_name}' harus berupa string atau angka.", 400)

    if not s:
        if default is not None:
            return default
        raise HargaJualError(err_code, f"Field '{field_name}' tidak boleh kosong.", 400)

    if len(s) > MAX_INPUT_LENGTH:
        raise HargaJualError(INVALID_NUMBER, f"Masukan '{field_name}' melebihi batas 40 karakter.", 400)

    # Buang titik dan spasi pemisah ribuan
    s_clean = s.replace(".", "").replace(" ", "")
    # Koma adalah tanda desimal
    s_clean = s_clean.replace(",", ".")

    if s_clean.count(".") > 1 or not re.fullmatch(r"^\d+(\.\d+)?$", s_clean):
        raise HargaJualError(
            err_code,
            f"Nilai '{field_name}' harus berupa angka rupiah positif yang valid.",
            400,
        )

    try:
        num = Decimal(s_clean)
    except Exception:
        raise HargaJualError(err_code, f"Nilai '{field_name}' tidak dapat dibaca sebagai angka.", 400)

    d_min = Decimal(min_val)
    d_max = Decimal(max_val)
    if num < d_min or num > d_max:
        raise HargaJualError(
            err_code,
            f"Nilai '{field_name}' harus bernilai antara Rp {min_val:,} hingga Rp {max_val:,}.".replace(",", "."),
            400,
        )

    return num


def parse_persen(
    val: Any,
    field_name: str,
    err_code: str,
    min_val: int,
    max_val: int,
    default: Decimal | None = None,
) -> Decimal:
    """Validasi dan parsing angka persentase.

    Koma atau titik diterima sebagai tanda desimal.
    """
    if val is None:
        if default is not None:
            return default
        raise HargaJualError(err_code, f"Field '{field_name}' wajib diisi.", 400)

    if isinstance(val, (int, float, Decimal)):
        s = str(val).strip()
    elif isinstance(val, str):
        s = val.strip()
    else:
        raise HargaJualError(err_code, f"Field '{field_name}' harus berupa string atau angka.", 400)

    if not s:
        if default is not None:
            return default
        raise HargaJualError(err_code, f"Field '{field_name}' tidak boleh kosong.", 400)

    if len(s) > MAX_INPUT_LENGTH:
        raise HargaJualError(INVALID_NUMBER, f"Masukan '{field_name}' melebihi batas 40 karakter.", 400)

    s_clean = s.replace(" ", "").replace(",", ".")

    if s_clean.count(".") > 1 or not re.fullmatch(r"^\d+(\.\d+)?$", s_clean):
        raise HargaJualError(
            err_code,
            f"Nilai '{field_name}' harus berupa angka persentase positif yang valid.",
            400,
        )

    try:
        num = Decimal(s_clean)
    except Exception:
        raise HargaJualError(err_code, f"Nilai '{field_name}' tidak dapat dibaca sebagai angka.", 400)

    d_min = Decimal(min_val)
    d_max = Decimal(max_val)
    if num < d_min or num > d_max:
        raise HargaJualError(
            err_code,
            f"Nilai '{field_name}' harus bernilai antara {min_val}% hingga {max_val}%.",
            400,
        )

    return num


def parse_pembulatan(val: Any) -> int:
    """Validasi dan parsing pilihan pembulatan (0, 100, 500, 1000)."""
    if val is None:
        return DEFAULT_PEMBULATAN

    if isinstance(val, int) and val in PILIHAN_PEMBULATAN:
        return val

    s = str(val).strip()
    if not s:
        return DEFAULT_PEMBULATAN

    if len(s) > MAX_INPUT_LENGTH:
        raise HargaJualError(INVALID_NUMBER, "Masukan 'pembulatan' melebihi batas 40 karakter.", 400)

    try:
        num = int(s)
    except ValueError:
        raise HargaJualError(
            INVALID_PEMBULATAN,
            "Pilihan pembulatan tidak valid. Pilih 0, 100, 500, atau 1000.",
            400,
        )

    if num not in PILIHAN_PEMBULATAN:
        raise HargaJualError(
            INVALID_PEMBULATAN,
            "Pilihan pembulatan tidak valid. Pilih 0, 100, 500, atau 1000.",
            400,
        )

    return num


def hitung_harga_jual(
    mode: Any,
    modal: Any,
    biaya_tambahan: Any = None,
    potongan_platform: Any = None,
    target: Any = None,
    pembulatan: Any = None,
) -> dict[str, Any]:
    """Hitung harga jual, laba per unit, dan skenario target murni di memori."""
    if mode is None:
        raise HargaJualError(INVALID_REQUEST, "Field 'mode' wajib diisi.", 400)

    if not isinstance(mode, str) and not isinstance(mode, (int, float)):
        raise HargaJualError(INVALID_REQUEST, "Field 'mode' harus berupa string.", 400)

    s_mode = str(mode).strip()
    if not s_mode:
        raise HargaJualError(INVALID_REQUEST, "Field 'mode' wajib diisi.", 400)

    if len(s_mode) > MAX_INPUT_LENGTH:
        raise HargaJualError(INVALID_NUMBER, "Masukan 'mode' melebihi batas 40 karakter.", 400)

    mode_norm = s_mode.lower()
    if mode_norm not in ("margin", "markup"):
        raise HargaJualError(
            UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak didukung. Pilih 'margin' atau 'markup'.",
            400,
        )

    # Parsing modal & biaya tambahan
    d_modal = parse_rupiah(modal, "modal", INVALID_MODAL, MIN_MODAL, MAX_MODAL)
    d_biaya = parse_rupiah(biaya_tambahan, "biaya_tambahan", INVALID_BIAYA, MIN_BIAYA, MAX_BIAYA, default=Decimal("0"))

    # Parsing potongan platform
    d_potongan = parse_persen(
        potongan_platform,
        "potongan_platform",
        INVALID_PLATFORM,
        MIN_POTONGAN,
        MAX_POTONGAN,
        default=Decimal("0"),
    )

    # Parsing target laba
    if mode_norm == "margin":
        d_target = parse_persen(target, "target", INVALID_TARGET, MIN_TARGET_MARGIN, MAX_TARGET_MARGIN)
        if (d_potongan + d_target) >= Decimal("100"):
            raise HargaJualError(
                TARGET_TOO_HIGH,
                "Target laba ditambah potongan marketplace harus di bawah 100%. Turunkan salah satunya.",
                400,
            )
    else:
        d_target = parse_persen(target, "target", INVALID_TARGET, MIN_TARGET_MARKUP, MAX_TARGET_MARKUP)

    # Parsing pembulatan
    pembulatan_int = parse_pembulatan(pembulatan)

    # Total modal + biaya operasional
    total_modal_biaya = d_modal + d_biaya

    # Hitung harga sebelum pembulatan
    if mode_norm == "margin":
        denom = Decimal("1") - (d_potongan / Decimal("100")) - (d_target / Decimal("100"))
        d_harga_sebelum = total_modal_biaya / denom
    else:
        denom = Decimal("1") - (d_potongan / Decimal("100"))
        d_harga_sebelum = total_modal_biaya * (Decimal("1") + (d_target / Decimal("100"))) / denom

    # Pembulatan ke atas
    harga_jual = _ceil_kelipatan(d_harga_sebelum, pembulatan_int)
    harga_sebelum_pembulatan = float(d_harga_sebelum.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    # Potongan marketplace rupiah
    d_potongan_rp = (Decimal(harga_jual) * d_potongan / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    potongan_platform_rp = int(d_potongan_rp)

    modal_int = int(d_modal.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    biaya_int = int(d_biaya.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    total_modal_biaya_int = modal_int + biaya_int
    total_biaya = total_modal_biaya_int + potongan_platform_rp

    laba_per_unit = harga_jual - total_biaya
    laba_persen = round((float(laba_per_unit) / float(harga_jual)) * 100.0, 2)
    markup_persen = round((float(laba_per_unit) / float(total_modal_biaya)) * 100.0, 2)
    harga_titik_balik = total_modal_biaya_int

    rincian = {
        "modal": modal_int,
        "biaya_tambahan": biaya_int,
        "potongan_platform": potongan_platform_rp,
        "total_biaya": total_biaya,
    }

    # Tabel skenario untuk target 10, 20, 30, 40, 50
    skenario: list[dict[str, Any]] = []
    target_skenario = [10, 20, 30, 40, 50]
    for t in target_skenario:
        d_t = Decimal(t)
        if mode_norm == "margin":
            if (d_potongan + d_t) >= Decimal("100") or d_t > Decimal(MAX_TARGET_MARGIN):
                continue
            s_denom = Decimal("1") - (d_potongan / Decimal("100")) - (d_t / Decimal("100"))
            s_harga_sebelum = total_modal_biaya / s_denom
        else:
            s_denom = Decimal("1") - (d_potongan / Decimal("100"))
            s_harga_sebelum = total_modal_biaya * (Decimal("1") + (d_t / Decimal("100"))) / s_denom

        s_harga_jual = _ceil_kelipatan(s_harga_sebelum, pembulatan_int)
        s_potongan_rp = int((Decimal(s_harga_jual) * d_potongan / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        s_total_biaya = total_modal_biaya_int + s_potongan_rp
        s_laba_unit = s_harga_jual - s_total_biaya
        s_laba_persen = round((float(s_laba_unit) / float(s_harga_jual)) * 100.0, 2)

        skenario.append({
            "target": t,
            "harga_jual": s_harga_jual,
            "laba_per_unit": s_laba_unit,
            "laba_persen": s_laba_persen,
        })

    catatan = [
        "Perhitungan ini belum memperhitungkan pajak (PPN/PPh), biaya iklan berbayar, dan risiko retur atau barang rusak.",
        "Potongan marketplace dihitung dari harga jual akhir ke pembeli.",
        "Jika ada biaya operasional lain atau promo diskon toko, masukkan ke biaya tambahan per unit.",
    ]

    return {
        "mode": mode_norm,
        "harga_jual": harga_jual,
        "harga_sebelum_pembulatan": harga_sebelum_pembulatan,
        "laba_per_unit": laba_per_unit,
        "laba_persen": laba_persen,
        "markup_persen": markup_persen,
        "harga_titik_balik": harga_titik_balik,
        "pembulatan": pembulatan_int,
        "rincian": rincian,
        "skenario": skenario,
        "catatan": catatan,
    }


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional dan pilihan kalkulator harga jual."""
    return {
        "modes": [
            {"value": "margin", "label": "Target laba dari harga jual (margin)"},
            {"value": "markup", "label": "Target laba dari modal (markup)"},
        ],
        "batas": {
            "modal": {"min": MIN_MODAL, "max": MAX_MODAL, "satuan": "rupiah"},
            "biaya_tambahan": {"min": MIN_BIAYA, "max": MAX_BIAYA, "bawaan": 0, "satuan": "rupiah"},
            "potongan_platform": {"min": MIN_POTONGAN, "max": MAX_POTONGAN, "bawaan": 0, "satuan": "%"},
            "target": {
                "margin": {"min": MIN_TARGET_MARGIN, "max": MAX_TARGET_MARGIN, "bawaan": 20, "satuan": "%"},
                "markup": {"min": MIN_TARGET_MARKUP, "max": MAX_TARGET_MARKUP, "bawaan": 20, "satuan": "%"},
            },
        },
        "pilihan_pembulatan": [
            {"value": 0, "label": "Tanpa pembulatan (rupiah penuh)"},
            {"value": 100, "label": "Ratusan (100)"},
            {"value": 500, "label": "Lima ratusan (500)"},
            {"value": 1000, "label": "Ribuan (1.000)"},
        ],
        "contoh": {
            "mode": "margin",
            "modal": 75000,
            "biaya_tambahan": 12500,
            "potongan_platform": 10,
            "target": 20,
            "pembulatan": 500,
        },
        "processed_on": "server",
        "note": "Perhitungan dilakukan di memori, nilai masukan tidak pernah disimpan ke disk atau dicatat ke log.",
    }
