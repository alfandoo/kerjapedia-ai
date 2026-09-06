"use client";

import Link from "next/link";

import { ScaleIcon, SearchIcon } from "@/components/icons";
import { useSettings } from "@/features/settings";

export default function NotFound() {
  const { t: translate } = useSettings();
  return (
    <main className="relative grid min-h-screen place-items-center overflow-hidden bg-background px-6 py-12 text-foreground">
      <div
        className="pointer-events-none absolute left-1/2 top-1/2 -z-0 -translate-x-1/2 -translate-y-1/2 select-none font-display text-[clamp(13rem,42vw,31rem)] font-medium leading-none tracking-[-0.08em] text-javanese/[0.045]"
        aria-hidden="true"
      >
        404
      </div>
      <section className="relative z-10 w-full max-w-xl text-center">
        <Link
          href="/chat"
          className="mx-auto inline-flex items-center gap-2.5 rounded-lg text-javanese transition hover:text-javanese-deep focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-javanese"
          aria-label={translate("notFound.homeAriaLabel")}
        >
          <span className="grid size-10 place-items-center rounded-xl bg-javanese text-emas shadow-sm">
            <ScaleIcon className="size-5 [stroke-width:1.8]" />
          </span>
          <span className="font-display text-lg font-semibold">KerjaPedia AI</span>
        </Link>

        <div className="mx-auto mt-12 max-w-md border-y border-javanese/20 py-9">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-javanese">
            {translate("notFound.error")}
          </p>
          <h1 className="mt-4 font-display text-[clamp(2.35rem,6vw,3.5rem)] font-medium leading-[1.06] tracking-[-0.04em] text-javanese-deep">
            {translate("notFound.title")}
          </h1>
          <p className="mx-auto mt-5 max-w-sm text-[15px] leading-7 text-muted-foreground">
            {translate("notFound.description")}
          </p>
        </div>

        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <Link
            href="/chat"
            className="inline-flex h-11 items-center justify-center rounded-lg bg-javanese px-5 text-sm font-semibold text-white transition hover:bg-forest focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-javanese"
          >
            {translate("notFound.backToChat")}
          </Link>
          <Link
            href="/search"
            className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-border bg-card px-5 text-sm font-semibold text-javanese transition hover:border-javanese hover:bg-teal-soft focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-javanese"
          >
            <SearchIcon className="size-4 [stroke-width:2]" />
            {translate("notFound.searchRegulations")}
          </Link>
        </div>
      </section>
    </main>
  );
}
