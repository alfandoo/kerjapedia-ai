"use client";

import Link from "next/link";
import { useState } from "react";

import { ExternalIcon, FileIcon, ThumbsDownIcon, ThumbsUpIcon } from "./icons";
import { submitFeedback } from "@/lib/api";
import { fallbackCitation } from "@/lib/sample-data";
import type { Citation } from "@/lib/types";

type SourcePanelProps = {
  citations?: Citation[];
  question?: string;
};

export function SourcePanel({ citations = [fallbackCitation], question = "" }: SourcePanelProps) {
  const [activeTab, setActiveTab] = useState<"sumber" | "pasal" | "kutipan">("sumber");
  const [feedback, setFeedback] = useState<"helpful" | "not_helpful" | null>(null);
  const activeCitations = citations.length > 0 ? citations : [fallbackCitation];

  async function handleFeedback(rating: "helpful" | "not_helpful") {
    setFeedback(rating);
    await submitFeedback({ question: question || "Sumber panel feedback", rating }).catch(
      () => undefined
    );
  }

  return (
    <section className="source-panel">
      <div className="source-tabs" role="tablist" aria-label="Detail sumber">
        {(["sumber", "pasal", "kutipan"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            className={activeTab === tab ? "source-tab active" : "source-tab"}
            onClick={() => setActiveTab(tab)}
          >
            {tab === "sumber" ? "Sumber" : tab === "pasal" ? "Pasal" : "Kutipan"}
          </button>
        ))}
      </div>
      <div className="source-list">
        {activeCitations.map((citation, index) => (
          <article className="source-card" key={citation.citation_id}>
            <div className="source-title">
              <span className="source-index">{index + 1}</span>
              <h3>{citation.document_title}</h3>
            </div>
            <dl className="source-meta">
              <div>
                <dt>Pasal</dt>
                <dd>{citation.article ?? "-"}</dd>
              </div>
              <div>
                <dt>Halaman</dt>
                <dd>
                  {citation.page_start}-{citation.page_end}
                </dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{citation.legal_status}</dd>
              </div>
            </dl>
            <div className="quote-box">
              <FileIcon className="icon" />
              <p>{citation.quote}</p>
            </div>
            <a href={citation.source_url} target="_blank" rel="noreferrer" className="source-link">
              Buka sumber resmi
              <ExternalIcon className="icon" />
            </a>
            <div className="source-feedback">
              <p>Apakah sumber ini membantu?</p>
              <div>
                <button
                  type="button"
                  className={feedback === "helpful" ? "tiny-button active" : "tiny-button"}
                  onClick={() => void handleFeedback("helpful")}
                >
                  <ThumbsUpIcon className="icon" />
                  Membantu
                </button>
                <button
                  type="button"
                  className={feedback === "not_helpful" ? "tiny-button active" : "tiny-button"}
                  onClick={() => void handleFeedback("not_helpful")}
                >
                  <ThumbsDownIcon className="icon" />
                  Tidak membantu
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
      <p className="source-note">Periksa tanggal dan versi regulasi sebelum digunakan.</p>
      <Link href="/legal/disclaimer" className="source-disclaimer">
        <FileIcon className="icon" />
        Baca disclaimer hukum
      </Link>
    </section>
  );
}
