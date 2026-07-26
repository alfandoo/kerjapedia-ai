"use client";

import Link from "next/link";
import { useState } from "react";

import { ExternalIcon, FileIcon, ThumbsDownIcon, ThumbsUpIcon } from "./icons";
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
    <section className="source-panel">
      <div className="source-tabs" role="tablist" aria-label="Detail sumber">
        {(["sumber", "pasal", "kutipan"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            id={`source-tab-${tab}`}
            aria-controls={`source-content-${tab}`}
            aria-selected={activeTab === tab}
            className={activeTab === tab ? "source-tab active" : "source-tab"}
            onClick={() => setActiveTab(tab)}
          >
            {tab === "sumber" ? "Sumber" : tab === "pasal" ? "Pasal" : "Kutipan"}
          </button>
        ))}
      </div>
      <div
        className="source-list"
        id={`source-content-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`source-tab-${activeTab}`}
      >
        {activeCitations.length === 0 ? (
          <div className="source-empty">
            <FileIcon className="icon" />
            <h3>Belum ada sumber</h3>
            <p>Sumber resmi akan muncul setelah KerjaPedia menjawab pertanyaan Anda.</p>
          </div>
        ) : null}
        {activeCitations.map((citation, index) => (
          <article className="source-card" key={citation.citation_id}>
            <div className="source-title">
              <span className="source-index">{index + 1}</span>
              <h3>{citation.document_title}</h3>
            </div>
            {activeTab !== "kutipan" ? (
              <dl className="source-meta">
                <div>
                  <dt>Pasal</dt>
                  <dd>
                    {[citation.article, citation.paragraph].filter(Boolean).join(" · ") || "-"}
                  </dd>
                </div>
                <div>
                  <dt>Halaman</dt>
                  <dd>
                    {citation.page_start}-{citation.page_end}
                  </dd>
                </div>
                {activeTab === "pasal" && citation.section ? (
                  <div>
                    <dt>Bagian</dt>
                    <dd>{citation.section}</dd>
                  </div>
                ) : null}
                {activeTab === "sumber" ? (
                  <div>
                    <dt>Status</dt>
                    <dd>
                      <span
                        className={
                          citation.legal_status === "active"
                            ? "legal-status verified"
                            : "legal-status warning"
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
              <div className="quote-box">
                <FileIcon className="icon" />
                <p>{citation.quote}</p>
              </div>
            ) : null}
            <a
              href={`${documentPdfUrl(citation.document_id)}${
                activeTab === "sumber" ? "" : `#page=${citation.page_start}`
              }`}
              target="_blank"
              rel="noreferrer"
              className="source-link"
            >
              Buka PDF dokumen
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
      {activeCitations.length > 0 ? (
        <p className="source-note">Periksa status dan versi regulasi sebelum digunakan.</p>
      ) : null}
      <Link href="/legal/disclaimer" className="source-disclaimer">
        <FileIcon className="icon" />
        Baca disclaimer hukum
      </Link>
    </section>
  );
}
