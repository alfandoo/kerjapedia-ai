# KerjaPedia AI

KerjaPedia AI membantu pengguna mencari dan memahami peraturan ketenagakerjaan Indonesia melalui retrieval dokumen dan jawaban bersitasi. Aplikasi ini bukan pengganti nasihat hukum.

[Aplikasi web](https://kerjapedia-ai.vercel.app) · [Dokumentasi API](docs/API.md) · [Panduan pengujian](docs/TESTING.md)

## Fitur

- Chat dengan mode cepat dan mendalam, riwayat, ringkasan konteks percakapan panjang, dan pembatalan request.
- Sitasi dokumen, pasal, ayat, dan halaman; verifikasi klaim serta penolakan saat sumber tidak memadai.
- Chat tamu yang dapat diklaim setelah login, autentikasi pengguna, dan mode personal berdasarkan profil kerja.
- Pencarian dokumen, kalkulator, tinjauan CV, halaman kepatuhan, serta dashboard admin.
- Observability chat per mode dan antarmuka bahasa Indonesia serta Inggris.

## Struktur dan layanan

| Lokasi | Isi |
| --- | --- |
| `apps/web/` | Next.js 16, React 19, proxy API, tes unit/integrasi, Playwright |
| `apps/api/` | FastAPI, Alembic, RAG, autentikasi, worker Celery |
| `dataset/` | Dokumen peraturan dan metadata sumber |
| `evaluation/` | Evaluasi retrieval dan jawaban |
| `docs/` | PRD dan dokumentasi teknis |
| `scripts/` | Alat bantu pengembangan dan tes |

PostgreSQL menyimpan data relasional; Supabase Storage menyimpan berkas; Upstash Vector menyimpan indeks retrieval; Redis mendukung cache, antrean, dan rate limit. Provider LLM produksi adalah Groq atau OpenRouter. Lihat [arsitektur](docs/ARCHITECTURE.md).

## Menjalankan lokal

Gunakan Node.js 22, Python 3.12, dan PostgreSQL yang dapat diakses melalui `DATABASE_URL`. Perintah ini memakai PowerShell dari akar repo.

1. Salin `.env.example` ke `.env` dan isi `DATABASE_URL` serta kredensial layanan yang dipakai. Jangan commit `.env`.
2. Jika memakai Redis lokal, jalankan `docker compose up -d redis`. `compose.yaml` hanya menyediakan Redis; siapkan PostgreSQL pengembangan secara terpisah.
3. Siapkan API dan migrasikan database:

   ```powershell
   cd apps/api
   python -m venv .venv
   .\.venv\Scripts\python -m pip install -r requirements-dev.txt
   .\.venv\Scripts\python -m alembic upgrade head
   .\.venv\Scripts\python -m alembic current
   .\.venv\Scripts\python -m uvicorn app.main:app --reload
   ```

4. Di terminal lain, jalankan web:

   ```powershell
   cd apps/web
   npm ci
   npm run dev
   ```

Web tersedia di `http://localhost:3000`, dokumentasi API di `http://127.0.0.1:8000/docs`, dan kesiapan API di `http://127.0.0.1:8000/ready`. Web memilih alamat backend dari `API_INTERNAL_URL`, lalu `NEXT_PUBLIC_API_URL`, lalu `http://127.0.0.1:8000`.

Jika startup API melaporkan `Database schema is out of date`, jalankan `python -m alembic upgrade head` dari `apps/api` memakai `DATABASE_URL` yang sama dengan proses API. Verifikasi dengan `python -m alembic current`.

Lihat [`.env.example`](.env.example) untuk konfigurasi dan [panduan deployment](docs/DEPLOYMENT.md) untuk produksi. `compose.production.yaml` menyediakan stack mandiri dengan PostgreSQL, Redis, API, worker, scheduler, dan web.

## Pengujian

CI menjalankan job `Web` dan `API` pada push ke `main` dan pull request. Jalankan pemeriksaan lokal berikut:

```powershell
# Dari akar repo: PostgreSQL uji sementara, migrasi, dan pytest
.\scripts\test_api.ps1

# Dari apps/api
.\.venv\Scripts\python -m ruff check app tests

# Dari apps/web
npm run lint
npm run build
npm run test:unit
npx playwright install chromium
npm run test:integration
npm run test:e2e
```

Script API memerlukan Docker dan memakai database uji terpisah pada port `5433`. CI juga memeriksa migrasi naik dan turun. Lihat [panduan pengujian](docs/TESTING.md).

## Dokumentasi

- [PRD](docs/PRD_KerjaPedia_AI.md)
- [Arsitektur](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Ingestion](docs/INGESTION_PIPELINE.md)
- [Evaluasi](docs/EVALUATION.md)
- [Deployment](docs/DEPLOYMENT.md)

Periksa peraturan yang dikutip sebelum memakai jawaban untuk keputusan hukum atau hubungan industrial.
