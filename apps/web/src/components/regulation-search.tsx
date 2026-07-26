"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AlertIcon, ExternalIcon, SearchIcon } from "./icons";
import { fetchDocuments } from "@/lib/api";
import { fallbackDocuments } from "@/lib/sample-data";
import type { DocumentSummary } from "@/lib/types";

export function RegulationSearch() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [query, setQuery] = useState("");
  const [topic, setTopic] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    async function loadDocuments() {
      try {
        const nextDocuments = await fetchDocuments(controller.signal);
        if (!controller.signal.aborted) setDocuments(nextDocuments);
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        setDocuments(fallbackDocuments);
        setError((err as Error).message);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void loadDocuments();
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

  const hasFilters = query.trim().length > 0 || topic !== "all";

  function resetSearch() {
    setQuery("");
    setTopic("all");
  }

  function formatStatus(status: string) {
    if (status === "active") return "Berlaku";
    if (status === "needs_verification") return "Perlu verifikasi";
    return status.replaceAll("_", " ");
  }

  return (
    <section className="search-page">
      <header className="search-hero">
        <h1>Temukan dasar hukum yang tepat</h1>
        <p>Telusuri regulasi ketenagakerjaan dari sumber resmi pemerintah.</p>
      </header>
      <div className="search-controls">
        <label className="search-field" htmlFor="regulation-search">
          <SearchIcon className="icon" />
          <input
            id="regulation-search"
            aria-label="Cari judul, nomor, atau topik regulasi"
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
        <div className="search-fallback-note" role="status">
          <AlertIcon className="icon" />
          Katalog API belum tersedia. Menampilkan daftar referensi lokal sementara.
        </div>
      ) : null}
      <div className="search-summary" aria-live="polite">
        <h2>Daftar regulasi</h2>
        <span>{loading ? "Memuat regulasi…" : `${filtered.length} regulasi ditemukan`}</span>
        {hasFilters ? (
          <button type="button" onClick={resetSearch}>
            Reset pencarian
          </button>
        ) : null}
      </div>
      <div className="regulation-list" aria-label="Daftar regulasi" aria-busy={loading}>
        {!loading && filtered.length > 0 ? (
          <div className="regulation-list-header" aria-hidden="true">
            <span>Jenis regulasi</span>
            <span>Dokumen</span>
            <span>Tahun</span>
            <span>Status</span>
            <span>Akses</span>
          </div>
        ) : null}
        {!loading && filtered.length === 0 ? (
          <div className="search-empty">
            <h2>Regulasi tidak ditemukan</h2>
            <p>Coba gunakan judul, nomor, atau topik yang lebih umum.</p>
            <button type="button" onClick={resetSearch}>
              Hapus filter
            </button>
          </div>
        ) : null}
        {filtered.map((document) => (
          <article className="regulation-row" key={document.document_id}>
            <div className="regulation-kind">
              <span>{document.regulation_type}</span>
              <small>
                Nomor {document.number} Tahun {document.year}
              </small>
            </div>
            <div className="regulation-copy">
              <h2>{document.title}</h2>
              <p>{document.topics.map((item) => item.replaceAll("_", " ")).join(", ")}</p>
            </div>
            <span className="regulation-year">{document.year}</span>
            <span className={`regulation-status ${document.legal_status}`}>
              <i aria-hidden="true" />
              {formatStatus(document.legal_status)}
            </span>
            <div className="regulation-actions">
              <Link href={`/documents/${document.document_id}`}>Lihat detail</Link>
              <a
                href={document.pdf_url}
                target="_blank"
                rel="noreferrer"
                aria-label={`Buka PDF ${document.short_title}`}
                title="Buka PDF dari dataset"
              >
                <ExternalIcon className="icon" />
              </a>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
