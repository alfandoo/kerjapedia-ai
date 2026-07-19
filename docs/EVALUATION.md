# RAG Evaluation

KerjaPedia AI mengevaluasi retrieval dan jawaban menggunakan
`evaluation/golden_questions.json`. Dataset seed berisi 150 pertanyaan sesuai
distribusi topik pada PRD, termasuk hard negative dan lima pertanyaan refusal.
Setiap item memuat jawaban ideal, dokumen, pasal, topik, serta status verifikasi.

## Quality Gate

Dataset yang dihasilkan otomatis berstatus `needs_human_review`. Pertanyaan,
jawaban ideal, dan rujukan hukum harus diperiksa oleh reviewer domain sebelum
hasil dipakai sebagai klaim kualitas produksi. Ubah `status` dan `verified_by`
hanya setelah sumbernya benar-benar diperiksa.

Target awal PRD adalah Retrieval Recall@5 minimal 0,80. Laporan juga mencakup:

- MRR untuk posisi dokumen relevan pertama.
- Citation correctness untuk kecocokan dokumen dan pasal.
- Faithfulness untuk dukungan kutipan terhadap jawaban.
- Refusal accuracy untuk pertanyaan tanpa dasar dokumen.
- Hard-negative Recall@5 dan rincian metrik per topik.

## Menjalankan Evaluasi

Dari root repository, buat ulang dataset bila definisi kasus berubah:

```powershell
apps\api\.venv\Scripts\python scripts\generate_evaluation_dataset.py
```

Jalankan empat eksperimen terhadap artifact ingestion lokal:

```powershell
cd apps/api
.venv\Scripts\python -m app.services.evaluation.cli `
  --dataset ../../evaluation/golden_questions.json `
  --storage-root ../../storage/ingestion `
  --output ../../storage/evaluation/report.json `
  --top-k 5
```

Mode `baseline`, `dense`, `hybrid`, dan `rerank` membandingkan lexical score,
semantic score, fusion score, dan final reranker score. Gunakan `--modes hybrid
rerank` untuk menjalankan sebagian mode.

## Regression Test

```powershell
cd apps/api
.venv\Scripts\python -m pytest tests/test_evaluation.py
```

Test memvalidasi jumlah dan distribusi dataset, implementasi metrik, perbandingan
mode, serta Recall@5 dan MRR pada kasus inti PKWT, PHK, THR, BPJS, dan K3.
