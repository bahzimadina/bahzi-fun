"""Logika alat CSV (CSV Tools): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Teks pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import re
from typing import Any

# Konstanta batas operasional
MAX_BYTES = 1_048_576  # 1 MB
MAX_CHARS = 400_000
MAX_ROWS = 20_000
MAX_COLS = 200
CHUNK_SIZE = 64 * 1024

MODES = ["ke_json", "ke_csv", "ringkas"]
PEMISAH_MAP = {
    "koma": ",",
    "titik_koma": ";",
    "tab": "\t",
    "pipa": "|",
}
PEMISAH_NAMES = {
    ",": "koma",
    ";": "titik_koma",
    "\t": "tab",
    "|": "pipa",
}
INDENTS = ["2", "4", "tab"]

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NO_TEXT = "NO_TEXT"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
INVALID_SEPARATOR = "INVALID_SEPARATOR"
INVALID_BOOLEAN = "INVALID_BOOLEAN"
INVALID_INDENT = "INVALID_INDENT"
INVALID_JSON = "INVALID_JSON"
INVALID_FORMAT = "INVALID_FORMAT"
TOO_LONG = "TOO_LONG"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
TOO_MANY_ROWS = "TOO_MANY_ROWS"
TOO_MANY_COLUMNS = "TOO_MANY_COLUMNS"


class CsvToolError(ValueError):
    """Galat operasional alat CSV dengan kode galat dan status HTTP."""

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


def _parse_bool(val: Any, field_name: str, default: bool = True) -> bool:
    """Validasi dan parsing nilai boolean dari string 'ya' / 'tidak'."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        clean = val.strip().lower()
        if clean in ("ya", "true", "1", "yes"):
            return True
        if clean in ("tidak", "false", "0", "no"):
            return False
        raise CsvToolError(
            INVALID_BOOLEAN,
            f"Nilai field '{field_name}' tidak valid. Gunakan 'ya' atau 'tidak'.",
            400,
        )
    raise CsvToolError(
        INVALID_BOOLEAN,
        f"Field '{field_name}' harus bernilai teks 'ya' atau 'tidak'.",
        400,
    )


def _tebak_pemisah_dari_baris(baris: str) -> tuple[str, str]:
    """Tebak karakter pemisah (, ; \\t |) dari baris teks pertama di luar tanda kutip."""
    counts = {",": 0, ";": 0, "\t": 0, "|": 0}
    inside_quote = False
    length = len(baris)
    i = 0
    while i < length:
        ch = baris[i]
        if ch == '"':
            if inside_quote and i + 1 < length and baris[i + 1] == '"':
                i += 1  # lewati tanda kutip ganda RFC 4180
            else:
                inside_quote = not inside_quote
        elif not inside_quote and ch in counts:
            counts[ch] += 1
        i += 1

    # Cari pemisah dengan hitungan terbanyak
    best_delim = ","
    best_count = 0
    for delim in (",", ";", "\t", "|"):
        if counts[delim] > best_count:
            best_count = counts[delim]
            best_delim = delim

    return best_delim, PEMISAH_NAMES.get(best_delim, "koma")


def _resolve_pemisah(pemisah_opt: Any, sample_text: str) -> tuple[str, str]:
    """Tentukan karakter pemisah dan nama labelnya."""
    if pemisah_opt is None or str(pemisah_opt).strip() == "" or str(pemisah_opt).strip().lower() == "otomatis":
        first_line = sample_text.splitlines()[0] if sample_text.splitlines() else ""
        return _tebak_pemisah_dari_baris(first_line)

    opt_clean = str(pemisah_opt).strip().lower()
    if opt_clean in PEMISAH_MAP:
        return PEMISAH_MAP[opt_clean], opt_clean

    valid_opts = ", ".join(["otomatis"] + list(PEMISAH_MAP.keys()))
    raise CsvToolError(
        INVALID_SEPARATOR,
        f"Pemisah '{pemisah_opt}' tidak didukung. Pilih salah satu: {valid_opts}.",
        400,
    )


