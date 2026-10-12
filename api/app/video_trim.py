"""Modul pemotongan video memakai ffmpeg/ffprobe.

Semua proses dijalankan di server dengan berkas sementara di /tmp (tmpfs)
yang selalu dibersihkan setelah selesai.
Privasi: log hanya mencatat metadata numerik dan status (durasi, byte, mode).
Nama berkas pengguna dan isinya tidak dicatat ke log.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import math
import os
import subprocess
import tempfile
from typing import Any

logger = logging.getLogger("omnitools.api")

# --- Batas operasional & konfigurasi -----------------------------------------
MAX_BYTES = 25 * 1024 * 1024          # 25 MB
MAX_DURATION_SECONDS = 300            # 5 menit
MIN_CLIP_SECONDS = 1                  # Minimal 1 detik
MAX_CLIP_SECONDS = 120                # Maksimal 2 menit
MAX_OUTPUT_BYTES = 100 * 1024 * 1024  # 100 MB
ALLOWED_FORMATS = ("mp4", "mov", "webm", "mkv")

MODES = (
    {
        "id": "cepat",
        "label": "Potong cepat",
        "desc": "Tidak menulis ulang gambar, hasilnya hampir seketika; potongan menempel ke titik kunci terdekat.",
    },
    {
        "id": "presisi",
        "label": "Potong presisi",
        "desc": "Gambar ditulis ulang supaya potongan tepat di detik yang dipilih; prosesnya lebih lama.",
    },
)

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
PROSES_TIMEOUT_SECONDS = 110
CHUNK_SIZE = 1024 * 1024


# --- Kelas galat khusus ------------------------------------------------------
class VideoTrimError(Exception):
    """Galat pemrosesan potong video yang dipetakan ke kode dan status HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Format respons galat standar OmniTools."""
        return {"error": {"code": self.code, "message": self.message}}


@dataclass
class TrimResult:
    """Hasil pemotongan video."""

    data: bytes
    output_name: str
    mime_type: str
    clip_seconds: float
    mode: str
    durasi_masukan: float
    resolusi: str | None


# --- Fungsi pembantu & logika inti -------------------------------------------
def limits_payload() -> dict[str, Any]:
    """Mengembalikan informasi batas operasional pemotong video."""
    return {
        "max_bytes": MAX_BYTES,
        "max_duration_seconds": MAX_DURATION_SECONDS,
        "min_clip_seconds": MIN_CLIP_SECONDS,
        "max_clip_seconds": MAX_CLIP_SECONDS,
        "max_output_bytes": MAX_OUTPUT_BYTES,
        "allowed_formats": [fmt.upper() for fmt in ALLOWED_FORMATS],
        "modes": [dict(m) for m in MODES],
        "output_format": "MP4 untuk presisi; untuk mode cepat sama dengan berkas masukan",
        "catatan": (
            "Berkas diproses di server lalu langsung dihapus. "
            "Durasi masukan paling lama 5 menit. "
            "Mode cepat memotong di titik kunci terdekat."
        ),
    }


def deteksi_format(data: bytes, nama: str) -> str | None:
    """Deteksi format video lewat magic bytes dan brand info."""
    if data is None or len(data) == 0:
        raise VideoTrimError("EMPTY_FILE", "Berkas video kosong.", 400)

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
        if nama and nama.lower().endswith(".mkv"):
            return "mkv"
        return "webm"

    return None


def parse_waktu(nilai: Any, nama_field: str = "Waktu") -> float:
    """Parse string waktu ('12', '12.5', 'mm:ss', 'hh:mm:ss') atau angka jadi detik."""
    err_msg = f"{nama_field} belum diisi dengan benar. Isi dalam detik (12) atau menit:detik (00:12)."
    if nilai is None:
        raise VideoTrimError("INVALID_TIME", err_msg, 400)

    if isinstance(nilai, bool):
        raise VideoTrimError("INVALID_TIME", err_msg, 400)

    if isinstance(nilai, (int, float)):
        val = float(nilai)
        if math.isnan(val) or math.isinf(val) or val < 0 or val > 86400:
            raise VideoTrimError("INVALID_TIME", err_msg, 400)
        return val

    s = str(nilai).strip()
    if not s or s.startswith("-") or "-" in s:
        raise VideoTrimError("INVALID_TIME", err_msg, 400)

    parts = s.split(":")
    try:
        if len(parts) == 1:
            val = float(parts[0])
            if val < 0 or val > 86400 or math.isnan(val) or math.isinf(val):
                raise VideoTrimError("INVALID_TIME", err_msg, 400)
            return val
        elif len(parts) == 2:
            m = int(parts[0]) if "." not in parts[0] else float(parts[0])
            s_val = float(parts[1])
            if m < 0 or s_val < 0 or s_val >= 60:
                raise VideoTrimError("INVALID_TIME", err_msg, 400)
            val = m * 60.0 + s_val
            if val < 0 or val > 86400 or math.isnan(val) or math.isinf(val):
                raise VideoTrimError("INVALID_TIME", err_msg, 400)
            return val
        elif len(parts) == 3:
            h = int(parts[0]) if "." not in parts[0] else float(parts[0])
            m = int(parts[1]) if "." not in parts[1] else float(parts[1])
            s_val = float(parts[2])
            if h < 0 or m < 0 or m >= 60 or s_val < 0 or s_val >= 60:
                raise VideoTrimError("INVALID_TIME", err_msg, 400)
            val = h * 3600.0 + m * 60.0 + s_val
            if val < 0 or val > 86400 or math.isnan(val) or math.isinf(val):
                raise VideoTrimError("INVALID_TIME", err_msg, 400)
            return val
        else:
            raise VideoTrimError("INVALID_TIME", err_msg, 400)
    except (ValueError, TypeError):
        raise VideoTrimError("INVALID_TIME", err_msg, 400)


def probe(data: bytes, ext: str) -> dict[str, Any]:
    """Jalankan ffprobe untuk memeriksa durasi, dimensi, dan keberadaan stream video/audio."""
    if not data or len(data) == 0:
        raise VideoTrimError("EMPTY_FILE", "Berkas video kosong.", 400)

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
            raise VideoTrimError("TRIM_TIMEOUT", "Proses membaca info video melebihi batas waktu.", 504)
        except FileNotFoundError:
            raise VideoTrimError("TRIM_FAILED", "Alat ffprobe tidak ditemukan di server.", 500)

        if proc.returncode != 0:
            logger.warning("ffprobe gagal membaca berkas: code=%s", proc.returncode)
            raise VideoTrimError("UNREADABLE_VIDEO", "Berkas video rusak atau tidak bisa dibaca.", 400)

        try:
            probe_data = json.loads(proc.stdout)
        except Exception:
            raise VideoTrimError("UNREADABLE_VIDEO", "Berkas video rusak atau tidak bisa dibaca.", 400)

        format_info = probe_data.get("format", {})
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

        return {
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


def durasi_berkas(path: str) -> float | None:
    """Baca durasi nyata sebuah berkas video lewat ffprobe.

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


