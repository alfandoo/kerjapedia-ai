import Link from "next/link";

import { AppShell } from "@/components/layout/app-shell";

export default function TermsPage() {
  return (
    <AppShell>
      <section className="mx-auto max-w-[940px] rounded-lg border border-line bg-surface p-7">
        <h1 className="text-2xl font-[760] leading-tight">Ketentuan penggunaan</h1>
        <p className="mt-1.5 leading-relaxed text-muted-text">
          Gunakan KerjaPedia AI sebagai alat bantu riset regulasi. Pengguna bertanggung jawab
          memeriksa sumber, status regulasi, dan kesesuaian konteks sebelum mengambil keputusan.
        </p>
        <p className="mt-1.5 leading-relaxed text-muted-text">
          Dilarang memakai layanan ini untuk membuat klaim hukum final tanpa verifikasi pihak
          berwenang.
        </p>
        <Link href="/legal/disclaimer" className="mt-5 font-bold text-teal-strong">Kembali ke disclaimer</Link>
      </section>
    </AppShell>
  );
}
