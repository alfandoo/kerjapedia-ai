# High-Assurance RAG Pipeline

Production KerjaPedia AI bersifat fail-closed. Mode `artifact`, embedding `hash`,
generator `local`, reranker heuristik, dan sumber unpublished hanya tersedia untuk
development/test. Contoh konfigurasi lengkap ada di `.env.production.example`.

## Source governance

Database adalah sumber kebenaran untuk versi dokumen, verifikasi sumber, review hukum,
publication status, serta relasi hukum. Migrasi status lama hanya mengisi
`source_verification_status`; dokumen tetap membutuhkan review hukum manusia dan bukti
HTTPS sebelum dapat dipublikasikan.

Retrieval umum hanya menerima versi yang:

- `is_current=true`, yang hanya berubah atomik saat release tervalidasi dipromosikan;
- `publication_status=published`;
- `ingestion_status=completed` (OCR/review gate lulus);
- source dan legal review berstatus `verified`; dan
- legal status `active` atau `amended`.

Versi lama hanya tersedia dalam immutable release untuk pertanyaan historis eksplisit.
Perubahan registry yang membuat snapshot aktif stale menyebabkan readiness dan chat
production gagal tertutup sampai release baru dipromosikan.

## Ingestion dan publication

Ingestion job menggunakan ID deterministik dari document ID dan checksum. Celery/Redis
memberikan retry durable dan mencegah job checksum yang sama diproses ulang. Pipeline:

1. memvalidasi PDF dan checksum;
2. menjalankan OCRmyPDF/Tesseract `ind+eng` untuk halaman minim teks;
3. menandai hasil OCR berkualitas rendah sebagai `review_required`;
4. parse Bab/Pasal/Ayat dan membentuk child chunk 250–450 token (maksimum 550,
   overlap maksimum 60, tidak lintas Pasal);
5. menyimpan parent context maksimum 1.200 token, halaman, offset, checksum, dan versi;
6. mengekspor pre-embedding chunks (`chunks.jsonl`, sumber kebenaran untuk indexing); dan
7. menyimpan artifact tanpa menulis namespace aktif.

Indexing ke Upstash dilakukan terpisah via `scripts/index_upstash.py`, yang
mengirim raw chunk text (Upstash meng-embedding server-side:
`open-ai/text-embedding-3-small` + BM25). Indexing bersifat idempoten
(chunk ID deterministik) dan mendukung `--dry-run`/`--limit`.

Startup production gagal tertutup ketika index Upstash tidak cocok dengan
kontrak hosted-embedding (HYBRID/BM25/COSINE) atau masih kosong.

## Retrieval

Index Upstash HYBRID (dense hosted + sparse BM25, metric COSINE). Aplikasi
mengirim raw query text; Upstash melakukan dense/sparse embedding
server-side dengan maksimum 100 kandidat per rewrite. Filter eksplisit
menjadi hard filter; topik hasil inferensi hanya memengaruhi ranking.

Heuristic reranker internal menilai kandidat. Setelah itu policy relasi
hukum, deduplikasi/diversity, dan context expansion memilih konteks akhir.
Threshold refusal berasal dari konfigurasi governance.

## Generation dan verification

Memory menyimpan pertanyaan asli, bahasa pertanyaan, retrieval query kontekstual, topik,
document ID, dan citation hints sebagai nilai terpisah. Hard filter Pasal/nomor/tahun
selalu diekstrak dari pertanyaan saat ini; konteks lama hanya menjadi soft ranking signal.
Hanya turn yang selesai, terjawab, dan memiliki citation valid yang eligible, serta turn
kedua hanya dipakai jika koheren dengan topik atau dokumen terbaru. Generator selalu
menerima pertanyaan asli.
Groq mengembalikan JSON terstruktur berisi jawaban, cited chunk IDs, dan klaim.

Setiap klaim diverifikasi dengan call verifier terpisah. Klaim tidak didukung atau bahasa
output salah memicu satu regenerasi. Kegagalan generator, reranker, verifier, atau index
production menghasilkan error `rag_temporarily_unavailable`; fallback lokal tidak
digunakan. Streaming hanya mengirim isi jawaban setelah verification selesai.

## Operasional

- `/health` adalah liveness tanpa panggilan dependency; `/ready` memeriksa DB,
  Upstash (verifikasi kontrak index), Supabase, dan Redis.
- `/metrics` mengekspor latency tahap, provider error, outcome, token usage, claim
  verification, retrieved document version, prompt/answer version, dan index release.
- OTLP spans dapat dikirim melalui `OTEL_EXPORTER_OTLP_ENDPOINT`.
- Trace server menyimpan hash query, versi pipeline, chunk/version, hasil verification,
  dan token usage tanpa prompt lengkap. Celery Beat menghapus trace setelah
  `RAG_TRACE_RETENTION_DAYS`.
