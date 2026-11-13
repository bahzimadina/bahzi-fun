"""Kalkulator bagi tagihan patungan: bagi rata atau sesuai pesanan.

Hitung pembagian tagihan untuk makan bersama, arisan, atau patungan kado.
Mendukung dua mode:
1. rata: total tagihan dibagi sama rata ke sejumlah orang.
2. pesanan: tiap orang membayar pesanannya sendiri, pajak dan biaya layanan
   dialokasikan proporsional sesuai nominal pesanan, dan biaya tambahan dibagi rata.
Keduanya mendukung pajak, biaya layanan, biaya tambahan, dan pembulatan ke atas.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
import math
from typing import Any

# Batas operasional & konstanta
MAX_ORANG = 100
MIN_ORANG_RATA = 2
MAX_PESANAN = 100
NAMA_MAX = 40
NOMINAL_MIN = 0
NOMINAL_MAX = 1_000_000_000_000  # 1 triliun rupiah
PAJAK_MIN = 0
PAJAK_MAX = 100
LAYANAN_MIN = 0
LAYANAN_MAX = 100
MAX_TEKS_PESANAN = 20_000
PEMBULATAN_PILIHAN = ("tidak", "100", "500", "1000")

CATATAN = (
    "Hitungan ini perkiraan untuk memudahkan patungan, bukan struk resmi. "
    "Pajak dan biaya layanan dihitung dari subtotal, serta pembulatan ke atas "
    "bisa membuat total yang ditagih sedikit lebih besar dari total akhir struk."
)

# Kode galat stabil
INVALID_MODE = "INVALID_MODE"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
NO_TOTAL = "NO_TOTAL"
INVALID_TOTAL = "INVALID_TOTAL"
INVALID_ORANG = "INVALID_ORANG"
NO_PESANAN = "NO_PESANAN"
TOO_MANY_PESANAN = "TOO_MANY_PESANAN"
INVALID_PESANAN = "INVALID_PESANAN"
NAMA_TOO_LONG = "NAMA_TOO_LONG"
INVALID_PAJAK = "INVALID_PAJAK"
INVALID_LAYANAN = "INVALID_LAYANAN"
INVALID_TAMBAHAN = "INVALID_TAMBAHAN"
INVALID_PEMBULATAN = "INVALID_PEMBULATAN"
TEXT_TOO_LONG = "TEXT_TOO_LONG"


class PatunganError(ValueError):
    """Galat operasional kalkulator patungan dengan kode galat dan status HTTP."""

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
    """Mengembalikan batas operasional dan nilai konfigurasi bawaan."""
    return {
        "max_orang": MAX_ORANG,
        "min_orang_rata": MIN_ORANG_RATA,
        "max_pesanan": MAX_PESANAN,
        "nama_max": NAMA_MAX,
        "nominal_min": NOMINAL_MIN,
        "nominal_max": NOMINAL_MAX,
        "pajak_min": PAJAK_MIN,
        "pajak_max": PAJAK_MAX,
        "layanan_min": LAYANAN_MIN,
        "layanan_max": LAYANAN_MAX,
        "max_teks_pesanan": MAX_TEKS_PESANAN,
        "pembulatan_pilihan": list(PEMBULATAN_PILIHAN),
        "default": {
            "mode": "rata",
            "pajak": 0,
            "layanan": 0,
            "tambahan": 0,
            "pembulatan": "tidak",
        },
    }


def _parse_rupiah(val: Any) -> int | None:
    """Konversi nominal rupiah ke integer. Mendukung titik atau koma ribuan."""
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, (int, float, Decimal)):
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        try:
            d = Decimal(str(val))
            return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except Exception:
            return None
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        if s.lower().startswith("rp"):
            s = s[2:].strip()
        if not s:
            return None

        is_negative = False
        if s.startswith("-"):
            is_negative = True
            s = s[1:].strip()

        s = s.replace(" ", "")
        if not s:
            return None

        # Penanganan koma dan titik ribuan / desimal
        if "." in s and "," in s:
            last_dot = s.rfind(".")
            last_comma = s.rfind(",")
            if last_comma > last_dot:
                # 1.500.000,00 -> titik ribuan, koma desimal
                int_part = s[:last_comma].replace(".", "")
                dec_part = s[last_comma + 1 :]
                s_norm = f"{int_part}.{dec_part}"
            else:
                # 1,500,000.00 -> koma ribuan, titik desimal
                int_part = s[:last_dot].replace(",", "")
                dec_part = s[last_dot + 1 :]
                s_norm = f"{int_part}.{dec_part}"
        elif "." in s:
            parts = s.split(".")
            if len(parts) > 1 and all(len(p) == 3 and p.isdigit() for p in parts[1:]):
                s_norm = "".join(parts)
            elif len(parts) == 2 and len(parts[1]) in (1, 2) and parts[1].isdigit():
                s_norm = s
            else:
                try:
                    d = Decimal(s)
                    s_norm = str(d)
                except Exception:
                    return None
        elif "," in s:
            parts = s.split(",")
            if len(parts) > 1 and all(len(p) == 3 and p.isdigit() for p in parts[1:]):
                s_norm = "".join(parts)
            elif len(parts) == 2 and len(parts[1]) in (1, 2) and parts[1].isdigit():
                s_norm = f"{parts[0]}.{parts[1]}"
            else:
                try:
                    d = Decimal(s.replace(",", "."))
                    s_norm = str(d)
                except Exception:
                    return None
        else:
            s_norm = s

        try:
            d = Decimal(s_norm)
            if d.is_nan() or d.is_infinite():
                return None
            if is_negative:
                d = -d
            return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except Exception:
            return None
    return None


def _parse_persen(val: Any) -> Decimal | None:
    """Konversi nilai persentase ke Decimal (0..100)."""
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, (int, float, Decimal)):
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        try:
            return Decimal(str(val))
        except Exception:
            return None
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        if s.endswith("%"):
            s = s[:-1].strip()
        s = s.replace(" ", "").replace(",", ".")
        try:
            d = Decimal(s)
            if d.is_nan() or d.is_infinite():
                return None
            return d
        except Exception:
            return None
    return None


def _bulatkan_ke_atas(nilai: Decimal | float | int, pembulatan: str) -> int:
    """Membulatkan nominal ke atas sesuai pilihan kelipatan (tidak / 100 / 500 / 1000)."""
    d = Decimal(str(nilai))
    if pembulatan == "100":
        step = Decimal("100")
    elif pembulatan == "500":
        step = Decimal("500")
    elif pembulatan == "1000":
        step = Decimal("1000")
    else:
        step = Decimal("1")

    divided = d / step
    ke_atas = int(divided.to_integral_value(rounding=ROUND_CEILING) * step)
    if d > 0 and ke_atas == 0:
        ke_atas = int(step)
    return ke_atas


def hitung_patungan(
    mode: str | None = None,
    total: int | float | str | None = None,
    orang: int | float | str | None = None,
    pesanan: str | None = None,
    pajak: int | float | str | None = None,
    layanan: int | float | str | None = None,
    tambahan: int | float | str | None = None,
    pembulatan: str | None = None,
) -> dict[str, Any]:
    """Menghitung pembagian tagihan patungan baik secara rata maupun sesuai pesanan."""
    # 1. Validasi mode
    if mode is None or (isinstance(mode, str) and not mode.strip()):
        raise PatunganError(
            INVALID_MODE,
            "Pilih mode patungan: bagi rata atau sesuai pesanan.",
            400,
        )

    mode_str = str(mode).strip().lower()
    if mode_str not in ("rata", "pesanan"):
        raise PatunganError(
            UNSUPPORTED_MODE,
            "Mode patungan tidak didukung. Pilih 'rata' atau 'pesanan'.",
            400,
        )

    # 2. Validasi field opsional / umum (pajak, layanan, tambahan, pembulatan)
    if pajak is None or (isinstance(pajak, str) and not pajak.strip()):
        pajak_dec = Decimal("0")
    else:
        pajak_parsed = _parse_persen(pajak)
        if pajak_parsed is None or pajak_parsed < PAJAK_MIN or pajak_parsed > PAJAK_MAX:
            raise PatunganError(
                INVALID_PAJAK,
                "Pajak harus berupa persentase antara 0% dan 100%.",
                400,
            )
        pajak_dec = pajak_parsed

    if layanan is None or (isinstance(layanan, str) and not layanan.strip()):
        layanan_dec = Decimal("0")
    else:
        layanan_parsed = _parse_persen(layanan)
        if layanan_parsed is None or layanan_parsed < LAYANAN_MIN or layanan_parsed > LAYANAN_MAX:
            raise PatunganError(
                INVALID_LAYANAN,
                "Biaya layanan harus berupa persentase antara 0% dan 100%.",
                400,
            )
        layanan_dec = layanan_parsed

    if tambahan is None or (isinstance(tambahan, str) and not tambahan.strip()):
        tambahan_val = 0
    else:
        tambahan_parsed = _parse_rupiah(tambahan)
        if (
            tambahan_parsed is None
            or tambahan_parsed < NOMINAL_MIN
            or tambahan_parsed > NOMINAL_MAX
        ):
            raise PatunganError(
                INVALID_TAMBAHAN,
                "Biaya tambahan harus berupa nominal antara Rp0 dan Rp1.000.000.000.000.",
                400,
            )
        tambahan_val = tambahan_parsed

    if pembulatan is None or (isinstance(pembulatan, str) and not pembulatan.strip()):
        pembulatan_str = "tidak"
    else:
        pembulatan_str = str(pembulatan).strip().lower()
        if pembulatan_str not in PEMBULATAN_PILIHAN:
            raise PatunganError(
                INVALID_PEMBULATAN,
                "Pilihan pembulatan harus salah satu dari: tidak, 100, 500, atau 1000.",
                400,
            )

    # 3. Mode rata
    if mode_str == "rata":
        if total is None or (isinstance(total, str) and not total.strip()):
            raise PatunganError(
                NO_TOTAL,
                "Total tagihan harus diisi untuk mode bagi rata.",
                400,
            )

        total_val = _parse_rupiah(total)
        if total_val is None or total_val < NOMINAL_MIN or total_val > NOMINAL_MAX:
            raise PatunganError(
                INVALID_TOTAL,
                "Total tagihan harus berupa angka antara Rp0 dan Rp1.000.000.000.000.",
                400,
            )

        if orang is None or (isinstance(orang, str) and not str(orang).strip()):
            raise PatunganError(
                INVALID_ORANG,
                f"Jumlah orang untuk mode bagi rata harus antara {MIN_ORANG_RATA} dan {MAX_ORANG} orang.",
                400,
            )

        try:
            f_val = float(str(orang).strip().replace(",", "."))
            if not f_val.is_integer():
                raise ValueError
            orang_val = int(f_val)
        except Exception:
            raise PatunganError(
                INVALID_ORANG,
                f"Jumlah orang untuk mode bagi rata harus antara {MIN_ORANG_RATA} dan {MAX_ORANG} orang.",
                400,
            )

        if orang_val < MIN_ORANG_RATA or orang_val > MAX_ORANG:
            raise PatunganError(
                INVALID_ORANG,
                f"Jumlah orang untuk mode bagi rata harus antara {MIN_ORANG_RATA} dan {MAX_ORANG} orang.",
                400,
            )

        subtotal = total_val
        subtotal_dec = Decimal(subtotal)
        pajak_rp = int((subtotal_dec * pajak_dec / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        layanan_rp = int((subtotal_dec * layanan_dec / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        total_akhir = subtotal + pajak_rp + layanan_rp + tambahan_val

        bagian_tepat = Decimal(total_akhir) / Decimal(orang_val)
        per_orang = _bulatkan_ke_atas(bagian_tepat, pembulatan_str)
        total_ditagih = per_orang * orang_val
        kelebihan = total_ditagih - total_akhir

        return {
            "mode": "rata",
            "jumlah_orang": orang_val,
            "subtotal": float(subtotal),
            "pajak_persen": float(pajak_dec),
            "pajak_rp": float(pajak_rp),
            "layanan_persen": float(layanan_dec),
            "layanan_rp": float(layanan_rp),
            "tambahan": float(tambahan_val),
            "pembulatan": pembulatan_str,
            "total_akhir": float(total_akhir),
            "per_orang": float(per_orang),
            "orang": None,
            "total_ditagih": float(total_ditagih),
            "kelebihan": float(kelebihan),
            "catatan": CATATAN,
        }

    # 4. Mode pesanan
    pesanan_text = str(pesanan or "")
    if len(pesanan_text) > MAX_TEKS_PESANAN:
        raise PatunganError(
            TEXT_TOO_LONG,
            f"Teks pesanan terlalu panjang. Maksimal {MAX_TEKS_PESANAN:,} karakter.",
            413,
        )

    lines = pesanan_text.splitlines()
    parsed_orders: list[dict[str, Any]] = []
    baris_terisi = 0

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        baris_terisi += 1
        if baris_terisi > MAX_PESANAN:
            raise PatunganError(
                TOO_MANY_PESANAN,
                f"Maksimal {MAX_PESANAN} baris pesanan sekali hitung.",
                400,
            )

        nama_raw = ""
        nom_raw = ""

        if ":" in line:
            parts = line.split(":", 1)
            nama_raw = parts[0].strip()
            nom_raw = parts[1].strip()
        elif "," in line:
            cleaned = line.lower().replace("rp", "").replace(" ", "").replace(".", "").replace(",", "")
            if cleaned.isdigit():
                nama_raw = ""
                nom_raw = line
            else:
                parts = line.split(",", 1)
                nama_raw = parts[0].strip()
                nom_raw = parts[1].strip()
        else:
            nom_coba = _parse_rupiah(line)
            if nom_coba is not None:
                nama_raw = ""
                nom_raw = line
            else:
                nama_raw = line
                nom_raw = ""

        if not nom_raw:
            raise PatunganError(
                INVALID_PESANAN,
                f"Baris {line_no}: nominal pesanan tidak boleh kosong.",
                400,
            )

        nom_val = _parse_rupiah(nom_raw)
        if nom_val is None or nom_val < NOMINAL_MIN or nom_val > NOMINAL_MAX:
            raise PatunganError(
                INVALID_PESANAN,
                f"Baris {line_no}: nominal pesanan harus berupa angka antara Rp0 dan Rp1.000.000.000.000.",
                400,
            )

        if not nama_raw:
            nama = f"Orang {len(parsed_orders) + 1}"
        else:
            cleaned_name = " ".join(nama_raw.split())
            if len(cleaned_name) > NAMA_MAX:
                raise PatunganError(
                    NAMA_TOO_LONG,
                    f"Baris {line_no}: nama terlalu panjang (maksimal {NAMA_MAX} karakter).",
                    400,
                )
            nama = cleaned_name if cleaned_name else f"Orang {len(parsed_orders) + 1}"

        parsed_orders.append({"nama": nama, "pesanan": nom_val})

    if not parsed_orders:
        raise PatunganError(
            NO_PESANAN,
            "Daftar pesanan harus diisi untuk mode sesuai pesanan.",
            400,
        )

    subtotal = sum(item["pesanan"] for item in parsed_orders)
    if subtotal <= 0:
        raise PatunganError(
            INVALID_PESANAN,
            "Total nominal pesanan harus lebih besar dari Rp0.",
            400,
        )

    n_orang = len(parsed_orders)
    tambahan_base = tambahan_val // n_orang
    sisa_tambahan = tambahan_val % n_orang

    total_pajak_rp = 0
    total_layanan_rp = 0
    orang_hasil: list[dict[str, Any]] = []

    for idx, item in enumerate(parsed_orders):
        pesanan_dec = Decimal(item["pesanan"])
        p_rp = int((pesanan_dec * pajak_dec / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        l_rp = int((pesanan_dec * layanan_dec / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        t_rp = tambahan_base + (1 if idx < sisa_tambahan else 0)

        total_pajak_rp += p_rp
        total_layanan_rp += l_rp

        raw_total = item["pesanan"] + p_rp + l_rp + t_rp
        total_bayar = _bulatkan_ke_atas(raw_total, pembulatan_str)

        orang_hasil.append(
            {
                "nama": item["nama"],
                "pesanan": float(item["pesanan"]),
                "pajak_rp": float(p_rp),
                "layanan_rp": float(l_rp),
                "tambahan_rp": float(t_rp),
                "total": float(total_bayar),
            }
        )

    total_akhir = subtotal + total_pajak_rp + total_layanan_rp + tambahan_val
    total_ditagih = sum(int(item["total"]) for item in orang_hasil)
    kelebihan = total_ditagih - total_akhir

    return {
        "mode": "pesanan",
        "jumlah_orang": n_orang,
        "subtotal": float(subtotal),
        "pajak_persen": float(pajak_dec),
        "pajak_rp": float(total_pajak_rp),
        "layanan_persen": float(layanan_dec),
        "layanan_rp": float(total_layanan_rp),
        "tambahan": float(tambahan_val),
        "pembulatan": pembulatan_str,
        "total_akhir": float(total_akhir),
        "per_orang": None,
        "orang": orang_hasil,
        "total_ditagih": float(total_ditagih),
        "kelebihan": float(kelebihan),
        "catatan": CATATAN,
    }
