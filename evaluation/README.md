# Golden Evaluation Dataset

`golden_questions.json` adalah dataset seed evaluasi RAG berisi 300 pertanyaan
(skema 1.1.0). Komposisinya mengikuti PRD dengan skala dua kali lipat: PKWT 30,
PHK/pesangon 50, alih daya 20, waktu kerja 20, pengupahan 40, THR 30, BPJS/JKP 40,
K3 30, hubungan industrial 30, dan refusal 10.

Semua item awal berstatus `needs_human_review`. Reviewer hukum harus memeriksa
pertanyaan, jawaban ideal, `expected_document_ids`, dan `expected_articles`
sebelum dataset dianggap golden untuk rilis. Jangan menghapus kasus hard
negative hanya karena skornya rendah; kasus tersebut melindungi sistem dari
kekeliruan istilah yang konteksnya berdekatan.

Setiap pertanyaan membawa `split` (`development` 203 / `test` 97, stratifikasi
per kategori) dan `scenario_tags` yang mencakup delapan skenario rilis
(`follow_up`, `typo`, `bilingual`, `topic_switch`, `historical`, `complex`,
`hard_negative`, `prompt_injection`). Daftar 150 pertanyaan lama dipertahankan
verbatim di dalam 300 pertanyaan baru agar baseline historis tetap sebanding.

Regenerasi dataset dengan:

```powershell
apps\api\.venv\Scripts\python scripts\generate_evaluation_dataset.py
```

Panduan metrik dan eksperimen tersedia di `docs/EVALUATION.md`.
