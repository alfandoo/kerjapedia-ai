"use client";

import Link from "next/link";
import styles from "./regulation-search.module.css";
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
import { Skeleton } from "@/components/ui/skeleton";
import { useSettings } from "@/features/settings";
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
        className="h-12 w-full min-w-0 rounded-xl border-border bg-card px-4 text-sm text-foreground transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:border-ring data-[size=default]:h-12 data-[state=open]:border-javanese"
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent
        position="popper"
        align="start"
        className="max-h-[min(220px,calc(100vh-120px))] overflow-y-auto border border-border bg-popover p-1 text-popover-foreground shadow-lg [scrollbar-color:var(--muted-foreground)_var(--popover)] [scrollbar-gutter:stable] [scrollbar-width:thin]"
      >
        {options.map((option) => (
          <SelectItem
            key={option.value}
            value={option.value}
            className="rounded-md text-foreground focus:bg-accent focus:text-accent-foreground"
          >
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function RegulationSearch() {
  const { t: translate } = useSettings();
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
    if (status === "active") return translate("search.statusActive");
    if (status === "needs_verification") return translate("search.statusNeedsVerification");
    return status.replaceAll("_", " ");
  }

  return (
    <section className={`${styles.searchPage} w-full text-foreground`}>
      <div className="mb-7 max-w-[760px]">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-javanese">
          {translate("search.eyebrow")}
        </p>
        <h1 className="font-display text-[clamp(34px,3.5vw,46px)] font-medium leading-[1.12] tracking-[-0.02em] text-javanese-deep">
          {translate("search.title")}
        </h1>
        <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
          {translate("search.subtitle")}
        </p>
      </div>

      <div className="mb-6 grid grid-cols-1 items-stretch gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(240px,1.6fr)_repeat(4,minmax(130px,1fr))_48px]">
        <label
          className={`${styles.searchField} flex h-12 min-w-0 items-center gap-3 rounded-xl border border-input bg-card px-4 transition-colors hover:border-javanese hover:bg-accent focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/40 sm:col-span-2 xl:col-span-1`}
          htmlFor="regulation-search"
        >
          <SearchIcon className="size-5 [stroke-width:1.8] shrink-0 text-javanese" />
          <input
            id="regulation-search"
            aria-label={translate("search.searchAria")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={translate("search.placeholder")}
            className="h-full w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </label>
        <FilterSelect
          id="topic-filter"
          label={translate("search.filterTopic")}
          value={topic}
          options={topics.map((item) => ({
            value: item,
            label: item === "all" ? translate("search.allTopics") : item.replaceAll("_", " "),
          }))}
          onValueChange={setTopic}
        />
        <FilterSelect
          id="type-filter"
          label={translate("search.filterType")}
          value={regulationType}
          options={regulationTypes.map((item) => ({
            value: item,
            label: item === "all" ? translate("search.allTypes") : item,
          }))}
          onValueChange={setRegulationType}
        />
        <FilterSelect
          id="year-filter"
          label={translate("search.filterYear")}
          value={year || "all"}
          options={years.map((item) => ({
            value: item,
            label: item === "all" ? translate("search.allYears") : item,
          }))}
          onValueChange={(value) => setYear(value === "all" ? "" : value)}
        />
        <FilterSelect
          id="status-filter"
          label={translate("search.filterStatus")}
          value={status}
          options={[
            { value: "all", label: translate("search.allStatus") },
            { value: "active", label: translate("search.statusActive") },
            { value: "needs_verification", label: translate("search.statusNeedsVerification") },
          ]}
          onValueChange={setStatus}
        />
        {hasFilters ? (
          <button
            type="button"
            onClick={resetSearch}
            aria-label={translate("search.reset")}
            title={translate("search.reset")}
            className="inline-flex size-12 shrink-0 items-center justify-center rounded-xl border border-border bg-card text-muted-foreground transition hover:border-javanese hover:bg-accent hover:text-javanese"
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
          {translate("search.apiError")}
        </div>
      ) : null}

      <div aria-label={translate("search.listAria")} aria-busy={loading} className="overflow-x-auto">
        {loading ? (
          <div className="overflow-x-auto rounded-xl border border-border bg-card">
            <div className="flex items-center gap-4 border-b border-border bg-muted px-4 py-3">
              <Skeleton className="h-3 w-[17%] max-w-[120px]" />
              <Skeleton className="h-3 w-[38%] max-w-[220px]" />
              <Skeleton className="h-3 w-[10%] max-w-[60px]" />
              <Skeleton className="h-3 w-[16%] max-w-[100px]" />
              <Skeleton className="h-3 w-[19%] max-w-[120px] ml-auto" />
            </div>
            {Array.from({ length: 5 }).map((_, index) => (
              <div
                key={index}
                className="flex items-center gap-4 border-b border-border px-4 py-4 last:border-b-0"
              >
                <Skeleton className="h-4 w-[17%] max-w-[120px]" />
                <Skeleton className="h-4 w-[38%] max-w-[220px]" />
                <Skeleton className="h-4 w-[10%] max-w-[60px]" />
                <Skeleton className="h-3 w-[16%] max-w-[100px]" />
                <div className="ml-auto flex gap-2">
                  <Skeleton className="h-10 w-28 rounded-lg" />
                  <Skeleton className="size-10 rounded-lg" />
                </div>
              </div>
            ))}
          </div>
        ) : null}

        {!loading && filtered.length === 0 ? (
          <div className="py-16 text-center">
            <h2 className="text-lg font-semibold text-foreground">{translate("search.emptyTitle")}</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              {translate("search.emptyDescription")}
            </p>
            <button
              type="button"
              onClick={resetSearch}
              className="mt-5 h-11 rounded-xl border border-input px-5 text-sm font-semibold text-javanese transition hover:border-javanese hover:bg-accent"
            >
              {translate("search.clearFilters")}
            </button>
          </div>
        ) : null}

        {!loading && filtered.length > 0 ? (
          <div className="overflow-x-auto rounded-xl border border-border bg-card">
            <table className="w-full min-w-[900px] border-collapse text-left">
              <thead>
                <tr className="border-b border-border bg-muted">
                  <th className="w-[17%] px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    {translate("search.colType")}
                  </th>
                  <th className="w-[38%] px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    {translate("search.colDocument")}
                  </th>
                  <th className="w-[10%] px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    {translate("search.colYear")}
                  </th>
                  <th className="w-[16%] px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    {translate("search.colStatus")}
                  </th>
                  <th className="w-[19%] px-4 py-3 text-right text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    {translate("search.colAccess")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((document) => (
                  <tr
                    className="border-b border-border transition-colors last:border-b-0 hover:bg-accent"
                    key={document.document_id}
                  >
                    <td className="px-4 py-4 align-middle">
                      <span className="block text-[11px] font-semibold uppercase tracking-[0.06em] text-forest">
                        {document.regulation_type}
                      </span>
                      <small className="mt-1 block text-[10px] leading-relaxed text-muted-foreground">
                        {translate("search.numberYear")
                          .replace("{number}", String(document.number))
                          .replace("{year}", String(document.year))}
                      </small>
                    </td>
                    <td className="px-4 py-4 align-middle">
                      <Link
                        href={`/documents/${document.document_id}`}
                        className="font-display text-[clamp(15px,1.3vw,18px)] font-medium leading-snug tracking-[-0.01em] text-foreground transition hover:text-teal-strong"
                      >
                        {document.title}
                      </Link>
                      <p className="mt-1.5 truncate text-[11px] capitalize leading-relaxed text-muted-foreground">
                        {document.topics.map((item) => item.replaceAll("_", " ")).join(" · ")}
                      </p>
                    </td>
                    <td className="px-4 py-4 align-middle font-mono text-xs text-muted-foreground">
                      {document.year}
                    </td>
                    <td className="px-4 py-4 align-middle">
                      <span
                        className={`inline-flex items-center gap-2 whitespace-nowrap text-[11px] ${
                          document.legal_status === "active" ? "text-forest" : "text-muted-foreground"
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
                          className="inline-flex h-10 items-center whitespace-nowrap rounded-lg border border-input px-3.5 text-xs font-semibold text-javanese transition hover:border-javanese hover:bg-accent"
                        >
                          {translate("search.openSource")}
                        </a>
                        <a
                          href={document.pdf_url}
                          download
                          aria-label={`${translate("search.downloadPdf")} ${document.short_title}`}
                          title={translate("search.downloadPdf")}
                          className="inline-flex size-10 shrink-0 items-center justify-center rounded-lg border border-input text-javanese transition hover:border-javanese hover:bg-accent"
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
            <span className="text-xs text-muted-foreground">
              {translate("search.fromTo")
                .replace("{start}", String(Math.min((safePage - 1) * PAGE_SIZE + 1, filtered.length)))
                .replace("{end}", String(Math.min(safePage * PAGE_SIZE, filtered.length)))
                .replace("{total}", String(filtered.length))}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPage(safePage - 1)}
                disabled={safePage <= 1}
                className="inline-flex h-9 items-center gap-1 rounded-lg border border-input px-3 text-xs font-semibold text-javanese transition hover:border-javanese hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
                aria-label={translate("search.prevAria")}
              >
                <ChevronLeft className="size-4" />
                {translate("search.prev")}
              </button>
              <span className="min-w-[72px] text-center text-xs font-semibold text-foreground">
                {safePage} / {totalPages}
              </span>
              <button
                type="button"
                onClick={() => setPage(safePage + 1)}
                disabled={safePage >= totalPages}
                className="inline-flex h-9 items-center gap-1 rounded-lg border border-input px-3 text-xs font-semibold text-javanese transition hover:border-javanese hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
                aria-label={translate("search.nextAria")}
              >
                {translate("search.next")}
                <ChevronRight className="size-4" />
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
