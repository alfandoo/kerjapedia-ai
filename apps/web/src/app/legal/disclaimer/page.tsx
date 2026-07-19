import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { SourcePanel } from "@/components/source-panel";

export default function DisclaimerPage() {
  return (
    <AppShell rightPanel={<SourcePanel />}>
      <section className="legal-page">
        <h1>Disclaimer</h1>
        <p>
          KerjaPedia AI menyediakan informasi berbasis dokumen yang tersedia dan bukan pengganti
          advokat, konsultan hukum, mediator hubungan industrial, atau instansi pemerintah.
        </p>
        <p>
          Jawaban harus diverifikasi terhadap sumber resmi, status hukum terbaru, dan konteks kasus
          masing-masing.
        </p>
        <div className="legal-links">
          <Link href="/legal/privacy">Kebijakan privasi</Link>
          <Link href="/legal/terms">Ketentuan penggunaan</Link>
        </div>
      </section>
    </AppShell>
  );
}
