"use client";

import { useDeferredValue, useEffect, useMemo, useState } from "react";
import {
  RefreshCw,
  BarChart3,
  MessageSquareQuote,
  Search,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, PageHeader, StatusBadge } from "./primitives";
import { cn } from "@/lib/utils";
import { fetchAdminFeedback } from "@/features/admin/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import styles from "./admin-ingestion.module.css";
import type { FeedbackItem } from "@/features/admin/types";

function safeDate(value: string) {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatDateTime(value: string) {
  const d = safeDate(value);
  if (!d) return "—";
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

function relativeTime(value: string) {
  const d = safeDate(value);
  if (!d) return "—";
  const diff = Date.now() - d.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "Baru saja";
  if (minutes < 60) return `${minutes} menit lalu`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} jam lalu`;
  const days = Math.floor(hours / 24);
  return `${days} hari lalu`;
}

const issueLabels: Record<string, string> = {
  citation_incorrect: "Sumber tidak sesuai",
  answer_incomplete: "Jawaban kurang lengkap",
  irrelevant: "Tidak relevan",
  outdated: "Informasi usang",
};

const filterOptions = [
  { value: "all", label: "Semua" },
  { value: "helpful", label: "Membantu" },
  { value: "not_helpful", label: "Perlu perbaikan" },
] as const;

export function AdminFeedback() {
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [search, setSearch] = useState("");
  const [rating, setRating] = useState("all");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);
  const [selected, setSelected] = useState<FeedbackItem | null>(null);
  const deferredSearch = useDeferredValue(search.toLowerCase());

  useEffect(() => {
    const controller = new AbortController();
    fetchAdminFeedback(controller.signal)
      .then((feedback) => {
        if (controller.signal.aborted) return;
        setItems(feedback);
        setError(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
    return () => controller.abort();
  }, [reloadKey]);

  const stats = useMemo(() => {
    const total = items.length;
    const helpful = items.filter((i) => i.rating === "helpful").length;
    const notHelpful = items.filter((i) => i.rating === "not_helpful").length;
    const withComment = items.filter((i) => i.comment).length;
    return { total, helpful, notHelpful, withComment };
  }, [items]);

  const filtered = useMemo(
    () =>
      items.filter(
        (item) =>
          (rating === "all" || item.rating === rating) &&
          `${item.question} ${item.comment ?? ""}`.toLowerCase().includes(deferredSearch)
      ),
    [deferredSearch, items, rating]
  );

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const start = (currentPage - 1) * pageSize;
  const visibleItems = filtered.slice(start, start + pageSize);
  const reload = () => {
    setIsLoading(true);
    setError(false);
    setReloadKey((key) => key + 1);
  };
  return (
    <div className={`${styles.ingestion} space-y-6`}>
      <PageHeader
        eyebrow="Evaluasi"
        title="Feedback pengguna"
        description="Tinjau penilaian dan masukan pengguna untuk meningkatkan kualitas jawaban."
        actions={
          <Button variant="outline" disabled={isLoading} onClick={reload}>
            <RefreshCw className={cn("size-4", isLoading && "animate-spin")} /> Muat ulang
          </Button>
        }
      />
      {isLoading ? (
        <div aria-label="Memuat feedback" aria-busy="true" className="space-y-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-80 w-full" />
        </div>
      ) : error ? (
        <div role="alert" className="rounded-xl border border-line bg-white p-6">
          <p className="text-sm text-red">
            Feedback belum dapat dimuat. Periksa koneksi dan coba lagi.
          </p>
          <Button className="mt-4" variant="outline" onClick={reload}>
            Coba lagi
          </Button>
        </div>
      ) : (
        <>
          {/* Stats */}
          <div className="grid gap-4 sm:grid-cols-3">
            <Card className="py-0">
              <CardContent className="flex items-center gap-3 py-4">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-surface-soft">
                  <BarChart3 className="size-5 text-tinta" />
                </span>
                <div>
                  <p className="text-xs text-muted-text">Total feedback</p>
                  <p className="text-2xl font-semibold tabular-nums text-tinta">{stats.total}</p>
                </div>
              </CardContent>
            </Card>
            <Card className="py-0">
              <CardContent className="flex items-center gap-3 py-4">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-teal-soft">
                  <ThumbsUp className="size-5 text-forest" />
                </span>
                <div>
                  <p className="text-xs text-muted-text">Membantu</p>
                  <p className="text-2xl font-semibold tabular-nums text-forest">
                    {stats.helpful}
                    {stats.total > 0 && (
                      <span className="ml-1 text-sm font-normal text-muted-text">
                        ({Math.round((stats.helpful / stats.total) * 100)}%)
                      </span>
                    )}
                  </p>
                </div>
              </CardContent>
            </Card>
            <Card className="py-0">
              <CardContent className="flex items-center gap-3 py-4">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-red-soft">
                  <ThumbsDown className="size-5 text-red" />
                </span>
                <div>
                  <p className="text-xs text-muted-text">Perlu perbaikan</p>
                  <p className="text-2xl font-semibold tabular-nums text-red">
                    {stats.notHelpful}
                    {stats.total > 0 && (
                      <span className="ml-1 text-sm font-normal text-muted-text">
                        ({Math.round((stats.notHelpful / stats.total) * 100)}%)
                      </span>
                    )}
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Search + filter */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-56">
              <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-text" />
              <Input
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
                aria-label="Cari pertanyaan atau komentar"
                placeholder="Cari pertanyaan atau komentar..."
                className="pl-8"
              />
            </div>
            <div className="flex flex-wrap gap-1.5">
              {filterOptions.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  aria-pressed={rating === opt.value}
                  onClick={() => {
                    setRating(opt.value);
                    setPage(1);
                  }}
                  className={cn(
                    "min-h-10 rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors",
                    rating === opt.value
                      ? "bg-javanese text-white"
                      : "bg-surface-soft text-muted-text hover:bg-teal-soft hover:text-tinta"
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {filtered.length === 0 ? (
            <EmptyState
              icon={MessageSquareQuote}
              title={items.length ? "Tidak ada feedback yang cocok" : "Belum ada feedback"}
              hint={
                items.length
                  ? "Coba kata kunci lain atau tampilkan semua penilaian."
                  : "Penilaian dan komentar pengguna akan muncul di sini."
              }
              action={
                items.length ? (
                  <Button
                    variant="outline"
                    onClick={() => {
                      setSearch("");
                      setRating("all");
                      setPage(1);
                    }}
                  >
                    Reset filter
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <div className="overflow-hidden rounded-xl border border-line bg-white">
              <Table aria-label="Daftar feedback pengguna" className="min-w-[720px]">
                <TableHeader className="bg-surface-soft">
                  <TableRow className="border-line">
                    {["Pertanyaan dan komentar", "Penilaian", "Diterima", "Tindakan"].map(
                      (label) => (
                        <TableHead scope="col" key={label} className="px-4 text-muted-text">
                          {label}
                        </TableHead>
                      )
                    )}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleItems.map((item) => (
                    <TableRow key={item.feedback_id} className="border-line">
                      <TableCell className="max-w-md whitespace-normal px-4 py-4">
                        <p className="line-clamp-2 font-medium text-tinta">
                          {item.question || "Pertanyaan tidak tersedia"}
                        </p>
                        <p className="mt-1 line-clamp-2 text-xs text-muted-text">
                          {item.comment?.trim() || "Tanpa komentar tambahan."}
                        </p>
                      </TableCell>
                      <TableCell className="px-4">
                        <StatusBadge tone={item.rating === "helpful" ? "success" : "danger"}>
                          {item.rating === "helpful" ? "Membantu" : "Perlu perbaikan"}
                        </StatusBadge>
                      </TableCell>
                      <TableCell className="px-4 text-xs text-muted-text">
                        <span title={formatDateTime(item.created_at)}>
                          {relativeTime(item.created_at)}
                        </span>
                      </TableCell>
                      <TableCell className="px-4">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setSelected(item)}
                          aria-label={`Detail feedback: ${item.question}`}
                        >
                          Detail
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3 text-xs text-muted-text">
                <label className="flex items-center gap-2">
                  Baris per halaman
                  <select
                    className="min-h-9 rounded-md border border-line bg-white px-2 text-tinta"
                    value={pageSize}
                    onChange={(event) => {
                      setPageSize(Number(event.target.value));
                      setPage(1);
                    }}
                  >
                    {[5, 10, 20, 50].map((size) => (
                      <option key={size} value={size}>
                        {size}
                      </option>
                    ))}
                  </select>
                </label>
                <span role="status">
                  {start + 1}–{Math.min(start + pageSize, filtered.length)} dari {filtered.length}{" "}
                  feedback
                </span>
                <nav aria-label="Pagination feedback" className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={currentPage === 1}
                    onClick={() => setPage(currentPage - 1)}
                  >
                    Sebelumnya
                  </Button>
                  <span>
                    {currentPage} / {pageCount}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={currentPage === pageCount}
                    onClick={() => setPage(currentPage + 1)}
                  >
                    Berikutnya
                  </Button>
                </nav>
              </div>
            </div>
          )}
        </>
      )}
      <Dialog
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      >
        <DialogContent
          className={`admin-theme ${styles.ingestion} ${styles.detailModal} max-h-[85dvh] overflow-y-auto p-6 sm:max-w-xl`}
        >
          <DialogHeader className="pr-8">
            <DialogTitle>Detail feedback</DialogTitle>
            <DialogDescription>Penilaian dan komentar pengguna terhadap jawaban.</DialogDescription>
          </DialogHeader>
          {selected && (
            <div className="space-y-5">
              <div className="flex flex-wrap gap-2">
                <StatusBadge tone={selected.rating === "helpful" ? "success" : "danger"}>
                  {selected.rating === "helpful" ? "Membantu" : "Perlu perbaikan"}
                </StatusBadge>
                {selected.issue_category && (
                  <StatusBadge tone="warning">
                    {issueLabels[selected.issue_category] ??
                      selected.issue_category.replaceAll("_", " ")}
                  </StatusBadge>
                )}
              </div>
              <div>
                <h3 className="mb-2 text-xs font-semibold text-muted-text">Pertanyaan</h3>
                <p className="whitespace-pre-wrap break-words text-sm">
                  {selected.question || "Pertanyaan tidak tersedia"}
                </p>
              </div>
              <div className="rounded-lg border border-line bg-surface-soft p-4">
                <h3 className="mb-2 text-xs font-semibold text-muted-text">Komentar pengguna</h3>
                <p className="whitespace-pre-wrap break-words text-sm">
                  {selected.comment?.trim() || "Tanpa komentar tambahan."}
                </p>
              </div>
              <dl className="grid gap-4 border-t border-line pt-4 sm:grid-cols-2">
                <div>
                  <dt className="text-xs text-muted-text">Pengguna</dt>
                  <dd className="mt-1 break-all font-mono text-xs">{selected.user_id}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-text">Diterima</dt>
                  <dd className="mt-1 text-sm">{formatDateTime(selected.created_at)}</dd>
                </div>
              </dl>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
