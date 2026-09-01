# Answer Generation and Citation

Prompt aktif adalah `kerjapedia-grounded-answer-v5`. Generator menerima pertanyaan asli
dan konteks retrieval terpilih, lalu meminta JSON berisi `answer`,
`cited_chunk_ids`, serta daftar klaim dan chunk pendukungnya.

Memory menyimpan pertanyaan asli, query retrieval kontekstual, descriptor citation,
dan bahasa pertanyaan sebagai nilai terpisah. Label bahasa Indonesia tidak disisipkan
ke query follow-up Inggris atau ke pertanyaan yang diterima generator.

Citation hanya dibuat dari chunk yang benar-benar diretrieve dan dipilih model. Setiap
citation mencakup document/version ID, status hukum, Pasal/Ayat, halaman, kutipan, URL,
dan score. Setiap klaim diverifikasi terhadap kutipan dengan verifier multilingual
terpisah. Coverage antara isi jawaban dan structured claims juga harus melewati gate
agar klaim yang dihilangkan dari daftar claims tidak lolos verifikasi. Confidence
dihitung dari retrieval score, support score, dan eligibility sumber; nilai confidence
dari model diabaikan.

Jawaban diregenerasi satu kali bila klaim tidak didukung atau bahasa output tidak sesuai
pertanyaan. Production bersifat fail-closed: kegagalan Groq, JSON/citation validation,
verifier, atau output language menghasilkan error sementara, bukan jawaban fallback.
Fallback lokal hanya tersedia untuk development/test.

Response tetap kompatibel dan menambahkan field opsional `trace_id`, `answer_status`,
`answer_version`, `claims`, serta `document_version` pada citation. Public debug hanya
memuat trace ID dan prompt version; prompt serta trace internal tidak dikirim ke browser.
Versi pipeline jawaban terverifikasi saat ini adalah `grounded-verified-answer-v3`.
