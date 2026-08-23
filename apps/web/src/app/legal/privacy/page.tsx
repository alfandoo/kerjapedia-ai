import Link from "next/link";

import { AppShell } from "@/components/app-shell";

export default function PrivacyPage() {
  return (
    <AppShell>
      <section className="mx-auto max-w-[940px] rounded-lg border border-line bg-surface p-7">
        <h1 className="text-2xl font-[760] leading-tight">Kebijakan privasi</h1>
        <p className="mt-1.5 leading-relaxed text-muted-text">
          Riwayat percakapan dan feedback dipakai untuk meningkatkan kualitas retrieval, citation,
          dan pengalaman produk. Jangan memasukkan data pribadi sensitif yang tidak diperlukan.
        </p>
        <p className="mt-1.5 leading-relaxed text-muted-text">
          Pada MVP lokal, sesi frontend tersimpan di browser dan sebagian data backend masih
          in-memory.
        </p>
        <Link href="/legal/disclaimer" className="mt-5 font-bold text-teal-strong">Kembali ke disclaimer</Link>
      </section>
    </AppShell>
  );
}
