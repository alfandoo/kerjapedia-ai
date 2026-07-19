# Product Requirements Document (PRD)

## KerjaPedia AI
### Asisten Regulasi Ketenagakerjaan Indonesia Berbasis Retrieval-Augmented Generation

**Versi:** 1.0
**Status:** Draft
**Tanggal:** 14 Juli 2026
**Pemilik Produk:** Al Fando
**Jenis Produk:** Web Application / AI Knowledge Assistant
**Target Platform:** Desktop dan mobile web

---

# 1. Ringkasan Produk

KerjaPedia AI adalah aplikasi berbasis Retrieval-Augmented Generation (RAG) yang membantu pengguna mencari, memahami, dan menelusuri regulasi ketenagakerjaan Indonesia dari dokumen resmi.

Sumber utama dokumen pada versi awal berasal dari Database Peraturan BPK:

- https://peraturan.bpk.go.id/

Pengguna dapat mengajukan pertanyaan menggunakan bahasa alami, seperti:

- Berapa lama batas maksimal PKWT?
- Apakah pekerja kontrak memperoleh uang kompensasi?
- Bagaimana ketentuan terbaru mengenai upah minimum?
- Apa hak pekerja ketika terkena PHK?
- Siapa yang berhak memperoleh THR?
- Apa perbedaan JHT, JKP, JKK, JKM, dan JP?
- Kapan perusahaan wajib membentuk P2K3?

Sistem akan mencari bagian regulasi yang relevan, menyusun jawaban berdasarkan dokumen yang ditemukan, dan menampilkan sumber berupa:

- Judul peraturan
- Nomor dan tahun peraturan
- Pasal dan ayat
- Nomor halaman
- Status peraturan
- Kutipan pendukung
- Tautan menuju sumber resmi

KerjaPedia AI bukan pengganti advokat, konsultan hukum, mediator hubungan industrial, atau instansi pemerintah. Produk berfungsi sebagai alat pencarian dan pemahaman informasi regulasi.

---

# 2. Latar Belakang

Informasi mengenai ketenagakerjaan Indonesia tersebar di banyak peraturan, mulai dari undang-undang, peraturan pemerintah, peraturan menteri, hingga peraturan perubahan.

Permasalahan utama yang dihadapi pengguna antara lain:

1. Sulit menentukan peraturan yang relevan dengan suatu persoalan.
2. Bahasa hukum sulit dipahami oleh masyarakat umum.
3. Sebuah ketentuan dapat berubah karena peraturan yang lebih baru.
4. Pengguna berisiko membaca dokumen yang sudah dicabut atau diubah.
5. Pencarian berdasarkan kata kunci belum selalu menemukan pasal yang paling relevan.
6. Pengguna membutuhkan jawaban cepat, tetapi tetap dapat memeriksa sumber aslinya.
7. Chatbot berbasis LLM dapat memberikan jawaban tanpa dasar dokumen yang jelas.

KerjaPedia AI dirancang untuk mengatasi masalah tersebut melalui retrieval berbasis dokumen resmi, metadata hukum, hybrid search, reranking, citation grounding, dan status-aware retrieval.

---

# 3. Visi Produk

Menjadi asisten pencarian regulasi ketenagakerjaan Indonesia yang mudah digunakan, dapat ditelusuri sumbernya, dan membantu pengguna memahami hak, kewajiban, serta proses ketenagakerjaan berdasarkan dokumen resmi.

---

# 4. Tujuan Produk

## 4.1 Tujuan Utama

1. Mempermudah pencarian informasi regulasi ketenagakerjaan.
2. Memberikan jawaban berdasarkan dokumen resmi.
3. Menampilkan pasal, ayat, halaman, dan sumber untuk setiap jawaban.
4. Memprioritaskan regulasi yang masih berlaku atau paling baru.
5. Mengurangi hallucination melalui retrieval dan mekanisme refusal.
6. Menyediakan sistem evaluasi RAG yang terukur.
7. Menjadi project portofolio AI Engineer yang production-oriented.

## 4.2 Tujuan Teknis

1. Membangun pipeline ingestion dokumen hukum.
2. Mengekstrak struktur dokumen berdasarkan BAB, bagian, pasal, dan ayat.
3. Mengimplementasikan hybrid retrieval.
4. Mengimplementasikan reranking.
5. Menyimpan relasi perubahan dan pencabutan antarperaturan.
6. Menampilkan citation yang dapat diverifikasi.
7. Memonitor latency, token usage, retrieval result, dan feedback pengguna.
8. Menyediakan evaluation dataset dan regression testing.

---

# 5. Sasaran dan Indikator Keberhasilan

## 5.1 Product Metrics

| Metrik | Target MVP |
|---|---:|
| Pertanyaan yang menghasilkan sumber valid | ≥ 90% |
| Jawaban dengan citation lengkap | 100% |
| Jawaban tanpa dukungan konteks | ≤ 5% |
| Retrieval Recall@5 | ≥ 0,80 |
| Mean Reciprocal Rank | ≥ 0,75 |
| Citation correctness | ≥ 0,90 |
| Faithfulness | ≥ 0,85 |
| Refusal accuracy | ≥ 0,85 |
| Median response time | ≤ 5 detik |
| Error rate request | < 2% |
| Ingestion success rate | ≥ 95% |

## 5.2 User Experience Metrics

| Metrik | Target MVP |
|---|---:|
| Pengguna dapat menemukan sumber dalam maksimal 2 klik | 100% |
| Feedback jawaban membantu | ≥ 75% |
| Pengguna memahami disclaimer | Tampil pada chat dan detail jawaban |
| Tampilan responsif | Desktop, tablet, dan mobile |

---

