# Task Roadmap KerjaPedia AI

Dokumen ini berisi tahapan kerja dari awal sampai akhir untuk membangun KerjaPedia AI: asisten regulasi ketenagakerjaan Indonesia berbasis Retrieval-Augmented Generation (RAG).

## 1. Persiapan Awal Project

**Status:** Selesai.

- [x] Finalisasi ruang lingkup MVP berdasarkan `docs/PRD_KerjaPedia_AI.md`.
- [x] Tentukan stack utama:
  - Frontend: Next.js.
  - Backend API: Python FastAPI.
  - Database: PostgreSQL (via Supabase).
  - Vector store: Upstash Vector (HYBRID; sebelumnya pgvector, lalu Pinecone+BGE-M3 — keduanya pensiun 2026-09).
  - LLM provider: Groq (sebelumnya OpenAI/OpenRouter).
- [x] Inisialisasi Git repository jika belum ada.
- [x] Buat struktur folder awal:
  - `apps/web/` untuk frontend.
  - `apps/api/` untuk backend.
  - `packages/` untuk shared utilities.
  - `scripts/` untuk ingestion dan evaluasi.
  - `docs/` untuk dokumentasi.
  - `dataset/` untuk dokumen hukum sumber.
- [x] Tambahkan file konfigurasi dasar seperti `.env.example`, `.gitignore`, dan `README.md`.

## 1.5. Setup Dependencies

**Status:** Selesai.

- [x] Inisialisasi project frontend di `apps/web/`.
- [x] Install dependencies frontend:
  - Next.js.
  - React.
  - TypeScript.
  - Tailwind CSS.
- [x] Inisialisasi project backend di `apps/api/`.
- [x] Install dependencies backend:
  - FastAPI.
  - Uvicorn.
  - Pydantic.
  - PostgreSQL client.
  - Library parsing PDF.
  - OpenAI SDK.
- [x] Buat file konfigurasi dependency seperti `package.json`, `requirements.txt`, atau `pyproject.toml`.
- [x] Tambahkan command development ke `README.md`.
- [x] Jalankan verifikasi awal:
  - Frontend dev server bisa berjalan.
  - Backend health check bisa berjalan.
  - Dependency lock file dibuat jika stack mendukung.

## 1.6. Local Infrastructure & Developer Tooling

**Status:** Selesai.

- [x] Siapkan Docker Compose untuk local development.
- [x] Tambahkan service lokal:
  - PostgreSQL dengan pgvector.
  - Redis untuk queue dan cache.
  - MinIO atau storage lokal untuk file PDF dan artifact parsing.
- [x] Tambahkan konfigurasi migration database.
- [x] Tambahkan formatter dan linter:
  - Frontend: ESLint dan Prettier.
  - Backend: Ruff.
- [x] Tambahkan pre-commit hook jika diperlukan.
- [x] Tambahkan GitHub Actions atau CI dasar untuk lint dan test.
- [x] Dokumentasikan command local infrastructure di `README.md`.

## 2. Audit dan Penataan Dataset

**Status:** Selesai.

Catatan: audit awal selesai untuk kebutuhan MVP. Status hukum final dan detail URL dokumen resmi masih ditandai `needs_verification` di `dataset/metadata.json` agar tidak dipakai sebagai klaim final sebelum diverifikasi admin.

- [x] Inventarisasi semua PDF di `dataset/` berdasarkan topik, nomor regulasi, tahun, dan status.
- [x] Tambahkan metadata untuk setiap dokumen:
  - Judul peraturan.
  - Nomor dan tahun.
  - Jenis regulasi.
  - Topik.
  - Status berlaku, diubah, atau dicabut.
  - URL sumber resmi.
- [x] Buat file metadata awal, misalnya `dataset/metadata.json` atau tabel database.
- [x] Validasi sumber dokumen dari situs resmi seperti Database Peraturan BPK.
- [x] Tandai relasi antarregulasi, misalnya peraturan yang mengubah atau mencabut regulasi sebelumnya.

## 3. Desain Arsitektur Sistem

**Status:** Selesai.

Dokumen arsitektur tersedia di `docs/ARCHITECTURE.md`.

- [x] Buat diagram alur sistem:
  - Upload atau import PDF.
  - Parsing dokumen.
  - Chunking.
  - Embedding.
  - Indexing.
  - Retrieval.
  - Reranking.
  - Answer generation.
  - Citation display.
- [x] Tentukan skema database untuk dokumen, chunk, metadata, citation, user feedback, dan log query.
- [x] Tentukan arsitektur authentication dan role:
  - Guest.
  - User.
  - Admin.
