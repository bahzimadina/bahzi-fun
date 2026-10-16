"""Logika peringkas teks (Text Summary): fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori secara ekstraktif (memilih kalimat penting
dari teks asli tanpa memanggil model bahasa atau layanan AI eksternal).
Teks pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

import heapq
import math
import re
from typing import Any, NamedTuple

# Batas operasional di memori
MAX_CHARS = 200_000
MAX_BYTES = 1_000_000
MIN_KALIMAT = 3
RASIO_MIN = 10
RASIO_MAX = 80
RASIO_DEFAULT = 30
FORMAT_PILIHAN = ("paragraf", "poin")

# Kode galat stabil
NO_TEXT = "NO_TEXT"
TOO_LONG = "TOO_LONG"
TOO_SHORT = "TOO_SHORT"
INVALID_RATIO = "INVALID_RATIO"
INVALID_FORMAT = "INVALID_FORMAT"
NOT_TEXT = "NOT_TEXT"
INVALID_REQUEST = "INVALID_REQUEST"


class TextSummaryError(ValueError):
    """Galat operasional peringkas teks dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


# Daftar kata umum (stopwords) Bahasa Indonesia bawaan (~120 kata)
STOPWORDS: set[str] = {
    # Kata tugas & penghubung yang disebutkan spesifikasi
    "yang", "dan", "di", "ke", "dari", "untuk", "dengan", "pada", "adalah", "itu",
    "ini", "tidak", "juga", "akan", "sudah", "telah", "karena", "agar", "bila", "jika",
    "maka", "serta", "sebagai", "dalam", "oleh", "atau", "tetapi", "namun", "se", "per",
    "para", "saat", "secara", "hingga", "sampai", "bahwa", "hanya", "masih", "bisa", "dapat",
    "harus", "ada", "tiap", "setiap", "antara", "bagi", "demi", "tanpa", "setelah", "sebelum",
    "ketika", "supaya", "nya", "pun", "lah", "kah", "dsb", "dll", "dst",
    # Kata umum tambahan Bahasa Indonesia
    "ia", "dia", "mereka", "kita", "kami", "kamu", "anda", "saya", "aku", "beliau",
    "saja", "lagi", "punya", "bukan", "hampir", "selalu", "sering", "kadang", "pernah",
    "sedang", "lalu", "kemudian", "sambil", "selain", "tentang", "maupun",
    "bahkan", "yaitu", "yakni", "ialah", "merupakan", "menjadi", "tersebut", "begini",
    "begitu", "sana", "sini", "situ", "mana", "siapa", "apa", "bagaimana", "mengapa",
    "kenapa", "kapan", "berapa", "seperti", "banyak", "sedikit", "semua", "seluruh",
    "suatu", "satu", "dua", "tiga", "lain", "lainnya", "terhadap", "atas",
    "bawah", "luar", "depan", "belakang", "tengah", "sekitar", "sejak",
    "sementara", "padahal", "melainkan", "walau", "walaupun", "meskipun", "kendati",
    "sungguh", "amat", "sangat", "paling", "terlalu", "cukup", "lebih", "kurang",
    "ikut", "mampu", "boleh", "perlu", "mesti", "tentu", "pasti",
}

# Singkatan umum Bahasa Indonesia yang tidak boleh dianggap sebagai pemisah kalimat
ABBR_ITEMS = (
    r"a\.n", r"s\.d", r"a\.l", "dll", "dsb", "dst", "no", "jl", "rp", "ybs", "hlm", "th",
    "bpk", "ibu", "sdr", "sdri", "pt", "cv", "ud", "dr", "ir", "hj", "h", "prof", "yth",
    "dkk", "tgl", "sda", "al", "him", "sby", "jkt", "ttg", "krn", "dgn", "sbb", "mohon",
)
ABBR_PATTERN = re.compile(
    r"\b(?:" + "|".join(ABBR_ITEMS) + r")\.",
    re.IGNORECASE,
)

