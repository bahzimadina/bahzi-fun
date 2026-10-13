"""Modul pembalikan video (memutar video mundur) memakai ffmpeg/ffprobe.

Semua proses dijalankan di server dengan berkas sementara di /tmp (tmpfs)
yang selalu dibersihkan setelah selesai.
Privasi: log hanya mencatat metadata numerik dan status (durasi, byte, kecepatan).
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

from .video_trim import VideoTrimError, deteksi_format, durasi_berkas

logger = logging.getLogger("omnitools.api")

# --- Batas operasional & konfigurasi -----------------------------------------
MAX_BYTES = 25 * 1024 * 1024           # 25 MB
MAX_DURATION_SECONDS = 60              # 60 detik
MAX_OUTPUT_BYTES = 100 * 1024 * 1024   # 100 MB
ALLOWED_FORMATS = ("mp4", "mov", "webm", "mkv")

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
PROSES_TIMEOUT_SECONDS = 110

KECEPATAN = (
    {
        "id": "0.5",
        "label": "Setengah kecepatan",
        "desc": "Hasil bergerak dua kali lebih lambat, cocok untuk melihat gerakan kecil.",
    },
    {
        "id": "1",
        "label": "Kecepatan asli",
        "desc": "Video berjalan sesuai kecepatan normal aslinya.",
    },
    {
        "id": "2",
        "label": "Dua kali lebih cepat",
        "desc": "Hasil bergerak dua kali lebih cepat, cocok untuk rekaman panjang.",
    },
)

KECEPATAN_BY_ID = {opt["id"]: opt for opt in KECEPATAN}

SUARA = (
    {
        "id": "ikut",
        "label": "Suara ikut dibalik",
        "desc": "Suaranya juga diputar mundur sehingga terdengar aneh. Pilih ini kalau suara tidak penting.",
    },
    {
        "id": "bisukan",
        "label": "Tanpa suara",
        "desc": "Hasilnya tanpa suara sama sekali. Paling aman untuk rekaman rapat atau video berisi percakapan.",
    },
)

SUARA_BY_ID = {opt["id"]: opt for opt in SUARA}


# --- Kelas galat khusus ------------------------------------------------------
class ReverseError(Exception):
    """Galat pemrosesan pembalikan video yang dipetakan ke kode dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar OmniTools."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass
class ReverseResult:
    """Hasil pembalikan video."""

    data: bytes
    output_name: str
    mime_type: str
    source_seconds: float
    result_seconds: float
    audio_mode: str
    speed: str


# --- Fungsi pembantu & logika inti -------------------------------------------
def limits_payload() -> dict[str, Any]:
    """Mengembalikan informasi batas operasional pembalik video."""
    return {
        "max_bytes": MAX_BYTES,
        "max_duration_seconds": MAX_DURATION_SECONDS,
        "max_output_bytes": MAX_OUTPUT_BYTES,
        "allowed_formats": [fmt.upper() for fmt in ALLOWED_FORMATS],
        "kecepatan": [
            {
                "id": opt["id"],
                "label": opt["label"],
                "desc": opt["desc"],
            }
            for opt in KECEPATAN
        ],
        "suara": [
            {
                "id": opt["id"],
                "label": opt["label"],
                "desc": opt["desc"],
            }
            for opt in SUARA
        ],
        "catatan": (
            "Berkas diproses di server lalu langsung dihapus. "
            "Video diputar mundur seluruhnya sehingga video panjang butuh waktu lebih lama. "
            "Batas durasi video maksimal 60 detik. "
            "Hasil terbaik dari video yang gambar dan suaranya jelas. "
            "Kalau berkas tidak ada suaranya, hasil otomatis tanpa suara."
        ),
    }