def _resolve_indent(indent_opt: Any) -> str | int:
    """Validasi pilihan indentasi untuk mode ke_json."""
    if indent_opt is None or str(indent_opt).strip() == "":
        return 2

    val_str = str(indent_opt).strip().lower()
    if val_str == "2":
        return 2
    if val_str == "4":
        return 4
    if val_str in ("tab", "\t"):
        return "tab"

    raise CsvToolError(
        INVALID_INDENT,
        f"Pilihan indentasi '{indent_opt}' tidak valid. Pilih 2, 4, atau 'tab'.",
        400,
    )


def _cell_to_csv_str(val: Any, rapikan: bool) -> str:
    """Konversi nilai sel JSON menjadi teks string CSV."""
    if val is None:
        return ""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (dict, list)):
        return json.dumps(val, separators=(",", ":"), ensure_ascii=False)
    if isinstance(val, str):
        return val.strip() if rapikan else val
    return str(val)


def _is_json_payload(text: str) -> bool:
    """Periksa apakah teks masukan tampak seperti data JSON."""
    s = text.strip()
    if not (s.startswith("{") or s.startswith("[")):
        return False
    try:
        json.loads(s)
        return True
    except Exception:
        return False


def _try_parse_number(val: str) -> float | int | None:
    """Mencoba parsing angka int atau float dari string."""
    s = val.strip()
    if not s:
        return None
    # Pola angka standar: 123, -456, 12.34
    if re.fullmatch(r"-?\d+", s):
        try:
            return int(s)
        except ValueError:
            return None
    if re.fullmatch(r"-?\d+\.\d+", s):
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _try_parse_date(val: str) -> str | None:
    """Mencoba mendeteksi format tanggal umum."""
    s = val.strip()
    if not s:
        return None
    # YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            datetime.date.fromisoformat(s)
            return s
        except ValueError:
            return None
    # YYYY/MM/DD
    if re.fullmatch(r"\d{4}/\d{2}/\d{2}", s):
        try:
            parts = [int(p) for p in s.split("/")]
            datetime.date(parts[0], parts[1], parts[2])
            return s
        except ValueError:
            return None
    # DD/MM/YYYY atau DD-MM-YYYY
    match_dmy = re.fullmatch(r"(\d{2})[-/](\d{2})[-/](\d{4})", s)
    if match_dmy:
        d, m, y = int(match_dmy.group(1)), int(match_dmy.group(2)), int(match_dmy.group(3))
        try:
            datetime.date(y, m, d)
            return s
        except ValueError:
            return None
    # ISO datetime: YYYY-MM-DDTHH:MM:SS
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?", s):
        return s[:10]
    return None


