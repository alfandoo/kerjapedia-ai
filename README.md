# KerjaPedia AI

KerjaPedia AI adalah asisten regulasi ketenagakerjaan Indonesia berbasis Retrieval-Augmented Generation (RAG). Produk ini membantu pengguna mencari, memahami, dan memverifikasi jawaban berdasarkan dokumen resmi yang tersimpan di `dataset/`.

## Status Project

Project berada pada tahap persiapan awal. Dokumen produk utama tersedia di `docs/PRD_KerjaPedia_AI.md`, dan roadmap pengerjaan tersedia di `task.md`.

## Stack Awal

- Frontend: Next.js
- Backend API: Python FastAPI
- Database: PostgreSQL
- Vector store: pgvector
- LLM provider: OpenAI

## Struktur Folder

- `apps/web/` untuk aplikasi frontend.
- `apps/api/` untuk backend API.
- `packages/` untuk utilitas bersama.
- `scripts/` untuk ingestion, indexing, dan evaluasi.
- `docs/` untuk dokumentasi produk dan teknis.
- `dataset/` untuk dokumen regulasi sumber.

## Menjalankan Project

### Local Infrastructure

Copy environment contoh bila ingin menjalankan service lokal:

```bash
copy .env.example .env
docker compose up -d
```

Service lokal:

- PostgreSQL + pgvector: `localhost:5432`
- Redis: `localhost:6379`
- MinIO API: `http://localhost:9000`
- MinIO Console: `http://localhost:9001`

Matikan service lokal:

```bash
docker compose down
```

### Frontend

```bash
cd apps/web
npm install
npm run dev
```

Frontend berjalan di `http://localhost:3000`.

### Backend

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend health check tersedia di `http://127.0.0.1:8000/health`.
OpenAPI tersedia di `http://127.0.0.1:8000/docs`. Lihat `docs/API.md` untuk daftar endpoint MVP.

Jalankan migration database:

```bash
cd apps/api
.venv\Scripts\python -m alembic upgrade head
```

### Verifikasi Awal

```bash
cd apps/web
npm run lint
npm run format:check
npm run build

cd ../api
.venv\Scripts\python -m ruff check app tests
.venv\Scripts\python -m pytest
```

Jalankan end-to-end test frontend:

```bash
cd apps/web
npx playwright install chromium
npm run test:e2e
```

Lihat `docs/TESTING.md` untuk cakupan unit, integration, E2E, refusal, dan target latency.

### Ingestion Dataset

```bash
cd apps/api
.venv\Scripts\python -m app.services.ingestion.cli --document-id PP-35-2021
```

Artifact ingestion disimpan di `storage/ingestion/`. Lihat `docs/INGESTION_PIPELINE.md` untuk detail pipeline dan opsi `--persist-db`.

### Retrieval Lokal

```bash
cd apps/api
.venv\Scripts\python -m app.services.retrieval.cli "Apakah pekerja PKWT memperoleh kompensasi?"
```

Retrieval lokal membaca artifact di `storage/ingestion/`. Lihat `docs/RETRIEVAL.md` untuk detail scoring dan ranking.

### Answer Generation Lokal

```bash
cd apps/api
.venv\Scripts\python -m app.services.answering.cli "Apakah pekerja PKWT memperoleh kompensasi?"
```

Answer generation lokal membuat response terstruktur berisi `answer`, `citations`, `confidence`, `related_documents`, `refusal_reason`, dan disclaimer. Lihat `docs/ANSWER_GENERATION.md` untuk detail prompt, citation, dan guardrail.

### Evaluasi RAG

```bash
cd apps/api
.venv\Scripts\python -m app.services.evaluation.cli --dataset ../../evaluation/golden_questions.json --storage-root ../../storage/ingestion --output ../../storage/evaluation/report.json --top-k 5
```

Evaluasi membandingkan mode baseline, dense, hybrid, dan rerank pada 150 pertanyaan seed. Dataset masih memerlukan verifikasi hukum manusia sebelum dipakai sebagai klaim kualitas produksi. Lihat `docs/EVALUATION.md` untuk metrik dan quality gate.

### Pre-commit

```bash
apps\api\.venv\Scripts\python -m pre_commit install
apps\api\.venv\Scripts\python -m pre_commit run --all-files
```

## Catatan Hukum

KerjaPedia AI bukan pengganti advokat, konsultan hukum, mediator hubungan industrial, atau instansi pemerintah. Jawaban harus selalu berbasis sumber resmi dan menyertakan citation yang dapat diverifikasi.
