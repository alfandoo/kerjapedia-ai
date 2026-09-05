# Deployment MVP

## Target Reference

Deployment reference menggunakan container OCI:

- Next.js web pada port `3000`.
- FastAPI pada port `8000`.
- PostgreSQL 16 + pgvector sebagai metadata database.
- Pinecone dan Groq sebagai managed provider.

Image dapat dijalankan di Railway, Render, Fly.io, VPS, Kubernetes, atau platform lain
yang menerima Docker image. Workflow GitHub Actions membangun image pada pull request
dan menerbitkannya ke GHCR pada branch `main` atau tag `v*`.

## Persiapan

1. Salin `.env.production.example` menjadi `.env.production`.
2. Ganti seluruh credential placeholder.
3. Set `PUBLIC_API_URL` ke URL HTTPS backend.
4. Set `CORS_ORIGINS` ke URL HTTPS frontend.
5. Pastikan `DATABASE_URL` memakai password yang sama dengan `POSTGRES_PASSWORD`.

Konfigurasi production akan menolak password admin default, credential provider kosong,
dan origin localhost.

## Menjalankan Container

```powershell
docker compose -f compose.production.yaml --env-file .env.production build
docker compose -f compose.production.yaml --env-file .env.production up -d
docker compose -f compose.production.yaml --env-file .env.production ps
```

Service `migrate` menjalankan Alembic setelah PostgreSQL sehat. API baru berjalan setelah
migration berhasil, dan web menunggu API sehat.

## Smoke Test

```powershell
python scripts/smoke_deployment.py `
  --api-url https://api.example.com `
  --web-url https://app.example.com
