# RAG Evaluation

`evaluation/golden_questions.json` berisi 130 seed case nonproduksi. Seed ini tetap
`needs_human_review` dan tidak boleh dipakai untuk klaim produksi.

## Dataset produksi

Release production membutuhkan minimal 300 pertanyaan yang seluruhnya memiliki
`status=verified`, reviewer nyata pada `verified_by`, serta split `development` dan
`test`. Kasus wajib mencakup follow-up, typo, bilingual, perpindahan topik, aturan
historis, hard negative, pertanyaan kompleks, refusal, dan prompt injection.
ID dan teks pertanyaan wajib unik; validasi ini dijalankan saat create, evaluation,
dan promotion untuk melindungi dataset legacy maupun perubahan langsung di database.
Scenario tags wajib mencakup `follow_up`, `typo`, `bilingual`, `topic_switch`,
`historical`, `complex`, `hard_negative`, dan `prompt_injection` sebelum release dapat
dievaluasi atau dipromosikan.
Dataset baru selalu dimulai sebagai `needs_human_review`; status terverifikasi hanya
dapat diberikan melalui endpoint review oleh role `legal_reviewer` dan disimpan dalam
audit event append-only per pertanyaan. Gate selalu memakai event review terbaru.

Development split hanya dipakai untuk kalibrasi threshold refusal. Semua quality gate
promosi dihitung pada held-out test split agar tidak terjadi evaluation leakage.

## Quality gate

- Recall@5 ≥ 0.90 dan Recall@10 ≥ 0.95.
- NDCG@10 dan MRR dilaporkan secara agregat serta per topik.
- Citation precision ≥ 0.95.
- Unsupported legal claim ≤ 1%.
- Unpublished/stale source retrieval = 0.
- Refusal recall ≥ 0.95 dan precision ≥ 0.90.
- Ketepatan bahasa ≥ 0.99.

Faithfulness utama menggunakan hasil claim verification. Ragas Faithfulness dijalankan
sebagai metrik sekunder untuk membantu diagnosis, tetapi tidak menggantikan verified
held-out gate atau menentukan promosi release sendirian.

## Menjalankan

Eksperimen artifact untuk development tetap tersedia melalui CLI:

```powershell
cd apps/api
.venv\Scripts\python -m app.services.evaluation.cli `
  --dataset ../../evaluation/golden_questions.json `
  --storage-root ../../storage/ingestion `
  --output ../../storage/evaluation/report.json `
  --top-k 10
```

Evaluasi backend live dilakukan via `scripts/eval_upstash_sample.py` (sampel
deterministik memakai fungsi metrik repo; report ke `storage/evaluation/`).
Evaluasi artifact-mode via `POST /evaluation/runs` tanpa `release_id`.
Jalur evaluasi berbasis release/namespace Pinecone sudah dipensiunkan
(2026-09) bersama pipeline Pinecone/BGE-M3.

CI menyediakan PostgreSQL test terisolasi, menjalankan migration upgrade–downgrade–
upgrade, lalu seluruh unit/integration/provider-contract/evaluation regression test.