# 6. Target Pengguna

## 6.1 Pekerja atau Karyawan

Kebutuhan:

- Memahami hak kerja.
- Mengetahui ketentuan PKWT, PHK, pesangon, THR, dan BPJS.
- Menemukan dasar hukum yang relevan.

## 6.2 Staf HR dan Recruiter

Kebutuhan:

- Mencari ketentuan tentang kontrak kerja.
- Memahami waktu kerja, istirahat, PHK, dan kompensasi.
- Menelusuri perubahan regulasi.

## 6.3 Pemilik UMKM dan Perusahaan

Kebutuhan:

- Memahami kewajiban pengusaha.
- Mengetahui aturan pengupahan, THR, BPJS, dan K3.
- Mengurangi risiko penggunaan peraturan yang sudah tidak berlaku.

## 6.4 Mahasiswa dan Peneliti

Kebutuhan:

- Mencari regulasi untuk tugas atau penelitian.
- Menemukan pasal tertentu.
- Membandingkan peraturan dasar dan perubahannya.

## 6.5 Administrator Sistem

Kebutuhan:

- Mengelola dokumen.
- Memantau ingestion.
- Memperbarui status regulasi.
- Mengelola evaluation dataset.
- Memonitor performa RAG.

---

# 7. Persona

## Persona 1 — Pekerja

**Nama:** Budi
**Usia:** 28 tahun
**Tujuan:** Mengetahui hak setelah kontrak kerja berakhir.
**Masalah:** Tidak memahami istilah hukum dan tidak tahu dokumen yang harus dibaca.
**Kebutuhan utama:** Jawaban ringkas dengan sumber resmi dan pasal yang jelas.

## Persona 2 — HR Generalist

**Nama:** Sinta
**Usia:** 31 tahun
**Tujuan:** Memastikan kebijakan HR sesuai regulasi terbaru.
**Masalah:** Harus membaca beberapa peraturan dan peraturan perubahan.
**Kebutuhan utama:** Status peraturan, relasi perubahan, dan jawaban berbasis konteks.

## Persona 3 — Pemilik UMKM

**Nama:** Rudi
**Usia:** 40 tahun
**Tujuan:** Mengetahui kewajiban perusahaan terhadap pekerja.
**Masalah:** Terbatasnya pengetahuan hukum dan sumber daya konsultasi.
**Kebutuhan utama:** Penjelasan sederhana mengenai THR, BPJS, waktu kerja, dan PHK.

## Persona 4 — Admin Knowledge Base

**Nama:** Dewi
**Usia:** 29 tahun
**Tujuan:** Menjaga dokumen dan indeks RAG tetap valid.
**Masalah:** Dokumen dapat berubah, dicabut, atau mengalami kegagalan parsing.
**Kebutuhan utama:** Dashboard ingestion, versioning, log, dan validasi metadata.

---

# 8. Ruang Lingkup Produk

## 8.1 Cakupan MVP

MVP berfokus pada regulasi pemerintah pusat dengan topik berikut:

1. Dasar ketenagakerjaan.
2. PKWT.
3. Alih daya.
4. Waktu kerja dan waktu istirahat.
5. Pemutusan hubungan kerja.
6. Pesangon dan kompensasi.
7. Pengupahan.
8. Upah minimum.
9. Tunjangan Hari Raya.
10. BPJS Ketenagakerjaan.
11. Jaminan Kehilangan Pekerjaan.
12. JKK, JKM, dan JHT.
13. Keselamatan dan kesehatan kerja.
14. Sistem Manajemen K3.
15. P2K3.
16. Perselisihan hubungan industrial.
17. Serikat pekerja.

## 8.2 Dokumen Utama MVP

### Dasar ketenagakerjaan

- UU Nomor 13 Tahun 2003 tentang Ketenagakerjaan.
- UU Nomor 6 Tahun 2023 tentang Cipta Kerja.

### PKWT, PHK, waktu kerja, dan alih daya

- PP Nomor 35 Tahun 2021.
- Permenaker Nomor 7 Tahun 2026.
- PP Nomor 34 Tahun 2021 sebagai dokumen opsional mengenai tenaga kerja asing.

### Pengupahan dan THR

- PP Nomor 36 Tahun 2021.
- PP Nomor 51 Tahun 2023.
- PP Nomor 49 Tahun 2025.
- Permenaker Nomor 6 Tahun 2016.

### Jaminan sosial ketenagakerjaan

- UU Nomor 24 Tahun 2011.
- PP Nomor 37 Tahun 2021.
- PP Nomor 6 Tahun 2025.
- Permenaker Nomor 1 Tahun 2025.

### Keselamatan dan kesehatan kerja

- UU Nomor 1 Tahun 1970.
- PP Nomor 50 Tahun 2012.
- Permenaker Nomor 11 Tahun 2023.
- Permenaker Nomor 13 Tahun 2025.

### Hubungan industrial

- UU Nomor 2 Tahun 2004.
- UU Nomor 21 Tahun 2000.

## 8.3 Di Luar Cakupan MVP

Fitur berikut belum termasuk MVP:

- Konsultasi hukum personal.
- Pembuatan surat gugatan.
- Prediksi hasil perkara.
- Rekomendasi keputusan hukum yang mengikat.
- Integrasi dengan pengadilan.
- Perhitungan otomatis pesangon yang bersifat final.
- Seluruh peraturan daerah di Indonesia.
- Seluruh putusan Mahkamah Agung dan Mahkamah Konstitusi.
- Voice assistant.
- Mobile application native.
- Pengambilan dokumen otomatis tanpa proses verifikasi admin.
- Multi-tenant enterprise billing.

---

# 9. Proposisi Nilai

