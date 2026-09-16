# Perbandingan Evaluasi Retrieval vs Re-ranking

## Ringkasan Eksekutif

| Aspek | Retrieval (Synthetic) | Retrieval (Pinecone) | Re-ranking (Synthetic) | Re-ranking (Real) |
|-------|----------------------|---------------------|----------------------|-------------------|
| **Status** | ✅ Selesai | ✅ Selesai | ⚠️ Invalid | 🔜 Belum jalan |
| **Data Source** | HashEmbeddingProvider | Pinecone Production | HashEmbeddingProvider | Pinecone Production |
| **Recall@5** | 40.83% | **89.02%** | 40.83% (identik) | - |
| **MRR** | 0.3114 | **0.7581** | 0.3114 (identik) | - |
| **nDCG@10** | 0.3102 | **0.7588** | 0.3102 (identik) | - |
| **Hit Rate** | - | **96.34%** | - | - |
| **Precision@5** | - | **42.07%** | - | - |

---

## 1. Retrieval Evaluation

### 1.1 Synthetic Data (retrieval_metrics_report.json)
- **Data:** `HashEmbeddingProvider` — synthetic embeddings
- **Hasil:** Recall@5=40.83%, MRR=0.3114
- **Masalah:** Tidak representatif — semua dokumen punya struktur sama

### 1.2 Real Pinecone Data (pinecone_full_eval.json)
- **Data:** Real embeddings dari BGE-M3 di Pinecone
- **Namespace:** `staging-bge-m3-3a779f061d1932ba8603`
- **Questions:** 130 total, 82 answerable, 6 refusal, 42 error (rate limit)

#### Hasil Per Kategori

| Kategori | Total | Recall@5 | Precision@5 | Hit Rate | MRR | nDCG@10 |
|----------|-------|----------|-------------|----------|-----|---------|
| alih_daya | 10 | 90.00% | 26.67% | 90.00% | 0.7167 | 0.7631 |
| bpjs_jkp | 16 | 78.12% | 44.79% | 93.75% | 0.6667 | 0.6523 |
| hubungan_industrial | 12 | **100.00%** | 44.44% | **100.00%** | 0.8333 | **0.8770** |
| k3 | 12 | 79.17% | 40.97% | 91.67% | 0.5694 | 0.5791 |
| pengupahan | 16 | - | - | - | - | - |
| phk_pesangon | 20 | **90.00%** | 50.42% | **100.00%** | **1.0000** | **0.9026** |
| pkwt | 12 | **100.00%** | 36.11% | **100.00%** | 0.6250 | 0.7192 |
| refusal | 10 | - | - | - | - | - |
| thr | 12 | - | - | - | - | - |
| waktu_kerja | 10 | - | - | - | - | - |

#### Kategori Terbaik
1. **phk_pesangon** — MRR=1.0, nDCG=0.9026
2. **hubungan_industrial** — Recall=100%, nDCG=0.8770
3. **pkwt** — Recall=100%, Hit Rate=100%

#### Kategori Bermasalah
- **pengupahan, thr, waktu_kerja** — Tidak ada data (error/rate limit)
- **bpjs_jkp** — Recall hanya 78.12%

---

## 2. Re-ranking Evaluation

### 2.1 Synthetic Data (reranker_tuning_report.json) — INVALID
- **Data:** `HashEmbeddingProvider` — synthetic embeddings
- **Masalah:** Semua konfigurasi menghasilkan **metrics sama**:
  - Recall@5 = 40.83% (identik untuk semua)
  - MRR = 0.3114 (identik untuk semua)
  - nDCG@10 = 0.3102 (identik untuk semua)

**Penyebab:** Synthetic documents punya struktur sama → reranker weights tidak ada efek

### 2.2 Real Pinecone Data (reranker_tuning_real_report.json) — BELUM JALAN
- **Script:** `tune_reranker_real.py` sudah dibuat
- **Status:** Belum bisa jalan karena Pinecone rate limit (429)
- **Fallback:** Menunggu rate limit reset atau upgrade plan

---

## 3. Gap Analysis

### 3.1 Masalah Utama

| Masalah | Dampak | Solusi |
|---------|--------|--------|
| **Synthetic data invalid** | Reranker evaluation tidak berguna | Gunakan `tune_reranker_real.py` |
| **Pinecone rate limit** | 42 errors dari 130 questions | Upgrade plan atau tunggu reset |
| **Missing categories** | pengupahan, thr, waktu_kerja tidak terukur | Fix data atau skip kategori |
| **Cross-encoder belum diuji** | Tidak tahu apakah cross-encoder lebih baik | Tambahkan evaluasi cross-encoder |

### 3.2 Metrics Gap

| Metric | Synthetic | Real Pinecone | Gap | Target |
|--------|-----------|---------------|-----|--------|
| Recall@5 | 40.83% | 89.02% | **+48.19%** | >90% |
| MRR | 0.3114 | 0.7581 | **+0.4467** | >0.80 |
| nDCG@10 | 0.3102 | 0.7588 | **+0.4486** | >0.80 |
| Hit Rate | - | 96.34% | - | >95% ✅ |
| Precision@5 | - | 42.07% | - | >50% |

---

## 4. Rekomendasi

### 4.1 Prioritas Tinggi
1. **Jalankan `tune_reranker_real.py`** dengan Pinecone production
2. **Tunggu rate limit reset** atau upgrade Pinecone plan
3. **Evaluate cross-encoder** vs heuristic reranking

### 4.2 Prioritas Sedang
4. **Fix missing categories** — pengupahan, thr, waktu_kerja
5. **Tambahkan latency benchmark** — bandingkan synthetic vs real
6. **Evaluasi MMR lambda** dengan real data

### 4.3 Prioritas Rendah
7. **Update baseline report** dengan real metrics
8. **Dokumentasikan** best practices untuk evaluation

---

## 5. Command untuk Evaluasi Lanjutan

```bash
# 1. Jalankan real reranker evaluation (setelah rate limit reset)
cd F:\Alfando\Portofolio\KerjaPediaAI
python evaluation/tune_reranker_real.py --top-k 5 --delay 0.3

# 2. Cek hasil
cat evaluation/reranker_tuning_real_report.json

# 3. Bandingkan dengan baseline
python -c "
import json
with open('evaluation/pinecone_full_eval.json') as f:
    baseline = json.load(f)
with open('evaluation/reranker_tuning_real_report.json') as f:
    rerank = json.load(f)
print('Baseline Recall@5:', baseline['overall']['recall_at_5'])
print('Best Reranker Recall@5:', rerank['weight_sweep'][0]['recall_at_5'])
"
```

---

## 6. Kesimpulan

### Retrieval Evaluation
- ✅ **Solid baseline** dengan real Pinecone data
- ✅ **Recall@5 = 89.02%** — sudah bagus
- ⚠️ **42 errors** karena rate limit
- ⚠️ **3 kategori missing** — perlu perbaikan

### Re-ranking Evaluation
- ❌ **Synthetic evaluation invalid** — semua metrics identik
- 🔜 **Real evaluation script ready** — butuh Pinecone access
- ⏳ **Menunggu rate limit reset** untuk menjalankan

### Selanjutnya
1. Tunggu Pinecone rate limit reset (biasanya 24 jam)
2. Jalankan `tune_reranker_real.py`
3. Bandingkan hasil dengan baseline
4. Update config jika ada improvement

---

*Report generated: 2026-09-15*
*Data sources: pinecone_full_eval.json, retrieval_metrics_report.json, reranker_tuning_report.json*
