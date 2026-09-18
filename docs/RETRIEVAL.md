# Retrieval and Ranking

Production memakai Upstash Vector HYBRID index (dense `open-ai/text-embedding-3-small`
+ sparse BM25, metric COSINE). Aplikasi mengirim raw query text; Upstash melakukan
dense/sparse embedding server-side, maksimum 100 kandidat per rewrite.

Filter Pasal serta tipe, nomor, dan tahun peraturan bersifat hard filter. Topik yang
hanya diduga dari sinonim Indonesia/Inggris menjadi boost. Sumber umum wajib current,
published, source-verified,
legal-reviewed, dan berstatus active/amended. Query historis eksplisit boleh mencari
versi lama yang tetap published dan verified.

Kandidat di-rerank memakai heuristic reranker internal, kemudian melalui policy
relasi hukum, diversity maksimum tiga chunk per dokumen, dan expansion pada Pasal/halaman
terdekat. Maksimum delapan konteks diberikan ke generator. Threshold refusal berasal
dari konfigurasi governance.

Engine artifact mempertahankan kontrak `RetrievalResponse` untuk unit test dan
development offline, tetapi dilarang saat `APP_ENV=production`.

> Historical note: sebelum migrasi 2026-09, retrieval memakai Pinecone
> (`dotproduct`) + BGE-M3 self-hosted dengan alpha 0.35/0.65 dan cross-encoder
> `bge-reranker-v2-m3` (maks 50 kandidat). Jalur itu sudah dipensiunkan.
