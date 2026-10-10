"""Logika alat XML (Rapikan & periksa XML): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Teks pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

import json
import re
from typing import Any
import xml.etree.ElementTree as ET

# Konstanta batas operasional
MAX_BYTES = 1_048_576  # 1 MB
MAX_CHARS = 400_000
MAX_DEPTH = 120
MAX_ELEMENTS = 200_000
CHUNK_SIZE = 64 * 1024

MODES = ["rapikan", "padatkan", "periksa", "ke_json"]
INDENTS = [2, 4, "tab"]

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NO_TEXT = "NO_TEXT"
TOO_LONG = "TOO_LONG"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
INVALID_XML = "INVALID_XML"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
INVALID_INDENT = "INVALID_INDENT"
INVALID_BOOLEAN = "INVALID_BOOLEAN"
TOO_DEEP = "TOO_DEEP"
TOO_MANY_ELEMENTS = "TOO_MANY_ELEMENTS"
DOCTYPE_NOT_SUPPORTED = "DOCTYPE_NOT_SUPPORTED"


class XmlToolError(Exception):
    """Galat operasional alat XML dengan kode galat dan status HTTP."""

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


def _friendly_xml_error(exc: ET.ParseError) -> str:
    """Ubah pesan galat teknis ParseError menjadi kalimat ramah berbahasa Indonesia."""
    msg = str(exc).lower()
    if "no element found" in msg:
        return "tidak ada elemen XML yang ditemukan atau dokumen kosong"
    if "mismatched tag" in msg:
        return "ada tanda penutup yang belum lengkap atau tidak cocok"
    if "unclosed token" in msg:
        return "ada tag atau tanda petik yang belum ditutup"
    if "not well-formed" in msg:
        return "ada karakter atau tanda kurung sudut yang tidak sah"
    if "junk after document element" in msg:
        return "ada teks tambahan di luar elemen akar"
    if "syntax error" in msg:
        return "terdapat kesalahan penulisan sintaks XML"
    return "struktur XML belum sah"


class _PrefixPreservingTreeBuilder(ET.TreeBuilder):
    """TreeBuilder yang mencatat awalan namespace (URI -> prefix) agar tetap terbaca."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.ns_map: dict[str, str] = {}

    def start_ns(self, prefix: str, uri: str) -> None:
        self.ns_map[uri] = prefix
        if prefix:
            try:
                ET.register_namespace(prefix, uri)
            except Exception:
                pass


def _resolve_name(name: str, ns_map: dict[str, str]) -> str:
    """Ubah notasi Clark {uri}tag menjadi prefix:tag bila awalan namespace tersedia."""
    if name.startswith("{"):
        parts = name[1:].split("}", 1)
        if len(parts) == 2:
            uri, local = parts
            prefix = ns_map.get(uri)
            if prefix:
                return f"{prefix}:{local}"
            return local
    return name


def _hitung_statistik_xml(
    root: ET.Element,
    max_depth: int = MAX_DEPTH,
    max_elements: int = MAX_ELEMENTS,
) -> tuple[int, int, int]:
    """Hitung kedalaman maksimum, jumlah elemen, dan total atribut secara iteratif.

    Mencegah RecursionError dan memastikan kedalaman serta jumlah elemen tidak melebihi batas.
    Mengembalikan: (kedalaman, total_elemen, total_atribut).
    """
    total_elements = 0
    total_attrs = 0
    max_d = 1

    stack: list[tuple[ET.Element, int]] = [(root, 1)]

    while stack:
        node, depth = stack.pop()
        total_elements += 1
        if total_elements > max_elements:
            raise XmlToolError(
                TOO_MANY_ELEMENTS,
                f"Jumlah elemen XML terlalu banyak. Batasnya {max_elements:,} elemen.",
                413,
            )
        if depth > max_d:
            max_d = depth
        if depth > max_depth:
            raise XmlToolError(
                TOO_DEEP,
                f"Struktur XML terlalu dalam. Batasnya {max_depth} tingkat.",
                400,
            )

        total_attrs += len(node.attrib)
        for child in reversed(list(node)):
            stack.append((child, depth + 1))

    return max_d, total_elements, total_attrs


def _element_ke_dict(
    elem: ET.Element,
    ns_map: dict[str, str],
    depth: int = 1,
    max_depth: int = MAX_DEPTH,
) -> dict[str, Any]:
    """Konversi satu elemen XML ke format dict sesuai aturan pemetaan."""
    if depth > max_depth:
        raise XmlToolError(
            TOO_DEEP,
            f"Struktur XML terlalu dalam. Batasnya {max_depth} tingkat.",
            400,
        )

    node: dict[str, Any] = {}

    # Atribut jadi kunci berawalan "@"
    for k, v in elem.attrib.items():
        node[f"@{_resolve_name(k, ns_map)}"] = v

    # Teks elemen yang bukan hanya spasi jadi kunci "#text"
    if elem.text and elem.text.strip():
        node["#text"] = elem.text.strip()

    # Tag bersaudara yang sama diulang jadi daftar (array)
    children_by_tag: dict[str, list[Any]] = {}
    for child in elem:
        tag = _resolve_name(child.tag, ns_map)
        child_val = _element_ke_dict(child, ns_map, depth=depth + 1, max_depth=max_depth)
        children_by_tag.setdefault(tag, []).append(child_val)

    for tag, vals in children_by_tag.items():
        if len(vals) == 1:
            node[tag] = vals[0]
        else:
            node[tag] = vals

    return node


