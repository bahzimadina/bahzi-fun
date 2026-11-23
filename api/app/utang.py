"""Simulasi pelunasan utang (avalanche vs snowball): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori.
PENTING: Jangan mencatat nama utang atau nominal uang pengguna ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, getcontext
import math
import re
from typing import Any

# Presisi desimal tinggi untuk perhitungan tenor panjang
getcontext().prec = 28

# Batas operasional & konstanta
MIN_UTANG_ITEMS = 1
MAX_UTANG_ITEMS = 8
NAMA_MAX_LEN = 40

SISA_MIN = Decimal("1000")
SISA_MAX = Decimal("1000000000000")  # Rp 1 triliun
BUNGA_MIN = Decimal("0")
BUNGA_MAX = Decimal("100")
MINIMUM_MIN = Decimal("1000")
DANA_MIN = Decimal("1000")

MAX_BULAN = 600  # 50 tahun
MAX_BODY_BYTES = 32768  # 32 KB

# Kode galat stabil
UTANG_JUMLAH = "UTANG_JUMLAH"
SISA_TIDAK_VALID = "SISA_TIDAK_VALID"
BUNGA_TIDAK_VALID = "BUNGA_TIDAK_VALID"
MINIMUM_TIDAK_VALID = "MINIMUM_TIDAK_VALID"
DANA_TIDAK_VALID = "DANA_TIDAK_VALID"
STRATEGI_TIDAK_VALID = "STRATEGI_TIDAK_VALID"
DANA_KURANG = "DANA_KURANG"
TERLALU_LAMA = "TERLALU_LAMA"
INVALID_REQUEST = "INVALID_REQUEST"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
NAMA_TIDAK_VALID = "NAMA_TIDAK_VALID"

STRATEGI_PILIHAN = ("bunga", "saldo")
STRATEGI_LABEL = {
    "bunga": "Bunga tertinggi dulu",
    "saldo": "Saldo terkecil dulu",
}

CONTOH_PAYLOAD = {
    "dana_bulanan": 2500000,
    "strategi": "bunga",
    "utang": [
        {
            "nama": "Kartu kredit",
            "sisa": 12000000,
            "bunga": 24,
            "minimum": 600000,
        },
        {
            "nama": "Paylater",
            "sisa": 3500000,
            "bunga": 36,
            "minimum": 350000,
        },
        {
            "nama": "Pinjaman bank",
            "sisa": 25000000,
            "bunga": 14,
            "minimum": 900000,
        },
    ],
}


class UtangError(ValueError):
    """Galat operasional alat simulasi pelunasan utang dengan kode galat dan status HTTP."""

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
    """Format angka ke rupiah gaya Indonesia (mis. Rp 2.500.000)."""
    n = int(Decimal(str(nominal)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    formatted = f"{n:,}".replace(",", ".")
    return f"Rp {formatted}"


def limits_payload() -> dict[str, Any]:
    """Mengembalikan batas operasional dan pilihan strategi pelunasan utang."""
    return {
        "maks_utang": MAX_UTANG_ITEMS,
        "batas": {
            "sisa": {"min": int(SISA_MIN), "max": int(SISA_MAX)},
            "bunga": {"min": int(BUNGA_MIN), "max": int(BUNGA_MAX)},
            "minimum": {"min": int(MINIMUM_MIN)},
            "dana_bulanan": {"min": int(DANA_MIN)},
            "maks_bulan": MAX_BULAN,
            "nama_max_length": NAMA_MAX_LEN,
        },
        "strategi": [
            {"nilai": "bunga", "label": STRATEGI_LABEL["bunga"]},
            {"nilai": "saldo", "label": STRATEGI_LABEL["saldo"]},
        ],
        "contoh": CONTOH_PAYLOAD,
    }


def _parse_rupiah_value(
    val: Any,
    nama_field: str,
    err_code: str,
    min_val: Decimal = SISA_MIN,
    max_val: Decimal | None = None,
) -> Decimal:
    """Validasi dan parsing nilai rupiah. Menolak boolean, non-angka, dan rentang di luar batas."""
    if val is None or isinstance(val, bool):
        raise UtangError(err_code, f"{nama_field} harus berupa angka.", 400)

    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            raise UtangError(err_code, f"{nama_field} tidak valid.", 400)
        num = Decimal(str(val))
    elif isinstance(val, str):
        s = val.strip().replace(" ", "").replace("Rp", "").replace("rp", "")
        if not s:
            raise UtangError(err_code, f"{nama_field} tidak boleh kosong.", 400)
        # Deteksi tanda minus
        if s.startswith("-"):
            raise UtangError(
                err_code,
                f"{nama_field} harus minimal {format_rupiah(min_val)}.",
                400,
            )
        # Bersihkan titik pemisah ribuan
        s_clean = s.replace(".", "").replace(",", ".")
        try:
            num = Decimal(s_clean)
        except Exception:
            raise UtangError(err_code, f"{nama_field} harus berupa angka.", 400)
    else:
        raise UtangError(err_code, f"{nama_field} harus berupa angka.", 400)

    if num < min_val:
        raise UtangError(
            err_code,
            f"{nama_field} harus minimal {format_rupiah(min_val)}.",
            400,
        )

    if max_val is not None and num > max_val:
        raise UtangError(
            err_code,
            f"{nama_field} maksimal {format_rupiah(max_val)}.",
            400,
        )

    return num


def _parse_bunga_value(val: Any, nama_utang: str) -> Decimal:
    """Validasi dan parsing suku bunga tahunan (0..100%)."""
    if val is None or isinstance(val, bool):
        raise UtangError(
            BUNGA_TIDAK_VALID,
            f"Suku bunga tahunan '{nama_utang}' harus berupa angka antara 0% sampai 100%.",
            400,
        )

    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            raise UtangError(
                BUNGA_TIDAK_VALID,
                f"Suku bunga tahunan '{nama_utang}' tidak valid.",
                400,
            )
        bunga = Decimal(str(val))
    elif isinstance(val, str):
        s = val.strip().replace(" ", "").rstrip("%").replace(",", ".")
        if not s:
            raise UtangError(
                BUNGA_TIDAK_VALID,
                f"Suku bunga tahunan '{nama_utang}' tidak boleh kosong.",
                400,
            )
        try:
            bunga = Decimal(s)
        except Exception:
            raise UtangError(
                BUNGA_TIDAK_VALID,
                f"Suku bunga tahunan '{nama_utang}' harus berupa angka antara 0% sampai 100%.",
                400,
            )
    else:
        raise UtangError(
            BUNGA_TIDAK_VALID,
            f"Suku bunga tahunan '{nama_utang}' harus berupa angka antara 0% sampai 100%.",
            400,
        )

    if bunga < BUNGA_MIN or bunga > BUNGA_MAX:
        raise UtangError(
            BUNGA_TIDAK_VALID,
            f"Suku bunga tahunan '{nama_utang}' harus antara 0% sampai 100%.",
            400,
        )

    return bunga


def _parse_nama_utang(val: Any, index: int) -> str:
    """Validasi dan pembersihan nama utang."""
    fallback = f"Utang {index + 1}"
    if val is None:
        return fallback

    if not isinstance(val, str):
        raise UtangError(
            NAMA_TIDAK_VALID,
            f"Nama utang ke-{index + 1} harus berupa teks.",
            400,
        )

    s = val.strip()
    if not s:
        return fallback

    if any(ord(c) < 32 for c in s):
        raise UtangError(
            NAMA_TIDAK_VALID,
            f"Nama utang ke-{index + 1} tidak boleh mengandung karakter kontrol.",
            400,
        )

    if len(s) > NAMA_MAX_LEN:
        raise UtangError(
            NAMA_TIDAK_VALID,
            f"Nama utang ke-{index + 1} maksimal {NAMA_MAX_LEN} karakter.",
            400,
        )

    return s


def _jalankan_simulasi(
    dana_bulanan: Decimal,
    utang_list: list[dict[str, Any]],
    strategi: str,
) -> tuple[int, list[dict[str, Any]], Decimal]:
    """Menjalankan simulasi pelunasan bulanan hingga semua utang lunas.

    Mengembalikan (selesai_bulan, lunas_urutan, total_akumulasi_bunga).
    Melempar UtangError jika tidak lunas dalam MAX_BULAN (600 bulan).
    """
    debts = []
    for idx, u in enumerate(utang_list):
        debts.append({
            "idx": idx,
            "nama": u["nama"],
            "sisa_awal": u["sisa"],
            "sisa": u["sisa"],
            "bunga": u["bunga"],
            "minimum": u["minimum"],
            "bunga_total": Decimal("0"),
            "total_dibayar": Decimal("0"),
            "lunas_bulan": None,
        })

    lunas_urutan = []
    selesai_bulan = 0

    for bulan in range(1, MAX_BULAN + 1):
        # 1. Tambah bunga bulan ini untuk tiap utang yang masih bersisa
        for d in debts:
            if d["sisa"] > Decimal("0"):
                # bunga bulanan = sisa * (bunga / 100 / 12) dibulatkan 2 desimal
                bunga_bulan = (d["sisa"] * (d["bunga"] / Decimal("1200"))).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                d["sisa"] += bunga_bulan
                d["bunga_total"] += bunga_bulan

        # 2. Bayar cicilan minimum tiap utang aktif (tidak boleh melebihi sisa)
        dana_sisa = dana_bulanan
        for d in debts:
            if d["sisa"] > Decimal("0"):
                bayar_min = min(d["minimum"], d["sisa"])
                d["sisa"] -= bayar_min
                d["total_dibayar"] += bayar_min
                dana_sisa -= bayar_min
                if d["sisa"] == Decimal("0"):
                    d["lunas_bulan"] = bulan
                    if d not in lunas_urutan:
                        lunas_urutan.append(d)

        # 3. Sisa dana dialokasikan penuh ke utang target
        while dana_sisa > Decimal("0"):
            aktif = [d for d in debts if d["sisa"] > Decimal("0")]
            if not aktif:
                break

            if strategi == "bunga":
                # Bunga tahunan tertinggi dulu, seri sisa terbesar, seri indeks urut awal
                target = max(aktif, key=lambda x: (x["bunga"], x["sisa"], -x["idx"]))
            else:
                # Saldo terkecil dulu, seri bunga tertinggi, seri indeks urut awal
                target = min(aktif, key=lambda x: (x["sisa"], -x["bunga"], x["idx"]))

            alokasi = min(dana_sisa, target["sisa"])
            target["sisa"] -= alokasi
            target["total_dibayar"] += alokasi
            dana_sisa -= alokasi
            if target["sisa"] == Decimal("0"):
                target["lunas_bulan"] = bulan
                if target not in lunas_urutan:
                    lunas_urutan.append(target)

        # Cek apakah semua utang sudah lunas
        if all(d["sisa"] == Decimal("0") for d in debts):
            selesai_bulan = bulan
            break
    else:
        raise UtangError(
            TERLALU_LAMA,
            "Utang belum lunas setelah 600 bulan (50 tahun). Dana bulanan terlalu kecil atau suku bunga terlalu besar.",
            400,
        )

    # Pastikan setiap utang tercatat di lunas_urutan
    for d in debts:
        if d not in lunas_urutan:
            lunas_urutan.append(d)

    total_bunga = sum(d["bunga_total"] for d in debts)
    return selesai_bulan, lunas_urutan, total_bunga


def hitung_rencana(payload: dict[str, Any]) -> dict[str, Any]:
    """Hitung simulasi rencana bebas utang dari payload JSON yang divalidasi."""
    if not isinstance(payload, dict):
        raise UtangError(INVALID_REQUEST, "Permintaan harus berupa objek JSON.", 400)

    # 1. Validasi daftar utang
    utang_raw = payload.get("utang")
    if not isinstance(utang_raw, list) or len(utang_raw) < MIN_UTANG_ITEMS or len(utang_raw) > MAX_UTANG_ITEMS:
        raise UtangError(
            UTANG_JUMLAH,
            f"Daftar utang harus berisi antara {MIN_UTANG_ITEMS} sampai {MAX_UTANG_ITEMS} utang.",
            400,
        )

    # 2. Parsing rincian tiap utang
    parsed_utang = []
    total_minimum = Decimal("0")

    for i, item in enumerate(utang_raw):
        if not isinstance(item, dict):
            raise UtangError(
                INVALID_REQUEST,
                f"Rincian utang ke-{i + 1} harus berupa objek JSON.",
                400,
            )

        nama = _parse_nama_utang(item.get("nama"), i)
        sisa = _parse_rupiah_value(
            item.get("sisa"),
            f"Sisa utang '{nama}'",
            SISA_TIDAK_VALID,
            min_val=SISA_MIN,
            max_val=SISA_MAX,
        )
        bunga = _parse_bunga_value(item.get("bunga"), nama)
        minimum = _parse_rupiah_value(
            item.get("minimum"),
            f"Cicilan minimum '{nama}'",
            MINIMUM_TIDAK_VALID,
            min_val=MINIMUM_MIN,
        )

        total_minimum += minimum
        parsed_utang.append({
            "nama": nama,
            "sisa": sisa,
            "bunga": bunga,
            "minimum": minimum,
        })

    # 3. Validasi dana bulanan
    dana_bulanan = _parse_rupiah_value(
        payload.get("dana_bulanan"),
        "Dana bulanan",
        DANA_TIDAK_VALID,
        min_val=DANA_MIN,
    )

    # 4. Validasi kecukupan dana bulanan terhadap total minimum
    if dana_bulanan < total_minimum:
        raise UtangError(
            DANA_KURANG,
            f"Dana bulanan ({format_rupiah(dana_bulanan)}) kurang dari total cicilan minimum ({format_rupiah(total_minimum)}). "
            f"Naikkan dana bulanan minimal sama dengan total cicilan minimum.",
            400,
        )

    # 5. Validasi strategi
    strat_raw = payload.get("strategi")
    if strat_raw is None or (isinstance(strat_raw, str) and not strat_raw.strip()):
        strategi = "bunga"
    elif isinstance(strat_raw, str) and strat_raw.strip().lower() in STRATEGI_PILIHAN:
        strategi = strat_raw.strip().lower()
    else:
        raise UtangError(
            STRATEGI_TIDAK_VALID,
            "Strategi pelunasan harus 'bunga' atau 'saldo'.",
            400,
        )

    # 6. Jalankan simulasi strategi utama
    selesai_bulan, lunas_debts, total_bunga_dec = _jalankan_simulasi(
        dana_bulanan, parsed_utang, strategi
    )

    # Susun per_utang sesuai urutan lunas
    per_utang = []
    total_utang_int = 0
    total_bunga_int = 0
    total_dibayar_int = 0

    for d in lunas_debts:
        sisa_awal_int = int(d["sisa_awal"].quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        bunga_total_int = int(d["bunga_total"].quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        total_dibayar_d_int = sisa_awal_int + bunga_total_int
        bunga_val = float(d["bunga"]) if d["bunga"] % 1 != 0 else int(d["bunga"])

        total_utang_int += sisa_awal_int
        total_bunga_int += bunga_total_int
        total_dibayar_int += total_dibayar_d_int

        per_utang.append({
            "nama": d["nama"],
            "sisa_awal": sisa_awal_int,
            "bunga": bunga_val,
            "minimum": int(d["minimum"].quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "lunas_bulan": d["lunas_bulan"],
            "bunga_total": bunga_total_int,
            "total_dibayar": total_dibayar_d_int,
        })

    # Susun ringkasan
    tahun = selesai_bulan // 12
    sisa_bulan = selesai_bulan % 12
    ringkasan = {
        "bulan": selesai_bulan,
        "tahun": tahun,
        "sisa_bulan": sisa_bulan,
        "total_utang": total_utang_int,
        "total_bunga": total_bunga_int,
        "total_dibayar": total_dibayar_int,
        "dana_bulanan": int(dana_bulanan.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "strategi": strategi,
        "strategi_label": STRATEGI_LABEL[strategi],
    }

    # 7. Hitung strategi pembanding (null jika gagal / TERLALU_LAMA)
    strategi_pembanding = "saldo" if strategi == "bunga" else "bunga"
    perbandingan = None
    try:
        bln_comp, _, bunga_comp_dec = _jalankan_simulasi(
            dana_bulanan, parsed_utang, strategi_pembanding
        )
        bunga_comp_int = int(bunga_comp_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        selisih_bunga = abs(total_bunga_int - bunga_comp_int)

        # Evaluasi strategi mana yang lebih hemat bunga secara keseluruhan
        bunga_avalanche = total_bunga_int if strategi == "bunga" else bunga_comp_int
        bunga_snowball = bunga_comp_int if strategi == "bunga" else total_bunga_int
        if bunga_avalanche < bunga_snowball:
            lebih_hemat = "bunga"
        elif bunga_snowball < bunga_avalanche:
            lebih_hemat = "saldo"
        else:
            lebih_hemat = "sama"

        perbandingan = {
            "strategi": strategi_pembanding,
            "strategi_label": STRATEGI_LABEL[strategi_pembanding],
            "bulan": bln_comp,
            "total_bunga": bunga_comp_int,
            "selisih_bunga": selisih_bunga,
            "lebih_hemat": lebih_hemat,
        }
    except UtangError:
        perbandingan = None

    # 8. Susun peringatan
    peringatan = []
    for item in parsed_utang:
        bunga_bulan_1 = (item["sisa"] * (item["bunga"] / Decimal("1200"))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if item["minimum"] < bunga_bulan_1:
            peringatan.append(
                f'Cicilan minimum "{item["nama"]}" belum menutup bunga bulanannya, jadi sisa utang bisa bertambah.'
            )

    if dana_bulanan == total_minimum:
        peringatan.append(
            "Dana bulanan sama dengan total cicilan minimum, jadi tidak ada dana percepatan awal."
        )

    peringatan.append(
        "Hitungan memakai bunga bulanan (bunga tahunan ÷ 12) tanpa biaya admin, denda, atau bunga dari transaksi baru."
    )

    return {
        "ringkasan": ringkasan,
        "per_utang": per_utang,
        "perbandingan": perbandingan,
        "peringatan": peringatan,
    }
