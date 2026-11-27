"""Modul kompresi video memakai ffmpeg/ffprobe.

Semua proses dijalankan di server dengan berkas sementara di /tmp (tmpfs)
yang selalu dibersihkan setelah selesai.
Privasi: log hanya mencatat metadata numerik dan status (durasi, byte, mode, preset).
Nama berkas pengguna dan isinya tidak dicatat ke log.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import math
import os
import re
import subprocess
import tempfile
from typing import Any

from .video_trim import durasi_berkas

logger = logging.getLogger("omnitools.api")

# --- Batas operasional & konfigurasi -----------------------------------------
MAX_FILES = 1
MAX_BYTES = 25 * 1024 * 1024           # 25 MB
MAX_DURATION_SECONDS = 120             # 120 detik (2 menit)
MAX_OUTPUT_BYTES = 100 * 1024 * 1024   # 100 MB
ALLOWED_FORMATS = ("mp4", "mov", "webm", "mkv")

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
PROSES_TIMEOUT_SECONDS = 110

TARGET_MB_MIN = 1.0
TARGET_MB_MAX = 20.0
TARGET_MB_DEFAULT = 5.0
MIN_VIDEO_BITRATE = 150                # kbps minimal agar video tetap layak tonton
MAX_DIMENSION = 1280                   # px batas sisi terpanjang bila diperkecil

PRESETS = (
    {
        "id": "ringan",
        "label": "Ringan (CRF 24)",
        "desc": "Kualitas visual paling terjaga, ukuran berkas berkurang wajar.",
        "crf": 24,
    },
    {
        "id": "seimbang",
        "label": "Seimbang (CRF 28)",
        "desc": "Paling pas untuk dibagikan ke WhatsApp, Telegram, atau medsos.",
        "crf": 28,
    },
    {
        "id": "kuat",
        "label": "Kuat (CRF 32)",
        "desc": "Ukuran berkas diperkecil maksimal dengan penurunan kualitas yang masih wajar.",
        "crf": 32,
    },
)

PRESETS_BY_ID = {p["id"]: p for p in PRESETS}


# --- Kelas galat khusus ------------------------------------------------------
class KompresVideoError(Exception):
    """Galat pemrosesan kompresi video yang dipetakan ke kode dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar OmniTools."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass
class KompresResult:
    """Hasil kompresi video."""

    data: bytes
    output_name: str
    mime_type: str
    input_bytes: int
    output_bytes: int
    hemat_percent: float
    durasi_detik: float
    resolusi: str
    mode: str
    preset: str


# --- Fungsi pembantu & logika inti -------------------------------------------
def limits_payload() -> dict[str, Any]:
    """Mengembalikan informasi batas operasional kompresi video."""
    return {
        "max_bytes": MAX_BYTES,
        "max_duration_seconds": MAX_DURATION_SECONDS,
        "allowed_formats": [fmt.upper() for fmt in ALLOWED_FORMATS],
        "presets": [
            {
                "id": p["id"],
                "label": p["label"],
                "desc": p["desc"],
            }
            for p in PRESETS
        ],
        "target_mb_min": int(TARGET_MB_MIN),
        "target_mb_max": int(TARGET_MB_MAX),
        "target_mb_default": int(TARGET_MB_DEFAULT),
        "max_output_bytes": MAX_OUTPUT_BYTES,
        "timeout_seconds": PROSES_TIMEOUT_SECONDS,
        "catatan": (
            "Video diproses di server lewat memori/tmpfs lalu langsung dibersihkan. "
            "Batas berkas 25 MB dan durasi maksimal 2 menit. "
            "Jika hasil kompresi lebih besar dari video asal, berkas asli dipertahankan."
        ),
    }


