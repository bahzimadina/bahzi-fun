"""Logika perapian teks (Text Formatter): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Teks pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

import re
from typing import Any

# Batas operasional teks di memori
MAX_CHARS = 200_000
MAX_BYTES = 1_000_000
CHUNK_SIZE = 1024 * 1024

# Pilihan yang didukung
BLANK_MODES: dict[str, str] = {
    "keep": "Biarkan baris kosong",
    "collapse": "Rapatkan baris kosong jadi maksimal satu",
    "remove": "Buang semua baris kosong",
}

LINE_MODES: dict[str, str] = {
    "keep": "Biarkan susunan baris",
    "paragraph": "Gabung baris berdampingan jadi paragraf",
    "single": "Jadikan satu baris",
}

TAB_WIDTHS: set[int] = {2, 4, 8}

# Kode galat stabil
NO_TEXT = "NO_TEXT"
TOO_LONG = "TOO_LONG"
UNSUPPORTED_BLANK_MODE = "UNSUPPORTED_BLANK_MODE"
UNSUPPORTED_LINE_MODE = "UNSUPPORTED_LINE_MODE"
INVALID_BOOLEAN = "INVALID_BOOLEAN"
INVALID_TAB_WIDTH = "INVALID_TAB_WIDTH"
NOT_TEXT = "NOT_TEXT"
INVALID_REQUEST = "INVALID_REQUEST"


class TextFormatterError(ValueError):
    """Galat operasional perapian teks dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


def check_size(text: str) -> None:
    """Periksa batas ukuran byte UTF-8 teks."""
    encoded_bytes = len(text.encode("utf-8"))
    if encoded_bytes > MAX_BYTES:
        raise TextFormatterError(
            TOO_LONG,
            f"Ukuran byte teks ({encoded_bytes:,} byte) melebihi batas 1 MB.",
            413,
        )


