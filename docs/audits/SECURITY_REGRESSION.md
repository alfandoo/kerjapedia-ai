# Regresi keamanan — 5 September 2026

Status: pemeriksaan keamanan terarah lulus; suite UI umum belum seluruhnya lulus. Belum commit, push, atau deployment.

## Hasil validasi

| Pemeriksaan | Hasil |
| --- | --- |
| API: security, upload, publikasi dokumen, trusted proxy, logout, kepemilikan feedback, batas upload, system, health | 119 lulus |
| Frontend: sesi HttpOnly, logout, feedback, security headers, profil dalam memori | 33 lulus |
| Browser login, pemulihan profil, refresh, streaming, CSRF, logout | Lulus |
| Browser CSP pada halaman utama, login admin, dashboard, pencarian, privasi | Lulus |
| Skrip tanpa nonce yang disisipkan ke HTML | Diblokir CSP |
| Build production | Lulus |
| ESLint | 0 error; 5 warning yang masih perlu dirapikan |
| git diff --check | Lulus |

Tes browser memakai frontend production sementara dan API mock lokal. Login menguji formulir nyata, cookie HttpOnly/Secure, penghapusan token lama dari storage, refresh cookie, dan logout dari menu admin. Pemeriksaan nonce berlaku pada skrip dalam respons HTML; chunk dinamis tepercaya tetap diizinkan oleh strict-dynamic.

## Batasan regresi UI umum

Percobaan suite Playwright lama dihentikan otomatis setelah batas tiga kegagalan. Artefaknya menunjukkan assertion usang pada `.desktop-sidebar`, `.editorial-answer-content > p`, serta teks `Simpan percakapan Anda`. Snapshot logout sudah menunjukkan tampilan tamu dengan judul baru `Dapatkan jawaban yang sesuai untuk Anda`.

Fixture sesi telah mengikuti endpoint cookie, locale browser dikunci ke Indonesia, dan sebagian selector awal diperbarui. Selector UI lama lainnya belum seluruhnya diselaraskan. Karena eksekusi berhenti lebih awal, tes yang tersisa belum tervalidasi; hasil ini bukan bukti bahwa seluruh alur aplikasi bebas regresi.

## Reproduksi lokal

Dari `apps/api`:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_security.py tests/test_uploads.py tests/test_public_document_access.py tests/test_proxy_trust.py tests/test_logout_security.py tests/test_feedback_ownership.py tests/test_upload_size_security.py tests/test_system_security.py tests/test_health.py --noconftest -p no:cacheprovider -q --tb=short
```

Gunakan interpreter virtualenv yang tersedia; `--noconftest` menghindari fixture integrasi yang menulis manifest dataset.

Dari `apps/web`, setelah menyiapkan build production `.next-security-headers`:

```powershell
node --test tests/httponly-session.test.cjs tests/logout-security.test.cjs tests/feedback-security.test.cjs tests/security-headers.test.cjs tests/session-memory.test.cjs
node tests/httponly-session-browser.cjs
node tests/security-headers-browser.cjs
npm run lint
```

## Cakupan yang belum dibuktikan

- Kebijakan RLS/storage dan konfigurasi Supabase/Pinecone nyata tidak diubah atau diuji.
- Tes integrasi database nyata dan uji beban tidak dijalankan.
- Audit advisory dependency tidak diperbarui lagi dalam tahap regresi ini.
- Rate limiter API masih melihat IP BFF bersama; pemisahan kuota pengguna memerlukan pekerjaan lanjutan.
- Token akses Supabase yang sudah diterbitkan dapat tetap valid sampai kedaluwarsa setelah logout; pencabutan sesi bukan denylist token akses.

Sebelum menyatakan siap production: selesaikan regresi UI umum, verifikasi konfigurasi deployment/cookie/origin dan kontrol cloud, lalu tinjau sisa risiko yang dicatat di atas.


## Pembaruan penyimpanan setelah review

Implementasi terbaru tidak mengakses localStorage/sessionStorage, termasuk penghapusan token lama. Penyebutan migrasi/penghapusan storage di hasil awal di atas merupakan catatan historis. Tema, bahasa, dan sidebar memakai cookie; pin memakai IndexedDB per akun; ID tamu memakai cookie HttpOnly yang diteruskan oleh BFF. Header ID tamu dari browser diabaikan. Data Web Storage lama tidak dimigrasikan maupun dihapus otomatis. Tes browser terbaru memblokir kedua Web Storage saat memeriksa preferensi, pin, dan sidebar.
