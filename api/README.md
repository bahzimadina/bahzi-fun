# OmniTools API — Merge PDF

API Python (FastAPI + uvicorn + pypdf) yang menggerakkan alat **Merge PDF** di
[bahzi.fun](https://bahzi.fun). Front-end statis memanggil API ini; semua
pemrosesan terjadi **di memori** server — tidak ada berkas yang ditulis ke disk.

Versi saat ini: `1.0.0` (`api/app/__init__.py` → `__version__`).

---

## Struktur

```
api/
├── app/
│   ├── __init__.py        # penanda paket + __version__
│   ├── main.py            # aplikasi FastAPI: endpoint, error handler, logging
│   ├── pdf_merge.py       # logika merge (fungsi murni, tanpa HTTP)
│   └── healthcheck.py     # health check container (dipakai HEALTHCHECK)
├── test_api.py            # uji otomatis (jalan tanpa pytest juga)
├── requirements.txt       # fastapi, uvicorn[standard], pypdf, python-multipart
├── Dockerfile             # image produksi: python:3.12-slim, non-root, uvicorn
├── docker-compose.yml     # compose khusus API (container omnitools-api, network webnet)
└── README.md
```

Catatan: `docker-compose.yml` untuk API **sengaja terpisah** dari compose di root
proyek (root = compose situs statis `bahzi-landing`).

---

## Menjalankan lokal

```bash
cd api
python3 -m venv /tmp/venv-api
/tmp/venv-api/bin/pip install -r requirements.txt
cd api && /tmp/venv-api/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8077
```

Atau langsung dengan Python sistem (bila fastapi/uvicorn/pypdf sudah ada):

```bash
cd api && python3 -m uvicorn app.main:app --port 8077
```

Dokumentasi interaktif: `http://127.0.0.1:8077/docs`

### Menjalankan uji otomatis

```bash
cd api && python3 test_api.py                     # skrip mandiri (tanpa pytest)
OMNITOOLS_API_URL=http://127.0.0.1:8077 python3 test_api.py   # + uji ke server hidup
cd api && python3 -m pytest test_api.py -v        # bila pytest tersedia
```

---

## Endpoint

### 1. `GET /health`

```json
{"status": "ok", "service": "omnitools-api", "version": "1.0.0"}
```

Dipakai health check container / gateway.

### 2. `POST /api/pdf/merge`

`multipart/form-data`, field bernama **`files`** diulang untuk setiap berkas.
**Urutan field = urutan halaman pada hasil.**

Contoh:

```bash
curl -s -o /tmp/hasil.pdf -w '%{http_code} %{size_download}\n' \
  -F 'files=@/tmp/a.pdf' -F 'files=@/tmp/b.pdf' \
  http://127.0.0.1:8077/api/pdf/merge
```

Respons sukses: `200`, `Content-Type: application/pdf`,
`Content-Disposition: attachment; filename="gabungan.pdf"`, plus header bantu:

| Header               | Isi                                             |
|----------------------|-------------------------------------------------|
| `Cache-Control`      | `no-store, no-cache, must-revalidate`           |
| `X-File-Count`       | jumlah berkas yang digabung                     |
| `X-Page-Count`       | jumlah halaman hasil                            |
| `X-Total-Bytes`      | ukuran PDF hasil (byte)                         |
| `X-Processing-Ms`    | durasi pemrosesan di server                     |
| `X-Pdf-Passthrough`  | `true` bila hanya 1 berkas (tidak ditulis ulang) |

### 3. `GET /api/pdf/merge/limits`

```json
{
  "max_files": 10,
  "max_total_bytes": 26214400,
  "max_total_mb": 25,
  "max_pages": 200,
  "accept": "application/pdf",
  "result_filename": "gabungan.pdf",
  "processed_on": "server",
  "note": "Berkas dikirim ke server ini, digabung di memori, lalu dibuang setelah respons dikirim. Tidak ada berkas yang disimpan di disk."
}
```

Dipakai front-end untuk menampilkan aturan ke pengguna (jangan hard-code di FE).

---

## Aturan & validasi

| Aturan                          | Nilai                                       |
|---------------------------------|---------------------------------------------|
| Jumlah berkas                   | maksimum **10**                             |
| Ukuran total                    | maksimum **25 MB** (semua berkas digabung)  |
| Jumlah halaman total            | maksimum **200**                            |
| Jenis berkas                    | hanya PDF asli (magic bytes `%PDF-`)        |

* **PDF asli diperiksa lewat magic bytes**, bukan ekstensi atau MIME. Berkas
  `.txt` yang dinamai `.pdf` ditolak `400 NOT_PDF`.
* **Satu berkas**: setelah divalidasi (magic bytes, halaman ≤ 200), berkas
  dikembalikan **apa adanya — byte-identik**, jadi tidak ada penulisan ulang
  yang tidak perlu (tidak kehilangan metadata/form). Header
  `X-Pdf-Passthrough: true` menandai kasus ini.
* **Di memori**: pembacaan unggahan memakai `UploadFile.read()` bertahap dengan
  batas 25 MB; penggabungan memakai `pypdf` + `io.BytesIO`. Tidak ada `open()`
  tulis ke disk, tidak ada berkas sementara.
* **Logging**: hanya metadata (jumlah berkas, total byte, jumlah halaman,
  durasi ms) — **nama berkas dan isi berkas tidak pernah dicatat**.

### Format error

```json
{"error": {"code": "TOO_MANY_FILES", "message": "Maksimum 10 berkas per penggabungan, dikirim 11 berkas."}}
```

| Status | `code`                                  | Kapan                                        |
|--------|-----------------------------------------|----------------------------------------------|
| 400    | `NO_FILES`                              | tidak ada field `files` / kosong             |
| 400    | `TOO_MANY_FILES`                        | lebih dari 10 berkas                         |
| 400    | `NOT_PDF`                               | magic bytes `%PDF-` tidak ditemukan          |
| 400    | `EMPTY_FILE`                            | salah satu berkas 0 byte                     |
| 400    | `INVALID_REQUEST`                       | body bukan multipart/form-data yang sah      |
| 413    | `PAYLOAD_TOO_LARGE`                     | ukuran total > 25 MB                         |
| 413    | `TOO_MANY_PAGES`                        | total halaman > 200                          |
| 422    | `PDF_UNREADABLE`                        | PDF rusak / struktur halaman tidak terbaca   |
| 422    | `PDF_ENCRYPTED`                         | PDF terproteksi kata sandi                   |
| 500    | `INTERNAL_ERROR`                        | kesalahan tak terduga di server              |

---

## Deploy (urusan operator)

```bash
cd /home/ubuntu/bahzi-fun-landing/api
docker compose up -d --build     # container: omnitools-api, network webnet
```

* **Tanpa publish port** — container hanya bisa dijangkau dari network `webnet`,
  jadi harus diakses lewat web-gateway (by Host) atau reverse proxy.
* Network `webnet` bersifat **external** (sama seperti container `bahzi-landing`).
* Front-end memanggil path relatif `/api/...` (same-origin). Agar
  `https://bahzi.fun/api/pdf/merge` sampai ke container ini, gateway/nginx harus
  mem-proxy `location /api/` ke `http://omnitools-api:8000`. Bila API diletakkan
  di hostname lain (mis. `api.bahzi.fun`), cukup isi
  `<meta name="omnitools-api-base" content="https://api.bahzi.fun">` di
  `index.html` — front-end akan memakai itu sebagai awalan.

### Variabel lingkungan

| Variabel                    | Default        | Fungsi                                                     |
|-----------------------------|----------------|------------------------------------------------------------|
| `LOG_LEVEL`                 | `INFO`         | level log uvicorn/aplikasi                                  |
| `OMNITOOLS_CORS_ORIGINS`    | *(kosong/mati)*| daftar origin dipisah koma bila FE dilayani dari origin lain |
| `HEALTHCHECK_URL`           | `http://127.0.0.1:8000/health` | target health check container             |

---

## Yang belum diuji

* Unggah lewat browser sungguhan (end-to-end dari UI ke API) — perlu container
  API jalan + routing gateway. Uji yang sudah dilakukan: endpoint lewat curl,
  TestClient FastAPI, dan uji ke server uvicorn lokal (lihat LOG tugas).
* Build image Docker (belum di-build; instruksi ada di `Dockerfile`).
