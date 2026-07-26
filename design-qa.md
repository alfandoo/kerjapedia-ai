# Design QA — Landing Guest KerjaPedia

Final result: passed

---

# Design QA - Kerapian Thread Chat

Final result: passed

## Referensi dan Implementasi

- Source visual truth: `C:\Users\ACER\AppData\Local\Temp\codex-clipboard-3a957c0d-5779-474f-a639-fcdfe01210cf.png`
- Implementation screenshot: `C:\Users\ACER\AppData\Local\Temp\kerjapedia-chat-desktop.png`
- State: percakapan desktop setelah jawaban selesai dan drawer sumber tertutup.

## Fidelity Check

| Area | Result |
| --- | --- |
| Alignment bubble pengguna | Passed; tidak lagi terganggu timestamp yang mengambang |
| Jarak pesan pengguna ke jawaban | Passed; ritme vertikal lebih rapat dan konsisten |
| Header jawaban | Passed; avatar dan nama asisten membentuk satu kelompok |
| Isi dan lebar baca | Passed; tetap berada pada reading width yang terkontrol |
| Tombol sumber | Passed; dekat dengan jawaban tanpa membuat kartu baru |
| Action bar | Passed; rapat, konsisten, dan tetap memiliki target interaksi |

Tidak ada temuan P0, P1, atau P2 pada state yang diperiksa. Timestamp tetap tersedia
secara semantik tetapi disembunyikan secara visual agar tidak memecah alignment.

Final result: passed

---

# Design QA - Menu Profil Pengguna

Final result: passed

- Source visual truth: `C:\Users\ACER\AppData\Local\Temp\codex-clipboard-93b97983-305e-4816-9210-becfb9fbc73e.png`
- Implementation screenshot: `C:\Users\ACER\AppData\Local\Temp\kerjapedia-profile-menu.png`
- CSS viewport: 1280 x 720, device scale factor 1.
- State: pengguna login, menu profil terbuka.
- Focused comparison: popover 248 px di kanan atas dibandingkan dengan referensi 253 px.

## Fidelity Check

| Surface | Result |
| --- | --- |
| Typography | Passed; nama, role, dan item memakai hierarchy ringkas |
| Spacing dan layout | Passed; header, divider, baris menu, dan radius sesuai referensi |
| Warna | Passed; permukaan charcoal dengan teks putih dan aksen hijau |
| Ikon | Passed; ikon disesuaikan dengan fungsi KerjaPedia |
| Copy | Passed; fitur paket/personalisasi yang tidak tersedia tidak ditampilkan |
| Interaksi | Passed; focus awal, klik luar, Escape, navigasi, dan logout berfungsi |

Tidak ada temuan P0, P1, atau P2. Deviasi disengaja: menu memakai tujuan KerjaPedia yang benar-benar tersedia, bukan menyalin fitur paket ChatGPT. Playwright login dan logout lulus.

Final result: passed

---

# Design QA - Collapsed Sidebar Rail

Final result: passed

- Source visual truth: `C:\Users\ACER\AppData\Local\Temp\codex-clipboard-c4d5eef0-7d6c-44c6-b8ef-d696616e6530.png`
- Implementation screenshot: `C:\Users\ACER\AppData\Local\Temp\kerjapedia-sidebar-collapsed.png`
- Reference pixels: 66 x 626; implementation pixels: 1280 x 720.
- CSS viewport: 1280 x 720, device scale factor 1.
- State: guest desktop, sidebar collapsed.
- Focused comparison: rail selebar 64 px dibandingkan dengan referensi 66 px.

## Fidelity Check

| Surface | Result |
| --- | --- |
| Typography | Passed; rail tidak menampilkan teks |
| Spacing dan layout | Passed; ikon vertikal konsisten dan profil berada di bawah |
| Warna | Passed; rail true-white dengan divider abu-abu dingin |
| Asset dan ikon | Passed; ikon produk KerjaPedia menggantikan fitur ChatGPT yang tidak relevan |
| Copy | Passed; tidak ada copy tambahan |
| Interaksi | Passed; chat baru, pencarian, legal, profil, dan expand tetap berfungsi |

Tidak ada temuan P0, P1, atau P2. Deviasi yang disengaja: ikon legal KerjaPedia menggantikan ikon gambar pada referensi. Screenshot full-view memastikan rail tidak memotong composer atau disclaimer. Pengujian collapse dan persistence lulus.

Final result: passed

## Reference

- `C:\Users\ACER\AppData\Local\Temp\codex-clipboard-f6e59657-a86f-436b-b08c-ec7e52d4f58e.png`
- Target pattern: narrow left sidebar, minimal top bar with authentication CTAs, centered prompt and composer, legal note at the bottom.

## Rendered Evidence

- Desktop 1365×650: `C:\Users\ACER\AppData\Local\Temp\kerjapedia-guest-landing-desktop-final.png`
- Mobile 390×844: `C:\Users\ACER\AppData\Local\Temp\kerjapedia-guest-landing-mobile-final.png`

## Fidelity Ledger

| Area | Result |
| --- | --- |
| Desktop sidebar width and hierarchy | Passed |
| Top authentication actions | Passed |
| Centered heading and compact composer | Passed |
| Bottom legal notice | Passed |
| Mobile top bar and safe-area layout | Passed |
| KerjaPedia palette and identity | Passed |
| Guest-to-chat interaction | Passed |

Intentional deviations: KerjaPedia branding and legal navigation replace ChatGPT-specific features. Voice, Images, pricing, and cookie consent are omitted because they are outside the approved product scope.

---

# Design QA - Header Ikon Sidebar

Final result: passed

## Reference dan Implementasi

- Source visual truth: `C:\Users\ACER\AppData\Local\Temp\codex-clipboard-f8fcc157-83f7-49d4-845f-e56cce032fb6.png`
- Implementation screenshot: `C:\Users\ACER\AppData\Local\Temp\kerjapedia-sidebar-header.png`
- Reference pixels: 251 x 52; implementation pixels: 1280 x 720.
- CSS viewport: 1280 x 720, device scale factor 1.
- State: guest desktop dengan sidebar terbuka.
- Focused comparison: header sidebar pada tinggi 52 px; full-view screenshot dipakai untuk memeriksa konteks rail.

## Fidelity Check

| Surface | Result |
| --- | --- |
| Typography | Passed; header dibuat icon-only seperti referensi |
| Spacing dan layout | Passed; mark kiri dan dua kontrol kanan sejajar |
| Warna | Passed; monokrom pada permukaan sidebar KerjaPedia |
| Asset dan ikon | Passed; ikon legal KerjaPedia menggantikan merek ChatGPT secara sengaja |
| Copy | Passed; tidak ada copy tambahan pada header |
| Interaksi | Passed; pencarian membuka `/search`, panel dapat ditutup dan dibuka kembali |

Tidak ada temuan P0, P1, atau P2. Deviasi yang disengaja adalah penggunaan ikon timbangan KerjaPedia sebagai pengganti logo ChatGPT. Pengujian Playwright desktop collapse dan drawer mobile lulus; tidak ada framework overlay atau console error yang relevan.

Final result: passed