def _proses_ke_json(
    teks: str,
    pemisah_opt: Any,
    header_val: bool,
    rapikan_val: bool,
    indent_val: str | int,
) -> dict[str, Any]:
    """Konversi teks CSV menjadi data JSON."""
    if _is_json_payload(teks):
        raise CsvToolError(
            INVALID_FORMAT,
            "Teks masukan berupa format JSON. Gunakan mode 'Ubah JSON jadi CSV' untuk data JSON.",
            400,
        )

    char_delim, pemisah_name = _resolve_pemisah(pemisah_opt, teks)

    try:
        reader = csv.reader(io.StringIO(teks), delimiter=char_delim, quotechar='"')
        raw_rows = list(reader)
    except Exception as exc:
        raise CsvToolError(INVALID_FORMAT, f"Gagal membaca data CSV: {exc}", 400)

    rows: list[list[str]] = []
    for r in raw_rows:
        if rapikan_val:
            cleaned = [c.strip() for c in r]
            if not cleaned or all(c == "" for c in cleaned):
                continue
            rows.append(cleaned)
        else:
            rows.append(r)

    if not rows:
        raise CsvToolError(NO_TEXT, "Data CSV tidak berisi baris yang dapat dibaca.", 400)

    if len(rows) > MAX_ROWS:
        raise CsvToolError(
            TOO_MANY_ROWS,
            f"Jumlah baris ({len(rows):,}) melebihi batas maksimal {MAX_ROWS:,} baris.",
            413,
        )

    max_cols = max(len(r) for r in rows)
    if max_cols > MAX_COLS:
        raise CsvToolError(
            TOO_MANY_COLUMNS,
            f"Jumlah kolom ({max_cols:,}) melebihi batas maksimal {MAX_COLS} kolom.",
            413,
        )

    catatan = ""
    if header_val:
        header_raw = rows[0]
        data_rows = rows[1:]

        # Penamaan otomatis untuk kunci kosong atau ganda
        header_keys: list[str] = []
        counts: dict[str, int] = {}
        for idx, col_name in enumerate(header_raw):
            base = col_name if col_name != "" else f"kolom_{idx + 1}"
            if base not in counts:
                counts[base] = 1
                header_keys.append(base)
            else:
                counts[base] += 1
                header_keys.append(f"{base}_{counts[base]}")

        has_extra_cols = False
        data_objects: list[dict[str, Any]] = []
        for r in data_rows:
            obj: dict[str, Any] = {}
            for i, k in enumerate(header_keys):
                obj[k] = r[i] if i < len(r) else ""
            if len(r) > len(header_keys):
                has_extra_cols = True
                for j in range(len(header_keys), len(r)):
                    extra_num = j - len(header_keys) + 1
                    obj[f"kolom_tambahan_{extra_num}"] = r[j]
            data_objects.append(obj)

        if has_extra_cols:
            catatan = "Beberapa baris memiliki sel lebih banyak dari header dan disimpan sebagai kolom_tambahan."
        else:
            catatan = "Berhasil mengubah CSV menjadi array objek JSON."

        data_output: Any = data_objects
        total_baris_data = len(data_rows)
        total_kolom_data = max(max_cols, len(header_keys))
    else:
        data_output = rows
        total_baris_data = len(rows)
        total_kolom_data = max_cols
        catatan = "Berhasil mengubah CSV menjadi array data JSON."

    indent_arg = "\t" if indent_val == "tab" else indent_val
    out_text = json.dumps(data_output, indent=indent_arg, ensure_ascii=False)

    return {
        "mode": "ke_json",
        "pemisah_terpakai": pemisah_name,
        "header": "ya" if header_val else "tidak",
        "rapikan": "ya" if rapikan_val else "tidak",
        "indent": indent_val,
        "ringkasan": {
            "jumlah_baris": total_baris_data,
            "jumlah_kolom": total_kolom_data,
            "pemisah_terpakai": pemisah_name,
        },
        "keluaran": {
            "teks": out_text,
            "chars": len(out_text),
            "lines": len(out_text.splitlines()),
            "data": data_output,
        },
        "catatan": catatan,
    }


