"""Logika bagi giliran tugas: fungsi murni di memori.

Modul ini tidak bergantung pada FastAPI/HTTP dan tidak melakukan I/O disk.
Semua pemrosesan dilakukan di memori. Data nama tidak pernah disimpan di disk.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import random
import re
from typing import Any

try:
    from zoneinfo import ZoneInfo
    JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
except Exception:
    from datetime import timezone
    JAKARTA_TZ = timezone(timedelta(hours=7))

# Batas operasional
MAX_NAMES = 100
MIN_NAMES = 1
MAX_NAME_CHARS = 40
MAX_SLOTS = 200
MIN_SLOTS = 1
MAX_PER_SLOT = 20
MIN_PER_SLOT = 1
MAX_TEXT_CHARS = 20000
MAX_BYTES = 64 * 1024  # 64 KB
MAX_TOTAL_ASSIGNMENTS = 2000

MIN_DATE_STR = "2000-01-01"
MAX_DATE_STR = "2100-12-31"

MIN_SEED = 0
MAX_SEED = 4294967295

TIMEOUT_SECONDS = 15

# Kode galat stabil
INVALID_REQUEST = "INVALID_REQUEST"
NO_NAMES = "NO_NAMES"
TOO_MANY_NAMES = "TOO_MANY_NAMES"
NAME_TOO_LONG = "NAME_TOO_LONG"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
UNSUPPORTED_ORDER = "UNSUPPORTED_ORDER"
INVALID_PER_SLOT = "INVALID_PER_SLOT"
INVALID_SLOTS = "INVALID_SLOTS"
TOO_MANY_ASSIGNMENTS = "TOO_MANY_ASSIGNMENTS"
INVALID_DATE = "INVALID_DATE"
INVALID_SEED = "INVALID_SEED"
TEXT_TOO_LONG = "TEXT_TOO_LONG"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"

HARI = [
    "Senin",
    "Selasa",
    "Rabu",
    "Kamis",
    "Jumat",
    "Sabtu",
    "Minggu",
]

BULAN = [
    "",
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
]


class GiliranError(ValueError):
    """Galat operasional bagi giliran tugas dengan kode galat dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar."""
        return {"error": {"code": self.code, "message": self.message}}


def parse_bool(value: Any, default: bool = True) -> bool:
    """Parse nilai boolean dari berbagai format masukan."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        norm = value.strip().lower()
        if norm in ("true", "1", "ya", "yes", "on"):
            return True
        if norm in ("false", "0", "tidak", "no", "off"):
            return False
    return default


def limits_payload() -> dict[str, Any]:
    """Mengembalikan konfigurasi batas operasional dan nilai bawaan bagi giliran."""
    return {
        "max_names": MAX_NAMES,
        "min_names": MIN_NAMES,
        "max_name_chars": MAX_NAME_CHARS,
        "max_slots": MAX_SLOTS,
        "min_slots": MIN_SLOTS,
        "max_per_slot": MAX_PER_SLOT,
        "min_per_slot": MIN_PER_SLOT,
        "max_text_chars": MAX_TEXT_CHARS,
        "modes": [
            {"value": "harian", "label": "Harian"},
            {"value": "mingguan", "label": "Mingguan"},
        ],
        "orders": [
            {"value": "maju", "label": "Maju sesuai tulisan"},
            {"value": "mundur", "label": "Mundur (dibalik)"},
            {"value": "acak", "label": "Acak"},
        ],
        "default_mode": "harian",
        "default_order": "maju",
        "default_per_slot": 2,
        "default_slots": 8,
        "default_tanggal_mulai": datetime.now(JAKARTA_TZ).date().isoformat(),
        "timeout_seconds": TIMEOUT_SECONDS,
        "notes": "Daftar nama diproses di memori server lalu langsung dibuang, tidak disimpan di disk.",
        "processed_on": "server",
    }


