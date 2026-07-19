import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { SourcePanel } from "@/components/source-panel";

export default function TermsPage() {
  return (
    <AppShell rightPanel={<SourcePanel />}>
      <section className="legal-page">
        <h1>Ketentuan penggunaan</h1>
        <p>
          Gunakan KerjaPedia AI sebagai alat bantu riset regulasi. Pengguna bertanggung jawab
          memeriksa sumber, status regulasi, dan kesesuaian konteks sebelum mengambil keputusan.
        </p>
        <p>
          Dilarang memakai layanan ini untuk membuat klaim hukum final tanpa verifikasi pihak
          berwenang.
        </p>
        <Link href="/legal/disclaimer">Kembali ke disclaimer</Link>
      </section>
    </AppShell>
  );
}
