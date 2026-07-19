# Golden Evaluation Dataset

`golden_questions.json` adalah dataset seed evaluasi RAG berisi 150 pertanyaan.
Komposisinya mengikuti PRD: PKWT 15, PHK/pesangon 25, alih daya 10, waktu kerja
10, pengupahan 20, THR 15, BPJS/JKP 20, K3 15, hubungan industrial 15, dan
refusal 5.

Semua item awal berstatus `needs_human_review`. Reviewer hukum harus memeriksa
pertanyaan, jawaban ideal, `expected_document_ids`, dan `expected_articles`
sebelum dataset dianggap golden untuk rilis. Jangan menghapus kasus hard
negative hanya karena skornya rendah; kasus tersebut melindungi sistem dari
kekeliruan istilah yang konteksnya berdekatan.

Regenerasi dataset dengan:

```powershell
apps\api\.venv\Scripts\python scripts\generate_evaluation_dataset.py
```

Panduan metrik dan eksperimen tersedia di `docs/EVALUATION.md`.