KerjaPedia AI memiliki nilai pembeda berikut:

1. Jawaban hanya berdasarkan dokumen yang berhasil di-retrieve.
2. Citation sampai level pasal, ayat, dan halaman.
3. Menampilkan status peraturan.
4. Menampilkan hubungan perubahan atau pencabutan.
5. Memprioritaskan ketentuan terbaru.
6. Mendukung pencarian kata hukum dan pertanyaan bahasa alami.
7. Menolak menjawab ketika konteks tidak memadai.
8. Menyediakan evaluation dashboard.
9. Dapat diaudit melalui logs dan traces.
10. Fokus pada regulasi ketenagakerjaan Indonesia.

---

# 10. User Journey Utama

## 10.1 Mencari Informasi Regulasi

```text
Pengguna membuka aplikasi
    ↓
Pengguna memasukkan pertanyaan
    ↓
Sistem mendeteksi topik dan intent
    ↓
Sistem melakukan query rewriting
    ↓
Sistem menjalankan hybrid retrieval
    ↓
Sistem melakukan metadata filtering
    ↓
Sistem melakukan reranking
    ↓
Sistem memeriksa status dan relasi peraturan
    ↓
LLM menyusun jawaban berdasarkan konteks
    ↓
Sistem menampilkan jawaban dan citation
    ↓
Pengguna membuka sumber atau memberi feedback
```

## 10.2 Menelusuri Sumber Jawaban

```text
Pengguna memilih citation
    ↓
Sistem membuka detail sumber
    ↓
Sistem menampilkan dokumen, pasal, ayat, dan halaman
    ↓
Bagian yang digunakan disorot
    ↓
Pengguna dapat membuka halaman resmi BPK
```

## 10.3 Mengunggah Dokumen

```text
Admin login
    ↓
Admin mengunggah PDF
    ↓
Sistem memvalidasi file
    ↓
Sistem mengekstrak metadata dan teks
    ↓
Sistem mendeteksi struktur hukum
    ↓
Sistem membuat chunk
    ↓
Sistem membuat embedding
    ↓
Sistem mengindeks data
    ↓
Admin memverifikasi hasil
    ↓
Dokumen dipublikasikan
```

---

# 11. Functional Requirements

## FR-01 — Authentication

Sistem harus menyediakan:

- Login.
- Logout.
- Session management.
- Role-based access.
- Protected admin routes.

Role MVP:

- Guest.
- User.
- Admin.

## FR-02 — Chat Interface

Pengguna harus dapat:

- Mengirim pertanyaan.
- Melihat streaming response.
- Menghentikan generasi.
- Membuat percakapan baru.
- Melihat riwayat percakapan.
- Menghapus percakapan.
- Menyalin jawaban.
- Membuka citation.
- Memberikan feedback.

## FR-03 — Query Understanding

Sistem harus:

- Mendeteksi bahasa pertanyaan.
- Mengidentifikasi topik.
- Mendeteksi jenis pertanyaan.
- Menormalisasi singkatan umum.
- Membuat query alternatif.
- Mempertahankan konteks percakapan.
- Mencegah query rewriting mengubah maksud pengguna.

Contoh intent:

- Definisi.
- Hak pekerja.
- Kewajiban perusahaan.
- Syarat.
- Durasi.
- Perhitungan.
- Prosedur.
- Perbandingan.
- Status peraturan.
- Perubahan regulasi.

## FR-04 — Hybrid Retrieval

Sistem harus menggabungkan:

- Dense vector retrieval.
- Sparse atau lexical retrieval.
- Metadata filtering.
- Reciprocal Rank Fusion atau metode fusion setara.
- Reranking.

Filter metadata minimum:

- Jenis peraturan.
- Nomor peraturan.
- Tahun.
- Topik.
- Status.
- Pasal.
- Institusi.
- Dokumen aktif atau historis.

## FR-05 — Status-Aware Retrieval

Sistem harus:

- Memeriksa status peraturan.
- Mengetahui apakah dokumen diubah.
- Mengetahui dokumen yang mengubah.
- Mengetahui apakah dokumen dicabut.
- Menyimpan hubungan antarperaturan.
- Memprioritaskan dokumen aktif.
- Memberi peringatan ketika sumber historis digunakan.
- Mengambil dokumen dasar dan perubahannya ketika diperlukan.

## FR-06 — Answer Generation

Jawaban harus:

- Berdasarkan konteks retrieval.
- Tidak menambahkan pasal yang tidak ada dalam konteks.
- Menggunakan bahasa yang mudah dipahami.
- Membedakan kutipan dan penjelasan.
- Menyebutkan ketidakpastian.
- Menolak menjawab jika sumber tidak cukup.
- Menampilkan disclaimer.
- Tidak memberikan klaim hukum definitif tanpa citation.

Format jawaban minimum:

1. Jawaban ringkas.
2. Penjelasan.
3. Dasar regulasi.
4. Citation.
5. Catatan atau keterbatasan.

## FR-07 — Citation

Setiap citation harus memuat:

- Document ID.
- Judul dokumen.
- Nomor dan tahun.
- BAB atau bagian.
- Pasal.
- Ayat jika tersedia.
- Halaman.
- Kutipan teks.
- Status.
- Source URL.
- Retrieval score internal.

Retrieval score tidak wajib ditampilkan kepada pengguna umum.

## FR-08 — Refusal dan Clarification

Sistem harus menolak atau meminta klarifikasi ketika:

- Dokumen yang relevan tidak ditemukan.
- Pertanyaan di luar domain ketenagakerjaan.
- Pertanyaan meminta keputusan hukum personal.
- Pertanyaan terlalu umum.
- Konteks saling bertentangan.
- Status regulasi belum diverifikasi.
- Pengguna meminta tindakan ilegal atau manipulatif.