- [x] Tentukan arsitektur asynchronous job untuk ingestion.
- [x] Tentukan penggunaan object storage untuk raw PDF, OCR output, parsing artifact, dan export evaluasi.
- [x] Tentukan format standar citation:
  - Judul peraturan.
  - Pasal dan ayat.
  - Nomor halaman.
  - Kutipan pendukung.
  - Link sumber.
- [x] Tentukan strategi prompt versioning dan audit log.
- [x] Tentukan strategi refusal ketika konteks tidak cukup.

## 4. Pipeline Ingestion Dokumen

**Status:** Selesai.

Pipeline tersedia melalui `python -m app.services.ingestion.cli` dari `apps/api`. Artifact lokal disimpan di `storage/ingestion/` dan dokumentasi tersedia di `docs/INGESTION_PIPELINE.md`.

Catatan: OCRmyPDF/Tesseract `ind+eng` dijalankan untuk halaman minim teks. Halaman yang tetap berkualitas rendah sesudah OCR berstatus `review_required` dan tidak dapat dipublikasikan.

- [x] Buat script ekstraksi teks PDF.
- [x] Tambahkan validasi file:
  - MIME type.
  - Ukuran file.
  - Checksum.
  - Duplicate detection.
- [x] Simpan hasil ekstraksi mentah untuk debugging.
- [x] Siapkan struktur artifact:
  - Raw PDF.
  - Interim text.
  - Processed chunks.
  - Metadata.
  - Logs.
- [x] Implementasikan parser struktur hukum:
  - BAB.
  - Bagian.
  - Pasal.
  - Ayat.
  - Halaman.
- [x] Tambahkan OCR fallback untuk PDF scan.
- [x] Implementasikan document versioning berdasarkan checksum dan tanggal update.
- [x] Buat strategi chunking yang menjaga konteks pasal dan ayat tetap utuh.
- [x] Generate embedding untuk setiap chunk.
- [x] Simpan chunk, embedding, dan metadata ke database atau vector store.
- [x] Tambahkan log ingestion untuk dokumen berhasil, gagal, dan perlu review manual.

## 5. Retrieval dan Ranking

**Status:** Selesai.

Retrieval baseline tersedia melalui `python -m app.services.retrieval.cli` dari `apps/api`. Dokumentasi tersedia di `docs/RETRIEVAL.md`.

Catatan: semantic search saat ini memakai embedding lokal deterministic dari artifact ingestion. Ini cukup untuk development/offline; kualitas semantic production perlu diganti ke embedding model sungguhan saat API key dan evaluasi RAG siap.

- [x] Implementasikan query understanding:
  - Deteksi topik.
  - Deteksi intent.
  - Normalisasi singkatan hukum.
  - Query rewriting.
- [x] Implementasikan keyword search untuk istilah hukum spesifik.
- [x] Implementasikan semantic search menggunakan embedding.
- [x] Gabungkan keduanya menjadi hybrid retrieval.
- [x] Tambahkan metadata filtering berdasarkan jenis peraturan, nomor, tahun, topik, status, dan pasal.
- [x] Implementasikan fusion ranking seperti Reciprocal Rank Fusion.
- [x] Tambahkan reranker untuk memilih chunk paling relevan.
- [x] Tambahkan threshold untuk refusal ketika skor retrieval rendah.
- [x] Tambahkan context expansion untuk mengambil pasal terkait bila diperlukan.
- [x] Prioritaskan regulasi terbaru dan masih berlaku.
- [x] Tampilkan peringatan ketika sumber historis atau belum terverifikasi digunakan.
- [x] Pastikan retrieval menampilkan minimal:
  - Query pengguna.
  - Dokumen kandidat.
  - Chunk terpilih.
  - Score retrieval.
  - Metadata hukum.

## 6. Answer Generation dan Citation

**Status:** Selesai.

Answer generation baseline tersedia melalui `python -m app.services.answering.cli`
dari `apps/api`. Dokumentasi tersedia di `docs/ANSWER_GENERATION.md`.

Catatan: generator saat ini offline-first dan menyusun jawaban dari chunk retrieval.
Prompt berversi sudah tersedia untuk integrasi LLM pada tahap backend/chat berikutnya.

- [x] Buat prompt sistem yang mewajibkan jawaban berbasis konteks.
- [x] Buat prompt template dengan versioning.
- [x] Tambahkan instruksi untuk tidak menjawab jika sumber tidak cukup.
- [x] Tambahkan mekanisme clarification untuk pertanyaan ambigu.
- [x] Format jawaban agar mudah dipahami pekerja, HR, UMKM, dan mahasiswa.
- [x] Tampilkan citation pada setiap klaim hukum penting.
- [x] Tambahkan disclaimer bahwa KerjaPedia AI bukan pengganti advokat, konsultan hukum, mediator, atau instansi pemerintah.
- [x] Buat output terstruktur untuk frontend, misalnya:
  - `answer`
  - `citations`
  - `confidence`
  - `related_documents`
  - `refusal_reason`

