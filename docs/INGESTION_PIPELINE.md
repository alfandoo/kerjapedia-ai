# Ingestion Pipeline

Pipeline ingestion mengubah PDF regulasi dari `dataset/` menjadi artifact terstruktur yang siap dipakai retrieval.

## Command

Jalankan dari folder `apps/api`:

```bash
.venv\Scripts\python -m app.services.ingestion.cli --document-id PP-35-2021
```

Untuk memproses seluruh dokumen:

```bash
.venv\Scripts\python -m app.services.ingestion.cli --all
```

Pipeline ingestion selalu memakai provider lokal `hash` (artifact development).
Embedding produksi di-hosting Upstash: indexing membaca pre-embedding
`chunks.jsonl` via `scripts/index_upstash.py` dan Upstash meng-embedding
server-side. Tidak ada opsi embedding lain.

Untuk menyimpan hasil ke PostgreSQL, pastikan `docker compose up -d` sudah berjalan dan migration sudah diterapkan, lalu gunakan:

```bash
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m app.services.ingestion.cli --document-id PP-35-2021 --persist-db
```

## Tahapan

1. Validasi file PDF: extension, header `%PDF-`, ukuran file, checksum SHA-256, dan duplicate checksum.
2. Salin raw PDF ke artifact storage lokal.
3. Ekstrak teks per halaman dengan PyMuPDF.
4. Jalankan OCRmyPDF/Tesseract bahasa Indonesia dan Inggris jika text-quality
   score rendah. Score menilai panjang, karakter terbaca, proporsi alfanumerik,
   dan replacement glyph. Halaman yang tetap berkualitas rendah membuat job
   berstatus `review_required`.
5. Normalisasi heading hukum/OCR umum, lalu parse struktur `BAB`, `Bagian`,
   `Pasal`, `Ayat`, dan halaman. Referensi pasal di dalam kalimat tidak dianggap
   sebagai heading baru.
6. Chunk per unit hukum menggunakan target 250–450 token, maksimum 550 token,
   overlap maksimum 60 token tanpa melintasi Pasal, serta simpan parent Pasal.
7. Buat artifact embedding hash lokal untuk setiap chunk (development/baseline).
8. Simpan artifact JSON dan log ingestion.
9. Opsional: persist dokumen, versi, chunk, embedding, dan ingestion job ke PostgreSQL.
10. Index produksi dibangun dari `chunks.jsonl` via `scripts/index_upstash.py`;
    ingestion tidak menulis langsung ke namespace aktif.

## Artifact Output

Default output berada di `storage/ingestion/`:

```text
storage/ingestion/
  documents/{document_id}/v{version}/raw/source.pdf
  documents/{document_id}/v{version}/metadata/document.json
  documents/{document_id}/v{version}/metadata/validation.json
  documents/{document_id}/v{version}/interim/extracted_text.json
  documents/{document_id}/v{version}/processed/segments.json
  documents/{document_id}/v{version}/processed/chunks.json
  documents/{document_id}/v{version}/processed/embeddings.json
  logs/{document_id}-v{version}.json
```

`storage/` di-ignore oleh Git karena berisi artifact hasil proses lokal.

## OCR Fallback

Jika halaman PDF hampir tidak memiliki teks, pipeline menjalankan OCRmyPDF
dengan Tesseract `ind+eng`. Dokumen tidak di-upsert ke vector store selama masih
`review_required`; admin harus memeriksa hasil OCR dan menjalankan ingestion
ulang sebelum source verification dan legal review.

## Immutable release-candidate builds

Each build is fingerprinted from the source checksum plus parser, OCR, chunker, embedding model revision, and effective configuration. Artifacts are written to `documents/{document_id}/v{version}/builds/{build_id}` and are never overwritten by a changed pipeline. Use `--persist-db` for builds whose metadata must land in PostgreSQL.

A successful automated quality report does not approve the build. An administrator must review every unresolved page and approve the immutable build through `POST /admin/ingestion/builds/{build_id}/review`. Source verification and substantive legal review remain separate gates.

The production worker uses Celery concurrency `1`. OCRmyPDF may use at most two OCR subprocesses inside that task. Checkpoint JSONL files make embedding resumable after worker restarts.
Canary order:

```bash
python -m app.services.ingestion.cli --document-id PP-36-2021 --document-id PP-35-2021 --document-id UU-6-2023 --persist-db
```

Only after all three canaries pass and their problematic pages are reviewed, run all 19 sources with `--all`. Indexing ke Upstash (`scripts/index_upstash.py --dry-run` dulu, lalu full) dilakukan setelah chunks tervalidasi.
