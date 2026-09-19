# OmniTools API — Merge PDF (FastAPI + pypdf)
# Image produksi: python:3.12-slim, jalan sebagai user non-root, tanpa curl di dalam.
# Tidak mempublikasikan port: diakses web-gateway lewat network eksternal `webnet`.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /srv

RUN apt-get update && apt-get install -y --no-install-recommends libcairo2 && rm -rf /var/lib/apt/lists/*

# Dependensi lebih dulu supaya layer cache tidak batal saat kode berubah.
COPY requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /srv/requirements.txt

COPY app/ /srv/app/

# Jalankan sebagai user non-root.
RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --home-dir /srv --shell /usr/sbin/nologin app \
    && chown -R app:app /srv
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "/srv/app/healthcheck.py"]

# Satu worker cukup: pemrosesan murni CPU/IO ringan dan proses di memori.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