Contoh refusal:

> Informasi yang cukup tidak ditemukan dalam dokumen yang tersedia. Silakan perjelas konteks atau periksa sumber resmi dan konsultasikan dengan pihak yang berwenang.

## FR-09 — Document Management

Admin harus dapat:

- Mengunggah PDF.
- Menambahkan source URL.
- Mengedit metadata.
- Melihat status ingestion.
- Melihat hasil parsing.
- Melihat jumlah halaman.
- Melihat jumlah chunk.
- Menandai status legal.
- Menambahkan relasi antarperaturan.
- Mengaktifkan atau menonaktifkan dokumen.
- Menghapus dokumen.
- Melakukan re-indexing.
- Mengunduh laporan ingestion.

## FR-10 — Ingestion Pipeline

Pipeline harus mencakup:

1. Upload atau download file.
2. File validation.
3. MIME type validation.
4. Checksum generation.
5. Duplicate detection.
6. PDF text extraction.
7. OCR fallback.
8. Header dan footer removal.
9. Page boundary preservation.
10. Struktur BAB, bagian, pasal, dan ayat.
11. Chunking.
12. Metadata enrichment.
13. Embedding.
14. Indexing.
15. Quality validation.
16. Publication.

Status ingestion:

- Queued.
- Downloading.
- Validating.
- Parsing.
- OCR.
- Chunking.
- Embedding.
- Indexing.
- Review required.
- Completed.
- Failed.

## FR-11 — Document Versioning

Sistem harus:

- Menyimpan versi file.
- Menyimpan checksum.
- Mendeteksi file yang berubah.
- Menonaktifkan index versi lama.
- Mempertahankan audit history.
- Menyimpan waktu pengambilan dokumen.
- Menampilkan status versi.

## FR-12 — Feedback

Pengguna dapat memberi:

- Helpful.
- Not helpful.
- Citation incorrect.
- Answer incomplete.
- Outdated regulation.
- Other feedback.

Admin dapat melihat:

- Pertanyaan.
- Jawaban.
- Context.
- Citation.
- Feedback.
- Timestamp.
- Model.
- Prompt version.

## FR-13 — Search Dokumen

Selain chat, pengguna harus dapat:

- Mencari dokumen berdasarkan judul.
- Memfilter jenis peraturan.
- Memfilter tahun.
- Memfilter topik.
- Memfilter status.
- Membuka detail regulasi.
- Melihat hubungan antarregulasi.

## FR-14 — Evaluation Dashboard

Admin harus dapat:

- Membuat evaluation dataset.
- Menjalankan retrieval evaluation.
- Menjalankan generation evaluation.
- Membandingkan eksperimen.
- Melihat regression.
- Mengekspor hasil.

Metrik minimum:

- Hit Rate@K.
- Recall@K.
- Precision@K.
- MRR.
- NDCG.
- Context precision.
- Context recall.
- Faithfulness.
- Answer relevance.
- Citation correctness.
- Refusal accuracy.
- Latency.
- Token usage.

## FR-15 — Observability

Sistem harus mencatat:

- User query.
- Rewritten query.
- Retrieved chunks.
- Retrieval scores.
- Reranking scores.
- Prompt version.
- Model version.
- Generated answer.
- Citation.
- Token usage.
- Cost estimation.
- Latency per tahap.
- Error.
- User feedback.

## FR-16 — Audit Log

Admin harus dapat melihat:

- Upload dokumen.
- Edit metadata.
- Perubahan status.
- Re-indexing.
- Penghapusan dokumen.
- Perubahan relationship.
- Perubahan prompt.
- Perubahan evaluation dataset.

---

# 12. Non-Functional Requirements

## NFR-01 — Performance

- Median response time maksimal 5 detik.
- Retrieval awal maksimal 1 detik.
- Reranking maksimal 2 detik.
- Chat mendukung streaming.
- Dokumen diproses secara asynchronous.
- Cache digunakan untuk pertanyaan populer.

## NFR-02 — Reliability

- Retry pada kegagalan ingestion.
- Idempotent document processing.
- Job yang gagal dapat dilanjutkan.
- Backup metadata database.
- Health check untuk service utama.
- Error message tidak mengekspos informasi sensitif.

## NFR-03 — Security

- Password disimpan dengan secure hashing.
- Authentication menggunakan token atau secure session.
- Admin endpoint dilindungi.
- File upload dibatasi berdasarkan tipe dan ukuran.
- Input disanitasi.
- Rate limiting diterapkan.
- Prompt injection dari dokumen harus diminimalkan.
- Source URL divalidasi.
- Secret disimpan melalui environment variable.
- Log tidak menyimpan password atau token.

## NFR-04 — Privacy

- Riwayat chat hanya dapat diakses oleh pemilik.
- Data personal pengguna tidak digunakan untuk training tanpa izin.
- Pengguna dapat menghapus riwayat percakapan.
- Admin tidak melihat data sensitif yang tidak diperlukan.
- Retention policy harus terdokumentasi.

## NFR-05 — Accessibility

- Mendukung keyboard navigation.
- Memiliki kontras yang cukup.
- Label form terbaca screen reader.
- Focus state terlihat.
- Font dapat dibaca pada mobile.
- Citation dapat diakses tanpa hover.

## NFR-06 — Maintainability

- Backend modular.
- Pipeline ingestion terpisah dari chat API.
- Prompt memiliki versioning.
- Schema tervalidasi.
- Automated testing tersedia.
- Dokumentasi deployment tersedia.
- Konfigurasi tidak di-hardcode.

## NFR-07 — Scalability

