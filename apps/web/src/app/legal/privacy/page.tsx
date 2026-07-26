import Link from "next/link";

import { AppShell } from "@/components/app-shell";

export default function PrivacyPage() {
  return (
    <AppShell>
      <section className="legal-page">
        <h1>Kebijakan privasi</h1>
        <p>
          Riwayat percakapan dan feedback dipakai untuk meningkatkan kualitas retrieval, citation,
          dan pengalaman produk. Jangan memasukkan data pribadi sensitif yang tidak diperlukan.
        </p>
        <p>
          Pada MVP lokal, sesi frontend tersimpan di browser dan sebagian data backend masih
          in-memory.
        </p>
        <Link href="/legal/disclaimer">Kembali ke disclaimer</Link>
      </section>
    </AppShell>
  );
}
