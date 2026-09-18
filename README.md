# KerjaPedia AI

KerjaPedia AI adalah asisten regulasi ketenagakerjaan Indonesia berbasis Retrieval-Augmented Generation (RAG). Produk ini membantu pengguna mencari, memahami, dan memverifikasi jawaban berdasarkan dokumen resmi yang tersimpan di `dataset/`.

## Status Project

Project sudah memiliki MVP RAG lokal dan jalur RAG industri berbasis provider:

- Mode lokal/offline: artifact ingestion + hash embedding + answer composer deterministik.
- Mode industri (aktif): Upstash Vector hybrid index + hosted embedding + Groq chat completions.

Dokumen produk utama tersedia di `docs/PRD_KerjaPedia_AI.md`, roadmap pengerjaan tersedia di `docs/project/ROADMAP.md`, dan arsitektur RAG provider tersedia di `docs/RAG_PIPELINE.md`.

## Stack Awal

- Frontend: Next.js
- Backend API: Python FastAPI
- Database: PostgreSQL
- Vector store: Upstash Vector untuk mode industri, artifact lokal untuk development/test
- Embedding: hosted oleh Upstash (open-ai/text-embedding-3-small + BM25) untuk mode industri; hash embedding untuk development/test
- LLM provider: Groq untuk mode industri, local answer composer untuk development/test

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

- Redis: `localhost:6379`

PostgreSQL berjalan via Supabase (`DATABASE_URL`) dan object storage via
Supabase Storage — tidak ada service postgres/MinIO lokal lagi. Lihat
`compose.production.yaml` untuk stack penuh.

Untuk mode industri, isi minimal variabel berikut di `.env`:

```bash
VECTOR_STORE=upstash_vector
UPSTASH_VECTOR_REST_URL=...
UPSTASH_VECTOR_REST_TOKEN=...
UPSTASH_VECTOR_NAMESPACE=production
LLM_PROVIDER=groq
GROQ_API_KEY=...
GROQ_MODEL=openai/gpt-oss-120b
```

### Upstash Vector Setup

Index dibuat di Upstash Console dengan konfigurasi:

- Index Type: `HYBRID`
- Dense Embedding: `open-ai/text-embedding-3-small`
- Sparse Embedding: `BM25`
- Similarity Metric: `COSINE`

Document embedding dan query embedding dilakukan oleh Upstash. Aplikasi
mengirim raw chunk text saat indexing (`scripts/index_upstash.py`) dan raw
query text saat retrieval — tidak diperlukan lagi self-hosted dense
embedding (BGE-M3), embedding di Google Colab, manual query embedding, atau
GPU untuk dense embedding. Reranker, context construction, generation, dan
evaluasi tidak berubah.

```bash
copy .env.example .env
```

Lalu isi `UPSTASH_VECTOR_REST_URL` dan `UPSTASH_VECTOR_REST_TOKEN` dari
Upstash Console. Nama legacy `UPSTASH_VECTOR_URL` / `UPSTASH_VECTOR_TOKEN`
tetap diterima.

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
.venv\Scripts\python -m pip install -r requirements-dev.txt
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

Untuk production, ingestion menghasilkan artifact (chunks + registry version).
Index Upstash dibangun dari pre-embedding chunks via `scripts/index_upstash.py`;
job ingestion tidak pernah menulis langsung ke namespace aktif.

```bash
cd apps/api
.venv\Scripts\python -m app.services.ingestion.cli --all --persist-db
```

Artifact ingestion tetap disimpan di `storage/ingestion/`. Lihat `docs/INGESTION_PIPELINE.md` untuk detail pipeline dan opsi `--persist-db`.

### Retrieval Lokal

```bash
cd apps/api
.venv\Scripts\python -m app.services.retrieval.cli "Apakah pekerja PKWT memperoleh kompensasi?"
```

Retrieval lokal membaca artifact di `storage/ingestion/`. Lihat `docs/RETRIEVAL.md` untuk detail scoring dan ranking.

Retrieval Upstash (hybrid, hosted embedding):

```bash
cd apps/api
.venv\Scripts\python -m app.services.retrieval.cli "Apakah pekerja PKWT memperoleh kompensasi?" --vector-store upstash_vector
```

### Indexing Upstash

Indexing membaca pre-embedding chunks yang sudah ada
(`storage/ingestion/preembedding/exports/chunks.jsonl`) — tanpa parsing
PDF ulang dan tanpa embedding lokal:

