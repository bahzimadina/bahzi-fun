"""Logika penyesuaian porsi resep masakan: fungsi murni di memori.

Hitung ulang takaran bahan masakan berdasarkan porsi asal dan porsi target,
lengkap dengan pembulatan ke takaran dapur yang wajar.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai bahan pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import re
from typing import Any

# Batas operasional
MIN_PORSI = 1
MAX_PORSI = 1000
MAX_BARIS = 200
MAX_KARAKTER_BARIS = 200
MAX_KARAKTER = 20_000
MAX_BODY_BYTES = 64 * 1024

# Satuan yang dikenal (peka huruf besar/kecil)
SATUAN_DIKENAL = (
    "gram", "g", "kg", "ons", "ml", "cc", "liter", "l",
    "sdm", "sdt", "gelas", "cup", "butir", "buah", "batang",
    "lembar", "siung", "sachet", "bungkus", "pak", "ekor",
    "potong", "ruas", "ikat", "porsi", "tetes", "kepal", "genggam"
)

# Urutkan satuan dari karakter terbanyak ke tersedikit agar nama satuan yang lebih panjang dicocokkan lebih dulu (mis. gram sebelum g)
SATUAN_SORTED = sorted(SATUAN_DIKENAL, key=len, reverse=True)

# Kelompok satuan hitungan / per butir / wadah
SATUAN_HITUNGAN = {
    "butir", "buah", "batang", "lembar", "siung", "sachet", "bungkus",
    "pak", "ekor", "potong", "ruas", "ikat", "porsi", "kepal", "genggam",
    "gelas", "cup",
}

# Kelompok satuan berat dan volume
SATUAN_BERAT_VOLUME = {
    "gram", "g", "kg", "ons", "ml", "cc", "liter", "l", "sdm", "sdt", "tetes",
}

CATATAN_DEFAULT = [
    "Hitungan ini hanya menyesuaikan takaran bahan masakan secara matematis.",
    "Waktu memasak, suhu oven/kompor, dan ukuran loyang tidak selalu naik sebanding dengan porsi.",
    "Bahan tanpa takaran angka (seperti 'secukupnya') dibiarkan apa adanya untuk disesuaikan saat memasak.",
]

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NO_BAHAN = "NO_BAHAN"
INVALID_PORSI = "INVALID_PORSI"
TERLALU_BANYAK_BARIS = "TERLALU_BANYAK_BARIS"
BARIS_TERLALU_PANJANG = "BARIS_TERLALU_PANJANG"
TEKS_TERLALU_PANJANG = "TEKS_TERLALU_PANJANG"
BARIS_TIDAK_VALID = "BARIS_TIDAK_VALID"


class ResepError(ValueError):
    """Galat operasional kalkulator resep masakan dengan kode galat dan status HTTP."""

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
    """Mengembalikan batas operasional dan daftar satuan yang dikenal."""
    return {
        "min_porsi": MIN_PORSI,
        "max_porsi": MAX_PORSI,
        "max_baris": MAX_BARIS,
        "max_karakter_baris": MAX_KARAKTER_BARIS,
        "max_karakter": MAX_KARAKTER,
        "max_bytes": MAX_BODY_BYTES,
        "satuan_dikenal": list(SATUAN_DIKENAL),
        "contoh": {
            "porsi_asal": 4,
            "porsi_target": 10,
            "bulatkan": True,
            "bahan": (
                "500 gram ayam\n"
                "3 butir telur\n"
                "3 siung bawang putih\n"
                "1/2 sdt merica\n"
                "2 sdm kecap manis\n"
                "garam secukupnya"
            ),
        },
    }


def format_angka(val: float) -> str:
    """Format angka gaya Indonesia: koma sebagai desimal, tanpa nol berekor."""
    if val.is_integer():
        return str(int(val))
    s = f"{val:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def bulatkan_takaran(val: float, satuan: str | None) -> float:
    """Membulatkan takaran bahan ke angka wajar di dapur sesuai satuan."""
    d = Decimal(str(round(val, 4)))

    if satuan in SATUAN_HITUNGAN or satuan not in SATUAN_BERAT_VOLUME:
        # Satuan hitungan / buah / tanpa satuan -> kelipatan 0,5 terdekat, minimal 0,5
        r = (d * Decimal("2")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / Decimal("2")
        if r < Decimal("0.5"):
            r = Decimal("0.5")
        return float(r)

    # Satuan berat / volume
    if d >= Decimal("100"):
        # Kelipatan 5
        r = (d / Decimal("5")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * Decimal("5")
    elif d >= Decimal("20"):
        # Bilangan bulat terdekat
        r = d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    elif d >= Decimal("10"):
        # Ke 0,5 terdekat
        r = (d * Decimal("2")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / Decimal("2")
    else:
        # < 10: ke 0,25 terdekat, minimal 0,25 bila val > 0
        r = (d * Decimal("4")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / Decimal("4")
        if r < Decimal("0.25") and d > Decimal("0"):
            r = Decimal("0.25")

    return float(r)


def hitung_padanan(jumlah_baru: float, satuan: str | None) -> str | None:
    """Padanan satuan untuk jumlah besar (misal gram >= 1000 -> kg, ml >= 1000 -> liter)."""
    if satuan in ("gram", "g") and jumlah_baru >= 1000:
        val_kg = round(jumlah_baru / 1000.0, 2)
        return f"≈{format_angka(val_kg)} kg"
    if satuan in ("ml", "cc") and jumlah_baru >= 1000:
        val_l = round(jumlah_baru / 1000.0, 2)
        return f"≈{format_angka(val_l)} liter"
    return None


def parse_porsi(val: Any, label: str) -> int:
    """Validasi porsi: bilangan bulat 1..1000."""
    if val is None:
        raise ResepError(INVALID_REQUEST, f"Field '{label}' wajib diisi.", 400)
    if isinstance(val, bool):
        raise ResepError(INVALID_PORSI, f"{label} harus berupa bilangan bulat antara {MIN_PORSI} sampai {MAX_PORSI}.", 400)
    if isinstance(val, (int, float)):
        if isinstance(val, float) and not val.is_integer():
            raise ResepError(INVALID_PORSI, f"{label} harus berupa bilangan bulat antara {MIN_PORSI} sampai {MAX_PORSI}.", 400)
        num = int(val)
    elif isinstance(val, str):
        s = val.strip()
        if not s:
            raise ResepError(INVALID_PORSI, f"{label} harus berupa bilangan bulat antara {MIN_PORSI} sampai {MAX_PORSI}.", 400)
        if not re.fullmatch(r"^\d+$", s):
            raise ResepError(INVALID_PORSI, f"{label} harus berupa bilangan bulat antara {MIN_PORSI} sampai {MAX_PORSI}.", 400)
        try:
            num = int(s)
        except ValueError:
            raise ResepError(INVALID_PORSI, f"{label} harus berupa bilangan bulat antara {MIN_PORSI} sampai {MAX_PORSI}.", 400)
    else:
        raise ResepError(INVALID_PORSI, f"{label} harus berupa bilangan bulat antara {MIN_PORSI} sampai {MAX_PORSI}.", 400)

    if num < MIN_PORSI or num > MAX_PORSI:
        raise ResepError(INVALID_PORSI, f"{label} harus di antara {MIN_PORSI} sampai {MAX_PORSI}.", 400)
    return num


def parse_bulatkan(val: Any) -> bool:
    """Parsing parameter bulatkan (bawaan True)."""
    if val is None or val == "":
        return True
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("false", "0", "off", "no"):
        return False
    return True


def hitung_resep(
    porsi_asal: Any,
    porsi_target: Any,
    bahan: Any,
    bulatkan: Any = True,
) -> dict[str, Any]:
    """Hitung ulang takaran bahan resep masakan.

    Parameters:
        porsi_asal: Porsi asli resep (1..1000).
        porsi_target: Porsi yang diinginkan (1..1000).
        bahan: Teks multiline daftar bahan (maksimal 200 baris, 20.000 karakter).
        bulatkan: Boolean atau string 'true'/'false' apakah takaran dibulatkan ke takaran dapur.

    Returns:
        Dictionary hasil perhitungan sesuai skema respons OmniTools.
    """
    p_asal = parse_porsi(porsi_asal, "Porsi resep asli")
    p_target = parse_porsi(porsi_target, "Porsi target")
    do_round = parse_bulatkan(bulatkan)

    if bahan is None:
        raise ResepError(INVALID_REQUEST, "Field 'bahan' wajib diisi.", 400)

    if not isinstance(bahan, str):
        bahan = str(bahan)

    if len(bahan) > MAX_KARAKTER:
        raise ResepError(
            TEKS_TERLALU_PANJANG,
            f"Total teks bahan melebihi batas {MAX_KARAKTER:,} karakter.",
            413,
        )

    lines = bahan.splitlines()
    if len(lines) > MAX_BARIS:
        raise ResepError(
            TERLALU_BANYAK_BARIS,
            f"Jumlah bahan melebihi batas {MAX_BARIS} baris.",
            413,
        )

    # Pastikan ada baris non-kosong
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        raise ResepError(NO_BAHAN, "Daftar bahan tidak boleh kosong.", 400)

    faktor = round(p_target / p_asal, 4)

    hasil_bahan: list[dict[str, Any]] = []
    tidak_dihitung: list[dict[str, Any]] = []

    for idx, raw_line in enumerate(lines, start=1):
        if len(raw_line) > MAX_KARAKTER_BARIS:
            raise ResepError(
                BARIS_TERLALU_PANJANG,
                f"Baris {idx}: panjang baris melebihi batas {MAX_KARAKTER_BARIS} karakter.",
                400,
            )

        trimmed = raw_line.strip()
        if not trimmed:
            # Baris kosong dibuang (tidak dihitung, tidak jadi galat)
            continue

        # Cek angka negatif
        if re.match(r"^-\s*\d", trimmed):
            raise ResepError(
                BARIS_TIDAK_VALID,
                f"Baris {idx}: jumlah bahan tidak boleh 0 atau negatif.",
                400,
            )

        # Cek apakah baris diawali angka: pecahan campuran, pecahan biasa, atau desimal/bulat
        m_mixed = re.match(r"^(\d+)\s+(\d+)\s*/\s*(\d+)", trimmed)
        m_frac = re.match(r"^(\d+)\s*/\s*(\d+)", trimmed)
        m_dec = re.match(r"^(\d+(?:[.,]\d+)?)", trimmed)

        if m_mixed:
            g1, g2, g3 = int(m_mixed.group(1)), int(m_mixed.group(2)), int(m_mixed.group(3))
            if g3 == 0:
                raise ResepError(BARIS_TIDAK_VALID, f"Baris {idx}: pecahan tidak valid.", 400)
            jumlah_asal = g1 + (g2 / g3)
            end_pos = m_mixed.end()
        elif m_frac:
            g1, g2 = int(m_frac.group(1)), int(m_frac.group(2))
            if g2 == 0:
                raise ResepError(BARIS_TIDAK_VALID, f"Baris {idx}: pecahan tidak valid.", 400)
            jumlah_asal = g1 / g2
            end_pos = m_frac.end()
        elif m_dec:
            s_val = m_dec.group(1).replace(",", ".")
            jumlah_asal = float(s_val)
            end_pos = m_dec.end()
        else:
            # Baris tidak diawali angka -> masuk daftar tidak_dihitung
            tidak_dihitung.append({
                "baris": idx,
                "teks_asal": trimmed,
            })
            continue

        # Cek angka 0 atau negatif
        if jumlah_asal <= 0:
            raise ResepError(
                BARIS_TIDAK_VALID,
                f"Baris {idx}: jumlah bahan tidak boleh 0 atau negatif.",
                400,
            )

        # Sisa teks setelah angka
        rest = trimmed[end_pos:].lstrip()

        # Deteksi satuan yang dikenal
        satuan: str | None = None
        for u in SATUAN_SORTED:
            if rest.startswith(u):
                if len(rest) == len(u):
                    satuan = u
                    rest = ""
                    break
                elif rest[len(u)].isspace() or rest[len(u)] in " :,-.":
                    satuan = u
                    rest = rest[len(u):].lstrip(" :,-.")
                    break

        nama = rest.strip()
        if not nama:
            raise ResepError(
                BARIS_TIDAK_VALID,
                f"Baris {idx}: setelah jumlah (dan satuan) belum ada nama bahannya.",
                400,
            )

        # Perhitungan nilai baru
        nilai_persis = round(jumlah_asal * faktor, 2)
        if do_round:
            jumlah_baru = bulatkan_takaran(jumlah_asal * faktor, satuan)
        else:
            jumlah_baru = nilai_persis

        padanan = hitung_padanan(jumlah_baru, satuan)

        tampilan_jumlah = format_angka(jumlah_baru)
        if satuan:
            teks_baru = f"{tampilan_jumlah} {satuan} {nama}"
        else:
            teks_baru = f"{tampilan_jumlah} {nama}"

        hasil_bahan.append({
            "baris": idx,
            "teks_asal": trimmed,
            "nama": nama,
            "satuan": satuan,
            "jumlah_asal": round(jumlah_asal, 4),
            "jumlah_baru": round(jumlah_baru, 4),
            "nilai_persis": nilai_persis,
            "teks_baru": teks_baru,
            "padanan": padanan,
        })

    return {
        "porsi_asal": p_asal,
        "porsi_target": p_target,
        "faktor": faktor,
        "bulatkan": do_round,
        "bahan": hasil_bahan,
        "tidak_dihitung": tidak_dihitung,
        "ringkas": {
            "jumlah_bahan": len(hasil_bahan),
            "jumlah_tidak_dihitung": len(tidak_dihitung),
        },
        "catatan": CATATAN_DEFAULT,
    }
