import { AlertTriangle, CheckCircle2, FileText } from "lucide-react";

import { LegalLayout } from "../legal-layout";

const verifications = [
  "Buka sumber resmi yang ditampilkan bersama jawaban.",
  "Periksa nomor, tahun, status berlaku, dan perubahan regulasi.",
  "Pastikan pasal yang dirujuk sesuai dengan fakta dan konteks kasus.",
];

export default function DisclaimerPage() {
  return (
    <LegalLayout>
      <header className="border-b border-border pb-8">
        <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-javanese">
          Pemberitahuan penting
        </p>
        <h1 className="max-w-[760px] font-display text-[clamp(34px,5vw,54px)] font-medium leading-[1.08] tracking-[-0.035em] text-javanese-deep">
          Gunakan sebagai panduan, bukan keputusan hukum akhir
        </h1>
        <p className="mt-5 max-w-[720px] text-[15px] leading-7 text-muted-text">
          KerjaPedia AI membantu Anda memahami regulasi ketenagakerjaan Indonesia berdasarkan
          dokumen yang tersedia. Layanan ini bukan pengganti nasihat dari advokat, konsultan hukum,
          mediator hubungan industrial, atau instansi pemerintah.
        </p>
        <div className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-[11px] text-muted-text">
          <span>Versi 1.0</span>
          <span>Terakhir diperbarui: 4 September 2026</span>
        </div>
      </header>

      <aside className="my-8 flex items-start gap-3 rounded-xl border border-[#bfe3c9] bg-[#f0f8f2] px-4 py-4 text-sm leading-6 text-javanese-deep">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-javanese" />
        <p>
          Jawaban AI dapat tidak lengkap, keliru, atau belum mencerminkan perubahan regulasi
          terbaru. Selalu buka sumber resmi dan periksa status hukum sebelum mengambil keputusan.
        </p>
      </aside>

      <div className="grid gap-10 text-[15px] leading-7 text-foreground">
        <section>
          <h2 className="mb-3 font-display text-2xl font-medium text-javanese-deep">
            Tentang layanan ini
          </h2>
          <p>
            KerjaPedia AI adalah alat bantu untuk menemukan dan memahami informasi dari dokumen
            regulasi ketenagakerjaan. Jawaban dibuat berdasarkan sumber yang berhasil ditemukan oleh
            sistem dan dapat disertai kutipan untuk membantu pemeriksaan.
          </p>
        </section>

        <section>
          <h2 className="mb-3 font-display text-2xl font-medium text-javanese-deep">
            Batasan jawaban AI
          </h2>
          <p>
            Sistem dapat salah memahami pertanyaan, melewatkan dokumen yang relevan, atau menyusun
            jawaban yang tidak sesuai dengan konteks kasus Anda. Jawaban bukan opini hukum,
            keputusan administratif, maupun jaminan atas hasil suatu perkara.
          </p>
        </section>

        <section>
          <h2 className="mb-3 font-display text-2xl font-medium text-javanese-deep">
            Periksa sumber sebelum bertindak
          </h2>
          <div className="grid gap-3">
            {verifications.map((item) => (
              <div
                key={item}
                className="flex items-start gap-3 rounded-lg border border-border bg-surface-soft px-4 py-3"
              >
                <CheckCircle2 className="mt-1 size-4 shrink-0 text-javanese" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="mb-3 font-display text-2xl font-medium text-javanese-deep">
            Data yang sebaiknya tidak dimasukkan
          </h2>
          <p>
            Jangan memasukkan data pribadi sensitif, rahasia perusahaan, kredensial, atau informasi
            pihak lain yang tidak diperlukan untuk memahami pertanyaan regulasi. Untuk informasi
            tentang pemrosesan data, baca Kebijakan privasi.
          </p>
        </section>

        <section>
          <h2 className="mb-3 font-display text-2xl font-medium text-javanese-deep">
            Kapan harus meminta bantuan profesional
          </h2>
          <p>
            Konsultasikan kepada profesional atau instansi berwenang untuk sengketa hubungan
            industrial, keputusan PHK, perhitungan hak finansial, pelaporan pelanggaran, atau
            situasi lain yang membutuhkan nasihat dan tindakan hukum khusus.
          </p>
        </section>
      </div>

      <footer className="mt-12 flex items-center gap-2 border-t border-border pt-5 text-xs text-muted-text">
        <FileText className="size-4 text-javanese" />
        Dokumen informasi KerjaPedia AI
      </footer>
    </LegalLayout>
  );
}
