# Dataset KerjaPedia AI

Folder ini menyimpan dokumen regulasi sumber untuk MVP KerjaPedia AI. Dokumen dikelompokkan berdasarkan topik agar mudah diaudit sebelum masuk pipeline ingestion.

## Struktur

- `Dasar ketenagakerjaan, PKWT, PHK, dan alih daya/`
- `Pengupahan dan THR/`
- `BPJS dan jaminan sosial ketenagakerjaan/`
- `Keselamatan dan kesehatan kerja/`
- `Hubungan industrial dan serikat pekerja/`

## Metadata

Metadata awal tersedia di `metadata.json`. Setiap entri dokumen berisi:

- `document_id`
- judul, nomor, tahun, jenis regulasi, dan penerbit
- topik
- path file lokal
- ukuran file dan SHA-256 checksum
- source search URL ke Database Peraturan JDIH BPK
- status verifikasi

Nilai `legal_status: "needs_verification"` berarti status berlaku/diubah/dicabut belum boleh dipakai sebagai klaim final. Sebelum production ingestion, admin harus membuka detail dokumen resmi, mengisi detail source URL, dan memverifikasi status hukum serta relasi perubahan.

## Relasi Dokumen

Relasi awal disimpan dalam properti `relationships` di `metadata.json`. Relasi dengan `confidence: "low"` atau `confidence: "medium"` wajib diverifikasi manual sebelum digunakan untuk status-aware retrieval.

## Aturan Update

Saat menambah PDF baru:

1. Simpan file pada folder topik paling sesuai.
2. Tambahkan entri baru di `metadata.json`.
3. Isi checksum SHA-256 file.
4. Tambahkan source URL resmi.
5. Tandai `verification_status` sampai detail dokumen selesai dicek.
