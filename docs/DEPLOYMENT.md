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
