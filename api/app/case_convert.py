"""Logika pengubahan huruf (Case Converter) — fungsi murni, tanpa HTTP, mudah diuji.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Teks pengguna tidak pernah dicatat ke log.

Mode yang didukung:
* upper: HURUF BESAR
* lower: huruf kecil
* title: Kapital Tiap Kata (apostrof dan tanda hubung dijaga)
* sentence: Kapital Awal Kalimat (setelah titik/seru/tanya atau baris baru)
* inverse: Balik Besar-Kecil
* alternating: Selang-seling huruf (hanya alfabet yang bergantian)
* camel: camelCase
* snake: snake_case
* kebab: kebab-case
* slug: slug-url (ASCII saja, tanda baca dibuang)

Batas operasional:
* Maks 200.000 karakter dan maks 1 MB teks UTF-8 per permintaan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Batas operasional teks di memori
MAX_CHARS = 200_000
MAX_BYTES = 1024 * 1024  # 1 MB teks UTF-8
CHUNK_SIZE = 1024 * 1024

# Kode error stabil
NO_TEXT = "NO_TEXT"
TOO_LONG = "TOO_LONG"
INVALID_REQUEST = "INVALID_REQUEST"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"

# Pemetaan mode ke label bahasa Indonesia
MODES: dict[str, str] = {
    "upper": "HURUF BESAR",
    "lower": "huruf kecil",
    "title": "Kapital Tiap Kata",
    "sentence": "Kapital Awal Kalimat",
    "inverse": "Balik Besar-Kecil",
    "alternating": "Selang-seling",
    "camel": "camelCase",
    "snake": "snake_case",
    "kebab": "kebab-case",
    "slug": "slug-url",
}
MODE_ORDER: list[str] = list(MODES.keys())

# Pola regex kata teks umum (mempertahankan apostrof dan tanda hubung di dalam kata)
WORD_PATTERN = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)
# Pola kata khusus untuk identifier (hanya huruf dan angka)
ALPHANUM_WORD_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
# Pola kata ASCII murni untuk slug URL
ASCII_ALPHANUM_PATTERN = re.compile(r"[a-zA-Z0-9]+")


class CaseConvertError(Exception):
    """Kesalahan pengubahan huruf dengan kode error dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons JSON standar: {"error": {"code": ..., "message": ...}}."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class CaseConvertResult:
    """Hasil pengubahan format huruf teks di memori."""

    mode: str
    text: str
    chars_in: int
    chars_out: int
    words: int
    changed: bool

    def to_dict(self) -> dict[str, Any]:
        """Konversi hasil ke format dictionary JSON."""
        return {
            "mode": self.mode,
            "text": self.text,
            "chars_in": self.chars_in,
            "chars_out": self.chars_out,
            "words": self.words,
            "changed": self.changed,
        }


def _to_title_case(text: str) -> str:
    # Huruf pertama kapital dan sisanya kecil untuk tiap kata
    return WORD_PATTERN.sub(
        lambda m: m.group(0)[0].upper() + m.group(0)[1:].lower(),
        text,
    )


def _to_sentence_case(text: str) -> str:
    # Awal kalimat: awal teks, setelah ./?/! (beserta spasi/baris baru), atau setelah baris baru
    lowered = text.lower()
    chars = list(lowered)
    n = len(chars)
    result: list[str] = []
    cap_next = True
    i = 0
    while i < n:
        ch = chars[i]
        if cap_next:
            if ch.isalpha():
                result.append(ch.upper())
                cap_next = False
                i += 1
                continue
            if ch.isdigit():
                result.append(ch)
                cap_next = False
                i += 1
                continue

        result.append(ch)
        if ch == "\n":
            cap_next = True
        elif ch in ".!?":
            j = i + 1
            while j < n and chars[j] in ".!?":
                result.append(chars[j])
                j += 1
            i = j - 1
            if i + 1 >= n or chars[i + 1].isspace():
                cap_next = True
        i += 1
    return "".join(result)


def _to_alternating_case(text: str) -> str:
    # Huruf ke-1 kecil, ke-2 besar; karakter non-alfabet tidak mengubah giliran
    result: list[str] = []
    letter_idx = 0
    for ch in text:
        if ch.isalpha():
            result.append(ch.lower() if letter_idx % 2 == 0 else ch.upper())
            letter_idx += 1
        else:
            result.append(ch)
    return "".join(result)