```bash
apps\api\.venv\Scripts\python scripts\index_upstash.py --dry-run
apps\api\.venv\Scripts\python scripts\index_upstash.py --limit 100
apps\api\.venv\Scripts\python scripts\index_upstash.py
```

Sanity test retrieval:

```bash
apps\api\.venv\Scripts\python scripts\test_upstash_retrieval.py "Siapa yang berhak memperoleh THR?"
```

### Answer Generation Lokal

```bash
cd apps/api
.venv\Scripts\python -m app.services.answering.cli "Apakah pekerja PKWT memperoleh kompensasi?"
```

Answer generation lokal membuat response terstruktur berisi `answer`, `citations`, `confidence`, `related_documents`, `refusal_reason`, dan disclaimer. Lihat `docs/ANSWER_GENERATION.md` untuk detail prompt, citation, dan guardrail.

Answer generation Groq:

```bash
cd apps/api
.venv\Scripts\python -m app.services.answering.cli "Apakah pekerja PKWT memperoleh kompensasi?" --vector-store upstash_vector --llm-provider groq
```

Groq memakai endpoint yang kompatibel OpenAI (`openai/gpt-oss-120b`) dengan
latensi jauh lebih rendah daripada routing gratis OpenRouter. Buat API key di
`https://console.groq.com/keys`, lalu isi `.env`:

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=...
GROQ_MODEL=openai/gpt-oss-120b
```

`CLAIM_VERIFIER_PROVIDER` dapat diisi `groq` (verifikasi LLM di Groq) atau
`deterministic` (verifikasi lokal instan tanpa API call).

### Evaluasi RAG

```bash
cd apps/api
.venv\Scripts\python -m app.services.evaluation.cli --dataset ../../evaluation/golden_questions.json --storage-root ../../storage/ingestion --output ../../storage/evaluation/report.json --top-k 10
```

Evaluasi CLI membandingkan mode development pada 150 pertanyaan seed. Promotion release
membutuhkan minimal 300 pertanyaan human-verified dengan development/held-out split dan
evaluation run yang terikat ke namespace release. Lihat `docs/EVALUATION.md`.

### Evaluasi Baseline vs Upstash (fair experiment)

Dataset evaluasi (`evaluation/golden_questions.json`) tidak diubah. Yang
berubah hanya backend embedding/index/retrieval; dokumen, chunking,
metadata, reranker, dan context construction dipertahankan sama:

| Metric | Baseline historis | Upstash Hybrid |
|---|---|---|
| Recall@5 | ... | ... |
| Precision@5 | ... | ... |
| Hit Rate | ... | ... |
| MRR | ... | ... |
| nDCG@10 | ... | ... |

1. Jalankan evaluasi artifact/baseline dengan command evaluasi di atas.
2. Index chunks ke Upstash (`scripts/index_upstash.py`), lalu uji retrieval
   (`scripts/test_upstash_retrieval.py` dan retrieval CLI
   `--vector-store upstash_vector`).
3. Bandingkan per tipe query: semantic, exact keyword (nomor peraturan /
   pasal), Bahasa Indonesia vs Inggris, short vs long query — untuk melihat
   kontribusi dense (`text-embedding-3-small`) vs sparse (BM25).

### Pre-commit

```bash
apps\api\.venv\Scripts\python -m pre_commit install
apps\api\.venv\Scripts\python -m pre_commit run --all-files
```

### Backup Metadata PostgreSQL

Setelah service PostgreSQL Docker aktif, buat backup sekaligus uji restore ke database
sementara:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\backup_postgres.ps1 -VerifyRestore
```

Lihat `docs/SECURITY.md` untuk konfigurasi production, retry ingestion, retention, dan
prosedur backup.

### Deployment Production

Salin `.env.production.example` menjadi `.env.production`, isi seluruh credential dan
URL HTTPS, lalu jalankan:

```powershell
docker compose -f compose.production.yaml --env-file .env.production up -d --build
python scripts/smoke_deployment.py --api-url https://api.example.com --web-url https://app.example.com
```

Panduan container, migration, GHCR, smoke test, dan rollback tersedia di
`docs/DEPLOYMENT.md`.

## Catatan Hukum

KerjaPedia AI bukan pengganti advokat, konsultan hukum, mediator hubungan industrial, atau instansi pemerintah. Jawaban harus selalu berbasis sumber resmi dan menyertakan citation yang dapat diverifikasi.
