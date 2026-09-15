# bahzi.fun

Landing page untuk **OmniTools** — konsep perkakas online yang (rencananya) berjalan sepenuhnya di dalam browser.

**Live:** https://bahzi.fun

## Tujuan

Halaman ini adalah **etalase konsep**: memperkenalkan gagasan OmniTools secara ringkas dan membuat daftar alatnya mudah ditelusuri. Semua pengolahan data dirancang terjadi di perangkat pengguna — berkas tidak dikirim ke server.

> **Status: demo.** Produk OmniTools belum ada. Halaman ini hanya tampilan konsep; label status pada kartu alat adalah penanda visual, bukan alat yang bisa dipakai.

## Fitur

- **Daftar alat sebagai fokus utama** — tanpa hero/banner; halaman langsung menampilkan daftar alat.
- **Toolbar sticky** — pencarian alat, filter kategori, filter status, tombol reset, dan penghitung hasil yang selalu mengikuti pencarian/filter.
- **Tema gelap** dengan palet ungu (referensi visual dari gaya situs sentry.io).
- **Responsif** dari layar ponsel sampai desktop.
- **Aksesibilitas** — navigasi keyboard, fokus terlihat, `aria-label`, skip-link, dan dukungan `prefers-reduced-motion`.
- **Tanpa dependency** — satu HTML, satu CSS, satu JavaScript vanilla. Tanpa framework, tanpa build step, tanpa CDN, tanpa analytics; font dilayani dari berkas lokal.
- **Siap deploy** sebagai gambar Docker (nginx) dengan penomoran versi aset otomatis agar cache tidak menyajikan berkas lama.

## Menjalankan lokal

```bash
git clone https://github.com/bahzimadina/bahzi-fun.git
cd bahzi-fun
python3 -m http.server 8000
# buka http://127.0.0.1:8000/
```

Halaman juga tetap tampil bila `index.html` dibuka langsung lewat `file://`.

## Menjalankan dengan Docker

```bash
docker compose up -d --build
```

Container tidak mem-publish port; di produksi diakses lewat reverse proxy berbasis Host header. Untuk uji cepat, tambahkan sementara mapping port pada `docker-compose.yml`.

## Struktur

```
index.html            Halaman (navbar, daftar alat, dan bagian pendukung).
assets/styles.css     Gaya tampilan (tema gelap, responsif, font lokal).
assets/app.js         Data alat, render daftar, pencarian, filter, penghitung.
assets/fonts/         Berkas font lokal.
Dockerfile            Gambar nginx + penomoran versi aset.
docker-compose.yml    Menjalankan container.
```

## Catatan

- Demo ini tidak memiliki backend, API, database, autentikasi, form nyata, maupun service worker.
- Referensi gaya visual diambil dari situs sentry.io; proyek ini tidak berafiliasi dengan Sentry.
