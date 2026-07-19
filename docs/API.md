# Backend API

Task 7 menyediakan baseline FastAPI untuk MVP KerjaPedia AI. Dokumentasi OpenAPI
otomatis tersedia saat server berjalan di `/docs` dan `/openapi.json`.

## Menjalankan Lokal

```bash
cd apps/api
.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Endpoint Utama

- `GET /health`: status service.
- `POST /auth/login`: login development. Email yang diawali `admin@` mendapat role
  `admin`.
- `POST /auth/logout`: revoke token development.
- `GET /auth/me`: user saat ini berdasarkan bearer token.
- `POST /chat/ask`: menjalankan retrieval dan answer generation.
- `GET /chat/conversations`: daftar conversation milik user/guest.
- `GET /chat/conversations/{conversation_id}`: detail conversation.
- `GET /documents`: daftar regulasi dari `dataset/metadata.json`.
- `GET /documents/{document_id}`: detail dokumen dan chunk yang sudah tersedia.
- `GET /documents/{document_id}/citations/{chunk_id}`: detail citation chunk.
- `PATCH /documents/{document_id}`: validasi update metadata admin.
- `POST /ingestion/jobs`: jalankan ingestion sinkron untuk admin.
- `GET /ingestion/jobs`: daftar ingestion job.
- `POST /evaluation/datasets`: buat dataset evaluasi admin.
- `POST /evaluation/runs`: jalankan evaluasi retrieval sederhana.
- `POST /feedback`: simpan feedback pengguna.

## Guardrail dan Observability

Request body divalidasi dengan Pydantic. Middleware menambahkan rate limit dasar per IP
dan header `X-Request-Latency-Ms`. Endpoint chat mengembalikan `retrieval_score` dan
`token_usage`; token usage masih `0` sampai integrasi LLM aktif.

## Catatan Implementasi

Auth, conversation history, feedback, ingestion job, dan evaluation run masih memakai
in-memory store untuk MVP awal. Data akan hilang ketika proses API restart. Persistensi
database dan session production perlu dikerjakan pada tahap hardening berikutnya.
