"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AlertIcon, ExternalIcon, SearchIcon } from "./icons";
import { fetchDocuments } from "@/lib/api";
import { fallbackDocuments } from "@/lib/sample-data";
import type { DocumentSummary } from "@/lib/types";

export function RegulationSearch() {
  const [documents, setDocuments] = useState<DocumentSummary[]>(fallbackDocuments);
  const [query, setQuery] = useState("");
  const [topic, setTopic] = useState("all");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchDocuments(controller.signal)
      .then(setDocuments)
      .catch((err: Error) => setError(err.message));
    return () => controller.abort();
  }, []);

  const topics = useMemo(
    () => ["all", ...Array.from(new Set(documents.flatMap((document) => document.topics))).sort()],
    [documents]
  );

  const filtered = useMemo(() => {
    const normalized = query.toLowerCase().trim();
    return documents.filter((document) => {
      const matchesTopic = topic === "all" || document.topics.includes(topic);
      const searchable =
        `${document.title} ${document.short_title} ${document.topics.join(" ")}`.toLowerCase();
      return matchesTopic && (!normalized || searchable.includes(normalized));
    });
  }, [documents, query, topic]);

  return (
    <section className="search-page">
      <div className="page-heading">
        <h1>Cari regulasi</h1>
        <p>Telusuri sumber hukum yang akan dipakai KerjaPedia AI saat menjawab.</p>
      </div>
      <div className="search-toolbar">
        <label className="search-field" htmlFor="regulation-search">
          <SearchIcon className="icon" />
          <input
            id="regulation-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Cari judul, nomor, atau topik regulasi"
          />
        </label>
        <label className="select-field" htmlFor="topic-filter">
          Topik
          <select
            id="topic-filter"
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
          >
            {topics.map((item) => (
              <option key={item} value={item}>
                {item === "all" ? "Semua topik" : item.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error ? (
        <div className="state-strip muted">
          <AlertIcon className="icon" />
          API belum aktif, memakai daftar contoh lokal.
        </div>
      ) : null}
      <div className="document-table" role="table" aria-label="Daftar regulasi">
        <div className="table-row table-head" role="row">
          <span>Regulasi</span>
          <span>Tahun</span>
          <span>Status</span>
          <span>Aksi</span>
        </div>
        {filtered.map((document) => (
          <div className="table-row" role="row" key={document.document_id}>
            <div>
              <strong>{document.title}</strong>
              <small>{document.topics.map((item) => item.replaceAll("_", " ")).join(", ")}</small>
            </div>
            <span>{document.year}</span>
            <span className="status-badge">{document.legal_status}</span>
            <div className="row-actions">
              <Link href={`/documents/${document.document_id}`}>Detail</Link>
              <a
                href={document.source_url}
                target="_blank"
                rel="noreferrer"
                aria-label="Buka sumber resmi"
              >
                <ExternalIcon className="icon" />
              </a>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