def parse_limits() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional dan daftar mode alat XML."""
    return {
        "max_bytes": MAX_BYTES,
        "max_chars": MAX_CHARS,
        "max_mb": MAX_BYTES // (1024 * 1024),
        "max_depth": MAX_DEPTH,
        "max_elements": MAX_ELEMENTS,
        "modes": [
            {
                "value": "rapikan",
                "label": "Rapikan (beri jarak & baris baru)",
                "contoh": "<toko>\n  <buku id=\"1\">Laskar Pelangi</buku>\n</toko>",
            },
            {
                "value": "padatkan",
                "label": "Padatkan jadi satu baris",
                "contoh": "<toko><buku id=\"1\">Laskar Pelangi</buku></toko>",
            },
            {
                "value": "periksa",
                "label": "Periksa saja (tidak diubah)",
                "contoh": "<toko><buku id=\"1\">Laskar Pelangi</buku></toko>",
            },
            {
                "value": "ke_json",
                "label": "Ubah jadi JSON",
                "contoh": "{\n  \"toko\": {\n    \"buku\": {\n      \"@id\": \"1\",\n      \"#text\": \"Laskar Pelangi\"\n    }\n  }\n}",
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


limits_payload = parse_limits


def process(
    teks: Any = None,
    mode: Any = "rapikan",
    indent: Any = 2,
    urutkan_kunci: Any = False,
    *,
    text: Any = None,
) -> dict[str, Any]:
    """Proses teks XML di memori: validasi, statistik, dan format ulang."""
    raw_input = teks if teks is not None else text
    if raw_input is None:
        raise XmlToolError(INVALID_REQUEST, "Permintaan tidak dikenali.", 400)

    if not isinstance(raw_input, str):
        raise XmlToolError(INVALID_REQUEST, "Permintaan tidak dikenali.", 400)

    if not raw_input.strip():
        raise XmlToolError(NO_TEXT, "Belum ada teks XML yang ditempel.", 400)

    if len(raw_input) > MAX_CHARS:
        raise XmlToolError(
            TOO_LONG,
            f"Teks XML terlalu panjang. Batasnya {MAX_CHARS:,} karakter.",
            413,
        )

    raw_bytes = raw_input.encode("utf-8")
    if len(raw_bytes) > MAX_BYTES:
        raise XmlToolError(
            PAYLOAD_TOO_LARGE,
            "Ukuran kiriman melebihi batas 1 MB.",
            413,
        )

    # Keamanan: tolak deklarasi DOCTYPE atau ENTITY sebelum parsing
    raw_upper = raw_input.upper()
    if "<!DOCTYPE" in raw_upper or "<!ENTITY" in raw_upper or re.search(r"<!\s*(DOCTYPE|ENTITY)\b", raw_input, re.IGNORECASE):
        raise XmlToolError(
            DOCTYPE_NOT_SUPPORTED,
            "Deklarasi DOCTYPE atau ENTITY belum didukung di sini karena alasan keamanan.",
            400,
        )

    # Validasi mode
    if mode is None:
        mode_norm = "rapikan"
    elif isinstance(mode, str):
        mode_norm = mode.strip().lower()
    else:
        raise XmlToolError(INVALID_REQUEST, "Permintaan tidak dikenali.", 400)

    if mode_norm not in MODES:
        valid_modes = ", ".join(MODES)
        raise XmlToolError(
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
            raise XmlToolError(
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
            raise XmlToolError(
                INVALID_INDENT,
                f"Pilihan indentasi '{indent}' tidak valid. Pilih 2, 4, atau 'tab'.",
                400,
            )
    else:
        raise XmlToolError(
            INVALID_INDENT,
            "Pilihan indentasi tidak valid. Pilih 2, 4, atau 'tab'.",
            400,
        )

    # Validasi urutkan_kunci
    if isinstance(urutkan_kunci, bool):
        sort_keys_val = urutkan_kunci
    elif isinstance(urutkan_kunci, str):
        uk_clean = urutkan_kunci.strip().lower()
        if uk_clean in ("true", "1", "yes", "on", "ya"):
            sort_keys_val = True
        elif uk_clean in ("false", "0", "no", "off", "tidak", ""):
            sort_keys_val = False
        else:
            raise XmlToolError(
                INVALID_BOOLEAN,
                f"Nilai urutkan_kunci '{urutkan_kunci}' tidak valid. Gunakan 'ya' atau 'tidak'.",
                400,
            )
    elif urutkan_kunci is None:
        sort_keys_val = False
    else:
        raise XmlToolError(INVALID_BOOLEAN, "Field 'urutkan_kunci' harus bernilai boolean.", 400)

    # Parsing XML
    builder = _PrefixPreservingTreeBuilder()
    parser = ET.XMLParser(target=builder)
    try:
        parser.feed(raw_input)
        root = parser.close()
    except ET.ParseError as exc:
        line, col = exc.position if exc.position else (1, 0)
        baris = max(1, line)
        kolom = max(1, col + 1)
        keterangan = _friendly_xml_error(exc)
        pesan = f"XML belum sah di baris {baris} kolom {kolom}: {keterangan}."
        raise XmlToolError(INVALID_XML, pesan, 400, detail={"baris": baris, "kolom": kolom})
    except RecursionError:
        raise XmlToolError(
            TOO_DEEP,
            f"Struktur XML terlalu dalam. Batasnya {MAX_DEPTH} tingkat.",
            400,
        )

    if root is None:
        raise XmlToolError(
            INVALID_XML,
            "XML belum sah di baris 1 kolom 1: tidak ada elemen XML yang ditemukan.",
            400,
            detail={"baris": 1, "kolom": 1},
        )

    kedalaman, jumlah_elemen, jumlah_atribut = _hitung_statistik_xml(
        root,
        max_depth=MAX_DEPTH,
        max_elements=MAX_ELEMENTS,
    )
    akar_tag = _resolve_name(root.tag, builder.ns_map)

    # Pemformatan keluaran sesuai mode
    if mode_norm == "rapikan":
        indent_space = "\t" if indent_val == "tab" else (" " * indent_val)
        try:
            for elem in root.iter():
                if elem.tail and not elem.tail.strip():
                    elem.tail = None
                if len(elem) > 0 and elem.text and not elem.text.strip():
                    elem.text = None
            ET.indent(root, space=indent_space)
            out_text = ET.tostring(root, encoding="unicode")
        except RecursionError:
            raise XmlToolError(
                TOO_DEEP,
                f"Struktur XML terlalu dalam. Batasnya {MAX_DEPTH} tingkat.",
                400,
            )
        catatan = "XML sah dan berhasil dirapikan dengan indentasi."

    elif mode_norm == "padatkan":
        try:
            for elem in root.iter():
                if elem.tail:
                    elem.tail = elem.tail.strip() or None
                if len(elem) > 0:
                    if elem.text:
                        elem.text = elem.text.strip() or None
                elif elem.text:
                    elem.text = elem.text.strip() or None
            out_text = ET.tostring(root, encoding="unicode")
        except RecursionError:
            raise XmlToolError(
                TOO_DEEP,
                f"Struktur XML terlalu dalam. Batasnya {MAX_DEPTH} tingkat.",
                400,
            )
        catatan = "XML sah dan berhasil dipadatkan jadi satu baris."

    elif mode_norm == "periksa":
        out_text = raw_input
        catatan = "XML sah dan strukturnya valid (teks masukan tidak diubah)."

    elif mode_norm == "ke_json":
        json_dict = {akar_tag: _element_ke_dict(root, builder.ns_map, depth=1, max_depth=MAX_DEPTH)}
        indent_arg = "\t" if indent_val == "tab" else indent_val
        try:
            out_text = json.dumps(json_dict, indent=indent_arg, sort_keys=sort_keys_val, ensure_ascii=False)
        except RecursionError:
            raise XmlToolError(
                TOO_DEEP,
                f"Struktur XML terlalu dalam. Batasnya {MAX_DEPTH} tingkat.",
                400,
            )
        catatan = "XML sah dan berhasil diubah menjadi JSON."

    else:
        raise XmlToolError(UNSUPPORTED_MODE, f"Mode '{mode}' tidak didukung.", 400)

    in_lines = len(raw_input.splitlines()) if raw_input else 0
    out_lines = len(out_text.splitlines()) if out_text else 0
    raw_out_bytes = out_text.encode("utf-8")

    statistik = {
        "baris_sebelum": in_lines,
        "baris_sesudah": out_lines,
        "karakter_sebelum": len(raw_input),
        "karakter_sesudah": len(out_text),
        "ukuran_sebelum": len(raw_bytes),
        "ukuran_sesudah": len(raw_out_bytes),
        "kedalaman": kedalaman,
        "elemen": jumlah_elemen,
        "atribut": jumlah_atribut,
        "akar": akar_tag,
    }

    return {
        "mode": mode_norm,
        "aturan": {"indentasi": indent_val, "urutkan_kunci": sort_keys_val},
        "sah": True,
        "teks": out_text,
        "masukan": {
            "chars": len(raw_input),
            "lines": in_lines,
            "bytes": len(raw_bytes),
        },
        "keluaran": {
            "teks": out_text,
            "chars": len(out_text),
            "lines": out_lines,
            "bytes": len(raw_out_bytes),
            "banyak_baris_ditambah": max(0, out_lines - in_lines),
        },
        "statistik": statistik,
        "catatan": catatan,
    }


proses_xml = process