def _proses_ke_csv(
    teks: str,
    pemisah_opt: Any,
    rapikan_val: bool,
) -> dict[str, Any]:
    """Konversi teks JSON menjadi format CSV."""
    try:
        parsed = json.loads(teks)
    except json.JSONDecodeError as exc:
        keterangan = _friendly_json_error(exc)
        posisi = {"baris": exc.lineno, "kolom": exc.colno, "offset": exc.pos}
        raise CsvToolError(
            INVALID_JSON,
            f"Baris {exc.lineno} kolom {exc.colno}: {keterangan}.",
            400,
            detail=posisi,
        )

    # Ekstrak dari objek pembungkus (data, items, rows) jika ada
    target_data = parsed
    if isinstance(target_data, dict):
        for wrapper_key in ("data", "items", "rows"):
            if wrapper_key in target_data and isinstance(target_data[wrapper_key], list):
                target_data = target_data[wrapper_key]
                break

    if not isinstance(target_data, list):
        raise CsvToolError(
            INVALID_FORMAT,
            "Struktur JSON tidak didukung untuk konversi CSV. Gunakan array objek, array dari array, atau objek dengan field 'data', 'items', atau 'rows'.",
            400,
        )

    # Tentukan karakter pemisah
    if pemisah_opt is None or str(pemisah_opt).strip() == "" or str(pemisah_opt).strip().lower() == "otomatis":
        char_delim = ","
        pemisah_name = "koma"
    else:
        opt_clean = str(pemisah_opt).strip().lower()
        if opt_clean in PEMISAH_MAP:
            char_delim = PEMISAH_MAP[opt_clean]
            pemisah_name = opt_clean
        else:
            valid_opts = ", ".join(["otomatis"] + list(PEMISAH_MAP.keys()))
            raise CsvToolError(
                INVALID_SEPARATOR,
                f"Pemisah '{pemisah_opt}' tidak didukung. Pilih salah satu: {valid_opts}.",
                400,
            )

    rows: list[list[str]] = []
    if not target_data:
        total_baris = 0
        total_kolom = 0
        out_csv = ""
    else:
        first_elem = target_data[0]
        if isinstance(first_elem, dict):
            # Array objek: kumpulkan kunci unik menurut kemunculan pertama
            headers: list[str] = []
            seen_keys: set[str] = set()
            for item in target_data:
                if isinstance(item, dict):
                    for k in item.keys():
                        if k not in seen_keys:
                            seen_keys.add(k)
                            headers.append(k)

            if len(headers) > MAX_COLS:
                raise CsvToolError(
                    TOO_MANY_COLUMNS,
                    f"Jumlah kolom ({len(headers):,}) melebihi batas {MAX_COLS} kolom.",
                    413,
                )

            rows.append(headers)
            for item in target_data:
                if isinstance(item, dict):
                    row = [_cell_to_csv_str(item.get(h), rapikan=rapikan_val) for h in headers]
                    if rapikan_val and all(c == "" for c in row):
                        continue
                    rows.append(row)
            total_baris = max(0, len(rows) - 1)
            total_kolom = len(headers)
        elif isinstance(first_elem, list):
            # Array dari array
            for item in target_data:
                if isinstance(item, list):
                    row = [_cell_to_csv_str(v, rapikan=rapikan_val) for v in item]
                    if rapikan_val and all(c == "" for c in row):
                        continue
                    rows.append(row)
                else:
                    rows.append([_cell_to_csv_str(item, rapikan=rapikan_val)])
            total_baris = len(rows)
            total_kolom = max((len(r) for r in rows), default=0)
            if total_kolom > MAX_COLS:
                raise CsvToolError(
                    TOO_MANY_COLUMNS,
                    f"Jumlah kolom ({total_kolom:,}) melebihi batas {MAX_COLS} kolom.",
                    413,
                )
        else:
            # Array skalar
            for item in target_data:
                rows.append([_cell_to_csv_str(item, rapikan=rapikan_val)])
            total_baris = len(rows)
            total_kolom = 1

        if len(rows) > MAX_ROWS:
            raise CsvToolError(
                TOO_MANY_ROWS,
                f"Jumlah baris ({len(rows):,}) melebihi batas {MAX_ROWS:,} baris.",
                413,
            )

        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=char_delim, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        for r in rows:
            writer.writerow(r)
        out_csv = buf.getvalue()

    return {
        "mode": "ke_csv",
        "pemisah_terpakai": pemisah_name,
        "rapikan": "ya" if rapikan_val else "tidak",
        "ringkasan": {
            "jumlah_baris": total_baris,
            "jumlah_kolom": total_kolom,
            "pemisah_terpakai": pemisah_name,
        },
        "keluaran": {
            "teks": out_csv,
            "chars": len(out_csv),
            "lines": len(out_csv.splitlines()),
        },
        "catatan": "Berhasil mengubah data JSON menjadi format CSV.",
    }