def validate_text(text: Any) -> str:
    """Validasi teks masukan terhadap ketiadaan field, tipe, dan panjang karakter."""
    if text is None:
        raise TextFormatterError(NO_TEXT, "Field teks 'text' wajib diisi.", 400)

    if not isinstance(text, str):
        raise TextFormatterError(NOT_TEXT, "Field 'text' harus berupa teks string.", 400)

    if len(text) > MAX_CHARS:
        raise TextFormatterError(
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
        raise TextFormatterError(INVALID_BOOLEAN, f"Nilai boolean untuk '{field_name}' wajib diisi.", 400)

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        raise TextFormatterError(
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
        raise TextFormatterError(
            INVALID_BOOLEAN,
            f"Nilai boolean untuk '{field_name}' tidak valid. Gunakan true/false, 1/0, ya/tidak, atau on/off.",
            400,
        )

    raise TextFormatterError(
        INVALID_BOOLEAN,
        f"Nilai boolean untuk '{field_name}' tidak valid. Gunakan true/false, 1/0, ya/tidak, atau on/off.",
        400,
    )


def parse_tab_width(value: Any, default: int = 4) -> int:
    """Validasi lebar tab (hanya 2, 4, atau 8)."""
    if value is None or value == "":
        return default

    if isinstance(value, int) and not isinstance(value, bool):
        num = value
    elif isinstance(value, str):
        try:
            num = int(value.strip())
        except ValueError:
            raise TextFormatterError(INVALID_TAB_WIDTH, "Lebar tab tidak valid. Pilih 2, 4, atau 8.", 400)
    else:
        raise TextFormatterError(INVALID_TAB_WIDTH, "Lebar tab tidak valid. Pilih 2, 4, atau 8.", 400)

    if num not in TAB_WIDTHS:
        raise TextFormatterError(INVALID_TAB_WIDTH, "Lebar tab tidak valid. Pilih 2, 4, atau 8.", 400)

    return num


def normalize_blank_mode(value: Any, default: str = "collapse") -> str:
    """Validasi mode penanganan baris kosong."""
    if value is None or value == "":
        return default

    if not isinstance(value, str):
        raise TextFormatterError(UNSUPPORTED_BLANK_MODE, "Pilihan baris kosong tidak valid.", 400)

    norm = value.strip().lower()
    if norm not in BLANK_MODES:
        raise TextFormatterError(
            UNSUPPORTED_BLANK_MODE,
            "Pilihan baris kosong tidak valid. Pilih 'keep', 'collapse', atau 'remove'.",
            400,
        )

    return norm


def normalize_line_mode(value: Any, default: str = "keep") -> str:
    """Validasi mode susunan baris."""
    if value is None or value == "":
        return default

    if not isinstance(value, str):
        raise TextFormatterError(UNSUPPORTED_LINE_MODE, "Pilihan format baris tidak valid.", 400)

    norm = value.strip().lower()
    if norm not in LINE_MODES:
        raise TextFormatterError(
            UNSUPPORTED_LINE_MODE,
            "Pilihan format baris tidak valid. Pilih 'keep', 'paragraph', atau 'single'.",
            400,
        )

    return norm


def format_text(
    text: Any,
    *,
    collapse_spaces: bool | str | None = True,
    trim_lines: bool | str | None = True,
    tabs_to_spaces: bool | str | None = True,
    tab_width: int | str | None = 4,
    space_before_punctuation: bool | str | None = True,
    unify_characters: bool | str | None = True,
    blank_mode: str | None = "collapse",
    line_mode: str | None = "keep",
) -> dict[str, Any]:
    """Rapikan teks sesuai urutan kerja standar."""
    valid_text = validate_text(text)
    valid_collapse_spaces = parse_bool(collapse_spaces, "collapse_spaces", default=True)
    valid_trim_lines = parse_bool(trim_lines, "trim_lines", default=True)
    valid_tabs_to_spaces = parse_bool(tabs_to_spaces, "tabs_to_spaces", default=True)
    valid_tab_width = parse_tab_width(tab_width, default=4)
    valid_space_before_punctuation = parse_bool(space_before_punctuation, "space_before_punctuation", default=True)
    valid_unify_characters = parse_bool(unify_characters, "unify_characters", default=True)
    valid_blank_mode = normalize_blank_mode(blank_mode, default="collapse")
    valid_line_mode = normalize_line_mode(line_mode, default="keep")

    pilihan = {
        "collapse_spaces": valid_collapse_spaces,
        "trim_lines": valid_trim_lines,
        "tabs_to_spaces": valid_tabs_to_spaces,
        "tab_width": valid_tab_width,
        "space_before_punctuation": valid_space_before_punctuation,
        "unify_characters": valid_unify_characters,
        "blank_mode": valid_blank_mode,
        "line_mode": valid_line_mode,
    }

    raw_normalized = valid_text.replace("\r\n", "\n").replace("\r", "\n")

    # Kasus teks kosong atau hanya berisi spasi
    if not valid_text.strip():
        in_lines = 0 if not valid_text else len(raw_normalized.split("\n"))
        return {
            "text": "",
            "masukan": {
                "chars": len(raw_normalized),
                "lines": in_lines,
                "blank_lines": in_lines,
            },
            "keluaran": {
                "chars": 0,
                "lines": 0,
                "blank_lines": 0,
            },
            "dihemat": {
                "chars": len(raw_normalized),
                "lines": in_lines,
            },
            "pilihan": pilihan,
        }

    # Hitung metrik masukan asli
    raw_lines = raw_normalized.split("\n")
    chars_in = len(raw_normalized)
    lines_in = len(raw_lines)
    blank_lines_in = sum(1 for line in raw_lines if line.strip() == "")

    # 1. Seragamkan akhir baris (\r\n dan \r menjadi \n)
    normalized = raw_normalized

    # 2. Kalau tabs_to_spaces: ganti tiap tab dengan tab_width spasi
    if valid_tabs_to_spaces:
        normalized = normalized.replace("\t", " " * valid_tab_width)

    current_lines = normalized.split("\n")

    # 3. Kalau trim_lines: buang spasi dan tab di awal dan akhir setiap baris
    if valid_trim_lines:
        current_lines = [line.strip(" \t") for line in current_lines]

    # 4. Kalau collapse_spaces: ubah setiap rentetan dua spasi atau lebih menjadi satu spasi
    if valid_collapse_spaces:
        current_lines = [re.sub(r" {2,}", " ", line) for line in current_lines]

    # 5. Kalau space_before_punctuation: buang spasi sebelum , . ; : ! ? dan sebelum ) dan ]
    if valid_space_before_punctuation:
        current_lines = [re.sub(r" +([,.;:!?\)\]])", r"\1", line) for line in current_lines]

    # 6. Kalau unify_characters: samakan tanda kutip, tanda pisah, elipsis, dan spasi khusus
    if valid_unify_characters:
        unify_table = str.maketrans({
            "\u201c": '"',
            "\u201d": '"',
            "\u201e": '"',
            "\u201f": '"',
            "\u2018": "'",
            "\u2019": "'",
            "\u201a": "'",
            "\u201b": "'",
            "\u2014": "-",
            "\u2013": "-",
            "\u2015": "-",
            "\u2026": "...",
            "\u00a0": " ",
            "\u202f": " ",
            "\u2007": " ",
        })
        current_lines = [line.translate(unify_table) for line in current_lines]

    # 7 & 8. Pengolahan blank_mode dan line_mode
    if valid_line_mode == "single":
        non_empty = [line for line in current_lines if line.strip() != ""]
        result_text = " ".join(non_empty).strip()

    elif valid_line_mode == "paragraph":
        # Kelompokkan baris non-kosong berdampingan dan jeda baris kosong
        tokens: list[tuple[str, Any]] = []
        cur_para: list[str] = []
        cur_blanks = 0

        for line in current_lines:
            if line.strip() != "":
                if cur_blanks > 0:
                    tokens.append(("blank", cur_blanks))
                    cur_blanks = 0
                cur_para.append(line)
            else:
                if cur_para:
                    tokens.append(("para", " ".join(cur_para)))
                    cur_para = []
                cur_blanks += 1

        if cur_para:
            tokens.append(("para", " ".join(cur_para)))
        if cur_blanks > 0:
            tokens.append(("blank", cur_blanks))

        # Rakit paragraf dengan penghormatan blank_mode
        parts: list[str] = []
        for kind, val in tokens:
            if kind == "para":
                parts.append(val)
            elif kind == "blank":
                if valid_blank_mode == "remove":
                    parts.append("\n")
                elif valid_blank_mode == "collapse":
                    parts.append("\n\n")
                else:
                    parts.append("\n" * (val + 1))

        # Gabungkan dan rapikan ujung
        result_text = "".join(parts).strip()

    else:
        # line_mode == "keep": terapkan blank_mode langsung pada baris
        if valid_blank_mode == "remove":
            filtered_lines = [line for line in current_lines if line.strip() != ""]
        elif valid_blank_mode == "collapse":
            filtered_lines = []
            prev_blank = False
            for line in current_lines:
                is_blank = (line.strip() == "")
                if is_blank:
                    if not prev_blank:
                        filtered_lines.append("")
                        prev_blank = True
                else:
                    filtered_lines.append(line)
                    prev_blank = False
        else:
            filtered_lines = current_lines

        result_text = "\n".join(filtered_lines).strip()

    if not result_text:
        chars_out = 0
        lines_out = 0
        blank_lines_out = 0
    else:
        out_lines = result_text.split("\n")
        chars_out = len(result_text)
        lines_out = len(out_lines)
        blank_lines_out = sum(1 for line in out_lines if line.strip() == "")

    return {
        "text": result_text,
        "masukan": {
            "chars": chars_in,
            "lines": lines_in,
            "blank_lines": blank_lines_in,
        },
        "keluaran": {
            "chars": chars_out,
            "lines": lines_out,
            "blank_lines": blank_lines_out,
        },
        "dihemat": {
            "chars": max(0, chars_in - chars_out),
            "lines": max(0, lines_in - lines_out),
        },
        "pilihan": pilihan,
    }
