import Link from "next/link";
import { ArrowLeft, Scale } from "lucide-react";
import type { ReactNode } from "react";

export function LegalLayout({ children }: { children: ReactNode }) {
  return (
    <div className="legal-page min-h-[100svh] bg-background text-foreground">
      <header className="legal-topbar sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur-xl">
        <div className="mx-auto flex h-[64px] w-full max-w-[1080px] items-center justify-between gap-4 px-6 max-[760px]:px-4">
          <Link
            href="/chat"
            className="flex min-h-[44px] items-center gap-2.5 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-javanese"
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
            className="legal-back-link inline-flex h-11 items-center gap-2 rounded-lg border border-border bg-secondary px-3.5 text-xs font-semibold text-javanese transition hover:border-javanese hover:bg-teal-soft focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-javanese"
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