def _to_camel_case(text: str) -> str:
    # Pemisah: apa pun selain huruf/angka, kata pertama kecil, berikutnya kapital
    words = ALPHANUM_WORD_PATTERN.findall(text)
    if not words:
        return ""
    first = words[0].lower()
    rest = [w[0].upper() + w[1:].lower() for w in words[1:]]
    return first + "".join(rest)


def _to_snake_case(text: str) -> str:
    words = ALPHANUM_WORD_PATTERN.findall(text)
    return "_".join(w.lower() for w in words)


def _to_kebab_case(text: str) -> str:
    words = ALPHANUM_WORD_PATTERN.findall(text)
    return "-".join(w.lower() for w in words)


def _to_slug(text: str) -> str:
    # Non-ASCII dan tanda baca dibuang, kata digabung dengan satu tanda hubung
    words = ASCII_ALPHANUM_PATTERN.findall(text)
    return "-".join(w.lower() for w in words)


def validate_text(text: str | None) -> str:
    """Validasi masukan teks sebelum diubah."""
    if text is None:
        raise CaseConvertError(INVALID_REQUEST, "Field teks 'text' wajib disertakan.", 400)

    if not isinstance(text, str):
        raise CaseConvertError(INVALID_REQUEST, "Field 'text' harus berupa teks string.", 400)

    if not text.strip():
        raise CaseConvertError(
            NO_TEXT,
            "Teks kosong atau hanya berisi spasi. Masukkan teks untuk diubah.",
            400,
        )

    if len(text) > MAX_CHARS:
        raise CaseConvertError(
            TOO_LONG,
            f"Panjang teks {len(text):,} karakter melebihi batas {MAX_CHARS:,} karakter.",
            413,
        )

    encoded_bytes = len(text.encode("utf-8"))
    if encoded_bytes > MAX_BYTES:
        max_mb = MAX_BYTES // (1024 * 1024)
        raise CaseConvertError(
            TOO_LONG,
            f"Ukuran byte teks ({encoded_bytes:,} byte) melebihi batas {max_mb} MB.",
            413,
        )

    return text


def normalize_mode(mode: str | None) -> str:
    """Validasi dan normalkan mode pengubahan."""
    if mode is None or not isinstance(mode, str) or not mode.strip():
        raise CaseConvertError(INVALID_REQUEST, "Mode pengubahan wajib dipilih.", 400)

    norm = mode.strip().lower()
    if norm not in MODES:
        raise CaseConvertError(UNSUPPORTED_MODE, "Mode pengubahan tidak dikenal.", 400)

    return norm


def convert_case(text: str | None, mode: str | None) -> CaseConvertResult:
    """Ubah format huruf teks di memori sesuai mode yang dipilih."""
    valid_mode = normalize_mode(mode)
    validated = validate_text(text)

    # Normalisasi baris baru CRLF/CR -> LF
    normalized = validated.replace("\r\n", "\n").replace("\r", "\n")

    if valid_mode == "upper":
        converted = normalized.upper()
    elif valid_mode == "lower":
        converted = normalized.lower()
    elif valid_mode == "title":
        converted = _to_title_case(normalized)
    elif valid_mode == "sentence":
        converted = _to_sentence_case(normalized)
    elif valid_mode == "inverse":
        converted = normalized.swapcase()
    elif valid_mode == "alternating":
        converted = _to_alternating_case(normalized)
    elif valid_mode == "camel":
        converted = _to_camel_case(normalized)
    elif valid_mode == "snake":
        converted = _to_snake_case(normalized)
    elif valid_mode == "kebab":
        converted = _to_kebab_case(normalized)
    elif valid_mode == "slug":
        converted = _to_slug(normalized)
    else:
        raise CaseConvertError(UNSUPPORTED_MODE, "Mode pengubahan tidak dikenal.", 400)

    words = len(WORD_PATTERN.findall(converted))
    changed = converted != normalized

    return CaseConvertResult(
        mode=valid_mode,
        text=converted,
        chars_in=len(normalized),
        chars_out=len(converted),
        words=words,
        changed=changed,
    )
