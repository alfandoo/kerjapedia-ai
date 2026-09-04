import Link from "next/link";
import { ArrowLeft, Scale } from "lucide-react";
import type { ReactNode } from "react";

export function LegalLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-[100svh] bg-white text-tinta">
      <header className="sticky top-0 z-20 border-b border-border bg-white/95 backdrop-blur-xl">
        <div className="mx-auto flex h-[64px] w-full max-w-[1080px] items-center justify-between gap-4 px-6 max-[760px]:px-4">
          <Link
            href="/chat"
            className="flex items-center gap-2.5"
            aria-label="KerjaPedia AI beranda"
          >
            <span className="grid size-9 place-items-center rounded-[9px] bg-javanese text-white">
              <Scale className="size-5" />
            </span>
            <strong className="font-display text-[15px] font-semibold text-javanese">
              KerjaPedia AI
            </strong>
          </Link>
          <Link
            href="/chat"
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-border bg-white px-3.5 text-xs font-semibold text-javanese transition hover:border-javanese hover:bg-teal-soft"
          >
            <ArrowLeft className="size-4" />
            Kembali ke chat
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1080px] px-6 py-10 max-[760px]:px-4 max-[760px]:py-8">
        {children}
      </main>
    </div>
  );
}
