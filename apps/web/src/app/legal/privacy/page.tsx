import { ShieldCheck } from "lucide-react";

import { LegalLayout } from "../legal-layout";

export default function PrivacyPage() {
  return (
    <LegalLayout>
      <header className="border-b border-border pb-8">
        <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-javanese">
          Privasi pengguna
        </p>
        <h1 className="max-w-[760px] font-display text-[clamp(32px,4.5vw,44px)] font-medium leading-[1.1] tracking-[-0.03em] text-javanese-deep">
          Kebijakan privasi
        </h1>
        <p className="mt-5 max-w-[720px] text-[15px] leading-7 text-muted-foreground">
          Kami menghormati privasi Anda dan menjelaskan dengan jelas data apa yang diproses serta
          bagaimana data tersebut digunakan saat Anda menggunakan KerjaPedia AI.
        </p>
        <div className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-xs text-muted-foreground">
          <span>Versi 1.0</span>
          <span>Terakhir diperbarui: 4 September 2026</span>
        </div>
      </header>

      <div className="mt-8 grid gap-10 text-[15px] leading-7 text-foreground">
        <section>
          <h2 className="mb-3 font-display text-2xl font-medium text-javanese-deep">
            Data yang kami proses
          </h2>
          <p>
            Pertanyaan yang Anda ajukan, riwayat percakapan, dan tanggapan feedback digunakan untuk
            meningkatkan kualitas retrieval, penyusunan kutipan, dan pengalaman produk secara
            keseluruhan.
          </p>
        </section>

        <section>
          <h2 className="mb-3 font-display text-2xl font-medium text-javanese-deep">
            Penyimpanan pada MVP lokal
          </h2>
          <p>
            Pada tahap awal (MVP), sesi frontend disimpan di browser Anda dan sebagian data backend
            masih bersifat in-memory. Ini berarti data dapat hilang ketika sesi berakhir atau server
            dimulai ulang.
          </p>
        </section>

        <section>
          <h2 className="mb-3 font-display text-2xl font-medium text-javanese-deep">
            Data yang sebaiknya tidak dimasukkan
          </h2>
          <p>
            Jangan memasukkan data pribadi sensitif, rahasia perusahaan, kredensial, atau informasi
            pihak lain yang tidak diperlukan untuk memahami pertanyaan regulasi Anda.
          </p>
        </section>

        <div className="flex items-start gap-3 rounded-xl legal-notice border border-javanese/20 bg-teal-soft px-4 py-4 text-sm leading-6 text-foreground">
          <ShieldCheck className="mt-0.5 size-5 shrink-0 text-javanese" />
          <p>
            Kami berupaya memproses data seminimal mungkin untuk kebutuhan layanan. Jika Anda
            memiliki pertanyaan, silakan hubungi kami melalui kanal resmi.
          </p>
        </div>
      </div>
    </LegalLayout>
  );
}
