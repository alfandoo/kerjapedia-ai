# Retrieval and Ranking

Production memakai true hybrid Pinecone pada index `dotproduct`. Dense dan sparse
BGE-M3 dikirim dalam satu request, maksimum 100 kandidat. Query dengan referensi hukum
eksplisit memakai alpha 0.35; query umum memakai 0.65.

Filter Pasal serta tipe, nomor, dan tahun peraturan bersifat hard filter. Topik yang
hanya diduga dari sinonim Indonesia/Inggris menjadi boost. Sumber umum wajib current,
published, source-verified,
legal-reviewed, dan berstatus active/amended. Query historis eksplisit boleh mencari
versi lama yang tetap published dan verified.

Maksimum 50 kandidat direrank memakai `bge-reranker-v2-m3`, kemudian melalui policy
relasi hukum, diversity maksimum tiga chunk per dokumen, dan expansion pada Pasal/halaman
terdekat. Maksimum delapan konteks diberikan ke generator. Threshold refusal dibaca dari
active release yang telah dikalibrasi.

Engine artifact mempertahankan kontrak `RetrievalResponse` untuk unit test dan
development offline, tetapi dilarang saat `APP_ENV=production`.