## 7. Backend API

**Status:** Selesai.

Baseline API tersedia di `apps/api/app/api/` dan dokumentasi endpoint ada di
`docs/API.md`. OpenAPI otomatis tersedia melalui `/docs` dan `/openapi.json`.

Catatan: auth, conversation history, feedback, ingestion jobs, dan evaluation runs
masih memakai in-memory store untuk MVP awal. Persistensi database production akan
dikerjakan pada tahap hardening.

- [x] Buat endpoint health check.
- [x] Buat endpoint authentication:
  - Login.
  - Logout.
  - Current user.
- [x] Buat endpoint chat atau ask-question.
- [x] Buat endpoint conversation history.
- [x] Buat endpoint detail dokumen dan citation.
- [x] Buat endpoint document management untuk admin.
- [x] Buat endpoint ingestion jobs.
- [x] Buat endpoint evaluation dataset dan evaluation run.
- [x] Buat endpoint feedback pengguna.
- [x] Tambahkan validasi input dan rate limiting dasar.
- [x] Tambahkan logging untuk latency, token usage, retrieval score, dan error.
- [x] Buat dokumentasi API berbasis OpenAPI.

## 8. Frontend Web Application

**Status:** Selesai.

- [x] Buat halaman utama berbentuk aplikasi chat, bukan landing page saja.
- [x] Tambahkan input pertanyaan bahasa alami.
- [x] Tambahkan streaming response dan tombol stop generation.
- [x] Tambahkan riwayat percakapan.
- [x] Tampilkan jawaban, citation, kutipan sumber, dan link dokumen.
- [x] Tambahkan panel sumber agar pengguna dapat memeriksa pasal dan halaman.
- [x] Tambahkan halaman search regulasi.
- [x] Tambahkan halaman detail regulasi dan source viewer.
- [x] Tambahkan halaman login dan session state.
- [x] Tambahkan state loading, empty, error, dan refusal.
- [x] Tambahkan feedback sederhana: membantu atau tidak membantu.
- [x] Tambahkan halaman legal:
  - Disclaimer.
  - Kebijakan privasi.
  - Ketentuan penggunaan.
- [x] Pastikan tampilan responsif untuk desktop dan mobile.
- [x] Pastikan aksesibilitas dasar:
  - Keyboard navigation.
  - Focus state.
  - Label form.
  - Kontras teks.

## 9. Dashboard Admin Knowledge Base

**Status:** Selesai.

- [x] Buat halaman daftar dokumen.
- [x] Buat halaman upload dokumen PDF.
- [x] Tampilkan status ingestion setiap dokumen.
- [x] Tampilkan metadata regulasi dan relasi perubahan.
- [x] Tambahkan metadata editor.
- [x] Tambahkan relationship editor.
- [x] Tambahkan fitur re-ingest dokumen.
- [x] Tambahkan fitur publish, unpublish, dan version history dokumen.
- [x] Tambahkan log error parsing dan dokumen yang perlu review manual.
- [x] Tambahkan halaman user feedback.
- [x] Tambahkan retrieval playground untuk debugging.
- [x] Batasi akses admin dengan autentikasi.

## 10. Evaluasi RAG

**Status:** Selesai untuk implementasi. Benchmark produksi tetap menunggu ingestion corpus lengkap dan verifikasi hukum manusia atas dataset seed.

- [x] Buat evaluation dataset berisi pertanyaan, jawaban ideal, dan sumber benar.
- [x] Targetkan minimal 150 pertanyaan evaluasi sesuai PRD.
- [x] Tambahkan test untuk:
  - Retrieval Recall@5.
  - Mean Reciprocal Rank.
  - Citation correctness.
  - Faithfulness.
  - Refusal accuracy.
- [x] Tambahkan hard negative questions untuk istilah yang mirip tetapi berbeda konteks.
- [x] Tambahkan experiment comparison antara baseline, dense, hybrid, dan rerank.
- [x] Buat regression test agar perubahan pipeline tidak merusak kualitas jawaban.
- [x] Bandingkan hasil berdasarkan topik seperti PKWT, PHK, THR, BPJS, dan K3.

## 11. Testing Aplikasi

**Status:** Selesai. Acceptance latency lokal memenuhi target PRD; load test staging dengan provider LLM nyata tetap menjadi quality gate deployment.

