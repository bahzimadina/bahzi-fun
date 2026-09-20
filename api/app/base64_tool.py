"""Logika konversi Base64: fungsi murni di memori, tanpa HTTP dan tanpa I/O disk.

Teks diproses di memori dan tidak pernah dicatat ke log.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import re
from typing import Any

# Batas operasional teks di memori
MAX_CHARS = 200_000
MAX_BYTES = 1024 * 1024  # 1 MB teks UTF-8
CHUNK_SIZE = 1024 * 1024

# Pilihan mode, varian alfabet, dan pembungkusan
MODES: dict[str, str] = {
    "encode": "Teks jadi Base64",
    "decode": "Base64 jadi teks",
}

VARIANTS: dict[str, str] = {
    "standard": "Standar",
    "urlsafe": "Aman tautan",
}

WRAP_OPTIONS: list[int] = [0, 64, 76]

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NO_TEXT = "NO_TEXT"
TOO_LONG = "TOO_LONG"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
INVALID_VARIANT = "INVALID_VARIANT"
INVALID_WRAP = "INVALID_WRAP"
INVALID_BASE64 = "INVALID_BASE64"
NOT_TEXT = "NOT_TEXT"

# Karakter yang diizinkan dalam Base64 sebelum padding
_BASE64_CHARS_PATTERN = re.compile(r"^[A-Za-z0-9+/=\-_]+$")


class Base64ToolError(Exception):
    """Galat operasional Base64 dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class Base64Result:
    """Hasil operasi encode atau decode Base64 di memori."""

    mode: str
    text: str
    variant: str
    wrap: int
    chars_in: int
    bytes_in: int
    chars_out: int
    bytes_out: int
    changed: bool

    def to_dict(self) -> dict[str, Any]:
        """Konversi hasil ke bentuk dictionary serializable."""
        return {
            "mode": self.mode,
            "text": self.text,
            "variant": self.variant,
            "wrap": self.wrap,
            "chars_in": self.chars_in,
            "bytes_in": self.bytes_in,
            "chars_out": self.chars_out,
            "bytes_out": self.bytes_out,
            "changed": self.changed,
        }


def validate_text(text: str | None) -> str:
    """Periksa masukan teks terhadap keberadaan nilai, tipe, dan batas ukuran."""
    if text is None:
        raise Base64ToolError(INVALID_REQUEST, "Field teks 'text' wajib disertakan.", 400)

    if not isinstance(text, str):
        raise Base64ToolError(INVALID_REQUEST, "Field 'text' harus berupa teks string.", 400)

    if not text.strip():
        raise Base64ToolError(
            NO_TEXT,
            "Teks kosong atau hanya berisi spasi. Masukkan teks untuk diubah.",
            400,
        )

    if len(text) > MAX_CHARS:
        raise Base64ToolError(
            TOO_LONG,
            f"Panjang teks {len(text):,} karakter melebihi batas {MAX_CHARS:,} karakter.",
            413,
        )

    encoded_bytes = len(text.encode("utf-8"))
    if encoded_bytes > MAX_BYTES:
        max_mb = MAX_BYTES // (1024 * 1024)
        raise Base64ToolError(
            TOO_LONG,
            f"Ukuran byte teks ({encoded_bytes:,} byte) melebihi batas {max_mb} MB.",
            413,
        )

    return text


def normalize_mode(mode: str | None) -> str:
    """Validasi dan sesuaikan mode operasi (encode atau decode)."""
    if mode is None or not isinstance(mode, str) or not mode.strip():
        raise Base64ToolError(INVALID_REQUEST, "Mode operasi wajib dipilih.", 400)

    norm = mode.strip().lower()
    if norm not in MODES:
        raise Base64ToolError(UNSUPPORTED_MODE, "Mode operasi tidak dikenal.", 400)

    return norm


def normalize_variant(variant: str | None) -> str:
    """Validasi varian alfabet Base64 yang dipilih."""
    if variant is None:
        return "standard"

    if not isinstance(variant, str):
        raise Base64ToolError(INVALID_VARIANT, "Varian Base64 tidak valid.", 400)

    norm = variant.strip().lower()
    if not norm:
        return "standard"

    if norm not in VARIANTS:
        raise Base64ToolError(
            INVALID_VARIANT,
            "Varian Base64 tidak valid. Pilih standar atau aman tautan.",
            400,
        )

    return norm


def normalize_wrap(wrap: int | str | None) -> int:
    """Validasi panjang pembungkusan baris hasil encode."""
    if wrap is None or wrap == "":
        return 0

    if isinstance(wrap, str):
        try:
            wrap = int(wrap.strip())
        except ValueError:
            raise Base64ToolError(
                INVALID_WRAP,
                "Pilihan pembungkusan baris tidak valid. Pilih 0, 64, atau 76.",
                400,
            )

    if not isinstance(wrap, int) or wrap not in WRAP_OPTIONS:
        raise Base64ToolError(
            INVALID_WRAP,
            "Pilihan pembungkusan baris tidak valid. Pilih 0, 64, atau 76.",
            400,
        )

    return wrap


