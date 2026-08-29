"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Database,
  FileSearch,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { Toaster, toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Callout, EmptyState, PageHeader, StatusBadge } from "./primitives";
import { cn } from "@/lib/utils";
import { createIngestionJob, fetchIngestionJob, fetchIngestionJobs } from "@/features/admin/api";
import { fallbackIngestionJobs } from "@/features/admin/sample-data";
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

const statusBorder: Record<IngestionJob["status"], string> = {
  completed: "border-l-forest",
  needs_review: "border-l-amber",
  failed: "border-l-red",
  running: "border-l-javanese",
  queued: "border-l-muted-text/30",
};

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

const filterOptions = [
  { value: "all", label: "Semua" },
  { value: "completed", label: "Selesai" },
  { value: "needs_review", label: "Review" },
  { value: "failed", label: "Gagal" },
  { value: "running", label: "Berjalan" },
] as const;

export function AdminIngestion() {
  const [jobs, setJobs] = useState(fallbackIngestionJobs);
  const [filter, setFilter] = useState("all");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(
    fallbackIngestionJobs[1]?.job_id ?? null
  );
  const [loadStatus, setLoadStatus] = useState("Memuat job ingestion...");
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
        if (items.length) {
          setJobs(items);
          setSelectedJobId(items[0].job_id);
        }
        setLoadStatus("Data tersinkron dengan API.");
      })
      .catch(() => setLoadStatus("Menampilkan data contoh — API belum tersedia."));
    return () => controller.abort();
  }, []);

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
  const selectedJob = jobs.find((job) => job.job_id === selectedJobId) ?? null;

  function startPolling(jobId: string) {
    if (pollingRef.current) clearInterval(pollingRef.current);
    pollingRef.current = setInterval(async () => {
      try {
        const updated = await fetchIngestionJob(jobId);
        if (updated.status !== "running" && updated.status !== "queued") {
          if (pollingRef.current) clearInterval(pollingRef.current);
          pollingRef.current = null;
          setJobs((current) => current.map((j) => (j.job_id === jobId ? { ...j, ...updated } : j)));
          toast.success(
            updated.status === "completed"
              ? `Ingestion selesai — ${updated.document_id}`
              : `Ingestion ${jobLabels[updated.status]} — ${updated.document_id}`
          );
        }
      } catch {
        // keep polling, transient network error
      }
    }, 3000);
  }

  async function rerun(documentId: string) {
    try {
      const next = await createIngestionJob(documentId);
      setJobs((current) => [next, ...current]);
      setSelectedJobId(next.job_id);
      toast.info(`Ingestion dimulai — ${documentId}`);
      startPolling(next.job_id);
    } catch {
      toast.error("Gagal memulai ingestion. Periksa koneksi API.");
    }
  }

  return (
    <div className="space-y-6">
      <Toaster position="bottom-right" richColors />

      <PageHeader eyebrow="Pipeline pemrosesan" title="Ingestion" description={loadStatus} />

      {/* Stats row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          {
            label: "Total job",
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

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        {/* Left — job list */}
        <div className="space-y-4">
          {/* Filter bar */}
          <div className="flex flex-wrap items-center gap-2">
            {filterOptions.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setFilter(opt.value)}
                className={cn(
                  "rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors",
                  filter === opt.value
                    ? "bg-javanese text-white"
                    : "bg-surface-soft text-muted-text hover:bg-teal-soft hover:text-tinta"
                )}
              >
                {opt.label}
              </button>
            ))}
            <span className="ml-auto text-xs text-muted-text">
              {filtered.length} dari {jobs.length} job
            </span>
          </div>

          {/* Job list */}
          {filtered.length === 0 ? (
            <EmptyState
              icon={FileSearch}
              title="Tidak ada job ditemukan"
              hint="Ubah filter atau jalankan ingestion dari halaman upload."
            />
          ) : (
            <div className="space-y-2">
              {filtered.map((job) => {
                const selected = job.job_id === selectedJobId;
                return (
                  <div
                    key={job.job_id}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedJobId(job.job_id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelectedJobId(job.job_id);
                      }
                    }}
                    className={cn(
                      "w-full rounded-xl border-l-4 p-4 text-left transition-all",
                      statusBorder[job.status],
                      selected
                        ? "border border-forest/30 bg-teal-soft/40 shadow-sm"
                        : "border border-line bg-white hover:border-forest/20 hover:shadow-sm"
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex items-center gap-2">
                          <p className="truncate text-sm font-semibold text-tinta">
                            {job.document_id}
                          </p>
                          <StatusBadge tone={jobTones[job.status]} pulse={job.status === "running"}>
                            {jobLabels[job.status]}
                          </StatusBadge>
                        </div>
                        <div className="flex items-center gap-3 text-xs text-muted-text">
                          <span className="font-mono">{job.job_id}</span>
                          <span>·</span>
                          <span>{relativeTime(job.updated_at)}</span>
                          {job.result?.chunk_count && (
                            <>
                              <span>·</span>
                              <span className="font-mono">{job.result.chunk_count} chunk</span>
                            </>
                          )}
                        </div>
                        {job.error && (
                          <p className="mt-1 line-clamp-1 text-xs text-red">{job.error}</p>
                        )}
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="shrink-0"
                        aria-label={`Jalankan ulang ${job.document_id}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          void rerun(job.document_id);
                        }}
                      >
                        <RefreshCw className="size-3.5" /> Re-ingest
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right — detail panel */}
        <div className="space-y-4">
          {selectedJob ? (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Detail job</CardTitle>
                </CardHeader>
                <CardContent className="space-y-5">
                  {/* Pipeline stages */}
                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-tinta">Pipeline</p>
                    <div className="space-y-1.5">
                      {[
                        { label: "PDF diekstrak", done: selectedJob.status !== "queued" },
                        {
                          label: "Parsing & chunking",
                          done:
                            selectedJob.status === "completed" ||
                            selectedJob.status === "needs_review" ||
                            selectedJob.status === "failed",
                        },
                        {
                          label: "Embedding & simpan",
                          done: selectedJob.status === "completed",
                        },
                      ].map((stage) => (
                        <div key={stage.label} className="flex items-center gap-2 text-sm">
                          <span
                            className={cn(
                              "flex size-5 shrink-0 items-center justify-center rounded-full",
                              stage.done
                                ? "bg-forest text-white"
                                : "bg-surface-soft text-muted-text"
                            )}
                          >
                            {stage.done ? (
                              <CheckCircle2 className="size-3" />
                            ) : (
                              <Clock className="size-3" />
                            )}
                          </span>
                          <span className={stage.done ? "text-tinta" : "text-muted-text"}>
                            {stage.label}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Metadata */}
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
                    <div className="min-w-0">
                      <dt className="text-xs text-muted-text">Job ID</dt>
                      <dd className="truncate font-mono text-sm font-medium">
                        {selectedJob.job_id}
                      </dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-xs text-muted-text">Dokumen</dt>
                      <dd className="truncate text-sm font-medium">{selectedJob.document_id}</dd>
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
                        {selectedJob.result?.chunk_count ?? "—"}
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
                </CardContent>
              </Card>

              {/* Status callout + action */}
              <Card>
                <CardContent className="space-y-3">
                  {selectedJob.error ? (
                    <Callout tone="warning" title="Perlu review manual">
                      {selectedJob.error}
                    </Callout>
                  ) : selectedJob.status === "completed" ? (
                    <Callout tone="success" title="Pipeline selesai">
                      Semua tahapan pemrosesan berhasil. Dokumen siap digunakan.
                    </Callout>
                  ) : (
                    <Callout tone="info" title="Menunggu pemrosesan">
                      Job ini masih dalam antrean.
                    </Callout>
                  )}

                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={() => void rerun(selectedJob.document_id)}
                  >
                    <RefreshCw className="size-4" /> Jalankan ulang
                  </Button>
                </CardContent>
              </Card>
            </>
          ) : (
            <EmptyState
              icon={FileSearch}
              title="Pilih job untuk melihat detail"
              hint="Klik salah satu job di daftar sebelah kiri."
            />
          )}
        </div>
      </div>
    </div>
  );
}