- [x] Tambahkan unit test untuk parser, chunker, metadata, dan formatter citation.
- [x] Tambahkan integration test untuk endpoint backend.
- [x] Tambahkan end-to-end test untuk alur tanya jawab di frontend.
- [x] Uji pertanyaan yang jawabannya ada di dokumen.
- [x] Uji pertanyaan yang tidak memiliki dasar dokumen dan harus ditolak.
- [x] Uji performa median response time sesuai target PRD.

## 12. Security, Privacy, dan Reliability

**Status:** Selesai untuk implementasi. Verifikasi restore backup pada service PostgreSQL
lokal tetap perlu dijalankan ketika Docker CLI tersedia.

- [x] Simpan API key hanya di environment variable.
- [x] Jangan commit file `.env`, log sensitif, atau vector index lokal.
- [x] Tambahkan secure password hashing atau session/token strategy.
- [x] Tambahkan validasi upload PDF dan batas ukuran file.
- [x] Tambahkan mitigasi prompt injection dari isi dokumen.
- [x] Tambahkan timeout untuk request LLM dan database.
- [x] Tambahkan retry untuk job ingestion yang gagal.
- [x] Tambahkan backup metadata database.
- [x] Tambahkan error handling jika retrieval kosong atau LLM gagal.
- [x] Tambahkan monitoring dasar untuk error rate dan latency.
- [x] Tambahkan tracing untuk prompt version, model version, retrieved chunks, dan token usage.
- [x] Tentukan retention policy untuk riwayat chat dan feedback.
- [x] Pastikan jawaban hukum selalu menyertakan sumber atau refusal.

## 13. Deployment MVP

**Status:** Siap deploy. Container, migration gate, CI image publishing, konfigurasi
production, dan smoke test sudah tersedia. Deployment cloud aktual menunggu pemilihan
provider, domain, dan akses akun.

- [ ] Pilih target deployment:
  - Frontend: Vercel, Netlify, atau server sendiri.
  - Backend: Railway, Render, Fly.io, VPS, atau cloud provider.
  - Database/vector store: managed PostgreSQL, Supabase, Qdrant Cloud, atau alternatif lain.
- [x] Siapkan environment production.
- [x] Siapkan Dockerfile frontend dan backend.
- [x] Siapkan Docker Compose production atau deployment manifest.
- [x] Siapkan CI/CD pipeline.
- [ ] Jalankan migration database.
- [x] Jalankan ingestion dataset awal.
- [ ] Deploy frontend dan backend.
- [ ] Uji smoke test production:
  - Chat berhasil.
  - Citation tampil.
  - Dokumen sumber dapat dibuka.
  - Feedback tersimpan.
  - Error log berjalan.

## 14. Dokumentasi Akhir

- [ ] Perbarui `README.md` dengan cara instalasi, konfigurasi, dan menjalankan project.
- [ ] Buat `SRS.md` untuk software requirements.
- [ ] Buat `TRD.md` untuk technical requirements.
- [ ] Buat `ERD.md` untuk desain database.
- [ ] Buat `API_SPEC.md`.
- [ ] Buat `RAG_PIPELINE.md`.
- [ ] Buat `EVALUATION_PLAN.md`.
- [ ] Buat `DATASET_DOCUMENTATION.md`.
- [ ] Buat `SECURITY.md`.
- [ ] Buat `DEPLOYMENT.md`.
- [ ] Dokumentasikan pipeline ingestion.
- [ ] Dokumentasikan format metadata regulasi.
- [ ] Dokumentasikan cara menambah dokumen baru.
- [ ] Dokumentasikan cara menjalankan evaluasi.
- [ ] Tambahkan catatan batasan produk dan disclaimer hukum.

## 15. Maintenance dan Iterasi Lanjutan

- [ ] Jadwalkan review regulasi baru atau perubahan regulasi.
- [ ] Tambahkan topik hukum ketenagakerjaan baru setelah MVP stabil.
- [ ] Analisis feedback pengguna untuk memperbaiki retrieval dan prompt.
- [ ] Optimalkan biaya token dan latency.
- [ ] Tambahkan fitur perbandingan regulasi lama dan baru.
- [ ] Tambahkan export jawaban atau ringkasan sumber jika diperlukan.

## Definition of Done MVP

- [ ] Pengguna dapat bertanya dalam bahasa alami.
- [ ] Sistem menjawab berdasarkan dokumen resmi di `dataset/`.
- [ ] Setiap jawaban hukum memiliki citation yang dapat diverifikasi.
- [ ] Sistem menolak menjawab ketika konteks tidak cukup.
- [ ] Admin dapat memantau dokumen dan status ingestion.
- [ ] Evaluasi RAG dasar berjalan dan memenuhi target minimum PRD.
- [ ] Aplikasi dapat diakses di environment production.
