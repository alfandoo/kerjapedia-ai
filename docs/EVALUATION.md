# RAG Evaluation

`evaluation/golden_questions.json` berisi 150 seed case nonproduksi. Seed ini tetap
`needs_human_review` dan tidak boleh dipakai untuk mempromosikan release.

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

Evaluasi release dilakukan melalui `POST /evaluation/runs` dengan `dataset_id` dan
`release_id`. Jalur ini memakai namespace Pinecone release, BGE-M3, reranker,
generator Groq, dan claim verifier fail-closed. `evaluation_run_id` tersebut kemudian
dikirim saat transisi `validate`; run dari artifact atau release lain ditolak.

CI menyediakan PostgreSQL test terisolasi, menjalankan migration upgrade–downgrade–
upgrade, lalu seluruh unit/integration/provider-contract/evaluation regression test.