def nama_keluaran(mode: str, fmt: str) -> str:
    """Tentukan nama berkas hasil potongan berdasarkan mode dan format masukan."""
    if mode == "presisi":
        return "potongan.mp4"
    if fmt in ("webm", "mkv"):
        return "potongan.webm"
    return "potongan.mp4"


def potong(
    data: bytes,
    nama: str,
    mulai: str | float,
    akhir: str | float,
    mode: str,
) -> TrimResult:
    """Potong berkas video sesuai detik mulai dan selesai."""
    if not data or len(data) == 0:
        raise VideoTrimError("EMPTY_FILE", "Berkas video kosong.", 400)

    if len(data) > MAX_BYTES:
        raise VideoTrimError(
            "FILE_TOO_LARGE",
            f"Ukuran berkas melebihi batas {MAX_BYTES // (1024 * 1024)} MB.",
            413,
        )

    mode_clean = (str(mode) if mode is not None else "").strip().lower()
    if mode_clean not in ("cepat", "presisi"):
        raise VideoTrimError("UNSUPPORTED_MODE", "Pilihan mode potong tidak dikenal.", 400)

    fmt = deteksi_format(data, nama)
    if not fmt or fmt not in ALLOWED_FORMATS:
        raise VideoTrimError(
            "UNSUPPORTED_FORMAT",
            "Format video belum didukung. Gunakan MP4, MOV, WebM, atau MKV.",
            400,
        )

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

        probe_info = probe(data, fmt)
        if not probe_info.get("ada_video"):
            raise VideoTrimError(
                "NO_VIDEO_STREAM",
                "Berkas ini tidak punya gambar video, jadi tidak bisa dipotong.",
                400,
            )

        durasi_masukan = float(probe_info.get("durasi", 0.0) or 0.0)
        if durasi_masukan > MAX_DURATION_SECONDS:
            raise VideoTrimError(
                "VIDEO_TOO_LONG",
                f"Durasi berkas video melebihi batas {MAX_DURATION_SECONDS // 60} menit.",
                400,
            )

        t_mulai = parse_waktu(mulai, "Waktu mulai")
        t_akhir = parse_waktu(akhir, "Waktu selesai")

        if t_akhir <= t_mulai:
            raise VideoTrimError(
                "INVALID_RANGE",
                "Waktu selesai harus lebih besar dari waktu mulai.",
                400,
            )

        durasi_klip = t_akhir - t_mulai
        if durasi_klip < MIN_CLIP_SECONDS:
            raise VideoTrimError(
                "CLIP_TOO_SHORT",
                f"Potongan video terlalu pendek. Minimal {MIN_CLIP_SECONDS} detik.",
                400,
            )
        if durasi_klip > MAX_CLIP_SECONDS:
            raise VideoTrimError(
                "CLIP_TOO_LONG",
                f"Potongan video terlalu panjang. Maksimal {MAX_CLIP_SECONDS} detik.",
                400,
            )

        out_name = nama_keluaran(mode_clean, fmt)
        out_ext = out_name.split(".")[-1]
        out_mime = "video/webm" if out_ext == "webm" else "video/mp4"

        with tempfile.NamedTemporaryFile(delete=False, suffix="." + out_ext, dir="/tmp") as out_tf:
            out_tmp_path = out_tf.name
            try:
                os.chmod(out_tmp_path, 0o600)
            except OSError:
                pass

        ss_str = f"{t_mulai:.3f}".rstrip("0").rstrip(".")
        t_str = f"{durasi_klip:.3f}".rstrip("0").rstrip(".")

        if mode_clean == "cepat":
            cmd = [
                FFMPEG,
                "-nostdin",
                "-hide_banner",
                "-loglevel", "error",
                "-ss", ss_str,
                "-i", in_tmp_path,
                "-t", t_str,
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
            ]
            if out_ext == "mp4":
                cmd.extend(["-movflags", "+faststart"])
            cmd.extend(["-y", out_tmp_path])
        else:
            cmd = [
                FFMPEG,
                "-nostdin",
                "-hide_banner",
                "-loglevel", "error",
                "-ss", ss_str,
                "-i", in_tmp_path,
                "-t", t_str,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-vf", "scale='min(1280,iw)':-2",
            ]
            if probe_info.get("ada_audio"):
                cmd.extend(["-c:a", "aac", "-b:a", "128k"])
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
            raise VideoTrimError(
                "TRIM_TIMEOUT",
                "Prosesnya lebih lama dari batas waktu. Coba bagian yang lebih pendek atau mode potong cepat.",
                504,
            )
        except FileNotFoundError:
            raise VideoTrimError("TRIM_FAILED", "Alat ffmpeg tidak ditemukan di server.", 500)

        if proc.returncode != 0:
            logger.warning("ffmpeg trim gagal: code=%s", proc.returncode)
            raise VideoTrimError(
                "TRIM_FAILED",
                "Bagian video ini tidak bisa dipotong. Coba geser titik potongnya sedikit.",
                422,
            )

        if not os.path.exists(out_tmp_path) or os.path.getsize(out_tmp_path) == 0:
            logger.warning("ffmpeg keluaran kosong atau tidak terbentuk")
            raise VideoTrimError(
                "TRIM_FAILED",
                "Bagian video ini tidak bisa dipotong. Coba geser titik potongnya sedikit.",
                422,
            )

        out_size = os.path.getsize(out_tmp_path)
        if out_size > MAX_OUTPUT_BYTES:
            raise VideoTrimError(
                "OUTPUT_TOO_LARGE",
                f"Ukuran hasil potongan ({out_size // (1024 * 1024)} MB) melebihi batas {MAX_OUTPUT_BYTES // (1024 * 1024)} MB.",
                413,
            )

        with open(out_tmp_path, "rb") as f:
            out_bytes = f.read()

        resolusi = None
        lebar = probe_info.get("lebar")
        tinggi = probe_info.get("tinggi")
        if lebar and tinggi:
            resolusi = f"{lebar}x{tinggi}"

        clip_seconds = round(durasi_klip, 2)
        if mode_clean == "cepat":
            # Mode cepat memakai -c copy tanpa menulis ulang gambar, jadi titik
            # potong menempel ke titik kunci terdekat dan durasi nyata berkas
            # hasil bisa lebih panjang dari yang diminta. Laporkan durasi nyata
            # itu supaya "durasi hasil" yang ditampilkan ke pengguna tidak menyesatkan.
            durasi_nyata = durasi_berkas(out_tmp_path)
            if durasi_nyata is not None and MIN_CLIP_SECONDS <= durasi_nyata <= MAX_CLIP_SECONDS:
                clip_seconds = round(durasi_nyata, 2)

        return TrimResult(
            data=out_bytes,
            output_name=out_name,
            mime_type=out_mime,
            clip_seconds=clip_seconds,
            mode=mode_clean,
            durasi_masukan=durasi_masukan,
            resolusi=resolusi,
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