def _clean_names(names: str | None) -> tuple[list[str], int]:
    """Bersihkan daftar nama, buang duplikat, dan laporkan jumlah duplikat yang dibuang."""
    if names is None:
        raise GiliranError(NO_NAMES, "Masukkan daftar nama terlebih dahulu.", 400)

    if not isinstance(names, str):
        raise GiliranError(INVALID_REQUEST, "Field 'names' harus berupa teks string.", 400)

    # Periksa ukuran byte UTF-8
    encoded_bytes = len(names.encode("utf-8"))
    if encoded_bytes > MAX_BYTES:
        raise GiliranError(
            PAYLOAD_TOO_LARGE,
            f"Ukuran teks ({encoded_bytes:,} byte) melebihi batas 64 KB.",
            413,
        )

    # Periksa batas jumlah karakter teks
    if len(names) > MAX_TEXT_CHARS:
        raise GiliranError(
            TEXT_TOO_LONG,
            f"Teks daftar nama terlalu panjang ({len(names):,} karakter). Batasnya {MAX_TEXT_CHARS:,} karakter.",
            400,
        )

    lines = names.splitlines()
    seen: set[str] = set()
    cleaned: list[str] = []
    duplikat_dibuang = 0

    for line in lines:
        name = line.strip()
        if not name:
            continue
        if len(name) > MAX_NAME_CHARS:
            snippet = name[:20] + "..." if len(name) > 20 else name
            raise GiliranError(
                NAME_TOO_LONG,
                f"Nama '{snippet}' terlalu panjang. Panjang satu nama maksimal {MAX_NAME_CHARS} karakter.",
                400,
            )
        key = name.lower()
        if key in seen:
            duplikat_dibuang += 1
        else:
            seen.add(key)
            cleaned.append(name)

    if len(cleaned) < MIN_NAMES:
        raise GiliranError(NO_NAMES, "Masukkan setidaknya 1 nama untuk menyusun jadwal.", 400)

    if len(cleaned) > MAX_NAMES:
        raise GiliranError(
            TOO_MANY_NAMES,
            f"Jumlah nama ({len(cleaned)}) melebihi batas maksimal {MAX_NAMES} nama.",
            400,
        )

    return cleaned, duplikat_dibuang


