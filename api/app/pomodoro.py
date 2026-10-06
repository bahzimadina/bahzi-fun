"""Logika Pomodoro Timer: fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Nilai pengguna tidak pernah dicatat ke log.
"""

from __future__ import annotations

from typing import Any

# Batas operasional
MAX_INPUT_CHARS = 40
MAX_BYTES = 65536
MIN_KERJA = 1
MAX_KERJA = 180
MIN_ISTIRAHAT = 1
MAX_ISTIRAHAT = 60
MIN_ISTIRAHAT_PANJANG = 1
MAX_ISTIRAHAT_PANJANG = 90
MIN_SESI = 1
MAX_SESI = 12
DEFAULT_SESI = 4

# Mode bawaan dan pengaturannya
MODE_DEFAULTS: dict[str, dict[str, int]] = {
    "klasik": {
        "kerja": 25,
        "istirahat": 5,
        "istirahat_panjang": 15,
    },
    "panjang": {
        "kerja": 50,
        "istirahat": 10,
        "istirahat_panjang": 20,
    },
    "pendek": {
        "kerja": 15,
        "istirahat": 3,
        "istirahat_panjang": 12,
    },
    "kustom": {
        "kerja": 25,
        "istirahat": 5,
        "istirahat_panjang": 15,
    },
}