# Pola penanda daftar di awal baris (angka+titik, angka+kurung tutup, atau butir -, *, •)
LIST_MARKER_PATTERN = re.compile(r"^\s*(?:\d+\.(?!\d)|\d+\)|[-*•])\s*")


def _parse_paragraph_to_items(p_clean: str) -> list[str]:
    """Pisahkan baris dalam paragraf bila memuat butir/nomor daftar."""
    lines = p_clean.split("\n")
    items: list[str] = []
    current_item: list[str] = []
    current_is_list = False

    for raw_line in lines:
        line_stripped = raw_line.strip()
        if not line_stripped:
            continue
        m = LIST_MARKER_PATTERN.match(line_stripped)
        if m:
            if current_item:
                items.append(" ".join(current_item))
                current_item = []
            content = line_stripped[m.end():].strip()
            while content and content[0] in "-*•":
                content = content[1:].strip()
            if content:
                current_item.append(content)
            current_is_list = True
        else:
            if current_is_list:
                # Baris lanjutan butir jika berindentasi
                if raw_line.startswith(" ") or raw_line.startswith("\t"):
                    current_item.append(line_stripped)
                else:
                    if current_item:
                        items.append(" ".join(current_item))
                        current_item = []
                    current_item.append(line_stripped)
                    current_is_list = False
            else:
                current_item.append(line_stripped)

    if current_item:
        items.append(" ".join(current_item))
    return items


def simplify_token(token: str) -> str:
    """Ringankan varian kata: buang akhiran -nya, -kah, -lah, -pun, -ku, -mu.

    Catatan: Ini adalah penyederhanaan varian kata (clitic stripping sederhana),
    bukan algoritma stemming penuh Bahasa Indonesia (seperti Nazief-Adriani atau CS).
    Hanya dijalankan jika panjang token lebih dari 5 huruf.
    """
    if len(token) > 5:
        for suffix in ("nya", "kah", "lah", "pun", "ku", "mu"):
            if token.endswith(suffix):
                return token[: -len(suffix)]
    return token


class Sentence(NamedTuple):
    text: str
    para_idx: int
    is_doc_first: bool
    is_doc_last: bool
    is_para_first: bool
    simplified_terms: list[str]
    word_set: set[str]


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Hitung kemiripan Jaccard antara dua himpunan kata."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def validate_text(text: Any) -> str:
    """Validasi masukan teks terhadap kekosongan, tipe, dan panjang batas."""
    if text is None:
        raise TextSummaryError(NO_TEXT, "Field teks 'text' wajib diisi.", 400)

    if not isinstance(text, str):
        raise TextSummaryError(NOT_TEXT, "Field 'text' harus berupa teks string.", 400)

    if not text.strip():
        raise TextSummaryError(NO_TEXT, "Teks masih kosong. Tempel dulu teks yang mau diringkas.", 400)

    if len(text) > MAX_CHARS:
        raise TextSummaryError(
            TOO_LONG,
            f"Teks terlalu panjang. Batasnya 200.000 karakter.",
            400,
        )

    if len(text.encode("utf-8")) > MAX_BYTES:
        raise TextSummaryError(
            TOO_LONG,
            "Ukuran byte teks melebihi batas 1 MB.",
            400,
        )

    return text


def parse_ratio(rasio: Any) -> int:
    """Validasi dan parse rasio ringkasan (10..80 persen)."""
    if rasio is None or rasio == "":
        return RASIO_DEFAULT

    try:
        val = int(rasio)
    except (ValueError, TypeError):
        raise TextSummaryError(INVALID_RATIO, "Rasio ringkasan harus angka 10 sampai 80 persen.", 400)

    if val < RASIO_MIN or val > RASIO_MAX:
        raise TextSummaryError(INVALID_RATIO, "Rasio ringkasan harus angka 10 sampai 80 persen.", 400)

    return val


def parse_format(format_val: Any) -> str:
    """Validasi format keluaran ringkasan (paragraf / poin)."""
    if format_val is None or format_val == "":
        return "paragraf"

    if not isinstance(format_val, str):
        raise TextSummaryError(INVALID_FORMAT, "Format hasil hanya bisa paragraf atau poin.", 400)

    norm = format_val.strip().lower()
    if norm not in FORMAT_PILIHAN:
        raise TextSummaryError(INVALID_FORMAT, "Format hasil hanya bisa paragraf atau poin.", 400)

    return norm


