"""Logika pembersihan baris duplikat (Remove Duplicates): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Teks pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Batas operasional teks di memori
MAX_CHARS = 200_000
MAX_BYTES = 1024 * 1024  # 1 MB teks UTF-8
CHUNK_SIZE = 1024 * 1024

# Pilihan kemunculan yang disimpan
KEEP_MODES: dict[str, str] = {
    "first": "Simpan kemunculan pertama",
    "last": "Simpan kemunculan terakhir",
}

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NO_TEXT = "NO_TEXT"
TOO_LONG = "TOO_LONG"
UNSUPPORTED_KEEP = "UNSUPPORTED_KEEP"
INVALID_BOOLEAN = "INVALID_BOOLEAN"


class RemoveDuplicatesError(Exception):
    """Galat operasional hapus duplikat dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class DedupeResult:
    """Hasil operasi pembersihan baris duplikat di memori."""

    text: str
    keep: str
    case_sensitive: bool
    trim: bool
    drop_empty: bool
    lines_in: int
    lines_out: int
    duplicates_removed: int
    empty_removed: int
    chars_in: int
    chars_out: int

    def to_dict(self) -> dict[str, Any]:
        """Konversi hasil ke dictionary JSON."""
        return {
            "text": self.text,
            "keep": self.keep,
            "case_sensitive": self.case_sensitive,
            "trim": self.trim,
            "drop_empty": self.drop_empty,
            "lines_in": self.lines_in,
            "lines_out": self.lines_out,
            "duplicates_removed": self.duplicates_removed,
            "empty_removed": self.empty_removed,
            "chars_in": self.chars_in,
            "chars_out": self.chars_out,
        }


def check_size(text: str) -> None:
    """Periksa batas ukuran byte UTF-8 teks."""
    encoded_bytes = len(text.encode("utf-8"))
    if encoded_bytes > MAX_BYTES:
        max_mb = MAX_BYTES // (1024 * 1024)
        raise RemoveDuplicatesError(
            TOO_LONG,
            f"Ukuran byte teks ({encoded_bytes:,} byte) melebihi batas {max_mb} MB.",
            413,
        )


def validate_text(text: str | None) -> str:
    """Validasi teks masukan terhadap ketiadaan teks, tipe, dan batas ukuran."""
    if text is None:
        raise RemoveDuplicatesError(NO_TEXT, "Masukkan dulu daftar baris yang ingin dirapikan.", 400)

    if not isinstance(text, str):
        raise RemoveDuplicatesError(INVALID_REQUEST, "Field 'text' harus berupa teks string.", 400)

    if not text.strip():
        raise RemoveDuplicatesError(NO_TEXT, "Masukkan dulu daftar baris yang ingin dirapikan.", 400)

    if len(text) > MAX_CHARS:
        raise RemoveDuplicatesError(
            TOO_LONG,
            "Teks terlalu panjang. Batasnya 200.000 karakter.",
            413,
        )

    check_size(text)
    return text


def normalize_keep(keep: str | None) -> str:
    """Validasi dan sesuaikan mode simpan kemunculan."""
    if keep is None or keep == "":
        return "first"

    if not isinstance(keep, str):
        raise RemoveDuplicatesError(UNSUPPORTED_KEEP, "Pilihan simpan duplikat tidak valid.", 400)

    norm = keep.strip().lower()
    if norm not in KEEP_MODES:
        raise RemoveDuplicatesError(
            UNSUPPORTED_KEEP,
            "Pilihan simpan duplikat tidak valid. Pilih 'first' atau 'last'.",
            400,
        )

    return norm


def parse_bool(value: Any, field_name: str = "boolean", default: bool | None = None) -> bool:
    """Parse nilai boolean dari bool, string, atau int."""
    if value is None or value == "":
        if default is not None:
            return default
        raise RemoveDuplicatesError(INVALID_BOOLEAN, f"Nilai boolean untuk '{field_name}' wajib diisi.", 400)

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        raise RemoveDuplicatesError(
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
        raise RemoveDuplicatesError(
            INVALID_BOOLEAN,
            f"Nilai boolean untuk '{field_name}' tidak valid. Gunakan true/false, 1/0, atau ya/tidak.",
            400,
        )

    raise RemoveDuplicatesError(
        INVALID_BOOLEAN,
        f"Nilai boolean untuk '{field_name}' tidak valid. Gunakan true/false, 1/0, atau ya/tidak.",
        400,
    )


def dedupe_text(
    text: str | None,
    keep: str | None = "first",
    case_sensitive: bool | str | None = False,
    trim: bool | str | None = True,
    drop_empty: bool | str | None = True,
) -> DedupeResult:
    """Hapus baris duplikat dari teks di memori."""
    validated_text = validate_text(text)
    valid_keep = normalize_keep(keep)
    valid_case = parse_bool(case_sensitive, "case_sensitive", default=False)
    valid_trim = parse_bool(trim, "trim", default=True)
    valid_drop = parse_bool(drop_empty, "drop_empty", default=True)

    chars_in = len(validated_text)
    raw_lines = validated_text.splitlines()
    lines_in = len(raw_lines)

    candidates: list[tuple[int, str, str]] = []
    empty_removed = 0

    for idx, line in enumerate(raw_lines):
        if valid_drop and line.strip() == "":
            empty_removed += 1
            continue

        key = line.strip() if valid_trim else line
        if not valid_case:
            key = key.casefold()
        candidates.append((idx, line, key))

    seen_keys: set[str] = set()
    if valid_keep == "first":
        kept_candidates: list[tuple[int, str]] = []
        for idx, line, key in candidates:
            if key not in seen_keys:
                seen_keys.add(key)
                kept_candidates.append((idx, line))
    else:
        kept_rev: list[tuple[int, str]] = []
        for idx, line, key in reversed(candidates):
            if key not in seen_keys:
                seen_keys.add(key)
                kept_rev.append((idx, line))
        kept_candidates = sorted(kept_rev, key=lambda x: x[0])

    out_lines = [line for _, line in kept_candidates]
    lines_out = len(out_lines)
    duplicates_removed = lines_in - empty_removed - lines_out
    result_text = "\n".join(out_lines)
    chars_out = len(result_text)

    return DedupeResult(
        text=result_text,
        keep=valid_keep,
        case_sensitive=valid_case,
        trim=valid_trim,
        drop_empty=valid_drop,
        lines_in=lines_in,
        lines_out=lines_out,
        duplicates_removed=duplicates_removed,
        empty_removed=empty_removed,
        chars_in=chars_in,
        chars_out=chars_out,
    )
