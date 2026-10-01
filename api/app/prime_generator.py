"""Logika pembuat dan pemeriksa bilangan prima di memori.

Modul ini tidak bergantung pada FastAPI dan tidak melakukan I/O disk.
Semua perhitungan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

import math
import time
from typing import Any

# Batas operasional alat
MAX_BYTES = 16384  # 16 KB
TIME_LIMIT_SECONDS = 10.0
MAX_RESULTS = 5000

DERET_MIN = 1
DERET_MAX = 5000
DERET_DEFAULT = 100

RENTANG_MIN = 2
RENTANG_MAX = 10_000_000

PERIKSA_MIN = 2
PERIKSA_MAX = 1_000_000_000_000_000  # 10^15
PERIKSA_MAX_CHARS = 20

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NO_VALUE = "NO_VALUE"
NOT_A_NUMBER = "NOT_A_NUMBER"
OUT_OF_RANGE = "OUT_OF_RANGE"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
INVALID_RANGE = "INVALID_RANGE"
TOO_MANY_RESULTS = "TOO_MANY_RESULTS"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
TIMEOUT = "TIMEOUT"

MODES = (
    {
        "id": "deret",
        "label": "Deret bilangan prima pertama",
        "deskripsi": "Hasilkan N bilangan prima pertama",
        "bawaan": DERET_DEFAULT,
        "min": DERET_MIN,
        "max": DERET_MAX,
    },
    {
        "id": "rentang",
        "label": "Cari prima dalam rentang",
        "deskripsi": "Cari semua bilangan prima di antara dua batas",
        "min": RENTANG_MIN,
        "max": RENTANG_MAX,
        "max_hasil": MAX_RESULTS,
        "bawaan_dari": RENTANG_MIN,
        "bawaan_sampai": 100,
    },
    {
        "id": "periksa",
        "label": "Periksa satu angka",
        "deskripsi": "Periksa prima atau bukan dan tampilkan faktorisasi prima",
        "min": PERIKSA_MIN,
        "max": PERIKSA_MAX,
        "max_digit": PERIKSA_MAX_CHARS,
        "bawaan": 97,
    },
)


class PrimeError(ValueError):
    """Galat operasional generator bilangan prima dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


def parse_int(
    value: Any,
    field_name: str,
    min_val: int | None = None,
    max_val: int | None = None,
    max_chars: int | None = None,
) -> int:
    """Validasi dan parsing string angka murni hanya berupa digit."""
    if value is None:
        raise PrimeError(NO_VALUE, f"Field '{field_name}' wajib diisi.", 400)

    if not isinstance(value, str):
        raise PrimeError(INVALID_REQUEST, f"Field '{field_name}' harus berupa string teks.", 400)

    clean = value.strip()
    if not clean:
        raise PrimeError(NO_VALUE, f"Nilai '{field_name}' wajib diisi.", 400)

    if max_chars is not None and len(clean) > max_chars:
        raise PrimeError(
            OUT_OF_RANGE,
            f"Panjang masukan '{field_name}' ({len(clean)} karakter) melebihi batas {max_chars} karakter.",
            400,
        )

    if not clean.isdigit():
        raise PrimeError(
            NOT_A_NUMBER,
            f"Nilai '{field_name}' harus berupa bilangan bulat positif tanpa tanda titik atau koma.",
            400,
        )

    val = int(clean)

    if min_val is not None and val < min_val:
        raise PrimeError(
            OUT_OF_RANGE,
            f"Nilai '{field_name}' ({val}) lebih kecil dari batas minimum ({min_val}).",
            400,
        )

    if max_val is not None and val > max_val:
        raise PrimeError(
            OUT_OF_RANGE,
            f"Nilai '{field_name}' ({val}) melebihi batas maksimum ({max_val}).",
            400,
        )

    return val


def is_prime(n: int, deadline: float | None = None) -> bool:
    """Pemeriksaan prima cepat untuk angka besar hingga 10^15 (di bawah 2 detik)."""
    if n < 2:
        return False
    if n in (2, 3):
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False

    limit = math.isqrt(n)
    d = 5
    step = 0
    while d <= limit:
        step += 1
        if (step & 0x3FFFF) == 0:
            if deadline is not None and time.monotonic() > deadline:
                raise PrimeError(TIMEOUT, "Waktu pemrosesan melebihi batas 10 detik.", 422)

        if n % d == 0 or n % (d + 2) == 0:
            return False
        d += 6

    return True