def extract_sentences(
    text: str,
) -> tuple[list[Sentence], dict[str, str], dict[str, int]]:
    """Pecah teks menjadi daftar kalimat dengan memperhatikan batas paragraf, singkatan, dan daftar.

    Mengembalikan (sentences, term_first_original, term_first_pos).
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    # 1. Rapikan spasi; pecah teks jadi paragraf (pemisah: satu baris kosong atau lebih)
    raw_paragraphs = re.split(r"\n\s*\n+", normalized.strip())

    parsed_units: list[tuple[str, int, bool]] = []
    para_counter = 0

    for p_raw in raw_paragraphs:
        p_clean = p_raw.strip()
        if not p_clean:
            continue

        items = _parse_paragraph_to_items(p_clean)
        is_p_first = True

        for item in items:
            # Lindungi singkatan umum agar tidak terpecah
            item_protected = ABBR_PATTERN.sub(
                lambda m: m.group(0).replace(".", "\uE000"),
                item,
            )

            # 2. Pecah kalimat dengan pola tanda baca akhir + spasi berikutnya (. ! ? … serta baris baru)
            parts = re.split(r"(?<=[.!?…])\s+", item_protected)

            for part in parts:
                restored = part.replace("\uE000", ".")
                cleaned = " ".join(restored.split())
                while cleaned and cleaned[0] in "-*•":
                    cleaned = cleaned[1:].strip()
                if not cleaned:
                    continue
                parsed_units.append((cleaned, para_counter, is_p_first))
                is_p_first = False

        para_counter += 1

    total_sentences = len(parsed_units)
    if total_sentences < MIN_KALIMAT:
        raise TextSummaryError(
            TOO_SHORT,
            "Teks terlalu pendek untuk diringkas. Minimal 3 kalimat.",
            400,
        )

    sentences: list[Sentence] = []
    term_first_original: dict[str, str] = {}
    term_first_pos: dict[str, int] = {}
    global_term_pos = 0

    for idx, (s_text, p_idx, is_p_first) in enumerate(parsed_units):
        # 3. Tokenisasi: huruf kecil, pola [a-z0-9] + aksen
        orig_words = re.findall(r"[a-zA-Z0-9\u00e0-\u024f]+", s_text)
        word_set = {w.lower() for w in orig_words}

        simplified_terms: list[str] = []
        for orig_w in orig_words:
            low_w = orig_w.lower()
            if len(low_w) <= 1 or low_w in STOPWORDS:
                continue

            # 4. Ringankan varian kata: buang akhiran -nya, -kah, -lah, -pun, -ku, -mu
            sim_w = simplify_token(low_w)
            if len(sim_w) <= 1 or sim_w in STOPWORDS:
                continue

            simplified_terms.append(sim_w)
            if sim_w not in term_first_original:
                term_first_original[sim_w] = orig_w
                term_first_pos[sim_w] = global_term_pos
            global_term_pos += 1

        sentences.append(
            Sentence(
                text=s_text,
                para_idx=p_idx,
                is_doc_first=(idx == 0),
                is_doc_last=(idx == total_sentences - 1),
                is_para_first=is_p_first,
                simplified_terms=simplified_terms,
                word_set=word_set,
            )
        )

    return sentences, term_first_original, term_first_pos


def summarize_text(
    text: Any,
    rasio: Any = RASIO_DEFAULT,
    format: Any = "paragraf",
) -> dict[str, Any]:
    """Ringkas teks secara ekstraktif di memori server.

    Parameter:
        text: string teks yang akan diringkas.
        rasio: persentase kalimat ringkasan (10..80, bawaan 30).
        format: 'paragraf' (bawaan) atau 'poin'.
    """
    clean_text = validate_text(text)
    ratio_val = parse_ratio(rasio)
    format_mode = parse_format(format)

    sentences, term_first_orig, term_first_pos = extract_sentences(clean_text)
    total_sentences = len(sentences)

    # 5. Bobot istilah: tf * idf sederhana
    # tf = jumlah kemunculan istilah di seluruh teks
    # idf = log(jumlah_kalimat / (1 + jumlah_kalimat_yang_memuat_istilah))
    tf: dict[str, int] = {}
    df_sentences: dict[str, set[int]] = {}

    for sent_idx, s in enumerate(sentences):
        for term in s.simplified_terms:
            tf[term] = tf.get(term, 0) + 1
            df_sentences.setdefault(term, set()).add(sent_idx)

    term_weights: dict[str, float] = {}
    for term, count in tf.items():
        df_count = len(df_sentences[term])
        ratio = total_sentences / (1 + df_count)
        # Cegah nilai negatif bila istilah ada di hampir setiap kalimat
        idf = math.log(ratio) if ratio > 1.0 else 0.001
        term_weights[term] = count * idf

    # 6. Skor kalimat: jumlah bobot istilah unik di kalimat dibagi (jumlah_istilah ** 0.6)
    # dikali penguat posisi: pertama dokumen x1.25, pertama tiap paragraf x1.1, terakhir dokumen x1.05
    raw_scores: list[float] = []
    for s in sentences:
        unique_terms = set(s.simplified_terms)
        sum_weights = sum(term_weights.get(t, 0.0) for t in unique_terms)
        term_count = len(s.simplified_terms)
        base_score = (sum_weights / (term_count ** 0.6)) if term_count > 0 else 0.0

        pos_mult = 1.0
        if s.is_doc_first:
            pos_mult *= 1.25
        elif s.is_para_first:
            pos_mult *= 1.1

        if s.is_doc_last:
            pos_mult *= 1.05

        raw_scores.append(base_score * pos_mult)

    # Normalisasi skor ke 0..1
    max_score = max(raw_scores) if raw_scores else 0.0
    if max_score > 0.0:
        normalized_scores = [sc / max_score for sc in raw_scores]
    else:
        normalized_scores = [0.0] * total_sentences

    # 7. Pilih kalimat dengan indeks terbalik dan heap
    k = round(total_sentences * (ratio_val / 100.0))
    k = max(1, min(k, total_sentences - 1))

    frozen_word_sets = [frozenset(s.word_set) for s in sentences]
    word_lengths = [len(fs) for fs in frozen_word_sets]

    # Indeks terbalik: kata -> daftar indeks kalimat
    inverted_index: dict[str, list[int]] = {}
    for idx, fs in enumerate(frozen_word_sets):
        for w in fs:
            inverted_index.setdefault(w, []).append(idx)

    # Cache kemiripan antar himpunan kata untuk menghindari hitung ulang
    similar_cache: dict[frozenset[str], list[int]] = {}

    def get_similar_candidates(best_idx: int) -> list[int]:
        ws = frozen_word_sets[best_idx]
        if ws in similar_cache:
            return similar_cache[ws]
        best_len = word_lengths[best_idx]
        if best_len == 0:
            similar_cache[ws] = []
            return []

        # Jaccard > 0.6 mensyaratkan irisan minimal
        min_b = math.floor(0.6 * best_len) + 1
        min_inter = math.floor(0.375 * (best_len + min_b)) + 1
        prefix_len = max(1, best_len - min_inter + 1)
        sorted_terms = sorted(ws, key=lambda w: len(inverted_index.get(w, ())))
        check_terms = sorted_terms[:prefix_len]

        candidates: set[int] = set()
        for w in check_terms:
            for c_idx in inverted_index.get(w, ()):
                candidates.add(c_idx)

        res: list[int] = []
        for idx in candidates:
            c_len = word_lengths[idx]
            if c_len * 10 <= best_len * 6 or best_len * 10 <= c_len * 6:
                continue
            inter = len(frozen_word_sets[idx] & ws)
            if inter / (c_len + best_len - inter) > 0.6:
                res.append(idx)

        similar_cache[ws] = res
        return res

    selected_indices: list[int] = []
    selected_mask = [False] * total_sentences
    current_scores = list(normalized_scores)
    score_version = [0] * total_sentences
    heap = [(-sc, idx, 0) for idx, sc in enumerate(current_scores)]
    heapq.heapify(heap)

    for _ in range(k):
        best_idx = -1
        while heap:
            neg_sc, idx, ver = heapq.heappop(heap)
            if selected_mask[idx] or ver != score_version[idx]:
                continue
            best_idx = idx
            break

        if best_idx == -1:
            for idx in range(total_sentences):
                if not selected_mask[idx]:
                    best_idx = idx
                    break

        selected_indices.append(best_idx)
        selected_mask[best_idx] = True
        if len(selected_indices) == k:
            break

        # Penalti kemiripan untuk kalimat yang berbagi kata dan Jaccard > 0.6
        for idx in get_similar_candidates(best_idx):
            if not selected_mask[idx]:
                current_scores[idx] *= 0.3
                score_version[idx] += 1
                heapq.heappush(heap, (-current_scores[idx], idx, score_version[idx]))

    # 8. Susun hasil: urutkan kalimat terpilih sesuai urutan aslinya
    selected_indices.sort()
    selected_sentences = [sentences[i] for i in selected_indices]

    if format_mode == "poin":
        ringkasan = "\n".join(f"- {s.text}" for s in selected_sentences)
    else:
        # Format paragraf: gabung kalimat bersebelahan dalam paragraf yang sama dengan spasi,
        # dan pisahkan antar paragraf dengan satu baris kosong
        para_groups: dict[int, list[str]] = {}
        for s in selected_sentences:
            para_groups.setdefault(s.para_idx, []).append(s.text)
        ringkasan = "\n\n".join(" ".join(sent_list) for sent_list in para_groups.values())

    # 9. Kata kunci: sampai 8 istilah dengan bobot total terbesar,
    # ditampilkan dalam bentuk aslinya (kemunculan pertama di teks),
    # minimal muncul di 2 kalimat.
    candidate_keywords = [
        t for t in term_weights
        if len(df_sentences.get(t, set())) >= 2
    ]
    candidate_keywords.sort(
        key=lambda t: (-term_weights[t], term_first_pos.get(t, 0))
    )
    kata_kunci = [term_first_orig[t] for t in candidate_keywords[:8]]

    # Statistik keluaran
    chars_in = len(clean_text)
    chars_out = len(ringkasan)
    hemat_persen = round((chars_in - chars_out) / chars_in * 100) if chars_in > 0 else 0
    hemat_persen = max(0, min(100, hemat_persen))

    words_in = len(clean_text.split())
    words_out = len(ringkasan.split())
    waktu_baca_detik = max(1, round((words_out / 200.0) * 60))

    return {
        "ringkasan": ringkasan,
        "format": format_mode,
        "rasio": ratio_val,
        "kalimat": {
            "masukan": total_sentences,
            "ringkasan": len(selected_sentences),
        },
        "karakter": {
            "masukan": chars_in,
            "ringkasan": chars_out,
            "hemat_persen": hemat_persen,
        },
        "kata": {
            "masukan": words_in,
            "ringkasan": words_out,
        },
        "waktu_baca_detik": waktu_baca_detik,
        "kata_kunci": kata_kunci,
        "catatan": None,
    }


def text_summary_limits_payload() -> dict[str, Any]:
    """Payload batas operasional untuk endpoint /api/text/summary/limits."""
    return {
        "max_chars": MAX_CHARS,
        "max_bytes": MAX_BYTES,
        "max_mb": MAX_BYTES // 1_000_000,
        "min_kalimat": MIN_KALIMAT,
        "rasio_min": RASIO_MIN,
        "rasio_max": RASIO_MAX,
        "rasio_default": RASIO_DEFAULT,
        "format": list(FORMAT_PILIHAN),
        "defaults": {
            "rasio": RASIO_DEFAULT,
            "format": "paragraf",
        },
        "processed_on": "server",
        "note": "Teks diproses di memori server lalu dibuang, tidak disimpan di disk.",
    }
