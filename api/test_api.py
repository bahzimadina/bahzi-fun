"""Uji otomatis OmniTools API — Merge PDF.

Bisa dijalankan dua cara:

1. Skrip mandiri (tanpa pytest, tanpa dependensi tambahan):
       cd api && python3 test_api.py
   Menguji logika murni (pdf_merge) + endpoint HTTP via TestClient bila `httpx`
   tersedia + endpoint HTTP langsung bila env OMNITOOLS_API_URL diisi.

2. Sebagai pytest biasa:
       cd api && python3 -m pytest test_api.py -v

Keluar dengan status 1 bila ada uji yang gagal.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from PIL import Image, ImageDraw  # noqa: E402
import pymupdf  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

from app import __version__  # noqa: E402
from app.image_convert import (  # noqa: E402
    EMPTY_FILE as IMG_EMPTY_FILE,
    IMAGE_TOO_LARGE as IMG_IMAGE_TOO_LARGE,
    IMAGE_UNREADABLE as IMG_IMAGE_UNREADABLE,
    INVALID_QUALITY as IMG_INVALID_QUALITY,
    INVALID_SVG as IMG_INVALID_SVG,
    INVALID_WIDTH as IMG_INVALID_WIDTH,
    MAX_BYTES as IMG_MAX_BYTES,
    MAX_FILES as IMG_MAX_FILES,
    MAX_PIXELS as IMG_MAX_PIXELS,
    NO_FILES as IMG_NO_FILES,
    NOT_IMAGE as IMG_NOT_IMAGE,
    PAYLOAD_TOO_LARGE as IMG_PAYLOAD_TOO_LARGE,
    QUALITY_DEFAULT as IMG_QUALITY_DEFAULT,
    QUALITY_MAX as IMG_QUALITY_MAX,
    QUALITY_MIN as IMG_QUALITY_MIN,
    SVG_DEFAULT_WIDTH as IMG_SVG_DEFAULT_WIDTH,
    SVG_MAX_SIDE as IMG_SVG_MAX_SIDE,
    SVG_MAX_WIDTH as IMG_SVG_MAX_WIDTH,
    TARGETS as IMG_TARGETS,
    TOO_MANY_FILES as IMG_TOO_MANY_FILES,
    UNSAFE_SVG as IMG_UNSAFE_SVG,
    UNSUPPORTED_TARGET as IMG_UNSUPPORTED_TARGET,
    ImageConvertError,
    check_file_count as check_image_file_count,
    check_total_size as check_image_total_size,
    convert_image,
    detect_format,
    is_supported_image,
    normalize_quality,
    normalize_target,
)
from app.pdf_merge import (  # noqa: E402
    ERR_EMPTY_FILE,
    ERR_ENCRYPTED,
    ERR_NOT_PDF,
    ERR_NO_FILES,
    ERR_TOO_LARGE,
    ERR_TOO_MANY_FILES,
    ERR_TOO_MANY_PAGES,
    ERR_UNREADABLE,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    MAX_TOTAL_PAGES,
    PdfMergeError,
    check_total_size,
    is_pdf_bytes,
    merge_pdfs,
)
from app.pdf_split import (  # noqa: E402
    DEFAULT_CHUNK as SPLIT_DEFAULT_CHUNK,
    ERR_EMPTY_FILE as SPLIT_ERR_EMPTY_FILE,
    ERR_PDF_ENCRYPTED as SPLIT_ERR_PDF_ENCRYPTED,
    ERR_INVALID_CHUNK as SPLIT_ERR_INVALID_CHUNK,
    ERR_INVALID_PAGES as SPLIT_ERR_INVALID_PAGES,
    ERR_NO_FILE as SPLIT_ERR_NO_FILE,
    ERR_NOT_PDF as SPLIT_ERR_NOT_PDF,
    ERR_PAYLOAD_TOO_LARGE as SPLIT_ERR_PAYLOAD_TOO_LARGE,
    ERR_PDF_UNREADABLE as SPLIT_ERR_PDF_UNREADABLE,
    ERR_TOO_MANY_PAGES as SPLIT_ERR_TOO_MANY_PAGES,
    ERR_UNSUPPORTED_MODE as SPLIT_ERR_UNSUPPORTED_MODE,
    MAX_CHUNK as SPLIT_MAX_CHUNK,
    MAX_FILE_BYTES as SPLIT_MAX_FILE_BYTES,
    MAX_PAGES as SPLIT_MAX_PAGES,
    MIN_CHUNK as SPLIT_MIN_CHUNK,
    PdfInfo,
    PdfSplitError,
    SplitResult,
    check_size as check_split_size,
    inspect_pdf,
    parse_page_range,
    split_pdf,
)
from app.pdf_compress import (  # noqa: E402
    DEFAULT_DPI as COMPRESS_DEFAULT_DPI,
    DEFAULT_QUALITY as COMPRESS_DEFAULT_QUALITY,
    ERR_EMPTY_FILE as COMPRESS_ERR_EMPTY_FILE,
    ERR_INVALID_DPI as COMPRESS_ERR_INVALID_DPI,
    ERR_INVALID_QUALITY as COMPRESS_ERR_INVALID_QUALITY,
    ERR_NO_FILE as COMPRESS_ERR_NO_FILE,
    ERR_NOT_PDF as COMPRESS_ERR_NOT_PDF,
    ERR_PAYLOAD_TOO_LARGE as COMPRESS_ERR_PAYLOAD_TOO_LARGE,
    ERR_PDF_ENCRYPTED as COMPRESS_ERR_PDF_ENCRYPTED,
    ERR_PDF_UNREADABLE as COMPRESS_ERR_PDF_UNREADABLE,
    ERR_TOO_MANY_PAGES as COMPRESS_ERR_TOO_MANY_PAGES,
    ERR_UNSUPPORTED_MODE as COMPRESS_ERR_UNSUPPORTED_MODE,
    MAX_DPI as COMPRESS_MAX_DPI,
    MAX_FILE_BYTES as COMPRESS_MAX_FILE_BYTES,
    MAX_PAGES as COMPRESS_MAX_PAGES,
    MAX_QUALITY as COMPRESS_MAX_QUALITY,
    MIN_DPI as COMPRESS_MIN_DPI,
    MIN_QUALITY as COMPRESS_MIN_QUALITY,
    MODES as COMPRESS_MODES,
    CompressResult,
    PdfCompressError,
    PdfInfo as CompressPdfInfo,
    check_size as check_compress_size,
    compress_pdf,
    inspect_pdf as inspect_compress_pdf,
    parse_dpi,
    parse_quality,
)
from app.pdf_to_image import (  # noqa: E402
    DEFAULT_DPI as PDF_IMG_DEFAULT_DPI,
    DEFAULT_QUALITY as PDF_IMG_DEFAULT_QUALITY,
    ERR_EMPTY_FILE as PDF_IMG_ERR_EMPTY_FILE,
    ERR_INVALID_DPI as PDF_IMG_ERR_INVALID_DPI,
    ERR_INVALID_QUALITY as PDF_IMG_ERR_INVALID_QUALITY,
    ERR_NO_FILE as PDF_IMG_ERR_NO_FILE,
    ERR_NOT_PDF as PDF_IMG_ERR_NOT_PDF,
    ERR_OUTPUT_TOO_LARGE as PDF_IMG_ERR_OUTPUT_TOO_LARGE,
    ERR_PAGE_TOO_LARGE as PDF_IMG_ERR_PAGE_TOO_LARGE,
    ERR_PAYLOAD_TOO_LARGE as PDF_IMG_ERR_PAYLOAD_TOO_LARGE,
    ERR_PDF_EMPTY as PDF_IMG_ERR_PDF_EMPTY,
    ERR_PDF_ENCRYPTED as PDF_IMG_ERR_PDF_ENCRYPTED,
    ERR_PDF_UNREADABLE as PDF_IMG_ERR_PDF_UNREADABLE,
    ERR_TOO_MANY_PAGES as PDF_IMG_ERR_TOO_MANY_PAGES,
    ERR_UNSUPPORTED_FORMAT as PDF_IMG_ERR_UNSUPPORTED_FORMAT,
    FORMATS as PDF_IMG_FORMATS,
    MAX_DPI as PDF_IMG_MAX_DPI,
    MAX_FILE_BYTES as PDF_IMG_MAX_FILE_BYTES,
    MAX_OUTPUT_BYTES as PDF_IMG_MAX_OUTPUT_BYTES,
    MAX_PAGES as PDF_IMG_MAX_PAGES,
    MAX_PAGE_PIXELS as PDF_IMG_MAX_PAGE_PIXELS,
    MAX_QUALITY as PDF_IMG_MAX_QUALITY,
    MIN_DPI as PDF_IMG_MIN_DPI,
    MIN_QUALITY as PDF_IMG_MIN_QUALITY,
    PdfToImageError,
    PdfToImageResult,
    check_size as check_pdf_to_image_size,
    is_pdf_bytes as is_pdf_to_image_bytes,
    limits_payload as pdf_to_image_limits_payload_func,
    parse_dpi as parse_pdf_to_image_dpi,
    parse_format as parse_pdf_to_image_format,
    parse_quality as parse_pdf_to_image_quality,
    pdf_to_image,
)
from app.word_count import (  # noqa: E402
    INVALID_REQUEST as WC_INVALID_REQUEST,
    MAX_BYTES as WC_MAX_BYTES,
    MAX_CHARS as WC_MAX_CHARS,
    NO_TEXT as WC_NO_TEXT,
    STOP_WORDS as WC_STOP_WORDS,
    TOO_LONG as WC_TOO_LONG,
    WordCountError,
    WordCountResult,
    count_text,
    validate_text,
)
from app.case_convert import (  # noqa: E402
    CHUNK_SIZE as CC_CHUNK_SIZE,
    INVALID_REQUEST as CC_INVALID_REQUEST,
    MAX_BYTES as CC_MAX_BYTES,
    MAX_CHARS as CC_MAX_CHARS,
    MODE_ORDER as CC_MODE_ORDER,
    MODES as CC_MODES,
    NO_TEXT as CC_NO_TEXT,
    TOO_LONG as CC_TOO_LONG,
    UNSUPPORTED_MODE as CC_UNSUPPORTED_MODE,
    CaseConvertError,
    CaseConvertResult,
    convert_case,
    normalize_mode,
    validate_text as validate_case_text,
)
from app.ocr import (  # noqa: E402
    BUSY as OCR_BUSY,
    DAMAGED_FILE as OCR_DAMAGED_FILE,
    DEFAULT_LANG as OCR_DEFAULT_LANG,
    EMPTY_FILE as OCR_EMPTY_FILE,
    INVALID_LANG as OCR_INVALID_LANG,
    LANGUAGES as OCR_LANGUAGES,
    LANGS as OCR_LANGS,
    MAX_BYTES as OCR_MAX_BYTES,
    MAX_PAGES as OCR_MAX_PAGES,
    NO_FILE as OCR_NO_FILE,
    OCR_FAILED,
    OCR_TIMEOUT,
    TIME_LIMIT_SECONDS as OCR_TIME_LIMIT_SECONDS,
    TOO_LARGE as OCR_TOO_LARGE,
    TOO_MANY_PAGES as OCR_TOO_MANY_PAGES,
    UNSUPPORTED_FILE as OCR_UNSUPPORTED_FILE,
    OcrError,
    OcrResult,
    run_ocr,
)
from app.base64_tool import (  # noqa: E402
    CHUNK_SIZE as B64_CHUNK_SIZE,
    INVALID_BASE64 as B64_INVALID_BASE64,
    INVALID_REQUEST as B64_INVALID_REQUEST,
    INVALID_VARIANT as B64_INVALID_VARIANT,
    INVALID_WRAP as B64_INVALID_WRAP,
    MAX_BYTES as B64_MAX_BYTES,
    MAX_CHARS as B64_MAX_CHARS,
    MODES as B64_MODES,
    NO_TEXT as B64_NO_TEXT,
    NOT_TEXT as B64_NOT_TEXT,
    TOO_LONG as B64_TOO_LONG,
    UNSUPPORTED_MODE as B64_UNSUPPORTED_MODE,
    VARIANTS as B64_VARIANTS,
    WRAP_OPTIONS as B64_WRAP_OPTIONS,
    Base64Result,
    Base64ToolError,
    convert_base64,
    normalize_mode as normalize_base64_mode,
    normalize_variant as normalize_base64_variant,
    normalize_wrap as normalize_base64_wrap,
    validate_text as validate_base64_text,
)
from app.remove_duplicates import (  # noqa: E402
    CHUNK_SIZE as RD_CHUNK_SIZE,
    INVALID_BOOLEAN as RD_INVALID_BOOLEAN,
    INVALID_REQUEST as RD_INVALID_REQUEST,
    KEEP_MODES as RD_KEEP_MODES,
    MAX_BYTES as RD_MAX_BYTES,
    MAX_CHARS as RD_MAX_CHARS,
    NO_TEXT as RD_NO_TEXT,
    TOO_LONG as RD_TOO_LONG,
    UNSUPPORTED_KEEP as RD_UNSUPPORTED_KEEP,
    DedupeResult,
    RemoveDuplicatesError,
    check_size as check_remove_duplicates_size,
    dedupe_text,
    normalize_keep as normalize_remove_duplicates_keep,
    parse_bool as parse_remove_duplicates_bool,
    validate_text as validate_remove_duplicates_text,
)
from app.list_shuffler import (  # noqa: E402
    CHUNK_SIZE as LS_CHUNK_SIZE,
    INVALID_BOOLEAN as LS_INVALID_BOOLEAN,
    INVALID_REQUEST as LS_INVALID_REQUEST,
    INVALID_SEED as LS_INVALID_SEED,
    INVALID_TAKE as LS_INVALID_TAKE,
    MAX_BYTES as LS_MAX_BYTES,
    MAX_CHARS as LS_MAX_CHARS,
    MAX_SEED as LS_MAX_SEED,
    MAX_TAKE as LS_MAX_TAKE,
    MIN_SEED as LS_MIN_SEED,
    NO_TEXT as LS_NO_TEXT,
    TOO_LONG as LS_TOO_LONG,
    ListShufflerError,
    ShuffleResult,
    check_size as check_list_shuffler_size,
    parse_bool as parse_list_shuffler_bool,
    parse_seed as parse_list_shuffler_seed,
    parse_take as parse_list_shuffler_take,
    shuffle_lines,
    validate_text as validate_list_shuffler_text,
)
from app.text_formatter import (  # noqa: E402
    CHUNK_SIZE as TF_CHUNK_SIZE,
    INVALID_BOOLEAN as TF_INVALID_BOOLEAN,
    INVALID_REQUEST as TF_INVALID_REQUEST,
    INVALID_TAB_WIDTH as TF_INVALID_TAB_WIDTH,
    MAX_BYTES as TF_MAX_BYTES,
    MAX_CHARS as TF_MAX_CHARS,
    NO_TEXT as TF_NO_TEXT,
    NOT_TEXT as TF_NOT_TEXT,
    TOO_LONG as TF_TOO_LONG,
    UNSUPPORTED_BLANK_MODE as TF_UNSUPPORTED_BLANK_MODE,
    UNSUPPORTED_LINE_MODE as TF_UNSUPPORTED_LINE_MODE,
    TextFormatterError,
    check_size as check_text_formatter_size,
    format_text,
    normalize_blank_mode as normalize_text_formatter_blank_mode,
    normalize_line_mode as normalize_text_formatter_line_mode,
    parse_bool as parse_text_formatter_bool,
    parse_tab_width as parse_text_formatter_tab_width,
    validate_text as validate_text_formatter_text,
)
from app.unit_convert import (  # noqa: E402
    CATEGORIES as UC_CATEGORIES,
    INVALID_REQUEST as UC_INVALID_REQUEST,
    MAX_DIGITS as UC_MAX_DIGITS,
    MAX_INPUT_CHARS as UC_MAX_INPUT_CHARS,
    MAX_VALUE as UC_MAX_VALUE,
    NO_VALUE as UC_NO_VALUE,
    NOT_A_NUMBER as UC_NOT_A_NUMBER,
    OUT_OF_RANGE as UC_OUT_OF_RANGE,
    UNSUPPORTED_CATEGORY as UC_UNSUPPORTED_CATEGORY,
    UNSUPPORTED_UNIT as UC_UNSUPPORTED_UNIT,
    UnitConvertError,
    convert as convert_units,
    format_angka,
    format_angka as format_unit_number,
    parse_value as parse_unit_value,
    parse_value as unit_parse_value,
)
from app.percent_calc import (
    DIVIDE_BY_ZERO as PC_DIVIDE_BY_ZERO,
    INVALID_REQUEST as PC_INVALID_REQUEST,
    MAX_ABS_VALUE as PC_MAX_ABS_VALUE,
    MAX_INPUT_CHARS as PC_MAX_INPUT_CHARS,
    NO_VALUE as PC_NO_VALUE,
    NOT_A_NUMBER as PC_NOT_A_NUMBER,
    OUT_OF_RANGE as PC_OUT_OF_RANGE,
    PAYLOAD_TOO_LARGE as PC_PAYLOAD_TOO_LARGE,
    UNSUPPORTED_MODE as PC_UNSUPPORTED_MODE,
    PercentCalcError,
    compute_percent,
    format_angka as format_percent_number,
    limits_payload as percent_calc_limits_payload_func,
    parse_number as parse_percent_number,
)
from app.json_tool import (
    CHUNK_SIZE as JT_CHUNK_SIZE,
    INDENTS as JT_INDENTS,
    INVALID_BOOLEAN as JT_INVALID_BOOLEAN,
    INVALID_INDENT as JT_INVALID_INDENT,
    INVALID_JSON as JT_INVALID_JSON,
    INVALID_REQUEST as JT_INVALID_REQUEST,
    MAX_BYTES as JT_MAX_BYTES,
    MAX_CHARS as JT_MAX_CHARS,
    MAX_DEPTH as JT_MAX_DEPTH,
    MODES as JT_MODES,
    NO_TEXT as JT_NO_TEXT,
    PAYLOAD_TOO_LARGE as JT_PAYLOAD_TOO_LARGE,
    TOO_DEEP as JT_TOO_DEEP,
    TOO_LONG as JT_TOO_LONG,
    UNSUPPORTED_MODE as JT_UNSUPPORTED_MODE,
    JsonToolError,
    limits_payload as json_limits_payload_func,
    proses_json,
)
from app.date_calc import (
    DIRECTIONS as DC_DIRECTIONS,
    HARI as DC_HARI,
    INVALID_AMOUNT as DC_INVALID_AMOUNT,
    INVALID_DATE as DC_INVALID_DATE,
    INVALID_DIRECTION as DC_INVALID_DIRECTION,
    INVALID_REQUEST as DC_INVALID_REQUEST,
    INVALID_UNIT as DC_INVALID_UNIT,
    MAX_AMOUNT as DC_MAX_AMOUNT,
    MAX_INPUT_CHARS as DC_MAX_INPUT_CHARS,
    MAX_YEAR as DC_MAX_YEAR,
    MIN_YEAR as DC_MIN_YEAR,
    MODES as DC_MODES,
    NO_DATE as DC_NO_DATE,
    OUT_OF_RANGE as DC_OUT_OF_RANGE,
    PAYLOAD_TOO_LARGE as DC_PAYLOAD_TOO_LARGE,
    UNITS as DC_UNITS,
    UNSUPPORTED_MODE as DC_UNSUPPORTED_MODE,
    WIB as DC_WIB,
    DateCalcError,
    add_months,
    compute_date,
    format_date_id,
    format_date_long_id,
    hitung_hari_kerja_dan_akhir_pekan,
    hitung_tahun_bulan_hari,
    limits_payload as date_calc_limits_payload_func,
    parse_date,
)
from app.countdown import (
    DEFAULT_JAM as CD_DEFAULT_JAM,
    HARI as CD_HARI,
    INVALID_AMOUNT as CD_INVALID_AMOUNT,
    INVALID_DATE as CD_INVALID_DATE,
    INVALID_REQUEST as CD_INVALID_REQUEST,
    INVALID_TIME as CD_INVALID_TIME,
    INVALID_UNIT as CD_INVALID_UNIT,
    MAX_AMOUNT as CD_MAX_AMOUNT,
    MAX_BYTES as CD_MAX_BYTES,
    MAX_INPUT_CHARS as CD_MAX_INPUT_CHARS,
    MAX_YEAR as CD_MAX_YEAR,
    MIN_YEAR as CD_MIN_YEAR,
    MODES as CD_MODES,
    NO_DATE as CD_NO_DATE,
    OUT_OF_RANGE as CD_OUT_OF_RANGE,
    PAYLOAD_TOO_LARGE as CD_PAYLOAD_TOO_LARGE,
    SATUAN as CD_SATUAN,
    UNSUPPORTED_MODE as CD_UNSUPPORTED_MODE,
    WIB as CD_WIB,
    CountdownError,
    compute_countdown,
    limits_payload as countdown_limits_payload_func,
    parse_amount as parse_countdown_amount,
    parse_date as parse_countdown_date,
    parse_time as parse_countdown_time,
    parse_unit as parse_countdown_unit,
)
from app.pomodoro import (
    DEFAULT_SESI as PM_DEFAULT_SESI,
    INVALID_NUMBER as PM_INVALID_NUMBER,
    INVALID_RANGE as PM_INVALID_RANGE,
    INVALID_REQUEST as PM_INVALID_REQUEST,
    INVALID_START_TIME as PM_INVALID_START_TIME,
    MAX_BYTES as PM_MAX_BYTES,
    MAX_INPUT_CHARS as PM_MAX_INPUT_CHARS,
    MAX_ISTIRAHAT as PM_MAX_ISTIRAHAT,
    MAX_ISTIRAHAT_PANJANG as PM_MAX_ISTIRAHAT_PANJANG,
    MAX_KERJA as PM_MAX_KERJA,
    MAX_SESI as PM_MAX_SESI,
    MIN_ISTIRAHAT as PM_MIN_ISTIRAHAT,
    MIN_ISTIRAHAT_PANJANG as PM_MIN_ISTIRAHAT_PANJANG,
    MIN_KERJA as PM_MIN_KERJA,
    MIN_SESI as PM_MIN_SESI,
    MODES as PM_MODES,
    PAYLOAD_TOO_LARGE as PM_PAYLOAD_TOO_LARGE,
    UNSUPPORTED_MODE as PM_UNSUPPORTED_MODE,
    PomodoroError,
    compute_pomodoro,
    limits_payload as pomodoro_limits_payload_func,
    parse_int_field as parse_pomodoro_int_field,
    parse_start_time as parse_pomodoro_start_time,
)
from app.qr_tool import (
    DEFAULT_CORRECTION as QR_DEFAULT_CORRECTION,
    DEFAULT_MODE as QR_DEFAULT_MODE,
    DEFAULT_SIZE as QR_DEFAULT_SIZE,
    INVALID_CORRECTION as QR_INVALID_CORRECTION,
    INVALID_REQUEST as QR_INVALID_REQUEST,
    INVALID_SIZE as QR_INVALID_SIZE,
    MAX_BYTES as QR_MAX_BYTES,
    MAX_CHARS_BARCODE as QR_MAX_CHARS_BARCODE,
    MAX_CHARS_QR as QR_MAX_CHARS_QR,
    MODES as QR_MODES,
    NO_TEXT as QR_NO_TEXT,
    NOT_ENCODABLE as QR_NOT_ENCODABLE,
    PAYLOAD_TOO_LARGE as QR_PAYLOAD_TOO_LARGE,
    TEXT_TOO_LONG as QR_TEXT_TOO_LONG,
    UKURAN_LIST as QR_UKURAN_LIST,
    UNSUPPORTED_KIND as QR_UNSUPPORTED_KIND,
    QrResult,
    QrToolError,
    generate_code,
    limits_payload as qr_limits_payload_func,
    validate_params as validate_qr_params,
)
from app.image_edit import (  # noqa: E402
    EMPTY_FILE as EDIT_EMPTY_FILE,
    IMAGE_UNREADABLE as EDIT_IMAGE_UNREADABLE,
    INVALID_BOOLEAN as EDIT_INVALID_BOOLEAN,
    INVALID_QUALITY as EDIT_INVALID_QUALITY,
    INVALID_REQUEST as EDIT_INVALID_REQUEST,
    MAX_BYTES as EDIT_MAX_BYTES,
    MAX_PIXELS as EDIT_MAX_PIXELS,
    NOT_IMAGE as EDIT_NOT_IMAGE,
    PAYLOAD_TOO_LARGE as EDIT_PAYLOAD_TOO_LARGE,
    TOO_MANY_PIXELS as EDIT_TOO_MANY_PIXELS,
    UNSUPPORTED_ANCHOR as EDIT_UNSUPPORTED_ANCHOR,
    UNSUPPORTED_FLIP as EDIT_UNSUPPORTED_FLIP,
    UNSUPPORTED_RATIO as EDIT_UNSUPPORTED_RATIO,
    UNSUPPORTED_ROTATE as EDIT_UNSUPPORTED_ROTATE,
    UNSUPPORTED_TARGET as EDIT_UNSUPPORTED_TARGET,
    ImageEditError,
    crop_to_ratio as edit_crop_to_ratio,
    detect_format as detect_edit_format,
    edit_image,
    limits_payload as image_edit_limits_payload_func,
    normalize_anchor as edit_normalize_anchor,
    normalize_flip as edit_normalize_flip,
    normalize_orientation as edit_normalize_orientation,
    normalize_quality as edit_normalize_quality,
    normalize_ratio as edit_normalize_ratio,
    normalize_rotate as edit_normalize_rotate,
    normalize_target as edit_normalize_target,
)
from app.prime_generator import (
    INVALID_RANGE as PRIME_INVALID_RANGE,
    INVALID_REQUEST as PRIME_INVALID_REQUEST,
    MAX_BYTES as PRIME_MAX_BYTES,
    NO_VALUE as PRIME_NO_VALUE,
    NOT_A_NUMBER as PRIME_NOT_A_NUMBER,
    OUT_OF_RANGE as PRIME_OUT_OF_RANGE,
    PAYLOAD_TOO_LARGE as PRIME_PAYLOAD_TOO_LARGE,
    TIMEOUT as PRIME_TIMEOUT,
    TOO_MANY_RESULTS as PRIME_TOO_MANY_RESULTS,
    UNSUPPORTED_MODE as PRIME_UNSUPPORTED_MODE,
    PrimeError,
    factorize_number,
    generate_primes_deret,
    generate_primes_rentang,
    is_prime,
    limits_payload as prime_limits_payload_func,
    process_prime,
)
from app.timezone import (
    INVALID_DATE as TZ_INVALID_DATE,
    INVALID_RANGE as TZ_INVALID_RANGE,
    INVALID_REQUEST as TZ_INVALID_REQUEST,
    INVALID_TIME as TZ_INVALID_TIME,
    INVALID_ZONE as TZ_INVALID_ZONE,
    MAX_BYTES as TZ_MAX_BYTES,
    MAX_ZONES as TZ_MAX_ZONES,
    MODES as TZ_MODES,
    OUT_OF_RANGE as TZ_OUT_OF_RANGE,
    PAYLOAD_TOO_LARGE as TZ_PAYLOAD_TOO_LARGE,
    TOO_MANY_ZONES as TZ_TOO_MANY_ZONES,
    UNSUPPORTED_MODE as TZ_UNSUPPORTED_MODE,
    ZONES as TZ_ZONES,
    TimezoneError,
    limits_payload as timezone_limits_payload_func,
    proses_zona,
)
from app.csv_tool import (
    CHUNK_SIZE as CSV_CHUNK_SIZE,
    INDENTS as CSV_INDENTS,
    INVALID_BOOLEAN as CSV_INVALID_BOOLEAN,
    INVALID_FORMAT as CSV_INVALID_FORMAT,
    INVALID_INDENT as CSV_INVALID_INDENT,
    INVALID_JSON as CSV_INVALID_JSON,
    INVALID_REQUEST as CSV_INVALID_REQUEST,
    INVALID_SEPARATOR as CSV_INVALID_SEPARATOR,
    MAX_BYTES as CSV_MAX_BYTES,
    MAX_CHARS as CSV_MAX_CHARS,
    MAX_COLS as CSV_MAX_COLS,
    MAX_ROWS as CSV_MAX_ROWS,
    MODES as CSV_MODES,
    NO_TEXT as CSV_NO_TEXT,
    PAYLOAD_TOO_LARGE as CSV_PAYLOAD_TOO_LARGE,
    TOO_LONG as CSV_TOO_LONG,
    TOO_MANY_COLUMNS as CSV_TOO_MANY_COLUMNS,
    TOO_MANY_ROWS as CSV_TOO_MANY_ROWS,
    UNSUPPORTED_MODE as CSV_UNSUPPORTED_MODE,
    CsvToolError,
    limits_payload as csv_limits_payload_func,
    proses_csv,
)
from app.listrik import (
    DIVIDE_BY_ZERO as LK_DIVIDE_BY_ZERO,
    INVALID_REQUEST as LK_INVALID_REQUEST,
    LIST_KOSONG as LK_LIST_KOSONG,
    MAX_INPUT_CHARS as LK_MAX_INPUT_CHARS,
    NILAI_KURANG as LK_NILAI_KURANG,
    NOT_A_NUMBER as LK_NOT_A_NUMBER,
    OUT_OF_RANGE as LK_OUT_OF_RANGE,
    PAYLOAD_TOO_LARGE as LK_PAYLOAD_TOO_LARGE,
    TERLALU_BANYAK_NILAI as LK_TERLALU_BANYAK_NILAI,
    TOO_MANY_ITEMS as LK_TOO_MANY_ITEMS,
    UNSUPPORTED_JENIS as LK_UNSUPPORTED_JENIS,
    UNSUPPORTED_MODE as LK_UNSUPPORTED_MODE,
    ListrikError,
    format_angka as format_listrik_angka,
    format_rupiah as format_listrik_rupiah,
    hitung_daya,
    hitung_hambatan,
    hitung_listrik,
    hitung_ohm,
    limits_payload as listrik_limits_payload_func,
    parse_number as parse_listrik_number,
)


SKIPPED: list[str] = []


# --- Pembantu ----------------------------------------------------------------
def make_pdf(pages: int, label: str = "") -> bytes:
    """PDF uji di memori dengan jumlah halaman tertentu."""
    writer = PdfWriter()
    for index in range(pages):
        writer.add_blank_page(width=200, height=200)
    if label:
        writer.add_metadata({"/Title": label})
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_encrypted_pdf(pages: int = 1, password: str = "rahasia") -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    writer.encrypt(password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def page_count(data: bytes) -> int:
    return len(PdfReader(io.BytesIO(data)).pages)


def make_image(format: str = "PNG", size: tuple[int, int] = (60, 60), color: str = "blue", mode: str | None = None) -> bytes:
    """Buat berkas gambar uji di memori."""
    img_mode = mode or ("RGBA" if "A" in format.upper() else "RGB")
    img = Image.new(img_mode, size, color)
    buf = io.BytesIO()
    save_fmt = "JPEG" if format.upper() in ("JPG", "JPEG") else format.upper()
    img.save(buf, format=save_fmt)
    return buf.getvalue()


def make_svg(width: int | None = 200, height: int | None = 100) -> bytes:
    """SVG uji dengan gradasi + teks. Tanpa width/height bila argumen None."""
    dims = ""
    if width is not None and height is not None:
        dims = f' width="{width}" height="{height}"'
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"{dims} viewBox="0 0 200 100">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="red"/>
      <stop offset="100%" stop-color="blue"/>
    </linearGradient>
  </defs>
  <rect width="200" height="100" fill="url(#g)"/>
  <text x="10" y="50" font-size="20" fill="white">Hi</text>
</svg>""".encode("utf-8")


def make_ocr_png(text: str = "KUCING OREN") -> bytes:
    """Buat berkas PNG uji berisi teks jelas (font bawaan, kontras tinggi)."""
    img = Image.new("RGB", (400, 120), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((30, 40), text, fill="black")
    img_large = img.resize((800, 240), Image.Resampling.NEAREST)
    buf = io.BytesIO()
    img_large.save(buf, format="PNG")
    return buf.getvalue()


def make_ocr_pdf(page1_text: str = "SURAT SATU", page2_text: str = "BERKAS DUA") -> bytes:
    """Buat dokumen PDF uji 2 halaman dengan PyMuPDF berisi teks berbeda per halaman."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=300, height=100)
    p1.insert_text((30, 50), page1_text, fontsize=24, color=(0, 0, 0))
    p2 = doc.new_page(width=300, height=100)
    p2.insert_text((30, 50), page2_text, fontsize=24, color=(0, 0, 0))
    data = doc.tobytes()
    doc.close()
    return data


def make_many_page_pdf(pages: int = 16) -> bytes:
    """Buat dokumen PDF dengan sejumlah halaman tertentu."""
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=200, height=200)
    data = doc.tobytes()
    doc.close()
    return data



def expect_image_error(func, code: str, status: int) -> ImageConvertError:
    """Pastikan func() melempar ImageConvertError dengan kode + status yang tepat."""
    try:
        func()
    except ImageConvertError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar ImageConvertError {code}")


def expect_error(func, code: str, status: int) -> PdfMergeError:
    """Pastikan func() melempar PdfMergeError dengan kode + status yang tepat."""
    try:
        func()
    except PdfMergeError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar PdfMergeError {code}")


def expect_split_error(func, code: str, status: int) -> PdfSplitError:
    """Pastikan func() melempar PdfSplitError dengan kode + status yang tepat."""
    try:
        func()
    except PdfSplitError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar PdfSplitError {code}")


def expect_compress_error(func, code: str, status: int) -> PdfCompressError:
    """Pastikan func() melempar PdfCompressError dengan kode + status yang tepat."""
    try:
        func()
    except PdfCompressError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar PdfCompressError {code}")


def expect_pdf_to_image_error(func, code: str, status: int) -> PdfToImageError:
    """Pastikan func() melempar PdfToImageError dengan kode + status yang tepat."""
    try:
        func()
    except PdfToImageError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar PdfToImageError {code}")


def expect_word_count_error(func, code: str, status: int) -> WordCountError:
    """Pastikan func() melempar WordCountError dengan kode + status yang tepat."""
    try:
        func()
    except WordCountError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar WordCountError {code}")


def expect_case_convert_error(func, code: str, status: int) -> CaseConvertError:
    """Pastikan func() melempar CaseConvertError dengan kode + status yang tepat."""
    try:
        func()
    except CaseConvertError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar CaseConvertError {code}")


def expect_base64_error(func, code: str, status: int) -> Base64ToolError:
    """Pastikan func() melempar Base64ToolError dengan kode dan status yang tepat."""
    try:
        func()
    except Base64ToolError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar Base64ToolError {code}")


def expect_image_edit_error(func, code: str, status: int) -> ImageEditError:
    """Pastikan func() melempar ImageEditError dengan kode + status yang tepat."""
    try:
        func()
    except ImageEditError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar ImageEditError {code}")


def expect_prime_error(func, code: str, status: int) -> PrimeError:
    """Pastikan func() melempar PrimeError dengan kode + status yang tepat."""
    try:
        func()
    except PrimeError as exc:
        assert exc.code == code, f"kode error {exc.code!r}, diharapkan {code!r}"
        assert exc.status_code == status, f"status {exc.status_code}, diharapkan {status}"
        body = exc.to_dict()
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        return exc
    raise AssertionError(f"tidak melempar PrimeError {code}")




# --- Uji logika murni --------------------------------------------------------
def test_magic_bytes_menerima_pdf_asli_menolak_palsu() -> None:
    assert is_pdf_bytes(make_pdf(1)) is True
    assert is_pdf_bytes(b"") is False
    assert is_pdf_bytes(b"ini file txt yang dinamai .pdf") is False
    assert is_pdf_bytes(b"%PDF-1.4\n") is True  # header saja: format benar, isi nanti dinilai


def test_merge_dua_dan_tiga_halaman_menjadi_lima() -> None:
    a = make_pdf(2, "A")
    b = make_pdf(3, "B")
    result = merge_pdfs([a, b])
    assert result.file_count == 2
    assert result.page_count == 5, f"total halaman {result.page_count}, diharapkan 5"
    assert result.page_counts == (2, 3)
    assert result.passthrough is False
    assert page_count(result.data) == 5
    assert result.data.startswith(b"%PDF-")


def test_urutan_berkas_diikuti() -> None:
    """Urutan kiriman menentukan urutan halaman (2+3 vs 3+2)."""
    a = make_pdf(2)
    b = make_pdf(3)
    assert merge_pdfs([a, b]).page_counts == (2, 3)
    assert merge_pdfs([b, a]).page_counts == (3, 2)


def test_satu_berkas_dikembalikan_apa_adanya() -> None:
    a = make_pdf(4)
    result = merge_pdfs([a])
    assert result.passthrough is True
    assert result.data == a, "berkas tunggal harus byte-identik"
    assert result.page_count == 4


def test_menolak_bukan_pdf() -> None:
    expect_error(lambda: merge_pdfs([b"bukan pdf sama sekali"]), ERR_NOT_PDF, 400)


def test_menolak_berkas_kosong() -> None:
    expect_error(lambda: merge_pdfs([b""]), ERR_EMPTY_FILE, 400)


def test_menolak_tanpa_berkas() -> None:
    expect_error(lambda: merge_pdfs([]), ERR_NO_FILES, 400)


def test_menolak_lebih_dari_sepuluh_berkas() -> None:
    payloads = [make_pdf(1) for _ in range(MAX_FILES + 1)]
    expect_error(lambda: merge_pdfs(payloads), ERR_TOO_MANY_FILES, 400)


def test_sepuluh_berkas_masih_diterima() -> None:
    payloads = [make_pdf(1) for _ in range(MAX_FILES)]
    result = merge_pdfs(payloads)
    assert result.file_count == MAX_FILES
    assert result.page_count == MAX_FILES


def test_menolak_total_ukuran_lewat_batas() -> None:
    check_total_size(MAX_TOTAL_BYTES)  # tepat di batas: boleh
    expect_error(lambda: check_total_size(MAX_TOTAL_BYTES + 1), ERR_TOO_LARGE, 413)
    besar = b"%PDF-1.4\n" + b"0" * (MAX_TOTAL_BYTES + 1024)
    expect_error(lambda: merge_pdfs([besar]), ERR_TOO_LARGE, 413)


def test_menolak_lebih_dari_dua_ratus_halaman() -> None:
    banyak = make_pdf(MAX_TOTAL_PAGES + 1)
    expect_error(lambda: merge_pdfs([banyak]), ERR_TOO_MANY_PAGES, 413)


def test_menolak_pdf_rusak() -> None:
    rusak = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog\n" + b"x" * 200
    expect_error(lambda: merge_pdfs([rusak]), ERR_UNREADABLE, 422)


def test_menolak_pdf_terproteksi_sandi() -> None:
    expect_error(lambda: merge_pdfs([make_encrypted_pdf(1)]), ERR_ENCRYPTED, 422)


# --- Uji logika Image Converter ---------------------------------------------
def test_image_magic_bytes_detection() -> None:
    png_data = make_image("PNG")
    jpeg_data = make_image("JPEG")
    webp_data = make_image("WEBP")

    assert detect_format(png_data) == "png"
    assert detect_format(jpeg_data) == "jpeg"
    assert detect_format(webp_data) == "webp"
    assert is_supported_image(png_data) is True
    assert is_supported_image(jpeg_data) is True
    assert is_supported_image(webp_data) is True

    assert detect_format(b"") is None
    assert detect_format(b"bukan gambar") is None
    assert is_supported_image(b"bukan gambar") is False


def test_image_convert_png_ke_jpeg_sukses() -> None:
    png = make_image("PNG", size=(50, 50), color="green")
    result = convert_image(png, target="jpeg", quality=85)
    assert result.input_format == "png"
    assert result.output_format == "jpeg"
    assert result.width == 50
    assert result.height == 50
    assert result.data.startswith(b"\xff\xd8\xff")
    assert detect_format(result.data) == "jpeg"


def test_image_convert_jpeg_ke_webp_sukses() -> None:
    jpeg = make_image("JPEG", size=(40, 40), color="red")
    result = convert_image(jpeg, target="webp", quality=80)
    assert result.input_format == "jpeg"
    assert result.output_format == "webp"
    assert detect_format(result.data) == "webp"


def test_image_convert_png_ke_png_sukses() -> None:
    png = make_image("PNG", size=(30, 30), color="yellow")
    result = convert_image(png, target="png")
    assert result.input_format == "png"
    assert result.output_format == "png"
    assert detect_format(result.data) == "png"


def test_image_convert_format_target_sama_dengan_masukan() -> None:
    jpeg = make_image("JPEG", size=(35, 35), color="blue")
    result_jpeg = convert_image(jpeg, target="jpeg")
    assert result_jpeg.output_format == "jpeg"

    webp = make_image("WEBP", size=(35, 35), color="cyan")
    result_webp = convert_image(webp, target="webp")
    assert result_webp.output_format == "webp"


def test_image_convert_kualitas_rendah_lebih_kecil_dari_kualitas_tinggi() -> None:
    img = Image.new("RGB", (120, 120))
    pixels = img.load()
    for x in range(120):
        for y in range(120):
            pixels[x, y] = ((x * 7) % 256, (y * 11) % 256, ((x + y) * 13) % 256)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    png_bytes = buf.getvalue()

    res_q20 = convert_image(png_bytes, target="jpeg", quality=20)
    res_q95 = convert_image(png_bytes, target="jpeg", quality=95)
    assert len(res_q20.data) < len(res_q95.data), (
        f"Kualitas 20 ({len(res_q20.data)} bytes) harus lebih kecil dari 95 ({len(res_q95.data)} bytes)"
    )


def test_image_convert_alpha_ke_jpeg_latar_putih() -> None:
    img = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    png_transparent = buf.getvalue()

    result = convert_image(png_transparent, target="jpeg")
    assert result.output_format == "jpeg"
    out_img = Image.open(io.BytesIO(result.data))
    assert out_img.mode == "RGB"
    assert out_img.getpixel((0, 0)) == (255, 255, 255)


def test_image_convert_menolak_tanpa_berkas() -> None:
    expect_image_error(lambda: check_image_file_count(0), IMG_NO_FILES, 400)


def test_image_convert_menolak_dua_berkas() -> None:
    expect_image_error(lambda: check_image_file_count(2), IMG_TOO_MANY_FILES, 400)


def test_image_convert_menolak_berkas_kosong() -> None:
    expect_image_error(lambda: convert_image(b""), IMG_EMPTY_FILE, 400)


def test_image_convert_menolak_bukan_gambar() -> None:
    expect_image_error(lambda: convert_image(b"ini berkas teks yang dinamai gambar.png"), IMG_NOT_IMAGE, 400)


def test_image_convert_menolak_target_tidak_didukung() -> None:
    png = make_image("PNG")
    expect_image_error(lambda: convert_image(png, target="gif"), IMG_UNSUPPORTED_TARGET, 400)
    expect_image_error(lambda: convert_image(png, target="tiff"), IMG_UNSUPPORTED_TARGET, 400)


def test_image_convert_menolak_kualitas_tidak_valid() -> None:
    png = make_image("PNG")
    expect_image_error(lambda: convert_image(png, quality=0), IMG_INVALID_QUALITY, 400)
    expect_image_error(lambda: convert_image(png, quality=101), IMG_INVALID_QUALITY, 400)
    expect_image_error(lambda: convert_image(png, quality="abc"), IMG_INVALID_QUALITY, 400)


def test_image_convert_menolak_gambar_rusak() -> None:
    corrupted = b"\x89PNG\r\n\x1a\n" + b"xyz" * 50
    expect_image_error(lambda: convert_image(corrupted, target="jpeg"), IMG_IMAGE_UNREADABLE, 422)


def test_image_convert_menolak_ukuran_lewat_batas() -> None:
    expect_image_error(lambda: check_image_total_size(IMG_MAX_BYTES + 1), IMG_PAYLOAD_TOO_LARGE, 413)


def test_image_convert_svg_20000x20000_diperkecil() -> None:
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="20000" height="20000">'
        b'<rect width="20000" height="20000" fill="blue"/>'
        b'</svg>'
    )
    res = convert_image(svg, target="png")
    assert res.scaled_down is True
    assert res.width * res.height <= IMG_MAX_PIXELS
    assert max(res.width, res.height) <= IMG_SVG_MAX_SIDE


def test_image_convert_svg_ekstrem_400000x1_diperkecil() -> None:
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="400000" height="1">'
        b'<rect width="400000" height="1" fill="red"/>'
        b'</svg>'
    )
    res = convert_image(svg, target="png")
    assert res.scaled_down is True
    assert max(res.width, res.height) <= IMG_SVG_MAX_SIDE
    assert res.width * res.height <= IMG_MAX_PIXELS


def test_image_convert_svg_viewbox_200x100_tanpa_width() -> None:
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">'
        b'<rect width="200" height="100" fill="green"/>'
        b'</svg>'
    )
    res = convert_image(svg, target="png")
    assert res.scaled_down is False
    assert (res.width, res.height) == (1024, 512)


def test_image_convert_svg_1500x800_tanpa_width() -> None:
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="800">'
        b'<rect width="1500" height="800" fill="blue"/>'
        b'</svg>'
    )
    res = convert_image(svg, target="png")
    assert res.scaled_down is False
    assert (res.width, res.height) == (1500, 800)


def test_image_convert_svg_24x24_viewbox_saja() -> None:
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<circle cx="12" cy="12" r="10" fill="red"/>'
        b'</svg>'
    )
    res = convert_image(svg, target="png")
    assert res.scaled_down is False
    assert (res.width, res.height) == (1024, 1024)


def test_image_convert_svg_600x300_tanpa_width() -> None:
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300">'
        b'<rect width="600" height="300" fill="green"/>'
        b'</svg>'
    )
    res = convert_image(svg, target="png")
    assert res.scaled_down is False
    assert (res.width, res.height) == (1024, 512)


def test_image_convert_svg_600x300_width_400() -> None:
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300">'
        b'<rect width="600" height="300" fill="green"/>'
        b'</svg>'
    )
    res = convert_image(svg, target="png", width=400)
    assert res.scaled_down is False
    assert (res.width, res.height) == (400, 200)


# --- Uji logika Word Counter ------------------------------------------------
def test_word_count_logika_teks_normal() -> None:
    res = count_text("Halo dunia. Ini uji coba!")
    assert res.chars == 25
    assert res.chars_no_spaces == 21
    assert res.words == 5
    assert res.unique_words == 5
    assert res.sentences == 2
    assert res.paragraphs == 1
    assert res.lines == 1
    assert res.reading_minutes == 1
    assert res.speaking_minutes == 1
    assert res.longest_word == "dunia"
    # 'ini' dan 'uji' < 4 huruf, jadi tidak masuk top_words
    top_dict = {item["word"]: item["count"] for item in res.top_words}
    assert top_dict == {"halo": 1, "dunia": 1, "coba": 1}


def test_word_count_logika_paragraf_dan_baris() -> None:
    text = (
        "Paragraf pertama terdiri dari dua baris.\n"
        "Ini baris kedua pada paragraf pertama.\n\n"
        "Paragraf kedua hanya satu baris.\n\n\n"
        "Paragraf ketiga adalah penutup."
    )
    res = count_text(text)
    assert res.paragraphs == 3
    assert res.lines == 4
    assert res.sentences == 4


def test_word_count_logika_case_insensitive_dan_top_words() -> None:
    # "Kucing" ditulis dengan variasi kapital, stop words Indonesia ("dan", "di", "itu") diabaikan
    text = "Kucing makan ikan. kucing dan KUCING tidur di kasur itu! Ikan sangat lezat."
    res = count_text(text)
    assert res.words == 13
    # unique_words tidak peka huruf besar-kecil
    lower_set = {
        "kucing", "makan", "ikan", "dan", "tidur", "di", "kasur", "itu", "sangat", "lezat"
    }
    assert res.unique_words == len(lower_set)
    # top_words: 'kucing' 3 kali, 'ikan' 2 kali; stopword 'dan', 'di', 'itu' tidak muncul
    top_dict = {item["word"]: item["count"] for item in res.top_words}
    assert top_dict["kucing"] == 3
    assert top_dict["ikan"] == 2
    for sw in WC_STOP_WORDS:
        assert sw not in top_dict


def test_word_count_logika_waktu_baca_dan_bicara() -> None:
    # 250 kata: waktu baca ceil(250/200) = 2 menit, waktu bicara ceil(250/130) = 2 menit
    words_250 = " ".join(["kata"] * 250)
    res = count_text(words_250)
    assert res.words == 250
    assert res.reading_minutes == 2
    assert res.speaking_minutes == 2

    # 1 kata: minimal 1 menit
    res_one = count_text("Satu")
    assert res_one.words == 1
    assert res_one.reading_minutes == 1
    assert res_one.speaking_minutes == 1


def test_word_count_logika_kata_terpanjang_seri() -> None:
    # Bila ada beberapa kata dengan panjang sama, kata pertama yang ditemukan dipilih
    res = count_text("satu dua tiga")  # 'satu' dan 'tiga' sama-sama 4 huruf
    assert res.longest_word == "satu"


def test_word_count_logika_menolak_teks_kosong() -> None:
    expect_word_count_error(lambda: count_text(""), WC_NO_TEXT, 400)


def test_word_count_logika_menolak_hanya_spasi() -> None:
    expect_word_count_error(lambda: count_text("   \n\t  "), WC_NO_TEXT, 400)


def test_word_count_logika_menolak_terlalu_panjang() -> None:
    long_text = "a" * (WC_MAX_CHARS + 1)
    expect_word_count_error(lambda: count_text(long_text), WC_TOO_LONG, 413)


def test_word_count_logika_menolak_none() -> None:
    expect_word_count_error(lambda: count_text(None), WC_INVALID_REQUEST, 400)  # type: ignore[arg-type]


def test_case_convert_logika_semua_mode() -> None:
    # Uji 10 mode menghasilkan keluaran yang benar sesuai spesifikasi
    assert convert_case("halo dunia", "upper").text == "HALO DUNIA"
    assert convert_case("HALO DUNIA", "lower").text == "halo dunia"
    assert convert_case("halo dunia don't stop dua-tiga", "title").text == "Halo Dunia Don't Stop Dua-tiga"
    assert convert_case("halo dunia. apa kabar? baik! tentu saja.\nbaris baru", "sentence").text == (
        "Halo dunia. Apa kabar? Baik! Tentu saja.\nBaris baru"
    )
    assert convert_case("Halo Dunia 123", "inverse").text == "hALO dUNIA 123"
    assert convert_case("abcd", "alternating").text == "aBcD"
    assert convert_case("a b c d", "alternating").text == "a B c D"
    assert convert_case("halo dunia", "camel").text == "haloDunia"
    assert convert_case("halo dunia", "snake").text == "halo_dunia"
    assert convert_case("halo dunia", "kebab").text == "halo-dunia"
    assert convert_case("Halo, Dunia! 2x", "slug").text == "halo-dunia-2x"


def test_case_convert_logika_changed() -> None:
    res_unchanged = convert_case("halo dunia", "lower")
    assert res_unchanged.changed is False
    res_changed = convert_case("halo dunia", "upper")
    assert res_changed.changed is True


def test_case_convert_logika_menolak_teks_kosong() -> None:
    expect_case_convert_error(lambda: convert_case("", "upper"), CC_NO_TEXT, 400)


def test_case_convert_logika_menolak_hanya_spasi() -> None:
    expect_case_convert_error(lambda: convert_case("   \n\t  ", "upper"), CC_NO_TEXT, 400)


def test_case_convert_logika_menolak_terlalu_panjang() -> None:
    long_text = "a" * (CC_MAX_CHARS + 1)
    expect_case_convert_error(lambda: convert_case(long_text, "upper"), CC_TOO_LONG, 413)


def test_case_convert_logika_menolak_none_text() -> None:
    expect_case_convert_error(lambda: convert_case(None, "upper"), CC_INVALID_REQUEST, 400)


def test_case_convert_logika_mode_tidak_valid() -> None:
    expect_case_convert_error(lambda: convert_case("halo", None), CC_INVALID_REQUEST, 400)
    expect_case_convert_error(lambda: convert_case("halo", ""), CC_INVALID_REQUEST, 400)
    expect_case_convert_error(lambda: convert_case("halo", "mode_palsu"), CC_UNSUPPORTED_MODE, 400)


def test_base64_logika_encode_biasa() -> None:
    import base64
    text = "Halo, dunia!"
    res = convert_base64(text, "encode")
    expected = base64.b64encode(text.encode("utf-8")).decode("ascii")
    assert res.text == expected
    assert res.mode == "encode"
    assert res.variant == "standard"
    assert res.wrap == 0
    assert res.chars_in == len(text)
    assert res.bytes_in == len(text.encode("utf-8"))
    assert res.chars_out == len(expected)
    assert res.bytes_out == len(expected.encode("utf-8"))
    assert res.changed is True


def test_base64_logika_encode_aksen_dan_emoji() -> None:
    import base64
    text = "Halo dunia! 🌟 café & résumé ☕"
    res = convert_base64(text, "encode")
    expected = base64.b64encode(text.encode("utf-8")).decode("ascii")
    assert res.text == expected


def test_base64_logika_urlsafe_encode() -> None:
    import base64
    text = ">>> ??? ~~~"
    res_std = convert_base64(text, "encode", variant="standard")
    res_url = convert_base64(text, "encode", variant="urlsafe")
    expected_url = base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")
    assert res_url.text == expected_url
    assert "+" in res_std.text or "/" in res_std.text
    assert "-" in res_url.text or "_" in res_url.text
    assert "+" not in res_url.text and "/" not in res_url.text


def test_base64_logika_wrap_76() -> None:
    import base64
    text = "Kalimat panjang yang menghasilkan Base64 lebih dari 76 karakter untuk memastikan pemotongan baris tepat."
    res = convert_base64(text, "encode", wrap=76)
    lines = res.text.split("\n")
    assert len(lines) > 1
    for line in lines:
        assert len(line) <= 76
    expected_full = base64.b64encode(text.encode("utf-8")).decode("ascii")
    assert "".join(lines) == expected_full


def test_base64_logika_wrap_64() -> None:
    text = "Kalimat panjang yang menghasilkan Base64 lebih dari 64 karakter untuk verifikasi."
    res = convert_base64(text, "encode", wrap=64)
    lines = res.text.split("\n")
    assert len(lines) > 1
    for line in lines:
        assert len(line) <= 64


def test_base64_logika_decode_bolak_balik() -> None:
    samples = [
        "Halo, dunia!",
        "Selamat pagi, apa kabar?",
        "Teks berbaris satu\nbaris dua\nbaris tiga",
        "Emoji test 🚀🔥🌈",
    ]
    for sample in samples:
        enc = convert_base64(sample, "encode")
        dec = convert_base64(enc.text, "decode")
        assert dec.text == sample
        assert dec.mode == "decode"
        assert dec.chars_out == len(sample)


def test_base64_logika_decode_toleran() -> None:
    import base64
    text = "Halo, dunia!"
    raw_b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")

    # Data URI prefix
    data_uri = f"data:text/plain;base64,{raw_b64}"
    assert convert_base64(data_uri, "decode").text == text

    # Whitespace dan baris baru
    with_spaces = f" \n\t {raw_b64[:4]} \n {raw_b64[4:]} \t\n "
    assert convert_base64(with_spaces, "decode").text == text

    # Padding hilang
    unpadded = raw_b64.rstrip("=")
    assert convert_base64(unpadded, "decode").text == text

    # Kombinasi data URI, spasi, dan tanpa padding
    combo = f" data:text/plain;base64, \n {unpadded} \t\n "
    assert convert_base64(combo, "decode").text == text


def test_base64_logika_decode_urlsafe_alfabet() -> None:
    text = ">>> ??? ~~~"
    enc_url = convert_base64(text, "encode", variant="urlsafe")
    assert ("-" in enc_url.text) or ("_" in enc_url.text)
    dec = convert_base64(enc_url.text, "decode")
    assert dec.text == text


def test_base64_logika_menolak_teks_kosong_dan_spasi() -> None:
    expect_base64_error(lambda: convert_base64("", "encode"), B64_NO_TEXT, 400)
    expect_base64_error(lambda: convert_base64("   \n\t  ", "encode"), B64_NO_TEXT, 400)
    expect_base64_error(lambda: convert_base64("", "decode"), B64_NO_TEXT, 400)
    expect_base64_error(lambda: convert_base64("data:text/plain;base64,", "decode"), B64_NO_TEXT, 400)


def test_base64_logika_menolak_none_text() -> None:
    expect_base64_error(lambda: convert_base64(None, "encode"), B64_INVALID_REQUEST, 400)
    expect_base64_error(lambda: convert_base64(None, "decode"), B64_INVALID_REQUEST, 400)


def test_base64_logika_menolak_invalid_base64() -> None:
    # Karakter di luar alfabet Base64
    expect_base64_error(lambda: convert_base64("Halo Dunia!", "decode"), B64_INVALID_BASE64, 400)
    # Panjang mustahil (sisa 1 karakter)
    expect_base64_error(lambda: convert_base64("A", "decode"), B64_INVALID_BASE64, 400)
    expect_base64_error(lambda: convert_base64("AAAAA", "decode"), B64_INVALID_BASE64, 400)
    # Samadengan di tengah atau salah posisi
    expect_base64_error(lambda: convert_base64("AA=A", "decode"), B64_INVALID_BASE64, 400)
    expect_base64_error(lambda: convert_base64("AAAA=", "decode"), B64_INVALID_BASE64, 400)


def test_base64_logika_mode_dan_opsi_tidak_valid() -> None:
    expect_base64_error(lambda: convert_base64("halo", None), B64_INVALID_REQUEST, 400)
    expect_base64_error(lambda: convert_base64("halo", ""), B64_INVALID_REQUEST, 400)
    expect_base64_error(lambda: convert_base64("halo", "mode_palsu"), B64_UNSUPPORTED_MODE, 400)
    expect_base64_error(lambda: convert_base64("halo", "encode", variant="invalid_var"), B64_INVALID_VARIANT, 400)
    expect_base64_error(lambda: convert_base64("halo", "encode", wrap=50), B64_INVALID_WRAP, 400)


def test_base64_logika_menolak_terlalu_panjang() -> None:
    long_text = "a" * (B64_MAX_CHARS + 1)
    expect_base64_error(lambda: convert_base64(long_text, "encode"), B64_TOO_LONG, 413)


def test_base64_logika_menolak_data_biner_bukan_teks() -> None:
    import base64
    binary_bytes = bytes(range(256))
    binary_b64 = base64.b64encode(binary_bytes).decode("ascii")
    expect_base64_error(lambda: convert_base64(binary_b64, "decode"), B64_NOT_TEXT, 400)




# --- Uji HTTP lewat TestClient (butuh httpx) ---------------------------------
def _test_client():
    try:
        from fastapi.testclient import TestClient
        from app.main import app
    except Exception as exc:  # httpx belum terpasang, dsb.
        SKIPPED.append(f"uji HTTP TestClient dilewati: {exc}")
        return None
    return TestClient(app)


def test_http_health() -> None:
    client = _test_client()
    if client is None:
        return
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "omnitools-api"
    assert body["version"] == __version__


def test_http_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/pdf/merge/limits")
    assert response.status_code == 200
    body = response.json()
    assert body["max_files"] == MAX_FILES
    assert body["max_total_mb"] == 25
    assert body["max_pages"] == MAX_TOTAL_PAGES
    assert response.headers["cache-control"] == "no-store"


def test_http_merge_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/pdf/merge",
        files=[
            ("files", ("a.pdf", make_pdf(2), "application/pdf")),
            ("files", ("b.pdf", make_pdf(3), "application/pdf")),
        ],
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert 'filename="gabungan.pdf"' in response.headers["content-disposition"]
    assert response.headers["cache-control"].startswith("no-store")
    assert response.headers["x-page-count"] == "5"
    assert response.headers["x-file-count"] == "2"
    assert page_count(response.content) == 5


def test_http_merge_txt_dinamai_pdf_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/pdf/merge",
        files=[("files", ("palsu.pdf", b"ini bukan pdf", "application/pdf"))],
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == ERR_NOT_PDF
    assert body["error"]["message"]


def test_http_merge_sebelas_berkas_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    files = [("files", (f"f{i}.pdf", make_pdf(1), "application/pdf")) for i in range(MAX_FILES + 1)]
    response = client.post("/api/pdf/merge", files=files)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == ERR_TOO_MANY_FILES


def test_http_merge_tanpa_berkas_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/pdf/merge", files=[])
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "NO_FILES"


def test_http_image_convert_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/image/convert/limits")
    assert response.status_code == 200
    body = response.json()
    assert body["max_files"] == IMG_MAX_FILES
    assert body["max_bytes"] == IMG_MAX_BYTES
    assert body["max_total_mb"] == 15
    assert body["max_pixels"] == IMG_MAX_PIXELS
    assert body["targets"] == ["jpeg", "png", "webp"]
    assert body["target_labels"]["jpeg"] == "JPG"
    assert body["quality_min"] == 10
    assert body["quality_max"] == 100
    assert body["quality_default"] == 85
    assert "svg" in body["inputs"]
    assert body["svgMaxWidth"] == IMG_SVG_MAX_WIDTH
    assert body["svgDefaultWidth"] == IMG_SVG_DEFAULT_WIDTH
    assert response.headers["cache-control"] == "no-store"


def test_http_image_convert_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    png_data = make_image("PNG", size=(60, 60), color="magenta")
    response = client.post(
        "/api/image/convert",
        files=[("files", ("test.png", png_data, "image/png"))],
        data={"format": "jpeg", "quality": "80"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/jpeg")
    assert 'filename="hasil.jpg"' in response.headers["content-disposition"]
    assert response.headers["cache-control"].startswith("no-store")
    assert response.headers["x-input-format"] == "png"
    assert response.headers["x-output-format"] == "jpeg"
    assert response.headers["x-pixels"] == "3600"
    assert response.headers["x-total-bytes"] == str(len(response.content))
    assert "x-processing-ms" in response.headers
    assert response.content.startswith(b"\xff\xd8\xff")


def test_http_image_convert_tanpa_berkas_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/image/convert", files=[])
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_NO_FILES


def test_http_image_convert_dua_berkas_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    files = [
        ("files", ("a.png", make_image("PNG"), "image/png")),
        ("files", ("b.png", make_image("PNG"), "image/png")),
    ]
    response = client.post("/api/image/convert", files=files)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_TOO_MANY_FILES


def test_http_image_convert_bukan_gambar_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/image/convert",
        files=[("files", ("palsu.png", b"ini cuma teks", "image/png"))],
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_NOT_IMAGE


def test_http_image_convert_kualitas_tidak_valid_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/image/convert",
        files=[("files", ("test.png", make_image("PNG"), "image/png"))],
        data={"quality": "150"},
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_INVALID_QUALITY


def test_http_image_convert_svg_ke_png_ukuran_asli() -> None:
    client = _test_client()
    if client is None:
        return
    svg = make_svg(width=1500, height=800)
    response = client.post(
        "/api/image/convert",
        files=[("files", ("test.svg", svg, "image/svg+xml"))],
        data={"format": "png"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-input-format"] == "svg"
    assert response.headers["x-output-format"] == "png"
    assert response.headers["x-pixels"] == str(1500 * 800)
    out_img = Image.open(io.BytesIO(response.content))
    assert out_img.size == (1500, 800)


def test_http_image_convert_svg_dengan_width_kustom() -> None:
    client = _test_client()
    if client is None:
        return
    svg = make_svg(width=200, height=100)
    response = client.post(
        "/api/image/convert",
        files=[("files", ("test.svg", svg, "image/svg+xml"))],
        data={"format": "png", "width": "400"},
    )
    assert response.status_code == 200, response.text
    out_img = Image.open(io.BytesIO(response.content))
    assert out_img.size == (400, 200)


def test_http_image_convert_svg_ke_jpg_dan_webp() -> None:
    client = _test_client()
    if client is None:
        return
    svg = make_svg(width=60, height=60)

    resp_jpg = client.post(
        "/api/image/convert",
        files=[("files", ("test.svg", svg, "image/svg+xml"))],
        data={"format": "jpeg"},
    )
    assert resp_jpg.status_code == 200, resp_jpg.text
    assert resp_jpg.headers["content-type"].startswith("image/jpeg")
    out_jpg = Image.open(io.BytesIO(resp_jpg.content))
    assert out_jpg.mode == "RGB"

    resp_jpg2 = client.post(
        "/api/image/convert",
        files=[("files", ("test.svg", svg, "image/svg+xml"))],
        data={"format": "jpg"},
    )
    assert resp_jpg2.status_code == 200, resp_jpg2.text
    assert resp_jpg2.headers["content-type"].startswith("image/jpeg")

    resp_webp = client.post(
        "/api/image/convert",
        files=[("files", ("test.svg", svg, "image/svg+xml"))],
        data={"format": "webp"},
    )
    assert resp_webp.status_code == 200, resp_webp.text
    assert resp_webp.headers["content-type"].startswith("image/webp")
    assert detect_format(resp_webp.content) == "webp"


def test_http_image_convert_svg_berbahaya_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    svg_doctype = (
        b'<?xml version="1.0"?><!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
        b'"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("evil.svg", svg_doctype, "image/svg+xml"))],
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_UNSAFE_SVG

    svg_script = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
        b"<script>alert(1)</script></svg>"
    )
    response2 = client.post(
        "/api/image/convert",
        files=[("files", ("evil2.svg", svg_script, "image/svg+xml"))],
    )
    assert response2.status_code == 400, response2.text
    assert response2.json()["error"]["code"] == IMG_UNSAFE_SVG


def test_http_image_convert_svg_xlink_href_eksternal_ditolak() -> None:
    client = _test_client()
    if client is None:
        return
    svg_href = (
        b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        b'width="50" height="50"><image xlink:href="http://example.com/x.png" '
        b'width="50" height="50"/></svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("href.svg", svg_href, "image/svg+xml"))],
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_UNSAFE_SVG


def test_http_image_convert_svg_rusak_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    svg_rusak = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">terpotong'
    response = client.post(
        "/api/image/convert",
        files=[("files", ("rusak.svg", svg_rusak, "image/svg+xml"))],
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_INVALID_SVG


def test_http_image_convert_width_tidak_valid_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    svg = make_svg(width=100, height=100)
    response = client.post(
        "/api/image/convert",
        files=[("files", ("test.svg", svg, "image/svg+xml"))],
        data={"format": "png", "width": "99999"},
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == IMG_INVALID_WIDTH


def test_http_image_convert_svg_20000x20000_diperkecil_waktu_wajar() -> None:
    client = _test_client()
    if client is None:
        return
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="20000" height="20000">\n'
        b'  <rect width="20000" height="20000" fill="blue"/>\n'
        b'</svg>'
    )
    t0 = time.perf_counter()
    response = client.post(
        "/api/image/convert",
        files=[("files", ("besar.svg", svg, "image/svg+xml"))],
        data={"format": "png"},
    )
    elapsed = time.perf_counter() - t0
    assert response.status_code == 200, response.text
    assert elapsed < 5.0, f"Waktu render terlalu lama: {elapsed:.2f} detik"
    assert response.headers["x-scaled-down"] == "true"
    out_img = Image.open(io.BytesIO(response.content))
    total_pixels = out_img.width * out_img.height
    assert total_pixels <= IMG_MAX_PIXELS, f"Piksel melebihi batas: {total_pixels}"
    assert max(out_img.width, out_img.height) <= IMG_SVG_MAX_SIDE


def test_http_image_convert_svg_ekstrem_400000x1_diperkecil() -> None:
    client = _test_client()
    if client is None:
        return
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="400000" height="1">\n'
        b'  <rect width="400000" height="1" fill="red"/>\n'
        b'</svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("gepeng.svg", svg, "image/svg+xml"))],
        data={"format": "png"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-scaled-down"] == "true"
    out_img = Image.open(io.BytesIO(response.content))
    assert max(out_img.width, out_img.height) <= IMG_SVG_MAX_SIDE
    assert out_img.width * out_img.height <= IMG_MAX_PIXELS


def test_http_image_convert_svg_viewbox_200x100_tanpa_width() -> None:
    client = _test_client()
    if client is None:
        return
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">\n'
        b'  <rect width="200" height="100" fill="green"/>\n'
        b'</svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("viewbox.svg", svg, "image/svg+xml"))],
        data={"format": "png"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-scaled-down"] == "false"
    out_img = Image.open(io.BytesIO(response.content))
    assert out_img.size == (1024, 512)


def test_http_image_convert_svg_1500x800_tanpa_width() -> None:
    client = _test_client()
    if client is None:
        return
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="800">\n'
        b'  <rect width="1500" height="800" fill="blue"/>\n'
        b'</svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("large.svg", svg, "image/svg+xml"))],
        data={"format": "png"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-scaled-down"] == "false"
    out_img = Image.open(io.BytesIO(response.content))
    assert out_img.size == (1500, 800)


def test_http_image_convert_svg_24x24_viewbox_saja() -> None:
    client = _test_client()
    if client is None:
        return
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">\n'
        b'  <circle cx="12" cy="12" r="10" fill="red"/>\n'
        b'</svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("icon.svg", svg, "image/svg+xml"))],
        data={"format": "png"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-scaled-down"] == "false"
    out_img = Image.open(io.BytesIO(response.content))
    assert out_img.size == (1024, 1024)


def test_http_image_convert_svg_600x300_tanpa_width_diperbesar() -> None:
    client = _test_client()
    if client is None:
        return
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300">\n'
        b'  <rect width="600" height="300" fill="green"/>\n'
        b'</svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("normal.svg", svg, "image/svg+xml"))],
        data={"format": "png"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-scaled-down"] == "false"
    out_img = Image.open(io.BytesIO(response.content))
    assert out_img.size == (1024, 512)


def test_http_image_convert_svg_600x300_dengan_width_400_proporsional() -> None:
    client = _test_client()
    if client is None:
        return
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300">\n'
        b'  <rect width="600" height="300" fill="green"/>\n'
        b'</svg>'
    )
    response = client.post(
        "/api/image/convert",
        files=[("files", ("normal.svg", svg, "image/svg+xml"))],
        data={"format": "png", "width": "400"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-scaled-down"] == "false"
    out_img = Image.open(io.BytesIO(response.content))
    assert out_img.size == (400, 200)


def test_http_image_convert_regresi_format_lama_tetap_jalan() -> None:
    client = _test_client()
    if client is None:
        return

    png_data = make_image("PNG", size=(40, 30), color="teal")
    resp_png_jpg = client.post(
        "/api/image/convert",
        files=[("files", ("a.png", png_data, "image/png"))],
        data={"format": "jpeg"},
    )
    assert resp_png_jpg.status_code == 200, resp_png_jpg.text
    assert Image.open(io.BytesIO(resp_png_jpg.content)).size == (40, 30)

    resp_png_jpg2 = client.post(
        "/api/image/convert",
        files=[("files", ("a2.png", png_data, "image/png"))],
        data={"format": "jpg"},
    )
    assert resp_png_jpg2.status_code == 200, resp_png_jpg2.text
    assert Image.open(io.BytesIO(resp_png_jpg2.content)).size == (40, 30)

    resp_png_webp = client.post(
        "/api/image/convert",
        files=[("files", ("b.png", png_data, "image/png"))],
        data={"format": "webp"},
    )
    assert resp_png_webp.status_code == 200, resp_png_webp.text
    assert Image.open(io.BytesIO(resp_png_webp.content)).size == (40, 30)

    jpeg_data = make_image("JPEG", size=(25, 45), color="orange")
    resp_jpeg_png = client.post(
        "/api/image/convert",
        files=[("files", ("c.jpg", jpeg_data, "image/jpeg"))],
        data={"format": "png"},
    )
    assert resp_jpeg_png.status_code == 200, resp_jpeg_png.text
    assert Image.open(io.BytesIO(resp_jpeg_png.content)).size == (25, 45)

    webp_data = make_image("WEBP", size=(33, 22), color="purple")
    resp_webp_png = client.post(
        "/api/image/convert",
        files=[("files", ("d.webp", webp_data, "image/webp"))],
        data={"format": "png"},
    )
    assert resp_webp_png.status_code == 200, resp_webp_png.text
    assert Image.open(io.BytesIO(resp_webp_png.content)).size == (33, 22)


def test_http_word_count_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/word-count/limits")
    assert response.status_code == 200
    body = response.json()
    assert body["processed_on"] == "server"
    assert body["max_chars"] == WC_MAX_CHARS
    assert body["max_bytes"] == WC_MAX_BYTES
    assert response.headers["cache-control"] == "no-store"


def test_http_word_count_teks_normal_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", data={"text": "Halo dunia. Ini uji coba!"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")

    # Respons sukses tidak memuat Cache-Control yang membolehkan cache
    cache = response.headers.get("cache-control", "")
    assert "no-store" in cache
    assert "no-cache" in cache
    assert response.headers.get("pragma") == "no-cache"

    # Header ringkas
    assert response.headers.get("x-char-count") == "25"
    assert response.headers.get("x-word-count") == "5"
    assert "x-processing-ms" in response.headers

    body = response.json()
    assert body["chars"] == 25
    assert body["chars_no_spaces"] == 21
    assert body["words"] == 5
    assert body["unique_words"] == 5
    assert body["sentences"] == 2
    assert body["paragraphs"] == 1
    assert body["lines"] == 1
    assert body["reading_minutes"] == 1
    assert body["speaking_minutes"] == 1
    assert body["longest_word"] == "dunia"


def test_http_word_count_paragraf_dan_baris() -> None:
    client = _test_client()
    if client is None:
        return
    text = (
        "Baris 1 paragraf 1\n"
        "Baris 2 paragraf 1\n\n"
        "Baris 3 paragraf 2\n\n\n"
        "Baris 4 paragraf 3"
    )
    response = client.post("/api/word-count", data={"text": text})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["paragraphs"] == 3
    assert body["lines"] == 4


def test_http_word_count_case_insensitive_dan_top_words() -> None:
    client = _test_client()
    if client is None:
        return
    text = "Mawar mawar MAWAR melati melati melati melati anggrek."
    response = client.post("/api/word-count", data={"text": text})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["unique_words"] == 3
    words = [item["word"] for item in body["top_words"]]
    assert words[0] == "melati"
    assert body["top_words"][0]["count"] == 4
    assert words[1] == "mawar"
    assert body["top_words"][1]["count"] == 3


def test_http_word_count_teks_kosong_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", data={"text": ""})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == WC_NO_TEXT


def test_http_word_count_teks_hanya_spasi_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", data={"text": "   \n\t  "})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == WC_NO_TEXT


def test_http_word_count_teks_terlalu_panjang_ditolak_413() -> None:
    client = _test_client()
    if client is None:
        return
    long_text = "x" * (WC_MAX_CHARS + 10)
    response = client.post("/api/word-count", data={"text": long_text})
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == WC_TOO_LONG


def test_http_word_count_bukan_multipart_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", json={"text": "Halo dunia"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == WC_INVALID_REQUEST


def test_http_word_count_field_text_hilang_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", data={})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] in (WC_INVALID_REQUEST, WC_NO_TEXT)


def test_http_word_count_cache_headers_tidak_membolehkan_cache() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/word-count", data={"text": "Uji cache header"})
    assert response.status_code == 200
    cache_control = response.headers.get("Cache-Control", "")
    assert "public" not in cache_control
    assert "max-age" not in cache_control
    assert "no-store" in cache_control
    assert "no-cache" in cache_control
    assert response.headers.get("Pragma") == "no-cache"


def test_http_case_convert_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/case/limits")
    assert response.status_code == 200
    body = response.json()
    assert body["processed_on"] == "server"
    assert body["max_chars"] == CC_MAX_CHARS
    assert body["max_bytes"] == CC_MAX_BYTES
    assert body["modes"] == CC_MODE_ORDER
    assert body["mode_labels"] == CC_MODES
    assert response.headers["cache-control"] == "no-store"


def test_http_case_convert_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/case", data={"text": "halo dunia", "mode": "upper"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")

    # Header no-cache
    cache = response.headers.get("cache-control", "")
    assert "no-store" in cache
    assert "no-cache" in cache
    assert response.headers.get("pragma") == "no-cache"

    # Header metadata
    assert response.headers.get("x-case-mode") == "upper"
    assert response.headers.get("x-char-count") == "10"
    assert "x-processing-ms" in response.headers

    body = response.json()
    assert body["mode"] == "upper"
    assert body["text"] == "HALO DUNIA"
    assert body["chars_in"] == 10
    assert body["chars_out"] == 10
    assert body["words"] == 2
    assert body["changed"] is True


def test_http_case_convert_teks_kosong_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/case", data={"text": "", "mode": "upper"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == CC_NO_TEXT


def test_http_case_convert_teks_hanya_spasi_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/case", data={"text": "   \n\t  ", "mode": "upper"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == CC_NO_TEXT


def test_http_case_convert_mode_tidak_valid_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    # Mode tidak dikenal
    response = client.post("/api/case", data={"text": "halo", "mode": "tidak_ada"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == CC_UNSUPPORTED_MODE

    # Mode tidak disertakan
    response2 = client.post("/api/case", data={"text": "halo"})
    assert response2.status_code == 400, response2.text
    assert response2.json()["error"]["code"] == CC_INVALID_REQUEST


def test_http_case_convert_bukan_multipart_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/case", json={"text": "halo", "mode": "upper"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == CC_INVALID_REQUEST


def test_http_case_convert_teks_terlalu_panjang_ditolak_413() -> None:
    client = _test_client()
    if client is None:
        return
    long_text = "x" * (CC_MAX_CHARS + 10)
    response = client.post("/api/case", data={"text": long_text, "mode": "upper"})
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == CC_TOO_LONG


def test_http_base64_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/base64/limits")
    assert response.status_code == 200
    body = response.json()
    assert body["processed_on"] == "server"
    assert body["max_chars"] == B64_MAX_CHARS
    assert body["max_bytes"] == B64_MAX_BYTES
    assert isinstance(body["modes"], list)
    assert isinstance(body["variants"], list)
    assert isinstance(body["wrap_options"], list)
    assert isinstance(body["decode_accepts"], list)
    assert response.headers["cache-control"] == "no-store"


def test_http_base64_encode_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/base64", data={"text": "Halo, dunia!", "mode": "encode"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")

    cache = response.headers.get("cache-control", "")
    assert "no-store" in cache
    assert "no-cache" in cache
    assert response.headers.get("pragma") == "no-cache"

    assert response.headers.get("x-base64-mode") == "encode"
    assert "x-output-length" in response.headers
    assert "x-processing-ms" in response.headers

    body = response.json()
    assert body["mode"] == "encode"
    assert body["text"] == "SGFsbywgZHVuaWEh"
    assert body["chars_in"] == 12
    assert body["chars_out"] == 16
    assert body["changed"] is True


def test_http_base64_encode_urlsafe_dan_wrap() -> None:
    client = _test_client()
    if client is None:
        return
    text = "Kalimat panjang untuk menguji opsi urlsafe dan pembungkusan baris 76 karakter pada endpoint HTTP."
    response = client.post(
        "/api/base64",
        data={"text": text, "mode": "encode", "variant": "urlsafe", "wrap": "76"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["variant"] == "urlsafe"
    assert body["wrap"] == 76
    lines = body["text"].split("\n")
    assert len(lines) > 1
    for line in lines:
        assert len(line) <= 76


def test_http_base64_decode_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    b64_input = "  data:text/plain;base64,\n SGFsbywgZHVuaWEh \n "
    response = client.post("/api/base64", data={"text": b64_input, "mode": "decode"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "decode"
    assert body["text"] == "Halo, dunia!"
    assert response.headers.get("x-base64-mode") == "decode"


def test_http_base64_teks_kosong_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/base64", data={"text": "", "mode": "encode"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == B64_NO_TEXT


def test_http_base64_teks_hanya_spasi_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/base64", data={"text": "   \n\t  ", "mode": "encode"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == B64_NO_TEXT


def test_http_base64_mode_tidak_valid_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/base64", data={"text": "halo", "mode": "tidak_ada"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == B64_UNSUPPORTED_MODE

    response2 = client.post("/api/base64", data={"text": "halo"})
    assert response2.status_code == 400, response2.text
    assert response2.json()["error"]["code"] == B64_INVALID_REQUEST


def test_http_base64_bukan_multipart_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/base64", json={"text": "halo", "mode": "encode"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == B64_INVALID_REQUEST


def test_http_base64_teks_terlalu_panjang_ditolak_413() -> None:
    client = _test_client()
    if client is None:
        return
    long_text = "x" * (B64_MAX_CHARS + 10)
    response = client.post("/api/base64", data={"text": long_text, "mode": "encode"})
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == B64_TOO_LONG


def test_http_base64_invalid_base64_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/base64", data={"text": "Bukan base64 valid! @#$", "mode": "decode"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == B64_INVALID_BASE64


def test_http_base64_data_biner_ditolak_400() -> None:
    import base64
    client = _test_client()
    if client is None:
        return
    binary_b64 = base64.b64encode(bytes(range(256))).decode("ascii")
    response = client.post("/api/base64", data={"text": binary_b64, "mode": "decode"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == B64_NOT_TEXT


# --- Uji OCR (Ambil teks dari gambar & PDF) ---------------------------------
def test_ocr_logic_detect_file_type() -> None:
    from app.ocr import detect_file_type
    assert detect_file_type(b"%PDF-1.4") == "pdf"
    assert detect_file_type(b"\x89PNG\r\n\x1a\n...") == "image"
    assert detect_file_type(b"\xff\xd8\xff...") == "image"
    assert detect_file_type(b"RIFF\x00\x00\x00\x00WEBP...") == "image"
    assert detect_file_type(b"II*\x00...") == "image"
    assert detect_file_type(b"MM\x00*...") == "image"
    assert detect_file_type(b"bukan gambar atau pdf") is None


def test_ocr_logic_empty_data() -> None:
    try:
        run_ocr(b"")
    except OcrError as exc:
        assert exc.code == OCR_EMPTY_FILE
        assert exc.status_code == 400
    else:
        assert False, "Harus melempar OcrError"


def test_ocr_logic_unsupported_data() -> None:
    try:
        run_ocr(b"Hello World plain text")
    except OcrError as exc:
        assert exc.code == OCR_UNSUPPORTED_FILE
        assert exc.status_code == 400
    else:
        assert False, "Harus melempar OcrError"


def test_ocr_logic_invalid_lang() -> None:
    try:
        run_ocr(make_ocr_png("TES"), lang="invalid_lang")
    except OcrError as exc:
        assert exc.code == OCR_INVALID_LANG
        assert exc.status_code == 400
    else:
        assert False, "Harus melempar OcrError"


def test_http_ocr_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/ocr/limits")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["max_bytes"] == OCR_MAX_BYTES
    assert body["max_pages"] == OCR_MAX_PAGES
    assert body["time_limit_seconds"] == OCR_TIME_LIMIT_SECONDS
    assert "languages" in body
    assert any(lang["value"] == "ind" for lang in body["languages"])
    assert any(lang["value"] == "eng" for lang in body["languages"])
    assert any(lang["value"] == "ind+eng" for lang in body["languages"])
    assert response.headers["cache-control"] == "no-store"


def test_http_ocr_gambar_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    png_bytes = make_ocr_png("KUCING OREN")
    response = client.post(
        "/api/ocr",
        files=[("file", ("kucing.png", png_bytes, "image/png"))],
        data={"lang": "ind+eng"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    text_lower = body["text"].lower()
    assert "kucing" in text_lower or "oren" in text_lower
    assert body["pages"] == 1
    assert body["source"] == "image"
    assert body["empty"] is False
    assert body["chars"] > 0
    assert response.headers["x-page-count"] == "1"
    assert "x-char-count" in response.headers
    assert "x-processing-ms" in response.headers
    assert response.headers["x-ocr-lang"] == "ind+eng"
    assert "no-store" in response.headers["cache-control"]


def test_http_ocr_pdf_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    pdf_bytes = make_ocr_pdf("SURAT SATU", "BERKAS DUA")
    response = client.post(
        "/api/ocr",
        files=[("file", ("dokumen.pdf", pdf_bytes, "application/pdf"))],
        data={"lang": "ind+eng"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    text_lower = body["text"].lower()
    assert "surat" in text_lower or "satu" in text_lower
    assert "berkas" in text_lower or "dua" in text_lower
    assert body["pages"] == 2
    assert body["source"] == "pdf"
    assert body["empty"] is False
    assert "=== Halaman 1 ===" in body["text"]
    assert "=== Halaman 2 ===" in body["text"]
    assert response.headers["x-page-count"] == "2"


def test_http_ocr_tanpa_field_file_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/ocr", data={"lang": "ind"})
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "INVALID_REQUEST"


def test_http_ocr_berkas_kosong_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/ocr",
        files=[("file", ("kosong.png", b"", "image/png"))],
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == OCR_EMPTY_FILE


def test_http_ocr_berkas_teks_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/ocr",
        files=[("file", ("catatan.txt", b"Halo ini berkas teks biasa", "text/plain"))],
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == OCR_UNSUPPORTED_FILE


def test_http_ocr_berkas_terlalu_besar_ditolak_413() -> None:
    client = _test_client()
    if client is None:
        return
    large_payload = b"\x89PNG\r\n\x1a\n" + b"0" * (OCR_MAX_BYTES + 100)
    response = client.post(
        "/api/ocr",
        files=[("file", ("besar.png", large_payload, "image/png"))],
    )
    assert response.status_code == 413, response.text
    body = response.json()
    assert body["error"]["code"] == OCR_TOO_LARGE


def test_http_ocr_pdf_terlalu_banyak_halaman_ditolak_413() -> None:
    client = _test_client()
    if client is None:
        return
    pdf_bytes = make_many_page_pdf(OCR_MAX_PAGES + 1)
    response = client.post(
        "/api/ocr",
        files=[("file", ("dokumen_tebal.pdf", pdf_bytes, "application/pdf"))],
    )
    assert response.status_code == 413, response.text
    body = response.json()
    assert body["error"]["code"] == OCR_TOO_MANY_PAGES


def test_http_ocr_lang_tidak_dikenal_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    png_bytes = make_ocr_png("TES")
    response = client.post(
        "/api/ocr",
        files=[("file", ("tes.png", png_bytes, "image/png"))],
        data={"lang": "xx"},
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == OCR_INVALID_LANG


def test_http_ocr_pdf_rusak_ditolak_422() -> None:
    client = _test_client()
    if client is None:
        return
    corrupted_pdf = b"%PDF-1.7\n" + b"\x00" * 2000
    response = client.post(
        "/api/ocr",
        files=[("file", ("rusak.pdf", corrupted_pdf, "application/pdf"))],
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"]["code"] == OCR_DAMAGED_FILE
    assert body["error"]["code"] != "INTERNAL_ERROR"
    assert "tidak bisa dibaca" in body["error"]["message"].lower()




# --- Uji Hapus Baris Duplikat (Remove Duplicates) ----------------------------
def test_remove_duplicates_logika_dasar() -> None:
    text = "apel\njeruk\napel\nmangga\njeruk"
    result = dedupe_text(text)
    assert result.text == "apel\njeruk\nmangga"
    assert result.lines_in == 5
    assert result.lines_out == 3
    assert result.duplicates_removed == 2
    assert result.empty_removed == 0
    assert result.chars_in == len(text)
    assert result.chars_out == len(result.text)
    assert result.to_dict()["lines_out"] == 3


def test_remove_duplicates_logika_keep_first_vs_last() -> None:
    text = "A\nB\nA\nC\nB"
    res_first = dedupe_text(text, keep="first")
    assert res_first.text == "A\nB\nC"
    assert res_first.lines_out == 3
    assert res_first.duplicates_removed == 2

    res_last = dedupe_text(text, keep="last")
    assert res_last.text == "A\nC\nB"
    assert res_last.lines_out == 3
    assert res_last.duplicates_removed == 2

    # Menjaga isi teks asli kemunculan terakhir
    text_case = "apple\nbanana\nAPPLE\ncherry"
    res_last_case = dedupe_text(text_case, keep="last", case_sensitive=False)
    assert res_last_case.text == "banana\nAPPLE\ncherry"
    assert res_last_case.lines_out == 3
    assert res_last_case.duplicates_removed == 1


def test_remove_duplicates_logika_trim() -> None:
    text = "  apel  \napel\njeruk\n  jeruk"
    # trim=True -> spasi di ujung dibersihkan untuk pembanding, teks asli tidak diubah
    res_trimmed = dedupe_text(text, trim=True)
    assert res_trimmed.text == "  apel  \njeruk"
    assert res_trimmed.lines_out == 2
    assert res_trimmed.duplicates_removed == 2

    # trim=False -> spasi membuat baris berbeda
    res_untrimmed = dedupe_text(text, trim=False)
    assert res_untrimmed.text == "  apel  \napel\njeruk\n  jeruk"
    assert res_untrimmed.lines_out == 4
    assert res_untrimmed.duplicates_removed == 0


def test_remove_duplicates_logika_case_sensitive() -> None:
    text = "Halo\nhalo\nHALO"
    res_sensitive = dedupe_text(text, case_sensitive=True)
    assert res_sensitive.text == "Halo\nhalo\nHALO"
    assert res_sensitive.lines_out == 3
    assert res_sensitive.duplicates_removed == 0

    res_insensitive = dedupe_text(text, case_sensitive=False)
    assert res_insensitive.text == "Halo"
    assert res_insensitive.lines_out == 1
    assert res_insensitive.duplicates_removed == 2


def test_remove_duplicates_logika_drop_empty() -> None:
    text = "apel\n\njeruk\n   \nmangga"
    # drop_empty=True -> baris kosong setelah trim dibuang ke empty_removed
    res_drop = dedupe_text(text, drop_empty=True)
    assert res_drop.text == "apel\njeruk\nmangga"
    assert res_drop.lines_out == 3
    assert res_drop.empty_removed == 2
    assert res_drop.duplicates_removed == 0

    # drop_empty=False -> baris kosong dipertahankan, duplikat baris kosong dibuang
    text2 = "apel\n\njeruk\n\nmangga"
    res_keep_empty = dedupe_text(text2, drop_empty=False)
    assert res_keep_empty.text == "apel\n\njeruk\nmangga"
    assert res_keep_empty.lines_out == 4
    assert res_keep_empty.empty_removed == 0
    assert res_keep_empty.duplicates_removed == 1


def test_remove_duplicates_logika_galat_no_text() -> None:
    try:
        dedupe_text("")
        assert False, "Harusnya melempar RemoveDuplicatesError"
    except RemoveDuplicatesError as exc:
        assert exc.code == RD_NO_TEXT
        assert exc.status_code == 400
        assert "Masukkan dulu daftar baris" in exc.message

    try:
        dedupe_text(None)
        assert False, "Harusnya melempar RemoveDuplicatesError"
    except RemoveDuplicatesError as exc:
        assert exc.code == RD_NO_TEXT
        assert exc.status_code == 400

    try:
        dedupe_text("   \n\t  \n  ")
        assert False, "Harusnya melempar RemoveDuplicatesError"
    except RemoveDuplicatesError as exc:
        assert exc.code == RD_NO_TEXT
        assert exc.status_code == 400


def test_remove_duplicates_logika_galat_too_long() -> None:
    long_text = "x" * (RD_MAX_CHARS + 1)
    try:
        dedupe_text(long_text)
        assert False, "Harusnya melempar RemoveDuplicatesError"
    except RemoveDuplicatesError as exc:
        assert exc.code == RD_TOO_LONG
        assert exc.status_code == 413

    # Uji batas byte UTF-8 via check_size
    multi_byte = "€" * (RD_MAX_BYTES // 3 + 10)
    try:
        check_remove_duplicates_size(multi_byte)
        assert False, "Harusnya melempar RemoveDuplicatesError"
    except RemoveDuplicatesError as exc:
        assert exc.code == RD_TOO_LONG
        assert exc.status_code == 413


def test_remove_duplicates_logika_galat_unsupported_keep() -> None:
    try:
        dedupe_text("a\nb", keep="tengah")
        assert False, "Harusnya melempar RemoveDuplicatesError"
    except RemoveDuplicatesError as exc:
        assert exc.code == RD_UNSUPPORTED_KEEP
        assert exc.status_code == 400


def test_remove_duplicates_logika_galat_invalid_boolean() -> None:
    # Nilai boolean yang sah
    assert parse_remove_duplicates_bool("true") is True
    assert parse_remove_duplicates_bool("ya") is True
    assert parse_remove_duplicates_bool("1") is True
    assert parse_remove_duplicates_bool("false") is False
    assert parse_remove_duplicates_bool("tidak") is False
    assert parse_remove_duplicates_bool("0") is False

    # Nilai boolean tidak dikenal
    for invalid in ["bukan", "maybe", "2", "-1"]:
        try:
            parse_remove_duplicates_bool(invalid, "trim")
            assert False, f"Harusnya melempar RemoveDuplicatesError untuk {invalid}"
        except RemoveDuplicatesError as exc:
            assert exc.code == RD_INVALID_BOOLEAN
            assert exc.status_code == 400


def test_http_remove_duplicates_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/remove-duplicates/limits")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["max_chars"] == RD_MAX_CHARS
    assert body["max_bytes"] == RD_MAX_BYTES
    assert body["max_mb"] == 1
    assert isinstance(body["keep_options"], list)
    assert len(body["keep_options"]) == 2
    assert body["processed_on"] == "server"
    assert "note" in body
    assert body["defaults"]["keep"] == "first"
    assert body["defaults"]["case_sensitive"] is False
    assert body["defaults"]["trim"] is True
    assert body["defaults"]["drop_empty"] is True
    assert "no-store" in response.headers.get("Cache-Control", "")


def test_http_remove_duplicates_sukses() -> None:
    client = _test_client()
    if client is None:
        return
    raw = "apel\njeruk\napel\nmangga\njeruk"
    response = client.post("/api/remove-duplicates", data={"text": raw})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == "apel\njeruk\nmangga"
    assert body["lines_in"] == 5
    assert body["lines_out"] == 3
    assert body["duplicates_removed"] == 2
    assert body["empty_removed"] == 0
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert response.headers.get("Pragma") == "no-cache"
    assert "X-Processing-Ms" in response.headers


def test_http_remove_duplicates_opsi_kustom() -> None:
    client = _test_client()
    if client is None:
        return
    raw = "  apel  \nAPEL\njeruk\n\n  jeruk  "
    response = client.post(
        "/api/remove-duplicates",
        data={
            "text": raw,
            "keep": "last",
            "case_sensitive": "false",
            "trim": "true",
            "drop_empty": "true",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == "APEL\n  jeruk  "
    assert body["lines_in"] == 5
    assert body["lines_out"] == 2
    assert body["empty_removed"] == 1
    assert body["duplicates_removed"] == 2


def test_http_remove_duplicates_teks_kosong_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/remove-duplicates", data={"text": ""})
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == RD_NO_TEXT
    assert "no-store" in response.headers.get("Cache-Control", "")


def test_http_remove_duplicates_teks_terlalu_panjang_ditolak_413() -> None:
    client = _test_client()
    if client is None:
        return
    long_text = "x" * (RD_MAX_CHARS + 10)
    response = client.post("/api/remove-duplicates", data={"text": long_text})
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == RD_TOO_LONG


def test_http_remove_duplicates_keep_tidak_valid_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/remove-duplicates", data={"text": "a\nb", "keep": "tengah"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == RD_UNSUPPORTED_KEEP


def test_http_remove_duplicates_boolean_tidak_valid_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/remove-duplicates", data={"text": "a\nb", "trim": "ngawur"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == RD_INVALID_BOOLEAN


def test_http_remove_duplicates_bukan_multipart_ditolak_400() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/remove-duplicates", json={"text": "a\nb"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == RD_INVALID_REQUEST


# --- Uji List Shuffler (Acak Urutan Daftar) ----------------------------------
def test_list_shuffler_logika_dasar() -> None:
    text = "satu\ndua\ntiga\nempat\nlima"
    result = shuffle_lines(text)
    assert result.lines_in == 5
    assert result.lines_out == 5
    assert set(result.text.splitlines()) == {"satu", "dua", "tiga", "empat", "lima"}
    assert result.take == 0
    assert isinstance(result.seed, int)
    assert result.seed_given is False
    assert result.trim is True
    assert result.drop_empty is True
    assert result.empty_removed == 0
    assert result.chars_in == len(text)
    assert result.chars_out == len(result.text)
    d = result.to_dict()
    assert d["lines_in"] == 5
    assert d["lines_out"] == 5
    assert "seed" in d


def test_list_shuffler_logika_seed() -> None:
    text = "alpha\nbravo\ncharlie\ndelta\necho"
    res1 = shuffle_lines(text, seed=42)
    res2 = shuffle_lines(text, seed=42)
    assert res1.seed == 42
    assert res1.seed_given is True
    assert res1.text == res2.text

    res3 = shuffle_lines(text, seed=999)
    assert res3.seed == 999
    assert res3.seed_given is True


def test_list_shuffler_logika_take() -> None:
    lines = [f"baris_{i}" for i in range(10)]
    text = "\n".join(lines)

    res_take3 = shuffle_lines(text, take=3, seed=123)
    assert res_take3.lines_in == 10
    assert res_take3.lines_out == 3
    assert res_take3.take == 3
    out3 = res_take3.text.splitlines()
    assert len(out3) == 3
    assert set(out3).issubset(set(lines))

    # take lebih besar dari jumlah baris -> ambil semua baris
    res_take20 = shuffle_lines(text, take=20, seed=123)
    assert res_take20.lines_in == 10
    assert res_take20.lines_out == 10
    assert set(res_take20.text.splitlines()) == set(lines)

    # take = 0 -> ambil semua baris
    res_take0 = shuffle_lines(text, take=0, seed=123)
    assert res_take0.lines_out == 10


def test_list_shuffler_logika_trim_dan_drop_empty() -> None:
    text = "  satu  \n\n  dua  \n   \ntiga"
    # trim=True, drop_empty=True (bawaan)
    res_default = shuffle_lines(text, trim=True, drop_empty=True, seed=1)
    assert res_default.lines_in == 5
    assert res_default.lines_out == 3
    assert res_default.empty_removed == 2
    assert set(res_default.text.splitlines()) == {"satu", "dua", "tiga"}

    # trim=False, drop_empty=False
    res_raw = shuffle_lines(text, trim=False, drop_empty=False, seed=1)
    assert res_raw.lines_in == 5
    assert res_raw.lines_out == 5
    assert res_raw.empty_removed == 0
    baris_raw = res_raw.text.split("\n")
    assert len(baris_raw) == 5
    assert "" in baris_raw
    assert "  satu  " in baris_raw
    assert "   " in baris_raw

    # trim=False, drop_empty=True
    res_no_trim_drop = shuffle_lines(text, trim=False, drop_empty=True, seed=1)
    assert res_no_trim_drop.lines_in == 5
    assert res_no_trim_drop.lines_out == 3
    assert res_no_trim_drop.empty_removed == 2
    assert "  satu  " in res_no_trim_drop.text.splitlines()


def test_list_shuffler_logika_galat() -> None:
    try:
        shuffle_lines("")
        assert False, "Harusnya melempar ListShufflerError"
    except ListShufflerError as exc:
        assert exc.code == LS_NO_TEXT
        assert exc.status_code == 400

    try:
        shuffle_lines(None)
        assert False, "Harusnya melempar ListShufflerError"
    except ListShufflerError as exc:
        assert exc.code == LS_NO_TEXT
        assert exc.status_code == 400

    try:
        shuffle_lines("   \n\t  \n  ")
        assert False, "Harusnya melempar ListShufflerError"
    except ListShufflerError as exc:
        assert exc.code == LS_NO_TEXT
        assert exc.status_code == 400

    long_text = "x" * (LS_MAX_CHARS + 1)
    try:
        shuffle_lines(long_text)
        assert False, "Harusnya melempar ListShufflerError"
    except ListShufflerError as exc:
        assert exc.code == LS_TOO_LONG
        assert exc.status_code == 413

    multi_byte = "€" * (LS_MAX_BYTES // 3 + 10)
    try:
        check_list_shuffler_size(multi_byte)
        assert False, "Harusnya melempar ListShufflerError"
    except ListShufflerError as exc:
        assert exc.code == LS_TOO_LONG
        assert exc.status_code == 413

    # seed tidak valid
    for inv_seed in ["abc", "-1", "4294967296", True]:
        try:
            parse_list_shuffler_seed(inv_seed)
            assert False, f"Harusnya melempar ListShufflerError untuk seed {inv_seed}"
        except ListShufflerError as exc:
            assert exc.code == LS_INVALID_SEED
            assert exc.status_code == 400

    # take tidak valid
    for inv_take in ["dua", "-1", "200001", True]:
        try:
            parse_list_shuffler_take(inv_take)
            assert False, f"Harusnya melempar ListShufflerError untuk take {inv_take}"
        except ListShufflerError as exc:
            assert exc.code == LS_INVALID_TAKE
            assert exc.status_code == 400

    # boolean tidak valid
    try:
        parse_list_shuffler_bool("mungkin", "trim")
        assert False, "Harusnya melempar ListShufflerError untuk boolean tidak valid"
    except ListShufflerError as exc:
        assert exc.code == LS_INVALID_BOOLEAN
        assert exc.status_code == 400


def test_http_list_shuffler_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/list-shuffler/limits")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["max_chars"] == LS_MAX_CHARS
    assert body["max_bytes"] == LS_MAX_BYTES
    assert body["max_mb"] == 1
    assert body["max_take"] == LS_MAX_TAKE
    assert body["min_seed"] == LS_MIN_SEED
    assert body["max_seed"] == LS_MAX_SEED
    assert isinstance(body["options"], list)
    assert body["defaults"]["take"] == 0
    assert body["defaults"]["seed"] is None
    assert body["defaults"]["trim"] is True
    assert body["defaults"]["drop_empty"] is True
    assert body["processed_on"] == "server"
    assert "note" in body
    assert "no-store" in response.headers.get("Cache-Control", "")


def test_http_list_shuffler_acak_5_baris() -> None:
    client = _test_client()
    if client is None:
        return
    raw = "Andi\nBudi\nCitra\nDewi\nEko"
    response = client.post("/api/list-shuffler", data={"text": raw})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lines_in"] == 5
    assert body["lines_out"] == 5
    assert set(body["text"].splitlines()) == {"Andi", "Budi", "Citra", "Dewi", "Eko"}
    assert isinstance(body["seed"], int)
    assert body["seed_given"] is False
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert response.headers.get("Pragma") == "no-cache"
    assert "X-Processing-Ms" in response.headers


def test_http_list_shuffler_seed_sama_dan_berbeda() -> None:
    client = _test_client()
    if client is None:
        return
    raw = "satu\ndua\ntiga\nempat\nlima\nenam\ntujuh\ndelapan"
    resp1 = client.post("/api/list-shuffler", data={"text": raw, "seed": "54321"})
    assert resp1.status_code == 200, resp1.text
    body1 = resp1.json()

    resp2 = client.post("/api/list-shuffler", data={"text": raw, "seed": "54321"})
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()

    # Kunci sama menghasilkan urutan persis sama
    assert body1["seed"] == 54321
    assert body1["seed_given"] is True
    assert body1["text"] == body2["text"]

    resp3 = client.post("/api/list-shuffler", data={"text": raw, "seed": "98765"})
    assert resp3.status_code == 200, resp3.text
    body3 = resp3.json()
    assert body3["seed"] == 98765
    assert body3["seed_given"] is True


def test_http_list_shuffler_take() -> None:
    client = _test_client()
    if client is None:
        return
    lines = [f"nama_{i}" for i in range(10)]
    raw = "\n".join(lines)

    # take=3 dari 10 baris
    resp = client.post("/api/list-shuffler", data={"text": raw, "take": "3", "seed": "77"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["lines_in"] == 10
    assert body["lines_out"] == 3
    out_lines = body["text"].splitlines()
    assert len(out_lines) == 3
    assert set(out_lines).issubset(set(lines))

    # take lebih besar dari jumlah baris -> ambil semua baris tanpa galat
    resp_large = client.post("/api/list-shuffler", data={"text": raw, "take": "50", "seed": "77"})
    assert resp_large.status_code == 200, resp_large.text
    body_large = resp_large.json()
    assert body_large["lines_in"] == 10
    assert body_large["lines_out"] == 10
    assert set(body_large["text"].splitlines()) == set(lines)


def test_http_list_shuffler_trim() -> None:
    client = _test_client()
    if client is None:
        return
    raw = "  Andi  \n  Budi  \n  Citra  "
    resp_trim = client.post("/api/list-shuffler", data={"text": raw, "trim": "true", "seed": "1"})
    assert resp_trim.status_code == 200, resp_trim.text
    body_trim = resp_trim.json()
    for line in body_trim["text"].splitlines():
        assert line == line.strip()

    resp_notrim = client.post("/api/list-shuffler", data={"text": raw, "trim": "false", "seed": "1"})
    assert resp_notrim.status_code == 200, resp_notrim.text
    body_notrim = resp_notrim.json()
    for line in body_notrim["text"].splitlines():
        assert line.startswith("  ") and line.endswith("  ")


def test_http_list_shuffler_drop_empty() -> None:
    client = _test_client()
    if client is None:
        return
    raw = "Andi\n\nBudi\n   \nCitra"
    resp_drop = client.post("/api/list-shuffler", data={"text": raw, "drop_empty": "true", "seed": "1"})
    assert resp_drop.status_code == 200, resp_drop.text
    body_drop = resp_drop.json()
    assert body_drop["lines_in"] == 5
    assert body_drop["lines_out"] == 3
    assert body_drop["empty_removed"] == 2

    resp_keep = client.post("/api/list-shuffler", data={"text": raw, "drop_empty": "false", "seed": "1"})
    assert resp_keep.status_code == 200, resp_keep.text
    body_keep = resp_keep.json()
    assert body_keep["lines_in"] == 5
    assert body_keep["lines_out"] == 5
    assert body_keep["empty_removed"] == 0


def test_http_list_shuffler_galat() -> None:
    client = _test_client()
    if client is None:
        return

    # Teks kosong
    resp_empty = client.post("/api/list-shuffler", data={"text": ""})
    assert resp_empty.status_code == 400, resp_empty.text
    body_empty = resp_empty.json()
    assert body_empty["error"]["code"] == LS_NO_TEXT
    assert "error" in body_empty and "message" in body_empty["error"]

    # Teks spasi saja
    resp_spaces = client.post("/api/list-shuffler", data={"text": "   \n\t  "})
    assert resp_spaces.status_code == 400, resp_spaces.text
    assert resp_spaces.json()["error"]["code"] == LS_NO_TEXT

    # Field text tidak dikirim sama sekali
    resp_notext = client.post("/api/list-shuffler", data={})
    assert resp_notext.status_code == 400, resp_notext.text
    assert resp_notext.json()["error"]["code"] in (LS_NO_TEXT, LS_INVALID_REQUEST)

    # Teks melebihi batas 200.000 karakter
    long_text = "x" * (LS_MAX_CHARS + 1)
    resp_long = client.post("/api/list-shuffler", data={"text": long_text})
    assert resp_long.status_code == 413, resp_long.text
    assert resp_long.json()["error"]["code"] == LS_TOO_LONG

    # seed bukan angka
    resp_seed_str = client.post("/api/list-shuffler", data={"text": "a\nb", "seed": "abc"})
    assert resp_seed_str.status_code == 400, resp_seed_str.text
    assert resp_seed_str.json()["error"]["code"] == LS_INVALID_SEED

    # seed negatif
    resp_seed_neg = client.post("/api/list-shuffler", data={"text": "a\nb", "seed": "-1"})
    assert resp_seed_neg.status_code == 400, resp_seed_neg.text
    assert resp_seed_neg.json()["error"]["code"] == LS_INVALID_SEED

    # take bukan angka
    resp_take_str = client.post("/api/list-shuffler", data={"text": "a\nb", "take": "dua"})
    assert resp_take_str.status_code == 400, resp_take_str.text
    assert resp_take_str.json()["error"]["code"] == LS_INVALID_TAKE

    # trim tidak valid
    resp_trim_inv = client.post("/api/list-shuffler", data={"text": "a\nb", "trim": "mungkin"})
    assert resp_trim_inv.status_code == 400, resp_trim_inv.text
    assert resp_trim_inv.json()["error"]["code"] == LS_INVALID_BOOLEAN

    # Bukan multipart/form-data
    resp_json = client.post("/api/list-shuffler", json={"text": "a\nb"})
    assert resp_json.status_code == 400, resp_json.text
    assert resp_json.json()["error"]["code"] == LS_INVALID_REQUEST


# --- Uji Text Formatter: Logika murni ---------------------------------------
def test_text_formatter_logika_spasi_dan_tab() -> None:
    # collapse_spaces
    res = format_text("Halo   dunia   lagi", collapse_spaces=True)
    assert res["text"] == "Halo dunia lagi"

    # collapse_spaces dimatikan
    res_no_collapse = format_text("Halo   dunia", collapse_spaces=False, trim_lines=False)
    assert res_no_collapse["text"] == "Halo   dunia"

    # trim_lines
    res_trim = format_text("   baris satu   \n   baris dua   ", trim_lines=True)
    assert res_trim["text"] == "baris satu\nbaris dua"

    # tabs_to_spaces dengan berbagai tab_width
    res_tab4 = format_text("kolom1\tkolom2", collapse_spaces=False, tab_width=4)
    assert res_tab4["text"] == "kolom1    kolom2"

    res_tab2 = format_text("kolom1\tkolom2", collapse_spaces=False, tab_width=2)
    assert res_tab2["text"] == "kolom1  kolom2"

    res_tab8 = format_text("kolom1\tkolom2", collapse_spaces=False, tab_width=8)
    assert res_tab8["text"] == "kolom1        kolom2"


def test_text_formatter_tanda_baca_dan_karakter_istimewa() -> None:
    # space_before_punctuation
    raw_punct = "Halo , dunia ! Apakah ini ; contoh ? Ya ( benar ) dan [ ini ] ."
    res_punct = format_text(raw_punct, space_before_punctuation=True)
    assert res_punct["text"] == "Halo, dunia! Apakah ini; contoh? Ya ( benar) dan [ ini]."

    # unify_characters: kutip melengkung, tanda pisah panjang, elipsis, spasi khusus
    raw_chars = (
        "\u201ckutip ganda\u201d dan \u201ebawah\u201f "
        "\u2018tunggal\u2019 dan \u201abawah\u201b "
        "panjang\u2014tengah\u2013garis\u2015strip "
        "tunggu\u2026 "
        "angka\u00a0satu\u202fdua\u2007tiga"
    )
    res_chars = format_text(raw_chars, unify_characters=True)
    expected = (
        '"kutip ganda" dan "bawah" '
        "'tunggal' dan 'bawah' "
        "panjang-tengah-garis-strip "
        "tunggu... "
        "angka satu dua tiga"
    )
    assert res_chars["text"] == expected


def test_text_formatter_akhir_baris_crlf() -> None:
    raw = "baris 1\r\nbaris 2\rbaris 3\nbaris 4"
    res = format_text(raw)
    assert res["text"] == "baris 1\nbaris 2\nbaris 3\nbaris 4"
    assert res["masukan"]["lines"] == 4
    assert res["keluaran"]["lines"] == 4


def test_text_formatter_crlf_masukan_dan_dihemat_chars() -> None:
    raw = "a  b\r\nc  d\r\n"
    res = format_text(raw)
    assert res["masukan"]["chars"] == len("a  b\nc  d\n")
    assert res["dihemat"]["chars"] == res["masukan"]["chars"] - res["keluaran"]["chars"]


def test_text_formatter_blank_modes() -> None:
    raw = "baris 1\n\n\nbaris 2\n\nbaris 3"

    # keep: baris kosong dibiarkan
    res_keep = format_text(raw, blank_mode="keep", line_mode="keep")
    assert res_keep["text"] == "baris 1\n\n\nbaris 2\n\nbaris 3"

    # collapse: baris kosong berurutan dirapatkan jadi maksimal satu
    res_collapse = format_text(raw, blank_mode="collapse", line_mode="keep")
    assert res_collapse["text"] == "baris 1\n\nbaris 2\n\nbaris 3"

    # remove: semua baris kosong dibuang
    res_remove = format_text(raw, blank_mode="remove", line_mode="keep")
    assert res_remove["text"] == "baris 1\nbaris 2\nbaris 3"


def test_text_formatter_line_modes() -> None:
    raw = "Paragraf 1 baris a\nParagraf 1 baris b\n\n\nParagraf 2 baris a\nParagraf 2 baris b"

    # keep
    res_keep = format_text(raw, blank_mode="collapse", line_mode="keep")
    assert res_keep["text"] == "Paragraf 1 baris a\nParagraf 1 baris b\n\nParagraf 2 baris a\nParagraf 2 baris b"

    # paragraph dengan blank_mode=collapse
    res_para_col = format_text(raw, blank_mode="collapse", line_mode="paragraph")
    assert res_para_col["text"] == "Paragraf 1 baris a Paragraf 1 baris b\n\nParagraf 2 baris a Paragraf 2 baris b"

    # paragraph dengan blank_mode=remove (dipisah satu baris baru saja)
    res_para_rem = format_text(raw, blank_mode="remove", line_mode="paragraph")
    assert res_para_rem["text"] == "Paragraf 1 baris a Paragraf 1 baris b\nParagraf 2 baris a Paragraf 2 baris b"

    # single: semua digabung jadi satu baris dipisah satu spasi
    res_single = format_text(raw, line_mode="single")
    assert res_single["text"] == "Paragraf 1 baris a Paragraf 1 baris b Paragraf 2 baris a Paragraf 2 baris b"


def test_text_formatter_hanya_spasi_dan_kosong() -> None:
    # Teks hanya spasi -> hasil kosong, angka keluaran 0, bukan galat
    res_spasi = format_text("   \n   \t   \n  ")
    assert res_spasi["text"] == ""
    assert res_spasi["keluaran"]["chars"] == 0
    assert res_spasi["keluaran"]["lines"] == 0
    assert res_spasi["keluaran"]["blank_lines"] == 0

    # Teks kosong
    res_kosong = format_text("")
    assert res_kosong["text"] == ""
    assert res_kosong["keluaran"]["chars"] == 0
    assert res_kosong["keluaran"]["lines"] == 0
    assert res_kosong["keluaran"]["blank_lines"] == 0
    assert res_kosong["masukan"]["chars"] == 0


def test_text_formatter_validasi_galat() -> None:
    # Field text None
    try:
        format_text(None)
        assert False, "Harusnya melempar TextFormatterError"
    except TextFormatterError as exc:
        assert exc.code == TF_NO_TEXT
        assert exc.status_code == 400

    # Field text bukan string
    try:
        format_text(12345)
        assert False, "Harusnya melempar TextFormatterError"
    except TextFormatterError as exc:
        assert exc.code == TF_NOT_TEXT
        assert exc.status_code == 400

    # Lebih dari 200.000 karakter
    long_text = "a" * (TF_MAX_CHARS + 1)
    try:
        format_text(long_text)
        assert False, "Harusnya melempar TextFormatterError"
    except TextFormatterError as exc:
        assert exc.code == TF_TOO_LONG
        assert exc.status_code == 413

    # tab_width tidak dikenal
    for inv_tab in [1, 3, 5, 10, "tujuh"]:
        try:
            parse_text_formatter_tab_width(inv_tab)
            assert False, f"Harusnya melempar galat untuk tab_width {inv_tab}"
        except TextFormatterError as exc:
            assert exc.code == TF_INVALID_TAB_WIDTH
            assert exc.status_code == 400

    # blank_mode tidak dikenal
    try:
        normalize_text_formatter_blank_mode("acak")
        assert False, "Harusnya melempar galat untuk blank_mode tidak dikenal"
    except TextFormatterError as exc:
        assert exc.code == TF_UNSUPPORTED_BLANK_MODE
        assert exc.status_code == 400

    # line_mode tidak dikenal
    try:
        normalize_text_formatter_line_mode("ngawur")
        assert False, "Harusnya melempar galat untuk line_mode tidak dikenal"
    except TextFormatterError as exc:
        assert exc.code == TF_UNSUPPORTED_LINE_MODE
        assert exc.status_code == 400

    # boolean tidak dikenal
    try:
        parse_text_formatter_bool("mungkin", "collapse_spaces")
        assert False, "Harusnya melempar galat untuk boolean tidak dikenal"
    except TextFormatterError as exc:
        assert exc.code == TF_INVALID_BOOLEAN
        assert exc.status_code == 400


# --- Uji HTTP TestClient untuk Text Formatter ---------------------------------
def test_http_text_formatter_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/text-formatter/limits")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["max_chars"] == TF_MAX_CHARS
    assert body["max_bytes"] == TF_MAX_BYTES
    assert body["max_mb"] == 1
    assert isinstance(body["blank_modes"], list)
    assert isinstance(body["line_modes"], list)
    assert body["tab_widths"] == [2, 4, 8]
    assert body["defaults"]["tab_width"] == 4
    assert body["defaults"]["blank_mode"] == "collapse"
    assert body["defaults"]["line_mode"] == "keep"
    assert "no-store" in response.headers.get("Cache-Control", "")


def test_http_text_formatter_sukses_dan_cache_control() -> None:
    client = _test_client()
    if client is None:
        return
    raw = "Halo   dunia !\nIni baris kedua   .\n\n\nIni paragraf   baru ."
    response = client.post(
        "/api/text-formatter",
        data={
            "text": raw,
            "collapse_spaces": "true",
            "trim_lines": "true",
            "space_before_punctuation": "true",
            "blank_mode": "collapse",
            "line_mode": "paragraph",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == "Halo dunia! Ini baris kedua.\n\nIni paragraf baru."
    assert body["keluaran"]["lines"] == 3
    assert body["keluaran"]["chars"] > 0
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert response.headers.get("Pragma") == "no-cache"
    assert "X-Processing-Ms" in response.headers


def test_http_text_formatter_hanya_spasi() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post("/api/text-formatter", data={"text": "   \n  \t  \n  "})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == ""
    assert body["keluaran"]["chars"] == 0
    assert body["keluaran"]["lines"] == 0
    assert body["keluaran"]["blank_lines"] == 0


def test_http_text_formatter_galat_dan_validasi() -> None:
    client = _test_client()
    if client is None:
        return

    # text absen -> INVALID_REQUEST 400
    resp_no_text = client.post("/api/text-formatter", data={})
    assert resp_no_text.status_code == 400, resp_no_text.text
    assert resp_no_text.json()["error"]["code"] == TF_INVALID_REQUEST

    # text terlalu panjang -> TOO_LONG 413
    long_text = "x" * (TF_MAX_CHARS + 1)
    resp_long = client.post("/api/text-formatter", data={"text": long_text})
    assert resp_long.status_code == 413, resp_long.text
    assert resp_long.json()["error"]["code"] == TF_TOO_LONG

    # tab_width tidak dikenal -> 400
    resp_tab = client.post("/api/text-formatter", data={"text": "a\tb", "tab_width": "5"})
    assert resp_tab.status_code == 400, resp_tab.text
    assert resp_tab.json()["error"]["code"] == TF_INVALID_TAB_WIDTH

    # blank_mode tidak dikenal -> 400
    resp_bm = client.post("/api/text-formatter", data={"text": "a\nb", "blank_mode": "aneh"})
    assert resp_bm.status_code == 400, resp_bm.text
    assert resp_bm.json()["error"]["code"] == TF_UNSUPPORTED_BLANK_MODE

    # line_mode tidak dikenal -> 400
    resp_lm = client.post("/api/text-formatter", data={"text": "a\nb", "line_mode": "ngawur"})
    assert resp_lm.status_code == 400, resp_lm.text
    assert resp_lm.json()["error"]["code"] == TF_UNSUPPORTED_LINE_MODE

    # boolean tidak dikenal -> 400
    resp_bool = client.post("/api/text-formatter", data={"text": "a\nb", "collapse_spaces": "mungkin"})
    assert resp_bool.status_code == 400, resp_bool.text
    assert resp_bool.json()["error"]["code"] == TF_INVALID_BOOLEAN

    # Bukan multipart/form-data -> 400
    resp_json = client.post("/api/text-formatter", json={"text": "a\nb"})
    assert resp_json.status_code == 400, resp_json.text
    assert resp_json.json()["error"]["code"] == TF_INVALID_REQUEST


def test_http_text_formatter_regresi_endpoint_lama() -> None:
    client = _test_client()
    if client is None:
        return

    # Endpoint lama tetap 200
    assert client.get("/health").status_code == 200
    assert client.get("/api/pdf/merge/limits").status_code == 200
    assert client.get("/api/image/convert/limits").status_code == 200
    assert client.get("/api/word-count/limits").status_code == 200
    assert client.get("/api/case/limits").status_code == 200
    assert client.get("/api/base64/limits").status_code == 200
    assert client.get("/api/remove-duplicates/limits").status_code == 200
    assert client.get("/api/list-shuffler/limits").status_code == 200

    # Root service info harus memuat text-formatter
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert "text-formatter" in root_data["tools"]


# --- Uji Konverter Satuan: Logika murni ---------------------------------------
def test_unit_convert_categories_dan_limits() -> None:
    # Minimal memuat 8 kategori
    assert len(UC_CATEGORIES) == 8
    expected_categories = ["panjang", "massa", "suhu", "luas", "volume", "kecepatan", "waktu", "data"]
    for cat_id in expected_categories:
        assert cat_id in UC_CATEGORIES
        cat = UC_CATEGORIES[cat_id]
        assert "id" in cat and "nama" in cat and "units" in cat
        assert len(cat["units"]) > 0
        for u in cat["units"]:
            assert "kode" in u and "label" in u and "simbol" in u


def test_unit_convert_panjang() -> None:
    # 2 m -> 200 cm
    res_m = convert_units("2", "panjang", "m", "cm")
    assert res_m["hasil"] == 200.0
    assert res_m["hasil_teks"] == "200"
    assert res_m["laju"] == 100.0
    assert res_m["laju_teks"] == "100"

    # 1 km -> 1000 m
    res_km = convert_units("1", "panjang", "km", "m")
    assert res_km["hasil"] == 1000.0
    assert res_km["hasil_teks"] == "1.000"

    # 1 mil -> 1,609344 km
    res_mil = convert_units("1", "panjang", "mil", "km")
    assert res_mil["hasil_teks"] == "1,609344"


def test_unit_convert_berat() -> None:
    # 1 pon -> 453,59237 g
    res_pon = convert_units("1", "massa", "pon", "g")
    assert res_pon["hasil_teks"] == "453,59237"

    # 1 ton -> 1000 kg
    res_ton = convert_units("1", "massa", "ton", "kg")
    assert res_ton["hasil"] == 1000.0
    assert res_ton["hasil_teks"] == "1.000"


def test_unit_convert_suhu() -> None:
    # 100 C -> 212 F
    res_f = convert_units("100", "suhu", "celsius", "fahrenheit")
    assert res_f["hasil_teks"] == "212"

    # 0 C -> 273,15 K
    res_k = convert_units("0", "suhu", "celsius", "kelvin")
    assert res_k["hasil_teks"] == "273,15"

    # 37 C -> 98,6 F
    res_body = convert_units("37", "suhu", "celsius", "fahrenheit")
    assert res_body["hasil_teks"] == "98,6"

    # -40 C -> -40 F
    res_minus = convert_units("-40", "suhu", "celsius", "fahrenheit")
    assert res_minus["hasil_teks"] == "-40"

    # 100 reamur -> 125 C
    res_re = convert_units("100", "suhu", "reamur", "celsius")
    assert res_re["hasil_teks"] == "125"

    # Catatan suhu berisi penjelasan rumus
    assert res_f["catatan"] != ""


def test_unit_convert_luas_kecepatan() -> None:
    # 1 hektar -> 10000 m2
    res_luas = convert_units("1", "luas", "hektar", "m2")
    assert res_luas["hasil"] == 10000.0
    assert res_luas["hasil_teks"] == "10.000"

    # 36 kmjam -> 10 ms
    res_speed = convert_units("36", "kecepatan", "kmjam", "ms")
    assert res_speed["hasil_teks"] == "10"


def test_unit_convert_waktu_data() -> None:
    # 1 tahun -> 365 hari
    res_time = convert_units("1", "waktu", "tahun", "hari")
    assert res_time["hasil_teks"] == "365"

    # 1 mib -> 1048576 byte
    res_mib = convert_units("1", "data", "mib", "byte")
    assert res_mib["hasil"] == 1048576.0
    assert res_mib["hasil_teks"] == "1.048.576"

    # 1 mb -> 1000000 byte
    res_mb = convert_units("1", "data", "mb", "byte")
    assert res_mb["hasil"] == 1000000.0
    assert res_mb["hasil_teks"] == "1.000.000"


def test_unit_convert_parsing_variasi_angka() -> None:
    # masukan "1.234,5" dan "1 234.5" menghasilkan nilai yang sama
    r1 = convert_units("1.234,5", "panjang", "m", "cm")
    r2 = convert_units("1 234.5", "panjang", "m", "cm")
    assert r1["hasil"] == r2["hasil"] == 123450.0
    assert r1["hasil_teks"] == r2["hasil_teks"]

    # Format lain juga valid
    r3 = convert_units("1234.5", "panjang", "m", "cm")
    r4 = convert_units("1234,5", "panjang", "m", "cm")
    assert r3["hasil"] == r4["hasil"] == 123450.0


def test_unit_convert_semua_satuan_konsisten() -> None:
    # semua berisi semua satuan kategori dan nilai yang konsisten dengan hasil
    res = convert_units("2", "panjang", "m", "cm")
    cat = UC_CATEGORIES["panjang"]
    assert len(res["semua"]) == len(cat["units"])
    for u in res["semua"]:
        assert "kode" in u and "label" in u and "simbol" in u and "nilai" in u and "teks" in u
        if u["kode"] == "cm":
            assert u["nilai"] == res["hasil"]
            assert u["teks"] == res["hasil_teks"]


def test_unit_convert_galat_kode_dan_status() -> None:
    # NO_VALUE
    try:
        convert_units("   ", "panjang", "m", "cm")
        assert False, "Harusnya melempar UnitConvertError NO_VALUE"
    except UnitConvertError as exc:
        assert exc.code == UC_NO_VALUE
        assert exc.status_code == 400

    # NOT_A_NUMBER
    try:
        convert_units("seribu", "panjang", "m", "cm")
        assert False, "Harusnya melempar UnitConvertError NOT_A_NUMBER"
    except UnitConvertError as exc:
        assert exc.code == UC_NOT_A_NUMBER
        assert exc.status_code == 400

    # OUT_OF_RANGE (nilai 1e20)
    try:
        convert_units("1e20", "panjang", "m", "cm")
        assert False, "Harusnya melempar UnitConvertError OUT_OF_RANGE"
    except UnitConvertError as exc:
        assert exc.code == UC_OUT_OF_RANGE
        assert exc.status_code == 413

    # OUT_OF_RANGE (karakter melebihi 40)
    try:
        convert_units("9" * 45, "panjang", "m", "cm")
        assert False, "Harusnya melempar UnitConvertError OUT_OF_RANGE"
    except UnitConvertError as exc:
        assert exc.code == UC_OUT_OF_RANGE
        assert exc.status_code == 413

    # UNSUPPORTED_CATEGORY
    try:
        convert_units("10", "kategori_tidak_ada", "m", "cm")
        assert False, "Harusnya melempar UnitConvertError UNSUPPORTED_CATEGORY"
    except UnitConvertError as exc:
        assert exc.code == UC_UNSUPPORTED_CATEGORY
        assert exc.status_code == 400

    # UNSUPPORTED_UNIT
    try:
        convert_units("10", "panjang", "m", "satuan_tidak_ada")
        assert False, "Harusnya melempar UnitConvertError UNSUPPORTED_UNIT"
    except UnitConvertError as exc:
        assert exc.code == UC_UNSUPPORTED_UNIT
        assert exc.status_code == 400

    # INVALID_REQUEST (None values)
    try:
        convert_units(None, "panjang", "m", "cm")
        assert False, "Harusnya melempar UnitConvertError INVALID_REQUEST"
    except UnitConvertError as exc:
        assert exc.code == UC_INVALID_REQUEST
        assert exc.status_code == 400


def test_unit_convert_nilai_bukan_nol_tidak_jadi_nol() -> None:
    # 1 mg -> ton: hasil_teks == "1,00000e-09" dan laju_teks == "1,00000e-09"
    res_mg = convert_units("1", "massa", "mg", "ton")
    assert res_mg["hasil_teks"] == "1,00000e-09"
    assert res_mg["laju_teks"] == "1,00000e-09"

    # 1 g -> ton: hasil_teks == "0,000001"
    res_g = convert_units("1", "massa", "g", "ton")
    assert res_g["hasil_teks"] == "0,000001"

    # 0 m -> km: hasil_teks == "0"
    res_nol = convert_units("0", "panjang", "m", "km")
    assert res_nol["hasil_teks"] == "0"

    # 1 byte -> tib: hasil_teks == "9,09495e-13"
    res_byte = convert_units("1", "data", "byte", "tib")
    assert res_byte["hasil_teks"] == "9,09495e-13"

    # -0.0 -> "0"
    assert format_unit_number(-0.0) == "0"


def test_unit_convert_format_angka_sembilan_contoh() -> None:
    # Uji 9 contoh spesifikasi langsung memanggil format_angka
    assert format_angka(9988371125.4096) == "9.988.371.125,4096"
    assert format_angka(433035566999.99994) == "433.035.566.999,99994"
    assert format_angka(1e-9) == "1,00000e-09"
    assert format_angka(1e-6) == "0,000001"
    assert format_angka(0.0) == "0"
    assert format_angka(2.5) == "2,5"
    assert format_angka(200.0) == "200"
    assert format_angka(-0.0) == "0"
    assert format_angka(1609.344) == "1.609,344"


# --- Uji HTTP TestClient untuk Konverter Satuan ------------------------------
def test_http_unit_convert_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/unit-convert/limits")
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["categories"], list)
    assert len(body["categories"]) == 8
    assert body["max_value"] == UC_MAX_VALUE
    assert body["max_input_chars"] == UC_MAX_INPUT_CHARS
    assert body["defaults"]["category"] == "panjang"
    assert body["defaults"]["from"] == "m"
    assert body["defaults"]["to"] == "cm"
    assert body["processed_on"] == "server"
    assert "no-store" in response.headers.get("Cache-Control", "")


def test_http_unit_convert_sukses_dan_headers() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/unit-convert",
        data={
            "value": "2",
            "category": "panjang",
            "from": "m",
            "to": "cm",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["hasil"] == 200.0
    assert body["hasil_teks"] == "200"
    assert body["kategori"]["id"] == "panjang"
    assert body["dari"]["kode"] == "m"
    assert body["ke"]["kode"] == "cm"
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert response.headers.get("Pragma") == "no-cache"
    assert "X-Processing-Ms" in response.headers


def test_http_unit_convert_galat() -> None:
    client = _test_client()
    if client is None:
        return

    # Field kurang -> 400 INVALID_REQUEST
    resp_missing = client.post("/api/unit-convert", data={"value": "2"})
    assert resp_missing.status_code == 400, resp_missing.text
    assert resp_missing.json()["error"]["code"] == UC_INVALID_REQUEST

    # NO_VALUE -> 400
    resp_no_val = client.post(
        "/api/unit-convert",
        data={"value": "   ", "category": "panjang", "from": "m", "to": "cm"},
    )
    assert resp_no_val.status_code == 400, resp_no_val.text
    assert resp_no_val.json()["error"]["code"] == UC_NO_VALUE

    # NOT_A_NUMBER -> 400
    resp_nan = client.post(
        "/api/unit-convert",
        data={"value": "seribu", "category": "panjang", "from": "m", "to": "cm"},
    )
    assert resp_nan.status_code == 400, resp_nan.text
    assert resp_nan.json()["error"]["code"] == UC_NOT_A_NUMBER

    # OUT_OF_RANGE -> 413
    resp_range = client.post(
        "/api/unit-convert",
        data={"value": "1e20", "category": "panjang", "from": "m", "to": "cm"},
    )
    assert resp_range.status_code == 413, resp_range.text
    assert resp_range.json()["error"]["code"] == UC_OUT_OF_RANGE

    # UNSUPPORTED_CATEGORY -> 400
    resp_cat = client.post(
        "/api/unit-convert",
        data={"value": "10", "category": "ngawur", "from": "m", "to": "cm"},
    )
    assert resp_cat.status_code == 400, resp_cat.text
    assert resp_cat.json()["error"]["code"] == UC_UNSUPPORTED_CATEGORY

    # UNSUPPORTED_UNIT -> 400
    resp_unit = client.post(
        "/api/unit-convert",
        data={"value": "10", "category": "panjang", "from": "m", "to": "ngawur"},
    )
    assert resp_unit.status_code == 400, resp_unit.text
    assert resp_unit.json()["error"]["code"] == UC_UNSUPPORTED_UNIT

    # Bukan multipart/form-data -> 400
    resp_json = client.post(
        "/api/unit-convert",
        json={"value": "10", "category": "panjang", "from": "m", "to": "cm"},
    )
    assert resp_json.status_code == 400, resp_json.text
    assert resp_json.json()["error"]["code"] == UC_INVALID_REQUEST


def test_http_unit_convert_root_endpoint() -> None:
    client = _test_client()
    if client is None:
        return
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert "unit-convert" in root_data["tools"]


# --- Uji Logika Kalkulator Persen -------------------------------------------
def test_percent_calc_lima_mode() -> None:
    # 1. persen_dari: 20 & 150 -> 30
    res1 = compute_percent("persen_dari", "20", "150")
    assert res1["hasil"]["nilai"] == 30.0
    assert res1["hasil"]["teks"] == "30"
    assert res1["hasil"]["satuan"] == ""
    assert res1["kalimat"] == "20% dari 150 adalah 30."
    assert res1["rumus"] == "20 : 100 x 150 = 30"
    assert res1["masukan"]["a"] == "20"
    assert res1["masukan"]["b"] == "150"

    # 2. berapa_persen: 45 & 180 -> 25
    res2 = compute_percent("berapa_persen", "45", "180")
    assert res2["hasil"]["nilai"] == 25.0
    assert res2["hasil"]["teks"] == "25"
    assert res2["hasil"]["satuan"] == "%"
    assert res2["kalimat"] == "45 adalah 25% dari 180."
    assert res2["rumus"] == "45 : 180 x 100 = 25%"

    # 3. perubahan: 200 & 250 -> 25
    res3 = compute_percent("perubahan", "200", "250")
    assert res3["hasil"]["nilai"] == 25.0
    assert res3["hasil"]["teks"] == "25"
    assert res3["hasil"]["satuan"] == "%"
    assert res3["kalimat"] == "Dari 200 ke 250 berarti naik 25%."
    assert res3["rumus"] == "(250 - 200) : 200 x 100 = 25%"

    # 4. tambah_persen: 10 & 150 -> 165
    res4 = compute_percent("tambah_persen", "10", "150")
    assert res4["hasil"]["nilai"] == 165.0
    assert res4["hasil"]["teks"] == "165"
    assert res4["hasil"]["satuan"] == ""
    assert res4["kalimat"] == "150 ditambah 10% menjadi 165."
    assert res4["rumus"] == "150 x (1 + 10 : 100) = 165"

    # 5. kurang_persen: 15 & 200 -> 170
    res5 = compute_percent("kurang_persen", "15", "200")
    assert res5["hasil"]["nilai"] == 170.0
    assert res5["hasil"]["teks"] == "170"
    assert res5["hasil"]["satuan"] == ""
    assert res5["kalimat"] == "200 dikurangi 15% menjadi 170."
    assert res5["rumus"] == "200 x (1 - 15 : 100) = 170"


def test_percent_calc_perubahan_arah_dan_nol() -> None:
    # Naik
    res_naik = compute_percent("perubahan", "200", "250")
    assert res_naik["hasil"]["nilai"] == 25.0
    assert res_naik["kalimat"] == "Dari 200 ke 250 berarti naik 25%."
    assert res_naik["rumus"] == "(250 - 200) : 200 x 100 = 25%"

    # Turun
    res_turun = compute_percent("perubahan", "250", "200")
    assert res_turun["hasil"]["nilai"] == -20.0
    assert res_turun["hasil"]["teks"] == "-20"
    assert res_turun["kalimat"] == "Dari 250 ke 200 berarti turun 20%."
    assert res_turun["rumus"] == "(200 - 250) : 250 x 100 = -20%"

    # Sama (0%)
    res_sama = compute_percent("perubahan", "200", "200")
    assert res_sama["hasil"]["nilai"] == 0.0
    assert res_sama["hasil"]["teks"] == "0"
    assert res_sama["kalimat"] == "Dari 200 ke 200 tidak ada perubahan (0%)."
    assert res_sama["rumus"] == "(200 - 200) : 200 x 100 = 0%"


def test_percent_calc_format_dan_parsing_angka() -> None:
    # Masukan ribuan gaya Indonesia: "1.234,5"
    res_indo = compute_percent("persen_dari", "10", "1.234,5")
    assert res_indo["hasil"]["nilai"] == 123.45
    assert res_indo["hasil"]["teks"] == "123,45"
    assert res_indo["masukan"]["b"] == "1.234,5"

    # Masukan ribuan gaya biasa: "1,234.5"
    res_biasa = compute_percent("persen_dari", "10", "1,234.5")
    assert res_biasa["hasil"]["nilai"] == 123.45

    # Masukan berkoma desimal
    res_koma = compute_percent("persen_dari", "2,5", "200")
    assert res_koma["hasil"]["nilai"] == 5.0
    assert res_koma["hasil"]["teks"] == "5"

    # Masukan bertitik tunggal dibaca sebagai tanda desimal (sama seperti alat konversi satuan)
    res_titik = compute_percent("persen_dari", "10", "1.500")
    assert res_titik["hasil"]["nilai"] == 0.15
    assert res_titik["hasil"]["teks"] == "0,15"

    # Pembulatan desimal banyak (maksimum 6 angka)
    res_des = compute_percent("berapa_persen", "10", "30")
    assert res_des["hasil"]["teks"] == "33,333333"

    # Angka negatif
    res_neg = compute_percent("tambah_persen", "10", "-100")
    assert res_neg["hasil"]["nilai"] == -110.0
    assert res_neg["hasil"]["teks"] == "-110"

    # 0 sebagai angka dasar tambah/kurang
    res_nol_tambah = compute_percent("tambah_persen", "10", "0")
    assert res_nol_tambah["hasil"]["nilai"] == 0.0
    assert res_nol_tambah["hasil"]["teks"] == "0"

    res_nol_kurang = compute_percent("kurang_persen", "10", "0")
    assert res_nol_kurang["hasil"]["nilai"] == 0.0
    assert res_nol_kurang["hasil"]["teks"] == "0"

    # Eksponen gaya Indonesia
    assert format_percent_number(5e-7) == "5e-07"
    assert format_percent_number(1.25e18) == "1,25e+18"
    assert format_percent_number(0.0) == "0"
    assert format_percent_number(-0.0) == "0"


def test_percent_calc_parser_sepakat_dengan_konversi_satuan() -> None:
    """Uji parser kalkulator persen sepakat dengan parser alat konversi satuan.

    Tujuannya supaya dua alat tidak pernah beda tafsir untuk masukan yang sama.
    """
    from app.unit_convert import parse_value as unit_parse_value, UnitConvertError

    masukan_list = ["1.500", "1,234.5", "1.234,5", "2,5", "1,2,3", "0,001", "-45.7", "12"]
    for item in masukan_list:
        percent_err = None
        unit_err = None
        percent_val = None
        unit_val = None

        try:
            percent_val = parse_percent_number(item)
        except PercentCalcError as exc:
            percent_err = exc

        try:
            unit_val = unit_parse_value(item)
        except UnitConvertError as exc:
            unit_err = exc

        if percent_err is not None or unit_err is not None:
            assert percent_err is not None and unit_err is not None, (
                f"Perbedaan penanganan galat untuk masukan {item!r}: "
                f"percent={percent_err!r}, unit={unit_err!r}"
            )
        else:
            assert percent_val == unit_val, (
                f"Hasil parsing berbeda untuk masukan {item!r}: "
                f"percent={percent_val!r}, unit={unit_val!r}"
            )


def test_percent_calc_batas_dan_galat() -> None:
    # Batas 1e15 yang boleh
    res_max = compute_percent("persen_dari", "10", "1e15")
    assert res_max["hasil"]["nilai"] == 1e14

    # Batas 1e16 yang ditolak (OUT_OF_RANGE 413)
    try:
        compute_percent("persen_dari", "10", "1e16")
        assert False, "Harusnya melempar PercentCalcError OUT_OF_RANGE"
    except PercentCalcError as exc:
        assert exc.code == PC_OUT_OF_RANGE
        assert exc.status_code == 413

    # DIVIDE_BY_ZERO pada mode 2 dengan b=0 (status 422)
    try:
        compute_percent("berapa_persen", "50", "0")
        assert False, "Harusnya melempar PercentCalcError DIVIDE_BY_ZERO"
    except PercentCalcError as exc:
        assert exc.code == PC_DIVIDE_BY_ZERO
        assert exc.status_code == 422
        assert "Angka total tidak boleh 0" in exc.message

    # DIVIDE_BY_ZERO pada mode 3 dengan a=0 (status 422)
    try:
        compute_percent("perubahan", "0", "100")
        assert False, "Harusnya melempar PercentCalcError DIVIDE_BY_ZERO"
    except PercentCalcError as exc:
        assert exc.code == PC_DIVIDE_BY_ZERO
        assert exc.status_code == 422
        assert "Angka awal tidak boleh 0" in exc.message

    # NOT_A_NUMBER
    try:
        compute_percent("persen_dari", "bukan_angka", "100")
        assert False, "Harusnya melempar PercentCalcError NOT_A_NUMBER"
    except PercentCalcError as exc:
        assert exc.code == PC_NOT_A_NUMBER
        assert exc.status_code == 400

    # NO_VALUE
    try:
        compute_percent("persen_dari", "   ", "100")
        assert False, "Harusnya melempar PercentCalcError NO_VALUE"
    except PercentCalcError as exc:
        assert exc.code == PC_NO_VALUE
        assert exc.status_code == 400

    # UNSUPPORTED_MODE
    try:
        compute_percent("mode_palsu", "10", "100")
        assert False, "Harusnya melempar PercentCalcError UNSUPPORTED_MODE"
    except PercentCalcError as exc:
        assert exc.code == PC_UNSUPPORTED_MODE
        assert exc.status_code == 400

    # INVALID_REQUEST (None values)
    try:
        compute_percent(None, "10", "100")
        assert False, "Harusnya melempar PercentCalcError INVALID_REQUEST"
    except PercentCalcError as exc:
        assert exc.code == PC_INVALID_REQUEST
        assert exc.status_code == 400

    # Panjang masukan 40 karakter diizinkan
    val_40 = "1" + "0" * 13 + "." + "0" * 25
    assert len(val_40) == 40
    res_40 = compute_percent("persen_dari", "10", val_40)
    assert res_40["hasil"]["nilai"] == 1000000000000.0

    # Panjang masukan 41 karakter ditolak (413)
    val_41 = "1" + "0" * 40
    assert len(val_41) == 41
    try:
        compute_percent("persen_dari", "10", val_41)
        assert False, "Harusnya melempar PercentCalcError OUT_OF_RANGE"
    except PercentCalcError as exc:
        assert exc.code == PC_OUT_OF_RANGE
        assert exc.status_code == 413


# --- Uji HTTP TestClient untuk Kalkulator Persen -----------------------------
def test_http_percent_calc_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/percent-calc/limits")
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["modes"], list)
    assert len(body["modes"]) == 5
    assert body["max_value"] == PC_MAX_ABS_VALUE
    assert body["max_input_chars"] == PC_MAX_INPUT_CHARS
    assert body["processed_on"] == "server"
    assert "no-store" in response.headers.get("Cache-Control", "")


def test_http_percent_calc_sukses_dan_headers() -> None:
    client = _test_client()
    if client is None:
        return

    cases = [
        ("persen_dari", "20", "150", 30.0, "30", ""),
        ("berapa_persen", "45", "180", 25.0, "25", "%"),
        ("perubahan", "200", "250", 25.0, "25", "%"),
        ("tambah_persen", "10", "150", 165.0, "165", ""),
        ("kurang_persen", "15", "200", 170.0, "170", ""),
    ]

    for mode, a, b, exp_val, exp_teks, exp_satuan in cases:
        response = client.post(
            "/api/percent-calc",
            data={"mode": mode, "a": a, "b": b},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["hasil"]["nilai"] == exp_val
        assert body["hasil"]["teks"] == exp_teks
        assert body["hasil"]["satuan"] == exp_satuan
        assert "kalimat" in body
        assert "rumus" in body
        assert "no-store" in response.headers.get("Cache-Control", "")
        assert response.headers.get("Pragma") == "no-cache"
        assert "X-Processing-Ms" in response.headers


def test_http_percent_calc_galat() -> None:
    client = _test_client()
    if client is None:
        return

    # Field kurang -> 400 INVALID_REQUEST
    resp_missing = client.post("/api/percent-calc", data={"mode": "persen_dari", "a": "20"})
    assert resp_missing.status_code == 400, resp_missing.text
    assert resp_missing.json()["error"]["code"] == PC_INVALID_REQUEST

    # NO_VALUE -> 400
    resp_no_val = client.post(
        "/api/percent-calc",
        data={"mode": "persen_dari", "a": "   ", "b": "100"},
    )
    assert resp_no_val.status_code == 400, resp_no_val.text
    assert resp_no_val.json()["error"]["code"] == PC_NO_VALUE

    # NOT_A_NUMBER -> 400
    resp_nan = client.post(
        "/api/percent-calc",
        data={"mode": "persen_dari", "a": "sepuluh", "b": "100"},
    )
    assert resp_nan.status_code == 400, resp_nan.text
    assert resp_nan.json()["error"]["code"] == PC_NOT_A_NUMBER

    # OUT_OF_RANGE -> 413
    resp_range = client.post(
        "/api/percent-calc",
        data={"mode": "persen_dari", "a": "10", "b": "1e20"},
    )
    assert resp_range.status_code == 413, resp_range.text
    assert resp_range.json()["error"]["code"] == PC_OUT_OF_RANGE

    # DIVIDE_BY_ZERO -> 422
    resp_zero = client.post(
        "/api/percent-calc",
        data={"mode": "berapa_persen", "a": "50", "b": "0"},
    )
    assert resp_zero.status_code == 422, resp_zero.text
    assert resp_zero.json()["error"]["code"] == PC_DIVIDE_BY_ZERO

    # UNSUPPORTED_MODE -> 400
    resp_mode = client.post(
        "/api/percent-calc",
        data={"mode": "mode_ngawur", "a": "10", "b": "100"},
    )
    assert resp_mode.status_code == 400, resp_mode.text
    assert resp_mode.json()["error"]["code"] == PC_UNSUPPORTED_MODE

    # Bukan multipart/form-data -> 400
    resp_json = client.post(
        "/api/percent-calc",
        json={"mode": "persen_dari", "a": "10", "b": "100"},
    )
    assert resp_json.status_code == 400, resp_json.text
    assert resp_json.json()["error"]["code"] == PC_INVALID_REQUEST


def test_http_percent_calc_root_endpoint_dan_regresi() -> None:
    client = _test_client()
    if client is None:
        return

    # Root endpoint berisi percent-calc
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert "percent-calc" in root_data["tools"]

    # Regresi endpoint yang sudah ada
    health_resp = client.get("/health")
    assert health_resp.status_code == 200

    uc_limits = client.get("/api/unit-convert/limits")
    assert uc_limits.status_code == 200

    wc_limits = client.get("/api/word-count/limits")
    assert wc_limits.status_code == 200


# --- Uji logika dan HTTP alat JSON (Rapikan & periksa JSON) -------------------
def test_json_tool_logika_murni() -> None:
    # 1. rapikan: {"b":1,"a":[1,2]} indent 2 -> keluaran berisi baris baru; indent "tab" -> diawali tab
    res_indent2 = proses_json('{"b":1,"a":[1,2]}', mode="rapikan", indent=2)
    assert "\n" in res_indent2["keluaran"]["teks"]
    assert res_indent2["sah"] is True
    assert res_indent2["mode"] == "rapikan"
    assert res_indent2["aturan"]["indentasi"] == 2
    assert res_indent2["keluaran"]["banyak_baris_ditambah"] > 0

    res_tab = proses_json('{"b":1,"a":[1,2]}', mode="rapikan", indent="tab")
    lines_tab = res_tab["keluaran"]["teks"].splitlines()
    assert any(line.startswith("\t") for line in lines_tab)
    assert res_tab["aturan"]["indentasi"] == "tab"

    # 2. urutkan_kunci=true -> kunci jadi urut (a sebelum b)
    res_sorted = proses_json('{"b":1,"a":[1,2]}', mode="rapikan", indent=2, urutkan_kunci=True)
    text_sorted = res_sorted["keluaran"]["teks"]
    pos_a = text_sorted.find('"a"')
    pos_b = text_sorted.find('"b"')
    assert pos_a != -1 and pos_b != -1 and pos_a < pos_b

    # 3. padatkan -> keluaran sama dengan json.dumps(..., separators=(",",":"), ensure_ascii=False)
    sample_obj = {"nama": "Ayu", "angka": [1, 2, 3], "aktif": True}
    sample_raw = json.dumps(sample_obj)
    res_compact = proses_json(sample_raw, mode="padatkan")
    expected_compact = json.dumps(sample_obj, separators=(",", ":"), ensure_ascii=False)
    assert res_compact["keluaran"]["teks"] == expected_compact
    assert res_compact["mode"] == "padatkan"

    # 4. periksa -> keluaran identik dengan masukan walau isinya berantakan spasinya
    messy_json = '  {   "b" :  1 ,  \n\n  "a" : [ 1 , 2 ] }  '
    res_check = proses_json(messy_json, mode="periksa")
    assert res_check["keluaran"]["teks"] == messy_json
    assert res_check["sah"] is True

    # 5. teks kosong -> 400 NO_TEXT
    for empty in ["", "   ", "\n\t  \n"]:
        try:
            proses_json(empty)
            assert False, "Harusnya melempar JsonToolError(NO_TEXT)"
        except JsonToolError as exc:
            assert exc.code == JT_NO_TEXT
            assert exc.status_code == 400

    # 6. bukan JSON ("halo dunia") -> 400 INVALID_JSON dan pesannya memuat "Baris"
    try:
        proses_json("halo dunia")
        assert False, "Harusnya melempar JsonToolError(INVALID_JSON)"
    except JsonToolError as exc:
        assert exc.code == JT_INVALID_JSON
        assert exc.status_code == 400
        assert "Baris" in exc.message
        assert exc.detail is not None
        assert "baris" in exc.detail and "kolom" in exc.detail and "offset" in exc.detail

    # 7. JSON terpotong (mis. '{"a": 1,') -> 400 INVALID_JSON
    try:
        proses_json('{"a": 1,')
        assert False, "Harusnya melempar JsonToolError(INVALID_JSON)"
    except JsonToolError as exc:
        assert exc.code == JT_INVALID_JSON
        assert exc.status_code == 400
        assert "Baris" in exc.message

    # 8. mode tidak dikenal -> 400 UNSUPPORTED_MODE; indent tidak dikenal -> 400 INVALID_INDENT
    try:
        proses_json('{"a": 1}', mode="acak")
        assert False, "Harusnya melempar JsonToolError(UNSUPPORTED_MODE)"
    except JsonToolError as exc:
        assert exc.code == JT_UNSUPPORTED_MODE
        assert exc.status_code == 400

    for bad_indent in [3, 8, "8", "spasi"]:
        try:
            proses_json('{"a": 1}', indent=bad_indent)
            assert False, f"Harusnya melempar JsonToolError(INVALID_INDENT) untuk {bad_indent}"
        except JsonToolError as exc:
            assert exc.code == JT_INVALID_INDENT
            assert exc.status_code == 400

    # 9. terlalu panjang (> MAX_CHARS) -> 413 TOO_LONG
    long_json = "[" + "1," * JT_MAX_CHARS + "1]"
    try:
        proses_json(long_json)
        assert False, "Harusnya melempar JsonToolError(TOO_LONG)"
    except JsonToolError as exc:
        assert exc.code == JT_TOO_LONG
        assert exc.status_code == 413

    # 10. JSON bersarang sangat dalam (> MAX_DEPTH) -> 400 TOO_DEEP (bukan 500)
    deep_json = "[" * (JT_MAX_DEPTH + 5) + "1" + "]" * (JT_MAX_DEPTH + 5)
    try:
        proses_json(deep_json)
        assert False, "Harusnya melempar JsonToolError(TOO_DEEP)"
    except JsonToolError as exc:
        assert exc.code == JT_TOO_DEEP
        assert exc.status_code == 400

    # 11. karakter non-ASCII (mis. {"nama":"Ayu — café"}) tetap utuh setelah rapikan (ensure_ascii=False)
    unicode_json = '{"nama":"Ayu — café"}'
    res_unicode = proses_json(unicode_json, mode="rapikan")
    assert "Ayu — café" in res_unicode["keluaran"]["teks"]
    assert r"\u" not in res_unicode["keluaran"]["teks"]

    # 12. limits_payload() -> 200 format
    limits = json_limits_payload_func()
    assert limits["max_bytes"] == JT_MAX_BYTES
    assert limits["max_chars"] == JT_MAX_CHARS
    assert isinstance(limits["modes"], list)
    assert len(limits["modes"]) == 3


def test_http_json_limits() -> None:
    client = _test_client()
    if client is None:
        return

    resp = client.get("/api/json/limits")
    assert resp.status_code == 200, resp.text
    assert "no-store" in resp.headers.get("Cache-Control", "")
    data = resp.json()
    assert data["max_bytes"] == JT_MAX_BYTES
    assert data["max_chars"] == JT_MAX_CHARS
    assert "max_mb" in data
    assert "max_depth" in data
    assert "modes" in data
    assert isinstance(data["modes"], list)
    assert len(data["modes"]) == 3
    assert data["processed_on"] == "server"


def test_http_json_modes_dan_sukses() -> None:
    client = _test_client()
    if client is None:
        return

    # rapikan indent 2
    resp_rapikan = client.post(
        "/api/json",
        data={"text": '{"b":1,"a":[1,2]}', "mode": "rapikan", "indent": "2"},
    )
    assert resp_rapikan.status_code == 200, resp_rapikan.text
    data_r = resp_rapikan.json()
    assert "\n" in data_r["keluaran"]["teks"]
    assert data_r["sah"] is True
    assert "no-store" in resp_rapikan.headers.get("Cache-Control", "")
    assert resp_rapikan.headers.get("Pragma") == "no-cache"
    assert "X-Processing-Ms" in resp_rapikan.headers

    # rapikan indent tab
    resp_tab = client.post(
        "/api/json",
        data={"text": '{"b":1,"a":[1,2]}', "mode": "rapikan", "indent": "tab"},
    )
    assert resp_tab.status_code == 200, resp_tab.text
    data_tab = resp_tab.json()
    lines_tab = data_tab["keluaran"]["teks"].splitlines()
    assert any(line.startswith("\t") for line in lines_tab)

    # urutkan_kunci=true
    resp_sort = client.post(
        "/api/json",
        data={
            "text": '{"b":1,"a":[1,2]}',
            "mode": "rapikan",
            "indent": "2",
            "urutkan_kunci": "true",
        },
    )
    assert resp_sort.status_code == 200, resp_sort.text
    out_sort = resp_sort.json()["keluaran"]["teks"]
    assert out_sort.find('"a"') < out_sort.find('"b"')

    # padatkan
    sample = '{\n  "b": 1,\n  "a": [1, 2]\n}'
    resp_padat = client.post(
        "/api/json",
        data={"text": sample, "mode": "padatkan"},
    )
    assert resp_padat.status_code == 200, resp_padat.text
    expected = json.dumps(json.loads(sample), separators=(",", ":"), ensure_ascii=False)
    assert resp_padat.json()["keluaran"]["teks"] == expected

    # periksa (teks tidak berubah)
    messy = '  {  "x" : 123  }  '
    resp_periksa = client.post(
        "/api/json",
        data={"text": messy, "mode": "periksa"},
    )
    assert resp_periksa.status_code == 200, resp_periksa.text
    assert resp_periksa.json()["keluaran"]["teks"] == messy

    # non-ASCII
    non_ascii = '{"nama":"Ayu — café"}'
    resp_na = client.post(
        "/api/json",
        data={"text": non_ascii, "mode": "rapikan"},
    )
    assert resp_na.status_code == 200, resp_na.text
    assert "Ayu — café" in resp_na.json()["keluaran"]["teks"]


def test_http_json_galat_dan_validasi() -> None:
    client = _test_client()
    if client is None:
        return

    # Field text kurang -> 400 INVALID_REQUEST
    resp_missing = client.post("/api/json", data={"mode": "rapikan"})
    assert resp_missing.status_code == 400, resp_missing.text
    assert resp_missing.json()["error"]["code"] == JT_INVALID_REQUEST

    # Teks kosong -> 400 NO_TEXT
    resp_empty = client.post("/api/json", data={"text": "   ", "mode": "rapikan"})
    assert resp_empty.status_code == 400, resp_empty.text
    assert resp_empty.json()["error"]["code"] == JT_NO_TEXT

    # Bukan JSON -> 400 INVALID_JSON dan pesan memuat "Baris"
    resp_invalid = client.post("/api/json", data={"text": "halo dunia", "mode": "rapikan"})
    assert resp_invalid.status_code == 400, resp_invalid.text
    err_inv = resp_invalid.json()["error"]
    assert err_inv["code"] == JT_INVALID_JSON
    assert "Baris" in err_inv["message"]
    assert "posisi" in err_inv
    assert "baris" in err_inv["posisi"]
    assert "kolom" in err_inv["posisi"]

    # JSON terpotong -> 400 INVALID_JSON
    resp_cut = client.post("/api/json", data={"text": '{"a": 1,', "mode": "rapikan"})
    assert resp_cut.status_code == 400, resp_cut.text
    assert resp_cut.json()["error"]["code"] == JT_INVALID_JSON

    # Mode tidak dikenal -> 400 UNSUPPORTED_MODE
    resp_bad_mode = client.post("/api/json", data={"text": '{"a": 1}', "mode": "aneh"})
    assert resp_bad_mode.status_code == 400, resp_bad_mode.text
    assert resp_bad_mode.json()["error"]["code"] == JT_UNSUPPORTED_MODE

    # Indent tidak dikenal -> 400 INVALID_INDENT
    resp_bad_indent = client.post("/api/json", data={"text": '{"a": 1}', "indent": "8"})
    assert resp_bad_indent.status_code == 400, resp_bad_indent.text
    assert resp_bad_indent.json()["error"]["code"] == JT_INVALID_INDENT

    # Terlalu panjang -> 413 TOO_LONG
    long_payload = "[" + "1," * JT_MAX_CHARS + "1]"
    resp_long = client.post("/api/json", data={"text": long_payload})
    assert resp_long.status_code == 413, resp_long.text
    assert resp_long.json()["error"]["code"] == JT_TOO_LONG

    # Bersarang sangat dalam -> 400 TOO_DEEP
    deep_payload = "[" * (JT_MAX_DEPTH + 10) + "1" + "]" * (JT_MAX_DEPTH + 10)
    resp_deep = client.post("/api/json", data={"text": deep_payload})
    assert resp_deep.status_code == 400, resp_deep.text
    assert resp_deep.json()["error"]["code"] == JT_TOO_DEEP

    # Bukan multipart/form-data -> 400 INVALID_REQUEST
    resp_bad_req = client.post("/api/json", json={"text": '{"a": 1}'})
    assert resp_bad_req.status_code == 400, resp_bad_req.text
    assert resp_bad_req.json()["error"]["code"] == JT_INVALID_REQUEST


def test_http_json_root_endpoint_dan_regresi() -> None:
    client = _test_client()
    if client is None:
        return

    # Root endpoint berisi "json"
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert "json" in root_data["tools"]
    assert "percent-calc" in root_data["tools"]

    # Regresi endpoint lain
    health_resp = client.get("/health")
    assert health_resp.status_code == 200

    pc_limits = client.get("/api/percent-calc/limits")
    assert pc_limits.status_code == 200


# --- Uji logika dan HTTP Kalkulator Tanggal (Date Calculator) -----------------
def test_date_calc_logika_murni() -> None:
    # 1. limits_payload memuat 4 mode, rentang tahun, dan today
    limits = date_calc_limits_payload_func()
    assert isinstance(limits["modes"], list)
    assert len(limits["modes"]) == 4
    assert limits["min_year"] == DC_MIN_YEAR
    assert limits["max_year"] == DC_MAX_YEAR
    assert "today" in limits
    assert isinstance(limits["today"], str) and len(limits["today"]) == 10
    assert limits["processed_on"] == "server"

    # 2. Aturan pembacaan tanggal (parse_date)
    # Spasi ujung dibuang
    d_clean = parse_date("  2026-09-28  ")
    assert d_clean.year == 2026 and d_clean.month == 9 and d_clean.day == 28

    # Format DD-MM-YYYY dan DD/MM/YYYY
    d_id = parse_date("28-09-2026")
    assert d_id.year == 2026 and d_id.month == 9 and d_id.day == 28
    d_slash = parse_date("28/09/2026")
    assert d_slash.year == 2026 and d_slash.month == 9 and d_slash.day == 28
    d_slash_ymd = parse_date("2026/09/28")
    assert d_slash_ymd.year == 2026 and d_slash_ymd.month == 9 and d_slash_ymd.day == 28

    # Pemisah campur -> 400 INVALID_DATE
    try:
        parse_date("2026-09/28")
        assert False, "Harusnya melempar INVALID_DATE"
    except DateCalcError as exc:
        assert exc.code == DC_INVALID_DATE
        assert exc.status_code == 400

    # Tahun 2 digit -> 400 INVALID_DATE
    try:
        parse_date("28-09-26")
        assert False, "Harusnya melempar INVALID_DATE"
    except DateCalcError as exc:
        assert exc.code == DC_INVALID_DATE
        assert exc.status_code == 400

    # Tanggal kabisat valid
    d_leap = parse_date("2024-02-29")
    assert d_leap.year == 2024 and d_leap.month == 2 and d_leap.day == 29

    # Tanggal kalender tidak valid (2026-02-30) -> 400 INVALID_DATE
    try:
        parse_date("2026-02-30")
        assert False, "Harusnya melempar INVALID_DATE"
    except DateCalcError as exc:
        assert exc.code == DC_INVALID_DATE
        assert exc.status_code == 400

    # Tanggal kosong -> 400 NO_DATE
    for empty in ["", "   "]:
        try:
            parse_date(empty)
            assert False, "Harusnya melempar NO_DATE"
        except DateCalcError as exc:
            assert exc.code == DC_NO_DATE
            assert exc.status_code == 400

    # Tahun di luar rentang (1899) -> 413 OUT_OF_RANGE
    try:
        parse_date("1899-12-31")
        assert False, "Harusnya melempar OUT_OF_RANGE"
    except DateCalcError as exc:
        assert exc.code == DC_OUT_OF_RANGE
        assert exc.status_code == 413
        assert "1900" in exc.message and "2100" in exc.message

    # Tahun 2101 -> 413 OUT_OF_RANGE
    try:
        parse_date("2101-01-01")
        assert False, "Harusnya melempar OUT_OF_RANGE"
    except DateCalcError as exc:
        assert exc.code == DC_OUT_OF_RANGE
        assert exc.status_code == 413

    # Spasi ujung dibuang LEBIH DULU, jadi masukan yang hanya panjang karena spasi tetap valid
    d_padded = parse_date("2026-09-28" + " " * 35)
    assert d_padded == date(2026, 9, 28)

    # Masukan lebih dari 40 karakter setelah dibersihkan -> 413 OUT_OF_RANGE
    try:
        parse_date("2026-09-28" + "9" * 31)
        assert False, "Harusnya melempar OUT_OF_RANGE"
    except DateCalcError as exc:
        assert exc.code == DC_OUT_OF_RANGE
        assert exc.status_code == 413

    # 3. Mode selisih
    # 1 Januari 2026 ke 31 Januari 2026 -> 30 hari
    res_selisih1 = compute_date("selisih", a="2026-01-01", b="2026-01-31")
    assert res_selisih1["hari"] == 30
    assert res_selisih1["hari_abs"] == 30
    assert res_selisih1["minggu"] == 4
    assert res_selisih1["hari_sisa"] == 2
    assert res_selisih1["hari_kerja"] == 22
    assert res_selisih1["akhir_pekan"] == 9
    assert res_selisih1["hari_kerja"] + res_selisih1["akhir_pekan"] == 31
    assert "catatan" in res_selisih1

    # 28 Februari 2024 ke 1 Maret 2024 -> 2 hari (tahun kabisat)
    res_selisih2 = compute_date("selisih", a="2024-02-28", b="2024-03-01")
    assert res_selisih2["hari"] == 2
    assert res_selisih2["hari_abs"] == 2
    assert res_selisih2["hari_kerja"] == 3
    assert res_selisih2["akhir_pekan"] == 0

    # Urutan terbalik -> nilai bertanda negatif
    res_selisih_rev = compute_date("selisih", a="2026-01-31", b="2026-01-01")
    assert res_selisih_rev["hari"] == -30
    assert res_selisih_rev["hari_abs"] == 30
    assert res_selisih_rev["hari_kerja"] == 22
    assert res_selisih_rev["akhir_pekan"] == 9

    # 4. Mode tambah_kurang
    # 31 Januari 2026 + 1 bulan -> 28 Februari 2026
    tk1 = compute_date("tambah_kurang", a="2026-01-31", amount=1, unit="bulan", direction="maju")
    assert tk1["tanggal_hasil"] == "2026-02-28"
    assert tk1["hari_hasil"] == "Sabtu"
    assert tk1["selisih_hari"] == 28

    # 31 Januari 2024 + 1 bulan -> 29 Februari 2024 (kabisat)
    tk2 = compute_date("tambah_kurang", a="2024-01-31", amount=1, unit="bulan", direction="maju")
    assert tk2["tanggal_hasil"] == "2024-02-29"
    assert tk2["hari_hasil"] == "Kamis"
    assert tk2["selisih_hari"] == 29

    # 1 Maret 2026 - 1 bulan -> 1 Februari 2026
    tk3 = compute_date("tambah_kurang", a="2026-03-01", amount=1, unit="bulan", direction="mundur")
    assert tk3["tanggal_hasil"] == "2026-02-01"
    assert tk3["hari_hasil"] == "Minggu"

    # 29 Februari 2024 + 1 tahun -> 28 Februari 2025
    tk4 = compute_date("tambah_kurang", a="2024-02-29", amount=1, unit="tahun", direction="maju")
    assert tk4["tanggal_hasil"] == "2025-02-28"
    assert tk4["hari_hasil"] == "Jumat"

    # + 2 minggu
    tk5 = compute_date("tambah_kurang", a="2026-01-01", amount=2, unit="minggu", direction="maju")
    assert tk5["tanggal_hasil"] == "2026-01-15"
    assert tk5["hari_hasil"] == "Kamis"
    assert tk5["selisih_hari"] == 14

    # 5. Mode hari_apa
    # 28 September 2026 -> Senin, hari ke tahun, pekan ISO
    ha1 = compute_date("hari_apa", a="2026-09-28")
    assert ha1["hari"] == "Senin"
    assert ha1["akhir_pekan"] is False
    assert "Senin, 28 September 2026" in ha1["tanggal_panjang"]
    assert ha1["hari_ke_tahun"] == 271
    assert ha1["sisa_hari_tahun"] == 94
    assert ha1["jumlah_hari_bulan"] == 30
    assert ha1["pekan_iso"] == 40

    # 26 September 2026 (Sabtu) -> akhir_pekan True
    ha2 = compute_date("hari_apa", a="2026-09-26")
    assert ha2["hari"] == "Sabtu"
    assert ha2["akhir_pekan"] is True

    # 6. Mode usia
    # 17 Agustus 1990 ke 17 Agustus 2026 -> 36 tahun 0 bulan 0 hari dan penanda Hari ini
    u1 = compute_date("usia", a="1990-08-17", b="2026-08-17")
    assert u1["tahun_bulan_hari"] == {"tahun": 36, "bulan": 0, "hari": 0}
    assert u1["ulang_tahun_berikutnya"]["berapa_hari_lagi"] == "Hari ini"

    # Tanggal acuan lebih awal dari tanggal lahir -> 400 INVALID_DATE
    try:
        compute_date("usia", a="2026-08-17", b="1990-08-17")
        assert False, "Harusnya melempar INVALID_DATE jika acuan lebih awal dari lahir"
    except DateCalcError as exc:
        assert exc.code == DC_INVALID_DATE
        assert exc.status_code == 400


def test_http_date_calc_limits() -> None:
    client = _test_client()
    if client is None:
        return

    resp = client.get("/api/date-calc/limits")
    assert resp.status_code == 200, resp.text
    assert "no-store" in resp.headers.get("Cache-Control", "")
    data = resp.json()
    assert isinstance(data["modes"], list)
    assert len(data["modes"]) == 4
    assert data["min_year"] == 1900
    assert data["max_year"] == 2100
    assert "today" in data
    assert isinstance(data["today"], str) and len(data["today"]) == 10
    assert data["processed_on"] == "server"


def test_http_date_calc_sukses() -> None:
    client = _test_client()
    if client is None:
        return

    # 1. Mode selisih
    resp_selisih = client.post(
        "/api/date-calc",
        data={"mode": "selisih", "a": "2026-01-01", "b": "2026-01-31"},
    )
    assert resp_selisih.status_code == 200, resp_selisih.text
    body_s = resp_selisih.json()
    assert body_s["hari"] == 30
    assert body_s["hari_abs"] == 30
    assert "no-store" in resp_selisih.headers.get("Cache-Control", "")
    assert resp_selisih.headers.get("Pragma") == "no-cache"
    assert "X-Processing-Ms" in resp_selisih.headers

    # 2. Mode tambah_kurang
    resp_tk = client.post(
        "/api/date-calc",
        data={
            "mode": "tambah_kurang",
            "a": "2026-01-31",
            "amount": "1",
            "unit": "bulan",
            "direction": "maju",
        },
    )
    assert resp_tk.status_code == 200, resp_tk.text
    assert resp_tk.json()["tanggal_hasil"] == "2026-02-28"

    # 3. Mode hari_apa
    resp_ha = client.post(
        "/api/date-calc",
        data={"mode": "hari_apa", "a": "2026-09-28"},
    )
    assert resp_ha.status_code == 200, resp_ha.text
    assert resp_ha.json()["hari"] == "Senin"

    # 4. Mode usia
    resp_usia = client.post(
        "/api/date-calc",
        data={"mode": "usia", "a": "1990-08-17", "b": "2026-08-17"},
    )
    assert resp_usia.status_code == 200, resp_usia.text
    assert resp_usia.json()["tahun_bulan_hari"]["tahun"] == 36


def test_http_date_calc_galat() -> None:
    client = _test_client()
    if client is None:
        return

    # Tanpa field mode -> 400 INVALID_REQUEST
    resp_no_mode = client.post("/api/date-calc", data={"a": "2026-01-01"})
    assert resp_no_mode.status_code == 400, resp_no_mode.text
    assert resp_no_mode.json()["error"]["code"] == DC_INVALID_REQUEST

    # Tanggal kosong -> 400 NO_DATE
    resp_empty = client.post("/api/date-calc", data={"mode": "selisih", "a": "   ", "b": "2026-01-31"})
    assert resp_empty.status_code == 400, resp_empty.text
    assert resp_empty.json()["error"]["code"] == DC_NO_DATE

    # 2026-02-30 -> 400 INVALID_DATE
    resp_inv_date = client.post("/api/date-calc", data={"mode": "hari_apa", "a": "2026-02-30"})
    assert resp_inv_date.status_code == 400, resp_inv_date.text
    assert resp_inv_date.json()["error"]["code"] == DC_INVALID_DATE

    # 2026-09/28 -> 400 INVALID_DATE
    resp_mixed = client.post("/api/date-calc", data={"mode": "hari_apa", "a": "2026-09/28"})
    assert resp_mixed.status_code == 400, resp_mixed.text
    assert resp_mixed.json()["error"]["code"] == DC_INVALID_DATE

    # Tahun 1899 -> 413 OUT_OF_RANGE
    resp_range = client.post("/api/date-calc", data={"mode": "hari_apa", "a": "1899-05-10"})
    assert resp_range.status_code == 413, resp_range.text
    assert resp_range.json()["error"]["code"] == DC_OUT_OF_RANGE

    # Mode tidak dikenal -> 400 UNSUPPORTED_MODE
    resp_bad_mode = client.post("/api/date-calc", data={"mode": "ngawur", "a": "2026-09-28"})
    assert resp_bad_mode.status_code == 400, resp_bad_mode.text
    assert resp_bad_mode.json()["error"]["code"] == DC_UNSUPPORTED_MODE

    # Satuan tidak dikenal -> 400 INVALID_UNIT
    resp_bad_unit = client.post(
        "/api/date-calc",
        data={"mode": "tambah_kurang", "a": "2026-09-28", "amount": "5", "unit": "abad"},
    )
    assert resp_bad_unit.status_code == 400, resp_bad_unit.text
    assert resp_bad_unit.json()["error"]["code"] == DC_INVALID_UNIT

    # Jumlah bukan angka -> 400 INVALID_AMOUNT
    resp_bad_amt = client.post(
        "/api/date-calc",
        data={"mode": "tambah_kurang", "a": "2026-09-28", "amount": "lima", "unit": "hari"},
    )
    assert resp_bad_amt.status_code == 400, resp_bad_amt.text
    assert resp_bad_amt.json()["error"]["code"] == DC_INVALID_AMOUNT

    # Body JSON (bukan multipart) -> 400
    resp_json = client.post(
        "/api/date-calc",
        json={"mode": "selisih", "a": "2026-01-01", "b": "2026-01-31"},
    )
    assert resp_json.status_code == 400, resp_json.text
    assert resp_json.json()["error"]["code"] == DC_INVALID_REQUEST


def test_http_date_calc_root_endpoint_dan_regresi() -> None:
    client = _test_client()
    if client is None:
        return

    # Root endpoint memuat date-calc
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert "date-calc" in root_data["tools"]
    assert "percent-calc" in root_data["tools"]
    assert "json" in root_data["tools"]

    # Regresi endpoint lain
    health_resp = client.get("/health")
    assert health_resp.status_code == 200

    pc_limits = client.get("/api/percent-calc/limits")
    assert pc_limits.status_code == 200

    json_limits = client.get("/api/json/limits")
    assert json_limits.status_code == 200


# --- Uji Hitung Mundur (Countdown Timer) -----------------------------------
def test_logika_countdown_ke_momen_maju() -> None:
    from datetime import datetime
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=CD_WIB)
    res = compute_countdown("ke_momen", tanggal="2026-01-05", jam="15:30", now=now)
    assert res["mode"] == "ke_momen"
    assert res["zona"] == "WIB (UTC+7)"
    assert res["server_now"] == "2026-01-01T12:00:00+07:00"
    assert res["target"] == "2026-01-05T15:30:00+07:00"
    assert res["lewat"] is False
    assert res["sisa_detik"] == 358200
    assert res["lewat_detik"] == 0
    assert res["hari"] == 4
    assert res["jam"] == 3
    assert res["menit"] == 30
    assert res["detik"] == 0
    assert res["total_jam"] == 99
    assert res["total_menit"] == 5970
    assert res["target_hari"] == "Senin"
    assert res["target_tanggal"] == "2026-01-05"
    assert res["target_jam"] == "15:30"
    assert res["target_tanggal_teks"] == "5 Januari 2026"
    assert res["target_label"] == "Senin, 5 Januari 2026, 15:30 WIB"
    assert res["sisa_teks"] == "4 hari 3 jam lagi"
    assert res["durasi_detik"] == 0
    assert "catatan" in res


def test_logika_countdown_ke_momen_lewat() -> None:
    from datetime import datetime
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=CD_WIB)
    res = compute_countdown("ke_momen", tanggal="2026-05-30", jam="10:00", now=now)
    assert res["mode"] == "ke_momen"
    assert res["lewat"] is True
    assert res["sisa_detik"] == 0
    assert res["lewat_detik"] == 180000
    assert res["hari"] == 0
    assert res["jam"] == 0
    assert res["menit"] == 0
    assert res["detik"] == 0
    assert res["total_jam"] == 0
    assert res["total_menit"] == 0
    assert res["sisa_teks"].startswith("sudah lewat")
    assert "Waktu ini sudah lewat" in res["catatan"]


def test_logika_countdown_ke_momen_sisa_nol() -> None:
    from datetime import datetime
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=CD_WIB)
    res = compute_countdown("ke_momen", tanggal="2026-01-01", jam="12:00", now=now)
    assert res["mode"] == "ke_momen"
    assert res["lewat"] is False
    assert res["sisa_detik"] == 0
    assert res["lewat_detik"] == 0
    assert res["sisa_teks"] == "kurang dari 1 detik lagi"


def test_logika_countdown_format_tanggal_dan_jam() -> None:
    from datetime import datetime
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=CD_WIB)

    # Format YYYY-MM-DD
    r1 = compute_countdown("ke_momen", tanggal="2026-12-31", jam="23:59", now=now)
    assert r1["target_tanggal"] == "2026-12-31"

    # Format DD-MM-YYYY
    r2 = compute_countdown("ke_momen", tanggal="31-12-2026", jam="23:59", now=now)
    assert r2["target_tanggal"] == "2026-12-31"

    # Format DD/MM/YYYY
    r3 = compute_countdown("ke_momen", tanggal="31/12/2026", jam="23:59", now=now)
    assert r3["target_tanggal"] == "2026-12-31"

    # Jam default kosong -> 00:00
    r4 = compute_countdown("ke_momen", tanggal="2026-12-31", jam=None, now=now)
    assert r4["target_jam"] == "00:00"

    # Pemisah campuran ditolak
    try:
        compute_countdown("ke_momen", tanggal="2026-12/31", now=now)
        assert False, "Harusnya gagal pemisah campuran"
    except CountdownError as exc:
        assert exc.code == CD_INVALID_DATE

    # Jam 6:5 ditolak
    try:
        compute_countdown("ke_momen", tanggal="2026-12-31", jam="6:5", now=now)
        assert False, "Harusnya gagal format jam 6:5"
    except CountdownError as exc:
        assert exc.code == CD_INVALID_TIME

    # Jam 24:00 ditolak
    try:
        compute_countdown("ke_momen", tanggal="2026-12-31", jam="24:00", now=now)
        assert False, "Harusnya gagal jam 24:00"
    except CountdownError as exc:
        assert exc.code == CD_INVALID_TIME

    # Tanggal 30 Februari ditolak
    try:
        compute_countdown("ke_momen", tanggal="2026-02-30", now=now)
        assert False, "Harusnya gagal tanggal 30 Februari"
    except CountdownError as exc:
        assert exc.code == CD_INVALID_DATE

    # Tahun 1899 ditolak
    try:
        compute_countdown("ke_momen", tanggal="1899-12-31", now=now)
        assert False, "Harusnya gagal tahun 1899"
    except CountdownError as exc:
        assert exc.code == CD_OUT_OF_RANGE

    # Tahun 2101 ditolak
    try:
        compute_countdown("ke_momen", tanggal="2101-01-01", now=now)
        assert False, "Harusnya gagal tahun 2101"
    except CountdownError as exc:
        assert exc.code == CD_OUT_OF_RANGE


def test_logika_countdown_dari_durasi() -> None:
    from datetime import datetime
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=CD_WIB)

    # 25 menit
    d_menit = compute_countdown("dari_durasi", jumlah=25, satuan="menit", now=now)
    assert d_menit["durasi_detik"] == 1500
    assert d_menit["total_menit"] == 25
    assert d_menit["menit"] == 25
    assert d_menit["jam"] == 0
    assert d_menit["hari"] == 0
    assert d_menit["sisa_detik"] == 1500

    # 2 jam
    d_jam = compute_countdown("dari_durasi", jumlah=2, satuan="jam", now=now)
    assert d_jam["durasi_detik"] == 7200
    assert d_jam["total_jam"] == 2
    assert d_jam["jam"] == 2

    # 3 hari
    d_hari = compute_countdown("dari_durasi", jumlah=3, satuan="hari", now=now)
    assert d_hari["durasi_detik"] == 259200
    assert d_hari["hari"] == 3

    # 1 minggu
    d_minggu = compute_countdown("dari_durasi", jumlah=1, satuan="minggu", now=now)
    assert d_minggu["durasi_detik"] == 604800
    assert d_minggu["hari"] == 7

    # Jumlah 0
    d_nol = compute_countdown("dari_durasi", jumlah=0, satuan="menit", now=now)
    assert d_nol["durasi_detik"] == 0
    assert d_nol["sisa_detik"] == 0
    assert d_nol["sisa_teks"] == "kurang dari 1 detik lagi"

    # Jumlah 100001 ditolak
    try:
        compute_countdown("dari_durasi", jumlah=100001, satuan="menit", now=now)
        assert False, "Harusnya gagal jumlah 100001"
    except CountdownError as exc:
        assert exc.code == CD_INVALID_AMOUNT

    # Satuan tidak dikenal ditolak
    try:
        compute_countdown("dari_durasi", jumlah=5, satuan="dekade", now=now)
        assert False, "Harusnya gagal satuan tidak dikenal"
    except CountdownError as exc:
        assert exc.code == CD_INVALID_UNIT

    # Mode tidak dikenal ditolak
    try:
        compute_countdown("ngawur", tanggal="2026-01-01", now=now)
        assert False, "Harusnya gagal mode tidak dikenal"
    except CountdownError as exc:
        assert exc.code == CD_UNSUPPORTED_MODE


def test_http_countdown_limits() -> None:
    client = _test_client()
    if client is None:
        return

    resp = client.get("/api/countdown/limits")
    assert resp.status_code == 200, resp.text
    assert "no-store" in resp.headers.get("Cache-Control", "")
    data = resp.json()
    assert data["tool"] == "countdown"
    assert data["zona"] == "WIB (UTC+7)"
    assert data["min_year"] == 1900
    assert data["max_year"] == 2100
    assert data["max_input_chars"] == 40
    assert data["max_bytes"] == 65536
    assert data["default_jam"] == "00:00"
    assert isinstance(data["modes"], list)
    assert len(data["modes"]) == 2
    assert isinstance(data["satuan"], list)
    assert len(data["satuan"]) == 4
    assert [s["id"] for s in data["satuan"]] == ["menit", "jam", "hari", "minggu"]


def test_http_countdown_sukses() -> None:
    client = _test_client()
    if client is None:
        return

    # 1. Mode ke_momen
    resp_momen = client.post(
        "/api/countdown",
        data={"mode": "ke_momen", "tanggal": "2099-12-31", "jam": "23:59"},
    )
    assert resp_momen.status_code == 200, resp_momen.text
    body_m = resp_momen.json()
    assert body_m["mode"] == "ke_momen"
    assert body_m["target_tanggal"] == "2099-12-31"
    assert body_m["target_jam"] == "23:59"
    assert body_m["lewat"] is False
    assert body_m["sisa_detik"] > 0
    assert "no-store" in resp_momen.headers.get("Cache-Control", "")
    assert resp_momen.headers.get("Pragma") == "no-cache"
    assert "X-Processing-Ms" in resp_momen.headers

    # 2. Mode dari_durasi
    resp_durasi = client.post(
        "/api/countdown",
        data={"mode": "dari_durasi", "jumlah": "45", "satuan": "menit"},
    )
    assert resp_durasi.status_code == 200, resp_durasi.text
    body_d = resp_durasi.json()
    assert body_d["mode"] == "dari_durasi"
    assert body_d["durasi_detik"] == 2700
    assert body_d["total_menit"] == 45


def test_http_countdown_galat() -> None:
    client = _test_client()
    if client is None:
        return

    # Tanpa field mode -> 400 INVALID_REQUEST
    resp_no_mode = client.post("/api/countdown", data={"tanggal": "2026-12-31"})
    assert resp_no_mode.status_code == 400, resp_no_mode.text
    assert resp_no_mode.json()["error"]["code"] == CD_INVALID_REQUEST

    # Mode ke_momen tanggal kosong -> 400 NO_DATE
    resp_no_date = client.post("/api/countdown", data={"mode": "ke_momen", "tanggal": "   "})
    assert resp_no_date.status_code == 400, resp_no_date.text
    assert resp_no_date.json()["error"]["code"] == CD_NO_DATE

    # 2026-02-30 -> 400 INVALID_DATE
    resp_inv_date = client.post("/api/countdown", data={"mode": "ke_momen", "tanggal": "2026-02-30"})
    assert resp_inv_date.status_code == 400, resp_inv_date.text
    assert resp_inv_date.json()["error"]["code"] == CD_INVALID_DATE

    # Pemisah campuran -> 400 INVALID_DATE
    resp_mixed = client.post("/api/countdown", data={"mode": "ke_momen", "tanggal": "2026-12/31"})
    assert resp_mixed.status_code == 400, resp_mixed.text
    assert resp_mixed.json()["error"]["code"] == CD_INVALID_DATE

    # Tahun 1899 -> 400 OUT_OF_RANGE
    resp_range_low = client.post("/api/countdown", data={"mode": "ke_momen", "tanggal": "1899-01-01"})
    assert resp_range_low.status_code == 400, resp_range_low.text
    assert resp_range_low.json()["error"]["code"] == CD_OUT_OF_RANGE

    # Tahun 2101 -> 400 OUT_OF_RANGE
    resp_range_high = client.post("/api/countdown", data={"mode": "ke_momen", "tanggal": "2101-01-01"})
    assert resp_range_high.status_code == 400, resp_range_high.text
    assert resp_range_high.json()["error"]["code"] == CD_OUT_OF_RANGE

    # Format jam 6:5 -> 400 INVALID_TIME
    resp_time_short = client.post("/api/countdown", data={"mode": "ke_momen", "tanggal": "2026-12-31", "jam": "6:5"})
    assert resp_time_short.status_code == 400, resp_time_short.text
    assert resp_time_short.json()["error"]["code"] == CD_INVALID_TIME

    # Jam 24:00 -> 400 INVALID_TIME
    resp_time_24 = client.post("/api/countdown", data={"mode": "ke_momen", "tanggal": "2026-12-31", "jam": "24:00"})
    assert resp_time_24.status_code == 400, resp_time_24.text
    assert resp_time_24.json()["error"]["code"] == CD_INVALID_TIME

    # Mode tidak dikenal -> 400 UNSUPPORTED_MODE
    resp_bad_mode = client.post("/api/countdown", data={"mode": "tidak_ada", "tanggal": "2026-12-31"})
    assert resp_bad_mode.status_code == 400, resp_bad_mode.text
    assert resp_bad_mode.json()["error"]["code"] == CD_UNSUPPORTED_MODE

    # Satuan tidak dikenal -> 400 INVALID_UNIT
    resp_bad_unit = client.post(
        "/api/countdown",
        data={"mode": "dari_durasi", "jumlah": "10", "satuan": "abad"},
    )
    assert resp_bad_unit.status_code == 400, resp_bad_unit.text
    assert resp_bad_unit.json()["error"]["code"] == CD_INVALID_UNIT

    # Jumlah bukan angka -> 400 INVALID_AMOUNT
    resp_bad_amt = client.post(
        "/api/countdown",
        data={"mode": "dari_durasi", "jumlah": "sepuluh", "satuan": "menit"},
    )
    assert resp_bad_amt.status_code == 400, resp_bad_amt.text
    assert resp_bad_amt.json()["error"]["code"] == CD_INVALID_AMOUNT

    # Jumlah 100001 -> 400 INVALID_AMOUNT
    resp_amt_high = client.post(
        "/api/countdown",
        data={"mode": "dari_durasi", "jumlah": "100001", "satuan": "menit"},
    )
    assert resp_amt_high.status_code == 400, resp_amt_high.text
    assert resp_amt_high.json()["error"]["code"] == CD_INVALID_AMOUNT

    # Body JSON (bukan multipart) -> 400
    resp_json = client.post(
        "/api/countdown",
        json={"mode": "ke_momen", "tanggal": "2026-12-31"},
    )
    assert resp_json.status_code == 400, resp_json.text
    assert resp_json.json()["error"]["code"] == CD_INVALID_REQUEST

    # Body > 64 KB -> 413 PAYLOAD_TOO_LARGE
    resp_large = client.post(
        "/api/countdown",
        data={"mode": "ke_momen", "tanggal": "2026-12-31", "ekstra": "x" * 70000},
    )
    assert resp_large.status_code == 413, resp_large.text
    assert resp_large.json()["error"]["code"] == CD_PAYLOAD_TOO_LARGE


def test_http_countdown_root_endpoint_dan_regresi() -> None:
    client = _test_client()
    if client is None:
        return

    # Root endpoint memuat countdown
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert "countdown" in root_data["tools"]
    assert "date-calc" in root_data["tools"]


# --- Uji QR & Barcode Generator ---------------------------------------------
def test_logika_qr_dan_barcode() -> None:
    """Uji logika murni pembuatan kode QR dan barcode."""
    # Validasi masukan dasar
    try:
        generate_code(teks="   ")
        raise AssertionError("Seharusnya galat teks kosong")
    except QrToolError as exc:
        assert exc.code == QR_NO_TEXT
        assert exc.status_code == 400

    try:
        generate_code(teks="A" * 1201, mode="qr")
        raise AssertionError("Seharusnya galat teks QR terlalu panjang")
    except QrToolError as exc:
        assert exc.code == QR_TEXT_TOO_LONG
        assert exc.status_code == 400

    try:
        generate_code(teks="A" * 81, mode="barcode")
        raise AssertionError("Seharusnya galat teks barcode terlalu panjang")
    except QrToolError as exc:
        assert exc.code == QR_TEXT_TOO_LONG
        assert exc.status_code == 400

    try:
        generate_code(teks="Halo", ukuran=999)
        raise AssertionError("Seharusnya galat ukuran")
    except QrToolError as exc:
        assert exc.code == QR_INVALID_SIZE
        assert exc.status_code == 400

    try:
        generate_code(teks="Halo", mode="pdf")
        raise AssertionError("Seharusnya galat mode")
    except QrToolError as exc:
        assert exc.code == QR_UNSUPPORTED_KIND
        assert exc.status_code == 400

    try:
        generate_code(teks="Halo", mode="qr", koreksi="Z")
        raise AssertionError("Seharusnya galat koreksi")
    except QrToolError as exc:
        assert exc.code == QR_INVALID_CORRECTION
        assert exc.status_code == 400

    try:
        generate_code(teks="halo dunia 😀", mode="barcode")
        raise AssertionError("Seharusnya galat karakter non-latin barcode")
    except QrToolError as exc:
        assert exc.code == QR_NOT_ENCODABLE
        assert exc.status_code == 400

    # Sukses QR
    res_qr = generate_code(mode="qr", teks="https://bahzi.fun", ukuran=512, koreksi="M")
    assert isinstance(res_qr, QrResult)
    assert res_qr.content.startswith(b"\x89PNG")
    assert res_qr.mode == "qr"
    assert res_qr.pixels == "512x512"

    # Sukses Barcode
    res_bc = generate_code(mode="barcode", teks="12345678", ukuran=512)
    assert isinstance(res_bc, QrResult)
    assert res_bc.content.startswith(b"\x89PNG")
    assert res_bc.mode == "barcode"


def test_http_qr_limits() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.get("/api/qr/limits")
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    data = resp.json()
    assert data["tool"] == "qr"
    assert data["teks_maks_qr"] == 1200
    assert data["teks_maks_barcode"] == 80
    assert data["ukuran"] == [256, 384, 512, 768, 1024]
    assert data["ukuran_bawaan"] == 512
    assert "qr" in data["mode"] and "barcode" in data["mode"]
    assert "Code 128" in data["jenis_barcode"]
    assert len(data["koreksi"]) == 4
    koreksi_values = [k["nilai"] for k in data["koreksi"]]
    assert koreksi_values == ["L", "M", "Q", "H"]
    assert "catatan" in data


def test_http_qr_sukses() -> None:
    client = _test_client()
    if client is None:
        return

    # QR teks pendek
    resp_qr = client.post("/api/qr", data={"teks": "Halo Dunia", "mode": "qr"})
    assert resp_qr.status_code == 200
    assert resp_qr.headers["content-type"] == "image/png"
    assert resp_qr.content.startswith(b"\x89PNG")
    assert resp_qr.headers["x-qr-mode"] == "qr"
    assert resp_qr.headers["x-qr-pixels"] == "512x512"
    assert "x-qr-bytes" in resp_qr.headers
    assert "x-processing-ms" in resp_qr.headers
    assert "no-store" in resp_qr.headers.get("cache-control", "")

    # QR teks panjang (900 karakter)
    long_text = "OmniTools 2026 QR Generator " * 32
    resp_long = client.post("/api/qr", data={"teks": long_text, "mode": "qr", "ukuran": "1024", "koreksi": "L"})
    assert resp_long.status_code == 200
    assert resp_long.headers["content-type"] == "image/png"
    assert resp_long.content.startswith(b"\x89PNG")

    # Barcode Code 128
    resp_bc = client.post("/api/qr", data={"teks": "12345678", "mode": "barcode", "ukuran": "512"})
    assert resp_bc.status_code == 200
    assert resp_bc.headers["content-type"] == "image/png"
    assert resp_bc.content.startswith(b"\x89PNG")
    assert resp_bc.headers["x-qr-mode"] == "barcode"


def test_http_qr_galat() -> None:
    client = _test_client()
    if client is None:
        return

    # Teks kosong / spasi saja -> 400 NO_TEXT
    resp_empty = client.post("/api/qr", data={"teks": "   "})
    assert resp_empty.status_code == 400
    assert resp_empty.json()["error"]["code"] == QR_NO_TEXT

    # Teks 1.201 karakter -> 400 TEXT_TOO_LONG
    resp_long_qr = client.post("/api/qr", data={"teks": "A" * 1201, "mode": "qr"})
    assert resp_long_qr.status_code == 400
    assert resp_long_qr.json()["error"]["code"] == QR_TEXT_TOO_LONG

    # Barcode 81 karakter -> 400 TEXT_TOO_LONG
    resp_long_bc = client.post("/api/qr", data={"teks": "A" * 81, "mode": "barcode"})
    assert resp_long_bc.status_code == 400
    assert resp_long_bc.json()["error"]["code"] == QR_TEXT_TOO_LONG

    # Ukuran tidak dikenal (999) -> 400 INVALID_SIZE
    resp_inv_size = client.post("/api/qr", data={"teks": "Test", "ukuran": "999"})
    assert resp_inv_size.status_code == 400
    assert resp_inv_size.json()["error"]["code"] == QR_INVALID_SIZE

    # Mode tidak dikenal ("pdf") -> 400 UNSUPPORTED_KIND
    resp_inv_mode = client.post("/api/qr", data={"teks": "Test", "mode": "pdf"})
    assert resp_inv_mode.status_code == 400
    assert resp_inv_mode.json()["error"]["code"] == QR_UNSUPPORTED_KIND

    # Koreksi tidak dikenal ("Z") -> 400 INVALID_CORRECTION
    resp_inv_ec = client.post("/api/qr", data={"teks": "Test", "mode": "qr", "koreksi": "Z"})
    assert resp_inv_ec.status_code == 400
    assert resp_inv_ec.json()["error"]["code"] == QR_INVALID_CORRECTION

    # Barcode non-latin ("halo dunia 😀") -> 400 NOT_ENCODABLE
    resp_not_enc = client.post("/api/qr", data={"teks": "halo dunia 😀", "mode": "barcode"})
    assert resp_not_enc.status_code == 400
    assert resp_not_enc.json()["error"]["code"] == QR_NOT_ENCODABLE

    # Format JSON bukan multipart -> 400 INVALID_REQUEST
    resp_json = client.post("/api/qr", json={"teks": "Test"})
    assert resp_json.status_code == 400
    assert resp_json.json()["error"]["code"] == QR_INVALID_REQUEST

    # Badan > 16 KB -> 413 PAYLOAD_TOO_LARGE
    resp_large = client.post("/api/qr", data={"teks": "Test", "extra": "x" * 20000})
    assert resp_large.status_code == 413
    assert resp_large.json()["error"]["code"] == QR_PAYLOAD_TOO_LARGE


def test_qr_dan_barcode_terbaca_zxing() -> None:
    """Pastikan keluaran gambar QR dan barcode benar-benar bisa dibaca ulang ke teks aslinya."""
    try:
        import pytest
        zxingcpp = pytest.importorskip("zxingcpp")
    except ImportError:
        try:
            import zxingcpp
        except ImportError:
            SKIPPED.append("uji dekode zxingcpp dilewati: pustaka zxingcpp tidak terpasang")
            return

    # Uji pembacaan kode QR
    qr_cases = [
        "https://bahzi.fun/omnitools",
        "Halo dunia dengan emoji 🚀 dan baris\nbaru",
        "Teks panjang " * 40,
    ]
    for text in qr_cases:
        res = generate_code(mode="qr", teks=text, ukuran=512, koreksi="M")
        img = Image.open(io.BytesIO(res.content))
        decoded = zxingcpp.read_barcodes(img)
        assert len(decoded) == 1, f"QR gagal dibaca untuk: {text[:30]}"
        assert decoded[0].text == text.strip()

    # Uji pembacaan barcode Code 128
    barcode_cases = [
        "ABC-12345-XYZ",
        "0123456789",
        "OmniTools-2026",
    ]
    for text in barcode_cases:
        res = generate_code(mode="barcode", teks=text, ukuran=512)
        img = Image.open(io.BytesIO(res.content))
        decoded = zxingcpp.read_barcodes(img)
        assert len(decoded) == 1, f"Barcode gagal dibaca untuk: {text}"
        assert decoded[0].text == text


def test_http_qr_root_endpoint_dan_regresi() -> None:
    client = _test_client()
    if client is None:
        return

    # Root endpoint memuat qr
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert "qr" in root_data["tools"]
    assert "countdown" in root_data["tools"]


# --- Uji Image Editor -------------------------------------------------------
def test_logika_murni_image_edit() -> None:
    """Uji logika murni edit_image: rotasi, balik, potong rasio, dan format."""
    # 1. Normalisasi
    assert edit_normalize_rotate(0) == 0
    assert edit_normalize_rotate("90") == 90
    assert edit_normalize_rotate("180") == 180
    assert edit_normalize_rotate("270") == 270
    expect_image_edit_error(lambda: edit_normalize_rotate("45"), EDIT_UNSUPPORTED_ROTATE, 400)

    assert edit_normalize_flip("tidak") == "tidak"
    assert edit_normalize_flip("horizontal") == "horizontal"
    assert edit_normalize_flip("vertikal") == "vertikal"
    expect_image_edit_error(lambda: edit_normalize_flip("miring"), EDIT_UNSUPPORTED_FLIP, 400)

    assert edit_normalize_ratio("bebas") == "bebas"
    assert edit_normalize_ratio("16:9") == "16:9"
    expect_image_edit_error(lambda: edit_normalize_ratio("21:9"), EDIT_UNSUPPORTED_RATIO, 400)

    assert edit_normalize_anchor("tengah") == "tengah"
    assert edit_normalize_anchor("atas") == "atas"
    expect_image_edit_error(lambda: edit_normalize_anchor("pojok"), EDIT_UNSUPPORTED_ANCHOR, 400)

    assert edit_normalize_orientation("ya") is True
    assert edit_normalize_orientation("tidak") is False
    expect_image_edit_error(lambda: edit_normalize_orientation("maybe"), EDIT_INVALID_BOOLEAN, 400)

    assert edit_normalize_target("tetap") == "tetap"
    assert edit_normalize_target("jpeg") == "jpeg"
    assert edit_normalize_target("jpg") == "jpeg"
    assert edit_normalize_target("png") == "png"
    assert edit_normalize_target("webp") == "webp"
    expect_image_edit_error(lambda: edit_normalize_target("bmp"), EDIT_UNSUPPORTED_TARGET, 400)

    assert edit_normalize_quality(90) == 90
    assert edit_normalize_quality("80") == 80
    expect_image_edit_error(lambda: edit_normalize_quality("abc"), EDIT_INVALID_QUALITY, 400)
    expect_image_edit_error(lambda: edit_normalize_quality(5), EDIT_INVALID_QUALITY, 400)
    expect_image_edit_error(lambda: edit_normalize_quality(105), EDIT_INVALID_QUALITY, 400)

    # 2. Pemotongan rasio murni
    img_wide = Image.new("RGB", (100, 50))
    res_kiri = edit_crop_to_ratio(img_wide, "1:1", "kiri")
    assert res_kiri.size == (50, 50)
    res_kanan = edit_crop_to_ratio(img_wide, "1:1", "kanan")
    assert res_kanan.size == (50, 50)
    res_tengah = edit_crop_to_ratio(img_wide, "1:1", "tengah")
    assert res_tengah.size == (50, 50)

    img_tall = Image.new("RGB", (50, 100))
    res_atas = edit_crop_to_ratio(img_tall, "1:1", "atas")
    assert res_atas.size == (50, 50)
    res_bawah = edit_crop_to_ratio(img_tall, "1:1", "bawah")
    assert res_bawah.size == (50, 50)
    res_tengah_tall = edit_crop_to_ratio(img_tall, "1:1", "tengah")
    assert res_tengah_tall.size == (50, 50)

    # 3. Putar & balik murni
    png_data = make_image("PNG", size=(60, 40), color="blue")
    res_rot90 = edit_image(png_data, putar=90)
    assert (res_rot90.width, res_rot90.height) == (40, 60)

    res_rot180 = edit_image(png_data, putar=180)
    assert (res_rot180.width, res_rot180.height) == (60, 40)

    res_rot270 = edit_image(png_data, putar=270)
    assert (res_rot270.width, res_rot270.height) == (40, 60)

    res_flip_h = edit_image(png_data, balik="horizontal")
    assert (res_flip_h.width, res_flip_h.height) == (60, 40)

    res_flip_v = edit_image(png_data, balik="vertikal")
    assert (res_flip_v.width, res_flip_v.height) == (60, 40)


def test_http_image_edit_limits() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.get("/api/image/edit/limits")
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    data = resp.json()
    assert data["max_mb"] == 15
    assert data["max_pixels"] == EDIT_MAX_PIXELS
    assert data["quality_min"] == 10
    assert data["quality_max"] == 100
    assert data["quality_default"] == 90
    assert "putar_options" in data
    assert "balik_options" in data
    assert "rasio_options" in data
    assert "patokan_options" in data
    assert "orientasi_options" in data
    assert "format_options" in data
    assert "defaults" in data
    assert data["defaults"]["putar"] == 0
    assert data["defaults"]["balik"] == "tidak"
    assert data["defaults"]["rasio"] == "bebas"
    assert data["defaults"]["patokan"] == "tengah"
    assert data["defaults"]["orientasi"] == "ya"
    assert data["defaults"]["format"] == "tetap"
    assert data["defaults"]["kualitas"] == 90


def test_http_image_edit_sukses_putar_dan_balik() -> None:
    client = _test_client()
    if client is None:
        return
    png_data = make_image("PNG", size=(60, 40), color="blue")

    # Putar 90
    resp_90 = client.post(
        "/api/image/edit",
        files={"file": ("foto.png", png_data, "image/png")},
        data={"putar": "90"},
    )
    assert resp_90.status_code == 200, resp_90.text
    assert resp_90.headers["content-type"] == "image/png"
    assert 'filename="hasil-edit.png"' in resp_90.headers["content-disposition"]
    assert "no-store" in resp_90.headers.get("cache-control", "")
    assert resp_90.headers["x-input-format"] == "png"
    assert resp_90.headers["x-output-format"] == "png"
    assert resp_90.headers["x-pixels"] == str(40 * 60)
    assert resp_90.headers["x-image-width"] == "40"
    assert resp_90.headers["x-image-height"] == "60"
    img_90 = Image.open(io.BytesIO(resp_90.content))
    assert img_90.size == (40, 60)

    # Putar 180
    resp_180 = client.post(
        "/api/image/edit",
        files={"file": ("foto.png", png_data, "image/png")},
        data={"putar": "180"},
    )
    assert resp_180.status_code == 200
    img_180 = Image.open(io.BytesIO(resp_180.content))
    assert img_180.size == (60, 40)

    # Putar 270
    resp_270 = client.post(
        "/api/image/edit",
        files={"file": ("foto.png", png_data, "image/png")},
        data={"putar": "270"},
    )
    assert resp_270.status_code == 200
    img_270 = Image.open(io.BytesIO(resp_270.content))
    assert img_270.size == (40, 60)

    # Balik horizontal & vertikal
    resp_flip_h = client.post(
        "/api/image/edit",
        files={"file": ("foto.png", png_data, "image/png")},
        data={"balik": "horizontal"},
    )
    assert resp_flip_h.status_code == 200
    assert Image.open(io.BytesIO(resp_flip_h.content)).size == (60, 40)

    resp_flip_v = client.post(
        "/api/image/edit",
        files={"file": ("foto.png", png_data, "image/png")},
        data={"balik": "vertikal"},
    )
    assert resp_flip_v.status_code == 200
    assert Image.open(io.BytesIO(resp_flip_v.content)).size == (60, 40)


def test_http_image_edit_sukses_potong_rasio_dan_patokan() -> None:
    client = _test_client()
    if client is None:
        return

    # Gambar lanskap 100x50 dipotong rasio 1:1 (harus jadi 50x50)
    png_wide = make_image("PNG", size=(100, 50), color="green")
    for anchor in ("kiri", "tengah", "kanan", "atas", "bawah"):
        resp = client.post(
            "/api/image/edit",
            files={"file": ("wide.png", png_wide, "image/png")},
            data={"rasio": "1:1", "patokan": anchor},
        )
        assert resp.status_code == 200, resp.text
        img_res = Image.open(io.BytesIO(resp.content))
        assert img_res.size == (50, 50), f"Gagal pada anchor {anchor}: {img_res.size}"

    # Gambar potret 50x100 dipotong rasio 1:1 (harus jadi 50x50)
    png_tall = make_image("PNG", size=(50, 100), color="yellow")
    for anchor in ("atas", "tengah", "bawah", "kiri", "kanan"):
        resp = client.post(
            "/api/image/edit",
            files={"file": ("tall.png", png_tall, "image/png")},
            data={"rasio": "1:1", "patokan": anchor},
        )
        assert resp.status_code == 200, resp.text
        img_res = Image.open(io.BytesIO(resp.content))
        assert img_res.size == (50, 50), f"Gagal pada anchor {anchor}: {img_res.size}"

    # Rasio 16:9 pada 160x100 -> tinggi 90
    png_169 = make_image("PNG", size=(160, 100), color="purple")
    resp_169 = client.post(
        "/api/image/edit",
        files={"file": ("test.png", png_169, "image/png")},
        data={"rasio": "16:9"},
    )
    assert resp_169.status_code == 200
    assert Image.open(io.BytesIO(resp_169.content)).size == (160, 90)

    # Rasio 9:16 pada 100x160 -> lebar 90
    png_916 = make_image("PNG", size=(100, 160), color="red")
    resp_916 = client.post(
        "/api/image/edit",
        files={"file": ("test.png", png_916, "image/png")},
        data={"rasio": "9:16"},
    )
    assert resp_916.status_code == 200
    assert Image.open(io.BytesIO(resp_916.content)).size == (90, 160)


def test_http_image_edit_sukses_format_tujuan() -> None:
    client = _test_client()
    if client is None:
        return
    png_data = make_image("PNG", size=(50, 50), color="red")
    jpeg_data = make_image("JPEG", size=(50, 50), color="blue")
    webp_data = make_image("WEBP", size=(50, 50), color="green")

    # format: tetap
    resp_png_tetap = client.post("/api/image/edit", files={"file": ("a.png", png_data, "image/png")}, data={"format": "tetap"})
    assert resp_png_tetap.status_code == 200
    assert resp_png_tetap.headers["content-type"] == "image/png"
    assert 'filename="hasil-edit.png"' in resp_png_tetap.headers["content-disposition"]

    resp_jpg_tetap = client.post("/api/image/edit", files={"file": ("b.jpg", jpeg_data, "image/jpeg")}, data={"format": "tetap"})
    assert resp_jpg_tetap.status_code == 200
    assert resp_jpg_tetap.headers["content-type"] == "image/jpeg"
    assert 'filename="hasil-edit.jpg"' in resp_jpg_tetap.headers["content-disposition"]

    resp_webp_tetap = client.post("/api/image/edit", files={"file": ("c.webp", webp_data, "image/webp")}, data={"format": "tetap"})
    assert resp_webp_tetap.status_code == 200
    assert resp_webp_tetap.headers["content-type"] == "image/webp"
    assert 'filename="hasil-edit.webp"' in resp_webp_tetap.headers["content-disposition"]

    # konversi ke JPEG dengan kualitas
    resp_to_jpeg = client.post(
        "/api/image/edit",
        files={"file": ("a.png", png_data, "image/png")},
        data={"format": "jpeg", "kualitas": "75"},
    )
    assert resp_to_jpeg.status_code == 200
    assert resp_to_jpeg.headers["content-type"] == "image/jpeg"
    assert resp_to_jpeg.content.startswith(b"\xff\xd8\xff")

    # konversi ke PNG
    resp_to_png = client.post(
        "/api/image/edit",
        files={"file": ("b.jpg", jpeg_data, "image/jpeg")},
        data={"format": "png"},
    )
    assert resp_to_png.status_code == 200
    assert resp_to_png.headers["content-type"] == "image/png"
    assert resp_to_png.content.startswith(b"\x89PNG")

    # konversi ke WebP
    resp_to_webp = client.post(
        "/api/image/edit",
        files={"file": ("a.png", png_data, "image/png")},
        data={"format": "webp", "kualitas": "85"},
    )
    assert resp_to_webp.status_code == 200
    assert resp_to_webp.headers["content-type"] == "image/webp"


def test_http_image_edit_galat_not_image_dan_empty_file() -> None:
    client = _test_client()
    if client is None:
        return

    # Bukan gambar -> 400 NOT_IMAGE
    resp_not = client.post(
        "/api/image/edit",
        files={"file": ("test.png", b"ini file teks yang dinamai .png", "image/png")},
    )
    assert resp_not.status_code == 400
    assert resp_not.json()["error"]["code"] == EDIT_NOT_IMAGE

    # SVG tidak didukung di Image Editor -> 400 NOT_IMAGE
    svg_data = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
    resp_svg = client.post(
        "/api/image/edit",
        files={"file": ("test.svg", svg_data, "image/svg+xml")},
    )
    assert resp_svg.status_code == 400
    assert resp_svg.json()["error"]["code"] == EDIT_NOT_IMAGE

    # Berkas kosong -> 400 EMPTY_FILE
    resp_empty = client.post(
        "/api/image/edit",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert resp_empty.status_code == 400
    assert resp_empty.json()["error"]["code"] == EDIT_EMPTY_FILE


def test_http_image_edit_galat_invalid_request() -> None:
    client = _test_client()
    if client is None:
        return

    # Tanpa field file
    resp_no_file = client.post("/api/image/edit", data={"putar": "0"})
    assert resp_no_file.status_code == 400
    assert resp_no_file.json()["error"]["code"] == EDIT_INVALID_REQUEST

    # Permintaan JSON bukan multipart
    resp_json = client.post("/api/image/edit", json={"putar": "0"})
    assert resp_json.status_code == 400
    assert resp_json.json()["error"]["code"] == EDIT_INVALID_REQUEST


def test_http_image_edit_galat_parameter() -> None:
    client = _test_client()
    if client is None:
        return
    png_data = make_image("PNG")

    # UNSUPPORTED_ROTATE
    resp_rot = client.post("/api/image/edit", files={"file": ("a.png", png_data, "image/png")}, data={"putar": "45"})
    assert resp_rot.status_code == 400
    assert resp_rot.json()["error"]["code"] == EDIT_UNSUPPORTED_ROTATE

    # UNSUPPORTED_FLIP
    resp_flip = client.post("/api/image/edit", files={"file": ("a.png", png_data, "image/png")}, data={"balik": "diagonal"})
    assert resp_flip.status_code == 400
    assert resp_flip.json()["error"]["code"] == EDIT_UNSUPPORTED_FLIP

    # UNSUPPORTED_RATIO
    resp_ratio = client.post("/api/image/edit", files={"file": ("a.png", png_data, "image/png")}, data={"rasio": "21:9"})
    assert resp_ratio.status_code == 400
    assert resp_ratio.json()["error"]["code"] == EDIT_UNSUPPORTED_RATIO

    # UNSUPPORTED_ANCHOR
    resp_anchor = client.post("/api/image/edit", files={"file": ("a.png", png_data, "image/png")}, data={"rasio": "1:1", "patokan": "pojok"})
    assert resp_anchor.status_code == 400
    assert resp_anchor.json()["error"]["code"] == EDIT_UNSUPPORTED_ANCHOR

    # INVALID_BOOLEAN
    resp_bool = client.post("/api/image/edit", files={"file": ("a.png", png_data, "image/png")}, data={"orientasi": "mungkin"})
    assert resp_bool.status_code == 400
    assert resp_bool.json()["error"]["code"] == EDIT_INVALID_BOOLEAN

    # UNSUPPORTED_TARGET
    resp_target = client.post("/api/image/edit", files={"file": ("a.png", png_data, "image/png")}, data={"format": "gif"})
    assert resp_target.status_code == 400
    assert resp_target.json()["error"]["code"] == EDIT_UNSUPPORTED_TARGET

    # INVALID_QUALITY (bukan angka, < 10, > 100)
    resp_q_str = client.post("/api/image/edit", files={"file": ("a.png", png_data, "image/png")}, data={"kualitas": "bukan_angka"})
    assert resp_q_str.status_code == 400
    assert resp_q_str.json()["error"]["code"] == EDIT_INVALID_QUALITY

    resp_q_low = client.post("/api/image/edit", files={"file": ("a.png", png_data, "image/png")}, data={"kualitas": "5"})
    assert resp_q_low.status_code == 400
    assert resp_q_low.json()["error"]["code"] == EDIT_INVALID_QUALITY

    resp_q_high = client.post("/api/image/edit", files={"file": ("a.png", png_data, "image/png")}, data={"kualitas": "105"})
    assert resp_q_high.status_code == 400
    assert resp_q_high.json()["error"]["code"] == EDIT_INVALID_QUALITY


def test_http_image_edit_galat_payload_too_large_dan_too_many_pixels() -> None:
    client = _test_client()
    if client is None:
        return

    # Uji PAYLOAD_TOO_LARGE lewat edit_image
    expect_image_edit_error(
        lambda: edit_image(b"\x89PNG\r\n\x1a\n" + b"0" * (EDIT_MAX_BYTES + 10)),
        EDIT_PAYLOAD_TOO_LARGE,
        413,
    )

    # Uji TOO_MANY_PIXELS (> 40.000.000 piksel)
    img_huge = Image.new("1", (7000, 6000), 0)
    buf = io.BytesIO()
    img_huge.save(buf, format="PNG")
    huge_png = buf.getvalue()

    expect_image_edit_error(
        lambda: edit_image(huge_png),
        EDIT_TOO_MANY_PIXELS,
        413,
    )

    resp_huge = client.post(
        "/api/image/edit",
        files={"file": ("huge.png", huge_png, "image/png")},
    )
    assert resp_huge.status_code == 413
    assert resp_huge.json()["error"]["code"] == EDIT_TOO_MANY_PIXELS


def test_http_image_edit_root_endpoint_dan_regresi() -> None:
    client = _test_client()
    if client is None:
        return

    root_resp = client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert "image-edit" in root_data["tools"]
    assert "image-convert" in root_data["tools"]


# --- Uji Prime Number Generator ---------------------------------------------
def test_http_prime_limits() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.get("/api/prime/limits")
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    data = resp.json()
    assert "modes" in data
    mode_ids = [m["id"] for m in data["modes"]]
    assert "deret" in mode_ids
    assert "rentang" in mode_ids
    assert "periksa" in mode_ids
    assert data["batas_hasil"] == 5000
    assert data["batas_waktu_detik"] == 10


def test_http_prime_deret_100() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.post("/api/prime", data={"mode": "deret", "jumlah": "100"})
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    data = resp.json()
    assert data["mode"] == "deret"
    assert data["banyak"] == 100
    assert len(data["daftar"]) == 100
    assert data["daftar"][0] == 2
    assert data["daftar"][-1] == 541
    assert data["terbesar"] == 541
    assert "jumlah_digit" in data
    assert "waktu_ms" in data


def test_http_prime_deret_1() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.post("/api/prime", data={"mode": "deret", "jumlah": "1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "deret"
    assert data["daftar"] == [2]
    assert data["banyak"] == 1
    assert data["terbesar"] == 2


def test_http_prime_rentang_10_50() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.post("/api/prime", data={"mode": "rentang", "dari": "10", "sampai": "50"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "rentang"
    expected = [11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]
    assert data["daftar"] == expected
    assert data["banyak"] == len(expected)
    assert data["terbesar"] == 47


def test_http_prime_rentang_batas_bawah_nol() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.post("/api/prime", data={"mode": "rentang", "dari": "0", "sampai": "50"})
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == PRIME_OUT_OF_RANGE


def test_http_prime_periksa_97() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.post("/api/prime", data={"mode": "periksa", "angka": "97"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "periksa"
    assert data["angka"] == 97
    assert data["prima"] is True
    assert data["faktor"] == [{"prima": 97, "pangkat": 1}]
    assert data["faktorisasi"] == "97"


def test_http_prime_periksa_100() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.post("/api/prime", data={"mode": "periksa", "angka": "100"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "periksa"
    assert data["angka"] == 100
    assert data["prima"] is False
    assert data["faktor"] == [{"prima": 2, "pangkat": 2}, {"prima": 5, "pangkat": 2}]
    assert data["faktorisasi"] == "2^2 x 5^2"


def test_http_prime_not_a_number() -> None:
    client = _test_client()
    if client is None:
        return
    resp1 = client.post("/api/prime", data={"mode": "deret", "jumlah": "abc"})
    assert resp1.status_code == 400
    assert resp1.json()["error"]["code"] == PRIME_NOT_A_NUMBER

    resp2 = client.post("/api/prime", data={"mode": "deret", "jumlah": "10.5"})
    assert resp2.status_code == 400
    assert resp2.json()["error"]["code"] == PRIME_NOT_A_NUMBER

    resp3 = client.post("/api/prime", data={"mode": "periksa", "angka": "1,000"})
    assert resp3.status_code == 400
    assert resp3.json()["error"]["code"] == PRIME_NOT_A_NUMBER


def test_http_prime_invalid_range() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.post("/api/prime", data={"mode": "rentang", "dari": "50", "sampai": "10"})
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == PRIME_INVALID_RANGE


def test_http_prime_unsupported_mode() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.post("/api/prime", data={"mode": "acak", "jumlah": "10"})
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == PRIME_UNSUPPORTED_MODE


def test_http_prime_too_many_results() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.post("/api/prime", data={"mode": "rentang", "dari": "2", "sampai": "100000"})
    assert resp.status_code == 413
    data = resp.json()
    assert data["error"]["code"] == PRIME_TOO_MANY_RESULTS


def test_http_prime_no_store_header() -> None:
    client = _test_client()
    if client is None:
        return
    resp_ok = client.post("/api/prime", data={"mode": "deret", "jumlah": "10"})
    assert resp_ok.status_code == 200
    assert "no-store" in resp_ok.headers.get("cache-control", "")

    resp_err = client.post("/api/prime", data={"mode": "deret", "jumlah": "-5"})
    assert resp_err.status_code == 400
    assert "no-store" in resp_err.headers.get("cache-control", "")


def test_http_prime_no_value_dan_invalid_request() -> None:
    client = _test_client()
    if client is None:
        return
    resp_no_mode = client.post("/api/prime", data={})
    assert resp_no_mode.status_code == 400
    assert resp_no_mode.json()["error"]["code"] == PRIME_INVALID_REQUEST

    resp_json = client.post("/api/prime", json={"mode": "deret", "jumlah": "10"})
    assert resp_json.status_code == 400
    assert resp_json.json()["error"]["code"] == PRIME_INVALID_REQUEST

    resp_no_val = client.post("/api/prime", data={"mode": "periksa", "angka": ""})
    assert resp_no_val.status_code == 400
    assert resp_no_val.json()["error"]["code"] == PRIME_NO_VALUE


def test_http_prime_root_endpoint_dan_regresi() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.get("/")
    assert resp.status_code == 200
    tools = resp.json()["tools"]
    assert "prime" in tools
    assert "qr" in tools


def test_prime_logika_is_prime_dan_faktorisasi() -> None:
    assert is_prime(2) is True
    assert is_prime(3) is True
    assert is_prime(4) is False
    assert is_prime(97) is True
    assert is_prime(100) is False
    assert is_prime(10**15) is False

    p_besar = 999999999999989
    t0 = time.monotonic()
    hasil_p = is_prime(p_besar)
    durasi = time.monotonic() - t0
    assert hasil_p is True
    assert durasi < 2.0, f"Pemeriksaan prima 10^15 terlalu lambat: {durasi:.2f} detik"

    is_p, factors, formula = factorize_number(100)
    assert is_p is False
    assert formula == "2^2 x 5^2"


# --- Uji Konverter Zona Waktu -----------------------------------------------
def test_http_timezone_limits() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.get("/api/timezone/limits")
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    data = resp.json()
    assert "modes" in data
    assert "zones" in data
    assert data["max_zones"] == 8
    assert len(data["zones"]) == 22
    mode_ids = [m["id"] for m in data["modes"]]
    assert "titik" in mode_ids
    assert "banding" in mode_ids
    assert "cocok" in mode_ids


def test_http_timezone_titik_wib_ke_london_dan_sebaliknya() -> None:
    client = _test_client()
    if client is None:
        return
    # WIB ke London (tanggal sama, 06:30 WIB -> 00:30 BST)
    resp = client.post(
        "/api/timezone",
        data={"mode": "titik", "tanggal": "2026-10-03", "jam": "06:30", "dari": "wib", "ke": "london"},
    )
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    data = resp.json()
    assert data["mode"] == "titik"
    assert data["acuan"]["zona"] == "wib"
    assert data["tujuan"]["zona"] == "london"
    assert data["tujuan"]["jam"] == "00:30"
    assert data["geser_hari"] == 0
    assert data["geser_teks"] == "tanggal sama"
    assert data["selisih_menit"] == 360
    assert "London 6 jam lebih lambat dari Jakarta" in data["selisih_teks"]

    # WIB ke London dengan geser hari kemarin (04:00 WIB -> 22:00 BST hari sebelumnya)
    resp_prev = client.post(
        "/api/timezone",
        data={"mode": "titik", "tanggal": "2026-10-03", "jam": "04:00", "dari": "wib", "ke": "london"},
    )
    assert resp_prev.status_code == 200
    data_prev = resp_prev.json()
    assert data_prev["geser_hari"] == -1
    assert data_prev["geser_teks"] == "kemarin di zona tujuan"

    # London ke WIB (00:30 BST -> 06:30 WIB)
    resp2 = client.post(
        "/api/timezone",
        data={"mode": "titik", "tanggal": "2026-10-03", "jam": "00:30", "dari": "london", "ke": "wib"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["tujuan"]["jam"] == "06:30"
    assert data2["geser_hari"] == 0
    assert data2["geser_teks"] == "tanggal sama"
    assert data2["selisih_menit"] == 360
    assert "Jakarta 6 jam lebih cepat dari London" in data2["selisih_teks"]

    # London ke WIB dengan geser hari besok (23:00 BST -> 05:00 WIB hari berikutnya)
    resp_next = client.post(
        "/api/timezone",
        data={"mode": "titik", "tanggal": "2026-10-03", "jam": "23:00", "dari": "london", "ke": "wib"},
    )
    assert resp_next.status_code == 200
    data_next = resp_next.json()
    assert data_next["geser_hari"] == 1
    assert data_next["geser_teks"] == "besok di zona tujuan"


def test_http_timezone_banding_4_zona() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.post(
        "/api/timezone",
        data={
            "mode": "banding",
            "tanggal": "2026-10-03",
            "jam": "09:00",
            "dari": "wib",
            "zona": "tokyo,london,newyork,sydney",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "banding"
    assert len(data["daftar"]) == 4
    zone_ids = [item["zona"] for item in data["daftar"]]
    assert zone_ids == ["tokyo", "london", "newyork", "sydney"]
    for item in data["daftar"]:
        assert "zona" in item
        assert "label" in item
        assert "iana" in item
        assert "tanggal" in item
        assert "jam" in item
        assert "waktu" in item
        assert "offset_teks" in item
        assert "singkatan" in item
        assert "geser_hari" in item
        assert "geser_teks" in item
        assert "jam_kerja" in item
        assert "keterangan" in item
        assert isinstance(item["jam_kerja"], bool)


def test_http_timezone_cocok_rentang_kecil() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.post(
        "/api/timezone",
        data={
            "mode": "cocok",
            "tanggal": "2026-10-03",
            "dari": "wib",
            "zona": "tokyo,london,sydney",
            "jam_mulai": "12",
            "jam_selesai": "16",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "cocok"
    assert data["rentang"]["jam_mulai"] == "12:00"
    assert data["rentang"]["jam_selesai"] == "16:00"
    rekom = data["rekomendasi"]
    assert len(rekom) == 5
    for i in range(len(rekom) - 1):
        assert rekom[i]["cocok"] >= rekom[i + 1]["cocok"]
    assert rekom[0]["total"] == 4
    assert "jam_acuan_teks" in rekom[0]
    assert len(rekom[0]["detail"]) == 4


def test_http_timezone_daylight_saving_summer_vs_winter() -> None:
    client = _test_client()
    if client is None:
        return
    # London musim panas (BST -> UTC+01:00)
    resp_summer = client.post(
        "/api/timezone",
        data={"mode": "titik", "tanggal": "2026-07-15", "jam": "12:00", "dari": "wib", "ke": "london"},
    )
    assert resp_summer.status_code == 200
    data_summer = resp_summer.json()
    assert data_summer["tujuan"]["offset_teks"] == "UTC+01:00"
    assert data_summer["tujuan"]["singkatan"] == "BST"

    # London musim dingin (GMT -> UTC+00:00)
    resp_winter = client.post(
        "/api/timezone",
        data={"mode": "titik", "tanggal": "2026-01-15", "jam": "12:00", "dari": "wib", "ke": "london"},
    )
    assert resp_winter.status_code == 200
    data_winter = resp_winter.json()
    assert data_winter["tujuan"]["offset_teks"] == "UTC+00:00"
    assert data_winter["tujuan"]["singkatan"] == "GMT"


def test_http_timezone_jalur_galat() -> None:
    client = _test_client()
    if client is None:
        return
    # INVALID_REQUEST: tanpa mode
    r1 = client.post("/api/timezone", data={})
    assert r1.status_code == 400
    assert r1.json()["error"]["code"] == TZ_INVALID_REQUEST

    # INVALID_REQUEST: kirim json bukan multipart
    r_json = client.post("/api/timezone", json={"mode": "titik"})
    assert r_json.status_code == 400
    assert r_json.json()["error"]["code"] == TZ_INVALID_REQUEST

    # INVALID_REQUEST: field kurang pada mode titik
    r_missing = client.post("/api/timezone", data={"mode": "titik", "tanggal": "2026-10-03"})
    assert r_missing.status_code == 400
    assert r_missing.json()["error"]["code"] == TZ_INVALID_REQUEST

    # UNSUPPORTED_MODE
    r_mode = client.post("/api/timezone", data={"mode": "teleport"})
    assert r_mode.status_code == 400
    assert r_mode.json()["error"]["code"] == TZ_UNSUPPORTED_MODE

    # INVALID_ZONE: zona tidak dikenal
    r_zone = client.post(
        "/api/timezone",
        data={"mode": "titik", "tanggal": "2026-10-03", "jam": "06:30", "dari": "atlantis", "ke": "london"},
    )
    assert r_zone.status_code == 400
    assert r_zone.json()["error"]["code"] == TZ_INVALID_ZONE
    assert "atlantis" in r_zone.json()["error"]["message"]

    # TOO_MANY_ZONES: lebih dari 8 zona
    r_many = client.post(
        "/api/timezone",
        data={
            "mode": "banding",
            "tanggal": "2026-10-03",
            "jam": "09:00",
            "dari": "wib",
            "zona": "tokyo,seoul,shanghai,hongkong,delhi,dubai,mekkah,kairo,london",
        },
    )
    assert r_many.status_code == 400
    assert r_many.json()["error"]["code"] == TZ_TOO_MANY_ZONES

    # INVALID_DATE: format tanggal salah
    r_date = client.post(
        "/api/timezone",
        data={"mode": "titik", "tanggal": "03-10-2026", "jam": "06:30", "dari": "wib", "ke": "london"},
    )
    assert r_date.status_code == 400
    assert r_date.json()["error"]["code"] == TZ_INVALID_DATE

    # OUT_OF_RANGE: tahun di luar 1900-2100
    r_year = client.post(
        "/api/timezone",
        data={"mode": "titik", "tanggal": "1899-10-03", "jam": "06:30", "dari": "wib", "ke": "london"},
    )
    assert r_year.status_code == 400
    assert r_year.json()["error"]["code"] == TZ_OUT_OF_RANGE

    # INVALID_TIME: format jam salah
    r_time = client.post(
        "/api/timezone",
        data={"mode": "titik", "tanggal": "2026-10-03", "jam": "25:70", "dari": "wib", "ke": "london"},
    )
    assert r_time.status_code == 400
    assert r_time.json()["error"]["code"] == TZ_INVALID_TIME

    # INVALID_RANGE: jam_mulai >= jam_selesai pada mode cocok
    r_range = client.post(
        "/api/timezone",
        data={
            "mode": "cocok",
            "tanggal": "2026-10-03",
            "dari": "wib",
            "zona": "tokyo,london",
            "jam_mulai": "18",
            "jam_selesai": "09",
        },
    )
    assert r_range.status_code == 400
    assert r_range.json()["error"]["code"] == TZ_INVALID_RANGE


def test_http_timezone_payload_too_large() -> None:
    client = _test_client()
    if client is None:
        return
    huge_data = "x" * 70000
    resp = client.post("/api/timezone", data={"mode": "titik", "ekstra": huge_data})
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == TZ_PAYLOAD_TOO_LARGE


def test_http_timezone_root_endpoint_dan_regresi() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.get("/")
    assert resp.status_code == 200
    tools = resp.json()["tools"]
    assert "timezone" in tools
    assert "prime" in tools
    assert "unit-convert" in tools

    r_prime = client.get("/api/prime/limits")
    assert r_prime.status_code == 200
    r_unit = client.get("/api/unit-convert/limits")
    assert r_unit.status_code == 200
    r_date = client.get("/api/date-calc/limits")
    assert r_date.status_code == 200


# --- Uji CSV Tools ----------------------------------------------------------
def test_csv_ke_json_lengkap() -> None:
    # 1. Parsing CSV sadar tanda kutip RFC 4180 dengan sel berkutip berisi koma dan kutip ganda
    csv_teks = (
        'nama,kota,catatan\n'
        'Budi,"Jakarta, Selatan","Kata dia: ""Halo!"""\n'
        'Siti,Surabaya,Biasa saja\n'
    )
    res = proses_csv(csv_teks, mode="ke_json", pemisah="otomatis", header="ya", rapikan="ya", indent="2")
    assert res["mode"] == "ke_json"
    assert res["pemisah_terpakai"] == "koma"
    assert res["ringkasan"]["jumlah_baris"] == 2
    assert res["ringkasan"]["jumlah_kolom"] == 3
    data = res["keluaran"]["data"]
    assert len(data) == 2
    assert data[0]["nama"] == "Budi"
    assert data[0]["kota"] == "Jakarta, Selatan"
    assert data[0]["catatan"] == 'Kata dia: "Halo!"'

    # 2. Header kosong dan ganda (kolom_2, nama_2)
    csv_header_aneh = (
        'nama,,nama,skor\n'
        'Budi,10,Utama,100\n'
    )
    res_hdr = proses_csv(csv_header_aneh, mode="ke_json", header="ya")
    data_hdr = res_hdr["keluaran"]["data"]
    assert "nama" in data_hdr[0]
    assert "kolom_2" in data_hdr[0]
    assert "nama_2" in data_hdr[0]
    assert "skor" in data_hdr[0]
    assert data_hdr[0]["kolom_2"] == "10"
    assert data_hdr[0]["nama_2"] == "Utama"

    # 3. Baris sel kurang (diisi string kosong) dan sel lebih (kolom_tambahan_1)
    csv_beda_sel = (
        'a,b\n'
        '1\n'
        '1,2,3,4\n'
    )
    res_sel = proses_csv(csv_beda_sel, mode="ke_json", header="ya")
    data_sel = res_sel["keluaran"]["data"]
    assert data_sel[0] == {"a": "1", "b": ""}
    assert data_sel[1]["a"] == "1"
    assert data_sel[1]["b"] == "2"
    assert data_sel[1]["kolom_tambahan_1"] == "3"
    assert data_sel[1]["kolom_tambahan_2"] == "4"
    assert "kolom_tambahan" in res_sel["catatan"]

    # 4. Header=tidak (array dari array)
    res_no_hdr = proses_csv("1,2\n3,4", mode="ke_json", header="tidak")
    assert res_no_hdr["keluaran"]["data"] == [["1", "2"], ["3", "4"]]

    # 5. Pemisah titik_koma, tab, pipa
    res_semi = proses_csv("a;b\n1;2", mode="ke_json", pemisah="titik_koma")
    assert res_semi["pemisah_terpakai"] == "titik_koma"
    assert res_semi["keluaran"]["data"] == [{"a": "1", "b": "2"}]

    res_tab = proses_csv("a\tb\n1\t2", mode="ke_json", pemisah="tab")
    assert res_tab["pemisah_terpakai"] == "tab"

    res_pipa = proses_csv("a|b\n1|2", mode="ke_json", pemisah="pipa")
    assert res_pipa["pemisah_terpakai"] == "pipa"

    # 6. Indentasi 4 dan tab
    res_ind4 = proses_csv("a,b\n1,2", mode="ke_json", indent="4")
    assert "    " in res_ind4["keluaran"]["teks"]

    res_ind_tab = proses_csv("a,b\n1,2", mode="ke_json", indent="tab")
    assert "\t" in res_ind_tab["keluaran"]["teks"]


def test_csv_ke_csv_lengkap() -> None:
    # 1. Array objek dengan kunci gabungan menurut kemunculan pertama
    json_obj = json.dumps([
        {"id": 1, "nama": "Budi"},
        {"nama": "Siti", "kota": "Surabaya"},
        {"id": 3, "kota": "Medan", "extra": {"level": 2}},
    ])
    res = proses_csv(json_obj, mode="ke_csv", pemisah="koma")
    assert res["mode"] == "ke_csv"
    assert res["ringkasan"]["jumlah_baris"] == 3
    assert res["ringkasan"]["jumlah_kolom"] == 4
    csv_lines = res["keluaran"]["teks"].splitlines()
    assert csv_lines[0] == "id,nama,kota,extra"
    # Nilai bersarang objek disimpan sebagai JSON padat; kutip di dalam sel ditulis ganda.
    baris_ketiga = list(csv.reader(csv_lines))[3]
    assert baris_ketiga == ["3", "", "Medan", '{"level":2}']

    # 2. Objek wrapper dengan field data / items / rows
    json_wrap = json.dumps({"data": [{"x": 10, "y": 20}]})
    res_wrap = proses_csv(json_wrap, mode="ke_csv")
    assert res_wrap["ringkasan"]["jumlah_baris"] == 1

    # 3. Array dari array
    json_arr = json.dumps([["h1", "h2"], ["val1", "val2,dengan,koma"]])
    res_arr = proses_csv(json_arr, mode="ke_csv")
    lines_arr = res_arr["keluaran"]["teks"].splitlines()
    assert lines_arr[0] == "h1,h2"
    assert lines_arr[1] == 'val1,"val2,dengan,koma"'


def test_csv_ringkas_lengkap() -> None:
    csv_teks = (
        "angka,tanggal,kategori,status,kosong\n"
        "10,2026-01-01,Elektronik,Aktif,\n"
        "50,2026-06-15,Pakaian,Aktif,\n"
        "100,2026-12-31,Elektronik,Pasif,\n"
        ",2026-03-10,Makanan,Aktif,\n"
    )
    res = proses_csv(csv_teks, mode="ringkas", header="ya", rapikan="ya")
    assert res["mode"] == "ringkas"
    assert res["ringkasan"]["total_baris"] == 4
    assert res["ringkasan"]["total_kolom"] == 5
    assert res["ringkasan"]["kolom_kosong"] == 1

    cols = {c["nama"]: c for c in res["kolom"]}
    # Angka
    assert cols["angka"]["tipe"] == "angka"
    assert cols["angka"]["nilai_terkecil"] == 10
    assert cols["angka"]["nilai_terbesar"] == 100
    assert cols["angka"]["sel_kosong"] == 1
    assert cols["angka"]["nilai_unik"] == 3

    # Tanggal
    assert cols["tanggal"]["tipe"] == "tanggal"
    assert cols["tanggal"]["nilai_terkecil"] == "2026-01-01"
    assert cols["tanggal"]["nilai_terbesar"] == "2026-12-31"

    # Teks
    assert cols["status"]["tipe"] == "teks"
    assert cols["status"]["nilai_terbanyak"][0] == {"nilai": "Aktif", "jumlah": 3}

    # Kolom kosong
    assert cols["kosong"]["tipe"] == "kosong"
    assert cols["kosong"]["sel_kosong"] == 4


def test_csv_galat_logika() -> None:
    # NO_TEXT
    try:
        proses_csv("", mode="ke_json")
        assert False, "harus gagal"
    except CsvToolError as e:
        assert e.code == CSV_NO_TEXT

    # INVALID_REQUEST (mode kosong)
    try:
        proses_csv("a,b", mode="")
        assert False, "harus gagal"
    except CsvToolError as e:
        assert e.code == CSV_INVALID_REQUEST

    # UNSUPPORTED_MODE
    try:
        proses_csv("a,b", mode="magic")
        assert False, "harus gagal"
    except CsvToolError as e:
        assert e.code == CSV_UNSUPPORTED_MODE

    # INVALID_SEPARATOR
    try:
        proses_csv("a,b", mode="ke_json", pemisah="spasi")
        assert False, "harus gagal"
    except CsvToolError as e:
        assert e.code == CSV_INVALID_SEPARATOR

    # INVALID_BOOLEAN
    try:
        proses_csv("a,b", mode="ke_json", header="mungkin")
        assert False, "harus gagal"
    except CsvToolError as e:
        assert e.code == CSV_INVALID_BOOLEAN

    # INVALID_INDENT
    try:
        proses_csv("a,b", mode="ke_json", indent="8")
        assert False, "harus gagal"
    except CsvToolError as e:
        assert e.code == CSV_INVALID_INDENT

    # INVALID_JSON pada mode ke_csv
    try:
        proses_csv("bukan json sah", mode="ke_csv")
        assert False, "harus gagal"
    except CsvToolError as e:
        assert e.code == CSV_INVALID_JSON
        assert e.detail is not None
        assert "baris" in e.detail

    # INVALID_FORMAT pada mode ke_csv (bukan array / tabel)
    try:
        proses_csv('{"skalar": 123}', mode="ke_csv")
        assert False, "harus gagal"
    except CsvToolError as e:
        assert e.code == CSV_INVALID_FORMAT

    # INVALID_FORMAT pada mode ke_json bila diberi data JSON
    try:
        proses_csv('[{"a": 1}]', mode="ke_json")
        assert False, "harus gagal"
    except CsvToolError as e:
        assert e.code == CSV_INVALID_FORMAT

    # TOO_LONG (> 400.000 karakter)
    try:
        proses_csv("a," * 250000, mode="ke_json")
        assert False, "harus gagal"
    except CsvToolError as e:
        assert e.code == CSV_TOO_LONG

    # TOO_MANY_COLUMNS (> 200)
    banyak_kolom = ",".join(f"col_{i}" for i in range(205))
    try:
        proses_csv(banyak_kolom + "\n" + banyak_kolom, mode="ke_json")
        assert False, "harus gagal"
    except CsvToolError as e:
        assert e.code == CSV_TOO_MANY_COLUMNS


def test_http_csv_limits() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.get("/api/csv/limits")
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    data = resp.json()
    assert "modes" in data
    assert "separators" in data
    assert "contoh_csv" in data
    assert "contoh_json" in data
    assert data["max_chars"] == CSV_MAX_CHARS
    assert data["max_rows"] == CSV_MAX_ROWS
    assert data["max_cols"] == CSV_MAX_COLS


def test_http_csv_ke_json_endpoint() -> None:
    client = _test_client()
    if client is None:
        return
    csv_data = "nama,nilai\nBudi,90\nSiti,95"
    resp = client.post(
        "/api/csv",
        data={"teks": csv_data, "mode": "ke_json", "header": "ya"},
    )
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
    assert "X-Processing-Ms" in resp.headers
    body = resp.json()
    assert body["mode"] == "ke_json"
    assert len(body["keluaran"]["data"]) == 2
    assert body["keluaran"]["data"][0]["nama"] == "Budi"


def test_http_csv_ke_csv_endpoint() -> None:
    client = _test_client()
    if client is None:
        return
    json_data = json.dumps([{"nama": "Andi", "skor": 85}])
    resp = client.post(
        "/api/csv",
        data={"teks": json_data, "mode": "ke_csv"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "ke_csv"
    assert "nama,skor" in body["keluaran"]["teks"]


def test_http_csv_ringkas_endpoint() -> None:
    client = _test_client()
    if client is None:
        return
    csv_data = "item,harga\nBuku,15000\nPena,5000"
    resp = client.post(
        "/api/csv",
        data={"teks": csv_data, "mode": "ringkas"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "ringkas"
    assert len(body["kolom"]) == 2


def test_http_csv_jalur_galat() -> None:
    client = _test_client()
    if client is None:
        return
    # JSON body ditolak
    r_json = client.post("/api/csv", json={"mode": "ke_json"})
    assert r_json.status_code == 400
    assert r_json.json()["error"]["code"] == CSV_INVALID_REQUEST

    # Mode kosong
    r_no_mode = client.post("/api/csv", data={"teks": "a,b"})
    assert r_no_mode.status_code == 400
    assert r_no_mode.json()["error"]["code"] == CSV_INVALID_REQUEST

    # Teks kosong
    r_no_text = client.post("/api/csv", data={"teks": "", "mode": "ke_json"})
    assert r_no_text.status_code == 400
    assert r_no_text.json()["error"]["code"] == CSV_NO_TEXT

    # Mode tidak didukung
    r_bad_mode = client.post("/api/csv", data={"teks": "a,b", "mode": "unknown"})
    assert r_bad_mode.status_code == 400
    assert r_bad_mode.json()["error"]["code"] == CSV_UNSUPPORTED_MODE

    # Format JSON salah di ke_csv
    r_bad_json = client.post("/api/csv", data={"teks": "{rusak", "mode": "ke_csv"})
    assert r_bad_json.status_code == 400
    assert r_bad_json.json()["error"]["code"] == CSV_INVALID_JSON
    assert "posisi" in r_bad_json.json()["error"]


def test_http_csv_root_endpoint_dan_regresi() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.get("/")
    assert resp.status_code == 200
    tools = resp.json()["tools"]
    assert "csv" in tools
    assert "timezone" in tools


# --- Uji Kalkulator Listrik --------------------------------------------------
def test_listrik_format_angka_dan_rupiah() -> None:
    assert format_listrik_angka(0) == "0"
    assert format_listrik_angka(220) == "220"
    assert format_listrik_angka(1100) == "1.100"
    assert format_listrik_angka(1444.7) == "1.444,7"
    assert format_listrik_angka(5.6) == "5,6"
    assert format_listrik_angka(3.333333333) == "3,333333"
    assert format_listrik_rupiah(1444.7) == "Rp 1.444,7"
    assert format_listrik_rupiah(242709.6) == "Rp 242.709,6"
    assert format_listrik_rupiah(0) == "Rp 0"


def test_listrik_parse_number() -> None:
    assert parse_listrik_number("220") == 220.0
    assert parse_listrik_number(" 5 ") == 5.0
    assert parse_listrik_number("1.444,7") == 1444.7
    assert parse_listrik_number("1444.7") == 1444.7
    assert parse_listrik_number("0,5") == 0.5
    assert parse_listrik_number("1.000.000") == 1000000.0


def test_listrik_mode_ohm_variasi() -> None:
    # 1. Hitung tegangan (arus=5 A, hambatan=44 Ω) -> V = 220 V, P = 1100 W
    res_v = hitung_ohm(tegangan_raw="", arus_raw="5", hambatan_raw="44")
    assert res_v["dihitung"] == "tegangan"
    assert res_v["hasil"]["nilai"] == 220.0
    assert res_v["hasil"]["teks"] == "220"
    assert res_v["hasil"]["satuan"] == "V"
    assert res_v["daya"]["nilai"] == 1100.0
    assert res_v["daya"]["teks"] == "1.100"
    assert len(res_v["langkah"]) == 2
    assert "catatan_jujur" in res_v

    # 2. Hitung arus (tegangan=220 V, hambatan=44 Ω) -> I = 5 A, P = 1100 W
    res_i = hitung_ohm(tegangan_raw="220", arus_raw="", hambatan_raw="44")
    assert res_i["dihitung"] == "arus"
    assert res_i["hasil"]["nilai"] == 5.0
    assert res_i["hasil"]["teks"] == "5"
    assert res_i["hasil"]["satuan"] == "A"
    assert res_i["daya"]["nilai"] == 1100.0

    # 3. Hitung hambatan (tegangan=220 V, arus=5 A) -> R = 44 Ω, P = 1100 W
    res_r = hitung_ohm(tegangan_raw="220", arus_raw="5", hambatan_raw="")
    assert res_r["dihitung"] == "hambatan"
    assert res_r["hasil"]["nilai"] == 44.0
    assert res_r["hasil"]["teks"] == "44"
    assert res_r["hasil"]["satuan"] == "Ω"
    assert res_r["daya"]["nilai"] == 1100.0


def test_listrik_mode_ohm_galat() -> None:
    # Kurang dari dua nilai terisi
    try:
        hitung_ohm(tegangan_raw="220", arus_raw="", hambatan_raw="")
    except ListrikError as e:
        assert e.code == LK_NILAI_KURANG
        assert e.status_code == 400
    else:
        assert False, "Harus memicu NILAI_KURANG"

    # Semua tiga nilai terisi
    try:
        hitung_ohm(tegangan_raw="220", arus_raw="5", hambatan_raw="44")
    except ListrikError as e:
        assert e.code == LK_TERLALU_BANYAK_NILAI
        assert e.status_code == 400
    else:
        assert False, "Harus memicu TERLALU_BANYAK_NILAI"

    # Hambatan 0 -> DIVIDE_BY_ZERO
    try:
        hitung_ohm(tegangan_raw="220", arus_raw="", hambatan_raw="0")
    except ListrikError as e:
        assert e.code == LK_DIVIDE_BY_ZERO
        assert e.status_code == 400
    else:
        assert False, "Harus memicu DIVIDE_BY_ZERO"

    # Arus 0 -> DIVIDE_BY_ZERO
    try:
        hitung_ohm(tegangan_raw="220", arus_raw="0", hambatan_raw="")
    except ListrikError as e:
        assert e.code == LK_DIVIDE_BY_ZERO
        assert e.status_code == 400
    else:
        assert False, "Harus memicu DIVIDE_BY_ZERO"

    # Tegangan 0 -> OUT_OF_RANGE
    try:
        hitung_ohm(tegangan_raw="0", arus_raw="5", hambatan_raw="")
    except ListrikError as e:
        assert e.code == LK_OUT_OF_RANGE
        assert e.status_code == 400
    else:
        assert False, "Harus memicu OUT_OF_RANGE"

    # Nilai negatif -> OUT_OF_RANGE
    try:
        hitung_ohm(tegangan_raw="-220", arus_raw="5", hambatan_raw="")
    except ListrikError as e:
        assert e.code == LK_OUT_OF_RANGE
        assert e.status_code == 400
    else:
        assert False, "Harus memicu OUT_OF_RANGE"

    # Nilai bukan angka -> NOT_A_NUMBER
    try:
        hitung_ohm(tegangan_raw="abc", arus_raw="5", hambatan_raw="")
    except ListrikError as e:
        assert e.code == LK_NOT_A_NUMBER
        assert e.status_code == 400
    else:
        assert False, "Harus memicu NOT_A_NUMBER"

    # Panjang karakter melebihi 24 -> OUT_OF_RANGE
    try:
        hitung_ohm(tegangan_raw="1" * 25, arus_raw="5", hambatan_raw="")
    except ListrikError as e:
        assert e.code == LK_OUT_OF_RANGE
        assert e.status_code == 400
    else:
        assert False, "Harus memicu OUT_OF_RANGE"


def test_listrik_mode_daya_sukses() -> None:
    res = hitung_daya(
        daya_alat_raw="350",
        jam_per_hari_raw="8",
        jumlah_alat_raw="2",
        hari_raw="30",
        tarif_raw="1444.7",
    )
    # kwh = 350 * 8 * 2 * 30 / 1000 = 168.0 kWh
    # biaya = 168.0 * 1444.7 = 242709.6 Rp
    assert res["hasil"]["kwh"]["nilai"] == 168.0
    assert res["hasil"]["kwh"]["teks"] == "168"
    assert res["hasil"]["biaya"]["nilai"] == 242709.6
    assert "242.709,6" in res["hasil"]["biaya"]["teks"]

    # Turunan
    assert res["turunan"]["kwh_per_hari"]["nilai"] == 5.6
    assert res["turunan"]["biaya_per_hari"]["nilai"] == 5.6 * 1444.7
    assert res["turunan"]["biaya_per_bulan"]["nilai"] == 5.6 * 30.0 * 1444.7
    assert res["turunan"]["biaya_per_tahun"]["nilai"] == 5.6 * 365.0 * 1444.7
    assert len(res["langkah"]) == 4

    # Tarif 0 diperbolehkan
    res_nol = hitung_daya(
        daya_alat_raw="100",
        jam_per_hari_raw="10",
        jumlah_alat_raw="1",
        hari_raw="1",
        tarif_raw="0",
    )
    assert res_nol["hasil"]["kwh"]["nilai"] == 1.0
    assert res_nol["hasil"]["biaya"]["nilai"] == 0.0


def test_listrik_mode_daya_galat() -> None:
    # Daya di bawah 0.1 W
    try:
        hitung_daya("0.05", "8", "1", "30", "1500")
    except ListrikError as e:
        assert e.code == LK_OUT_OF_RANGE
        assert e.status_code == 400
    else:
        assert False, "Harus memicu OUT_OF_RANGE"

    # Jam di atas 24
    try:
        hitung_daya("100", "25", "1", "30", "1500")
    except ListrikError as e:
        assert e.code == LK_OUT_OF_RANGE
        assert e.status_code == 400
    else:
        assert False, "Harus memicu OUT_OF_RANGE"

    # Jumlah alat bukan bilangan bulat
    try:
        hitung_daya("100", "8", "2.5", "30", "1500")
    except ListrikError as e:
        assert e.code == LK_OUT_OF_RANGE
        assert e.status_code == 400
    else:
        assert False, "Harus memicu OUT_OF_RANGE"

    # Jumlah hari bukan bilangan bulat
    try:
        hitung_daya("100", "8", "2", "30.5", "1500")
    except ListrikError as e:
        assert e.code == LK_OUT_OF_RANGE
        assert e.status_code == 400
    else:
        assert False, "Harus memicu OUT_OF_RANGE"

    # Tarif negatif
    try:
        hitung_daya("100", "8", "2", "30", "-1500")
    except ListrikError as e:
        assert e.code == LK_OUT_OF_RANGE
        assert e.status_code == 400
    else:
        assert False, "Harus memicu OUT_OF_RANGE"

    # Tarif melebihi 100.000
    try:
        hitung_daya("100", "8", "2", "30", "100001")
    except ListrikError as e:
        assert e.code == LK_OUT_OF_RANGE
        assert e.status_code == 400
    else:
        assert False, "Harus memicu OUT_OF_RANGE"


def test_listrik_mode_hambatan_seri_dan_paralel() -> None:
    # Seri: 100 + 220 + 470 = 790 Ω
    res_s = hitung_hambatan("100\n220\n470", "seri")
    assert res_s["jenis"] == "seri"
    assert res_s["jumlah_komponen"] == 3
    assert res_s["hasil"]["nilai"] == 790.0
    assert res_s["hasil"]["teks"] == "790"
    assert res_s["hasil"]["satuan"] == "Ω"
    assert len(res_s["komponen"]) == 3

    # Paralel: 1/(1/100 + 1/100) = 50 Ω
    res_p = hitung_hambatan("100\n100", "paralel")
    assert res_p["jenis"] == "paralel"
    assert res_p["jumlah_komponen"] == 2
    assert res_p["hasil"]["nilai"] == 50.0
    assert res_p["hasil"]["teks"] == "50"

    # Paralel 3 komponen: 10, 20, 30
    # 1/R = 1/10 + 1/20 + 1/30 = 6/60 + 3/60 + 2/60 = 11/60
    # R = 60/11 = 5.4545454545...
    res_p3 = hitung_hambatan("10\n20\n30", "paralel")
    expected = 60.0 / 11.0
    assert abs(res_p3["hasil"]["nilai"] - expected) < 1e-9
    assert res_p3["hasil"]["teks"] == "5,454545"

    # Mengabaikan baris kosong
    res_sp = hitung_hambatan("100\n\n  \n220\n470\n", "seri")
    assert res_sp["hasil"]["nilai"] == 790.0

    # 50 komponen seri dan paralel
    items_50 = "\n".join(["100"] * 50)
    res_50_s = hitung_hambatan(items_50, "seri")
    assert res_50_s["hasil"]["nilai"] == 5000.0
    assert res_50_s["jumlah_komponen"] == 50

    res_50_p = hitung_hambatan(items_50, "paralel")
    assert abs(res_50_p["hasil"]["nilai"] - 2.0) < 1e-9
    assert res_50_p["jumlah_komponen"] == 50


def test_listrik_mode_hambatan_galat() -> None:
    # Daftar kosong
    try:
        hitung_hambatan("", "seri")
    except ListrikError as e:
        assert e.code == LK_LIST_KOSONG
        assert e.status_code == 400
    else:
        assert False, "Harus memicu LIST_KOSONG"

    # Daftar spasi saja
    try:
        hitung_hambatan("   \n\n  ", "seri")
    except ListrikError as e:
        assert e.code == LK_LIST_KOSONG
        assert e.status_code == 400
    else:
        assert False, "Harus memicu LIST_KOSONG"

    # Lebih dari 50 komponen (51 baris) -> TOO_MANY_ITEMS (413)
    items_51 = "\n".join(["10"] * 51)
    try:
        hitung_hambatan(items_51, "seri")
    except ListrikError as e:
        assert e.code == LK_TOO_MANY_ITEMS
        assert e.status_code == 413
    else:
        assert False, "Harus memicu TOO_MANY_ITEMS"

    # Jenis tidak didukung
    try:
        hitung_hambatan("100\n200", "campuran")
    except ListrikError as e:
        assert e.code == LK_UNSUPPORTED_JENIS
        assert e.status_code == 400
    else:
        assert False, "Harus memicu UNSUPPORTED_JENIS"

    # Nilai 0 -> DIVIDE_BY_ZERO
    try:
        hitung_hambatan("100\n0\n200", "seri")
    except ListrikError as e:
        assert e.code == LK_DIVIDE_BY_ZERO
        assert e.status_code == 400
    else:
        assert False, "Harus memicu DIVIDE_BY_ZERO"

    # Nilai negatif -> OUT_OF_RANGE
    try:
        hitung_hambatan("100\n-50\n200", "seri")
    except ListrikError as e:
        assert e.code == LK_OUT_OF_RANGE
        assert e.status_code == 400
    else:
        assert False, "Harus memicu OUT_OF_RANGE"

    # Nilai bukan angka -> NOT_A_NUMBER
    try:
        hitung_hambatan("100\nsepuluh\n200", "seri")
    except ListrikError as e:
        assert e.code == LK_NOT_A_NUMBER
        assert e.status_code == 400
    else:
        assert False, "Harus memicu NOT_A_NUMBER"


def test_listrik_limits_payload() -> None:
    data = listrik_limits_payload_func()
    assert data["max_input_chars"] == 24
    assert data["max_value"] == 1e12
    assert data["max_items"] == 50
    assert data["processed_on"] == "server"
    modes = [m["value"] for m in data["modes"]]
    assert "ohm" in modes
    assert "daya" in modes
    assert "hambatan" in modes
    assert "catatan_jujur" in data


def test_http_listrik_endpoints() -> None:
    client = _test_client()
    if client is None:
        return

    # 1. GET /api/listrik/limits
    r_limits = client.get("/api/listrik/limits")
    assert r_limits.status_code == 200
    assert "no-store" in r_limits.headers.get("cache-control", "")
    assert len(r_limits.json()["modes"]) == 3

    # 2. POST /api/listrik - mode ohm
    r_ohm = client.post(
        "/api/listrik",
        data={"mode": "ohm", "tegangan": "", "arus": "5", "hambatan": "44"},
    )
    assert r_ohm.status_code == 200
    assert "no-store" in r_ohm.headers.get("cache-control", "")
    assert "X-Processing-Ms" in r_ohm.headers
    body_ohm = r_ohm.json()
    assert body_ohm["mode"] == "ohm"
    assert body_ohm["hasil"]["nilai"] == 220.0
    assert body_ohm["daya"]["nilai"] == 1100.0

    # 3. POST /api/listrik - mode daya
    r_daya = client.post(
        "/api/listrik",
        data={
            "mode": "daya",
            "daya_alat": "350",
            "jam_per_hari": "8",
            "jumlah_alat": "2",
            "hari": "30",
            "tarif": "1444.7",
        },
    )
    assert r_daya.status_code == 200
    body_daya = r_daya.json()
    assert body_daya["mode"] == "daya"
    assert body_daya["hasil"]["kwh"]["nilai"] == 168.0

    # 4. POST /api/listrik - mode hambatan
    r_hambatan = client.post(
        "/api/listrik",
        data={"mode": "hambatan", "jenis": "paralel", "daftar": "100\n100"},
    )
    assert r_hambatan.status_code == 200
    body_hambatan = r_hambatan.json()
    assert body_hambatan["mode"] == "hambatan"
    assert body_hambatan["hasil"]["nilai"] == 50.0


def test_http_listrik_jalur_galat() -> None:
    client = _test_client()
    if client is None:
        return

    # Non-multipart body (JSON) -> 400 INVALID_REQUEST
    r_json = client.post("/api/listrik", json={"mode": "ohm"})
    assert r_json.status_code == 400
    assert r_json.json()["error"]["code"] == LK_INVALID_REQUEST

    # Mode kosong -> 400 INVALID_REQUEST
    r_no_mode = client.post("/api/listrik", data={})
    assert r_no_mode.status_code == 400
    assert r_no_mode.json()["error"]["code"] == LK_INVALID_REQUEST

    # Mode tidak didukung -> 400 UNSUPPORTED_MODE
    r_bad_mode = client.post("/api/listrik", data={"mode": "tidak_ada"})
    assert r_bad_mode.status_code == 400
    assert r_bad_mode.json()["error"]["code"] == LK_UNSUPPORTED_MODE

    # Mode ohm kurang nilai -> 400 NILAI_KURANG
    r_ohm_kurang = client.post("/api/listrik", data={"mode": "ohm", "tegangan": "220"})
    assert r_ohm_kurang.status_code == 400
    assert r_ohm_kurang.json()["error"]["code"] == LK_NILAI_KURANG

    # Mode ohm terlalu banyak nilai -> 400 TERLALU_BANYAK_NILAI
    r_ohm_lebih = client.post(
        "/api/listrik",
        data={"mode": "ohm", "tegangan": "220", "arus": "5", "hambatan": "44"},
    )
    assert r_ohm_lebih.status_code == 400
    assert r_ohm_lebih.json()["error"]["code"] == LK_TERLALU_BANYAK_NILAI

    # Mode ohm pembagian dengan nol -> 400 DIVIDE_BY_ZERO
    r_ohm_zero = client.post(
        "/api/listrik",
        data={"mode": "ohm", "tegangan": "220", "arus": "0"},
    )
    assert r_ohm_zero.status_code == 400
    assert r_ohm_zero.json()["error"]["code"] == LK_DIVIDE_BY_ZERO

    # Mode daya di luar rentang -> 400 OUT_OF_RANGE
    r_daya_range = client.post(
        "/api/listrik",
        data={
            "mode": "daya",
            "daya_alat": "0",
            "jam_per_hari": "8",
            "jumlah_alat": "1",
            "hari": "30",
            "tarif": "1500",
        },
    )
    assert r_daya_range.status_code == 400
    assert r_daya_range.json()["error"]["code"] == LK_OUT_OF_RANGE

    # Mode hambatan daftar kosong -> 400 LIST_KOSONG
    r_hambatan_empty = client.post(
        "/api/listrik",
        data={"mode": "hambatan", "jenis": "seri", "daftar": "   "},
    )
    assert r_hambatan_empty.status_code == 400
    assert r_hambatan_empty.json()["error"]["code"] == LK_LIST_KOSONG

    # Mode hambatan > 50 baris -> 413 TOO_MANY_ITEMS
    r_hambatan_banyak = client.post(
        "/api/listrik",
        data={"mode": "hambatan", "jenis": "seri", "daftar": "\n".join(["10"] * 51)},
    )
    assert r_hambatan_banyak.status_code == 413
    assert r_hambatan_banyak.json()["error"]["code"] == LK_TOO_MANY_ITEMS

    # Mode hambatan jenis tidak didukung -> 400 UNSUPPORTED_JENIS
    r_hambatan_bad_j = client.post(
        "/api/listrik",
        data={"mode": "hambatan", "jenis": "segitiga", "daftar": "10\n20"},
    )
    assert r_hambatan_bad_j.status_code == 400
    assert r_hambatan_bad_j.json()["error"]["code"] == LK_UNSUPPORTED_JENIS


def test_http_listrik_root_endpoint() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.get("/")
    assert resp.status_code == 200
    tools = resp.json()["tools"]
    assert "listrik" in tools


# --- Uji HTTP ke server yang benar-benar jalan ------------------------------
def test_http_live_jika_env_diisi() -> None:
    """Jalankan hanya bila OMNITOOLS_API_URL diisi, mis. http://127.0.0.1:8077."""
    base = os.getenv("OMNITOOLS_API_URL", "").rstrip("/")
    if not base:
        SKIPPED.append("uji live dilewati: OMNITOOLS_API_URL tidak diisi")
        return

    with urllib.request.urlopen(base + "/health", timeout=10) as response:
        assert response.status == 200
        assert json.loads(response.read())["status"] == "ok"

    # Merge 2 + 3 halaman lewat multipart/form-data sungguhan.
    boundary = "----omnitoolsuji"
    parts: list[bytes] = []
    for name, payload in (("a.pdf", make_pdf(2)), ("b.pdf", make_pdf(3))):
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="files"; filename="{name}"\r\n'
                "Content-Type: application/pdf\r\n\r\n"
            ).encode()
            + payload
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    request = urllib.request.Request(
        base + "/api/pdf/merge",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            disposition = response.headers.get("Content-Disposition", "")
            cache = response.headers.get("Cache-Control", "")
            pages_header = response.headers.get("X-Page-Count", "")
            data = response.read()
    except urllib.error.HTTPError as exc:
        raise AssertionError(f"merge live gagal: HTTP {exc.code} {exc.read()[:200]!r}") from exc

    assert status == 200
    assert content_type.startswith("application/pdf"), content_type
    assert 'filename="gabungan.pdf"' in disposition, disposition
    assert cache.startswith("no-store"), cache
    assert pages_header == "5", pages_header
    assert page_count(data) == 5

    # Word Count live lewat multipart/form-data
    boundary_wc = "----omnitoolswc"
    body_wc = (
        f"--{boundary_wc}\r\n"
        f'Content-Disposition: form-data; name="text"\r\n\r\n'
        f"Halo dunia. Ini uji coba!\r\n"
        f"--{boundary_wc}--\r\n"
    ).encode()
    req_wc = urllib.request.Request(
        base + "/api/word-count",
        data=body_wc,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary_wc}"},
    )
    with urllib.request.urlopen(req_wc, timeout=10) as resp:
        assert resp.status == 200
        wc_data = json.loads(resp.read().decode())
        assert wc_data["words"] == 5
        assert wc_data["chars"] == 25



# --- Uji Pomodoro Timer ----------------------------------------------------
def test_logika_pomodoro_klasik() -> None:
    res = compute_pomodoro("klasik")
    assert res["mode"] == "klasik"
    assert res["kerja_menit"] == 25
    assert res["istirahat_menit"] == 5
    assert res["istirahat_panjang_menit"] == 15
    assert res["sesi_fokus"] == 4
    assert res["jumlah_langkah"] == 7
    assert res["total_fokus_detik"] == 4 * 25 * 60
    assert res["total_istirahat_detik"] == 3 * 5 * 60
    assert res["total_detik"] == res["total_fokus_detik"] + res["total_istirahat_detik"]
    assert "perkiraan_selesai" not in res

    # Periksa langkah satu per satu
    langkah = res["langkah"]
    assert len(langkah) == 7
    assert langkah[0]["urutan"] == 1
    assert langkah[0]["jenis"] == "fokus"
    assert langkah[0]["label"] == "Fokus sesi 1"
    assert langkah[0]["durasi_detik"] == 1500
    assert langkah[0]["mulai_detik"] == 0
    assert langkah[0]["selesai_detik"] == 1500
    assert "jam_mulai" not in langkah[0]

    assert langkah[1]["urutan"] == 2
    assert langkah[1]["jenis"] == "istirahat"
    assert langkah[1]["label"] == "Istirahat pendek"
    assert langkah[1]["durasi_detik"] == 300
    assert langkah[1]["mulai_detik"] == 1500
    assert langkah[1]["selesai_detik"] == 1800

    assert langkah[6]["urutan"] == 7
    assert langkah[6]["jenis"] == "fokus"
    assert langkah[6]["label"] == "Fokus sesi 4"
    assert langkah[6]["durasi_detik"] == 1500
    assert langkah[6]["mulai_detik"] == 5400
    assert langkah[6]["selesai_detik"] == 6900


def test_logika_pomodoro_siklus_istirahat_panjang() -> None:
    # 5 sesi: sesi 4 diikuti istirahat panjang, lalu fokus sesi 5 (terakhir, tanpa istirahat)
    res5 = compute_pomodoro("klasik", sesi=5)
    assert res5["sesi_fokus"] == 5
    assert res5["jumlah_langkah"] == 9
    langkah5 = res5["langkah"]

    # Langkah 7: fokus sesi 4
    assert langkah5[6]["jenis"] == "fokus"
    assert langkah5[6]["label"] == "Fokus sesi 4"
    # Langkah 8: istirahat panjang
    assert langkah5[7]["jenis"] == "istirahat_panjang"
    assert langkah5[7]["label"] == "Istirahat panjang"
    assert langkah5[7]["durasi_detik"] == 15 * 60
    # Langkah 9: fokus sesi 5
    assert langkah5[8]["jenis"] == "fokus"
    assert langkah5[8]["label"] == "Fokus sesi 5"

    # 1 sesi: hanya fokus 1 langkah saja
    res1 = compute_pomodoro("klasik", sesi=1)
    assert res1["jumlah_langkah"] == 1
    assert res1["langkah"][0]["label"] == "Fokus sesi 1"
    assert res1["total_istirahat_detik"] == 0

    # 8 sesi: sesi 4 ada istirahat panjang, sesi 8 terakhir tanpa istirahat
    res8 = compute_pomodoro("klasik", sesi=8)
    assert res8["jumlah_langkah"] == 15
    assert res8["langkah"][7]["jenis"] == "istirahat_panjang"
    assert res8["langkah"][14]["jenis"] == "fokus"
    assert res8["langkah"][14]["label"] == "Fokus sesi 8"


def test_logika_pomodoro_mode_panjang_dan_pendek() -> None:
    res_p = compute_pomodoro("panjang")
    assert res_p["kerja_menit"] == 50
    assert res_p["istirahat_menit"] == 10
    assert res_p["istirahat_panjang_menit"] == 20
    assert res_p["sesi_fokus"] == 4

    res_s = compute_pomodoro("pendek")
    assert res_s["kerja_menit"] == 15
    assert res_s["istirahat_menit"] == 3
    assert res_s["istirahat_panjang_menit"] == 12
    assert res_s["sesi_fokus"] == 4


def test_logika_pomodoro_kustom() -> None:
    res_k = compute_pomodoro(
        "kustom",
        kerja=35,
        istirahat=7,
        istirahat_panjang=22,
        sesi=3,
    )
    assert res_k["mode"] == "kustom"
    assert res_k["kerja_menit"] == 35
    assert res_k["istirahat_menit"] == 7
    assert res_k["istirahat_panjang_menit"] == 22
    assert res_k["sesi_fokus"] == 3
    assert res_k["jumlah_langkah"] == 5


def test_logika_pomodoro_dengan_jam_mulai() -> None:
    res = compute_pomodoro("klasik", sesi=2, mulai="08:00")
    assert "perkiraan_selesai" in res
    assert res["perkiraan_selesai"] == "08:55"
    assert res["langkah"][0]["jam_mulai"] == "08:00"
    assert res["langkah"][0]["jam_selesai"] == "08:25"
    assert res["langkah"][1]["jam_mulai"] == "08:25"
    assert res["langkah"][1]["jam_selesai"] == "08:30"
    assert res["langkah"][2]["jam_mulai"] == "08:30"
    assert res["langkah"][2]["jam_selesai"] == "08:55"

    # Uji jam mulai melewati tengah malam
    res_mid = compute_pomodoro("klasik", sesi=1, mulai="23:50")
    assert res_mid["langkah"][0]["jam_mulai"] == "23:50"
    assert res_mid["langkah"][0]["jam_selesai"] == "00:15"
    assert res_mid["perkiraan_selesai"] == "00:15"


def test_logika_pomodoro_galat() -> None:
    # Mode kosong atau bukan string
    try:
        compute_pomodoro(None)
        assert False, "Harusnya gagal mode None"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_REQUEST

    try:
        compute_pomodoro("")
        assert False, "Harusnya gagal mode kosong"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_REQUEST

    try:
        compute_pomodoro(123)
        assert False, "Harusnya gagal mode bukan string"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_REQUEST

    # Mode tidak didukung
    try:
        compute_pomodoro("ngawur")
        assert False, "Harusnya gagal mode tidak didukung"
    except PomodoroError as exc:
        assert exc.code == PM_UNSUPPORTED_MODE

    # Bilangan tidak valid (bukan angka)
    try:
        compute_pomodoro("kustom", kerja="bukan_angka")
        assert False, "Harusnya gagal bukan angka"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_NUMBER

    try:
        compute_pomodoro("kustom", kerja="12.5")
        assert False, "Harusnya gagal angka desimal"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_NUMBER

    # Di luar rentang kerja (1..180)
    try:
        compute_pomodoro("kustom", kerja=0)
        assert False, "Harusnya gagal kerja 0"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_RANGE

    try:
        compute_pomodoro("kustom", kerja=181)
        assert False, "Harusnya gagal kerja 181"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_RANGE

    # Di luar rentang istirahat (1..60)
    try:
        compute_pomodoro("kustom", istirahat=0)
        assert False, "Harusnya gagal istirahat 0"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_RANGE

    try:
        compute_pomodoro("kustom", istirahat=61)
        assert False, "Harusnya gagal istirahat 61"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_RANGE

    # Di luar rentang istirahat panjang (1..90)
    try:
        compute_pomodoro("kustom", istirahat_panjang=0)
        assert False, "Harusnya gagal istirahat panjang 0"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_RANGE

    try:
        compute_pomodoro("kustom", istirahat_panjang=91)
        assert False, "Harusnya gagal istirahat panjang 91"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_RANGE

    # Di luar rentang sesi (1..12)
    try:
        compute_pomodoro("klasik", sesi=0)
        assert False, "Harusnya gagal sesi 0"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_RANGE

    try:
        compute_pomodoro("klasik", sesi=13)
        assert False, "Harusnya gagal sesi 13"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_RANGE

    # Format jam mulai tidak valid
    try:
        compute_pomodoro("klasik", mulai="8:00")
        assert False, "Harusnya gagal jam 8:00"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_START_TIME

    try:
        compute_pomodoro("klasik", mulai="25:00")
        assert False, "Harusnya gagal jam 25:00"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_START_TIME

    try:
        compute_pomodoro("klasik", mulai="12:60")
        assert False, "Harusnya gagal jam 12:60"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_START_TIME

    try:
        compute_pomodoro("klasik", mulai="jam_pagi")
        assert False, "Harusnya gagal jam teks"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_START_TIME

    # Masukan melebihi 40 karakter
    try:
        compute_pomodoro("klasik", kerja="1" * 45)
        assert False, "Harusnya gagal masukan > 40 karakter"
    except PomodoroError as exc:
        assert exc.code == PM_INVALID_RANGE


def test_http_pomodoro_limits() -> None:
    client = _test_client()
    if client is None:
        return

    resp = client.get("/api/pomodoro/limits")
    assert resp.status_code == 200, resp.text
    assert "no-store" in resp.headers.get("Cache-Control", "")
    data = resp.json()
    assert data["tool"] == "pomodoro"
    assert data["max_input_chars"] == 40
    assert data["max_bytes"] == 65536
    assert isinstance(data["modes"], list)
    assert len(data["modes"]) == 4
    mode_ids = [m["id"] for m in data["modes"]]
    assert mode_ids == ["klasik", "panjang", "pendek", "kustom"]
    assert "limits" in data
    assert data["limits"]["kerja"]["min"] == 1
    assert data["limits"]["kerja"]["max"] == 180
    assert data["limits"]["sesi"]["min"] == 1
    assert data["limits"]["sesi"]["max"] == 12


def test_http_pomodoro_sukses() -> None:
    client = _test_client()
    if client is None:
        return

    # 1. Mode klasik dengan mulai
    resp_klasik = client.post(
        "/api/pomodoro",
        data={"mode": "klasik", "sesi": "4", "mulai": "08:30"},
    )
    assert resp_klasik.status_code == 200, resp_klasik.text
    body_k = resp_klasik.json()
    assert body_k["mode"] == "klasik"
    assert body_k["kerja_menit"] == 25
    assert body_k["istirahat_menit"] == 5
    assert body_k["sesi_fokus"] == 4
    assert body_k["jumlah_langkah"] == 7
    assert body_k["perkiraan_selesai"] == "10:25"
    assert "no-store" in resp_klasik.headers.get("Cache-Control", "")
    assert resp_klasik.headers.get("Pragma") == "no-cache"
    assert "X-Processing-Ms" in resp_klasik.headers

    # 2. Mode kustom
    resp_kustom = client.post(
        "/api/pomodoro",
        data={
            "mode": "kustom",
            "kerja": "40",
            "istirahat": "8",
            "istirahat_panjang": "20",
            "sesi": "3",
        },
    )
    assert resp_kustom.status_code == 200, resp_kustom.text
    body_c = resp_kustom.json()
    assert body_c["mode"] == "kustom"
    assert body_c["kerja_menit"] == 40
    assert body_c["istirahat_menit"] == 8
    assert body_c["istirahat_panjang_menit"] == 20
    assert body_c["sesi_fokus"] == 3
    assert body_c["jumlah_langkah"] == 5


def test_http_pomodoro_galat() -> None:
    client = _test_client()
    if client is None:
        return

    # Tanpa field mode -> 400 INVALID_REQUEST
    resp_no_mode = client.post("/api/pomodoro", data={"kerja": "25"})
    assert resp_no_mode.status_code == 400, resp_no_mode.text
    assert resp_no_mode.json()["error"]["code"] == PM_INVALID_REQUEST

    # Mode tidak dikenal -> 400 UNSUPPORTED_MODE
    resp_bad_mode = client.post("/api/pomodoro", data={"mode": "acak"})
    assert resp_bad_mode.status_code == 400, resp_bad_mode.text
    assert resp_bad_mode.json()["error"]["code"] == PM_UNSUPPORTED_MODE

    # Kerja bukan angka -> 400 INVALID_NUMBER
    resp_bad_num = client.post("/api/pomodoro", data={"mode": "kustom", "kerja": "sepuluh"})
    assert resp_bad_num.status_code == 400, resp_bad_num.text
    assert resp_bad_num.json()["error"]["code"] == PM_INVALID_NUMBER

    # Kerja di luar batas -> 400 INVALID_RANGE
    resp_bad_range = client.post("/api/pomodoro", data={"mode": "kustom", "kerja": "300"})
    assert resp_bad_range.status_code == 400, resp_bad_range.text
    assert resp_bad_range.json()["error"]["code"] == PM_INVALID_RANGE

    # Jam mulai salah format -> 400 INVALID_START_TIME
    resp_bad_time = client.post("/api/pomodoro", data={"mode": "klasik", "mulai": "08.00"})
    assert resp_bad_time.status_code == 400, resp_bad_time.text
    assert resp_bad_time.json()["error"]["code"] == PM_INVALID_START_TIME

    # Body JSON (bukan multipart) -> 400 INVALID_REQUEST
    resp_json = client.post("/api/pomodoro", json={"mode": "klasik"})
    assert resp_json.status_code == 400, resp_json.text
    assert resp_json.json()["error"]["code"] == PM_INVALID_REQUEST

    # Body > 64 KB -> 413 PAYLOAD_TOO_LARGE
    resp_large = client.post("/api/pomodoro", data={"mode": "klasik", "ekstra": "x" * 70000})
    assert resp_large.status_code == 413, resp_large.text
    assert resp_large.json()["error"]["code"] == PM_PAYLOAD_TOO_LARGE


def test_http_pomodoro_root_endpoint_dan_regresi() -> None:
    client = _test_client()
    if client is None:
        return

    root_resp = client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert "pomodoro" in root_data["tools"]
    assert "countdown" in root_data["tools"]
    assert "listrik" in root_data["tools"]


# --- Uji Pisah PDF (PDF Splitter) --------------------------------------------
def test_pdf_split_inspect_pdf() -> None:
    pdf_3 = make_pdf(3)
    info = inspect_pdf(pdf_3)
    assert info.page_count == 3
    assert info.size_bytes == len(pdf_3)
    d = info.to_dict()
    assert d["page_count"] == 3
    assert d["max_pages"] == 300


def test_pdf_split_per_halaman_3_halaman() -> None:
    pdf_3 = make_pdf(3)
    result = split_pdf(pdf_3, mode="per-halaman")
    assert isinstance(result, SplitResult)
    assert result.output_kind == "zip"
    assert result.output_name == "pisah-pdf.zip"
    assert result.output_count == 3
    assert result.source_pages == 3
    assert result.result_pages == 3
    assert result.first_page == 1
    assert result.last_page == 3

    import zipfile
    with zipfile.ZipFile(io.BytesIO(result.data), "r") as zf:
        names = zf.namelist()
        assert names == ["halaman-01.pdf", "halaman-02.pdf", "halaman-03.pdf"]
        for name in names:
            entry_bytes = zf.read(name)
            assert entry_bytes.startswith(b"%PDF-")
            reader = PdfReader(io.BytesIO(entry_bytes))
            assert len(reader.pages) == 1


def test_pdf_split_per_halaman_1_halaman() -> None:
    pdf_1 = make_pdf(1)
    result = split_pdf(pdf_1, mode="per-halaman")
    assert isinstance(result, SplitResult)
    assert result.output_kind == "pdf"
    assert result.output_name == "pisah-pdf.pdf"
    assert result.output_count == 1
    assert result.source_pages == 1
    assert result.result_pages == 1
    assert result.first_page == 1
    assert result.last_page == 1
    assert page_count(result.data) == 1


def test_pdf_split_rentang_sukses() -> None:
    pdf_5 = make_pdf(5)

    # Rentang 1-3 -> 3 halaman
    res1 = split_pdf(pdf_5, mode="rentang", pages="1-3")
    assert isinstance(res1, SplitResult)
    assert res1.output_kind == "pdf"
    assert res1.output_name == "pisah-pdf.pdf"
    assert res1.output_count == 1
    assert res1.source_pages == 5
    assert res1.result_pages == 3
    assert res1.first_page == 1
    assert res1.last_page == 3
    assert page_count(res1.data) == 3

    # Rentang 2,4 -> 2 halaman
    res2 = split_pdf(pdf_5, mode="rentang", pages="2,4")
    assert isinstance(res2, SplitResult)
    assert res2.output_kind == "pdf"
    assert res2.output_count == 1
    assert res2.source_pages == 5
    assert res2.result_pages == 2
    assert res2.first_page == 2
    assert res2.last_page == 4
    assert page_count(res2.data) == 2

    # Rentang tumpang tindih 1-3,2 -> 3 halaman (tanpa duplikat, urut)
    res3 = split_pdf(pdf_5, mode="rentang", pages="1-3,2")
    assert isinstance(res3, SplitResult)
    assert res3.output_kind == "pdf"
    assert res3.output_count == 1
    assert res3.source_pages == 5
    assert res3.result_pages == 3
    assert page_count(res3.data) == 3


def test_pdf_split_rentang_invalid() -> None:
    pdf_5 = make_pdf(5)
    for invalid in ["3-1", "0", "abc", "1-99", "", "   ", "1-3-5", "-2"]:
        expect_split_error(
            lambda inv=invalid: split_pdf(pdf_5, mode="rentang", pages=inv),
            SPLIT_ERR_INVALID_PAGES,
            400,
        )


def test_pdf_split_setiap_n_chunk_2_dari_5_halaman() -> None:
    pdf_5 = make_pdf(5)
    result = split_pdf(pdf_5, mode="setiap-n", chunk=2)
    assert isinstance(result, SplitResult)
    assert result.output_kind == "zip"
    assert result.output_name == "pisah-pdf.zip"
    assert result.output_count == 3
    assert result.source_pages == 5
    assert result.result_pages == 5
    assert result.first_page == 1
    assert result.last_page == 5

    import zipfile
    with zipfile.ZipFile(io.BytesIO(result.data), "r") as zf:
        names = zf.namelist()
        assert names == ["bagian-01.pdf", "bagian-02.pdf", "bagian-03.pdf"]
        assert len(PdfReader(io.BytesIO(zf.read("bagian-01.pdf"))).pages) == 2
        assert len(PdfReader(io.BytesIO(zf.read("bagian-02.pdf"))).pages) == 2
        assert len(PdfReader(io.BytesIO(zf.read("bagian-03.pdf"))).pages) == 1


def test_pdf_split_setiap_n_chunk_lebih_besar_dari_halaman() -> None:
    pdf_5 = make_pdf(5)
    result = split_pdf(pdf_5, mode="setiap-n", chunk=10)
    assert isinstance(result, SplitResult)
    assert result.output_kind == "pdf"
    assert result.output_name == "pisah-pdf.pdf"
    assert result.output_count == 1
    assert result.source_pages == 5
    assert result.result_pages == 5
    assert page_count(result.data) == 5


def test_pdf_split_logika_galat() -> None:
    pdf_1 = make_pdf(1)

    # Tanpa berkas / berkas kosong / bukan PDF
    expect_split_error(lambda: split_pdf(None, mode="per-halaman"), SPLIT_ERR_NO_FILE, 400)
    expect_split_error(lambda: split_pdf(b"", mode="per-halaman"), SPLIT_ERR_EMPTY_FILE, 400)
    expect_split_error(lambda: split_pdf(b"bukan pdf sama sekali", mode="per-halaman"), SPLIT_ERR_NOT_PDF, 400)

    # Mode tidak dikenal
    expect_split_error(lambda: split_pdf(pdf_1, mode="acak"), SPLIT_ERR_UNSUPPORTED_MODE, 400)

    # Chunk tidak valid
    expect_split_error(lambda: split_pdf(pdf_1, mode="setiap-n", chunk=0), SPLIT_ERR_INVALID_CHUNK, 400)
    expect_split_error(lambda: split_pdf(pdf_1, mode="setiap-n", chunk=101), SPLIT_ERR_INVALID_CHUNK, 400)
    expect_split_error(lambda: split_pdf(pdf_1, mode="setiap-n", chunk="abc"), SPLIT_ERR_INVALID_CHUNK, 400)

    # PDF rusak / terenkripsi
    rusak = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog\n" + b"x" * 200
    expect_split_error(lambda: split_pdf(rusak, mode="per-halaman"), SPLIT_ERR_PDF_UNREADABLE, 422)
    expect_split_error(lambda: split_pdf(make_encrypted_pdf(1), mode="per-halaman"), SPLIT_ERR_PDF_ENCRYPTED, 422)

    # Ukuran / halaman lewat batas
    expect_split_error(lambda: check_split_size(SPLIT_MAX_FILE_BYTES + 1), SPLIT_ERR_PAYLOAD_TOO_LARGE, 413)
    banyak = make_pdf(SPLIT_MAX_PAGES + 1)
    expect_split_error(lambda: split_pdf(banyak, mode="per-halaman"), SPLIT_ERR_TOO_MANY_PAGES, 413)


def test_http_pdf_split_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/pdf/split/limits")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["max_file_bytes"] == 26214400
    assert data["max_file_mb"] == 25
    assert data["max_pages"] == 300
    assert data["default_chunk"] == 5
    assert data["min_chunk"] == 1
    assert data["max_chunk"] == 100
    assert data["sample_range"] == "1-3,5"
    assert isinstance(data["modes"], list)
    mode_ids = [m["id"] for m in data["modes"]]
    assert mode_ids == ["per-halaman", "rentang", "setiap-n"]
    assert "no-store" in response.headers.get("Cache-Control", "")


def test_http_pdf_split_info_mode() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/pdf/split",
        files=[("file", ("dokumen.pdf", make_pdf(4), "application/pdf"))],
        data={"mode": "info"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["page_count"] == 4
    assert data["size_bytes"] > 0
    assert data["max_pages"] == 300
    assert "no-store" in response.headers.get("Cache-Control", "")


def test_http_pdf_split_per_halaman_zip() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/pdf/split",
        files=[("file", ("dokumen.pdf", make_pdf(3), "application/pdf"))],
        data={"mode": "per-halaman"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/zip")
    assert 'filename="pisah-pdf.zip"' in response.headers.get("content-disposition", "")
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert response.headers.get("X-Output-Kind") == "zip"
    assert response.headers.get("X-Output-Count") == "3"
    assert response.headers.get("X-Source-Pages") == "3"
    assert response.headers.get("X-Result-Pages") == "3"
    assert response.headers.get("X-First-Page") == "1"
    assert response.headers.get("X-Last-Page") == "3"

    import zipfile
    with zipfile.ZipFile(io.BytesIO(response.content), "r") as zf:
        names = zf.namelist()
        assert names == ["halaman-01.pdf", "halaman-02.pdf", "halaman-03.pdf"]


def test_http_pdf_split_per_halaman_single_pdf() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/pdf/split",
        files=[("file", ("dokumen.pdf", make_pdf(1), "application/pdf"))],
        data={"mode": "per-halaman"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert 'filename="pisah-pdf.pdf"' in response.headers.get("content-disposition", "")
    assert response.headers.get("X-Output-Kind") == "pdf"
    assert response.headers.get("X-Output-Count") == "1"
    assert response.headers.get("X-Source-Pages") == "1"
    assert response.headers.get("X-Result-Pages") == "1"
    assert page_count(response.content) == 1


def test_http_pdf_split_rentang_pdf() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.post(
        "/api/pdf/split",
        files=[("file", ("dokumen.pdf", make_pdf(5), "application/pdf"))],
        data={"mode": "rentang", "pages": "1-3"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert 'filename="pisah-pdf.pdf"' in response.headers.get("content-disposition", "")
    assert response.headers.get("X-Output-Count") == "1"
    assert response.headers.get("X-Result-Pages") == "3"
    assert response.headers.get("X-First-Page") == "1"
    assert response.headers.get("X-Last-Page") == "3"
    assert page_count(response.content) == 3


def test_http_pdf_split_galat() -> None:
    client = _test_client()
    if client is None:
        return

    # Tanpa file -> 400 NO_FILE
    r_no_file = client.post("/api/pdf/split", data={"mode": "per-halaman"})
    assert r_no_file.status_code == 400, r_no_file.text
    assert r_no_file.json()["error"]["code"] == SPLIT_ERR_NO_FILE

    # Berkas kosong -> 400 EMPTY_FILE
    r_empty = client.post(
        "/api/pdf/split",
        files=[("file", ("kosong.pdf", b"", "application/pdf"))],
        data={"mode": "per-halaman"},
    )
    assert r_empty.status_code == 400, r_empty.text
    assert r_empty.json()["error"]["code"] == SPLIT_ERR_EMPTY_FILE

    # Bukan PDF -> 400 NOT_PDF
    r_not_pdf = client.post(
        "/api/pdf/split",
        files=[("file", ("catatan.txt", b"halo ini teks", "text/plain"))],
        data={"mode": "per-halaman"},
    )
    assert r_not_pdf.status_code == 400, r_not_pdf.text
    assert r_not_pdf.json()["error"]["code"] == SPLIT_ERR_NOT_PDF

    # Mode tidak dikenal -> 400 UNSUPPORTED_MODE
    r_bad_mode = client.post(
        "/api/pdf/split",
        files=[("file", ("doc.pdf", make_pdf(1), "application/pdf"))],
        data={"mode": "mode_ngawur"},
    )
    assert r_bad_mode.status_code == 400, r_bad_mode.text
    assert r_bad_mode.json()["error"]["code"] == SPLIT_ERR_UNSUPPORTED_MODE

    # Chunk tidak valid -> 400 INVALID_CHUNK
    for chunk_val in ["0", "101", "abc"]:
        r_chunk = client.post(
            "/api/pdf/split",
            files=[("file", ("doc.pdf", make_pdf(1), "application/pdf"))],
            data={"mode": "setiap-n", "chunk": chunk_val},
        )
        assert r_chunk.status_code == 400, r_chunk.text
        assert r_chunk.json()["error"]["code"] == SPLIT_ERR_INVALID_CHUNK

    # PDF rusak -> 422 PDF_UNREADABLE
    rusak = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog\n" + b"x" * 200
    r_rusak = client.post(
        "/api/pdf/split",
        files=[("file", ("rusak.pdf", rusak, "application/pdf"))],
        data={"mode": "per-halaman"},
    )
    assert r_rusak.status_code == 422, r_rusak.text
    assert r_rusak.json()["error"]["code"] == SPLIT_ERR_PDF_UNREADABLE

    # PDF terenkripsi -> 422 PDF_ENCRYPTED
    r_enc = client.post(
        "/api/pdf/split",
        files=[("file", ("rahasia.pdf", make_encrypted_pdf(1), "application/pdf"))],
        data={"mode": "per-halaman"},
    )
    assert r_enc.status_code == 422, r_enc.text
    assert r_enc.json()["error"]["code"] == SPLIT_ERR_PDF_ENCRYPTED


def test_http_pdf_split_regresi_dan_root() -> None:
    client = _test_client()
    if client is None:
        return

    # Root memiliki pdf-split di daftar alat
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert "pdf-split" in root_data["tools"]

    # Endpoint limits lama tetap 200
    assert client.get("/api/pdf/merge/limits").status_code == 200
    assert client.get("/api/image/convert/limits").status_code == 200
    assert client.get("/api/word-count/limits").status_code == 200
    assert client.get("/health").status_code == 200


def test_http_pdf_split_live_bila_tersedia() -> None:
    base = os.getenv("OMNITOOLS_API_URL", "").rstrip("/")
    if not base:
        return
    req = urllib.request.Request(f"{base}/api/pdf/split/limits")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
def test_pdf_compress_logika_dasar() -> None:
    pdf_data = make_pdf(2)

    # Inspect
    info = inspect_compress_pdf(pdf_data)
    assert isinstance(info, CompressPdfInfo)
    assert info.page_count == 2
    assert info.size_bytes == len(pdf_data)

    # Ringan
    res_ringan = compress_pdf(pdf_data, mode="ringan")
    assert isinstance(res_ringan, CompressResult)
    assert res_ringan.page_count == 2
    assert res_ringan.mode == "ringan"
    assert res_ringan.keep_text is True
    assert isinstance(res_ringan.data, bytes)
    assert len(res_ringan.data) > 0

    # Sedang
    res_sedang = compress_pdf(pdf_data, mode="sedang")
    assert isinstance(res_sedang, CompressResult)
    assert res_sedang.page_count == 2
    assert res_sedang.mode == "sedang"
    assert res_sedang.keep_text is True

    # Kuat
    res_kuat = compress_pdf(pdf_data, mode="kuat", dpi=90, quality=50)
    assert isinstance(res_kuat, CompressResult)
    assert res_kuat.page_count == 2
    assert res_kuat.mode == "kuat"
    assert res_kuat.keep_text is False

    # DPI & Quality parsing
    assert parse_dpi(None) == COMPRESS_DEFAULT_DPI
    assert parse_dpi("120") == 120
    assert parse_quality(None) == COMPRESS_DEFAULT_QUALITY
    assert parse_quality("75") == 75

    expect_compress_error(lambda: parse_dpi(50), COMPRESS_ERR_INVALID_DPI, 400)
    expect_compress_error(lambda: parse_dpi(300), COMPRESS_ERR_INVALID_DPI, 400)
    expect_compress_error(lambda: parse_quality(10), COMPRESS_ERR_INVALID_QUALITY, 400)
    expect_compress_error(lambda: parse_quality(100), COMPRESS_ERR_INVALID_QUALITY, 400)


def test_pdf_compress_logika_gambar_dan_fallback() -> None:
    def make_pdf_with_image(pages: int = 1) -> bytes:
        import fitz
        doc = fitz.open()
        for _ in range(pages):
            page = doc.new_page(width=300, height=300)
            img_bytes = make_image("JPEG", size=(200, 200), color="blue")
            rect = fitz.Rect(20, 20, 280, 280)
            page.insert_image(rect, stream=img_bytes)
        buf = io.BytesIO()
        doc.save(buf)
        data = buf.getvalue()
        doc.close()
        return data

    # Dokumen dengan gambar
    pdf_img = make_pdf_with_image(pages=3)
    res_kuat = compress_pdf(pdf_img, mode="kuat", dpi=72, quality=40)
    assert isinstance(res_kuat, CompressResult)
    assert res_kuat.page_count == 3
    assert res_kuat.keep_text is False
    assert len(res_kuat.notes) >= 1

    # Cek dokumen yang sudah efisien: used_original bernilai True
    tiny_pdf = make_pdf(1)
    res_tiny = compress_pdf(tiny_pdf, mode="ringan")
    assert isinstance(res_tiny, CompressResult)
    assert res_tiny.used_original is True
    assert res_tiny.size_after == res_tiny.size_before
    assert res_tiny.data == tiny_pdf
    # (b) catatan fallback tetap muncul saat hasil tidak lebih kecil
    assert any("Berkas aslinya sudah efisien, jadi hasil kompresi tidak lebih kecil" in note for note in res_tiny.notes)

    # (c) untuk mode kuat yang jatuh ke fallback, catatan lanjutan "Tingkat Sedang atau Ringan bisa dicoba" juga muncul
    res_kuat_fallback = compress_pdf(tiny_pdf, mode="kuat")
    assert res_kuat_fallback.used_original is True
    assert any("Berkas aslinya sudah efisien, jadi hasil kompresi tidak lebih kecil" in note for note in res_kuat_fallback.notes)
    assert any("Rasterisasi tidak membuat berkas ini lebih kecil. Tingkat Sedang atau Ringan bisa dicoba sebagai perbandingan." in note for note in res_kuat_fallback.notes)

    # Uji dokumen multi-halaman (20 halaman) pada mode kuat yang jatuh ke fallback
    pdf_20 = make_pdf(20)
    res_20_kuat = compress_pdf(pdf_20, mode="kuat")
    assert res_20_kuat.used_original is True
    assert any("Rasterisasi tidak membuat berkas ini lebih kecil. Tingkat Sedang atau Ringan bisa dicoba sebagai perbandingan." in note for note in res_20_kuat.notes)

    # (a) catatan "Penghematannya sangat kecil" muncul untuk PDF yang hasil kompresinya hampir sama besarnya (< 1%)
    doc_clean = pymupdf.open()
    doc_clean.new_page(width=300, height=300)
    buf_clean = io.BytesIO()
    doc_clean.save(
        buf_clean,
        garbage=4,
        deflate=True,
        deflate_images=True,
        deflate_fonts=True,
        clean=True,
    )
    clean_bytes = buf_clean.getvalue()
    doc_clean.close()

    pdf_near_equal = clean_bytes + b"\n%"
    res_near = compress_pdf(pdf_near_equal, mode="ringan")
    assert res_near.used_original is False
    assert len(res_near.data) < len(pdf_near_equal)
    assert (len(pdf_near_equal) - len(res_near.data)) * 100 / len(pdf_near_equal) < 1
    assert any("Penghematannya sangat kecil (di bawah 1 persen)" in note for note in res_near.notes)


def test_pdf_compress_logika_galat() -> None:
    pdf_1 = make_pdf(1)

    # Tanpa berkas / berkas kosong / bukan PDF
    expect_compress_error(lambda: compress_pdf(None, mode="ringan"), COMPRESS_ERR_NO_FILE, 400)
    expect_compress_error(lambda: compress_pdf(b"", mode="ringan"), COMPRESS_ERR_EMPTY_FILE, 400)
    expect_compress_error(lambda: compress_pdf(b"bukan pdf sama sekali", mode="ringan"), COMPRESS_ERR_NOT_PDF, 400)

    # Mode tidak dikenal
    expect_compress_error(lambda: compress_pdf(pdf_1, mode="acak"), COMPRESS_ERR_UNSUPPORTED_MODE, 400)

    # DPI / Kualitas di luar rentang
    expect_compress_error(lambda: compress_pdf(pdf_1, mode="kuat", dpi=50), COMPRESS_ERR_INVALID_DPI, 400)
    expect_compress_error(lambda: compress_pdf(pdf_1, mode="kuat", dpi=250), COMPRESS_ERR_INVALID_DPI, 400)
    expect_compress_error(lambda: compress_pdf(pdf_1, mode="kuat", quality=20), COMPRESS_ERR_INVALID_QUALITY, 400)
    expect_compress_error(lambda: compress_pdf(pdf_1, mode="kuat", quality=99), COMPRESS_ERR_INVALID_QUALITY, 400)

    # PDF rusak / terenkripsi
    rusak = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog\n" + b"x" * 200
    expect_compress_error(lambda: compress_pdf(rusak, mode="ringan"), COMPRESS_ERR_PDF_UNREADABLE, 422)
    expect_compress_error(lambda: compress_pdf(make_encrypted_pdf(1), mode="ringan"), COMPRESS_ERR_PDF_ENCRYPTED, 422)

    # Ukuran / halaman lewat batas
    expect_compress_error(lambda: check_compress_size(COMPRESS_MAX_FILE_BYTES + 1), COMPRESS_ERR_PAYLOAD_TOO_LARGE, 413)
    banyak = make_pdf(COMPRESS_MAX_PAGES + 1)
    expect_compress_error(lambda: compress_pdf(banyak, mode="ringan"), COMPRESS_ERR_TOO_MANY_PAGES, 413)


def test_http_pdf_compress_limits() -> None:
    client = _test_client()
    if client is None:
        return
    response = client.get("/api/pdf/compress/limits")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["max_file_bytes"] == 26214400
    assert data["max_file_mb"] == 25
    assert data["max_pages"] == 300
    assert data["dpi_min"] == 72
    assert data["dpi_max"] == 200
    assert data["dpi_default"] == 110
    assert data["quality_min"] == 30
    assert data["quality_max"] == 95
    assert data["quality_default"] == 60
    mode_ids = [m["id"] for m in data["modes"]]
    assert mode_ids == ["ringan", "sedang", "kuat"]
    assert "no-store" in response.headers.get("Cache-Control", "")


def test_http_pdf_compress_modes_sukses() -> None:
    client = _test_client()
    if client is None:
        return

    def make_pdf_with_image(pages: int = 1) -> bytes:
        import fitz
        doc = fitz.open()
        for _ in range(pages):
            page = doc.new_page(width=300, height=300)
            img_bytes = make_image("JPEG", size=(200, 200), color="blue")
            rect = fitz.Rect(20, 20, 280, 280)
            page.insert_image(rect, stream=img_bytes)
        buf = io.BytesIO()
        doc.save(buf)
        data = buf.getvalue()
        doc.close()
        return data

    pdf_3 = make_pdf_with_image(pages=3)

    # Mode ringan
    r_ringan = client.post(
        "/api/pdf/compress",
        files=[("file", ("dokumen.pdf", pdf_3, "application/pdf"))],
        data={"mode": "ringan"},
    )
    assert r_ringan.status_code == 200, r_ringan.text
    assert r_ringan.headers["content-type"].startswith("application/pdf")
    assert 'filename="kompres-pdf.pdf"' in r_ringan.headers.get("Content-Disposition", "")
    assert r_ringan.headers.get("X-Mode") == "ringan"
    assert r_ringan.headers.get("X-Keep-Text") == "true"
    assert r_ringan.headers.get("X-Page-Count") == "3"

    # Mode sedang
    r_sedang = client.post(
        "/api/pdf/compress",
        files=[("file", ("dokumen.pdf", pdf_3, "application/pdf"))],
        data={"mode": "sedang"},
    )
    assert r_sedang.status_code == 200, r_sedang.text
    assert r_sedang.headers["content-type"].startswith("application/pdf")
    assert r_sedang.headers.get("X-Mode") == "sedang"
    assert r_sedang.headers.get("X-Keep-Text") == "true"

    # Mode kuat
    r_kuat = client.post(
        "/api/pdf/compress",
        files=[("file", ("dokumen.pdf", pdf_3, "application/pdf"))],
        data={"mode": "kuat", "dpi": "80", "quality": "40"},
    )
    assert r_kuat.status_code == 200, r_kuat.text
    assert r_kuat.headers["content-type"].startswith("application/pdf")
    assert r_kuat.headers.get("X-Mode") == "kuat"
    assert r_kuat.headers.get("X-Keep-Text") == "false"
    assert "no-store" in r_kuat.headers.get("Cache-Control", "")


def test_http_pdf_compress_fallback_dan_catatan() -> None:
    client = _test_client()
    if client is None:
        return

    tiny_pdf = make_pdf(1)
    # Mode ringan fallback
    r_tiny = client.post(
        "/api/pdf/compress",
        files=[("file", ("dokumen.pdf", tiny_pdf, "application/pdf"))],
        data={"mode": "ringan"},
    )
    assert r_tiny.status_code == 200
    assert r_tiny.headers.get("X-Used-Original") == "true"
    assert r_tiny.headers.get("X-Saved-Percent") == "0"
    assert "Berkas aslinya sudah efisien" in r_tiny.headers.get("X-Notes", "")

    # Mode kuat fallback
    r_kuat = client.post(
        "/api/pdf/compress",
        files=[("file", ("dokumen.pdf", tiny_pdf, "application/pdf"))],
        data={"mode": "kuat"},
    )
    assert r_kuat.status_code == 200
    assert r_kuat.headers.get("X-Used-Original") == "true"
    assert "Rasterisasi tidak membuat berkas ini lebih kecil" in r_kuat.headers.get("X-Notes", "")

    # Mode ringan penghematan < 1%
    doc_clean = pymupdf.open()
    doc_clean.new_page(width=300, height=300)
    buf_clean = io.BytesIO()
    doc_clean.save(
        buf_clean,
        garbage=4,
        deflate=True,
        deflate_images=True,
        deflate_fonts=True,
        clean=True,
    )
    clean_bytes = buf_clean.getvalue()
    doc_clean.close()

    pdf_near = clean_bytes + b"\n%"
    r_near = client.post(
        "/api/pdf/compress",
        files=[("file", ("dokumen.pdf", pdf_near, "application/pdf"))],
        data={"mode": "ringan"},
    )
    assert r_near.status_code == 200
    assert r_near.headers.get("X-Used-Original") == "false"
    assert r_near.headers.get("X-Saved-Percent") == "0"
    assert "Penghematannya sangat kecil" in r_near.headers.get("X-Notes", "")


def test_http_pdf_compress_galat() -> None:
    client = _test_client()
    if client is None:
        return

    # Tanpa berkas -> 400 NO_FILE
    r_no_file = client.post("/api/pdf/compress", data={"mode": "ringan"})
    assert r_no_file.status_code == 400, r_no_file.text
    assert r_no_file.json()["error"]["code"] == COMPRESS_ERR_NO_FILE

    # Berkas kosong -> 400 EMPTY_FILE
    r_empty = client.post(
        "/api/pdf/compress",
        files=[("file", ("kosong.pdf", b"", "application/pdf"))],
        data={"mode": "ringan"},
    )
    assert r_empty.status_code == 400, r_empty.text
    assert r_empty.json()["error"]["code"] == COMPRESS_ERR_EMPTY_FILE

    # Bukan PDF -> 400 NOT_PDF
    r_not_pdf = client.post(
        "/api/pdf/compress",
        files=[("file", ("catatan.txt", b"halo ini bukan pdf", "text/plain"))],
        data={"mode": "ringan"},
    )
    assert r_not_pdf.status_code == 400, r_not_pdf.text
    assert r_not_pdf.json()["error"]["code"] == COMPRESS_ERR_NOT_PDF

    # Mode tidak dikenal -> 400 UNSUPPORTED_MODE
    r_bad_mode = client.post(
        "/api/pdf/compress",
        files=[("file", ("dokumen.pdf", make_pdf(1), "application/pdf"))],
        data={"mode": "ngawur"},
    )
    assert r_bad_mode.status_code == 400, r_bad_mode.text
    assert r_bad_mode.json()["error"]["code"] == COMPRESS_ERR_UNSUPPORTED_MODE

    # DPI tidak valid -> 400 INVALID_DPI
    r_bad_dpi = client.post(
        "/api/pdf/compress",
        files=[("file", ("dokumen.pdf", make_pdf(1), "application/pdf"))],
        data={"mode": "kuat", "dpi": "50"},
    )
    assert r_bad_dpi.status_code == 400, r_bad_dpi.text
    assert r_bad_dpi.json()["error"]["code"] == COMPRESS_ERR_INVALID_DPI

    # Quality tidak valid -> 400 INVALID_QUALITY
    r_bad_qual = client.post(
        "/api/pdf/compress",
        files=[("file", ("dokumen.pdf", make_pdf(1), "application/pdf"))],
        data={"mode": "kuat", "quality": "999"},
    )
    assert r_bad_qual.status_code == 400, r_bad_qual.text
    assert r_bad_qual.json()["error"]["code"] == COMPRESS_ERR_INVALID_QUALITY

    # PDF rusak -> 422 PDF_UNREADABLE
    rusak = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog\n" + b"x" * 200
    r_rusak = client.post(
        "/api/pdf/compress",
        files=[("file", ("rusak.pdf", rusak, "application/pdf"))],
        data={"mode": "ringan"},
    )
    assert r_rusak.status_code == 422, r_rusak.text
    assert r_rusak.json()["error"]["code"] == COMPRESS_ERR_PDF_UNREADABLE

    # PDF terenkripsi -> 422 PDF_ENCRYPTED
    r_enc = client.post(
        "/api/pdf/compress",
        files=[("file", ("rahasia.pdf", make_encrypted_pdf(1), "application/pdf"))],
        data={"mode": "ringan"},
    )
    assert r_enc.status_code == 422, r_enc.text
    assert r_enc.json()["error"]["code"] == COMPRESS_ERR_PDF_ENCRYPTED


def test_http_pdf_compress_regresi_dan_root() -> None:
    client = _test_client()
    if client is None:
        return

    # Root memiliki pdf-compress di daftar alat
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert "pdf-compress" in root_data["tools"]

    # Endpoint limits lama tetap 200
    assert client.get("/api/pdf/merge/limits").status_code == 200
    assert client.get("/api/pdf/split/limits").status_code == 200
    assert client.get("/api/pdf/compress/limits").status_code == 200


def test_pdf_to_image_logika_dasar() -> None:
    # Parsing format
    assert parse_pdf_to_image_format("PNG") == "png"
    assert parse_pdf_to_image_format("jpg") == "jpg"
    assert parse_pdf_to_image_format("JPEG") == "jpg"
    expect_pdf_to_image_error(lambda: parse_pdf_to_image_format("gif"), PDF_IMG_ERR_UNSUPPORTED_FORMAT, 400)
    expect_pdf_to_image_error(lambda: parse_pdf_to_image_format(None), PDF_IMG_ERR_UNSUPPORTED_FORMAT, 400)

    # Parsing DPI
    assert parse_pdf_to_image_dpi(None) == PDF_IMG_DEFAULT_DPI
    assert parse_pdf_to_image_dpi("") == PDF_IMG_DEFAULT_DPI
    assert parse_pdf_to_image_dpi("100") == 100
    assert parse_pdf_to_image_dpi(72) == 72
    assert parse_pdf_to_image_dpi(200) == 200
    expect_pdf_to_image_error(lambda: parse_pdf_to_image_dpi(50), PDF_IMG_ERR_INVALID_DPI, 400)
    expect_pdf_to_image_error(lambda: parse_pdf_to_image_dpi(201), PDF_IMG_ERR_INVALID_DPI, 400)
    expect_pdf_to_image_error(lambda: parse_pdf_to_image_dpi("abc"), PDF_IMG_ERR_INVALID_DPI, 400)

    # Parsing Quality
    assert parse_pdf_to_image_quality(None) == PDF_IMG_DEFAULT_QUALITY
    assert parse_pdf_to_image_quality("") == PDF_IMG_DEFAULT_QUALITY
    assert parse_pdf_to_image_quality("90") == 90
    assert parse_pdf_to_image_quality(30) == 30
    assert parse_pdf_to_image_quality(95) == 95
    expect_pdf_to_image_error(lambda: parse_pdf_to_image_quality(20), PDF_IMG_ERR_INVALID_QUALITY, 400)
    expect_pdf_to_image_error(lambda: parse_pdf_to_image_quality(100), PDF_IMG_ERR_INVALID_QUALITY, 400)

    # Limits payload
    payload = pdf_to_image_limits_payload_func()
    assert payload["max_file_bytes"] == PDF_IMG_MAX_FILE_BYTES
    assert payload["max_pages"] == PDF_IMG_MAX_PAGES
    assert payload["min_dpi"] == 72
    assert payload["max_dpi"] == 200
    assert payload["default_dpi"] == 150
    assert payload["min_quality"] == 30
    assert payload["max_quality"] == 95
    assert payload["default_quality"] == 85
    assert payload["formats"] == ["png", "jpg"]
    assert payload["max_output_bytes"] == PDF_IMG_MAX_OUTPUT_BYTES


def test_pdf_to_image_3_halaman_zip_dan_dpi() -> None:
    import zipfile
    import pymupdf

    doc = pymupdf.open()
    for _ in range(3):
        page = doc.new_page(width=200, height=200)
        page.draw_rect(pymupdf.Rect(10, 10, 100, 100), color=(1, 0, 0), fill=(0, 1, 0))
    buf = io.BytesIO()
    doc.save(buf)
    pdf_bytes = buf.getvalue()
    doc.close()

    # Render dengan DPI 72
    res_72 = pdf_to_image(pdf_bytes, format="png", dpi=72)
    assert res_72.output_kind == "zip"
    assert res_72.output_name == "halaman-pdf.zip"
    assert res_72.page_count == 3
    assert res_72.image_count == 3
    assert res_72.mime_type == "application/zip"

    # Periksa isi ZIP
    with zipfile.ZipFile(io.BytesIO(res_72.data)) as zf:
        namelist = sorted(zf.namelist())
        assert namelist == ["halaman-01.png", "halaman-02.png", "halaman-03.png"]
        img_72 = Image.open(io.BytesIO(zf.read("halaman-01.png")))
        assert img_72.format == "PNG"
        w_72, h_72 = img_72.size

    # Render dengan DPI 150 -> resolusi & dimensi piksel harus lebih besar
    res_150 = pdf_to_image(pdf_bytes, format="png", dpi=150)
    with zipfile.ZipFile(io.BytesIO(res_150.data)) as zf_150:
        img_150 = Image.open(io.BytesIO(zf_150.read("halaman-01.png")))
        assert img_150.format == "PNG"
        w_150, h_150 = img_150.size

    assert w_150 > w_72
    assert h_150 > h_72
    assert len(res_150.data) > len(res_72.data)


def test_pdf_to_image_1_halaman_jpg_dan_png() -> None:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=150, height=150)
    page.draw_circle(pymupdf.Point(75, 75), 40, color=(0, 0, 1), fill=(1, 1, 0))
    buf = io.BytesIO()
    doc.save(buf)
    pdf_bytes = buf.getvalue()
    doc.close()

    # 1 halaman JPG -> satu gambar (bukan ZIP), cek magic bytes \xff\xd8
    res_jpg = pdf_to_image(pdf_bytes, format="jpg", dpi=100, quality=80)
    assert res_jpg.output_kind == "image"
    assert res_jpg.output_name == "halaman-1.jpg"
    assert res_jpg.mime_type == "image/jpeg"
    assert res_jpg.format == "jpg"
    assert res_jpg.page_count == 1
    assert res_jpg.image_count == 1
    assert res_jpg.data[:2] == b"\xff\xd8"
    img_jpg = Image.open(io.BytesIO(res_jpg.data))
    assert img_jpg.format == "JPEG"

    # 1 halaman PNG -> satu gambar (bukan ZIP)
    res_png = pdf_to_image(pdf_bytes, format="png", dpi=100)
    assert res_png.output_kind == "image"
    assert res_png.output_name == "halaman-1.png"
    assert res_png.mime_type == "image/png"
    assert res_png.format == "png"
    assert res_png.data[:8] == b"\x89PNG\r\n\x1a\n"
    img_png = Image.open(io.BytesIO(res_png.data))
    assert img_png.format == "PNG"


def test_pdf_to_image_logika_galat() -> None:
    import pymupdf

    pdf_1 = make_pdf(1)

    # Tanpa berkas / berkas kosong / bukan PDF
    expect_pdf_to_image_error(lambda: pdf_to_image(None), PDF_IMG_ERR_NO_FILE, 400)
    expect_pdf_to_image_error(lambda: pdf_to_image(b""), PDF_IMG_ERR_EMPTY_FILE, 400)
    expect_pdf_to_image_error(lambda: pdf_to_image(b"bukan berkas pdf"), PDF_IMG_ERR_NOT_PDF, 400)

    # Format tidak didukung
    expect_pdf_to_image_error(lambda: pdf_to_image(pdf_1, format="bmp"), PDF_IMG_ERR_UNSUPPORTED_FORMAT, 400)

    # DPI / Quality di luar rentang
    expect_pdf_to_image_error(lambda: pdf_to_image(pdf_1, dpi=50), PDF_IMG_ERR_INVALID_DPI, 400)
    expect_pdf_to_image_error(lambda: pdf_to_image(pdf_1, dpi=250), PDF_IMG_ERR_INVALID_DPI, 400)
    expect_pdf_to_image_error(lambda: pdf_to_image(pdf_1, format="jpg", quality=20), PDF_IMG_ERR_INVALID_QUALITY, 400)
    expect_pdf_to_image_error(lambda: pdf_to_image(pdf_1, format="jpg", quality=100), PDF_IMG_ERR_INVALID_QUALITY, 400)

    # Dokumen melebihi 50 halaman (51 halaman)
    doc_51 = pymupdf.open()
    for _ in range(51):
        doc_51.new_page(width=50, height=50)
    buf_51 = io.BytesIO()
    doc_51.save(buf_51)
    pdf_51 = buf_51.getvalue()
    doc_51.close()
    expect_pdf_to_image_error(lambda: pdf_to_image(pdf_51), PDF_IMG_ERR_TOO_MANY_PAGES, 413)

    # PDF terenkripsi / berpasword
    doc_enc = pymupdf.open()
    doc_enc.new_page(width=50, height=50)
    buf_enc = io.BytesIO()
    doc_enc.save(buf_enc, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="rahasia", user_pw="rahasia")
    pdf_enc = buf_enc.getvalue()
    doc_enc.close()
    expect_pdf_to_image_error(lambda: pdf_to_image(pdf_enc), PDF_IMG_ERR_PDF_ENCRYPTED, 422)

    # PDF rusak
    rusak = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog\n" + b"x" * 200
    expect_pdf_to_image_error(lambda: pdf_to_image(rusak), PDF_IMG_ERR_PDF_UNREADABLE, 422)

    # Batas ukuran payload
    expect_pdf_to_image_error(lambda: check_pdf_to_image_size(PDF_IMG_MAX_FILE_BYTES + 1), PDF_IMG_ERR_PAYLOAD_TOO_LARGE, 413)


def test_http_pdf_to_image_limits() -> None:
    client = _test_client()
    if client is None:
        return
    resp = client.get("/api/pdf/to-image/limits")
    assert resp.status_code == 200, resp.text
    assert "no-store" in resp.headers.get("Cache-Control", "")
    data = resp.json()
    assert data["max_file_bytes"] == 26214400
    assert data["max_file_mb"] == 25
    assert data["max_pages"] == 50
    assert data["min_dpi"] == 72
    assert data["max_dpi"] == 200
    assert data["default_dpi"] == 150
    assert data["min_quality"] == 30
    assert data["max_quality"] == 95
    assert data["default_quality"] == 85
    assert data["formats"] == ["png", "jpg"]
    assert data["max_output_bytes"] == 83886080


def test_http_pdf_to_image_sukses_dan_galat() -> None:
    import zipfile
    import pymupdf

    client = _test_client()
    if client is None:
        return

    # Buat PDF 3 halaman
    doc_3 = pymupdf.open()
    for _ in range(3):
        p = doc_3.new_page(width=150, height=150)
        p.draw_rect(pymupdf.Rect(10, 10, 80, 80), color=(1, 0, 0), fill=(0, 0, 1))
    buf_3 = io.BytesIO()
    doc_3.save(buf_3)
    pdf_3 = buf_3.getvalue()
    doc_3.close()

    # 1. POST 3 halaman PNG -> ZIP
    r_zip = client.post(
        "/api/pdf/to-image",
        files=[("file", ("dokumen.pdf", pdf_3, "application/pdf"))],
        data={"format": "png", "dpi": "100"},
    )
    assert r_zip.status_code == 200, r_zip.text
    assert r_zip.headers["content-type"].startswith("application/zip")
    assert 'filename="halaman-pdf.zip"' in r_zip.headers.get("Content-Disposition", "")
    assert r_zip.headers.get("X-Output-Kind") == "zip"
    assert r_zip.headers.get("X-Page-Count") == "3"
    assert r_zip.headers.get("X-Image-Count") == "3"
    assert r_zip.headers.get("X-Image-Format") == "png"
    assert r_zip.headers.get("X-Dpi") == "100"
    assert "no-store" in r_zip.headers.get("Cache-Control", "")

    with zipfile.ZipFile(io.BytesIO(r_zip.content)) as zf:
        assert sorted(zf.namelist()) == ["halaman-01.png", "halaman-02.png", "halaman-03.png"]
        img = Image.open(io.BytesIO(zf.read("halaman-01.png")))
        assert img.format == "PNG"

    # 2. POST 1 halaman JPG -> Single image file
    doc_1 = pymupdf.open()
    p1 = doc_1.new_page(width=100, height=100)
    p1.draw_circle(pymupdf.Point(50, 50), 30, color=(0, 1, 0), fill=(1, 0, 0))
    buf_1 = io.BytesIO()
    doc_1.save(buf_1)
    pdf_1 = buf_1.getvalue()
    doc_1.close()

    r_jpg = client.post(
        "/api/pdf/to-image",
        files=[("file", ("satu.pdf", pdf_1, "application/pdf"))],
        data={"format": "jpg", "dpi": "120", "quality": "90"},
    )
    assert r_jpg.status_code == 200, r_jpg.text
    assert r_jpg.headers["content-type"].startswith("image/jpeg")
    assert 'filename="halaman-1.jpg"' in r_jpg.headers.get("Content-Disposition", "")
    assert r_jpg.headers.get("X-Output-Kind") == "image"
    assert r_jpg.headers.get("X-Page-Count") == "1"
    assert r_jpg.headers.get("X-Image-Count") == "1"
    assert r_jpg.content[:2] == b"\xff\xd8"

    # 3. Galat HTTP: tanpa file -> 400 NO_FILE
    r_no_file = client.post("/api/pdf/to-image", data={"format": "png"})
    assert r_no_file.status_code == 400
    assert r_no_file.json()["error"]["code"] == PDF_IMG_ERR_NO_FILE

    # 4. Galat HTTP: bukan PDF -> 400 NOT_PDF
    r_not_pdf = client.post(
        "/api/pdf/to-image",
        files=[("file", ("bukan.txt", b"ini cuma teks", "text/plain"))],
        data={"format": "png"},
    )
    assert r_not_pdf.status_code == 400
    assert r_not_pdf.json()["error"]["code"] == PDF_IMG_ERR_NOT_PDF

    # 5. Galat HTTP: format tidak didukung -> 400 UNSUPPORTED_FORMAT
    r_bad_fmt = client.post(
        "/api/pdf/to-image",
        files=[("file", ("dokumen.pdf", pdf_1, "application/pdf"))],
        data={"format": "webp"},
    )
    assert r_bad_fmt.status_code == 400
    assert r_bad_fmt.json()["error"]["code"] == PDF_IMG_ERR_UNSUPPORTED_FORMAT

    # 6. Galat HTTP: DPI tidak valid -> 400 INVALID_DPI
    r_bad_dpi = client.post(
        "/api/pdf/to-image",
        files=[("file", ("dokumen.pdf", pdf_1, "application/pdf"))],
        data={"dpi": "50"},
    )
    assert r_bad_dpi.status_code == 400
    assert r_bad_dpi.json()["error"]["code"] == PDF_IMG_ERR_INVALID_DPI

    # 7. Galat HTTP: Kualitas tidak valid -> 400 INVALID_QUALITY
    r_bad_qual = client.post(
        "/api/pdf/to-image",
        files=[("file", ("dokumen.pdf", pdf_1, "application/pdf"))],
        data={"format": "jpg", "quality": "10"},
    )
    assert r_bad_qual.status_code == 400
    assert r_bad_qual.json()["error"]["code"] == PDF_IMG_ERR_INVALID_QUALITY

    # 8. Galat HTTP: PDF terenkripsi -> 422 PDF_ENCRYPTED
    doc_enc = pymupdf.open()
    doc_enc.new_page(width=50, height=50)
    buf_enc = io.BytesIO()
    doc_enc.save(buf_enc, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="rahasia", user_pw="rahasia")
    pdf_enc = buf_enc.getvalue()
    doc_enc.close()

    r_enc = client.post(
        "/api/pdf/to-image",
        files=[("file", ("terkunci.pdf", pdf_enc, "application/pdf"))],
    )
    assert r_enc.status_code == 422
    assert r_enc.json()["error"]["code"] == PDF_IMG_ERR_PDF_ENCRYPTED

    # 9. Galat HTTP: lebih dari 50 halaman -> 413 TOO_MANY_PAGES
    doc_51 = pymupdf.open()
    for _ in range(51):
        doc_51.new_page(width=50, height=50)
    buf_51 = io.BytesIO()
    doc_51.save(buf_51)
    pdf_51 = buf_51.getvalue()
    doc_51.close()

    r_too_many = client.post(
        "/api/pdf/to-image",
        files=[("file", ("banyak.pdf", pdf_51, "application/pdf"))],
    )
    assert r_too_many.status_code == 413
    assert r_too_many.json()["error"]["code"] == PDF_IMG_ERR_TOO_MANY_PAGES


def test_http_pdf_to_image_regresi_dan_root() -> None:
    client = _test_client()
    if client is None:
        return

    # Root memiliki pdf-to-image di daftar alat
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert "pdf-to-image" in root_data["tools"]

    # Endpoint limits lama tetap 200
    assert client.get("/api/pdf/merge/limits").status_code == 200
    assert client.get("/api/pdf/split/limits").status_code == 200
    assert client.get("/api/pdf/compress/limits").status_code == 200
    assert client.get("/api/image/convert/limits").status_code == 200


# --- Runner mandiri ---------------------------------------------------------
def main() -> int:
    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    passed = 0
    failures: list[tuple[str, str]] = []

    print(f"OmniTools API — uji Merge PDF (versi {__version__}, python {sys.version.split()[0]})")
    print(f"Pemeriksaan akan dijalankan: {len(tests)}\n")

    for name, func in tests:
        try:
            func()
        except BaseException as exc:
            if exc.__class__.__name__ == "Skipped":
                SKIPPED.append(f"{name}: {exc}")
                print(f"LEWAT  {name}")
                continue
            failures.append((name, traceback.format_exc()))
            print(f"GAGAL  {name}")
        else:
            passed += 1
            print(f"LULUS  {name}")

    for note in SKIPPED:
        print(f"LEWAT  {note}")

    print(f"\nRingkasan: {passed} lulus, {len(failures)} gagal, {len(SKIPPED)} dilewati")

    for name, detail in failures:
        print(f"\n--- detail kegagalan: {name} ---")
        print(detail)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