def generate_primes_deret(count: int, deadline: float | None = None) -> list[int]:
    """Hasilkan N bilangan prima pertama (N = 1..5000)."""
    if count < DERET_MIN or count > DERET_MAX:
        raise PrimeError(
            OUT_OF_RANGE,
            f"Jumlah bilangan prima harus antara {DERET_MIN} sampai {DERET_MAX}.",
            400,
        )

    if count == 1:
        return [2]

    # Saringan Eratosthenes sampai batas yang cukup untuk 5.000 prima (prima ke-5000 adalah 48.611)
    limit = 60000
    sieve = bytearray([1]) * (limit + 1)
    sieve[0] = sieve[1] = 0

    primes: list[int] = []
    for i in range(2, limit + 1):
        if sieve[i]:
            primes.append(i)
            if len(primes) == count:
                return primes
            for j in range(i * i, limit + 1, i):
                sieve[j] = 0

    return primes


def generate_primes_rentang(start: int, end: int, deadline: float | None = None) -> list[int]:
    """Cari semua bilangan prima di antara start dan end (batas 2..10.000.000)."""
    if start < RENTANG_MIN or start > RENTANG_MAX:
        raise PrimeError(
            OUT_OF_RANGE,
            f"Batas awal rentang ('dari') harus antara {RENTANG_MIN} sampai {RENTANG_MAX}.",
            400,
        )

    if end < RENTANG_MIN or end > RENTANG_MAX:
        raise PrimeError(
            OUT_OF_RANGE,
            f"Batas akhir rentang ('sampai') harus antara {RENTANG_MIN} sampai {RENTANG_MAX}.",
            400,
        )

    if end < start:
        raise PrimeError(
            INVALID_RANGE,
            "Batas akhir rentang harus lebih besar atau sama dengan batas awal.",
            400,
        )

    primes: list[int] = []

    # Saringan Eratosthenes untuk rentang kecil (end <= 200.000)
    if end <= 200_000:
        sieve = bytearray([1]) * (end + 1)
        sieve[0] = sieve[1] = 0
        limit = math.isqrt(end)
        for i in range(2, limit + 1):
            if sieve[i]:
                for j in range(i * i, end + 1, i):
                    sieve[j] = 0

        for p in range(start, end + 1):
            if sieve[p]:
                primes.append(p)
                if len(primes) > MAX_RESULTS:
                    raise PrimeError(
                        TOO_MANY_RESULTS,
                        f"Hasil melebihi batas {MAX_RESULTS} bilangan prima. Silakan persempit rentang pencarian.",
                        413,
                    )
        return primes

    # Pemeriksaan per angka untuk rentang besar
    curr = start
    if curr <= 2 and end >= 2:
        primes.append(2)
        curr = 3
    elif curr % 2 == 0:
        curr += 1

    step = 0
    while curr <= end:
        step += 1
        if (step & 0x1FFF) == 0:
            if deadline is not None and time.monotonic() > deadline:
                raise PrimeError(TIMEOUT, "Waktu pemrosesan melebihi batas 10 detik.", 422)

        if is_prime(curr, deadline):
            primes.append(curr)
            if len(primes) > MAX_RESULTS:
                raise PrimeError(
                    TOO_MANY_RESULTS,
                    f"Hasil melebihi batas {MAX_RESULTS} bilangan prima. Silakan persempit rentang pencarian.",
                    413,
                )
        curr += 2

    return primes