MVP harus dapat dikembangkan untuk:

- Ratusan hingga ribuan dokumen.
- Multi-worker ingestion.
- Horizontal scaling API.
- Managed vector database.
- Object storage.
- Multi-tenant organization.

---

# 13. Dataset Requirements

## 13.1 Struktur Dataset

```text
kerjapedia-rag-dataset/
├── 01_raw/
├── 02_interim/
├── 03_processed/
├── 04_metadata/
├── 05_evaluation/
├── 06_versions/
├── 07_schemas/
└── 08_logs/
```

## 13.2 Metadata Dokumen

```json
{
  "document_id": "PP-35-2021",
  "title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
  "short_title": "PP 35/2021",
  "regulation_type": "PP",
  "number": 35,
  "year": 2021,
  "topics": [
    "pkwt",
    "alih_daya",
    "waktu_kerja",
    "phk",
    "pesangon"
  ],
  "legal_status": "berlaku",
  "effective_date": "2021-02-02",
  "issuer": "Pemerintah Republik Indonesia",
  "source_name": "Database Peraturan BPK",
  "source_url": "https://peraturan.bpk.go.id/",
  "local_file": "01_raw/02_pkwt_phk_alih_daya/pp_35_2021.pdf",
  "checksum": "sha256-value",
  "downloaded_at": "2026-07-14T00:00:00+07:00",
  "version": 1
}
```

## 13.3 Metadata Chunk

```json
{
  "chunk_id": "PP-35-2021-PASAL-15-AYAT-1",
  "document_id": "PP-35-2021",
  "document_title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
  "chapter": "BAB II",
  "section": "Perjanjian Kerja Waktu Tertentu",
  "article": "Pasal 15",
  "paragraph": "Ayat (1)",
  "page_start": 12,
  "page_end": 12,
  "topic": "kompensasi_pkwt",
  "text": "Isi teks regulasi...",
  "legal_status": "berlaku",
  "source_url": "https://peraturan.bpk.go.id/",
  "token_count": 142
}
```

## 13.4 Document Relationship

Relationship yang didukung:

- Amends.
- Amended by.
- Revokes.
- Revoked by.
- Implements.
- Implemented by.
- Related to.
- Judicially reviewed by.
- Replaces.
- Replaced by.

Contoh:

```json
{
  "source_document_id": "PP-51-2023",
  "relationship": "amends",
  "target_document_id": "PP-36-2021",
  "description": "Mengubah sejumlah ketentuan pengupahan"
}
```

---

# 14. Chunking Strategy

Chunking dokumen hukum tidak boleh hanya menggunakan ukuran karakter tetap.

## 14.1 Hierarchical Legal Chunking

Urutan struktur:

```text
Dokumen
  └── BAB
      └── Bagian
          └── Paragraf
              └── Pasal
                  └── Ayat
```

## 14.2 Aturan Chunking

1. Satu pasal pendek menjadi satu chunk.
2. Pasal panjang dapat dipisah berdasarkan ayat.
3. Judul BAB dan bagian dimasukkan sebagai parent context.
4. Chunk tidak boleh memisahkan satu kalimat.
5. Nomor halaman harus dipertahankan.
6. Penjelasan peraturan disimpan sebagai tipe chunk terpisah.
7. Lampiran dipisahkan berdasarkan tabel atau bagian.
8. Overlap hanya digunakan bila struktur tidak cukup.

Target ukuran:

- 250–700 token per chunk.
- Maksimal 1.000 token.
- Overlap 50–100 token untuk chunk non-struktural.

## 14.3 Context Expansion

Saat sebuah ayat diambil, sistem dapat menambahkan:

- Judul pasal.
- Ayat sebelum dan sesudah.
- Judul bagian.
- Metadata regulasi.
- Relationship summary.

---

# 15. Retrieval Design

## 15.1 Retrieval Pipeline

```text
Original query
    ↓
Intent classification
    ↓
Query rewriting
    ↓
Dense retrieval
    +
Sparse retrieval
    ↓
Metadata filtering
    ↓
Result fusion
    ↓
Cross-encoder reranking
    ↓
Status-aware validation
    ↓
Context assembly
```

## 15.2 Retrieval Parameters Awal

| Parameter | Nilai Awal |
|---|---:|
| Dense top-k | 20 |
| Sparse top-k | 20 |
| Fusion candidates | 30 |
| Reranker candidates | 20 |
| Final context | 5–8 chunks |
| Score threshold | Ditentukan melalui evaluasi |
| Maximum context tokens | Disesuaikan model |

## 15.3 Query Expansion

Contoh:

```text
Pertanyaan asli:
Apakah pegawai kontrak dapat uang setelah kontraknya selesai?

Query alternatif:
- uang kompensasi PKWT
- berakhirnya perjanjian kerja waktu tertentu
- hak pekerja PKWT
- kompensasi masa kerja kontrak
```

---

# 16. Prompt Requirements

System prompt harus mengatur agar model:

1. Hanya menggunakan konteks.
2. Tidak mengarang pasal.
3. Tidak memberikan nasihat hukum personal.
4. Menyebutkan ketika sumber tidak cukup.
5. Menampilkan perbedaan antara aturan umum dan pengecualian.
6. Memprioritaskan peraturan terbaru.
7. Menyebutkan jika dokumen telah diubah.
8. Menggunakan bahasa Indonesia yang jelas.
9. Menyertakan citation pada setiap klaim utama.
10. Tidak mengikuti instruksi berbahaya dari isi dokumen.

Template jawaban:

```text
Jawaban:
[Ringkasan berdasarkan konteks]

Penjelasan:
[Penjelasan mudah dipahami]

Dasar regulasi:
- [Peraturan, pasal, ayat, halaman]

Catatan:
[Status perubahan, keterbatasan, atau disclaimer]
```

