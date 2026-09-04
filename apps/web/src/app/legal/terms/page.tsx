import { FileText } from "lucide-react";

import { LegalLayout } from "../legal-layout";

export default function TermsPage() {
  return (
    <LegalLayout>
      <header className="border-b border-border pb-8">
        <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-javanese">
          Ketentuan layanan
        </p>
        <h1 className="max-w-[760px] font-display text-[clamp(32px,4.5vw,44px)] font-medium leading-[1.1] tracking-[-0.03em] text-javanese-deep">
          Ketentuan penggunaan
        </h1>
        <p className="mt-5 max-w-[720px] text-[15px] leading-7 text-muted-text">
          Dengan menggunakan KerjaPedia AI, Anda setuju untuk memanfaatkan layanan ini secara
          bertanggung jawab dan memahami batasan alat bantu berbasis AI.
        </p>
        <div className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-[11px] text-muted-text">
          <span>Versi 1.0</span>
          <span>Terakhir diperbarui: 4 September 2026</span>
        </div>
      </header>

      <div className="grid gap-10 text-[15px] leading-7 text-foreground">
        <section>
          <h2 className="mb-3 font-display text-2xl font-medium text-javanese-deep">
            Tanggung jawab pengguna
          </h2>
          <p>
            Gunakan KerjaPedia AI sebagai alat bantu riset regulasi. Anda bertanggung jawab
            memeriksa sumber, status regulasi, dan kesesuaian konteks sebelum mengambil keputusan.
          </p>
        </section>

        <section>
          <h2 className="mb-3 font-display text-2xl font-medium text-javanese-deep">
            Penggunaan yang wajar
          </h2>
          <p>
            Dilarang memakai layanan ini untuk membuat klaim hukum final tanpa verifikasi pihak
            berwenang, atau untuk tujuan yang melanggar hukum dan merugikan pihak lain.
          </p>
        </section>

        <section>
          <h2 className="mb-3 font-display text-2xl font-medium text-javanese-deep">
            Batasan jawaban
          </h2>
          <p>
            Jawaban yang diberikan tidak menggantikan opini hukum profesional. KerjaPedia AI tidak
            menjamin kebenaran, kelengkapan, atau pembaruan atas seluruh informasi yang disajikan.
          </p>
        </section>

        <div className="flex items-start gap-3 rounded-xl border border-[#bfe3c9] bg-[#f0f8f2] px-4 py-4 text-sm leading-6 text-javanese-deep">
          <FileText className="mt-0.5 size-5 shrink-0 text-javanese" />
          <p>
            Dengan melanjutkan penggunaan, Anda dianggap telah membaca dan menyetujui ketentuan yang
            berlaku. Baca juga Kebijakan privasi untuk memahami cara data Anda diproses.
          </p>
        </div>
      </div>
    </LegalLayout>
  );
}
