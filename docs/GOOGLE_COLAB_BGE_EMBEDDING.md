# BGE-M3 di Google Colab

> ARCHIVED 2026-09: BGE-M3/Pinecone dipensiunkan. Produksi memakai Upstash
> Vector HYBRID (dense text-embedding-3-small + BM25, server-side). Dokumen ini
> dipertahankan sebagai arsip historis, bukan panduan produksi.

Dokumen ini menghasilkan embedding dari artifact ingestion yang telah lulus
validasi. Proses ini tidak mengubah database, Pinecone, retrieval, atau file
`chunks.jsonl` sumber.

## 1. Pilih GPU

Di Colab, pilih **Runtime > Change runtime type > T4 GPU** (atau GPU yang
tersedia), kemudian unggah dua file berikut dari repository:

- `storage/ingestion/preembedding/exports/chunks.jsonl`
- `scripts/colab_embed_bge_m3.py`

## 2. Instal dependensi

```python
!pip install -q FlagEmbedding==1.4.2 huggingface-hub
```

## 3. Jalankan embedding

```python
!python colab_embed_bge_m3.py \
  --input chunks.jsonl \
  --output bge_m3_embeddings.jsonl \
  --manifest bge_m3_embedding_manifest.json \
  --failures bge_m3_embedding_failures.json \
  --batch-size 16 \
  --max-retries 3
```

Model dipin ke `BAAI/bge-m3` revision
`5617a9f61b028005a4858fdac845db406aefb181` dan setiap dense vector harus
memiliki 1.024 dimensi. BGE-M3 juga menghasilkan sparse lexical weights agar
artifact tetap kompatibel dengan kebutuhan hybrid indexing di tahap berikutnya.

Jika GPU kehabisan memori, jalankan ulang dengan `--batch-size 8`. Output
bersifat resumable: baris yang sudah lengkap untuk kombinasi `chunk_id` dan
`content_hash` yang sama tidak dibuat ulang. Jangan gunakan output file yang
sama untuk `chunks.jsonl` dari build lain.

## 4. Verifikasi hasil dan unduh

Proses berhasil hanya jika `bge_m3_embedding_manifest.json` berisi `failed: 0`.
Jika ada kegagalan, skrip berhenti dengan error setelah menulis detailnya ke
`bge_m3_embedding_failures.json`; tidak ada chunk yang diabaikan diam-diam.

```python
import json
from google.colab import files

manifest = json.load(open("bge_m3_embedding_manifest.json", encoding="utf-8"))
assert manifest["failed"] == 0, manifest
assert manifest["input_chunks"] == (
    manifest["previously_completed"] + manifest["embedded_this_run"]
), manifest
files.download("bge_m3_embeddings.jsonl")
files.download("bge_m3_embedding_manifest.json")
```

Simpan ketiga artifact bersama-sama ketika mengembalikan hasil ke project:
`chunks.jsonl`, `bge_m3_embeddings.jsonl`, dan manifest. File vector tidak
mengulang isi/provenance lengkap chunk; penggabungan nantinya dilakukan secara
deterministik melalui `chunk_id` dan `content_hash`.