---

# 17. Information Architecture

## 17.1 Public Pages

- Landing page.
- Tentang produk.
- Kebijakan privasi.
- Ketentuan penggunaan.
- Disclaimer.
- Login.

## 17.2 User Pages

- Chat.
- Riwayat chat.
- Detail percakapan.
- Search regulasi.
- Detail regulasi.
- Source viewer.
- Profil.
- Settings.

## 17.3 Admin Pages

- Dashboard.
- Documents.
- Upload document.
- Ingestion jobs.
- Document detail.
- Metadata editor.
- Relationship editor.
- Retrieval playground.
- Evaluation datasets.
- Evaluation results.
- Prompt management.
- User feedback.
- Logs.
- Audit trail.
- System settings.

---

# 18. UI/UX Requirements

## 18.1 Design Direction

Gaya visual:

- Modern SaaS.
- Bersih dan profesional.
- Dominan putih atau off-white.
- Primary biru.
- Accent hijau untuk status berlaku.
- Kuning untuk peringatan.
- Merah untuk dicabut atau gagal.
- Rounded card.
- Soft shadow.
- Typography yang mudah dibaca.

## 18.2 Chat Layout

Desktop:

```text
┌───────────────┬──────────────────────────────┬─────────────────┐
│ Conversations │ Chat and answer              │ Source details  │
│               │                              │                 │
│               │ Question                     │ Regulation      │
│               │ Answer                       │ Article         │
│               │ Citations                    │ Quotation       │
└───────────────┴──────────────────────────────┴─────────────────┘
```

Mobile:

- Sidebar menjadi drawer.
- Source detail menjadi bottom sheet atau halaman terpisah.
- Composer tetap mudah dijangkau.
- Citation tampil dalam card ringkas.

## 18.3 Answer Card

Answer card harus memiliki:

- Answer text.
- Status badge.
- Source count.
- Citation chips.
- Copy action.
- Helpful/not helpful.
- Disclaimer.
- Generated timestamp.

---

# 19. Data Model Utama

## 19.1 Relational Database

Tabel minimum:

- users
- roles
- user_roles
- documents
- document_versions
- document_topics
- document_relationships
- ingestion_jobs
- conversations
- messages
- message_citations
- feedback
- evaluation_datasets
- evaluation_questions
- evaluation_runs
- evaluation_results
- prompt_versions
- audit_logs

## 19.2 Vector Database

Collection minimum:

- active_regulations
- historical_regulations
- court_decisions
- regional_regulations

Payload minimum:

- chunk_id
- document_id
- title
- document_type
- number
- year
- topic
- article
- paragraph
- page
- legal_status
- version
- source_url
- access_level
- text

## 19.3 Object Storage

Menyimpan:

- Raw PDF.
- Page images.
- OCR output.
- Parsing artifacts.
- Exported evaluation reports.

---

# 20. API Requirements

## 20.1 Authentication

```text
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

## 20.2 Chat

```text
POST   /api/v1/chat/query
GET    /api/v1/conversations
POST   /api/v1/conversations
GET    /api/v1/conversations/{id}
DELETE /api/v1/conversations/{id}
POST   /api/v1/messages/{id}/feedback
```

## 20.3 Documents

```text
GET    /api/v1/documents
POST   /api/v1/documents
GET    /api/v1/documents/{id}
PATCH  /api/v1/documents/{id}
DELETE /api/v1/documents/{id}
POST   /api/v1/documents/{id}/reindex
POST   /api/v1/documents/{id}/publish
```

## 20.4 Ingestion

```text
POST /api/v1/ingestion/jobs
GET  /api/v1/ingestion/jobs
GET  /api/v1/ingestion/jobs/{id}
POST /api/v1/ingestion/jobs/{id}/retry
```

## 20.5 Evaluation

```text
GET  /api/v1/evaluations/datasets
POST /api/v1/evaluations/datasets
POST /api/v1/evaluations/runs
GET  /api/v1/evaluations/runs/{id}
GET  /api/v1/evaluations/runs/{id}/results
```

---

# 21. Rekomendasi Tech Stack

## Frontend

- Next.js.
- TypeScript.
- Tailwind CSS.
- shadcn/ui.
- TanStack Query.
- React Hook Form.
- Zod.
- Recharts.

## Backend

- FastAPI.
- Pydantic.
- SQLAlchemy.
- Alembic.
- Celery atau Dramatiq.
- Redis.

## Data Storage

- PostgreSQL atau Supabase PostgreSQL.
- Qdrant.
- MinIO untuk local development.
- S3-compatible storage untuk production.
- Redis untuk queue dan cache.

## RAG dan AI

- PyMuPDF.
- Unstructured sebagai parser tambahan.
- Tesseract untuk OCR fallback.
- Multilingual embedding model.
- Sparse retrieval atau BM25.
- Cross-encoder reranker.
- LLM API untuk generation.
- Ragas untuk evaluation.
- Langfuse untuk tracing dan observability.

## DevOps

- Docker.
- Docker Compose.
- GitHub Actions.
- Nginx.
- Pytest.
- Playwright.
- Ruff.
- MyPy.
- Pre-commit.

---

# 22. Arsitektur Sistem

```text
┌─────────────────────────────────────────┐
│              Next.js Web App            │
│ Chat • Search • Sources • Admin         │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│              FastAPI Backend            │
│ Auth • Chat • Documents • Evaluation   │
└─────────┬─────────────────┬─────────────┘
          │                 │
