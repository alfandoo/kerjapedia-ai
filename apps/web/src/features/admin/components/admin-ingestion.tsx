"use client";

import Link from "next/link";
import styles from "./admin-ingestion.module.css";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  FileSearch,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { Toaster, toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Callout, EmptyState, PageHeader, StatusBadge } from "./primitives";
import { cn } from "@/lib/utils";
import { createIngestionJob, fetchIngestionJobs } from "@/features/admin/api";
import type { IngestionJob } from "@/features/admin/types";

const jobLabels: Record<IngestionJob["status"], string> = {
  completed: "Selesai",
  needs_review: "Perlu review",
  failed: "Gagal",
  running: "Berjalan",
  queued: "Antre",
};

const jobTones: Record<
  IngestionJob["status"],
  "success" | "warning" | "danger" | "info" | "neutral"
> = {
  completed: "success",
  needs_review: "warning",
  failed: "danger",
  running: "info",
  queued: "neutral",
};

function safeDate(value: string) {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatDateTime(value: string) {
  const d = safeDate(value);
  if (!d) return "Tidak diketahui";
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
  if (!d) return "Tidak diketahui";
  const diff = Date.now() - d.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "Baru saja";
  if (minutes < 60) return `${minutes} menit lalu`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} jam lalu`;
  const days = Math.floor(hours / 24);
  return `${days} hari lalu`;
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return "Belum ada data";
  if (seconds < 60) return "Kurang dari 1 menit";
  const mins = Math.round(seconds / 60);
  if (mins < 60) return `${mins} menit`;
  const hours = Math.floor(mins / 60);
  const remMins = mins % 60;
  return `${hours} jam ${remMins > 0 ? `${remMins} menit` : ""}`.trim();
}

function ProgressEta({ job }: { job: IngestionJob }) {
  const elapsed = (job as IngestionJob & { elapsed_seconds?: number }).elapsed_seconds ?? null;
  const avg =
    (job as IngestionJob & { avg_duration_seconds?: number }).avg_duration_seconds ?? null;
  const isActive = job.status === "running" || job.status === "queued";
  if (!isActive) return null;

  return (
    <div className="space-y-1.5 rounded-lg border border-line bg-surface-soft/60 px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold text-tinta">
          {job.status === "running" ? "Sedang memproses" : "Menunggu antrean"}
        </p>
        {elapsed != null ? (
          <span className="font-mono text-[11px] text-muted-text tabular-nums">
            berjalan {formatDuration(elapsed)}
          </span>
        ) : null}
      </div>
      <p className="text-[11px] text-muted-text">
        {job.status === "queued"
          ? "Pemrosesan akan dimulai setelah antrean tersedia."
          : avg != null && avg > 0 && elapsed != null
            ? elapsed < avg
              ? `Estimasi sisa waktu ${formatDuration(avg - elapsed)}. Durasi dapat berubah.`
              : "Proses lebih lama dari rata-rata. Status akan diperbarui otomatis."
            : "Estimasi waktu belum tersedia. Status akan diperbarui otomatis."}
      </p>
    </div>
  );
}

const filterOptions = [
  { value: "all", label: "Semua" },
  { value: "completed", label: "Selesai" },
  { value: "needs_review", label: "Review" },
  { value: "failed", label: "Gagal" },
  { value: "running", label: "Berjalan" },
  { value: "queued", label: "Antre" },
] as const;

function IngestionSkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-3 w-40" />
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-80" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-[76px] rounded-xl" />
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {Array.from({ length: 5 }).map((_, index) => (
          <Skeleton key={index} className="h-8 w-20 rounded-lg" />
        ))}
      </div>
      <div className="grid min-w-0 gap-6">
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-24 w-full rounded-xl" />
          ))}
        </div>
        <div className="space-y-4">
          <Skeleton className="h-64 w-full rounded-xl" />
          <Skeleton className="h-32 w-full rounded-xl" />
        </div>
      </div>
    </div>
  );
}

export function AdminIngestion() {
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadStatus, setLoadStatus] = useState("");
  const [loadError, setLoadError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [rerunPending, setRerunPending] = useState(false);
  const rerunBusy = useRef(false);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchIngestionJobs(controller.signal)
      .then((items) => {
        if (controller.signal.aborted) return;
        setLoadError(false);
        setJobs(items);
        setSelectedJobId(items[0]?.job_id ?? null);
        setLoadStatus(items.length ? "" : "Belum ada job ingestion — mulai dari halaman dokumen.");
      })
      .catch((err) => {
        if ((err as Error)?.name === "AbortError") return;
        setLoadError(true);
        setLoadStatus("Daftar pemrosesan belum dapat dimuat. Periksa koneksi lalu coba lagi.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
    return () => controller.abort();
  }, [reloadKey]);

  const stats = useMemo(() => {
    const total = jobs.length;
    const completed = jobs.filter((j) => j.status === "completed").length;
    const needsReview = jobs.filter((j) => j.status === "needs_review").length;
    const failed = jobs.filter((j) => j.status === "failed").length;
    const running = jobs.filter((j) => j.status === "running" || j.status === "queued").length;
    return { total, completed, needsReview, failed, running };
  }, [jobs]);

  const filtered = useMemo(
    () => jobs.filter((job) => filter === "all" || job.status === filter),
    [filter, jobs]
  );
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pageStart = (currentPage - 1) * pageSize;
  const visibleJobs = filtered.slice(pageStart, pageStart + pageSize);
  const showDetail = (jobId: string) => {
    setSelectedJobId(jobId);
    setDetailOpen(true);
  };
  const selectedJob = filtered.find((job) => job.job_id === selectedJobId) ?? filtered[0] ?? null;

  const hasActiveJobs = jobs.some((job) => job.status === "running" || job.status === "queued");
  useEffect(() => {
    if (!hasActiveJobs) return;
    const controller = new AbortController();
    let inFlight = false;
    pollingRef.current = setInterval(async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const items = await fetchIngestionJobs(controller.signal);
        if (!controller.signal.aborted) {
          setJobs(items);
          setLoadStatus("Status diperbarui otomatis setiap 3 detik.");
        }
      } catch {
        if (!controller.signal.aborted)
          setLoadStatus(
            "Pembaruan tertunda. Menampilkan status terakhir; mencoba kembali otomatis."
          );
      } finally {
        inFlight = false;
      }
    }, 3000);
    return () => {
      controller.abort();
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [hasActiveJobs]);

  async function rerun(documentId: string, force = false) {
    if (
      rerunBusy.current ||
      jobs.some(
        (job) =>
          job.document_id === documentId && (job.status === "running" || job.status === "queued")
      )
    )
      return;
    rerunBusy.current = true;
    setRerunPending(true);
    try {
      const next = await createIngestionJob(documentId, force);
      setJobs((current) => {
        const withoutPrevious = current.filter((job) => job.job_id !== next.job_id);
        return [next, ...withoutPrevious];
      });
      setSelectedJobId(next.job_id);
      setFilter("all");
      setPage(1);
      toast.info(
        force ? `Ingestion dipaksa diulang — ${documentId}` : `Ingestion dimulai — ${documentId}`
      );
    } catch {
      toast.error("Gagal memulai pemrosesan. Periksa koneksi lalu coba lagi.");
    } finally {
      rerunBusy.current = false;
      setRerunPending(false);
    }
  }

  async function rerunForce(documentId: string) {
    if (
      !window.confirm(
        `Dokumen ${documentId} sudah selesai diingest. Paksa ulang? Ini akan membuat build baru dan menghabiskan waktu komputasi.`
      )
    )
      return;
    await rerun(documentId, true);
  }

  return (
    <div className={`${styles.ingestion} space-y-6`}>
      <Toaster position="bottom-right" richColors />

      <PageHeader
        eyebrow="Pengelolaan dokumen"
        title="Pemrosesan dokumen"
        description="Pantau antrean, periksa hasil, dan tangani dokumen yang perlu ditinjau."
        actions={
          <Button
            variant="outline"
            className="min-h-11"
            disabled={isLoading}
            onClick={() => {
              setIsLoading(true);
              setLoadError(false);
              setReloadKey((key) => key + 1);
            }}
          >
            <RefreshCw /> Muat ulang
          </Button>
        }
      />
      {loadStatus && (
        <p role="status" className="text-xs text-muted-text">
          {loadStatus}
        </p>
      )}

      {isLoading ? (
        <div role="status" aria-label="Memuat daftar ingestion">
          <IngestionSkeleton />
        </div>
      ) : loadError ? (
        <div role="alert">
          <Callout tone="danger" title="Data belum tersedia">
            {loadStatus}
          </Callout>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Stats row */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              {
                label: "Total pekerjaan",
                value: stats.total,
                icon: Database,
                color: "text-tinta",
                bg: "bg-surface-soft",
              },
              {
                label: "Selesai",
                value: stats.completed,
                icon: CheckCircle2,
                color: "text-forest",
                bg: "bg-teal-soft",
              },
              {
                label: "Perlu review",
                value: stats.needsReview,
                icon: AlertTriangle,
                color: "text-amber",
                bg: "bg-amber-soft",
              },
              {
                label: "Gagal",
                value: stats.failed,
                icon: XCircle,
                color: "text-red",
                bg: "bg-red-soft",
              },
            ].map((stat) => (
              <Card key={stat.label} className="py-0">
                <CardContent className="flex items-center gap-3 py-4">
                  <span
                    className={cn(
                      "flex size-10 shrink-0 items-center justify-center rounded-xl",
                      stat.bg
                    )}
                  >
                    <stat.icon className={cn("size-5", stat.color)} />
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs text-muted-text">{stat.label}</p>
                    <p className={cn("text-2xl font-semibold tabular-nums", stat.color)}>
                      {stat.value}
                    </p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="grid min-w-0 gap-6">
            {/* Left — job list */}
            <div className="min-w-0 space-y-4">
              {/* Filter bar */}
              <div className="flex flex-wrap items-center gap-2">
                {filterOptions.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    aria-pressed={filter === opt.value}
                    onClick={() => {
                      setFilter(opt.value);
                      setPage(1);
                    }}
                    className={cn(
                      "min-h-11 rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors",
                      filter === opt.value
                        ? "bg-javanese text-white"
                        : "bg-surface-soft text-muted-text hover:bg-teal-soft hover:text-tinta"
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
                <span className="ml-auto text-xs text-muted-text">
                  {filtered.length} dari {jobs.length} pekerjaan
                </span>
              </div>

              {/* Job list */}
              {filtered.length === 0 ? (
                <EmptyState
                  icon={FileSearch}
                  title={
                    jobs.length === 0
                      ? "Belum ada pemrosesan"
                      : "Tidak ada pekerjaan dengan status ini"
                  }
                  hint={
                    jobs.length === 0
                      ? "Unggah PDF untuk mulai menyiapkan dokumen."
                      : "Pilih status lain untuk melihat pekerjaan."
                  }
                    action={
                      jobs.length === 0 ? (
                        <Button asChild className="min-h-11">
                          <Link href="/admin/upload">Upload PDF</Link>
                        </Button>
                      ) : (
                        <Button
                          variant="outline"
                          className="min-h-11"
                          onClick={() => {
                            setFilter("all");
                            setPage(1);
                          }}
                        >
                          Tampilkan semua
                        </Button>
                      )
                    }
                />
              ) : (
                <div className="overflow-hidden rounded-xl border border-line bg-white">
                  <Table className="min-w-[600px]" aria-label="Daftar ingestion dokumen">
                    <TableHeader className="bg-surface-soft">
                      <TableRow className="border-line hover:bg-transparent">
                        <TableHead scope="col" className="px-4 text-muted-text">
                          Dokumen
                        </TableHead>
                        <TableHead scope="col" className="text-muted-text">
                          Status
                        </TableHead>
                        <TableHead scope="col" className="text-muted-text">
                          Diperbarui
                        </TableHead>
                        <TableHead scope="col" className="px-4 text-right text-muted-text">
                          Tindakan
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {visibleJobs.map((job) => {
                        const selected = job.job_id === selectedJob?.job_id;
                        return (
                          <TableRow
                            key={job.job_id}
                            data-state={selected ? "selected" : undefined}
                            className="border-line"
                          >
                            <TableCell className="max-w-64 whitespace-normal px-4 py-4">
                              <button
                                type="button"
                                title={job.document_id}
                                onClick={() => showDetail(job.job_id)}
                                className="block min-h-11 text-left text-sm font-semibold text-tinta underline-offset-4 hover:underline break-all"
                              >
                                {job.document_id}
                              </button>
                              <p
                                title={job.job_id}
                                className="mt-1 truncate font-mono text-xs text-muted-text"
                              >
                                {job.job_id}
                              </p>
                              {job.result?.chunk_count != null && (
                                <p className="mt-1 text-xs text-muted-text">
                                  {job.result.chunk_count} chunk
                                </p>
                              )}
                              {job.error && (
                                <p title={job.error} className="mt-1 line-clamp-2 text-xs text-red">
                                  {job.error}
                                </p>
                              )}
                            </TableCell>
                            <TableCell>
                              <StatusBadge tone={jobTones[job.status]}>
                                {jobLabels[job.status]}
                              </StatusBadge>
                            </TableCell>
                            <TableCell className="text-xs text-muted-text">
                              <span title={formatDateTime(job.updated_at)}>
                                {relativeTime(job.updated_at)}
                              </span>
                            </TableCell>
                            <TableCell className="px-4 text-right">
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="mr-2 min-h-11"
                                aria-label={`Detail ${job.document_id}`}
                                aria-controls="ingestion-detail"
                                onClick={() => showDetail(job.job_id)}
                              >
                                <FileSearch className="size-3.5" /> Detail
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="min-h-11 shrink-0"
                                aria-label={`Jalankan ulang ${job.document_id}`}
                                disabled={
                                  rerunPending ||
                                  jobs.some(
                                    (item) =>
                                      item.document_id === job.document_id &&
                                      (item.status === "running" || item.status === "queued")
                                  )
                                }
                                title={
                                  job.status === "completed"
                                    ? "Klik untuk memaksa ulang (force)"
                                    : undefined
                                }
                                onClick={(event) => {
                                  event.stopPropagation();
                                  if (job.status === "completed") {
                                    void rerunForce(job.document_id);
                                  } else {
                                    void rerun(job.document_id);
                                  }
                                }}
                              >
                                <RefreshCw className="size-3.5" /> Ulangi
                              </Button>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                  <div className="flex flex-wrap items-center justify-between gap-4 border-t border-line px-4 py-3 text-xs text-muted-text">
                    <label className="flex items-center gap-2">
                      Baris per halaman
                      <select
                        value={pageSize}
                        onChange={(event) => {
                          setPageSize(Number(event.target.value));
                          setPage(1);
                        }}
                        className="min-h-11 rounded-md border border-line bg-white px-2 text-sm text-tinta focus-visible:outline-2 focus-visible:outline-forest"
                      >
                        {[5, 10, 20, 50].map((size) => (
                          <option key={size} value={size}>
                            {size}
                          </option>
                        ))}
                      </select>
                    </label>
                    <span role="status">
                      {pageStart + 1} sampai {Math.min(pageStart + pageSize, filtered.length)}{" "}
                      dari {filtered.length} pekerjaan
                    </span>
                    <nav
                      aria-label="Pagination daftar ingestion"
                      className="flex items-center gap-2"
                    >
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="min-h-11"
                        disabled={currentPage === 1}
                        onClick={() => setPage(currentPage - 1)}
                      >
                        Sebelumnya
                      </Button>
                      <span className="tabular-nums">
                        {currentPage} / {pageCount}
                      </span>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="min-h-11"
                        disabled={currentPage === pageCount}
                        onClick={() => setPage(currentPage + 1)}
                      >
                        Berikutnya
                      </Button>
                    </nav>
                  </div>
                </div>
              )}
            </div>

            <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
              <DialogContent
                id="ingestion-detail"
                className={`admin-theme ${styles.ingestion} ${styles.detailModal} max-h-[85dvh] overflow-y-auto sm:max-w-xl p-6`}
              >
                <DialogHeader className="pr-8">
                  <DialogTitle>Detail pemrosesan</DialogTitle>
                  <DialogDescription>
                    Status dan hasil pemrosesan dokumen dari API.
                  </DialogDescription>
                </DialogHeader>
                {loadStatus && (
                  <p role="status" className="text-xs text-muted-text">
                    {loadStatus}
                  </p>
                )}
                {selectedJob ? (
                  <>
                    <div className="space-y-5">
                      <p className="text-sm leading-relaxed text-muted-text">
                        Status tahapan terperinci belum tersedia. Ringkasan di bawah mengikuti
                        status pekerjaan dari server.
                      </p>

                      <ProgressEta job={selectedJob} />

                      {/* Metadata */}
                      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
                        <div className="min-w-0">
                          <dt className="text-xs text-muted-text">Job ID</dt>
                          <dd className="break-all font-mono text-xs font-medium">
                            {selectedJob.job_id}
                          </dd>
                        </div>
                        <div className="min-w-0">
                          <dt className="text-xs text-muted-text">Dokumen</dt>
                          <dd className="break-words text-sm font-medium">
                            {selectedJob.document_id}
                          </dd>
                        </div>
                        <div className="min-w-0">
                          <dt className="text-xs text-muted-text">Status</dt>
                          <dd>
                            <StatusBadge tone={jobTones[selectedJob.status]}>
                              {jobLabels[selectedJob.status]}
                            </StatusBadge>
                          </dd>
                        </div>
                        <div className="min-w-0">
                          <dt className="text-xs text-muted-text">Chunk</dt>
                          <dd className="font-mono text-sm font-medium tabular-nums">
                            {selectedJob.result?.chunk_count ?? "Belum ada data"}
                          </dd>
                        </div>
                        <div className="min-w-0">
                          <dt className="text-xs text-muted-text">Dibuat</dt>
                          <dd className="text-sm">{formatDateTime(selectedJob.created_at)}</dd>
                        </div>
                        <div className="min-w-0">
                          <dt className="text-xs text-muted-text">Diperbarui</dt>
                          <dd className="text-sm">{formatDateTime(selectedJob.updated_at)}</dd>
                        </div>
                      </dl>
                    </div>

                    {/* Status callout + action */}
                    <div className="space-y-3 border-t border-line pt-4">
                      {selectedJob.status === "failed" ? (
                        <Callout tone="danger" title="Ingestion gagal">
                          {selectedJob.error ?? "Pipeline berhenti karena kegagalan internal."}
                        </Callout>
                      ) : selectedJob.status === "needs_review" ? (
                        <Callout tone="warning" title="Perlu review manual">
                          {selectedJob.error ??
                            "Quality gate tidak lulus. Periksa hasil ekstraksi lalu tandai terverifikasi atau jalankan ulang."}
                        </Callout>
                      ) : selectedJob.status === "completed" ? (
                        <Callout tone="success" title="Pipeline selesai">
                          Pemrosesan selesai. Tinjau dokumen dan status publikasinya sebelum
                          digunakan sebagai sumber jawaban.
                        </Callout>
                      ) : selectedJob.status === "running" ? (
                        <Callout tone="info" title="Sedang diproses">
                          Status diperbarui otomatis. Tidak perlu menjalankan ulang pekerjaan ini.
                        </Callout>
                      ) : (
                        <Callout tone="info" title="Menunggu pemrosesan">
                          Job ini masih dalam antrean.
                        </Callout>
                      )}

                      <Button
                        variant="outline"
                        className="min-h-11 w-full"
                        disabled={
                          rerunPending ||
                          jobs.some(
                            (item) =>
                              item.document_id === selectedJob.document_id &&
                              (item.status === "running" || item.status === "queued")
                          )
                        }
                        onClick={() =>
                          void (selectedJob.status === "completed"
                            ? rerunForce(selectedJob.document_id)
                            : rerun(selectedJob.document_id))
                        }
                      >
                        <RefreshCw className="size-4" />
                        {selectedJob.status === "completed"
                          ? "Paksa ulang (force)"
                          : "Jalankan ulang"}
                      </Button>
                    </div>
                  </>
                ) : (
                  <EmptyState
                    icon={FileSearch}
                    title="Pilih job untuk melihat detail"
                    hint="Pilih tombol Detail pada daftar ingestion."
                  />
                )}
              </DialogContent>
            </Dialog>
          </div>
        </div>
      )}
    </div>
  );
}
