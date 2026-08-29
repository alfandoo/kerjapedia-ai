"use client";

import Link from "next/link";
import { useState } from "react";

import { ChevronDown, ExternalLink, FileText, ThumbsDown, ThumbsUp } from "lucide-react";
import { useSettings } from "@/features/settings";
import { documentPdfUrl, submitFeedback } from "@/features/chat/api";
import type { Citation } from "@/features/chat/types";

type SourcePanelProps = {
  citations?: Citation[];
  question?: string;
};

export function SourcePanel({ citations = [], question = "" }: SourcePanelProps) {
  const { t: translate } = useSettings();
  const [expandedQuotes, setExpandedQuotes] = useState<Set<string>>(new Set());
  const [feedback, setFeedback] = useState<"helpful" | "not_helpful" | null>(null);

  function toggleQuote(citationId: string) {
    setExpandedQuotes((current) => {
      const next = new Set(current);
      if (next.has(citationId)) next.delete(citationId);
      else next.add(citationId);
      return next;
    });
  }

  function legalStatusLabel(status: string) {
    if (status === "active") return translate("source.statusActive");
    if (status === "needs_verification") return translate("source.statusNeedsVerification");
    return status;
  }

  async function handleFeedback(rating: "helpful" | "not_helpful") {
    setFeedback(rating);
    await submitFeedback({
      question: question || translate("source.feedbackFallback"),
      rating,
    }).catch(() => undefined);
  }

  return (
    <section
      className="flex h-full flex-col bg-background text-foreground"
      aria-label={translate("source.panelLabel")}
    >
      {citations.length > 0 ? (
        <div className="border-b border-border px-5 py-3 text-[11px] font-medium text-muted-foreground">
          {citations.length}{" "}
          {translate(citations.length === 1 ? "source.countSingular" : "source.countPlural")}
        </div>
      ) : null}
      {citations.length === 0 ? (
        <div className="m-5 flex flex-col items-center rounded-xl border border-dashed border-border bg-secondary px-5 py-9 text-center">
          <span className="grid size-10 place-items-center rounded-full bg-background text-muted-foreground shadow-sm">
            <FileText className="size-[18px]" />
          </span>
          <h3 className="mt-3 text-sm font-semibold">{translate("source.emptyTitle")}</h3>
          <p className="mt-1 max-w-[30ch] text-xs leading-5 text-muted-foreground">
            {translate("source.emptyDescription")}
          </p>
        </div>
      ) : (
        <div className="divide-y divide-border">
          {citations.map((citation, index) => {
            const expanded = expandedQuotes.has(citation.citation_id);
            const canExpand = citation.quote.length > 260;
            const reference = [citation.article, citation.paragraph].filter(Boolean).join(" · ");
            const pages =
              citation.page_start === citation.page_end
                ? `${citation.page_start}`
                : `${citation.page_start}–${citation.page_end}`;

            return (
              <article className="px-5 py-5" key={citation.citation_id}>
                <div className="flex items-start gap-3">
                  <span
                    className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-md border border-border bg-secondary font-mono text-[11px] font-semibold text-muted-foreground"
                    aria-hidden="true"
                  >
                    {index + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
                      <h3 className="min-w-0 flex-1 text-sm font-semibold leading-5">
                        {citation.document_title}
                      </h3>
                      <span
                        className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-1 text-[10px] font-semibold leading-none ${citation.legal_status === "active" ? "bg-javanese/10 text-javanese dark:bg-javanese/20 dark:text-[#82d5a9]" : "bg-amber-soft text-amber"}`}
                      >
                        <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
                        {legalStatusLabel(citation.legal_status)}
                      </span>
                    </div>
                    <dl className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] leading-4 text-muted-foreground">
                      {reference ? (
                        <div className="flex gap-1">
                          <dt>{translate("source.article")}</dt>
                          <dd className="font-medium text-foreground">{reference}</dd>
                        </div>
                      ) : null}
                      <div className="flex gap-1">
                        <dt>{translate("source.page")}</dt>
                        <dd className="font-medium text-foreground">{pages}</dd>
                      </div>
                      {citation.section ? (
                        <div className="flex min-w-0 gap-1">
                          <dt>{translate("source.section")}</dt>
                          <dd className="truncate font-medium text-foreground">
                            {citation.section}
                          </dd>
                        </div>
                      ) : null}
                    </dl>
                    {citation.quote ? (
                      <div className="mt-3 rounded-lg border border-border bg-secondary px-3.5 py-3">
                        <p
                          className={`text-xs leading-[1.65] text-muted-foreground ${expanded ? "" : "line-clamp-4"}`}
                        >
                          {citation.quote}
                        </p>

                        {canExpand ? (
                          <button
                            type="button"
                            className="mt-2 inline-flex min-h-7 items-center gap-1 rounded-md px-1 text-[11px] font-semibold text-foreground transition hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-javanese focus-visible:ring-offset-2 focus-visible:ring-offset-secondary"
                            aria-expanded={expanded}
                            onClick={() => toggleQuote(citation.citation_id)}
                          >
                            {expanded ? translate("source.showLess") : translate("source.showMore")}
                            <ChevronDown
                              className={`size-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
                            />
                          </button>
                        ) : null}
                      </div>
                    ) : null}
                    <a
                      href={`${documentPdfUrl(citation.document_id)}#page=${citation.page_start}`}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-3 inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-[11px] font-semibold text-foreground transition hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-javanese focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                    >
                      {translate("source.openPdf")}
                      <ExternalLink className="size-3.5" />
                    </a>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
      {citations.length > 0 ? (
        <footer className="border-t border-border px-5 py-5">
          <div className="rounded-lg border border-amber/25 bg-amber-soft px-3.5 py-3 text-xs leading-5 text-amber">
            {translate("source.verificationNote")}
          </div>
          <div className="mt-4">
            <p className="text-xs text-muted-foreground">{translate("source.feedbackQuestion")}</p>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                className={`inline-flex min-h-9 flex-1 items-center justify-center gap-2 rounded-lg border px-3 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-javanese ${feedback === "helpful" ? "border-javanese/40 bg-javanese/10 text-javanese dark:text-[#82d5a9]" : "border-border bg-background text-foreground hover:bg-accent"}`}
                aria-pressed={feedback === "helpful"}
                onClick={() => void handleFeedback("helpful")}
              >
                <ThumbsUp className="size-4" />
                {translate("source.helpful")}
              </button>
              <button
                type="button"
                className={`inline-flex min-h-9 flex-1 items-center justify-center gap-2 rounded-lg border px-3 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-javanese ${feedback === "not_helpful" ? "border-javanese/40 bg-javanese/10 text-javanese dark:text-[#82d5a9]" : "border-border bg-background text-foreground hover:bg-accent"}`}
                aria-pressed={feedback === "not_helpful"}
                onClick={() => void handleFeedback("not_helpful")}
              >
                <ThumbsDown className="size-4" />
                {translate("source.notHelpful")}
              </button>
            </div>
          </div>
          <Link
            href="/legal/disclaimer"
            className="mt-4 inline-flex min-h-8 items-center gap-1.5 rounded-md text-xs font-semibold text-javanese transition hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-javanese"
          >
            <FileText className="size-4" />
            {translate("source.disclaimer")}
          </Link>
        </footer>
      ) : null}
    </section>
  );
}
