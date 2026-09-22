"""Logika pengacakan urutan baris daftar (List Shuffler): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Teks pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any

# Batas operasional teks di memori
MAX_CHARS = 200_000
MAX_BYTES = 1024 * 1024  # 1 MB teks UTF-8
CHUNK_SIZE = 1024 * 1024
MAX_TAKE = 200_000
MIN_SEED = 0
MAX_SEED = 4_294_967_295

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NO_TEXT = "NO_TEXT"
TOO_LONG = "TOO_LONG"
INVALID_SEED = "INVALID_SEED"
INVALID_TAKE = "INVALID_TAKE"
INVALID_BOOLEAN = "INVALID_BOOLEAN"


class ListShufflerError(Exception):
    """Galat operasional acak urutan daftar dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class ShuffleResult:
    """Hasil operasi pengacakan urutan baris di memori."""

    text: str
    lines_in: int
    lines_out: int
    take: int
    seed: int
    seed_given: bool
    trim: bool
    drop_empty: bool
    empty_removed: int
    chars_in: int
    chars_out: int

    def to_dict(self) -> dict[str, Any]:
        """Konversi hasil ke dictionary JSON."""
        return {
            "text": self.text,
            "lines_in": self.lines_in,
            "lines_out": self.lines_out,
            "take": self.take,
            "seed": self.seed,
            "seed_given": self.seed_given,
            "trim": self.trim,
            "drop_empty": self.drop_empty,
            "empty_removed": self.empty_removed,
            "chars_in": self.chars_in,
            "chars_out": self.chars_out,
        }


def check_size(text: str) -> None:
    """Periksa batas ukuran byte UTF-8 teks."""
    encoded_bytes = len(text.encode("utf-8"))
    if encoded_bytes > MAX_BYTES:
        max_mb = MAX_BYTES // (1024 * 1024)
        raise ListShufflerError(
            TOO_LONG,
            f"Ukuran byte teks ({encoded_bytes:,} byte) melebihi batas {max_mb} MB.",
            413,
        )


def validate_text(text: str | None) -> str:
    """Validasi teks masukan terhadap ketiadaan teks, tipe, dan batas ukuran."""
    if text is None:
        raise ListShufflerError(NO_TEXT, "Masukkan dulu daftar baris yang ingin diacak.", 400)

    if not isinstance(text, str):
        raise ListShufflerError(INVALID_REQUEST, "Field 'text' harus berupa teks string.", 400)

    if not text.strip():
        raise ListShufflerError(NO_TEXT, "Masukkan dulu daftar baris yang ingin diacak.", 400)

    if len(text) > MAX_CHARS:
        raise ListShufflerError(
            TOO_LONG,
            "Teks terlalu panjang. Batasnya 200.000 karakter.",
            413,
        )

    check_size(text)
    return text


def parse_bool(value: Any, field_name: str = "boolean", default: bool | None = None) -> bool:
    """Parse nilai boolean dari bool, string, atau int."""
    if value is None or value == "":
        if default is not None:
            return default
        raise ListShufflerError(INVALID_BOOLEAN, f"Nilai boolean untuk '{field_name}' wajib diisi.", 400)

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        raise ListShufflerError(
            INVALID_BOOLEAN,
            f"Nilai boolean untuk '{field_name}' tidak valid. Gunakan true/false, 1/0, atau ya/tidak.",
            400,
        )

    if isinstance(value, str):
        norm = value.strip().lower()
        if norm in ("true", "1", "ya"):
            return True
        if norm in ("false", "0", "tidak"):
            return False
        raise ListShufflerError(
            INVALID_BOOLEAN,
            f"Nilai boolean untuk '{field_name}' tidak valid. Gunakan true/false, 1/0, atau ya/tidak.",
            400,
        )

    raise ListShufflerError(
        INVALID_BOOLEAN,
        f"Nilai boolean untuk '{field_name}' tidak valid. Gunakan true/false, 1/0, atau ya/tidak.",
        400,
    )


def parse_take(value: Any) -> int:
    """Parse nilai take (jumlah baris yang diambil)."""
    if value is None:
        return 0

    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return 0
        try:
            num = int(stripped)
        except ValueError:
            raise ListShufflerError(
                INVALID_TAKE,
                "Jumlah baris yang diambil harus angka bulat 0 sampai 200.000.",
                400,
            )
    elif isinstance(value, int) and not isinstance(value, bool):
        num = value
    else:
        raise ListShufflerError(
            INVALID_TAKE,
            "Jumlah baris yang diambil harus angka bulat 0 sampai 200.000.",
            400,
        )

    if num < 0 or num > MAX_TAKE:
        raise ListShufflerError(
            INVALID_TAKE,
            "Jumlah baris yang diambil harus angka bulat 0 sampai 200.000.",
            400,
        )

    return num


def parse_seed(value: Any) -> tuple[int, bool]:
    """Parse kunci acak atau buat kunci acak baru bila kosong."""
    if value is None:
        generated = random.SystemRandom().randint(1, 999_999_999)
        return generated, False

    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            generated = random.SystemRandom().randint(1, 999_999_999)
            return generated, False
        try:
            seed_val = int(stripped)
        except ValueError:
            raise ListShufflerError(
                INVALID_SEED,
                "Kunci acak harus angka bulat 0 sampai 4294967295.",
                400,
            )
    elif isinstance(value, int) and not isinstance(value, bool):
        seed_val = value
    else:
        raise ListShufflerError(
            INVALID_SEED,
            "Kunci acak harus angka bulat 0 sampai 4294967295.",
            400,
        )

    if seed_val < MIN_SEED or seed_val > MAX_SEED:
        raise ListShufflerError(
            INVALID_SEED,
            "Kunci acak harus angka bulat 0 sampai 4294967295.",
            400,
        )

    return seed_val, True


def shuffle_lines(
    text: str | None,
    take: int | str | None = None,
    seed: int | str | None = None,
    trim: bool | str | None = True,
    drop_empty: bool | str | None = True,
) -> ShuffleResult:
    """Acak urutan baris daftar teks di memori."""
    validated_text = validate_text(text)
    valid_trim = parse_bool(trim, "trim", default=True)
    valid_drop = parse_bool(drop_empty, "drop_empty", default=True)
    valid_take = parse_take(take)
    valid_seed, seed_given = parse_seed(seed)

    chars_in = len(validated_text)
    raw_lines = validated_text.splitlines()
    lines_in = len(raw_lines)

    working_lines: list[str] = []
    empty_removed = 0

    for line in raw_lines:
        if valid_drop and line.strip() == "":
            empty_removed += 1
            continue

        item = line.strip() if valid_trim else line
        working_lines.append(item)

    rng = random.Random(valid_seed)
    rng.shuffle(working_lines)

    if valid_take > 0 and valid_take < len(working_lines):
        out_lines = working_lines[:valid_take]
    else:
        out_lines = working_lines

    lines_out = len(out_lines)
    result_text = "\n".join(out_lines)
    chars_out = len(result_text)

    return ShuffleResult(
        text=result_text,
        lines_in=lines_in,
        lines_out=lines_out,
        take=valid_take,
        seed=valid_seed,
        seed_given=seed_given,
        trim=valid_trim,
        drop_empty=valid_drop,
        empty_removed=empty_removed,
        chars_in=chars_in,
        chars_out=chars_out,
    )