def _proses_ringkas(
    teks: str,
    pemisah_opt: Any,
    header_val: bool,
    rapikan_val: bool,
) -> dict[str, Any]:
    """Menganalisis kolom dan menghasilkan ringkasan tipe data serta statistik."""
    if _is_json_payload(teks):
        raise CsvToolError(
            INVALID_FORMAT,
            "Teks masukan berupa format JSON. Mode ringkas memerlukan masukan data tabel CSV.",
            400,
        )

    char_delim, pemisah_name = _resolve_pemisah(pemisah_opt, teks)

    try:
        reader = csv.reader(io.StringIO(teks), delimiter=char_delim, quotechar='"')
        raw_rows = list(reader)
    except Exception as exc:
        raise CsvToolError(INVALID_FORMAT, f"Gagal membaca data CSV: {exc}", 400)

    rows: list[list[str]] = []
    for r in raw_rows:
        if rapikan_val:
            cleaned = [c.strip() for c in r]
            if not cleaned or all(c == "" for c in cleaned):
                continue
            rows.append(cleaned)
        else:
            rows.append(r)

    if not rows:
        raise CsvToolError(NO_TEXT, "Data CSV tidak berisi baris yang dapat dibaca.", 400)

    if len(rows) > MAX_ROWS:
        raise CsvToolError(
            TOO_MANY_ROWS,
            f"Jumlah baris ({len(rows):,}) melebihi batas maksimal {MAX_ROWS:,} baris.",
            413,
        )

    max_cols = max(len(r) for r in rows)
    if max_cols > MAX_COLS:
        raise CsvToolError(
            TOO_MANY_COLUMNS,
            f"Jumlah kolom ({max_cols:,}) melebihi batas maksimal {MAX_COLS} kolom.",
            413,
        )

    if header_val:
        header_raw = rows[0]
        data_rows = rows[1:]
        column_names: list[str] = []
        counts: dict[str, int] = {}
        for idx in range(max_cols):
            raw_name = header_raw[idx] if idx < len(header_raw) else ""
            base = raw_name if raw_name != "" else f"kolom_{idx + 1}"
            if base not in counts:
                counts[base] = 1
                column_names.append(base)
            else:
                counts[base] += 1
                column_names.append(f"{base}_{counts[base]}")
    else:
        data_rows = rows
        column_names = [f"kolom_{idx + 1}" for idx in range(max_cols)]

    total_baris = len(data_rows)
    kolom_ringkasan: list[dict[str, Any]] = []
    kolom_kosong_count = 0

    for col_idx in range(max_cols):
        col_name = column_names[col_idx]
        col_values: list[str] = []
        for r in data_rows:
            v = r[col_idx] if col_idx < len(r) else ""
            col_values.append(v)

        sel_kosong = sum(1 for v in col_values if v == "")
        non_empty = [v for v in col_values if v != ""]
        unique_vals = list(set(non_empty))
        nilai_unik = len(unique_vals)

        if not non_empty:
            tipe = "kosong"
            kolom_kosong_count += 1
            min_val = None
            max_val = None
            nilai_terbanyak: list[dict[str, Any]] = []
        else:
            # Periksa tipe masing-masing nilai non-kosong
            count_angka = 0
            count_tanggal = 0
            angka_list: list[float | int] = []
            tanggal_list: list[str] = []

            for val in non_empty:
                num = _try_parse_number(val)
                if num is not None:
                    count_angka += 1
                    angka_list.append(num)
                    continue

                dt = _try_parse_date(val)
                if dt is not None:
                    count_tanggal += 1
                    tanggal_list.append(dt)
                    continue

            total_non_empty = len(non_empty)
            if count_angka == total_non_empty:
                tipe = "angka"
                min_val = min(angka_list)
                max_val = max(angka_list)
                nilai_terbanyak = []
            elif count_tanggal == total_non_empty:
                tipe = "tanggal"
                min_val = min(tanggal_list)
                max_val = max(tanggal_list)
                nilai_terbanyak = []
            elif count_angka == 0 and count_tanggal == 0:
                tipe = "teks"
                min_val = None
                max_val = None
                # Hitung 3 nilai paling sering muncul
                freq: dict[str, int] = {}
                for v in non_empty:
                    freq[v] = freq.get(v, 0) + 1
                sorted_freq = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
                nilai_terbanyak = [{"nilai": k, "jumlah": v} for k, v in sorted_freq[:3]]
            else:
                tipe = "campuran"
                min_val = None
                max_val = None
                freq = {}
                for v in non_empty:
                    freq[v] = freq.get(v, 0) + 1
                sorted_freq = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
                nilai_terbanyak = [{"nilai": k, "jumlah": v} for k, v in sorted_freq[:3]]

        item_kolom: dict[str, Any] = {
            "indeks": col_idx + 1,
            "nama": col_name,
            "tipe": tipe,
            "sel_kosong": sel_kosong,
            "nilai_unik": nilai_unik,
        }
        if min_val is not None:
            item_kolom["nilai_terkecil"] = min_val
        if max_val is not None:
            item_kolom["nilai_terbesar"] = max_val
        if nilai_terbanyak:
            item_kolom["nilai_terbanyak"] = nilai_terbanyak

        kolom_ringkasan.append(item_kolom)

    # Format teks ringkasan untuk kemudahan salin dan unduh
    lines_txt = [
        "Ringkasan Kolom CSV (bahzi.fun)",
        f"Total baris data : {total_baris}",
        f"Total kolom      : {max_cols}",
        f"Kolom kosong     : {kolom_kosong_count}",
        f"Pemisah terpakai : {pemisah_name}",
        "",
        "Rincian Kolom:",
    ]
    for c in kolom_ringkasan:
        line = f"- #{c['indeks']} {c['nama']} ({c['tipe']}): {c['sel_kosong']} kosong, {c['nilai_unik']} unik"
        if "nilai_terkecil" in c and "nilai_terbesar" in c:
            line += f", rentang: {c['nilai_terkecil']} s.d. {c['nilai_terbesar']}"
        elif "nilai_terbanyak" in c and c["nilai_terbanyak"]:
            top_str = ", ".join(f"\"{t['nilai']}\" ({t['jumlah']}x)" for t in c["nilai_terbanyak"])
            line += f", terbanyak: {top_str}"
        lines_txt.append(line)

    text_summary = "\n".join(lines_txt)

    return {
        "mode": "ringkas",
        "pemisah_terpakai": pemisah_name,
        "header": "ya" if header_val else "tidak",
        "rapikan": "ya" if rapikan_val else "tidak",
        "ringkasan": {
            "total_baris": total_baris,
            "total_kolom": max_cols,
            "kolom_kosong": kolom_kosong_count,
            "pemisah_terpakai": pemisah_name,
        },
        "kolom": kolom_ringkasan,
        "keluaran": {
            "teks": text_summary,
            "chars": len(text_summary),
            "lines": len(lines_txt),
        },
        "catatan": f"Analisis selesai untuk {max_cols} kolom dan {total_baris} baris data.",
    }