┌─────────▼────────┐  ┌─────▼────────────┐
│ Retrieval Engine │  │ Ingestion Worker │
│ Dense + Sparse   │  │ Parse • OCR      │
│ Filter • Rerank  │  │ Chunk • Embed    │
└─────────┬────────┘  └─────┬────────────┘
          │                 │
┌─────────▼─────────────────▼─────────────┐
│                Qdrant                   │
│ Vectors • Payload • Hybrid Search      │
└─────────────────────────────────────────┘

┌────────────────┐ ┌────────────┐ ┌───────────────┐
│ PostgreSQL     │ │ Redis      │ │ MinIO / S3    │
│ App metadata   │ │ Queue/cache│ │ Document files│
└────────────────┘ └────────────┘ └───────────────┘

┌─────────────────────────────────────────┐
│       Langfuse • Ragas • Monitoring     │
└─────────────────────────────────────────┘
```

---

# 23. Evaluation Dataset

## 23.1 Target Awal

Minimal 150 pertanyaan yang diverifikasi manual.

Distribusi:

| Topik | Jumlah |
|---|---:|
| PKWT | 15 |
| PHK dan pesangon | 25 |
| Alih daya | 10 |
| Waktu kerja | 10 |
| Pengupahan | 20 |
| THR | 15 |
| BPJS dan JKP | 20 |
| K3 | 15 |
| Hubungan industrial | 15 |
| Refusal/out-of-domain | 5 |
| **Total** | **150** |

## 23.2 Format Evaluation Question

```json
{
  "question_id": "EVAL-PKWT-001",
  "question": "Apakah pekerja PKWT memperoleh uang kompensasi?",
  "expected_answer": "Pekerja PKWT memperoleh uang kompensasi sesuai ketentuan dan masa kerja.",
  "expected_document_ids": [
    "PP-35-2021"
  ],
  "expected_articles": [
    "Pasal terkait uang kompensasi PKWT"
  ],
  "expected_topics": [
    "pkwt",
    "kompensasi"
  ],
  "should_refuse": false,
  "verified_by": "human",
  "status": "approved"
}
```

## 23.3 Hard Negative Questions

Dataset harus memuat pertanyaan dengan istilah mirip tetapi konteks berbeda untuk menguji retrieval.

Contoh:

- Perbedaan kompensasi PKWT dan pesangon PHK.
- Perbedaan JKP dan JHT.
- Perbedaan waktu istirahat dan cuti.
- Perbedaan outsourcing dan PKWT.

---

# 24. Security dan Responsible AI

## 24.1 Legal Safety

- Selalu tampilkan disclaimer.
- Jangan menyebut jawaban sebagai keputusan hukum.
- Jangan menjamin hasil perselisihan.
- Jangan mengarang pasal atau putusan.
- Gunakan tanggal pembaruan dataset.
- Beri peringatan jika peraturan telah diubah.
- Sarankan verifikasi ke sumber resmi pada persoalan berisiko tinggi.

## 24.2 Prompt Injection Defense

- Isi dokumen diperlakukan sebagai data, bukan instruksi.
- Instruksi pada dokumen tidak boleh mengubah system prompt.
- Output retrieval dipisahkan dari tool instruction.
- Source URL dan file divalidasi.
- HTML dan script dihapus dari dokumen.
- Citation harus berasal dari document ID yang valid.

## 24.3 Abuse Prevention

Sistem harus menolak permintaan untuk:

- Memalsukan dokumen hukum.
- Memanipulasi bukti.
- Menghindari kewajiban hukum secara ilegal.
- Melakukan diskriminasi terhadap pekerja.
- Mengintimidasi pekerja atau pengusaha.
- Menghasilkan informasi palsu yang mengatasnamakan instansi.

---

# 25. Analytics

Data yang dikumpulkan:

- Jumlah query.
- Topik populer.
- Query tanpa jawaban.
- Query dengan refusal.
- Citation click-through.
- Helpful rate.
- Average latency.
- Token usage.
- Error rate.
- Retrieval confidence distribution.
- Frequently failed documents.
- Search-to-source conversion.

Analytics tidak boleh menyimpan data personal sensitif tanpa kebutuhan jelas.

---

# 26. Acceptance Criteria MVP

## Chat

- Pengguna dapat mengirim pertanyaan.
- Jawaban ditampilkan secara streaming.
- Jawaban memiliki minimal satu citation ketika informasi ditemukan.
- Citation dapat dibuka.
- Sistem menolak jawaban jika tidak menemukan konteks cukup.

## Retrieval

- Dense dan sparse retrieval berjalan.
- Metadata filtering berjalan.
- Reranking berjalan.
- Dokumen historis tidak diprioritaskan dibanding dokumen aktif.
- Relationship antarperaturan dipertimbangkan.

## Document Management

- Admin dapat mengunggah PDF.
- Sistem memvalidasi PDF.
- Sistem mengekstrak teks dan halaman.
- Sistem menghasilkan chunk.
- Sistem mengindeks chunk ke vector database.
- Admin dapat melihat dan mengulang job yang gagal.

## Citation

- Citation menampilkan judul.
- Citation menampilkan nomor dan tahun.
- Citation menampilkan pasal atau bagian jika tersedia.
- Citation menampilkan halaman.
- Citation memiliki tautan sumber.

## Evaluation

- Minimal 150 pertanyaan tersedia.
- Retrieval metrics dapat dihitung.
- Generation metrics dapat dihitung.
- Hasil baseline dan hybrid dapat dibandingkan.

## Security

- Admin route tidak dapat diakses user biasa.
- Rate limiting aktif.
- File non-PDF ditolak pada MVP.
- Secret tidak terdapat pada source code.
- Input pengguna tervalidasi.

---

# 27. Roadmap Pengembangan

## Phase 1 — Foundation

- Setup repository.
- Setup frontend dan backend.
- Setup PostgreSQL.
- Setup Qdrant.
- Setup object storage.
- Authentication.
- Basic document schema.

## Phase 2 — Baseline RAG

- Upload PDF.
- Text extraction.
- Basic chunking.
- Dense embedding.
- Vector retrieval.
- LLM answer.
- Basic citation.

## Phase 3 — Legal Document Processing

- BAB, pasal, dan ayat extraction.
- Page preservation.
- Legal metadata.
- Document relationship.
- Status-aware retrieval.
- Historical regulation handling.

## Phase 4 — Retrieval Improvement

- Sparse retrieval.
- Hybrid fusion.
- Query rewriting.
- Reranking.
- Context expansion.
- Threshold tuning.
- Refusal mechanism.

## Phase 5 — Admin and Evaluation

- Document dashboard.
- Ingestion monitoring.
- Evaluation dataset.
- Retrieval evaluation.
- Generation evaluation.
- Experiment comparison.

## Phase 6 — Production Readiness

- Observability.
- Prompt versioning.
- Caching.
- Rate limiting.
- Security hardening.
- CI/CD.
- Load testing.
- Deployment.

## Phase 7 — Future Expansion

- Putusan Mahkamah Konstitusi.
- Putusan Mahkamah Agung.
- Peraturan daerah.
- Upah minimum provinsi.
- Perbandingan peraturan.
- Timeline regulasi.
- Multimodal document understanding.
- Enterprise workspace.
- API access.

---

# 28. Risiko dan Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Peraturan berubah | Jawaban usang | Versioning, update schedule, status-aware retrieval |
| Parsing pasal gagal | Citation salah | Validation, review admin, parser khusus regulasi |
| PDF scan | Teks tidak terbaca | OCR fallback dan confidence threshold |
| Hallucination | Informasi menyesatkan | Grounded prompt, citation, refusal |
| Retrieval salah | Jawaban tidak relevan | Hybrid search, reranking, evaluation |
| Perubahan hubungan hukum kompleks | Prioritas sumber keliru | Relationship graph dan verifikasi manual |
| Source website berubah | Download gagal | Retry, source manifest, snapshot |
| Query ambigu | Jawaban salah konteks | Clarification dan intent detection |
| Latency tinggi | UX buruk | Cache, async processing, model optimization |
| Biaya LLM meningkat | Operasional mahal | Token limit, caching, model routing |

---

# 29. Dependencies

## External Dependencies

- Database Peraturan BPK.
- LLM provider.
- Embedding model.
- Qdrant.
- PostgreSQL atau Supabase.
- Redis.
- Object storage.
- OCR engine.

## Internal Dependencies

- Dataset regulasi.
- Metadata terverifikasi.
- Relationship antarperaturan.
- Evaluation dataset.
- Prompt template.
- Infrastructure deployment.

---

# 30. Assumptions

1. Dokumen yang digunakan tersedia untuk akses publik.
2. MVP menggunakan dokumen pemerintah pusat.
3. Pengguna utama menggunakan bahasa Indonesia.
4. LLM digunakan melalui API.
5. Embedding dapat dijalankan secara lokal atau melalui service.
6. Admin melakukan validasi metadata hukum.
7. Aplikasi tidak memberikan keputusan hukum yang mengikat.
8. Dokumen terbaru akan diperbarui secara berkala.

---

# 31. Definition of Done

MVP dianggap selesai apabila:

1. Minimal 18 dokumen utama berhasil di-ingest.
2. Struktur pasal dan halaman berhasil dipertahankan.
3. Chat RAG berjalan dengan citation.
4. Hybrid retrieval dan reranking aktif.
5. Relationship perubahan regulasi tersimpan.
6. Dokumen historis dapat dibedakan dari dokumen aktif.
7. Minimal 150 pertanyaan evaluasi tersedia.
8. Retrieval Recall@5 mencapai minimal 0,80.
9. Faithfulness mencapai minimal 0,85.
10. Admin dapat mengelola dokumen dan ingestion job.
11. Observability dan feedback tersedia.
12. Aplikasi dapat dijalankan menggunakan Docker Compose.
13. Dokumentasi instalasi dan penggunaan tersedia.
14. Disclaimer tampil pada area yang relevan.
15. Automated test utama berhasil dijalankan.

---

# 32. Deliverables

- `PRD.md`
- `SRS.md`
- `TRD.md`
- `ERD.md`
- `API_SPEC.md`
- `RAG_PIPELINE.md`
- `EVALUATION_PLAN.md`
- `DATASET_DOCUMENTATION.md`
- `SECURITY.md`
- `DEPLOYMENT.md`
- Source code frontend.
- Source code backend.
- Ingestion worker.
- Evaluation scripts.
- Docker Compose.
- CI/CD workflow.
- Dataset manifest.
- Evaluation report.
- Demo video.
- Portfolio case study.

---

# 33. Ringkasan MVP

KerjaPedia AI versi MVP adalah web application yang memungkinkan pengguna menanyakan regulasi ketenagakerjaan Indonesia dan memperoleh jawaban berbasis dokumen resmi.

Kemampuan utama MVP:

- Chat regulasi.
- Hybrid retrieval.
- Reranking.
- Status-aware retrieval.
- Citation pasal dan halaman.
- Document relationship.
- Refusal mechanism.
- Admin document management.
- Evaluation dashboard.
- Observability.
- Dockerized deployment.

Fokus utama produk bukan menggantikan konsultan hukum, tetapi menyediakan sistem pencarian regulasi yang cepat, transparan, dapat diaudit, dan mudah digunakan.
