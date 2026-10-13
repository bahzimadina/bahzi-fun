"""Modul ekstraksi audio dari video memakai ffmpeg/ffprobe.

Semua proses dijalankan di server dengan berkas sementara di /tmp (tmpfs)
yang selalu dibersihkan setelah selesai.
Privasi: log hanya mencatat metadata numerik dan status (durasi, byte, format).
Nama berkas pengguna dan isinya tidak dicatat ke log.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import subprocess
import tempfile
from typing import Any

from .video_trim import VideoTrimError, deteksi_format

logger = logging.getLogger("omnitools.api")

# --- Batas operasional & konfigurasi -----------------------------------------
MAX_BYTES = 25 * 1024 * 1024          # 25 MB
MAX_DURATION_SECONDS = 300            # 5 menit
MAX_OUTPUT_BYTES = 100 * 1024 * 1024  # 100 MB
ALLOWED_FORMATS = ("mp4", "mov", "webm", "mkv")

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
PROSES_TIMEOUT_SECONDS = 110
CHUNK_SIZE = 1024 * 1024

OUTPUTS = (
    {
        "id": "mp3",
        "label": "MP3",
        "desc": "Paling umum dipakai, bisa diputar hampir di semua aplikasi. 192 kbps.",
        "ext": "mp3",
        "mime": "audio/mpeg",
        "filename": "suara.mp3",
    },
    {
        "id": "m4a",
        "label": "M4A",
        "desc": "Kualitas bagus dengan berkas yang lebih kecil (AAC 192 kbps).",
        "ext": "m4a",
        "mime": "audio/mp4",
        "filename": "suara.m4a",
    },
    {
        "id": "wav",
        "label": "WAV",
        "desc": "Tanpa kompresi, berkas paling besar (PCM 16-bit, 44,1 kHz).",
        "ext": "wav",
        "mime": "audio/wav",
        "filename": "suara.wav",
    },
)

OUTPUTS_BY_ID = {opt["id"]: opt for opt in OUTPUTS}


# --- Kelas galat khusus ------------------------------------------------------
class AudioExtractError(Exception):
    """Galat pemrosesan ekstraksi audio yang dipetakan ke kode dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar OmniTools."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass
class ExtractResult:
    """Hasil ekstraksi audio dari video."""

    data: bytes
    output_name: str
    mime_type: str
    format_id: str
    audio_seconds: float
    source_seconds: float


# --- Fungsi pembantu & logika inti -------------------------------------------
def limits_payload() -> dict[str, Any]:
    """Mengembalikan informasi batas operasional ekstraksi audio."""
    return {
        "max_bytes": MAX_BYTES,
        "max_duration_seconds": MAX_DURATION_SECONDS,
        "max_output_bytes": MAX_OUTPUT_BYTES,
        "allowed_formats": [fmt.upper() for fmt in ALLOWED_FORMATS],
        "outputs": [
            {
                "id": opt["id"],
                "label": opt["label"],
                "desc": opt["desc"],
                "mime": opt["mime"],
                "ext": opt["ext"],
            }
            for opt in OUTPUTS
        ],
        "catatan": (
            "Berkas diproses di server lalu langsung dihapus. "
            "Hasil terbaik dari video dengan suara jelas. "
            "Kualitas suara tidak bisa bertambah dari kualitas aslinya. "
            "Berkas dengan suara bawaan berbahasa apa pun tetap bisa diambil."
        ),
    }