MODES: list[dict[str, Any]] = [
    {
        "id": "klasik",
        "label": "Klasik (25 / 5 / 15 menit)",
        "kerja": 25,
        "istirahat": 5,
        "istirahat_panjang": 15,
        "keterangan": "Fokus 25 menit, istirahat 5 menit, istirahat panjang 15 menit setiap 4 sesi",
    },
    {
        "id": "panjang",
        "label": "Panjang (50 / 10 / 20 menit)",
        "kerja": 50,
        "istirahat": 10,
        "istirahat_panjang": 20,
        "keterangan": "Fokus 50 menit, istirahat 10 menit, istirahat panjang 20 menit setiap 4 sesi",
    },
    {
        "id": "pendek",
        "label": "Pendek (15 / 3 / 12 menit)",
        "kerja": 15,
        "istirahat": 3,
        "istirahat_panjang": 12,
        "keterangan": "Fokus 15 menit, istirahat 3 menit, istirahat panjang 12 menit setiap 4 sesi",
    },
    {
        "id": "kustom",
        "label": "Kustom (atur sendiri)",
        "kerja": 25,
        "istirahat": 5,
        "istirahat_panjang": 15,
        "keterangan": "Atur menit fokus, istirahat pendek, dan istirahat panjang sendiri",
    },
]

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
INVALID_NUMBER = "INVALID_NUMBER"
INVALID_RANGE = "INVALID_RANGE"
INVALID_START_TIME = "INVALID_START_TIME"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class PomodoroError(ValueError):
    """Galat operasional pomodoro dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


def parse_int_field(
    value: Any,
    field_name: str,
    min_val: int,
    max_val: int,
    default_val: int,
) -> int:
    """Validasi dan konversi nilai bilangan bulat dengan batas rentang."""
    if value is None:
        return default_val

    if isinstance(value, bool):
        raise PomodoroError(INVALID_NUMBER, f"Field '{field_name}' harus berupa bilangan bulat.", 400)

    if isinstance(value, (int, float)):
        if isinstance(value, float) and not value.is_integer():
            raise PomodoroError(
                INVALID_NUMBER,
                f"Field '{field_name}' harus berupa bilangan bulat, bukan desimal.",
                400,
            )
        num = int(value)
    elif isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return default_val
        if len(cleaned) > MAX_INPUT_CHARS:
            raise PomodoroError(
                INVALID_RANGE,
                f"Panjang masukan '{field_name}' ({len(cleaned)} karakter) melebihi batas {MAX_INPUT_CHARS} karakter.",
                400,
            )
        if "." in cleaned or "," in cleaned:
            raise PomodoroError(
                INVALID_NUMBER,
                f"Field '{field_name}' harus berupa bilangan bulat, bukan desimal.",
                400,
            )
        try:
            num = int(cleaned)
        except ValueError:
            raise PomodoroError(
                INVALID_NUMBER,
                f"Field '{field_name}' harus berupa angka bilangan bulat.",
                400,
            )
    else:
        raise PomodoroError(INVALID_NUMBER, f"Field '{field_name}' tidak valid.", 400)

    if num < min_val or num > max_val:
        raise PomodoroError(
            INVALID_RANGE,
            f"Nilai '{field_name}' ({num}) di luar rentang {min_val} sampai {max_val}.",
            400,
        )

    return num


def parse_start_time(value: Any) -> tuple[int, int] | None:
    """Validasi dan parsing format jam mulai 'HH:MM'.

    Mengembalikan tuple (jam, menit) atau None bila tidak diisi.
    """
    if value is None:
        return None

    if not isinstance(value, str):
        raise PomodoroError(INVALID_REQUEST, "Field 'mulai' harus berupa teks string.", 400)

    cleaned = value.strip()
    if not cleaned:
        return None

    if len(cleaned) > MAX_INPUT_CHARS:
        raise PomodoroError(
            INVALID_RANGE,
            f"Panjang masukan jam mulai melebihi batas {MAX_INPUT_CHARS} karakter.",
            400,
        )

    parts = cleaned.split(":")
    if len(parts) != 2:
        raise PomodoroError(
            INVALID_START_TIME,
            "Format jam mulai tidak valid. Gunakan format 'HH:MM' (contoh: 08:30).",
            400,
        )

    h_str, m_str = parts
    if len(h_str) != 2 or len(m_str) != 2 or not h_str.isdigit() or not m_str.isdigit():
        raise PomodoroError(
            INVALID_START_TIME,
            "Format jam mulai harus 2 digit jam dan 2 digit menit 'HH:MM' (00:00 sampai 23:59).",
            400,
        )

    hour = int(h_str)
    minute = int(m_str)

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise PomodoroError(
            INVALID_START_TIME,
            f"Jam mulai '{cleaned}' tidak valid. Jam harus antara 00:00 sampai 23:59.",
            400,
        )

    return hour, minute


def _format_clock(total_sec: int) -> str:
    """Format total detik ke format jam 24 jam 'HH:MM'."""
    sec_in_day = total_sec % 86400
    h = sec_in_day // 3600
    m = (sec_in_day % 3600) // 60
    return f"{h:02d}:{m:02d}"


def compute_pomodoro(
    mode: Any,
    kerja: Any = None,
    istirahat: Any = None,
    istirahat_panjang: Any = None,
    sesi: Any = None,
    mulai: Any = None,
) -> dict[str, Any]:
    """Susun jadwal Pomodoro murni di memori berdasarkan mode dan masukan."""
    if mode is None:
        raise PomodoroError(INVALID_REQUEST, "Field 'mode' wajib diisi.", 400)

    if not isinstance(mode, str):
        raise PomodoroError(INVALID_REQUEST, "Field 'mode' harus berupa teks string.", 400)

    mode_norm = mode.strip()
    if not mode_norm:
        raise PomodoroError(INVALID_REQUEST, "Field 'mode' wajib diisi.", 400)

    if len(mode_norm) > MAX_INPUT_CHARS:
        raise PomodoroError(
            INVALID_RANGE,
            f"Panjang masukan mode ({len(mode_norm)} karakter) melebihi batas {MAX_INPUT_CHARS} karakter.",
            400,
        )

    if mode_norm not in MODE_DEFAULTS:
        valid_modes = ", ".join(MODE_DEFAULTS.keys())
        raise PomodoroError(
            UNSUPPORTED_MODE,
            f"Mode '{mode_norm}' tidak dikenali. Pilih salah satu: {valid_modes}.",
            400,
        )

    defaults = MODE_DEFAULTS[mode_norm]
    kerja_menit = parse_int_field(kerja, "kerja", MIN_KERJA, MAX_KERJA, defaults["kerja"])
    istirahat_menit = parse_int_field(istirahat, "istirahat", MIN_ISTIRAHAT, MAX_ISTIRAHAT, defaults["istirahat"])
    istirahat_panjang_menit = parse_int_field(
        istirahat_panjang,
        "istirahat_panjang",
        MIN_ISTIRAHAT_PANJANG,
        MAX_ISTIRAHAT_PANJANG,
        defaults["istirahat_panjang"],
    )
    sesi_fokus = parse_int_field(sesi, "sesi", MIN_SESI, MAX_SESI, DEFAULT_SESI)

    start_time_parsed = parse_start_time(mulai)
    start_seconds: int | None = None
    if start_time_parsed is not None:
        start_seconds = (start_time_parsed[0] * 60 + start_time_parsed[1]) * 60

    langkah: list[dict[str, Any]] = []
    urutan = 1
    detik_berjalan = 0

    for s in range(1, sesi_fokus + 1):
        # 1. Sesi fokus
        durasi_fokus = kerja_menit * 60
        mulai_f = detik_berjalan
        selesai_f = detik_berjalan + durasi_fokus
        detik_berjalan = selesai_f

        step_fokus: dict[str, Any] = {
            "urutan": urutan,
            "jenis": "fokus",
            "label": f"Fokus sesi {s}",
            "durasi_detik": durasi_fokus,
            "mulai_detik": mulai_f,
            "selesai_detik": selesai_f,
        }
        if start_seconds is not None:
            step_fokus["jam_mulai"] = _format_clock(start_seconds + mulai_f)
            step_fokus["jam_selesai"] = _format_clock(start_seconds + selesai_f)

        langkah.append(step_fokus)
        urutan += 1

        # Jika sesi terakhir, tidak ada sesi istirahat setelahnya
        if s == sesi_fokus:
            break

        # 2. Sesi istirahat
        if s % 4 == 0:
            jenis_istirahat = "istirahat_panjang"
            label_istirahat = "Istirahat panjang"
            durasi_istirahat = istirahat_panjang_menit * 60
        else:
            jenis_istirahat = "istirahat"
            label_istirahat = "Istirahat pendek"
            durasi_istirahat = istirahat_menit * 60

        mulai_b = detik_berjalan
        selesai_b = detik_berjalan + durasi_istirahat
        detik_berjalan = selesai_b

        step_break: dict[str, Any] = {
            "urutan": urutan,
            "jenis": jenis_istirahat,
            "label": label_istirahat,
            "durasi_detik": durasi_istirahat,
            "mulai_detik": mulai_b,
            "selesai_detik": selesai_b,
        }
        if start_seconds is not None:
            step_break["jam_mulai"] = _format_clock(start_seconds + mulai_b)
            step_break["jam_selesai"] = _format_clock(start_seconds + selesai_b)

        langkah.append(step_break)
        urutan += 1

    total_fokus_detik = sesi_fokus * kerja_menit * 60
    total_detik = detik_berjalan
    total_istirahat_detik = total_detik - total_fokus_detik

    out: dict[str, Any] = {
        "mode": mode_norm,
        "kerja_menit": kerja_menit,
        "istirahat_menit": istirahat_menit,
        "istirahat_panjang_menit": istirahat_panjang_menit,
        "sesi_fokus": sesi_fokus,
        "langkah": langkah,
        "total_detik": total_detik,
        "total_fokus_detik": total_fokus_detik,
        "total_istirahat_detik": total_istirahat_detik,
        "jumlah_langkah": len(langkah),
    }

    if start_seconds is not None:
        out["perkiraan_selesai"] = _format_clock(start_seconds + detik_berjalan)

    return out


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional dan daftar mode Pomodoro."""
    return {
        "tool": "pomodoro",
        "max_input_chars": MAX_INPUT_CHARS,
        "max_bytes": MAX_BYTES,
        "max_mb": MAX_BYTES // (1024 * 1024),
        "limits": {
            "kerja": {"min": MIN_KERJA, "max": MAX_KERJA, "satuan": "menit", "bawaan": 25},
            "istirahat": {"min": MIN_ISTIRAHAT, "max": MAX_ISTIRAHAT, "satuan": "menit", "bawaan": 5},
            "istirahat_panjang": {"min": MIN_ISTIRAHAT_PANJANG, "max": MAX_ISTIRAHAT_PANJANG, "satuan": "menit", "bawaan": 15},
            "sesi": {"min": MIN_SESI, "max": MAX_SESI, "bawaan": DEFAULT_SESI},
        },
        "modes": MODES,
    }
