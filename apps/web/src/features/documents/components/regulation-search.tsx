"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AlertIcon, SearchIcon } from "@/components/icons";
import { ChevronLeft, ChevronRight, Download, X as XIcon } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { fetchDocuments } from "@/features/documents/api";
import { fallbackDocuments } from "@/features/documents/sample-data";
import type { DocumentSummary } from "@/features/documents/types";

function FilterSelect({
  id,
  label,
  value,
  options,
  onValueChange,
}: {
  id: string;
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onValueChange: (value: string) => void;
}) {
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger
        id={id}
        aria-label={label}
        className="h-12 w-full min-w-0 rounded-xl border-border bg-white px-4 text-sm text-tinta transition focus-visible:outline-none focus-visible:ring-0 focus-visible:border-javanese data-[size=default]:h-12 data-[state=open]:border-javanese"
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent
        position="popper"
        align="start"
        className="max-h-[min(220px,calc(100vh-120px))] overflow-y-auto border border-border bg-white p-1 text-tinta [scrollbar-color:#8bc99d_#f0f8f2] [scrollbar-gutter:stable] [scrollbar-width:thin] [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:bg-[#f0f8f2] [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-[#8bc99d] [&::-webkit-scrollbar-thumb:hover]:bg-[#176b3a]"
      >
        {options.map((option) => (
          <SelectItem
            key={option.value}
            value={option.value}
            className="rounded-md text-tinta focus:bg-teal-soft focus:text-javanese"
          >
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function RegulationSearch() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [query, setQuery] = useState("");
  const [topic, setTopic] = useState("all");
  const [regulationType, setRegulationType] = useState("all");
  const [year, setYear] = useState("");
  const [status, setStatus] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 5;

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
    () => [
      "all",
      ...Array.from(new Set(documents.map((document) => document.regulation_type))).sort(),
    ],
    [documents]
  );

  const years = useMemo(
    () => [
      "all",
      ...Array.from(new Set(documents.map((document) => String(document.year))))
        .sort()
        .reverse(),
    ],
    [documents]
  );

  const filtered = useMemo(() => {
    const normalized = query.toLowerCase().trim();
    return documents.filter((document) => {
      const matchesTopic = topic === "all" || document.topics.includes(topic);
      const matchesType = regulationType === "all" || document.regulation_type === regulationType;
      const matchesYear = year === "" || year === "all" || String(document.year) === year;
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

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageRows = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  function resetSearch() {
    setQuery("");
    setTopic("all");
    setRegulationType("all");
    setYear("");
    setStatus("all");
    setPage(1);
  }

  function formatStatus(status: string) {
    if (status === "active") return "Berlaku";
    if (status === "needs_verification") return "Perlu verifikasi";
    return status.replaceAll("_", " ");
  }

  return (
    <section className="w-full">
      <header className="mb-7 max-w-[760px]">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-javanese">
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

      <div className="mb-6 grid grid-cols-1 items-stretch gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(240px,1.6fr)_repeat(4,minmax(130px,1fr))_48px]">
        <label
          className="flex h-12 min-w-0 items-center gap-3 rounded-xl border border-border bg-white px-4 transition hover:border-javanese hover:bg-teal-soft focus-within:border-javanese focus-within:ring-2 focus-within:ring-javanese/10 sm:col-span-2 xl:col-span-1"
          htmlFor="regulation-search"
        >
          <SearchIcon className="size-5 [stroke-width:1.8] shrink-0 text-javanese" />
          <input
            id="regulation-search"
            aria-label="Cari judul, nomor, atau topik regulasi"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Cari judul, nomor, atau topik..."
            className="h-full w-full bg-transparent text-sm outline-none placeholder:text-slate-400"
          />
        </label>
        <FilterSelect
          id="topic-filter"
          label="Topik"
          value={topic}
          options={topics.map((item) => ({
            value: item,
            label: item === "all" ? "Semua topik" : item.replaceAll("_", " "),
          }))}
          onValueChange={setTopic}
        />
        <FilterSelect
          id="type-filter"
          label="Jenis"
          value={regulationType}
          options={regulationTypes.map((item) => ({
            value: item,
            label: item === "all" ? "Semua jenis" : item,
          }))}
          onValueChange={setRegulationType}
        />
        <FilterSelect
          id="year-filter"
          label="Tahun"
          value={year || "all"}
          options={years.map((item) => ({
            value: item,
            label: item === "all" ? "Semua tahun" : item,
          }))}
          onValueChange={(value) => setYear(value === "all" ? "" : value)}
        />
        <FilterSelect
          id="status-filter"
          label="Status"
          value={status}
          options={[
            { value: "all", label: "Semua status" },
            { value: "active", label: "Berlaku" },
            { value: "needs_verification", label: "Perlu verifikasi" },
          ]}
          onValueChange={setStatus}
        />
        {hasFilters ? (
          <button
            type="button"
            onClick={resetSearch}
            aria-label="Reset pencarian"
            title="Reset pencarian"
            className="inline-flex size-12 shrink-0 items-center justify-center rounded-xl border border-border bg-white text-muted-text transition hover:border-javanese hover:bg-teal-soft hover:text-javanese"
          >
            <XIcon className="size-4" />
          </button>
        ) : null}
      </div>

      {error ? (
        <div
          className="mb-6 flex items-center gap-2.5 rounded-lg border-l-[3px] border-amber bg-amber-soft px-4 py-3 text-xs text-amber"
          role="status"
        >
          <AlertIcon className="size-4 [stroke-width:1.8] shrink-0" />
          Katalog API belum tersedia. Menampilkan daftar referensi lokal sementara.
        </div>
      ) : null}

      <div aria-label="Daftar regulasi" aria-busy={loading} className="overflow-x-auto">
        {!loading && filtered.length === 0 ? (
          <div className="py-16 text-center">
            <h2 className="text-lg font-semibold text-tinta">Regulasi tidak ditemukan</h2>
            <p className="mt-2 text-sm text-muted-text">
              Coba gunakan judul, nomor, atau topik yang lebih umum.
            </p>
            <button
              type="button"
              onClick={resetSearch}
              className="mt-5 h-11 rounded-xl border border-input px-5 text-sm font-semibold text-javanese transition hover:border-javanese hover:bg-teal-soft"
            >
              Hapus filter
            </button>
          </div>
        ) : null}

        {!loading && filtered.length > 0 ? (
          <div className="overflow-x-auto border border-border rounded-xl">
            <table className="w-full min-w-[900px] border-collapse text-left">
              <thead>
                <tr className="border-b border-border bg-surface-soft">
                  <th className="w-[17%] px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-text">
                    Jenis regulasi
                  </th>
                  <th className="w-[38%] px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-text">
                    Dokumen
                  </th>
                  <th className="w-[10%] px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-text">
                    Tahun
                  </th>
                  <th className="w-[16%] px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-text">
                    Status
                  </th>
                  <th className="w-[19%] px-4 py-3 text-right text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-text">
                    Akses
                  </th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((document) => (
                  <tr
                    className="border-b border-border transition-colors last:border-b-0 hover:bg-surface-soft"
                    key={document.document_id}
                  >
                    <td className="px-4 py-4 align-middle">
                      <span className="block text-[11px] font-semibold uppercase tracking-[0.06em] text-forest">
                        {document.regulation_type}
                      </span>
                      <small className="mt-1 block text-[10px] leading-relaxed text-muted-text">
                        Nomor {document.number} Tahun {document.year}
                      </small>
                    </td>
                    <td className="px-4 py-4 align-middle">
                      <Link
                        href={`/documents/${document.document_id}`}
                        className="font-display text-[clamp(15px,1.3vw,18px)] font-medium leading-snug tracking-[-0.01em] text-tinta transition hover:text-forest"
                      >
                        {document.title}
                      </Link>
                      <p className="mt-1.5 truncate text-[11px] capitalize leading-relaxed text-muted-text">
                        {document.topics.map((item) => item.replaceAll("_", " ")).join(" · ")}
                      </p>
                    </td>
                    <td className="px-4 py-4 align-middle font-mono text-xs text-slate-600">
                      {document.year}
                    </td>
                    <td className="px-4 py-4 align-middle">
                      <span
                        className={`inline-flex items-center gap-2 whitespace-nowrap text-[11px] ${
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
                    </td>
                    <td className="px-4 py-4 align-middle">
                      <div className="flex items-center justify-end gap-2 whitespace-nowrap">
                        <a
                          href={document.source_url || document.pdf_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex h-10 items-center whitespace-nowrap rounded-lg border border-input px-3.5 text-xs font-semibold text-javanese transition hover:border-javanese hover:bg-teal-soft"
                        >
                          Buka sumber
                        </a>
                        <a
                          href={document.pdf_url}
                          download
                          aria-label={`Download PDF ${document.short_title}`}
                          title="Download PDF"
                          className="inline-flex size-10 shrink-0 items-center justify-center rounded-lg border border-input text-javanese transition hover:border-javanese hover:bg-teal-soft"
                        >
                          <Download className="size-4" />
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {!loading && filtered.length > 0 && totalPages > 1 ? (
          <div className="mt-5 flex items-center justify-between gap-3">
            <span className="text-xs text-muted-text">
              {Math.min((safePage - 1) * PAGE_SIZE + 1, filtered.length)}–
              {Math.min(safePage * PAGE_SIZE, filtered.length)} dari {filtered.length}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPage(safePage - 1)}
                disabled={safePage <= 1}
                className="inline-flex h-9 items-center gap-1 rounded-lg border border-input px-3 text-xs font-semibold text-javanese transition hover:border-javanese hover:bg-teal-soft disabled:cursor-not-allowed disabled:opacity-40"
                aria-label="Halaman sebelumnya"
              >
                <ChevronLeft className="size-4" />
                Sebelumnya
              </button>
              <span className="min-w-[72px] text-center text-xs font-semibold text-tinta">
                {safePage} / {totalPages}
              </span>
              <button
                type="button"
                onClick={() => setPage(safePage + 1)}
                disabled={safePage >= totalPages}
                className="inline-flex h-9 items-center gap-1 rounded-lg border border-input px-3 text-xs font-semibold text-javanese transition hover:border-javanese hover:bg-teal-soft disabled:cursor-not-allowed disabled:opacity-40"
                aria-label="Halaman berikutnya"
              >
                Berikutnya
                <ChevronRight className="size-4" />
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