def probe(data: bytes, ext: str) -> dict[str, Any]:
    """Jalankan ffprobe untuk memeriksa durasi, stream audio, dan codec."""
    if not data or len(data) == 0:
        raise AudioExtractError("EMPTY_FILE", "Berkas video kosong.", 400)

    clean_ext = ext.lstrip(".")
    tmp_path: str | None = None
    try:
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
            raise AudioExtractError("EXTRACT_TIMEOUT", "Proses membaca info video melebihi batas waktu.", 504)
        except FileNotFoundError:
            raise AudioExtractError("EXTRACT_FAILED", "Alat ffprobe tidak ditemukan di server.", 500)

        if proc.returncode != 0:
            logger.warning("ffprobe gagal membaca berkas: code=%s", proc.returncode)
            raise AudioExtractError("EXTRACT_FAILED", "Berkas video rusak atau tidak bisa dibaca.", 422)

        try:
            probe_data = json.loads(proc.stdout)
        except Exception:
            raise AudioExtractError("EXTRACT_FAILED", "Berkas video rusak atau tidak bisa dibaca.", 422)

        format_info = probe_data.get("format", {})
        streams = probe_data.get("streams", [])

        durasi = 0.0
        try:
            durasi = float(format_info.get("duration", 0.0) or 0.0)
        except (ValueError, TypeError):
            durasi = 0.0

        ada_audio = False
        kodek_audio: str | None = None
        kanal_audio: int | None = None

        for st in streams:
            codec_type = st.get("codec_type")
            if codec_type == "audio" and not ada_audio:
                ada_audio = True
                kodek_audio = st.get("codec_name")
                try:
                    kanal_audio = int(st.get("channels")) if st.get("channels") is not None else None
                except (ValueError, TypeError):
                    kanal_audio = None
                if durasi == 0.0 and st.get("duration"):
                    try:
                        durasi = float(st.get("duration"))
                    except (ValueError, TypeError):
                        pass

        if not ada_audio:
            raise AudioExtractError(
                "NO_AUDIO_STREAM",
                "Berkas ini tidak punya suara, jadi tidak ada yang bisa diambil.",
                400,
            )

        return {
            "durasi": durasi,
            "ada_audio": ada_audio,
            "kodek_audio": kodek_audio,
            "kanal_audio": kanal_audio,
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def durasi_berkas(path: str) -> float | None:
    """Baca durasi nyata sebuah berkas audio/video lewat ffprobe.

    Tidak pernah melempar galat ke pemanggil; mengembalikan None bila
    ffprobe gagal atau hasilnya tidak masuk akal.
    """
    try:
        proc = subprocess.run(
            [FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-i", path],
            capture_output=True,
            text=True,
            timeout=PROSES_TIMEOUT_SECONDS,
        )
        info = json.loads(proc.stdout)
        durasi = float(info.get("format", {}).get("duration"))
        if durasi > 0:
            return durasi
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
        return None


def ambil_audio(
    data: bytes,
    nama: str,
    format_tujuan: str = "mp3",
) -> ExtractResult:
    """Ambil trek audio dari berkas video dan konversi ke format pilihan."""
    # 1. Validasi kosong / terlalu besar
    if data is None or len(data) == 0:
        raise AudioExtractError("EMPTY_FILE", "Berkas video kosong.", 400)

    if len(data) > MAX_BYTES:
        raise AudioExtractError(
            "FILE_TOO_LARGE",
            f"Ukuran berkas melebihi batas {MAX_BYTES // (1024 * 1024)} MB.",
            413,
        )

    # 2. Deteksi format masukan
    try:
        fmt = deteksi_format(data, nama)
    except VideoTrimError:
        fmt = None

    if not fmt or fmt not in ALLOWED_FORMATS:
        raise AudioExtractError(
            "UNSUPPORTED_FORMAT",
            "Format video belum didukung. Gunakan MP4, MOV, WebM, atau MKV.",
            400,
        )

    # Validasi format tujuan
    fmt_target = (str(format_tujuan) if format_tujuan is not None else "").strip().lower()
    if not fmt_target:
        fmt_target = "mp3"

    if fmt_target not in OUTPUTS_BY_ID:
        raise AudioExtractError(
            "UNSUPPORTED_OUTPUT",
            "Format keluaran audio tidak didukung. Pilih MP3, M4A, atau WAV.",
            400,
        )

    target_cfg = OUTPUTS_BY_ID[fmt_target]
    out_name = target_cfg["filename"]
    out_mime = target_cfg["mime"]
    out_ext = target_cfg["ext"]

    # 3. Probe untuk memastikan stream audio dan mendapatkan durasi
    probe_info = probe(data, fmt)
    durasi_masukan = float(probe_info.get("durasi", 0.0) or 0.0)

    # 4. Batas durasi video
    if durasi_masukan > MAX_DURATION_SECONDS:
        raise AudioExtractError(
            "VIDEO_TOO_LONG",
            f"Durasi berkas video melebihi batas {MAX_DURATION_SECONDS // 60} menit.",
            400,
        )

    # 6. Eksekusi konversi dengan ffmpeg
    in_tmp_path: str | None = None
    out_tmp_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix="." + fmt, dir="/tmp") as in_tf:
            in_tmp_path = in_tf.name
            try:
                os.chmod(in_tmp_path, 0o600)
            except OSError:
                pass
            in_tf.write(data)
            in_tf.flush()

        with tempfile.NamedTemporaryFile(delete=False, suffix="." + out_ext, dir="/tmp") as out_tf:
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
            "-vn",
        ]

        if fmt_target == "mp3":
            cmd.extend([
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                "-ar", "44100",
                "-map_metadata", "-1",
                "-threads", "2",
                "-y", out_tmp_path,
            ])
        elif fmt_target == "m4a":
            cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-movflags", "+faststart",
                "-map_metadata", "-1",
                "-threads", "2",
                "-y", out_tmp_path,
            ])
        elif fmt_target == "wav":
            cmd.extend([
                "-c:a", "pcm_s16le",
                "-ar", "44100",
                "-ac", "2",
                "-map_metadata", "-1",
                "-y", out_tmp_path,
            ])

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=PROSES_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            raise AudioExtractError(
                "EXTRACT_TIMEOUT",
                "Proses mengambil audio melebihi batas waktu.",
                504,
            )
        except FileNotFoundError:
            raise AudioExtractError("EXTRACT_FAILED", "Alat ffmpeg tidak ditemukan di server.", 500)

        if proc.returncode != 0:
            logger.warning("ffmpeg audio extract gagal: code=%s", proc.returncode)
            raise AudioExtractError(
                "EXTRACT_FAILED",
                "Audio tidak bisa diambil dari video ini. Coba berkas video lain.",
                422,
            )

        if not os.path.exists(out_tmp_path) or os.path.getsize(out_tmp_path) == 0:
            logger.warning("ffmpeg audio extract keluaran kosong atau tidak terbentuk")
            raise AudioExtractError(
                "EXTRACT_FAILED",
                "Audio tidak bisa diambil dari video ini. Coba berkas video lain.",
                422,
            )

        out_size = os.path.getsize(out_tmp_path)
        if out_size > MAX_OUTPUT_BYTES:
            raise AudioExtractError(
                "OUTPUT_TOO_LARGE",
                f"Ukuran hasil audio ({out_size // (1024 * 1024)} MB) melebihi batas {MAX_OUTPUT_BYTES // (1024 * 1024)} MB.",
                413,
            )

        with open(out_tmp_path, "rb") as f:
            out_bytes = f.read()

        durasi_hasil = durasi_berkas(out_tmp_path)
        if durasi_hasil is not None and durasi_hasil > 0:
            audio_seconds = round(durasi_hasil, 2)
        else:
            audio_seconds = round(durasi_masukan, 2)

        return ExtractResult(
            data=out_bytes,
            output_name=out_name,
            mime_type=out_mime,
            format_id=fmt_target,
            audio_seconds=audio_seconds,
            source_seconds=round(durasi_masukan, 2),
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
