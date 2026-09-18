# KerjaPedia AI Evaluation Pipeline

Evaluasi kualitas RAG (Retrieval-Augmented Generation) untuk asisten hukum ketenagakerjaan Indonesia.

## Dataset

### Golden Questions (`golden_questions.json`)

Dataset evaluasi berisi **130 pertanyaan** (skema 1.1.0) dengan distribusi:

| Kategori | Jumlah | Deskripsi |
|---|---|---|
| pkwt | 12 | Perjanjian Kerja Waktu Tertentu |
| phk_pesangon | 20 | Pemutusan Hubungan Kerja & Pesangon |
| alih_daya | 10 | Alih Daya / Outsourcing |
| waktu_kerja | 10 | Waktu Kerja & Lembur |
| pengupahan | 16 | Upah & Pengupahan |
| thr | 12 | Tunjangan Hari Raya |
| bpjs_jkp | 16 | Jaminan Kehilangan Pekerjaan |
| k3 | 12 | Keselamatan & Kesehatan Kerja |
| hubungan_industrial | 12 | Hubungan Industrial |
| refusal | 10 | Pertanyaan di luar cakupan |

**Split**: 89 development / 41 test

### Struktur Setiap Pertanyaan

```json
{
  "question_id": "EVAL-PKWT-001",
  "category": "pkwt",
  "question": "Apakah pekerja PKWT memperoleh uang kompensasi?",
  "expected_answer": "Pekerja PKWT memperoleh uang kompensasi...",
  "expected_document_ids": ["PP-35-2021"],
  "expected_articles": ["Pasal 15", "Pasal 16"],
  "expected_topics": ["pkwt", "kompensasi"],
  "should_refuse": false,
  "hard_negative": false,
  "split": "development",
  "scenario_tags": []
}
```

### Validasi Dataset

```bash
cd apps/api
python -m pytest tests/test_evaluation.py::test_golden_dataset_has_prd_distribution_and_hard_negatives -v
```

## Script Evaluasi

### 0. Evaluasi Backend Live — Upstash Hybrid (`scripts/eval_upstash_sample.py`)

Jalur aktif untuk mengukur retrieval produksi (wajib kredensial Upstash):

```bash
apps/api/.venv/Scripts/python scripts/eval_upstash_sample.py
```

Sampel deterministik 10 pertanyaan memakai fungsi metrik repo; report JSON
ditulis ke `storage/evaluation/` (tidak di-commit).

### 1. Retrieval Metrics (`retrieval_metrics.py`)

Mengukur kualitas retrieval tanpa answer generation.

```bash
cd evaluation
python retrieval_metrics.py --top-k 5 --output retrieval_metrics_report.json
```

**Metrik yang diukur:**
- **Recall@K**: Proporsi dokumen yang benar ditemukan di top-K
- **MRR (Mean Reciprocal Rank)**: Rata-rata 1/rank dokumen pertama yang benar
- **nDCG@10**: Normalized Discounted Cumulative Gain

### 2. Reranker Tuning (`tune_reranker.py`)

Menguji konfigurasi weight berbeda untuk reranker.

```bash
cd evaluation
python tune_reranker.py --top-k 5 --output reranker_tuning_report.json
```

**Konfigurasi yang diuji:**
- `baseline`: Default weights
- `semantic_heavy`: Lebih mengutamakan semantic similarity
- `lexical_heavy`: Lebih mengutamakan keyword matching
- `fusion_heavy`: Lebih mengutamakan fusion score
- `balanced`: Seimbang semua komponen
- `topic_boosted`: Boost untuk topic match
- `article_boosted`: Boost untuk article match

### 3. Semantic Evaluation (`semantic_eval.py`)

Mengukur kualitas jawaban dan citation.

```bash
cd evaluation
python semantic_eval.py --top-k 5 --output semantic_eval_report.json
```

**Metrik yang diukur:**
- **Recall@K**: Kualitas retrieval
- **Citation Correctness**: Akurasi citation yang dikutip
- **Faithfulness**: Seberapa didukung jawaban oleh citation
- **Unsupported Claim Rate**: Proporsi klaim tanpa citation

## Interpretasi Metrik

### Target Kualitas

