# Evaluasi ingestion: load sampai metadata

## Batas evaluasi

Runner `app.services.ingestion.evaluation.preembedding` menjalankan validasi file,
ekstraksi halaman, OCR selektif, cleaning, parsing struktur, chunking, dan enrichment
metadata. Runner tidak memanggil provider embedding, database aplikasi, Pinecone,
retrieval, generation, approval, atau aktivasi release.

Hasil ditulis terpisah dari build/release aktif:

- `storage/ingestion/preembedding/reports/corpus.json` dan `corpus.md`.
- `storage/ingestion/preembedding/reports/<document_id>.json` dan `.md`.
- `storage/ingestion/preembedding/artifacts/<document_id>/<build_id>/` berisi
  halaman asli/bersih, struktur, chunk, validasi sumber, dan manifest eksekusi.
- `storage/ingestion/preembedding/cache/` menyimpan ekstraksi dan OCR per halaman.

`PASS` berarti tidak ada temuan evaluator pada scope `through_metadata`, bukan
sertifikasi akurasi hukum, tabel, OCR, embedding, atau kesiapan publikasi.
`FAIL` berarti hasil memerlukan penanganan; proses evaluasi dokumen tetap selesai
dan artefaknya tersedia. Embedding/indexing ditandai `NOT_RUN`, bukan PASS.
Corpus menyajikan rasio embedding/index yang belum diukur sebagai `null`.

## Menjalankan ulang

Dari `apps/api`, dengan Python environment proyek dan Tesseract terpasang:

```powershell
$env:TESSDATA_PREFIX='F:\Alfando\Portofolio\KerjaPediaAI\storage\ingestion\runtime\tessdata'
.\.venv\Scripts\python.exe -m app.services.ingestion.evaluation.preembedding --all --ocr --ocr-page PP-49-2025:21 --ocr-page PERMENAKER-6-2016:7
```

`--document-id` dapat diulang untuk subset. `--ocr-page DOCUMENT_ID:PAGE` meminta
ekstraksi ulang halaman yang diketahui bermasalah, bukan mengubah teks secara
manual atau memaksa status. Permintaan ini dicatat di manifest dan fingerprint.
Untuk batch ini, PP-49-2025 halaman PDF 21 kehilangan suffix J pada text layer,
sedangkan PERMENAKER-6-2016 halaman 7 mengandung heading `Pasall0` pada text layer.

Data OCR Indonesia lokal berasal dari `tesseract-ocr/tessdata_fast`, commit
`87416418657359cb625c412a48b6e1d6d41c29bd`; SHA-256 `ind.traineddata`:
`69786901da87ab8766c1ea7fbb10b28f2110c14da3f6c8f2735df131fba95d88`.
Bahasa yang dipakai tersimpan pada flag halaman. Gunakan output/cache baru dengan
`--output-dir` jika engine/model OCR berubah: cache lama belum memiliki fingerprint
runtime OCR yang lengkap. Tidak ada model embedding yang dijalankan dalam batch ini.

## Perbaikan yang diterapkan

1. Ekstraksi menjaga raw text dan mengurutkan working text berdasarkan posisi
   PDF; inventaris halaman kosong/gagal tidak dibuang.
2. OCR Tesseract berjalan dalam subprocess dengan timeout, decoding UTF-8,
   dan diagnostik kegagalan. Halaman yang tetap bermasalah tetap FAIL.
3. Kualitas diperiksa setelah cleaning; perubahan bukti margin sesudah OCR juga
   diperiksa kembali. Setiap halaman dicoba paling banyak sekali per run.
4. Label legal dan ayat dilindungi dari penghapusan margin, termasuk `Pasal2`.
   Penjelasan pendek `Cukup jelas`/`Dihapus` tidak dianggap kehilangan spasi kata.
5. Parser membedakan rujukan Pasal/Lampiran dari heading, menerima Penjelasan
   dengan huruf berspasi, menjaga judul BAB multiline, serta mengidentifikasi
   catchword hanya dengan bukti heading identik di halaman berikutnya.