```

Smoke test memastikan `/health` mengembalikan status `ok` dan frontend mengembalikan
halaman HTML.

## Deployment Provider

Untuk managed deployment, buat tiga service:

1. `web` dari `apps/web/Dockerfile`.
2. `api` dari `apps/api/Dockerfile`.
3. PostgreSQL managed atau service dari `compose.production.yaml`.

Jalankan `python -m alembic upgrade head` sebagai release command backend. Mount object
storage persisten ke `/workspace/storage` bila fitur upload admin digunakan. Dataset
harus tersedia read-only di `/workspace/dataset`, atau endpoint admin yang bergantung
pada manifest harus dinonaktifkan sampai dataset tersedia.

## Rollback

Gunakan image bertag commit SHA dari GHCR. Rollback aplikasi dilakukan dengan mengganti
tag image ke SHA sebelumnya. Migration database harus backward-compatible; lakukan
backup dan restore-verification sebelum migration yang mengubah atau menghapus data.

## Belum Dilakukan

Deployment cloud aktual, konfigurasi DNS/TLS, dan smoke test URL production menunggu
pemilihan provider serta akses akun deployment.

## Trusted proxy dan rate limit

Entrypoint API container (`python -m app.server`) mengabaikan header forwarding secara
default. `FORWARDED_ALLOW_IPS` hanya diisi dengan IP atau CIDR proxy yang benar-benar
dikendalikan, dipisahkan koma. Wildcard `*` dan jaringan `/0` ditolak saat startup.
Contoh untuk proxy internal dengan IP tetap: `FORWARDED_ALLOW_IPS=172.30.0.10`.
Jangan menyalin IP contoh tanpa memeriksa alamat peer yang diterima container.

Compose production mengikat port API ke `127.0.0.1:8000` pada host. Pasang reverse
proxy HTTPS untuk `PUBLIC_API_URL`; proxy di host meneruskan ke port lokal ini,
atau proxy dalam jaringan Docker meneruskan ke `api:8000`. Pastikan firewall dan
jaringan membatasi akses langsung ke API. Proxy harus menimpa atau membersihkan
header forwarding dari klien, lalu mengisi alamat klien yang benar.

Pada platform managed, gunakan daftar alamat proxy resmi platform dan batasi
koneksi langsung ke backend. Jangan mempercayai semua IP untuk mengatasi alamat
proxy dinamis. Jika daftar belum diketahui, biarkan kosong; permintaan melalui
proxy akan berbagi batas berdasarkan IP proxy sampai trust dikonfigurasi.

Untuk menjalankan Uvicorn langsung saat development, gunakan `--no-proxy-headers`.
Pengaturan ini mengatasi spoofing IP; limiter saat ini masih berbasis memori per
proses dan belum menyatukan kuota antar-replica.

## Security headers frontend

Frontend memasang CSP dengan nonce acak per respons. `connect-src` production dibatasi ke origin frontend
karena semua request browser melewati BFF. Build production memblokir script inline
tanpa nonce dan `eval`; development mengizinkan `eval` dan WebSocket untuk HMR.
Style inline tetap diizinkan karena digunakan komponen UI. Halaman dirender dinamis
dan tidak boleh di-cache bersama oleh CDN agar nonce pada header dan HTML tetap cocok.
Header anti-iframe, nosniff, kebijakan referrer, permissions, dan HSTS production juga aktif.

## Sesi browser HttpOnly

Browser memakai `/api/backend/*` pada origin frontend. Next.js meneruskan request
ke `API_INTERNAL_URL` (Compose: `http://api:8000`); untuk development default-nya
`http://127.0.0.1:8000`. `APP_ORIGIN` harus sama persis dengan origin HTTPS frontend,
misalnya `https://app.example.com`, terutama bila web berada di belakang reverse proxy.
Backend tetap memverifikasi bearer dan role di server. Jangan mengekspos backend
langsung sebagai pengganti jalur BFF untuk sesi browser.

Access token dan refresh token hanya diterima route server lalu disimpan dalam
cookie host-only HttpOnly, SameSite=Lax, Path=/; production memakai Secure serta
prefix `__Host-`. Masa simpan cookie maksimum 30 hari; validitas token tetap ditentukan
Supabase. Browser hanya menerima profil pengguna dan menyimpannya di memori.
Token lama di localStorage/sessionStorage dihapus saat aplikasi dimuat: pengguna
perlu login ulang sekali setelah migrasi. Refresh dan logout tidak lagi menerima
token dari JavaScript browser. Jangan log header Cookie/Authorization di proxy.

Semua mutation BFF, termasuk login, wajib membawa Origin yang cocok dengan
`APP_ORIGIN` dan header `X-KerjaPedia-CSRF: 1`. Tidak ada CORS lintas origin di BFF.
Respons sesi tidak boleh di-cache. Pengujian lokal build production sebaiknya memakai
localhost yang didukung browser untuk cookie Secure; deployment nyata wajib HTTPS.
Token HttpOnly mencegah pembacaan token oleh JavaScript, tetapi bukan pengganti CSP
atau otorisasi: XSS yang berhasil tetap dapat bertindak lewat sesi korban.

Limiter backend saat ini menghitung IP koneksi BFF (kuota bersama untuk request
melalui proses proxy). Identitas IP klien dari header browser sengaja tidak diteruskan;
kuota per pengguna/guest atau edge limiter tepercaya tetap diperlukan untuk scaling.

## Endpoint operasional

`GET /health` tetap publik dan tanpa probe jaringan; respons hanya status dan nama
layanan. `GET /ready` tetap dapat dipakai Docker/orchestrator tanpa token, tetapi
hanya mengembalikan `ready` (200) atau `not_ready` (503), tanpa detail dependency.
Probe readiness dibagikan antar-request dengan cache 10 detik per proses; perubahan
kesiapan dapat memerlukan sampai 10 detik untuk terlihat.

Detail readiness, versi dan provider tersedia melalui `GET /admin/system/diagnostics`
dengan autentikasi admin (browser lewat BFF). `GET /metrics` backend juga memerlukan
bearer admin yang valid dan tidak diteruskan oleh BFF publik. Monitoring yang melakukan
scrape harus mengirim kredensial tersebut melalui jaringan internal; jangan menaruhnya
di URL atau membuka endpoint lewat pengecualian autentikasi reverse proxy.
