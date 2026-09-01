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

Secara default pipeline mengikuti `EMBEDDING_PROVIDER`. Untuk development offline gunakan `hash`; untuk mode industri gunakan BGE-M3 lokal:

```bash
.venv\Scripts\python -m app.services.ingestion.cli --document-id PP-35-2021 --embedding-provider bge_m3
```

OpenAI embeddings tetap tersedia sebagai opsi eksplisit:

```bash
.venv\Scripts\python -m app.services.ingestion.cli --document-id PP-35-2021 --embedding-provider openai
```

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
7. Generate dense dan sparse embedding BGE-M3 untuk setiap chunk.
8. Simpan artifact JSON dan log ingestion.
9. Opsional: persist dokumen, versi, chunk, embedding, dan ingestion job ke PostgreSQL.
10. Candidate yang sudah direview dimasukkan ke namespace Pinecone baru hanya
    melalui immutable release builder; ingestion tidak dapat menulis langsung ke
    namespace aktif.

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

Release-candidate ingestion must run in the Linux worker image and pass the runtime preflight:

```bash
python -m app.services.ingestion.preflight
```

Each build is fingerprinted from the source checksum plus parser, OCR, chunker, embedding model revision, and effective configuration. Artifacts are written to `documents/{document_id}/v{version}/builds/{build_id}` and are never overwritten by a changed pipeline. Use `--release-candidate --persist-db` for candidate builds; native dense and sparse BGE-M3 vectors are mandatory.

A successful automated quality report does not approve the build. An administrator must review every unresolved page and approve the immutable build through `POST /admin/ingestion/builds/{build_id}/review`. Source verification and substantive legal review remain separate gates. Only approved builds can be attached to an index release.

The production worker uses Celery concurrency `1` so one BGE-M3 model process owns CPU memory. OCRmyPDF may use at most two OCR subprocesses inside that task. Checkpoint JSONL files make embedding resumable after worker restarts.
Canary order:

```bash
python -m app.services.ingestion.cli --document-id PP-36-2021 --document-id PP-35-2021 --document-id UU-6-2023 --embedding-provider bge_m3 --release-candidate --persist-db
```

Only after all three canaries pass and their problematic pages are reviewed, run all 19 sources with `--all`. Promotion remains blocked until canonical source verification, substantive legal review, build approval, and the release evaluation gates are complete.
