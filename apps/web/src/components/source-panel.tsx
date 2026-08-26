"use client";

import Link from "next/link";
import { useState } from "react";

import { ExternalLink, FileText, ThumbsDown, ThumbsUp } from "lucide-react";
import { documentPdfUrl, submitFeedback } from "@/lib/api";
import type { Citation } from "@/lib/types";

type SourcePanelProps = {
  citations?: Citation[];
  question?: string;
};

export function SourcePanel({ citations = [], question = "" }: SourcePanelProps) {
  const [activeTab, setActiveTab] = useState<"sumber" | "pasal" | "kutipan">("sumber");
  const [feedback, setFeedback] = useState<"helpful" | "not_helpful" | null>(null);
  const activeCitations = citations;

  async function handleFeedback(rating: "helpful" | "not_helpful") {
    setFeedback(rating);
    await submitFeedback({ question: question || "Sumber panel feedback", rating }).catch(
      () => undefined
    );
  }

  return (
    <section className="flex h-full flex-col gap-3.5 bg-white">
      <div
        className="sticky top-0 z-10 flex h-[58px] shrink-0 border-b border-[#e8e4dc] bg-white"
        role="tablist"
        aria-label="Detail sumber"
      >
        {(["sumber", "pasal", "kutipan"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            id={`source-tab-${tab}`}
            aria-controls={`source-content-${tab}`}
            aria-selected={activeTab === tab}
            className={`relative min-h-12 flex-1 cursor-pointer border-0 bg-transparent text-xs font-medium text-[#68736c] transition hover:text-tinta ${
              activeTab === tab
                ? "font-semibold text-javanese after:absolute after:inset-x-[18px] after:bottom-[-1px] after:h-0.5 after:rounded-t after:bg-emas"
                : ""
            }`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === "sumber" ? "Sumber" : tab === "pasal" ? "Pasal" : "Kutipan"}
          </button>
        ))}
      </div>
      <div
        className="block"
        id={`source-content-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`source-tab-${activeTab}`}
      >
        {activeCitations.length === 0 ? (
          <div className="flex flex-col items-center rounded-xl border border-dashed border-[#e2ddd3] bg-[#faf8f4] p-[34px_18px] text-center">
            <FileText className="size-6 text-emas" />
            <h3 className="mt-3 text-sm font-semibold text-tinta">Belum ada sumber</h3>
            <p className="text-xs leading-[1.55] text-muted-text">
              Sumber resmi akan muncul setelah KerjaPedia menjawab pertanyaan Anda.
            </p>
          </div>
        ) : null}
        {activeCitations.map((citation, index) => (
          <article className="border-b border-[#f0ede8] py-5" key={citation.citation_id}>
            <div className="flex items-start gap-3">
              <span className="grid size-6 shrink-0 place-items-center rounded-lg bg-emas/10 font-mono text-[11px] font-bold text-emas">
                {index + 1}
              </span>
              <h3 className="mt-0.5 font-display text-sm font-semibold leading-snug text-tinta">
                {citation.document_title}
              </h3>
            </div>
            {activeTab !== "kutipan" ? (
              <dl className="ml-[34px] mt-4 divide-y divide-[#f5f2ed] border-t border-[#f5f2ed]">
                <div className="grid min-h-10 grid-cols-[82px_minmax(0,1fr)] items-center py-[7px]">
                  <dt className="text-[11px] font-medium text-[#78837c]">Pasal</dt>
                  <dd className="font-mono text-xs leading-normal text-tinta">
                    {[citation.article, citation.paragraph].filter(Boolean).join(" · ") || "-"}
                  </dd>
                </div>
                <div className="grid min-h-10 grid-cols-[82px_minmax(0,1fr)] items-center py-[7px]">
                  <dt className="text-[11px] font-medium text-[#78837c]">Halaman</dt>
                  <dd className="font-mono text-xs leading-normal text-tinta">
                    {citation.page_start}–{citation.page_end}
                  </dd>
                </div>
                {activeTab === "pasal" && citation.section ? (
                  <div className="grid min-h-10 grid-cols-[82px_minmax(0,1fr)] items-center py-[7px]">
                    <dt className="text-[11px] font-medium text-[#78837c]">Bagian</dt>
                    <dd className="text-xs leading-normal text-tinta">{citation.section}</dd>
                  </div>
                ) : null}
                {activeTab === "sumber" ? (
                  <div className="grid min-h-10 grid-cols-[82px_minmax(0,1fr)] items-center py-[7px]">
                    <dt className="text-[11px] font-medium text-[#78837c]">Status</dt>
                    <dd>
                      <span
                        className={
                          citation.legal_status === "active"
                            ? "inline-flex items-center gap-1.5 text-[11px] font-semibold text-[#236b48] before:size-[7px] before:rounded-full before:bg-current"
                            : "inline-flex items-center gap-1.5 text-[11px] font-semibold text-[#88540d] before:size-[7px] before:rounded-full before:bg-current"
                        }
                      >
                        {citation.legal_status === "active"
                          ? "Berlaku"
                          : citation.legal_status === "needs_verification"
                            ? "Perlu verifikasi"
                            : citation.legal_status}
                      </span>
                    </dd>
                  </div>
                ) : null}
              </dl>
            ) : null}
            {activeTab === "kutipan" ? (
              <div className="ml-[34px] mt-4 flex items-start gap-2.5 rounded-r-lg border-l-[3px] border-emas bg-[#faf8f4] p-[14px_15px]">
                <FileText className="size-4 shrink-0 text-emas" />
                <p className="m-0 font-display text-xs leading-[1.7] text-[#5a4f3a]">
                  {citation.quote}
                </p>
              </div>
            ) : null}
            <a
              href={`${documentPdfUrl(citation.document_id)}${
                activeTab === "sumber" ? "" : `#page=${citation.page_start}`
              }`}
              target="_blank"
              rel="noreferrer"
              className="ml-[34px] mt-3 inline-flex min-h-[32px] items-center gap-1.5 rounded-lg border border-[#e8e4dc] bg-white px-3 text-[11px] font-semibold text-javanese transition hover:border-javanese/40 hover:bg-[#f0f5f1]"
            >
              Buka PDF
              <ExternalLink className="size-3.5" />
            </a>
            <div className="ml-[34px] mt-[18px] hidden last:block">
              <p className="mb-2 text-xs text-muted-text">Apakah sumber ini membantu?</p>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  className={`inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border px-3 text-xs font-semibold transition hover:border-javanese hover:text-javanese ${
                    feedback === "helpful"
                      ? "border-javanese/30 bg-[#f0f5f1] text-javanese"
                      : "border-[#e8e4dc] bg-white text-tinta"
                  }`}
                  onClick={() => void handleFeedback("helpful")}
                >
                  <ThumbsUp className="size-[18px]" />
                  Membantu
                </button>
                <button
                  type="button"
                  className={`inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border px-3 text-xs font-semibold transition hover:border-javanese hover:text-javanese ${
                    feedback === "not_helpful"
                      ? "border-javanese/30 bg-[#f0f5f1] text-javanese"
                      : "border-[#e8e4dc] bg-white text-tinta"
                  }`}
                  onClick={() => void handleFeedback("not_helpful")}
                >
                  <ThumbsDown className="size-[18px]" />
                  Tidak membantu
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
      {activeCitations.length > 0 ? (
        <p className="ml-[34px] text-xs text-muted-text">
          Periksa status dan versi regulasi sebelum digunakan.
        </p>
      ) : null}
      <Link
        href="/legal/disclaimer"
        className="ml-[34px] mt-2 inline-flex items-center gap-[7px] text-xs font-semibold text-javanese transition hover:underline"
      >
        <FileText className="size-[18px]" />
        Baca disclaimer hukum
      </Link>
    </section>
  );
}
