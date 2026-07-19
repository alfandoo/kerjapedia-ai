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

Secara default pipeline menggunakan embedding lokal deterministic `local-hash-embedding-v1` agar bisa berjalan offline. Untuk memakai OpenAI embeddings:

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
4. Tandai halaman yang membutuhkan OCR jika teks terlalu sedikit.
5. Parse struktur hukum: `BAB`, `Bagian`, `Pasal`, `Ayat`, dan halaman.
6. Chunk teks dengan konteks hukum tetap melekat.
7. Generate embedding untuk setiap chunk.
8. Simpan artifact JSON dan log ingestion.
9. Opsional: persist dokumen, versi, chunk, embedding, dan ingestion job ke PostgreSQL.

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

Jika halaman PDF hampir tidak memiliki teks, pipeline menandai halaman tersebut sebagai `requires_ocr` dan status job menjadi `review_required`. Engine OCR belum diaktifkan pada tahap ini; integrasi Tesseract atau OCR service masuk ke iterasi berikutnya bila dataset scan membutuhkan OCR.