def bagi_giliran(
    names: str | None,
    mode: str | None = "harian",
    per_slot: int | str | None = 2,
    slots: int | str | None = 8,
    tanggal_mulai: str | None = None,
    urutan: str | None = "maju",
    seed: int | str | None = None,
    lewati_akhir_pekan: bool | str | None = True,
) -> dict[str, Any]:
    """Susun jadwal giliran tugas dari daftar nama murni di memori."""
    cleaned_names, duplikat_dibuang = _clean_names(names)

    # Validasi mode
    if mode is None:
        mode_norm = "harian"
    elif isinstance(mode, str):
        mode_stripped = mode.strip().lower()
        if not mode_stripped:
            mode_norm = "harian"
        elif mode_stripped in ("harian", "mingguan"):
            mode_norm = mode_stripped
        else:
            raise GiliranError(
                UNSUPPORTED_MODE,
                "Mode yang dipilih tidak dikenal. Pilih harian atau mingguan.",
                400,
            )
    else:
        raise GiliranError(
            UNSUPPORTED_MODE,
            "Mode yang dipilih tidak dikenal. Pilih harian atau mingguan.",
            400,
        )

    # Validasi urutan
    if urutan is None:
        urutan_norm = "maju"
    elif isinstance(urutan, str):
        urutan_stripped = urutan.strip().lower()
        if not urutan_stripped:
            urutan_norm = "maju"
        elif urutan_stripped in ("maju", "mundur", "acak"):
            urutan_norm = urutan_stripped
        else:
            raise GiliranError(
                UNSUPPORTED_ORDER,
                "Urutan yang dipilih tidak dikenal. Pilih maju, mundur, atau acak.",
                400,
            )
    else:
        raise GiliranError(
            UNSUPPORTED_ORDER,
            "Urutan yang dipilih tidak dikenal. Pilih maju, mundur, atau acak.",
            400,
        )

    # Validasi per_slot
    if per_slot is None or (isinstance(per_slot, str) and per_slot.strip() == ""):
        per_slot_int = 2
    elif isinstance(per_slot, bool):
        raise GiliranError(
            INVALID_PER_SLOT,
            "Jumlah orang per giliran harus berupa bilangan bulat antara 1 sampai 20.",
            400,
        )
    else:
        try:
            per_slot_int = int(per_slot)
        except (ValueError, TypeError):
            raise GiliranError(
                INVALID_PER_SLOT,
                "Jumlah orang per giliran harus berupa bilangan bulat antara 1 sampai 20.",
                400,
            )
        if per_slot_int < MIN_PER_SLOT or per_slot_int > MAX_PER_SLOT:
            raise GiliranError(
                INVALID_PER_SLOT,
                f"Jumlah orang per giliran harus antara {MIN_PER_SLOT} sampai {MAX_PER_SLOT}.",
                400,
            )

    # Validasi slots (jumlah giliran)
    if slots is None or (isinstance(slots, str) and slots.strip() == ""):
        slots_int = 8
    elif isinstance(slots, bool):
        raise GiliranError(
            INVALID_SLOTS,
            "Jumlah giliran harus berupa bilangan bulat antara 1 sampai 200.",
            400,
        )
    else:
        try:
            slots_int = int(slots)
        except (ValueError, TypeError):
            raise GiliranError(
                INVALID_SLOTS,
                "Jumlah giliran harus berupa bilangan bulat antara 1 sampai 200.",
                400,
            )
        if slots_int < MIN_SLOTS or slots_int > MAX_SLOTS:
            raise GiliranError(
                INVALID_SLOTS,
                f"Jumlah giliran harus antara {MIN_SLOTS} sampai {MAX_SLOTS}.",
                400,
            )

    # Validasi total penugasan
    if slots_int * per_slot_int > MAX_TOTAL_ASSIGNMENTS:
        raise GiliranError(
            TOO_MANY_ASSIGNMENTS,
            f"Total penugasan ({slots_int * per_slot_int:,}) melebihi batas maksimal {MAX_TOTAL_ASSIGNMENTS:,}.",
            400,
        )

    # Validasi seed
    seed_val: int | None = None
    if seed is not None and str(seed).strip() != "":
        try:
            seed_val = int(seed)
        except (ValueError, TypeError):
            raise GiliranError(
                INVALID_SEED,
                "Kunci acak (seed) harus berupa bilangan bulat antara 0 sampai 4294967295.",
                400,
            )
        if seed_val < MIN_SEED or seed_val > MAX_SEED:
            raise GiliranError(
                INVALID_SEED,
                f"Kunci acak (seed) harus antara {MIN_SEED} sampai {MAX_SEED}.",
                400,
            )

    if urutan_norm == "acak":
        if seed_val is None:
            seed_val = random.randint(MIN_SEED, MAX_SEED)
    else:
        seed_val = None

    # Validasi tanggal mulai
    start_dt: date
    if tanggal_mulai is not None and str(tanggal_mulai).strip() != "":
        t_str = str(tanggal_mulai).strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", t_str):
            raise GiliranError(
                INVALID_DATE,
                "Format tanggal mulai tidak valid. Gunakan format YYYY-MM-DD.",
                400,
            )
        try:
            start_dt = datetime.strptime(t_str, "%Y-%m-%d").date()
        except ValueError:
            raise GiliranError(
                INVALID_DATE,
                "Tanggal mulai tidak valid.",
                400,
            )
        min_dt = datetime.strptime(MIN_DATE_STR, "%Y-%m-%d").date()
        max_dt = datetime.strptime(MAX_DATE_STR, "%Y-%m-%d").date()
        if start_dt < min_dt or start_dt > max_dt:
            raise GiliranError(
                INVALID_DATE,
                f"Tanggal mulai harus antara {MIN_DATE_STR} sampai {MAX_DATE_STR}.",
                400,
            )
    else:
        start_dt = datetime.now(JAKARTA_TZ).date()

    # Perlakuan lewati akhir pekan
    lewati_bool = parse_bool(lewati_akhir_pekan, default=True)
    if mode_norm == "mingguan":
        lewati_dipakai = False
    else:
        lewati_dipakai = lewati_bool

    # Penyusunan urutan nama
    if urutan_norm == "maju":
        ordered_names = list(cleaned_names)
    elif urutan_norm == "mundur":
        ordered_names = list(reversed(cleaned_names))
    else:
        rng = random.Random(seed_val)
        ordered_names = list(cleaned_names)
        rng.shuffle(ordered_names)

    # Inisialisasi struktur hitungan per nama
    original_idx = {name: idx for idx, name in enumerate(cleaned_names)}
    hitungan_map: dict[str, dict[str, Any]] = {
        name: {"nama": name, "kali": 0, "giliran": []}
        for name in cleaned_names
    }

    giliran_list: list[dict[str, Any]] = []
    pointer = 0
    n_names = len(ordered_names)
    slot_size = min(per_slot_int, n_names)

    if mode_norm == "harian":
        current_dt = start_dt
        if lewati_dipakai:
            while current_dt.weekday() >= 5:
                current_dt += timedelta(days=1)

        for i in range(slots_int):
            slot_no = i + 1
            slot_people = [ordered_names[(pointer + j) % n_names] for j in range(slot_size)]
            pointer = (pointer + per_slot_int) % n_names

            for person in slot_people:
                hitungan_map[person]["kali"] += 1
                if slot_no not in hitungan_map[person]["giliran"]:
                    hitungan_map[person]["giliran"].append(slot_no)

            t_iso = current_dt.isoformat()
            hari_nama = HARI[current_dt.weekday()]
            bln_nama = BULAN[current_dt.month]
            label = f"{hari_nama}, {current_dt.day} {bln_nama} {current_dt.year}"

            giliran_list.append({
                "nomor": slot_no,
                "tanggal": t_iso,
                "tanggal_selesai": t_iso,
                "label": label,
                "orang": slot_people,
            })

            current_dt += timedelta(days=1)
            if lewati_dipakai:
                while current_dt.weekday() >= 5:
                    current_dt += timedelta(days=1)

    else:
        # Mode mingguan: satu giliran = 7 hari (start .. start+6)
        current_start = start_dt
        for i in range(slots_int):
            slot_no = i + 1
            slot_people = [ordered_names[(pointer + j) % n_names] for j in range(slot_size)]
            pointer = (pointer + per_slot_int) % n_names

            for person in slot_people:
                hitungan_map[person]["kali"] += 1
                if slot_no not in hitungan_map[person]["giliran"]:
                    hitungan_map[person]["giliran"].append(slot_no)

            current_end = current_start + timedelta(days=6)
            start_iso = current_start.isoformat()
            end_iso = current_end.isoformat()

            if current_start.year != current_end.year:
                label = f"{current_start.day} {BULAN[current_start.month]} {current_start.year} - {current_end.day} {BULAN[current_end.month]} {current_end.year}"
            elif current_start.month != current_end.month:
                label = f"{current_start.day} {BULAN[current_start.month]} - {current_end.day} {BULAN[current_end.month]} {current_start.year}"
            else:
                label = f"{current_start.day} - {current_end.day} {BULAN[current_start.month]} {current_start.year}"

            giliran_list.append({
                "nomor": slot_no,
                "minggu_ke": slot_no,
                "tanggal": start_iso,
                "tanggal_selesai": end_iso,
                "label": label,
                "orang": slot_people,
            })

            current_start += timedelta(days=7)

    # Hitungan diurutkan menurun berdasarkan kali, lalu menurut urutan nama asli
    hitungan_sorted = sorted(
        hitungan_map.values(),
        key=lambda item: (-item["kali"], original_idx[item["nama"]]),
    )

    # Catatan santai dan jujur
    catatan = [
        "Jadwal disusun secara bergilir (round-robin) dari daftar nama yang ditulis, bukan dari kalender kantor.",
        (
            "Pilihan lewati akhir pekan aktif sehingga jadwal selalu jatuh pada hari kerja (Senin sampai Jumat)."
            if (mode_norm == "harian" and lewati_dipakai)
            else (
                "Jadwal harian berjalan setiap hari tanpa melewati hari Sabtu dan Minggu."
                if mode_norm == "harian"
                else "Jadwal mingguan membagi giliran per 7 hari tanpa melewati akhir pekan."
            )
        ),
        (
            f"Urutan acak memakai kunci seed {seed_val} sehingga susunan jadwal ini bisa dibuat ulang kapan saja."
            if urutan_norm == "acak"
            else "Urutan nama dapat diatur maju, mundur, atau diacak dengan kunci yang bisa diulang."
        ),
    ]

    if len(cleaned_names) < per_slot_int:
        catatan.append(
            "Jumlah nama lebih sedikit daripada orang per giliran, jadi tiap giliran diisi semua nama yang ada."
        )

    return {
        "mode": mode_norm,
        "urutan": urutan_norm,
        "seed": seed_val,
        "per_slot": per_slot_int,
        "jumlah_nama": len(cleaned_names),
        "duplikat_dibuang": duplikat_dibuang,
        "jumlah_giliran": slots_int,
        "tanggal_mulai": start_dt.isoformat(),
        "lewati_akhir_pekan": lewati_bool,
        "lewati_akhir_pekan_dipakai": lewati_dipakai,
        "giliran": giliran_list,
        "hitungan": hitungan_sorted,
        "catatan": catatan,
    }