def proses_csv(
    teks: Any,
    mode: Any,
    pemisah: Any = "otomatis",
    header: Any = "ya",
    rapikan: Any = "ya",
    indent: Any = "2",
) -> dict[str, Any]:
    """Eksekusi pemrosesan alat CSV di memori sesuai mode."""
    if teks is None:
        raise CsvToolError(NO_TEXT, "Field 'teks' belum diisi. Masukkan data CSV atau JSON terlebih dahulu.", 400)
    if not isinstance(teks, str):
        raise CsvToolError(INVALID_REQUEST, "Field 'teks' harus berupa string.", 400)
    if not teks.strip():
        raise CsvToolError(NO_TEXT, "Field 'teks' belum diisi. Masukkan data CSV atau JSON terlebih dahulu.", 400)

    if len(teks) > MAX_CHARS:
        raise CsvToolError(
            TOO_LONG,
            f"Panjang teks ({len(teks):,} karakter) melebihi batas {MAX_CHARS:,} karakter.",
            413,
        )

    raw_bytes = teks.encode("utf-8")
    if len(raw_bytes) > MAX_BYTES:
        raise CsvToolError(
            PAYLOAD_TOO_LARGE,
            f"Ukuran teks ({len(raw_bytes):,} byte) melebihi batas {MAX_BYTES} byte (1 MB).",
            413,
        )

    if mode is None or not str(mode).strip():
        raise CsvToolError(INVALID_REQUEST, "Field 'mode' wajib diisi.", 400)
    if not isinstance(mode, str):
        raise CsvToolError(INVALID_REQUEST, "Field 'mode' harus berupa string.", 400)

    mode_norm = mode.strip().lower()
    if mode_norm not in MODES:
        valid_modes = ", ".join(MODES)
        raise CsvToolError(
            UNSUPPORTED_MODE,
            f"Mode '{mode}' tidak didukung. Pilih salah satu: {valid_modes}.",
            400,
        )

    header_val = _parse_bool(header, "header", default=True)
    rapikan_val = _parse_bool(rapikan, "rapikan", default=True)
    indent_val = _resolve_indent(indent)

    if mode_norm == "ke_json":
        return _proses_ke_json(teks, pemisah, header_val, rapikan_val, indent_val)
    if mode_norm == "ke_csv":
        return _proses_ke_csv(teks, pemisah, rapikan_val)
    return _proses_ringkas(teks, pemisah, header_val, rapikan_val)


