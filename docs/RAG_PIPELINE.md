# Industrial RAG Pipeline

KerjaPedia AI mendukung dua mode RAG:

- `artifact`: mode lokal/offline untuk development dan test deterministik.
- `pinecone`: mode industri memakai Pinecone, embedding BGE-M3 lokal, dan Groq untuk answer generation.

## Provider Configuration

Variabel utama:

```bash
VECTOR_STORE=pinecone
PINECONE_API_KEY=
PINECONE_INDEX_NAME=kerjapedia-regulations
PINECONE_NAMESPACE=production
PINECONE_CLOUD=aws
PINECONE_REGION=us-east-1

EMBEDDING_PROVIDER=bge_m3
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSION=1024

LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
GROQ_TIMEOUT_SECONDS=30
GROQ_MAX_RETRIES=2
GROQ_MAX_TOKENS=1200
```

`artifact`, `hash`, dan `local` tetap tersedia untuk development:

```bash
VECTOR_STORE=artifact
EMBEDDING_PROVIDER=hash
LLM_PROVIDER=local
```

## Ingestion Flow

Pipeline membaca metadata dari `dataset/metadata.json`, memvalidasi PDF, mengekstrak teks, parse struktur hukum, chunking, membuat embedding, menulis artifact JSON, lalu opsional mengirim vector ke Pinecone.

Command full dataset:

```powershell
cd apps/api
.venv\Scripts\python -m app.services.ingestion.cli --all --vector-store pinecone --embedding-provider bge_m3
```

Pinecone index dibuat otomatis bila belum ada, dengan dense cosine index berdimensi `1024`. Upsert memakai `chunk_id` sebagai ID sehingga proses bisa diulang secara idempotent.

Metadata Pinecone dibuat flat dan memuat field penting untuk filter dan citation: `document_id`, `version`, `title`, `short_title`, `topics`, `regulation_type`, `year`, `article`, `paragraph`, `page_start`, `page_end`, `legal_status`, `source_url`, dan `text`.

## Retrieval Flow

Mode Pinecone:

1. Query understanding mendeteksi topik, intent, rewrite, dan filter.
   Query terkait waktu juga diperluas dengan frasa hukum seperti `paling lambat`
   dan `wajib dibayarkan`.
2. Query di-embed dengan provider yang sama dengan ingestion.
3. Pinecone mengembalikan minimal 100 kandidat semantic berdasarkan vector dan
   metadata filter agar lexical reranker tetap dapat mengangkat frasa hukum persis.
4. Kandidat dikonversi ke kontrak `RetrievalDocument`.
5. Existing reranker menghitung lexical, semantic, fusion, final score, warning status hukum, dan refusal threshold.
6. Query di luar domain ketenagakerjaan ditolak dengan
   `refusal_reason=out_of_scope_query` sebelum embedding atau pemanggilan Groq.

Command:

```powershell
cd apps/api
.venv\Scripts\python -m app.services.retrieval.cli "Apakah pekerja PKWT memperoleh kompensasi?" --vector-store pinecone
```

## Answer Generation Flow

Mode Groq mempertahankan guardrail lokal:

1. Pertanyaan terlalu umum tetap meminta klarifikasi sebelum memanggil LLM.
2. Retrieval kosong, lemah, atau di luar scope tetap refusal sebelum memanggil LLM.
3. Prompt sistem dan konteks retrieval dikirim ke Groq.
4. Model wajib mengembalikan JSON berisi `answer`, `confidence`, dan `cited_chunk_ids`.
5. Service memvalidasi citation agar hanya chunk yang benar-benar retrieved yang boleh dipakai.
6. Jika JSON invalid, timeout, atau citation salah, service memakai citation-safe fallback lokal.

Command:

```powershell
cd apps/api
.venv\Scripts\python -m app.services.answering.cli "Apakah pekerja PKWT memperoleh kompensasi?" --vector-store pinecone --llm-provider groq
```

## Health and Verification

`GET /health` menampilkan provider aktif, model embedding, model Groq, index Pinecone, namespace, dan status readiness Pinecone tanpa menampilkan secret.

Verifikasi lokal:

```powershell
cd apps/api
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check app tests --no-cache
```

Smoke test dengan credential nyata:

1. Isi `PINECONE_API_KEY` dan `GROQ_API_KEY`.
2. Jalankan ingestion seluruh dataset ke Pinecone.
3. Jalankan retrieval CLI untuk topik PKWT, PHK, THR, BPJS, K3, dan serikat pekerja.
4. Jalankan answer CLI dengan Groq.
5. Jalankan evaluation dan pastikan Recall@5 memenuhi target di `docs/EVALUATION.md`.
