"""Logika alat JSON (Rapikan & periksa JSON): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Teks pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

import json
from typing import Any

# Konstanta batas operasional
MAX_BYTES = 1_048_576  # 1 MB
MAX_CHARS = 400_000
MAX_DEPTH = 120
CHUNK_SIZE = 64 * 1024

MODES = ["rapikan", "padatkan", "periksa"]
INDENTS = [2, 4, "tab"]

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NO_TEXT = "NO_TEXT"
TOO_LONG = "TOO_LONG"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
INVALID_JSON = "INVALID_JSON"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
INVALID_INDENT = "INVALID_INDENT"
INVALID_BOOLEAN = "INVALID_BOOLEAN"
TOO_DEEP = "TOO_DEEP"


class JsonToolError(Exception):
    """Galat operasional alat JSON dengan kode galat dan status HTTP."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        res: dict[str, Any] = {"error": {"code": self.code, "message": self.message}}
        if self.detail:
            res["error"]["posisi"] = self.detail
        return res


def _friendly_json_error(exc: json.JSONDecodeError) -> str:
    """Ubah pesan galat teknis JSONDecodeError menjadi kalimat ramah berbahasa Indonesia."""
    msg = exc.msg.lower()
    if "expecting value" in msg:
        if exc.pos == 0:
            return "teks yang ditempel bukan JSON yang sah"
        return "ada tanda koma yang berlebih atau nilai yang belum lengkap"
    if "extra data" in msg:
        return "ada teks tambahan setelah JSON selesai atau tanda koma berlebih"
    if "unterminated string" in msg:
        return "tanda petik penutup teks belum ada"
    if "expecting property name" in msg:
        return "nama kunci harus memakai tanda petik ganda"
    if "expecting ':'" in msg:
        return "kurang tanda titik dua ':' pemisah kunci dan nilai"
    if "expecting ','" in msg:
        return "kurang tanda koma ',' pemisah antar-item"
    return f"struktur JSON tidak sah ({exc.msg})"


def _detect_root_type(val: Any) -> str:
    """Tentukan tipe akar objek JSON dalam Bahasa Indonesia."""
    if isinstance(val, dict):
        return "object"
    if isinstance(val, list):
        return "array"
    if isinstance(val, str):
        return "teks"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return "angka"
    if val is None:
        return "null"
    return "lainnya"


def _hitung_statistik(data: Any, max_depth: int = MAX_DEPTH) -> tuple[int, int, int, int]:
    """Hitung kedalaman, jumlah kunci, jumlah item, dan jumlah daun secara iteratif.

    Mencegah RecursionError dan memastikan kedalaman tidak melebihi MAX_DEPTH.
    Mengembalikan: (kedalaman, jumlah_kunci, jumlah_item, jumlah_daun).
    """
    if not isinstance(data, (dict, list)):
        return 1, 0, 1, 1

    max_d = 1
    total_kunci = 0
    total_item = 0
    total_daun = 0

    # Stack berisi tuple: (node, depth)
    stack: list[tuple[Any, int]] = [(data, 1)]

    while stack:
        node, depth = stack.pop()
        if depth > max_d:
            max_d = depth
        if depth > max_depth:
            raise JsonToolError(
                TOO_DEEP,
                f"Struktur JSON terlalu dalam bersarang (kedalaman {depth} melebihi batas maksimum {max_depth}).",
                400,
            )

        if isinstance(node, dict):
            total_kunci += len(node)
            total_item += len(node)
            if not node:
                total_daun += 1
            else:
                for v in node.values():
                    if isinstance(v, (dict, list)):
                        if depth + 1 > max_depth:
                            raise JsonToolError(
                                TOO_DEEP,
                                f"Struktur JSON terlalu dalam bersarang (kedalaman {depth + 1} melebihi batas maksimum {max_depth}).",
                                400,
                            )
                        stack.append((v, depth + 1))
                    else:
                        if depth + 1 > max_d:
                            max_d = depth + 1
                        total_daun += 1
        elif isinstance(node, list):
            total_item += len(node)
            if not node:
                total_daun += 1
            else:
                for v in node:
                    if isinstance(v, (dict, list)):
                        if depth + 1 > max_depth:
                            raise JsonToolError(
                                TOO_DEEP,
                                f"Struktur JSON terlalu dalam bersarang (kedalaman {depth + 1} melebihi batas maksimum {max_depth}).",
                                400,
                            )
                        stack.append((v, depth + 1))
                    else:
                        if depth + 1 > max_d:
                            max_d = depth + 1
                        total_daun += 1
        else:
            total_daun += 1

    if max_d > max_depth:
        raise JsonToolError(
            TOO_DEEP,
            f"Struktur JSON terlalu dalam bersarang (kedalaman {max_d} melebihi batas maksimum {max_depth}).",
            400,
        )

    return max_d, total_kunci, total_item, total_daun