6. Daftar bernomor pada Lampiran tidak otomatis dianggap Ayat tanpa Pasal.
   Konteks amendemen eksplisit dicatat melalui `amendment_scope`, termasuk
   marker bertingkat seperti `N. Ketentuan Pasal ... diubah`, `Angka N` dalam
   Penjelasan, dan artefak OCR angka Pasal (`1O8` → `108`).
7. Chunker mempertahankan teks pembukaan/penjelasan/lampiran di luar Pasal,
   tidak menggandakan teks seluruh parent, dan tidak membuat chunk terpisah
   untuk heading-only yang sudah ada dalam struktur. Batas token tidak dinaikkan.
8. Evaluator tidak menuntut kepemilikan Pasal untuk chunk yang hanya mengutip
   Pasal lain. Dua Pasal sumber yang berulang secara berurutan dan identik
   ditandai `source_duplicate_of`, tetap dipertahankan di struktur/artifact,
   dan hanya occurrence kanonis yang menjadi chunk. Duplikasi sungguhan,
   provenance invalid, dan batas token tetap diperiksa; tidak ada whitelist
   dokumen atau override PASS.

Versi pipeline: `kerjapedia-ingestion-v15-amendment-provenance`; parser `v10`;
chunker `v6`.
Perubahan versi mencegah penggunaan kembali build lama sebagai hasil baru.
Laporan juga mencatat fingerprint kode ingestion. Kompatibilitas legacy tetap
melalui adapter; field `amendment_scope` merupakan tambahan nullable.

## Penyelesaian kasus sumber yang berulang

- **UU-6-2023**: parser sekarang memisahkan scope Pasal pengubah, Pasal target,
  marker amendemen yang berada pada parent Bagian/Paragraf, dan blok `Angka` di
  Penjelasan. Semua occurrence tetap memiliki node dan rentang halaman; evaluasi
  versi `v15` menghasilkan `PASS` tanpa collision Pasal, chunk duplikat, maupun
  provenance metadata yang hilang.
- **UU-2-2004**: inspeksi halaman PDF 97 (halaman cetak 25) mengonfirmasi Pasal
  80 dan 81 memang dicetak ulang. Kedua occurrence kedua disimpan sebagai node
  dengan `source_duplicate_of` yang menunjuk occurrence pertama dan provenance
  halaman asalnya. Chunker mengeluarkan hanya occurrence kanonis sehingga indeks
  tidak bias, tanpa menghapus atau menyamarkan bukti sumber.

PDF pembanding yang diinspeksi tanpa diubah:

- `dataset/Hubungan industrial dan serikat pekerja/UU Nomor 2 Tahun 2004.pdf`, halaman 97.
- `dataset/Pengupahan dan THR/PP Nomor 49 Tahun 2025.pdf`, halaman 21.
- `dataset/Dasar ketenagakerjaan, PKWT, PHK, dan alih daya/PP Nomor 35 Tahun 2021.pdf`, halaman 5.

## Verifikasi dan keterbatasan

Tes regresi mencakup urutan baca, raw text, OCR failure, heading legal,
catchword, referensi Lampiran, amendemen, validasi metadata, cakupan evaluasi,
cache, kompatibilitas pipeline, serta idempotency. Jalankan:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_preembedding_regressions.py tests/test_ingestion_legal_structure.py tests/test_ingestion_evaluation.py tests/test_ingestion_structure_chunking.py tests/test_ingestion_cleaning.py tests/test_ingestion_document_model.py tests/test_ingestion_metadata.py tests/test_ingestion_pipeline.py tests/test_ingestion_idempotency.py tests/test_ingestion_job_payload.py tests/test_ingestion_retry.py -q
```

Penghitungan token batch ini memakai `RegexTokenizer` offline, bukan tokenizer
model BGE. Batas tokenizer BGE dan teks input embedding tetap harus divalidasi
pada tahap embedding nanti. Rekonstruksi tabel tidak dijalankan pada runner ini;
manifest menandainya `not_run`. Provenance halaman berupa rentang halaman,
bukan jaminan pemetaan karakter/bounding-box setiap kalimat. OCR dapat menghasilkan
karakter yang tampak valid tetapi salah; pemeriksaan otomatis tidak menggantikan
review kutipan legal. Snapshot laporan terakhir dapat diperbarui saat rerun;
runner ini bukan mekanisme publikasi immutable production.
