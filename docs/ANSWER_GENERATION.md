# Answer Generation and Citation

Task 6 menambahkan lapisan jawaban setelah retrieval. Implementasi mendukung mode
offline-first dan mode Groq. Mode lokal membuat jawaban terstruktur dari chunk retrieval
tanpa memanggil LLM eksternal. Mode industri mengirim prompt dan konteks retrieval ke
Groq, lalu memvalidasi JSON dan citation sebelum response dikirim ke frontend.

## Komponen

- `apps/api/app/services/answering/prompts.py`: prompt sistem dan template user
  berversi `kerjapedia-grounded-answer-v1`.
- `apps/api/app/services/answering/generator.py`: orchestration refusal,
  clarification, confidence, disclaimer, dan answer composition.
- `apps/api/app/services/answering/groq_generator.py`: Groq chat completion,
  JSON parsing, citation validation, timeout/retry config, dan fallback aman.
- `apps/api/app/services/answering/citations.py`: formatter citation dan related
  documents.
- `apps/api/app/services/answering/schemas.py`: kontrak response untuk frontend.
- `apps/api/app/services/answering/cli.py`: CLI lokal untuk smoke test.

## Output Response

Response utama mengikuti kontrak berikut:

```json
{
  "answer": "Jawaban berbasis konteks.",
  "citations": [],
  "confidence": 0.74,
  "related_documents": [],
  "refusal_reason": null,
  "clarification_question": null,
  "disclaimer": "KerjaPedia AI bukan pengganti ...",
  "prompt_version_id": "kerjapedia-grounded-answer-v1"
}
```

Setiap citation memuat `document_id`, judul dokumen, pasal/ayat, halaman, kutipan
pendukung, status hukum, URL sumber, serta skor retrieval/rerank untuk debugging admin.

## Guardrail

Service akan menolak menjawab ketika retrieval menandai konteks tidak cukup. Service
akan meminta klarifikasi ketika pertanyaan terlalu umum, misalnya `Hak saya apa?`, karena
belum jelas apakah topiknya PKWT, PHK, THR, serikat pekerja, atau isu lain.

Semua jawaban selalu menyertakan disclaimer bahwa KerjaPedia AI bukan pengganti advokat,
konsultan hukum, mediator hubungan industrial, atau instansi pemerintah.

## Menjalankan Lokal

Jalankan dari `apps/api` setelah ingestion artifact tersedia:

```bash
.venv\Scripts\python -m app.services.answering.cli "Apakah pekerja PKWT memperoleh kompensasi?"
```

Untuk saat ini kualitas jawaban mengikuti kualitas retrieval dan artifact lokal. Ketika
Groq diaktifkan, gunakan:

```bash
.venv\Scripts\python -m app.services.answering.cli "Apakah pekerja PKWT memperoleh kompensasi?" --vector-store pinecone --llm-provider groq
```

Jika Groq gagal mengembalikan JSON valid atau mencoba mengutip chunk yang tidak
diretrieve, service memakai fallback lokal berbasis citation yang sudah aman.
Pada respons Groq yang valid, citation dan related document hanya dibentuk dari
`cited_chunk_ids` yang benar-benar dipilih model, bukan dari seluruh kandidat
retrieval.
