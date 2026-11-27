"""Hitung berat volumetrik paket kiriman: fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori.
PENTING: Jangan mencatat nama koli atau rincian data pengguna ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP, getcontext
import math
from typing import Any

# Presisi desimal tinggi untuk perhitungan volume dan pembagian
getcontext().prec = 28

# Batas operasional & konstanta
MAX_KOLI = 10
MIN_KOLI = 1
DIMENSI_MIN = Decimal("1")
DIMENSI_MAX = Decimal("300")
BERAT_MIN = Decimal("0.01")
BERAT_MAX = Decimal("1000")
TARIF_MIN = Decimal("0")
TARIF_MAX = Decimal("1000000")
MAX_BODY_BYTES = 65536  # 64 KB
NAMA_MAX_LEN = 40

PEMBAGI_PILIHAN = (6000, 5000, 4000)
PEMBULATAN_PILIHAN = (Decimal("0.1"), Decimal("0.5"), Decimal("1"))

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
KOLI_KOSONG = "KOLI_KOSONG"
TERLALU_BANYAK_KOLI = "TERLALU_BANYAK_KOLI"
DIMENSI_TIDAK_VALID = "DIMENSI_TIDAK_VALID"
BERAT_TIDAK_VALID = "BERAT_TIDAK_VALID"
PEMBAGI_TIDAK_DIKENAL = "PEMBAGI_TIDAK_DIKENAL"
PEMBULATAN_TIDAK_DIKENAL = "PEMBULATAN_TIDAK_DIKENAL"
TARIF_TIDAK_VALID = "TARIF_TIDAK_VALID"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"

CONTOH_PAYLOAD = {
    "pembagi": 6000,
    "pembulatan": 0.5,
    "tarif_per_kg": 18000,
    "koli": [
        {
            "nama": "Kardus 1",
            "panjang": 40,
            "lebar": 30,
            "tinggi": 25,
            "berat": 2.4,
        }
    ],
}


class VolumetrikError(ValueError):
    """Galat operasional alat hitung berat volumetrik paket."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat terstandar."""
        err = {"code": self.code, "message": self.message}
        return {
            "ok": False,
            "kode": self.code,
            "pesan": self.message,
            "error": err,
            "detail": err,
        }


