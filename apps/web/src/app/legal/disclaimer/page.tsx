import Link from "next/link";

import { AppShell } from "@/components/layout/app-shell";

export default function DisclaimerPage() {
  return (
    <AppShell>
      <section className="mx-auto max-w-[940px] rounded-lg border border-line bg-surface p-7">
        <h1 className="text-2xl font-[760] leading-tight">Disclaimer</h1>
        <p className="mt-1.5 leading-relaxed text-muted-text">
          KerjaPedia AI menyediakan informasi berbasis dokumen yang tersedia dan bukan pengganti
          advokat, konsultan hukum, mediator hubungan industrial, atau instansi pemerintah.
        </p>
        <p className="mt-1.5 leading-relaxed text-muted-text">
          Jawaban harus diverifikasi terhadap sumber resmi, status hukum terbaru, dan konteks kasus
          masing-masing.
        </p>
        <div className="mt-5 flex gap-4">
          <Link href="/legal/privacy" className="font-bold text-teal-strong">Kebijakan privasi</Link>
          <Link href="/legal/terms" className="font-bold text-teal-strong">Ketentuan penggunaan</Link>
        </div>
      </section>
    </AppShell>
  );
}