def proses_json(
    text: Any,
    mode: Any = "rapikan",
    indent: Any = 2,
    urutkan_kunci: Any = False,
) -> dict[str, Any]:
    """Proses teks JSON di memori: validasi, statistik, dan format ulang."""
    if text is None:
        raise JsonToolError(INVALID_REQUEST, "Field teks 'text' wajib diisi.", 400)

    if not isinstance(text, str):
        raise JsonToolError(INVALID_REQUEST, "Field teks 'text' harus berupa teks string.", 400)

    if not text.strip():
        raise JsonToolError(NO_TEXT, "Teks JSON belum diisi. Masukkan atau tempel teks JSON terlebih dahulu.", 400)

    if len(text) > MAX_CHARS:
        raise JsonToolError(
            TOO_LONG,
            f"Panjang masukan ({len(text):,} karakter) melebihi batas {MAX_CHARS:,} karakter.",
            413,
        )

    raw_bytes = text.encode("utf-8")
    if len(raw_bytes) > MAX_BYTES:
        raise JsonToolError(
            PAYLOAD_TOO_LARGE,
            f"Ukuran teks ({len(raw_bytes):,} byte) melebihi batas {MAX_BYTES} byte (1 MB).",
            413,
        )

    if mode is None:
        mode_norm = "rapikan"
    elif isinstance(mode, str):
        mode_norm = mode.strip().lower()
    else:
        raise JsonToolError(INVALID_REQUEST, "Field 'mode' harus berupa string.", 400)

    if mode_norm not in MODES:
        valid_modes = ", ".join(MODES)
        raise JsonToolError(
            UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak didukung. Pilih salah satu: {valid_modes}.",
            400,
        )

    # Validasi pilihan indentasi
    if isinstance(indent, str):
        ind_clean = indent.strip().lower()
        if ind_clean == "2":
            indent_val: int | str = 2
        elif ind_clean == "4":
            indent_val = 4
        elif ind_clean in ("tab", "\t"):
            indent_val = "tab"
        else:
            raise JsonToolError(
                INVALID_INDENT,
                f"Pilihan indentasi '{indent}' tidak valid. Pilih 2, 4, atau 'tab'.",
                400,
            )
    elif isinstance(indent, int):
        if indent == 2:
            indent_val = 2
        elif indent == 4:
            indent_val = 4
        else:
            raise JsonToolError(
                INVALID_INDENT,
                f"Pilihan indentasi '{indent}' tidak valid. Pilih 2, 4, atau 'tab'.",
                400,
            )
    else:
        raise JsonToolError(
            INVALID_INDENT,
            "Pilihan indentasi tidak valid. Pilih 2, 4, atau 'tab'.",
            400,
        )

    # Validasi urutkan_kunci
    if isinstance(urutkan_kunci, bool):
        sort_keys_val = urutkan_kunci
    elif isinstance(urutkan_kunci, str):
        uk_clean = urutkan_kunci.strip().lower()
        if uk_clean in ("true", "1", "yes", "on"):
            sort_keys_val = True
        elif uk_clean in ("false", "0", "no", "off", ""):
            sort_keys_val = False
        else:
            raise JsonToolError(
                INVALID_BOOLEAN,
                f"Nilai urutkan_kunci '{urutkan_kunci}' tidak valid. Gunakan 'true' atau 'false'.",
                400,
            )
    else:
        raise JsonToolError(INVALID_BOOLEAN, "Field 'urutkan_kunci' harus bernilai boolean.", 400)

    # Parsing JSON
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        keterangan = _friendly_json_error(exc)
        pesan = f"Baris {exc.lineno} kolom {exc.colno}: {keterangan}."
        posisi = {"baris": exc.lineno, "kolom": exc.colno, "offset": exc.pos}
        raise JsonToolError(INVALID_JSON, pesan, 400, detail=posisi)
    except RecursionError:
        raise JsonToolError(
            TOO_DEEP,
            f"Struktur JSON terlalu dalam bersarang (melebihi batas kedalaman {MAX_DEPTH}).",
            400,
        )

    kedalaman, jumlah_kunci, jumlah_item, jumlah_daun = _hitung_statistik(parsed, max_depth=MAX_DEPTH)
    akar_type = _detect_root_type(parsed)

    # Pemformatan keluaran
    if mode_norm == "rapikan":
        indent_arg = "\t" if indent_val == "tab" else indent_val
        try:
            out_text = json.dumps(parsed, indent=indent_arg, sort_keys=sort_keys_val, ensure_ascii=False)
        except RecursionError:
            raise JsonToolError(
                TOO_DEEP,
                f"Struktur JSON terlalu dalam bersarang (melebihi batas kedalaman {MAX_DEPTH}).",
                400,
            )
        catatan = "JSON sah dan berhasil dirapikan dengan indentasi."

    elif mode_norm == "padatkan":
        try:
            out_text = json.dumps(parsed, separators=(",", ":"), sort_keys=sort_keys_val, ensure_ascii=False)
        except RecursionError:
            raise JsonToolError(
                TOO_DEEP,
                f"Struktur JSON terlalu dalam bersarang (melebihi batas kedalaman {MAX_DEPTH}).",
                400,
            )
        catatan = "JSON sah dan berhasil dipadatkan jadi satu baris."

    elif mode_norm == "periksa":
        out_text = text
        catatan = "JSON sah dan strukturnya valid (teks masukan tidak diubah)."

    else:
        raise JsonToolError(UNSUPPORTED_MODE, f"Mode '{mode}' tidak didukung.", 400)

    in_lines = len(text.splitlines()) if text else 0
    out_lines = len(out_text.splitlines()) if out_text else 0
    banyak_baris_ditambah = max(0, out_lines - in_lines)

    return {
        "mode": mode_norm,
        "aturan": {"indentasi": indent_val, "urutkan_kunci": sort_keys_val},
        "sah": True,
        "masukan": {
            "chars": len(text),
            "lines": in_lines,
            "bytes": len(raw_bytes),
        },
        "keluaran": {
            "teks": out_text,
            "chars": len(out_text),
            "lines": out_lines,
            "banyak_baris_ditambah": banyak_baris_ditambah,
        },
        "statistik": {
            "akar": akar_type,
            "kedalaman": kedalaman,
            "jumlah_kunci": jumlah_kunci,
            "jumlah_item": jumlah_item,
            "jumlah_daun": jumlah_daun,
        },
        "catatan": catatan,
    }


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional dan daftar mode alat JSON."""
    return {
        "max_bytes": MAX_BYTES,
        "max_chars": MAX_CHARS,
        "max_mb": MAX_BYTES // (1024 * 1024),
        "max_depth": MAX_DEPTH,
        "modes": [
            {
                "value": "rapikan",
                "label": "Rapikan (beri jarak & baris baru)",
                "contoh": "{\n  \"nama\": \"Budi\",\n  \"aktif\": true\n}",
            },
            {
                "value": "padatkan",
                "label": "Padatkan jadi satu baris",
                "contoh": "{\"nama\":\"Budi\",\"aktif\":true}",
            },
            {
                "value": "periksa",
                "label": "Periksa saja (tidak diubah)",
                "contoh": "{\"nama\": \"Budi\", \"aktif\": true}",
            },
        ],
        "indents": [
            {"value": "2", "label": "2 spasi"},
            {"value": "4", "label": "4 spasi"},
            {"value": "tab", "label": "Tab"},
        ],
        "processed_on": "server",
        "note": "Teks diproses di memori lalu dibuang, tidak disimpan di disk.",
    }