| Metrik | Target | Deskripsi |
|---|---|---|
| Recall@5 | ≥ 90% | Dokumen relevan harus masuk top-5 |
| Recall@10 | ≥ 95% | Dokumen relevan harus masuk top-10 |
| MRR | ≥ 0.8 | Dokumen pertama harus benar |
| Citation Correctness | ≥ 95% | Citation harus akurat |
| Faithfulness | ≥ 90% | Jawaban harus didukung citation |
| Unsupported Claim Rate | ≤ 5% | Semua klaim harus ada citation |

### Cara Membaca Hasil

**Contoh output:**
```
Overall Metrics:
  Recall@5:          67.22%
  MRR:              0.5933
  Citation Correctness: 13.85%
  Faithfulness:     98.33%
  Unsupported Claim Rate: 0.00%
```

**Interpretasi:**
- **Recall@5 67.22%**: Dari 100 pertanyaan, 67 berhasil menemukan dokumen relevan di top-5
- **MRR 0.5933**: Rata-rata dokumen benar berada di rank 1.7 (1/0.5933)
- **Citation Correctness 13.85%**: Hanya 13.85% citation memiliki article yang benar
- **Faithfulness 98.33%**: 98.33% klaim dalam jawaban didukung oleh citation
- **Unsupported Claim Rate 0.00%**: Semua klaim memiliki citation

### Per-Category Analysis

Lihat breakdown per kategori untuk menemukan area yang perlu perbaikan:

```
pkwt                       R@5=100.00%  Cite=16.67%  Faith=100.00%
pengupahan                 R@5=85.42%   Cite=30.47%  Faith=100.00%
waktu_kerja                R@5=20.00%   Cite=2.50%   Faith=100.00%
```

- **pkwt**: Retrieval sempurna, tapi citation kurang akurat
- **waktu_kerja**: Retrieval perlu perbaikan

## Pipeline Evaluasi Lengkap

### 1. Persiapan

```bash
# Install dependencies
cd apps/api
pip install -r requirements.txt

# Validasi dataset
python -m pytest tests/test_evaluation.py -v
```

### 2. Run Evaluasi

```bash
cd evaluation

# 1. Retrieval metrics
python retrieval_metrics.py --top-k 5

# 2. Tuning reranker
python tune_reranker.py --top-k 5

# 3. Semantic evaluation
python semantic_eval.py --top-k 5
```

### 3. Analisis Hasil

```bash
# Lihat summary
cat retrieval_metrics_report.json | python -m json.tool | head -30

# Lihat per-category
cat retrieval_metrics_report.json | python -c "
import json, sys
data = json.load(sys.stdin)
for cat, info in data['per_category'].items():
    print(f\"{cat:25s} R@5={info['recall_at_k']:.2%}\")
"
```

## Troubleshooting

### Masalah Umum

| Masalah | Solusi |
|---|---|
| `ImportError: cannot import name` | Jalankan dari root directory: `python -m evaluation.retrieval_metrics` |
| `FileNotFoundError` | Pastikan `golden_questions.json` ada di `evaluation/` |
| `PermissionError` untuk temp | Hapus folder `C:\Users\ACER\AppData\Local\Temp\pytest-of-ACER` |

### Debug Mode

```bash
# Jalankan dengan verbose
python -c "
import json
from evaluation.retrieval_metrics import run_retrieval_evaluation
from pathlib import Path

report = run_retrieval_evaluation(Path('golden_questions.json'), top_k=5)
print(json.dumps(report['questions'][:3], indent=2))
"
```

## File Struktur

```
evaluation/
├── golden_questions.json          # Dataset evaluasi utama (source of truth)
├── golden_questions_backup.json   # Backup sebelum dedup (arsip)
├── retrieval_metrics.py           # Retrieval-only metrics (harness sintetik)
├── tune_reranker.py              # Reranker weight tuning (harness sintetik)
├── semantic_eval.py              # Semantic evaluation
├── *_report.json / pinecone_*.json / chunk_calibration_results.json
│                                  # Generated output (regenerable; kandidat .gitignore)
└── README.md                      # Dokumentasi ini
```

Script Pinecone (`tune_reranker_real.py`, `upsert_*.py`, `debug_cross_encoder.py`)
sudah dipensiunkan bersama pipeline Pinecone/BGE-M3 (2026-09).

## Referensi

- [PRD KerjaPedia AI](../docs/PRD_KerjaPedia_AI.md)
- [Retrieval Documentation](../docs/RETRIEVAL.md)
- [Evaluation Policy](../apps/api/app/services/evaluation/policy.py)
