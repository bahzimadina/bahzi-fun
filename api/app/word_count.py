"""Logika penghitungan kata (Word Counter) — fungsi murni, tanpa HTTP, mudah diuji.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Teks pengguna tidak pernah dicatat ke log.

Aturan hitung:
* kata = rangkaian karakter huruf/angka/apostrof/tanda hubung, dipisah spasi/baris/tanda baca lain;
  TIDAK peka huruf besar-kecil untuk `unique_words` dan `top_words` (lowercase).
* karakter = semua karakter termasuk spasi; chars_no_spaces = tanpa spasi/tab/newline.
* kalimat = dipisah `.`, `!`, `?` dan baris kosong; kalimat kosong tidak dihitung.
* paragraf = blok teks dipisah satu atau lebih baris kosong.
* baris = jumlah baris berisi teks (baris kosong tidak dihitung).
* waktu baca = asumsi 200 kata/menit, dibulatkan ke atas, minimal 1 bila ada kata.
* waktu bicara = asumsi 130 kata/menit, dibulatkan ke atas, minimal 1 bila ada kata.
* kata terpanjang = kata dengan karakter terbanyak (jika seri, kata pertama yang ditemukan di teks).
* top_words = maks 5 kata paling sering muncul, panjang kata >= 4 huruf, tanpa kata umum Indonesia.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

# --- Batas operasional ------------------------------------------------------
MAX_CHARS = 200_000
MAX_BYTES = 1024 * 1024  # 1 MB teks UTF-8
CHUNK_SIZE = 1024 * 1024
ENTRY_LIMIT = 1024 * 1024

# --- Kecepatan baca dan bicara (kata per menit) ------------------------------
READING_WPM = 200
SPEAKING_WPM = 130

# --- Kata umum (stop words) Indonesia yang diabaikan pada top_words ---------
STOP_WORDS: frozenset[str] = frozenset({
    "yang",
    "dan",
    "di",
    "ke",
    "dari",
    "untuk",
    "dengan",
    "pada",
    "ini",
    "itu",
    "adalah",
    "tidak",
})

# --- Pola regex -------------------------------------------------------------
# Kata: rangkaian huruf/angka dengan apostrof atau tanda hubung di antaranya.
WORD_PATTERN = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)
# Pemisah kalimat: titik, seru, tanya, atau satu/lebih baris kosong.
SENTENCE_SPLIT_PATTERN = re.compile(r"[.!?]+|\n\s*\n+", re.UNICODE)
# Pemisah paragraf: satu atau lebih baris kosong.
PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n+", re.UNICODE)

# --- Kode error stabil ------------------------------------------------------
NO_TEXT = "NO_TEXT"
TOO_LONG = "TOO_LONG"
INVALID_REQUEST = "INVALID_REQUEST"


class WordCountError(Exception):
    """Kesalahan penghitungan kata dengan kode error dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons JSON standar: {"error": {"code": ..., "message": ...}}."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class WordCountResult:
    """Hasil penghitungan statistik teks di memori."""

    chars: int
    chars_no_spaces: int
    words: int
    unique_words: int
    sentences: int
    paragraphs: int
    lines: int
    reading_minutes: int
    speaking_minutes: int
    longest_word: str
    top_words: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Konversi hasil ke format dictionary JSON."""
        return {
            "chars": self.chars,
            "chars_no_spaces": self.chars_no_spaces,
            "words": self.words,
            "unique_words": self.unique_words,
            "sentences": self.sentences,
            "paragraphs": self.paragraphs,
            "lines": self.lines,
            "reading_minutes": self.reading_minutes,
            "speaking_minutes": self.speaking_minutes,
            "longest_word": self.longest_word,
            "top_words": self.top_words,
        }


def validate_text(text: str | None) -> str:
    """Validasi masukan teks sebelum dihitung."""
    if text is None:
        raise WordCountError(INVALID_REQUEST, "Field teks 'text' wajib disertakan.", 400)

    if not isinstance(text, str):
        raise WordCountError(INVALID_REQUEST, "Field 'text' harus berupa teks string.", 400)

    if not text.strip():
        raise WordCountError(NO_TEXT, "Teks kosong atau hanya berisi spasi. Masukkan teks untuk dihitung.", 400)

    if len(text) > MAX_CHARS:
        raise WordCountError(
            TOO_LONG,
            f"Panjang teks {len(text):,} karakter melebihi batas {MAX_CHARS:,} karakter.",
            413,
        )

    encoded_bytes = len(text.encode("utf-8"))
    if encoded_bytes > MAX_BYTES:
        max_mb = MAX_BYTES // (1024 * 1024)
        raise WordCountError(
            TOO_LONG,
            f"Ukuran byte teks ({encoded_bytes:,} byte) melebihi batas {max_mb} MB.",
            413,
        )

    return text


def count_text(text: str) -> WordCountResult:
    """Hitung metrik teks di memori."""
    validated = validate_text(text)

    # Normalisasi baris baru CRLF/CR -> LF
    normalized = validated.replace("\r\n", "\n").replace("\r", "\n")

    # Karakter
    chars = len(normalized)
    chars_no_spaces = sum(1 for c in normalized if not c.isspace())

    # Kata
    raw_words = WORD_PATTERN.findall(normalized)
    words = len(raw_words)

    # Kata unik (case-insensitive)
    lower_words = [w.lower() for w in raw_words]
    unique_words = len(set(lower_words))

    # Kalimat: dipisah . ! ? dan baris kosong; kalimat tanpa huruf/angka tidak dihitung
    raw_sentences = SENTENCE_SPLIT_PATTERN.split(normalized)
    sentences = sum(1 for s in raw_sentences if re.search(r"[^\W_]", s))

    # Paragraf: dipisah satu atau lebih baris kosong
    raw_paragraphs = PARAGRAPH_SPLIT_PATTERN.split(normalized)
    paragraphs = sum(1 for p in raw_paragraphs if p.strip())

    # Baris: jumlah baris berisi teks (baris kosong tidak dihitung)
    lines = sum(1 for line in normalized.split("\n") if line.strip())

    # Waktu baca & bicara
    reading_minutes = math.ceil(words / READING_WPM) if words > 0 else 0
    speaking_minutes = math.ceil(words / SPEAKING_WPM) if words > 0 else 0

    # Kata terpanjang (jika seri, kata pertama yang ditemukan di teks asli)
    longest_word = max(raw_words, key=len) if raw_words else ""

    # Top words: maks 5 kata paling sering, panjang >= 4 huruf, non-stopword
    filtered_words = [w for w in lower_words if len(w) >= 4 and w not in STOP_WORDS]
    word_counter = Counter(filtered_words)
    top_words = [{"word": word, "count": count} for word, count in word_counter.most_common(5)]

    return WordCountResult(
        chars=chars,
        chars_no_spaces=chars_no_spaces,
        words=words,
        unique_words=unique_words,
        sentences=sentences,
        paragraphs=paragraphs,
        lines=lines,
        reading_minutes=reading_minutes,
        speaking_minutes=speaking_minutes,
        longest_word=longest_word,
        top_words=top_words,
    )
