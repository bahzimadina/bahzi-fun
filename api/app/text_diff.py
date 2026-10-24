"""Logika perbandingan teks (Text Diff): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Teks pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

import difflib
import re
from typing import Any

# Batas operasional perbandingan teks di memori
MAX_CHARS = 200_000
MAX_BYTES = 1_000_000
MAX_LINES = 5_000
MAX_REQUEST_BYTES = 8 * 1024 * 1024  # 8 MB

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NO_TEXT = "NO_TEXT"
TOO_LONG = "TOO_LONG"
TOO_MANY_LINES = "TOO_MANY_LINES"
INVALID_BOOLEAN = "INVALID_BOOLEAN"


class TextDiffError(ValueError):
    """Galat operasional perbandingan teks dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


def parse_bool(value: Any, field_name: str = "boolean", default: bool | None = None) -> bool:
    """Parse nilai boolean dari bool, string, atau int."""
    if value is None or value == "":
        if default is not None:
            return default
        raise TextDiffError(INVALID_BOOLEAN, f"Nilai boolean untuk '{field_name}' wajib diisi.", 400)

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        raise TextDiffError(
            INVALID_BOOLEAN,
            f"Nilai boolean untuk '{field_name}' tidak valid. Gunakan true/false, 1/0, ya/tidak, atau on/off.",
            400,
        )

    if isinstance(value, str):
        norm = value.strip().lower()
        if norm in ("true", "1", "ya", "yes", "on"):
            return True
        if norm in ("false", "0", "tidak", "no", "off"):
            return False
        raise TextDiffError(
            INVALID_BOOLEAN,
            f"Nilai boolean untuk '{field_name}' tidak valid. Gunakan true/false, 1/0, ya/tidak, atau on/off.",
            400,
        )

    raise TextDiffError(
        INVALID_BOOLEAN,
        f"Nilai boolean untuk '{field_name}' tidak valid. Gunakan true/false, 1/0, ya/tidak, atau on/off.",
        400,
    )


def validate_single_text(text: Any, field_name: str) -> str:
    """Validasi teks masukan terhadap ketiadaan field, tipe, dan batasan panjang."""
    if text is None:
        raise TextDiffError(INVALID_REQUEST, f"Field '{field_name}' wajib diisi.", 400)

    if not isinstance(text, str):
        raise TextDiffError(INVALID_REQUEST, f"Field '{field_name}' harus berupa teks string.", 400)

    if len(text) > MAX_CHARS:
        raise TextDiffError(
            TOO_LONG,
            f"Teks '{field_name}' terlalu panjang. Batasnya {MAX_CHARS:,} karakter per teks.",
            413,
        )

    encoded_bytes = len(text.encode("utf-8"))
    if encoded_bytes > MAX_BYTES:
        raise TextDiffError(
            TOO_LONG,
            f"Ukuran byte teks '{field_name}' ({encoded_bytes:,} byte) melebihi batas 1 MB.",
            413,
        )

    return text


