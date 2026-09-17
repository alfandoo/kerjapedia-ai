"use client";

import Link from "next/link";

import { ScaleIcon } from "@/components/icons";
import { useSettings } from "@/features/settings";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t: translate } = useSettings();
  return (
    <main className="relative grid min-h-screen place-items-center overflow-hidden bg-background px-6 py-12 text-foreground">
      <section className="relative z-10 w-full max-w-xl text-center">
        <span className="mx-auto grid size-10 place-items-center rounded-xl bg-javanese text-emas shadow-sm">
          <ScaleIcon className="size-5 [stroke-width:1.8]" aria-hidden="true" />
        </span>

        <div className="mx-auto mt-12 max-w-md border-y border-javanese/20 py-9">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-javanese">
            {translate("error.eyebrow")}
          </p>
          <h1 className="mt-4 font-display text-[clamp(2.35rem,6vw,3.5rem)] font-medium leading-[1.06] tracking-[-0.04em] text-javanese-deep">
            {translate("error.title")}
          </h1>
          <p className="mx-auto mt-5 max-w-sm text-[15px] leading-7 text-muted-foreground">
            {translate("error.description")}
          </p>
        </div>

        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <button
            type="button"
            onClick={() => reset()}
            className="inline-flex h-11 items-center justify-center rounded-lg bg-javanese px-5 text-sm font-semibold text-white transition hover:bg-forest focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-javanese"
          >
            {translate("error.retry")}
          </button>
          <Link
            href="/chat"
            className="inline-flex h-11 items-center justify-center rounded-lg border border-border bg-card px-5 text-sm font-semibold text-javanese transition hover:border-javanese hover:bg-teal-soft focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-javanese"
          >
            {translate("error.backToChat")}
          </Link>
        </div>
      </section>
    </main>
  );
}