def hitung_bitrate_target(
    target_mb: float,
    durasi_detik: float,
    ada_audio: bool = True,
) -> tuple[int, int]:
    """Hitung alokasi bitrate video dan audio berdasarkan target ukuran dan durasi.

    Rumus bitrate total = (target_mb * 8 * 1000 * 0.96) / durasi_detik, dengan 4%
    cadangan overhead kontainer MP4 agar ukuran berkas tidak melampaui target.

    Mengembalikan tuple (video_kbps, audio_kbps).
    Melempar KompresVideoError('TARGET_TOO_SMALL') bila bitrate video di bawah batas wajar.
    """
    if durasi_detik <= 0:
        raise KompresVideoError("TARGET_TOO_SMALL", "Durasi video tidak valid untuk perhitungan bitrate.", 400)

    # Total bitrate dalam kbps (0.96 cadangan muxing overhead)
    total_kbps = int((target_mb * 8 * 1000 * 0.96) / durasi_detik)

    if ada_audio:
        if total_kbps >= 600:
            audio_kbps = 96
        elif total_kbps >= 350:
            audio_kbps = 80
        else:
            audio_kbps = 64
        video_kbps = total_kbps - audio_kbps
    else:
        audio_kbps = 0
        video_kbps = total_kbps

    if video_kbps < MIN_VIDEO_BITRATE:
        durasi_str = f"{int(durasi_detik)}"
        raise KompresVideoError(
            "TARGET_TOO_SMALL",
            f"Target ukuran {target_mb:g} MB terlalu kecil untuk video berdurasi {durasi_str} detik "
            f"(bitrate video minimal {MIN_VIDEO_BITRATE} kbps). Pilih target ukuran yang lebih besar.",
            400,
        )

    return video_kbps, audio_kbps


def deteksi_format_magic(data: bytes) -> str | None:
    """Deteksi awal format video lewat magic bytes."""
    if not data or len(data) == 0:
        raise KompresVideoError("EMPTY_FILE", "Berkas video kosong.", 400)

    if len(data) < 8:
        return None

    # MP4 / MOV: 'ftyp' pada offset 4
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand == b"qt  ":
            return "mov"
        return "mp4"

    # WebM / MKV: EBML header 1A 45 DF A3
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        header_sample = data[:256].lower()
        if b"matroska" in header_sample:
            return "mkv"
        if b"webm" in header_sample:
            return "webm"
        return "webm"

    return None