def limits_payload() -> dict[str, Any]:
    """Kembalikan batas operasional dan konfigurasi alat CSV."""
    return {
        "modes": [
            {
                "id": "ke_json",
                "value": "ke_json",
                "label": "Ubah CSV jadi JSON",
                "desc": "Konversi tabel CSV menjadi array objek atau array JSON",
            },
            {
                "id": "ke_csv",
                "value": "ke_csv",
                "label": "Ubah JSON jadi CSV",
                "desc": "Konversi data JSON menjadi tabel CSV",
            },
            {
                "id": "ringkas",
                "value": "ringkas",
                "label": "Ringkasan kolom CSV",
                "desc": "Lihat tipe dugaan, keunikan, nilai ekstrem, dan statistik per kolom",
            },
        ],
        "separators": [
            {"id": "otomatis", "value": "otomatis", "label": "Otomatis tebak"},
            {"id": "koma", "value": "koma", "label": "Koma (,)"},
            {"id": "titik_koma", "value": "titik_koma", "label": "Titik koma (;)"},
            {"id": "tab", "value": "tab", "label": "Tab (\\t)"},
            {"id": "pipa", "value": "pipa", "label": "Pipa (|)"},
        ],
        "indents": [
            {"value": "2", "label": "2 spasi"},
            {"value": "4", "label": "4 spasi"},
            {"value": "tab", "label": "Tab"},
        ],
        "max_chars": MAX_CHARS,
        "max_bytes": MAX_BYTES,
        "max_mb": MAX_BYTES // (1024 * 1024),
        "max_rows": MAX_ROWS,
        "max_cols": MAX_COLS,
        "defaults": {
            "mode": "ke_json",
            "pemisah": "otomatis",
            "header": "ya",
            "rapikan": "ya",
            "indent": "2",
        },
        "contoh_csv": (
            "nama,kota,pekerjaan,gaji\n"
            "Budi,\"Jakarta, Selatan\",Programmer,12000000\n"
            "Siti,Surabaya,Desainer,9500000\n"
            "Andi,\"Bandung, Barat\",Penulis,8000000"
        ),
        "contoh_json": (
            "[\n"
            "  {\"nama\": \"Budi\", \"kota\": \"Jakarta, Selatan\", \"pekerjaan\": \"Programmer\", \"gaji\": 12000000},\n"
            "  {\"nama\": \"Siti\", \"kota\": \"Surabaya\", \"pekerjaan\": \"Desainer\", \"gaji\": 9500000},\n"
            "  {\"nama\": \"Andi\", \"kota\": \"Bandung, Barat\", \"pekerjaan\": \"Penulis\", \"gaji\": 8000000}\n"
            "]"
        ),
        "error_codes": [
            INVALID_REQUEST,
            NO_TEXT,
            UNSUPPORTED_MODE,
            INVALID_SEPARATOR,
            INVALID_BOOLEAN,
            INVALID_INDENT,
            INVALID_JSON,
            INVALID_FORMAT,
            TOO_LONG,
            PAYLOAD_TOO_LARGE,
            TOO_MANY_ROWS,
            TOO_MANY_COLUMNS,
        ],
        "processed_on": "server",
        "subjudul": "Ubah CSV jadi JSON, JSON jadi CSV, atau lihat ringkasan kolomnya",
        "note": "Teks diproses di memori server lalu dibuang, tidak disimpan di disk.",
    }