def format_rupiah(nominal: Decimal | int | float) -> str:
    """Format angka ke rupiah gaya Indonesia (mis. Rp 18.000)."""
    n = int(Decimal(str(nominal)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    formatted = f"{n:,}".replace(",", ".")
    return f"Rp {formatted}"


def limits_payload() -> dict[str, Any]:
    """Batas operasional dan pilihan konfigurasi hitung berat volumetrik."""
    return {
        "maks_koli": MAX_KOLI,
        "dimensi_cm": {"min": int(DIMENSI_MIN), "max": int(DIMENSI_MAX)},
        "berat_kg": {"min": float(BERAT_MIN), "max": float(BERAT_MAX)},
        "pembagi": list(PEMBAGI_PILIHAN),
        "pembulatan": [float(p) if p % 1 != 0 else int(p) for p in PEMBULATAN_PILIHAN],
        "tarif_per_kg": {"min": int(TARIF_MIN), "max": int(TARIF_MAX)},
        "catatan_singkat": "Hitung berat volumetrik paket kiriman berdasarkan ukuran kardus vs berat timbangan.",
        "contoh": CONTOH_PAYLOAD,
    }


def _parse_pembagi(val: Any) -> int:
    """Validasi pembagi volumetrik (4000, 5000, atau 6000)."""
    if val is None or isinstance(val, bool):
        raise VolumetrikError(
            PEMBAGI_TIDAK_DIKENAL,
            "Pembagi volumetrik harus salah satu dari 4000, 5000, atau 6000.",
            400,
        )

    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            raise VolumetrikError(
                PEMBAGI_TIDAK_DIKENAL,
                "Pembagi volumetrik harus salah satu dari 4000, 5000, atau 6000.",
                400,
            )
        int_val = int(val)
        if int_val != val:
            raise VolumetrikError(
                PEMBAGI_TIDAK_DIKENAL,
                "Pembagi volumetrik harus salah satu dari 4000, 5000, atau 6000.",
                400,
            )
    elif isinstance(val, str):
        cleaned = val.strip().replace(".", "")
        try:
            int_val = int(cleaned)
        except Exception:
            raise VolumetrikError(
                PEMBAGI_TIDAK_DIKENAL,
                "Pembagi volumetrik harus salah satu dari 4000, 5000, atau 6000.",
                400,
            )
    else:
        raise VolumetrikError(
            PEMBAGI_TIDAK_DIKENAL,
            "Pembagi volumetrik harus salah satu dari 4000, 5000, atau 6000.",
            400,
        )

    if int_val not in PEMBAGI_PILIHAN:
        raise VolumetrikError(
            PEMBAGI_TIDAK_DIKENAL,
            "Pembagi volumetrik harus salah satu dari 4000, 5000, atau 6000.",
            400,
        )

    return int_val


def _parse_pembulatan(val: Any) -> Decimal:
    """Validasi kelipatan pembulatan berat (0.1, 0.5, atau 1 kg)."""
    if val is None or isinstance(val, bool):
        raise VolumetrikError(
            PEMBULATAN_TIDAK_DIKENAL,
            "Kelipatan pembulatan berat harus 0,1, 0,5, atau 1 kg.",
            400,
        )

    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            raise VolumetrikError(
                PEMBULATAN_TIDAK_DIKENAL,
                "Kelipatan pembulatan berat harus 0,1, 0,5, atau 1 kg.",
                400,
            )
        dec_val = Decimal(str(val))
    elif isinstance(val, str):
        cleaned = val.strip().replace(",", ".")
        try:
            dec_val = Decimal(cleaned)
        except Exception:
            raise VolumetrikError(
                PEMBULATAN_TIDAK_DIKENAL,
                "Kelipatan pembulatan berat harus 0,1, 0,5, atau 1 kg.",
                400,
            )
    elif isinstance(val, Decimal):
        dec_val = val
    else:
        raise VolumetrikError(
            PEMBULATAN_TIDAK_DIKENAL,
            "Kelipatan pembulatan berat harus 0,1, 0,5, atau 1 kg.",
            400,
        )

    matched = None
    for p in PEMBULATAN_PILIHAN:
        if dec_val == p:
            matched = p
            break

    if matched is None:
        raise VolumetrikError(
            PEMBULATAN_TIDAK_DIKENAL,
            "Kelipatan pembulatan berat harus 0,1, 0,5, atau 1 kg.",
            400,
        )

    return matched


def _parse_tarif(val: Any) -> Decimal | None:
    """Validasi dan parsing tarif per kg (opsional, 0..1.000.000)."""
    if val is None:
        return None

    if isinstance(val, bool):
        raise VolumetrikError(
            TARIF_TIDAK_VALID,
            "Tarif per kg harus berupa angka antara Rp 0 sampai Rp 1.000.000.",
            400,
        )

    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            raise VolumetrikError(
                TARIF_TIDAK_VALID,
                "Tarif per kg tidak valid.",
                400,
            )
        dec_val = Decimal(str(val))
    elif isinstance(val, str):
        cleaned = (
            val.strip()
            .replace(" ", "")
            .replace("Rp", "")
            .replace("rp", "")
            .replace(".", "")
            .replace(",", ".")
        )
        if not cleaned:
            return None
        try:
            dec_val = Decimal(cleaned)
        except Exception:
            raise VolumetrikError(
                TARIF_TIDAK_VALID,
                "Tarif per kg harus berupa angka antara Rp 0 sampai Rp 1.000.000.",
                400,
            )
    elif isinstance(val, Decimal):
        dec_val = val
    else:
        raise VolumetrikError(
            TARIF_TIDAK_VALID,
            "Tarif per kg harus berupa angka antara Rp 0 sampai Rp 1.000.000.",
            400,
        )

    if dec_val < TARIF_MIN or dec_val > TARIF_MAX:
        raise VolumetrikError(
            TARIF_TIDAK_VALID,
            f"Tarif per kg harus antara {format_rupiah(TARIF_MIN)} sampai {format_rupiah(TARIF_MAX)}.",
            400,
        )

    if dec_val == Decimal("0"):
        return None

    return dec_val


def _parse_dimensi(val: Any, field_name: str, koli_name: str) -> Decimal:
    """Validasi dan parsing ukuran dimensi kardus (1..300 cm)."""
    if val is None or isinstance(val, bool):
        raise VolumetrikError(
            DIMENSI_TIDAK_VALID,
            f"Dimensi {field_name} '{koli_name}' harus berupa angka antara 1 sampai 300 cm.",
            400,
        )

    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            raise VolumetrikError(
                DIMENSI_TIDAK_VALID,
                f"Dimensi {field_name} '{koli_name}' tidak valid.",
                400,
            )
        dec_val = Decimal(str(val))
    elif isinstance(val, str):
        cleaned = val.strip().replace(" ", "").replace("cm", "").replace(",", ".")
        if not cleaned:
            raise VolumetrikError(
                DIMENSI_TIDAK_VALID,
                f"Dimensi {field_name} '{koli_name}' tidak boleh kosong.",
                400,
            )
        try:
            dec_val = Decimal(cleaned)
        except Exception:
            raise VolumetrikError(
                DIMENSI_TIDAK_VALID,
                f"Dimensi {field_name} '{koli_name}' harus berupa angka antara 1 sampai 300 cm.",
                400,
            )
    elif isinstance(val, Decimal):
        dec_val = val
    else:
        raise VolumetrikError(
            DIMENSI_TIDAK_VALID,
            f"Dimensi {field_name} '{koli_name}' harus berupa angka antara 1 sampai 300 cm.",
            400,
        )

    if dec_val < DIMENSI_MIN or dec_val > DIMENSI_MAX:
        raise VolumetrikError(
            DIMENSI_TIDAK_VALID,
            f"Dimensi {field_name} '{koli_name}' harus antara 1 sampai 300 cm.",
            400,
        )

    return dec_val


def _parse_berat(val: Any, koli_name: str) -> Decimal:
    """Validasi dan parsing berat timbangan koli (0.01..1000 kg)."""
    if val is None or isinstance(val, bool):
        raise VolumetrikError(
            BERAT_TIDAK_VALID,
            f"Berat aktual '{koli_name}' harus berupa angka antara 0,01 sampai 1.000 kg.",
            400,
        )

    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            raise VolumetrikError(
                BERAT_TIDAK_VALID,
                f"Berat aktual '{koli_name}' tidak valid.",
                400,
            )
        dec_val = Decimal(str(val))
    elif isinstance(val, str):
        cleaned = val.strip().replace(" ", "").replace("kg", "").replace(",", ".")
        if not cleaned:
            raise VolumetrikError(
                BERAT_TIDAK_VALID,
                f"Berat aktual '{koli_name}' tidak boleh kosong.",
                400,
            )
        try:
            dec_val = Decimal(cleaned)
        except Exception:
            raise VolumetrikError(
                BERAT_TIDAK_VALID,
                f"Berat aktual '{koli_name}' harus berupa angka antara 0,01 sampai 1.000 kg.",
                400,
            )
    elif isinstance(val, Decimal):
        dec_val = val
    else:
        raise VolumetrikError(
            BERAT_TIDAK_VALID,
            f"Berat aktual '{koli_name}' harus berupa angka antara 0,01 sampai 1.000 kg.",
            400,
        )

    if dec_val < BERAT_MIN or dec_val > BERAT_MAX:
        raise VolumetrikError(
            BERAT_TIDAK_VALID,
            f"Berat aktual '{koli_name}' harus antara 0,01 sampai 1.000 kg.",
            400,
        )

    return dec_val


def _parse_nama_koli(val: Any, index: int) -> str:
    """Validasi dan penataan nama kardus / koli."""
    fallback = f"Kardus {index + 1}"
    if val is None:
        return fallback

    if not isinstance(val, str):
        raise VolumetrikError(
            INVALID_REQUEST,
            f"Nama koli ke-{index + 1} harus berupa teks.",
            400,
        )

    s = val.strip()
    if not s:
        return fallback

    if any(ord(c) < 32 for c in s):
        raise VolumetrikError(
            INVALID_REQUEST,
            f"Nama koli ke-{index + 1} tidak boleh mengandung karakter kontrol.",
            400,
        )

    if len(s) > NAMA_MAX_LEN:
        s = s[:NAMA_MAX_LEN]

    return s


def hitung_volumetrik(payload: Any) -> dict[str, Any]:
    """Hitung perbandingan berat volumetrik vs timbangan koli ekspedisi."""
    if not isinstance(payload, dict):
        raise VolumetrikError(
            INVALID_REQUEST,
            "Permintaan harus berupa objek JSON.",
            400,
        )

    pembagi = _parse_pembagi(payload.get("pembagi", 6000))
    pembulatan = _parse_pembulatan(payload.get("pembulatan", Decimal("0.5")))
    tarif_per_kg = _parse_tarif(payload.get("tarif_per_kg"))

    koli_raw = payload.get("koli")
    if koli_raw is None or not isinstance(koli_raw, list):
        raise VolumetrikError(
            INVALID_REQUEST,
            "Daftar koli harus berupa array.",
            400,
        )

    if len(koli_raw) == 0:
        raise VolumetrikError(
            KOLI_KOSONG,
            "Daftar koli tidak boleh kosong.",
            400,
        )

    if len(koli_raw) > MAX_KOLI:
        raise VolumetrikError(
            TERLALU_BANYAK_KOLI,
            f"Jumlah koli maksimal {MAX_KOLI} buah.",
            400,
        )

    pembagi_dec = Decimal(str(pembagi))
    koli_hasil = []
    total_volume_cm3 = Decimal("0")
    total_berat = Decimal("0")
    saran_koli_list = []

    for idx, item in enumerate(koli_raw):
        if not isinstance(item, dict):
            raise VolumetrikError(
                INVALID_REQUEST,
                f"Data koli ke-{idx + 1} harus berupa objek.",
                400,
            )

        nama = _parse_nama_koli(item.get("nama"), idx)
        panjang = _parse_dimensi(item.get("panjang"), "panjang", nama)
        lebar = _parse_dimensi(item.get("lebar"), "lebar", nama)
        tinggi = _parse_dimensi(item.get("tinggi"), "tinggi", nama)
        berat_aktual = _parse_berat(item.get("berat"), nama)

        volume_cm3 = panjang * lebar * tinggi
        berat_volumetrik = volume_cm3 / pembagi_dec

        if berat_volumetrik > berat_aktual:
            berat_dasar = "volumetrik"
            berat_terpakai = berat_volumetrik
        else:
            berat_dasar = "aktual"
            berat_terpakai = berat_aktual

        # Pembulatan KE ATAS ke kelipatan pembulatan (ROUND_CEILING)
        berat_dibulatkan = (
            berat_terpakai / pembulatan
        ).to_integral_value(rounding=ROUND_CEILING) * pembulatan

        selisih_kg = berat_dibulatkan - berat_aktual
        selisih_persen = (selisih_kg / berat_aktual * Decimal("100")).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )

        total_volume_cm3 += volume_cm3
        total_berat += berat_dibulatkan

        berat_volumetrik_tampil = berat_volumetrik.quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )
        berat_terpakai_tampil = berat_terpakai.quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )

        # Saran koli jika berat_dasar volumetrik dan selisih_persen > 15
        if berat_dasar == "volumetrik" and selisih_persen > Decimal("15"):
            koli_label = nama if nama.lower().startswith("kardus") else f"Kardus {nama}"
            saran_koli_list.append(
                f"{koli_label} lebih ringan dari ukurannya. Kurangi ruang kosong atau pakai kardus yang lebih pas supaya ongkir tidak dihitung dari volume."
            )

        koli_hasil.append({
            "nama": nama,
            "panjang": float(panjang) if panjang % 1 != 0 else int(panjang),
            "lebar": float(lebar) if lebar % 1 != 0 else int(lebar),
            "tinggi": float(tinggi) if tinggi % 1 != 0 else int(tinggi),
            "volume_cm3": int(volume_cm3),
            "berat_aktual": float(berat_aktual) if berat_aktual % 1 != 0 else int(berat_aktual),
            "berat_volumetrik": float(berat_volumetrik_tampil),
            "berat_terpakai": float(berat_terpakai_tampil),
            "berat_dibulatkan": float(berat_dibulatkan) if berat_dibulatkan % 1 != 0 else int(berat_dibulatkan),
            "berat_dasar": berat_dasar,
            "selisih_kg": float(selisih_kg.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)),
            "selisih_persen": float(selisih_persen),
        })

    if tarif_per_kg is not None and tarif_per_kg > Decimal("0"):
        total_ongkir = int(
            (total_berat * tarif_per_kg).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        tarif_out = int(tarif_per_kg)
    else:
        total_ongkir = None
        tarif_out = None

    # Susun saran
    saran = []
    # (a) bila ada koli yang berat_dasar "volumetrik" dan selisih_persen > 15
    saran.extend(saran_koli_list)

    # (b) bila tarif kosong
    if total_ongkir is None:
        saran.append("Isi tarif per kg untuk melihat perkiraan ongkir.")

    # (c) selalu
    saran.append(
        "Pembagi, aturan pembulatan, dan tarif berbeda tiap ekspedisi serta bisa berubah sewaktu-waktu, jadi angka ini adalah perkiraan."
    )

    pembulatan_num = float(pembulatan) if pembulatan % 1 != 0 else int(pembulatan)
    total_berat_num = float(total_berat) if total_berat % 1 != 0 else int(total_berat)

    ringkasan = {
        "total_koli": len(koli_hasil),
        "total_volume_cm3": int(total_volume_cm3),
        "total_berat": total_berat_num,
        "total_ongkir": total_ongkir,
        "pembagi": pembagi,
        "pembulatan": pembulatan_num,
        "tarif_per_kg": tarif_out,
    }

    return {
        "total_berat": total_berat_num,
        "total_volume_cm3": int(total_volume_cm3),
        "total_ongkir": total_ongkir,
        "pembagi": pembagi,
        "pembulatan": pembulatan_num,
        "tarif_per_kg": tarif_out,
        "ringkasan": ringkasan,
        "koli": koli_hasil,
        "saran": saran,
    }
