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
  const [regulationType, setRegulationType] = useState("all");
  const [year, setYear] = useState("");
  const [status, setStatus] = useState("all");
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

  const regulationTypes = useMemo(
    () => ["all", ...Array.from(new Set(documents.map((document) => document.regulation_type))).sort()],
    [documents]
  );

  const years = useMemo(
    () =>
      ["all", ...Array.from(new Set(documents.map((document) => document.year))).sort().reverse()],
    [documents]
  );

  const filtered = useMemo(() => {
    const normalized = query.toLowerCase().trim();
    return documents.filter((document) => {
      const matchesTopic = topic === "all" || document.topics.includes(topic);
      const matchesType =
        regulationType === "all" || document.regulation_type === regulationType;
      const matchesYear = year === "" || String(document.year) === year;
      const matchesStatus = status === "all" || document.legal_status === status;
      const searchable =
        `${document.title} ${document.short_title} ${document.topics.join(" ")}`.toLowerCase();
      return (
        matchesTopic &&
        matchesType &&
        matchesYear &&
        matchesStatus &&
        (!normalized || searchable.includes(normalized))
      );
    });
  }, [documents, query, topic, regulationType, year, status]);

  const hasFilters =
    query.trim().length > 0 ||
    topic !== "all" ||
    regulationType !== "all" ||
    year !== "" ||
    status !== "all";

  function resetSearch() {
    setQuery("");
    setTopic("all");
    setRegulationType("all");
    setYear("");
    setStatus("all");
  }

  function formatStatus(status: string) {
    if (status === "active") return "Berlaku";
    if (status === "needs_verification") return "Perlu verifikasi";
    return status.replaceAll("_", " ");
  }

  const selectClass =
    "h-12 rounded-xl border border-[#dce4df] bg-white px-4 text-sm text-tinta " +
    "outline-none transition focus:border-javanese focus:ring-2 focus:ring-javanese/10";

  return (
    <section className="w-full">
      <header className="mb-7 max-w-[760px]">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-emas">
          Basis hukum ketenagakerjaan
        </p>
        <h1 className="font-display text-[clamp(34px,3.5vw,46px)] font-medium leading-[1.12] tracking-[-0.02em] text-javanese">
          Temukan dasar hukum yang tepat
        </h1>
        <p className="mt-4 text-sm leading-relaxed text-muted-text">
          Telusuri regulasi ketenagakerjaan Indonesia dari sumber resmi pemerintah — UU, PP, dan
          Permenaker yang telah dikurasi.
        </p>
      </header>

      <div className="mb-6 flex flex-wrap items-stretch gap-3">
        <label
          className="flex h-12 min-w-[260px] flex-1 items-center gap-3 rounded-xl border border-[#dce4df] bg-white px-4 transition focus-within:border-javanese focus-within:ring-2 focus-within:ring-javanese/10"
          htmlFor="regulation-search"
        >
          <SearchIcon className="icon size-5 shrink-0 text-javanese" />
          <input
            id="regulation-search"
            aria-label="Cari judul, nomor, atau topik regulasi"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Cari judul, nomor, atau topik regulasi"
            className="h-full w-full bg-transparent text-sm outline-none placeholder:text-slate-400"
          />
        </label>
        <label className="sr-only" htmlFor="topic-filter">
          Topik
        </label>
        <select
          id="topic-filter"
          className={selectClass}
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
        >
          {topics.map((item) => (
            <option key={item} value={item}>
              {item === "all" ? "Semua topik" : item.replaceAll("_", " ")}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="type-filter">
          Jenis
        </label>
        <select
          id="type-filter"
          className={selectClass}
          value={regulationType}
          onChange={(event) => setRegulationType(event.target.value)}
        >
          {regulationTypes.map((item) => (
            <option key={item} value={item}>
              {item === "all" ? "Semua jenis" : item}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="year-filter">
          Tahun
        </label>
        <select
          id="year-filter"
          className={selectClass}
          value={year}
          onChange={(event) => setYear(event.target.value)}
        >
          {years.map((item) => (
            <option key={item} value={item}>
              {item === "all" ? "Semua tahun" : item}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="status-filter">
          Status
        </label>
        <select
          id="status-filter"
          className={selectClass}
          value={status}
          onChange={(event) => setStatus(event.target.value)}
        >
          <option value="all">Semua status</option>
          <option value="active">Berlaku</option>
          <option value="needs_verification">Perlu verifikasi</option>
        </select>
      </div>

      {error ? (
        <div
          className="mb-6 flex items-center gap-2.5 rounded-lg border-l-[3px] border-[#bc8121] bg-[#fffaf0] px-4 py-3 text-xs text-[#6e531c]"
          role="status"
        >
          <AlertIcon className="icon size-4 shrink-0" />
          Katalog API belum tersedia. Menampilkan daftar referensi lokal sementara.
        </div>
      ) : null}

      <div className="grid min-h-16 grid-cols-[1fr_auto] items-center gap-2 border-b border-[#dce4df] py-4" aria-live="polite">
        <div>
          <h2 className="text-sm font-semibold text-tinta">Daftar regulasi</h2>
          <span className="mt-0.5 block text-xs text-muted-text">
            {loading ? "Memuat regulasi…" : `${filtered.length} regulasi ditemukan`}
          </span>
        </div>
        {hasFilters ? (
          <button
            type="button"
            onClick={resetSearch}
            className="text-xs font-semibold text-forest transition hover:text-emas"
          >
            Reset pencarian
          </button>
        ) : null}
      </div>

      <div aria-label="Daftar regulasi" aria-busy={loading}>
        {!loading && filtered.length === 0 ? (
          <div className="py-16 text-center">
            <h2 className="text-lg font-semibold text-tinta">Regulasi tidak ditemukan</h2>
            <p className="mt-2 text-sm text-muted-text">
              Coba gunakan judul, nomor, atau topik yang lebih umum.
            </p>
            <button
              type="button"
              onClick={resetSearch}
              className="mt-5 h-11 rounded-xl border border-[#c7d4cd] px-5 text-sm font-semibold text-forest transition hover:border-emas hover:text-emas"
            >
              Hapus filter
            </button>
          </div>
        ) : null}

        {!loading && filtered.length > 0 ? (
          <div className="hidden grid-cols-[170px_minmax(280px,1fr)_70px_130px_150px] items-center gap-5 border-b border-[#dce4df] py-3 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500 md:grid" aria-hidden="true">
            <span>Jenis regulasi</span>
            <span>Dokumen</span>
            <span>Tahun</span>
            <span>Status</span>
            <span className="text-right">Akses</span>
          </div>
        ) : null}

        {filtered.map((document) => (
          <article
            className="grid grid-cols-1 items-center gap-4 border-b border-[#dce4df] px-2 py-5 transition hover:bg-[#f8faf8] md:grid-cols-[170px_minmax(280px,1fr)_70px_130px_150px] md:gap-5 md:px-0"
            key={document.document_id}
          >
            <div className="border-r border-[#dce4df] pr-5">
              <span className="block text-[11px] font-semibold uppercase tracking-[0.06em] text-forest">
                {document.regulation_type}
              </span>
              <small className="mt-1.5 block text-[10px] leading-relaxed text-muted-text">
                Nomor {document.number} Tahun {document.year}
              </small>
            </div>
            <div>
              <h2 className="font-display text-[clamp(18px,1.7vw,23px)] font-medium leading-snug tracking-[-0.01em] text-tinta">
                <Link
                  href={`/documents/${document.document_id}`}
                  className="transition hover:text-forest"
                >
                  {document.title}
                </Link>
              </h2>
              <p className="mt-2 text-[11px] capitalize leading-relaxed text-muted-text">
                {document.topics.map((item) => item.replaceAll("_", " ")).join(" · ")}
              </p>
            </div>
            <span className="font-mono text-xs text-slate-600">{document.year}</span>
            <span
              className={`inline-flex w-fit items-center gap-2 text-[11px] ${
                document.legal_status === "active" ? "text-forest" : "text-slate-600"
              }`}
            >
              <i
                aria-hidden="true"
                className={`size-2 rounded-full ${
                  document.legal_status === "active" ? "bg-forest" : "bg-[#dc8a12]"
                }`}
              />
              {formatStatus(document.legal_status)}
            </span>
            <div className="flex items-center justify-start gap-2.5 md:justify-end">
              <Link
                href={`/documents/${document.document_id}`}
                className="inline-flex h-10 items-center rounded-lg border border-[#c7d4cd] px-3.5 text-xs font-semibold text-forest transition hover:border-emas hover:text-emas"
              >
                Lihat detail
              </Link>
              <a
                href={document.pdf_url}
                target="_blank"
                rel="noreferrer"
                aria-label={`Buka PDF ${document.short_title}`}
                title="Buka PDF dari dataset"
                className="inline-flex size-10 items-center justify-center rounded-lg border border-[#c7d4cd] text-forest transition hover:border-emas hover:text-emas"
              >
                <ExternalIcon className="icon size-4" />
              </a>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