def factorize_number(n: int, deadline: float | None = None) -> tuple[bool, list[dict[str, int]], str]:
    """Faktorisasi prima lengkap dan pemeriksaan status prima suatu angka."""
    if is_prime(n, deadline):
        return True, [{"prima": n, "pangkat": 1}], str(n)

    rem = n
    factors: list[dict[str, int]] = []

    # Faktor 2
    if rem % 2 == 0:
        k = 0
        while rem % 2 == 0:
            k += 1
            rem //= 2
        factors.append({"prima": 2, "pangkat": k})

    # Faktor 3
    if rem % 3 == 0:
        k = 0
        while rem % 3 == 0:
            k += 1
            rem //= 3
        factors.append({"prima": 3, "pangkat": k})

    # Faktor 6k +/- 1
    d = 5
    limit = math.isqrt(rem)
    step = 0
    while d <= limit:
        step += 1
        if (step & 0x1FFF) == 0:
            if deadline is not None and time.monotonic() > deadline:
                raise PrimeError(TIMEOUT, "Waktu pemrosesan melebihi batas 10 detik.", 422)

        if rem % d == 0:
            k = 0
            while rem % d == 0:
                k += 1
                rem //= d
            factors.append({"prima": d, "pangkat": k})
            limit = math.isqrt(rem)

        d2 = d + 2
        if d2 <= limit and rem % d2 == 0:
            k = 0
            while rem % d2 == 0:
                k += 1
                rem //= d2
            factors.append({"prima": d2, "pangkat": k})
            limit = math.isqrt(rem)

        d += 6

    if rem > 1:
        factors.append({"prima": rem, "pangkat": 1})

    parts = []
    for item in factors:
        p = item["prima"]
        k = item["pangkat"]
        if k > 1:
            parts.append(f"{p}^{k}")
        else:
            parts.append(str(p))

    faktorisasi = " x ".join(parts)
    return False, factors, faktorisasi


def process_prime(
    mode: Any,
    jumlah: Any = None,
    dari: Any = None,
    sampai: Any = None,
    angka: Any = None,
) -> dict[str, Any]:
    """Hitung dan proses bilangan prima murni di memori."""
    started = time.monotonic()
    deadline = started + TIME_LIMIT_SECONDS

    if mode is None:
        raise PrimeError(INVALID_REQUEST, "Field 'mode' wajib diisi.", 400)

    if not isinstance(mode, str):
        raise PrimeError(INVALID_REQUEST, "Field 'mode' harus berupa string teks.", 400)

    mode_str = mode.strip()
    valid_modes = [m["id"] for m in MODES]
    if mode_str not in valid_modes:
        raise PrimeError(
            UNSUPPORTED_MODE,
            f"Mode '{mode_str}' tidak didukung. Pilih salah satu: {', '.join(valid_modes)}.",
            400,
        )

    if mode_str == "deret":
        n = parse_int(jumlah, "jumlah", min_val=DERET_MIN, max_val=DERET_MAX)
        primes = generate_primes_deret(n, deadline)
        terbesar = max(primes) if primes else 0
        jumlah_digit = sum(len(str(p)) for p in primes)
        waktu_ms = round((time.monotonic() - started) * 1000, 2)
        return {
            "mode": "deret",
            "daftar": primes,
            "banyak": len(primes),
            "terbesar": terbesar,
            "jumlah_digit": jumlah_digit,
            "waktu_ms": waktu_ms,
        }

    elif mode_str == "rentang":
        val_dari = parse_int(dari, "dari", min_val=RENTANG_MIN, max_val=RENTANG_MAX)
        val_sampai = parse_int(sampai, "sampai", min_val=RENTANG_MIN, max_val=RENTANG_MAX)
        primes = generate_primes_rentang(val_dari, val_sampai, deadline)
        terbesar = max(primes) if primes else 0
        jumlah_digit = sum(len(str(p)) for p in primes)
        waktu_ms = round((time.monotonic() - started) * 1000, 2)
        return {
            "mode": "rentang",
            "daftar": primes,
            "banyak": len(primes),
            "terbesar": terbesar,
            "jumlah_digit": jumlah_digit,
            "waktu_ms": waktu_ms,
        }

    elif mode_str == "periksa":
        val_angka = parse_int(
            angka,
            "angka",
            min_val=PERIKSA_MIN,
            max_val=PERIKSA_MAX,
            max_chars=PERIKSA_MAX_CHARS,
        )
        is_p, factors, formula = factorize_number(val_angka, deadline)
        waktu_ms = round((time.monotonic() - started) * 1000, 2)
        return {
            "mode": "periksa",
            "angka": val_angka,
            "prima": is_p,
            "faktor": factors,
            "faktorisasi": formula,
            "waktu_ms": waktu_ms,
        }

    raise PrimeError(UNSUPPORTED_MODE, f"Mode '{mode_str}' tidak didukung.", 400)


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional dan daftar mode alat bilangan prima."""
    return {
        "modes": [dict(m) for m in MODES],
        "batas_hasil": MAX_RESULTS,
        "batas_waktu_detik": int(TIME_LIMIT_SECONDS),
        "max_bytes": MAX_BYTES,
        "processed_on": "server",
        "note": "Perhitungan dilakukan di memori lalu dibuang, tidak disimpan di disk.",
    }