def _encode_text(text: str, variant: str, wrap: int) -> Base64Result:
    # Normalisasi CRLF/CR menjadi LF agar konsisten di semua sistem operasi
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_bytes = normalized.encode("utf-8")

    if variant == "urlsafe":
        encoded_str = base64.urlsafe_b64encode(raw_bytes).decode("ascii")
    else:
        encoded_str = base64.b64encode(raw_bytes).decode("ascii")

    if wrap > 0:
        lines = [encoded_str[i : i + wrap] for i in range(0, len(encoded_str), wrap)]
        result_text = "\n".join(lines)
    else:
        result_text = encoded_str

    result_bytes = result_text.encode("utf-8")
    return Base64Result(
        mode="encode",
        text=result_text,
        variant=variant,
        wrap=wrap,
        chars_in=len(normalized),
        bytes_in=len(raw_bytes),
        chars_out=len(result_text),
        bytes_out=len(result_bytes),
        changed=result_text != normalized,
    )


def _decode_text(text: str) -> Base64Result:
    # Simpan ukuran asli masukan sebelum pembersihan spasi
    chars_in = len(text)
    bytes_in = len(text.encode("utf-8"))

    # Buang semua whitespace (spasi, tab, baris baru)
    cleaned = re.sub(r"\s+", "", text)

    # Dukungan data URI, buang metadata skema hingga penanda base64
    if cleaned.startswith("data:") and ";base64," in cleaned:
        cleaned = cleaned.split(";base64,", 1)[1]

    if not cleaned:
        raise Base64ToolError(
            NO_TEXT,
            "Teks Base64 kosong setelah awalan data URI dibuang.",
            400,
        )

    if not _BASE64_CHARS_PATTERN.match(cleaned):
        raise Base64ToolError(
            INVALID_BASE64,
            "Karakter tidak valid untuk Base64. Hanya huruf, angka, +, /, -, _, dan = yang diizinkan.",
            400,
        )

    # Pastikan padding samadengan hanya berada di bagian paling akhir
    unpadded = cleaned.rstrip("=")
    if "=" in unpadded:
        raise Base64ToolError(
            INVALID_BASE64,
            "Tanda samadengan (=) untuk padding berada di posisi yang salah.",
            400,
        )

    rem = len(unpadded) % 4
    if rem == 1:
        # 1 karakter base64 hanya membawa 6 bit sehingga tidak mungkin membentuk byte utuh
        raise Base64ToolError(
            INVALID_BASE64,
            "Panjang teks Base64 tidak valid (tidak mungkin bersisa 1 karakter).",
            400,
        )

    pad_count = len(cleaned) - len(unpadded)
    needed_pad = (4 - rem) % 4

    if rem == 0 and pad_count > 0:
        raise Base64ToolError(
            INVALID_BASE64,
            "Tanda samadengan (=) untuk padding berada di posisi yang salah.",
            400,
        )

    if pad_count > needed_pad:
        raise Base64ToolError(
            INVALID_BASE64,
            "Jumlah tanda samadengan (=) melebihi batas padding yang valid.",
            400,
        )

    # Lengkapi padding yang kurang agar selalu kelipatan 4
    padded = unpadded + ("=" * needed_pad)

    # Terima alfabet urlsafe (- dan _) dengan mentranslasikannya ke standar (+ dan /)
    standard_b64 = padded.replace("-", "+").replace("_", "/")

    try:
        decoded_bytes = base64.b64decode(standard_b64.encode("ascii"), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise Base64ToolError(
            INVALID_BASE64,
            "Format Base64 tidak valid atau data rusak.",
            400,
        ) from exc

    if len(decoded_bytes) > MAX_BYTES:
        max_mb = MAX_BYTES // (1024 * 1024)
        raise Base64ToolError(
            TOO_LONG,
            f"Ukuran hasil dekode ({len(decoded_bytes):,} byte) melebihi batas {max_mb} MB.",
            413,
        )

    try:
        decoded_text = decoded_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Base64ToolError(
            NOT_TEXT,
            "Data Base64 berisi data biner (seperti gambar atau berkas), bukan teks UTF-8 yang dapat dibaca.",
            400,
        ) from exc

    return Base64Result(
        mode="decode",
        text=decoded_text,
        variant="standard",
        wrap=0,
        chars_in=chars_in,
        bytes_in=bytes_in,
        chars_out=len(decoded_text),
        bytes_out=len(decoded_bytes),
        changed=True,
    )


def convert_base64(
    text: str | None,
    mode: str | None,
    variant: str | None = None,
    wrap: int | str | None = None,
) -> Base64Result:
    """Proses teks masukan untuk diubah menjadi Base64 atau sebaliknya."""
    valid_text = validate_text(text)
    valid_mode = normalize_mode(mode)

    if valid_mode == "encode":
        valid_variant = normalize_variant(variant)
        valid_wrap = normalize_wrap(wrap)
        return _encode_text(valid_text, valid_variant, valid_wrap)

    return _decode_text(valid_text)