def _normalize_newlines(text: str) -> str:
    """Ubah CRLF dan CR menjadi LF standar."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _normalize_line(line: str, abaikan_spasi: bool, peka_huruf: bool) -> str:
    """Normalisasi satu baris sesuai opsi sebelum dicocokkan difflib."""
    s = line
    if abaikan_spasi:
        s = re.sub(r"[ \t]+", " ", s.strip())
    if not peka_huruf:
        s = s.casefold()
    return s


def _format_range_unified(start: int, stop: int) -> str:
    """Format rentang nomor baris gaya unified diff (1-indexed)."""
    beginning = start + 1
    length = stop - start
    if length == 1:
        return f"{beginning}"
    if not length:
        beginning -= 1
    return f"{beginning},{length}"


def generate_unified_diff(
    a: list[str],
    b: list[str],
    matcher: difflib.SequenceMatcher,
    fromfile: str = "teks lama",
    tofile: str = "teks baru",
    n: int = 3,
) -> str:
    """Hasilkan diff format unified standar dari opcode SequenceMatcher."""
    lines: list[str] = []
    started = False
    for group in matcher.get_grouped_opcodes(n):
        if not started:
            started = True
            lines.append(f"--- {fromfile}")
            lines.append(f"+++ {tofile}")

        first, last = group[0], group[-1]
        file1_range = _format_range_unified(first[1], last[2])
        file2_range = _format_range_unified(first[3], last[4])
        lines.append(f"@@ -{file1_range} +{file2_range} @@")

        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for line in a[i1:i2]:
                    lines.append(" " + line)
                continue
            if tag in {"replace", "delete"}:
                for line in a[i1:i2]:
                    lines.append("-" + line)
            if tag in {"replace", "insert"}:
                for line in b[j1:j2]:
                    lines.append("+" + line)
    return "\n".join(lines)


def diff_text(
    teks_a: Any,
    teks_b: Any,
    *,
    abaikan_spasi: bool | str | None = True,
    peka_huruf: bool | str | None = True,
) -> dict[str, Any]:
    """Bandingkan dua teks baris per baris di memori."""
    valid_a = validate_single_text(teks_a, "teks_a")
    valid_b = validate_single_text(teks_b, "teks_b")

    bool_abaikan_spasi = parse_bool(abaikan_spasi, "abaikan_spasi", default=True)
    bool_peka_huruf = parse_bool(peka_huruf, "peka_huruf", default=True)

    # Validasi NO_TEXT: kedua teks kosong setelah dirapikan
    norm_a_trimmed = re.sub(r"[ \t]+", " ", valid_a.strip())
    norm_b_trimmed = re.sub(r"[ \t]+", " ", valid_b.strip())
    if not norm_a_trimmed and not norm_b_trimmed:
        raise TextDiffError(NO_TEXT, "Kedua teks kosong setelah dirapikan.", 400)

    # Normalisasi akhir baris CRLF/CR -> LF
    text_a_lf = _normalize_newlines(valid_a)
    text_b_lf = _normalize_newlines(valid_b)

    # Pecah jadi baris
    baris_a_asli = text_a_lf.split("\n") if text_a_lf else []
    baris_b_asli = text_b_lf.split("\n") if text_b_lf else []

    if len(baris_a_asli) > MAX_LINES:
        raise TextDiffError(
            TOO_MANY_LINES,
            f"Jumlah baris teks lama ({len(baris_a_asli):,} baris) melebihi batas {MAX_LINES:,} baris.",
            413,
        )

    if len(baris_b_asli) > MAX_LINES:
        raise TextDiffError(
            TOO_MANY_LINES,
            f"Jumlah baris teks baru ({len(baris_b_asli):,} baris) melebihi batas {MAX_LINES:,} baris.",
            413,
        )

    # Normalisasi per baris untuk perbandingan SequenceMatcher
    norm_lines_a = [_normalize_line(line, bool_abaikan_spasi, bool_peka_huruf) for line in baris_a_asli]
    norm_lines_b = [_normalize_line(line, bool_abaikan_spasi, bool_peka_huruf) for line in baris_b_asli]

    matcher = difflib.SequenceMatcher(None, norm_lines_a, norm_lines_b)
    opcodes = matcher.get_opcodes()

    hasil_baris: list[dict[str, Any]] = []
    count_sama = 0
    count_tambah = 0
    count_hapus = 0
    count_ubah = 0

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            n = i2 - i1
            for k in range(n):
                idx_a = i1 + k
                idx_b = j1 + k
                count_sama += 1
                hasil_baris.append({
                    "jenis": "sama",
                    "nomor_a": idx_a + 1,
                    "nomor_b": idx_b + 1,
                    "teks": baris_a_asli[idx_a],
                    "teks_a": baris_a_asli[idx_a],
                    "teks_b": baris_b_asli[idx_b],
                })
        elif tag == "delete":
            for idx_a in range(i1, i2):
                count_hapus += 1
                hasil_baris.append({
                    "jenis": "hapus",
                    "nomor_a": idx_a + 1,
                    "nomor_b": None,
                    "teks": baris_a_asli[idx_a],
                    "teks_a": baris_a_asli[idx_a],
                    "teks_b": None,
                })
        elif tag == "insert":
            for idx_b in range(j1, j2):
                count_tambah += 1
                hasil_baris.append({
                    "jenis": "tambah",
                    "nomor_a": None,
                    "nomor_b": idx_b + 1,
                    "teks": baris_b_asli[idx_b],
                    "teks_a": None,
                    "teks_b": baris_b_asli[idx_b],
                })
        elif tag == "replace":
            len_a = i2 - i1
            len_b = j2 - j1
            min_len = min(len_a, len_b)

            # Pasangkan baris ke-i blok lama dengan ke-i blok baru sebagai "ubah"
            for k in range(min_len):
                idx_a = i1 + k
                idx_b = j1 + k
                count_ubah += 1
                hasil_baris.append({
                    "jenis": "ubah",
                    "nomor_a": idx_a + 1,
                    "nomor_b": idx_b + 1,
                    "teks": baris_b_asli[idx_b],
                    "teks_a": baris_a_asli[idx_a],
                    "teks_b": baris_b_asli[idx_b],
                })

            # Sisa blok lama tak berpasangan menjadi "hapus"
            if len_a > len_b:
                for idx_a in range(i1 + min_len, i2):
                    count_hapus += 1
                    hasil_baris.append({
                        "jenis": "hapus",
                        "nomor_a": idx_a + 1,
                        "nomor_b": None,
                        "teks": baris_a_asli[idx_a],
                        "teks_a": baris_a_asli[idx_a],
                        "teks_b": None,
                    })
            # Sisa blok baru tak berpasangan menjadi "tambah"
            elif len_b > len_a:
                for idx_b in range(j1 + min_len, j2):
                    count_tambah += 1
                    hasil_baris.append({
                        "jenis": "tambah",
                        "nomor_a": None,
                        "nomor_b": idx_b + 1,
                        "teks": baris_b_asli[idx_b],
                        "teks_a": None,
                        "teks_b": baris_b_asli[idx_b],
                    })

    total_beda = count_tambah + count_hapus + count_ubah
    identik = (total_beda == 0)

    ringkasan = {
        "baris_a": len(baris_a_asli),
        "baris_b": len(baris_b_asli),
        "sama": count_sama,
        "tambah": count_tambah,
        "hapus": count_hapus,
        "ubah": count_ubah,
        "total_beda": total_beda,
        "identik": identik,
    }

    teks_selisih = generate_unified_diff(
        baris_a_asli,
        baris_b_asli,
        matcher,
        fromfile="teks lama",
        tofile="teks baru",
    )

    return {
        "ringkasan": ringkasan,
        "baris": hasil_baris,
        "teks_selisih": teks_selisih,
    }


def text_diff_limits_payload() -> dict[str, Any]:
    """Payload info batas operasional perbandingan teks."""
    return {
        "max_chars": MAX_CHARS,
        "max_bytes": MAX_BYTES,
        "max_mb": MAX_BYTES // 1_000_000,
        "max_lines": MAX_LINES,
        "defaults": {
            "abaikan_spasi": True,
            "peka_huruf": True,
        },
        "processed_on": "server",
        "note": "Teks diproses di memori server lalu dibuang, tidak disimpan di disk.",
    }