def probe(data: bytes, ext: str) -> dict[str, Any]:
    """Jalankan ffprobe untuk memeriksa durasi dan keberadaan stream video/audio."""
    if not data or len(data) == 0:
        raise ReverseError("EMPTY_FILE", "Berkas video kosong.", 400)

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
            raise ReverseError("REVERSE_TIMEOUT", "Proses membaca info video melebihi batas waktu.", 504)
        except FileNotFoundError:
            raise ReverseError("REVERSE_FAILED", "Alat ffprobe tidak ditemukan di server.", 500)

        if proc.returncode != 0:
            logger.warning("ffprobe gagal membaca berkas: code=%s", proc.returncode)
            raise ReverseError("REVERSE_FAILED", "Berkas video rusak atau tidak bisa dibaca.", 422)

        try:
            probe_data = json.loads(proc.stdout)
        except Exception:
            raise ReverseError("REVERSE_FAILED", "Berkas video rusak atau tidak bisa dibaca.", 422)

        format_info = probe_data.get("format", {})
        streams = probe_data.get("streams", [])

        durasi = 0.0
        try:
            durasi = float(format_info.get("duration", 0.0) or 0.0)
        except (ValueError, TypeError):
            durasi = 0.0

        ada_video = False
        resolusi = None
        ada_audio = False

        for st in streams:
            codec_type = st.get("codec_type")
            if codec_type == "video" and not ada_video:
                ada_video = True
                w = st.get("width")
                h = st.get("height")
                if w and h:
                    resolusi = f"{w}x{h}"
                if durasi == 0.0 and st.get("duration"):
                    try:
                        durasi = float(st.get("duration"))
                    except (ValueError, TypeError):
                        pass
            elif codec_type == "audio":
                ada_audio = True

        if not ada_video:
            raise ReverseError(
                "NO_VIDEO_STREAM",
                "Berkas ini tidak punya gambar video, jadi tidak ada yang bisa dibalik.",
                400,
            )

        return {
            "durasi": durasi,
            "ada_video": ada_video,
            "resolusi": resolusi,
            "ada_audio": ada_audio,
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def balik_video(
    data: bytes,
    nama: str,
    suara: str = "ikut",
    kecepatan: str = "1",
) -> ReverseResult:
    """Putar video mundur dengan pilihan kecepatan dan mode suara."""
    if data is None or len(data) == 0:
        raise ReverseError("EMPTY_FILE", "Berkas video kosong.", 400)

    if len(data) > MAX_BYTES:
        raise ReverseError(
            "FILE_TOO_LARGE",
            f"Ukuran berkas melebihi batas {MAX_BYTES // (1024 * 1024)} MB.",
            413,
        )

    try:
        fmt = deteksi_format(data, nama)
    except VideoTrimError:
        fmt = None

    if not fmt or fmt not in ALLOWED_FORMATS:
        raise ReverseError(
            "UNSUPPORTED_FORMAT",
            "Format video belum didukung. Gunakan MP4, MOV, WebM, atau MKV.",
            400,
        )

    suara_clean = (str(suara) if suara is not None else "").strip().lower()
    if not suara_clean:
        suara_clean = "ikut"
    if suara_clean not in SUARA_BY_ID:
        raise ReverseError(
            "UNSUPPORTED_AUDIO_MODE",
            "Pilihan suara tidak dikenali. Pilih suara ikut dibalik atau tanpa suara.",
            400,
        )

    kecepatan_clean = (str(kecepatan) if kecepatan is not None else "").strip().lower()
    if not kecepatan_clean:
        kecepatan_clean = "1"
    if kecepatan_clean not in KECEPATAN_BY_ID:
        raise ReverseError(
            "UNSUPPORTED_SPEED",
            "Pilihan kecepatan tidak dikenali. Pilih kecepatan asli, setengah, atau dua kali.",
            400,
        )

    probe_info = probe(data, fmt)
    durasi_masukan = float(probe_info.get("durasi", 0.0) or 0.0)

    if durasi_masukan > MAX_DURATION_SECONDS:
        raise ReverseError(
            "VIDEO_TOO_LONG",
            f"Durasi video melebihi batas {MAX_DURATION_SECONDS} detik. Potong dulu videonya, lalu balik potongannya.",
            400,
        )

    has_audio = bool(probe_info.get("ada_audio"))
    sertakan_audio = (suara_clean == "ikut" and has_audio)

    if suara_clean == "bisukan":
        audio_mode = "tanpa suara"
    elif has_audio:
        audio_mode = "ikut"
    else:
        audio_mode = "tidak ada suara"

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

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4", dir="/tmp") as out_tf:
            out_tmp_path = out_tf.name
            try:
                os.chmod(out_tmp_path, 0o600)
            except OSError:
                pass

        if kecepatan_clean == "0.5":
            atempo_val = "0.5"
        elif kecepatan_clean == "2":
            atempo_val = "2.0"
        else:
            atempo_val = "1.0"

        v_filter = f"[0:v]scale='min(1280,iw)':-2,reverse,setpts=PTS/{kecepatan_clean}[v]"

        cmd = [
            FFMPEG,
            "-nostdin",
            "-hide_banner",
            "-loglevel", "error",
            "-i", in_tmp_path,
        ]

        if sertakan_audio:
            a_filter = f"[0:a]areverse,atempo={atempo_val}[a]"
            cmd.extend([
                "-filter_complex", f"{v_filter};{a_filter}",
                "-map", "[v]",
                "-map", "[a]",
                "-c:a", "aac",
                "-b:a", "128k",
                "-ac", "2",
                "-ar", "44100",
            ])
        else:
            cmd.extend([
                "-filter_complex", v_filter,
                "-map", "[v]",
                "-an",
            ])

        cmd.extend([
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-threads", "2",
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
            raise ReverseError(
                "REVERSE_TIMEOUT",
                "Proses membalik video melebihi batas waktu.",
                504,
            )
        except FileNotFoundError:
            raise ReverseError("REVERSE_FAILED", "Alat ffmpeg tidak ditemukan di server.", 500)

        if proc.returncode != 0:
            logger.warning("ffmpeg reverse video gagal: code=%s", proc.returncode)
            raise ReverseError(
                "REVERSE_FAILED",
                "Video ini tidak bisa dibalik. Coba berkas video lain.",
                422,
            )

        if not os.path.exists(out_tmp_path) or os.path.getsize(out_tmp_path) == 0:
            logger.warning("ffmpeg reverse video keluaran kosong atau tidak terbentuk")
            raise ReverseError(
                "REVERSE_FAILED",
                "Video ini tidak bisa dibalik. Coba berkas video lain.",
                422,
            )

        out_size = os.path.getsize(out_tmp_path)
        if out_size > MAX_OUTPUT_BYTES:
            raise ReverseError(
                "OUTPUT_TOO_LARGE",
                f"Ukuran hasil video ({out_size // (1024 * 1024)} MB) melebihi batas {MAX_OUTPUT_BYTES // (1024 * 1024)} MB.",
                413,
            )

        with open(out_tmp_path, "rb") as f:
            out_bytes = f.read()

        durasi_hasil = durasi_berkas(out_tmp_path)
        if durasi_hasil is not None and durasi_hasil > 0:
            result_seconds = round(durasi_hasil, 2)
        else:
            speed_factor = float(kecepatan_clean)
            result_seconds = round(durasi_masukan / speed_factor, 2)

        return ReverseResult(
            data=out_bytes,
            output_name="video-dibalik.mp4",
            mime_type="video/mp4",
            source_seconds=round(durasi_masukan, 2),
            result_seconds=result_seconds,
            audio_mode=audio_mode,
            speed=kecepatan_clean,
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