def probe_video(data: bytes, ext_hint: str = "mp4") -> dict[str, Any]:
    """Jalankan ffprobe untuk memeriksa kontainer, durasi, dimensi, dan stream video/audio.

    Format dideteksi langsung dari format_name kontainer ffprobe, bukan sekadar ekstensi.
    """
    if not data or len(data) == 0:
        raise KompresVideoError("EMPTY_FILE", "Berkas video kosong.", 400)

    tmp_path: str | None = None
    try:
        clean_ext = ext_hint.lstrip(".") if ext_hint else "mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix="." + clean_ext, dir="/tmp") as tf:
            tmp_path = tf.name
            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass
            tf.write(data)
            tf.flush()

        cmd = [
            FFPROBE,
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            "-i", tmp_path,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=PROSES_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            raise KompresVideoError("PROSES_TIMEOUT", "Proses membaca info video melebihi batas waktu.", 504)
        except FileNotFoundError:
            raise KompresVideoError("PROSES_GAGAL", "Alat ffprobe tidak ditemukan di server.", 500)

        if proc.returncode != 0:
            # Jika magic bytes bukan video (mis. teks atau PNG) -> tolak format tidak didukung
            magic_fmt = deteksi_format_magic(data)
            if magic_fmt is None:
                raise KompresVideoError(
                    "UNSUPPORTED_FORMAT",
                    "Format video belum didukung. Gunakan video MP4, MOV, WebM, atau MKV.",
                    400,
                )
            raise KompresVideoError("DAMAGED_VIDEO", "Berkas video rusak atau tidak dapat dibaca.", 400)

        try:
            probe_data = json.loads(proc.stdout)
        except Exception:
            raise KompresVideoError("DAMAGED_VIDEO", "Berkas video rusak atau tidak dapat dibaca.", 400)

        format_info = probe_data.get("format", {})
        format_name = str(format_info.get("format_name", "")).lower()

        # Deteksi format dari container ffprobe
        container_fmt: str | None = None
        for allowed in ALLOWED_FORMATS:
            if allowed in format_name:
                container_fmt = allowed
                break
        if not container_fmt:
            if "quicktime" in format_name or "3gp" in format_name:
                container_fmt = "mov"
            elif "matroska" in format_name:
                container_fmt = "mkv"

        if not container_fmt or container_fmt not in ALLOWED_FORMATS:
            raise KompresVideoError(
                "UNSUPPORTED_FORMAT",
                "Format video belum didukung. Gunakan video MP4, MOV, WebM, atau MKV.",
                400,
            )

        streams = probe_data.get("streams", [])
        durasi = 0.0
        try:
            durasi = float(format_info.get("duration", 0.0) or 0.0)
        except (ValueError, TypeError):
            durasi = 0.0

        ada_video = False
        lebar: int | None = None
        tinggi: int | None = None
        kodek_video: str | None = None
        ada_audio = False

        for st in streams:
            codec_type = st.get("codec_type")
            if codec_type == "video" and not ada_video:
                ada_video = True
                kodek_video = st.get("codec_name")
                try:
                    lebar = int(st.get("width")) if st.get("width") is not None else None
                except (ValueError, TypeError):
                    lebar = None
                try:
                    tinggi = int(st.get("height")) if st.get("height") is not None else None
                except (ValueError, TypeError):
                    tinggi = None
                if durasi == 0.0 and st.get("duration"):
                    try:
                        durasi = float(st.get("duration"))
                    except (ValueError, TypeError):
                        pass
            elif codec_type == "audio":
                ada_audio = True

        if not ada_video:
            raise KompresVideoError(
                "UNSUPPORTED_FORMAT",
                "Berkas tidak memiliki trek video yang valid untuk dikompres.",
                400,
            )

        return {
            "container": container_fmt,
            "durasi": durasi,
            "lebar": lebar,
            "tinggi": tinggi,
            "ada_video": ada_video,
            "kodek_video": kodek_video,
            "ada_audio": ada_audio,
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def bersihkan_nama_berkas(nama: str) -> str:
    """Bersihkan nama berkas keluaran agar aman untuk header HTTP."""
    if not nama:
        return "video"
    # Ambil nama dasar tanpa path dan ekstensi
    base = os.path.basename(nama)
    base = base.rsplit(".", 1)[0] if "." in base else base
    # Hapus karakter tidak aman
    clean = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', base).strip("._")
    return clean or "video"


def kompres(
    data: bytes,
    nama_asal: str = "",
    mode: str = "kualitas",
    preset: str = "seimbang",
    target_mb: float | str | None = None,
    kecilkan: bool | str = True,
) -> KompresResult:
    """Kompresi berkas video di server memakai ffmpeg."""
    if not data or len(data) == 0:
        raise KompresVideoError("EMPTY_FILE", "Berkas video kosong.", 400)

    if len(data) > MAX_BYTES:
        raise KompresVideoError(
            "FILE_TOO_LARGE",
            f"Ukuran berkas melebihi batas {MAX_BYTES // (1024 * 1024)} MB.",
            413,
        )

    mode_clean = (str(mode) if mode is not None else "").strip().lower()
    if mode_clean not in ("kualitas", "target"):
        raise KompresVideoError(
            "INVALID_PRESET",
            "Pilihan mode kompresi tidak valid. Pilih mode 'kualitas' atau 'target'.",
            400,
        )

    preset_clean = (str(preset) if preset is not None else "seimbang").strip().lower()
    if mode_clean == "kualitas" and preset_clean not in PRESETS_BY_ID:
        raise KompresVideoError(
            "INVALID_PRESET",
            "Pilihan preset kompresi tidak dikenal. Pilih ringan, seimbang, atau kuat.",
            400,
        )

    target_mb_val: float | None = None
    if mode_clean == "target":
        if target_mb is None or str(target_mb).strip() == "":
            raise KompresVideoError(
                "INVALID_TARGET",
                f"Target ukuran berkas harus berupa angka antara {int(TARGET_MB_MIN)} sampai {int(TARGET_MB_MAX)} MB.",
                400,
            )
        try:
            target_mb_val = float(str(target_mb).replace(",", ".").strip())
        except (ValueError, TypeError):
            raise KompresVideoError(
                "INVALID_TARGET",
                f"Target ukuran berkas harus berupa angka antara {int(TARGET_MB_MIN)} sampai {int(TARGET_MB_MAX)} MB.",
                400,
            )
        if math.isnan(target_mb_val) or math.isinf(target_mb_val) or target_mb_val < TARGET_MB_MIN or target_mb_val > TARGET_MB_MAX:
            raise KompresVideoError(
                "INVALID_TARGET",
                f"Target ukuran berkas harus di antara {int(TARGET_MB_MIN)} dan {int(TARGET_MB_MAX)} MB.",
                400,
            )

    # Normalisasi opsi kecilkan
    if isinstance(kecilkan, str):
        kecilkan_bool = kecilkan.strip().lower() in ("ya", "true", "1")
    else:
        kecilkan_bool = bool(kecilkan)

    # Deteksi format container dan periksa metadata
    ext_hint = "mp4"
    if nama_asal and "." in nama_asal:
        ext_hint = nama_asal.rsplit(".", 1)[-1].lower()

    probe_info = probe_video(data, ext_hint=ext_hint)
    container_fmt = probe_info["container"]
    durasi = float(probe_info.get("durasi", 0.0) or 0.0)

    if durasi > MAX_DURATION_SECONDS:
        durasi_menit = MAX_DURATION_SECONDS // 60
        raise KompresVideoError(
            "DURATION_TOO_LONG",
            f"Durasi video ({int(durasi)} detik) melebihi batas maksimal {durasi_menit} menit ({MAX_DURATION_SECONDS} detik).",
            400,
        )

    ada_audio = bool(probe_info.get("ada_audio"))
    lebar = probe_info.get("lebar")
    tinggi = probe_info.get("tinggi")

    # Siapkan filter skala
    # Jika kecilkan=ya dan sisi terpanjang > 1280 px: perkecil menjaga rasio dan dimensi genap
    # Jangan pernah memperbesar video kecil. Dimensi selalu dipastikan genap untuk libx264.
    if lebar and tinggi:
        sisi_terpanjang = max(lebar, tinggi)
        if kecilkan_bool and sisi_terpanjang > MAX_DIMENSION:
            if lebar >= tinggi:
                vf_scale = f"scale={MAX_DIMENSION}:-2"
            else:
                vf_scale = f"scale=-2:{MAX_DIMENSION}"
        else:
            vf_scale = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    else:
        if kecilkan_bool:
            vf_scale = (
                f"scale='if(gt(max(iw,ih),{MAX_DIMENSION}),if(gte(iw,ih),{MAX_DIMENSION},-2),trunc(iw/2)*2):"
                f"if(gt(max(iw,ih),{MAX_DIMENSION}),if(gte(iw,ih),-2,{MAX_DIMENSION}),trunc(ih/2)*2)'"
            )
        else:
            vf_scale = "scale=trunc(iw/2)*2:trunc(ih/2)*2"

    in_tmp_path: str | None = None
    out_tmp_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix="." + container_fmt, dir="/tmp") as in_tf:
            in_tmp_path = in_tf.name
            try:
                os.chmod(in_tmp_path, 0o600)
            except OSError:
                pass
            in_tf.write(data)
            in_tf.flush()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4", dir="/tmp") as out_tf:
            out_tmp_path = out_tf.name
            try:
                os.chmod(out_tmp_path, 0o600)
            except OSError:
                pass

        cmd = [
            FFMPEG,
            "-nostdin",
            "-hide_banner",
            "-loglevel", "error",
            "-i", in_tmp_path,
        ]

        if mode_clean == "kualitas":
            crf = PRESETS_BY_ID[preset_clean]["crf"]
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", str(crf),
                "-pix_fmt", "yuv420p",
                "-vf", vf_scale,
            ])
            if ada_audio:
                cmd.extend(["-c:a", "aac", "-b:a", "96k"])
            else:
                cmd.append("-an")
        else:
            # Mode target ukuran
            assert target_mb_val is not None
            durasi_hitung = durasi if durasi > 0 else 1.0
            video_kbps, audio_kbps = hitung_bitrate_target(target_mb_val, durasi_hitung, ada_audio)
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-b:v", f"{video_kbps}k",
                "-maxrate", f"{int(video_kbps * 1.5)}k",
                "-bufsize", f"{video_kbps * 2}k",
                "-pix_fmt", "yuv420p",
                "-vf", vf_scale,
            ])
            if ada_audio and audio_kbps > 0:
                cmd.extend(["-c:a", "aac", "-b:a", f"{audio_kbps}k"])
            else:
                cmd.append("-an")

        cmd.extend([
            "-movflags", "+faststart",
            "-threads", "2",
            "-y",
            out_tmp_path,
        ])

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=PROSES_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            raise KompresVideoError(
                "PROSES_TIMEOUT",
                "Proses kompresi video melebihi batas waktu (110 detik). Coba video yang lebih pendek atau preset lebih ringan.",
                504,
            )
        except FileNotFoundError:
            raise KompresVideoError("PROSES_GAGAL", "Alat ffmpeg tidak ditemukan di server.", 500)

        if proc.returncode != 0:
            logger.warning("ffmpeg kompres gagal: code=%s", proc.returncode)
            raise KompresVideoError(
                "PROSES_GAGAL",
                "Video tidak dapat dikompres. Pastikan berkas video tidak rusak.",
                500,
            )

        if not os.path.exists(out_tmp_path) or os.path.getsize(out_tmp_path) == 0:
            logger.warning("ffmpeg kompres keluaran kosong atau tidak terbentuk")
            raise KompresVideoError(
                "PROSES_GAGAL",
                "Gagal menghasilkan berkas video terkompresi.",
                500,
            )

        out_size = os.path.getsize(out_tmp_path)
        if out_size > MAX_OUTPUT_BYTES:
            raise KompresVideoError(
                "FILE_TOO_LARGE",
                f"Ukuran hasil kompresi ({out_size // (1024 * 1024)} MB) melebihi batas {MAX_OUTPUT_BYTES // (1024 * 1024)} MB.",
                413,
            )

        with open(out_tmp_path, "rb") as f:
            out_bytes = f.read()

        in_size = len(data)

        clean_base = bersihkan_nama_berkas(nama_asal)

        # Jika hasil kompresi ternyata lebih besar atau sama dengan aslinya, gunakan berkas asli
        if len(out_bytes) >= in_size:
            final_data = data
            final_out_size = in_size
            hemat_percent = 0.0
            mime_map = {
                "mp4": "video/mp4",
                "mov": "video/quicktime",
                "webm": "video/webm",
                "mkv": "video/x-matroska",
            }
            final_mime = mime_map.get(container_fmt, f"video/{container_fmt}")
            output_name = f"{clean_base}-kompres.{container_fmt}"
        else:
            final_data = out_bytes
            final_out_size = len(out_bytes)
            hemat_percent = round(((in_size - final_out_size) / in_size) * 100, 1)
            final_mime = "video/mp4"
            output_name = f"{clean_base}-kompres.mp4"

        resolusi = "-"
        if lebar and tinggi:
            resolusi = f"{lebar}x{tinggi}"

        return KompresResult(
            data=final_data,
            output_name=output_name,
            mime_type=final_mime,
            input_bytes=in_size,
            output_bytes=final_out_size,
            hemat_percent=hemat_percent,
            durasi_detik=round(durasi, 1),
            resolusi=resolusi,
            mode=mode_clean,
            preset=preset_clean if mode_clean == "kualitas" else f"target {target_mb_val:g} MB",
        )
    finally:
        if in_tmp_path and os.path.exists(in_tmp_path):
            try:
                os.remove(in_tmp_path)
            except OSError:
                pass
        if out_tmp_path and os.path.exists(out_tmp_path):
            try:
                os.remove(out_tmp_path)
            except OSError:
                pass
