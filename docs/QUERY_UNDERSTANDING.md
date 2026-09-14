# Query: User Input → Retrieval Pipeline

Tahap ini mendefinisikan kontrak **pertanyaan pengguna** → **retrieval yang relevan** untuk Korupedia AI, tanpa mengubah pipeline ingestion, dataset, atau UI. Ini bukan dokumen UI (lihat `docs/PRD_KerjaPedia_AI.md` untuk user flow lengkap); ini hanya kontrak perilaku yang diverifikasi melalui pengujian.

## 1. Kontrak Pertanyaan (Tersirat dari PRD §3.1–3.5)

- Pertanyaan bisa pendek (2–5 kata) atau kompleks (2–4 paragraf); bahasa Indonesia atau Inggris terdeteksi otomatis (`generator._detect_language`).
- Pertanyaan di luar topik ketenagakerjaan harus ditolak (`retrieval.should_refuse`), bukan dijawab generik (`refusal_reason="out_of_scope_query"`).
- Konteks (`conversation_id`, pesan sebelumnya, artikel/topik/ID dokumen/pertanyaan) boleh diteruskan sebagai `context_*`; tapi **artikel konteks (`context_article`) tidak boleh menjadi filter keras** — artikel sering kali justru bagian dari jawaban, bukan navigasi. Ini diverifikasi melalui pengujian (`tests/test_retrieval.py`).

## 2. Ekstraksi Entitas dan Filter (Harus Verifikasi Deterministik)

Tahap ini mengekstrak sinyal eksplisit dari pertanyaan dan menetapkan filter server-side yang **narrow**, bukan spekulatif:

- `Pasal 15` (`article`) → filter keras: `article: {"$eq":"Pasal ..."}`
- `PP 35 Tahun 2021` (`regulation_type`, `number`, `year`) → filter keras: `regulation_type: {"$eq":"PP"}`, `number: {"$eq":35}`, `year: {"$eq":2021}`
- `PKWT` (`topics`) → sinyal lunak (`inferred_topics`), bukan filter keras
- `kompensasi` (`calculation`) → ekspansi sinonim (`uang kompensasi`), tapi **tidak** menambah filter `regulation_type=PP` kecuali pengguna menyebutkan eksplisit (`has_regulation`). Ini diverifikasi melalui pengujian (`tests/test_retrieval.py`, `tests/test_industrial_rag_providers.py`).
- `kapan batas waktu pembayaran THR?` (`timing`) → ekspansi timing (`paling lambat wajib dibayarkan sebelum batas waktu pembayaran`), tapi **tidak** filter `year` kecuali eksplisit; filter tahun tersirat yang berdiri sendiri (`"berlaku sejak 2019"`) dihapus (`understand_query`). Ini diverifikasi (`tests/test_retrieval.py`).
- Nama undang-undang umum (`"cipta kerja"` → UU 6/2023, `"undang-undang ketenagakerjaan"` → UU 13/2003) diterapkan hanya bila **tidak** ada kode eksplisit; kode eksplisit selalu menang (`tests/test_retrieval.py`).

## 3. Aturan Kontrak yang Diverifikasi Melalui Pengujian

- **Filter keras hanya dari eksplisit.** Konteks memori (`context_document_ids`, `context_articles`, `context_topics`) tidak boleh membuat filter keras otomatis (`tests/test_retrieval.py` — `test_contextual_retrieval_never_creates_hard_filters_from_memory`).
- **Inherensi regulasi dari memori bersifat bersyarat.** Saat pertanyaan lanjutan (`"dendanya bayar ke siapa?"`) tidak menyebut regulasi baru tapi `context_document_ids` berisi `PERMENAKER-6-2016`, maka `regulation_type`, `number`, `year` diwarisi sebagai filter keras — tapi `article` (`Pasal 5`) tidak diwarisi (`tests/test_retrieval.py` — `test_context_inheritance_stops_on_topic_switch_or_ambiguity`). Ini juga diverifikasi untuk ambiguitas (`PERMENAKER-6-2016` + `PP-35-2021` bersama) → tak diwarisi.
- **Artikel tidak diwarisi.** Artikel sering kali bagian jawaban (`Pasal 5` dalam pertanyaan `"Berapa besaran THR?"`), bukan sinyal navigasi — diwarisi akan over-filter (`tests/test_retrieval.py`).
- **Ekspansi sinonim (`kompensasi`) dan regulasi tersirat (`PP 35`) adalah sinyal lunak (`soft retrieval signal`)**, bukan filter keras. Filter keras hanya dari eksplisit (`tests/test_retrieval.py`).
- **Topik terdeteksi (`pkwt`, `phk`, `thr`) tetap sinyal lunak**, bukan filter keras (`tests/test_industrial_rag_providers.py` — `test_inferred_topic_is_a_soft_signal_not_a_hard_filter`).

## 4. Keterhubungan dengan Modul Lain (Tanpa Ubah Modul Ini)

- **Collection**: `metadata.json` → `topics` → sinyal lunak; `verification_status: verified` → filter `publication_status`/`legal_review_status` hanya saat `allow_unpublished=False`.
- **Chunking / Metadata**: `retrieval_text`, `topics_chunk` (verifikasi: `metadata.builder.verify_topics`), `embedding_model` (verifikasi: `embedding.verify_index_compatibility`), `effective_date` (filter `filters.build_filter`).
- **Retrieval**: `retrieval/query.py`, `retrieval/filtering.py`, `retrieval/postprocessing.py` (`diversify_ranked`), `retrieval/pinecone_store.py` (multi-query fusion + filter + rerank).
- **Citation / Answering**: `citation.build_citations` menggunakan `retrieval_text`; `claim_coverage_score` mengukur seberapa lengkap jawaban mencakup klaim hukum (`tests/test_answering.py` — `test_claim_coverage_detects_omitted_answer_claims`).
- **Validation**: `retrieval.store.py` + `retrieval/schemas.RetrievalResponse` + `cleaning.gates.py` (`detected_article_coverage`) + `tests/test_industrial_rag_providers.py` (`test_explicit_regulation_filter_never_falls_back_to_other_documents`).

Dokumen ini **tidak** mengandung kode baru — hanya kontrak yang sudah diverifikasi oleh pengujian (`tests/`) dan hasil E2E (kompensasi `answered`, THR `answered`, pajak `refused`, recall 1.0, gate `go`).
