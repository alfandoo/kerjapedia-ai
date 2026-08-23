"use client";

import { useEffect, useMemo, useState } from "react";
import { RefreshCw, Timer } from "lucide-react";
import { Toaster, toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Callout, EmptyState, PageHeader, StatusBadge } from "@/components/admin/primitives";
import { cn } from "@/lib/utils";
import { createIngestionJob, fetchIngestionJobs } from "@/lib/api";
import { fallbackIngestionJobs } from "@/lib/sample-data";
import type { IngestionJob } from "@/lib/types";

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

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function AdminIngestion() {
  const [jobs, setJobs] = useState(fallbackIngestionJobs);
  const [filter, setFilter] = useState("all");
  const [selectedJobId, setSelectedJobId] = useState(fallbackIngestionJobs[1].job_id);
  const [loadStatus, setLoadStatus] = useState("Memuat job ingestion...");

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
      .catch(() => setLoadStatus("Menampilkan log contoh karena API belum tersedia."));
    return () => controller.abort();
  }, []);

  const filtered = useMemo(
    () => jobs.filter((job) => filter === "all" || job.status === filter),
    [filter, jobs]
  );
  const selectedJob = jobs.find((job) => job.job_id === selectedJobId) ?? null;

  async function rerun(documentId: string) {
    try {
      const next = await createIngestionJob(documentId);
      setJobs((current) => [next, ...current]);
      setSelectedJobId(next.job_id);
      toast.success(`Ingestion selesai dengan status ${jobLabels[next.status]}.`);
    } catch {
      toast.info("API belum tersedia; re-ingest belum dapat dijalankan.");
    }
  }

  const detailRows = selectedJob
    ? [
        { dt: "Job ID", dd: selectedJob.job_id },
        { dt: "Dokumen", dd: selectedJob.document_id },
        { dt: "Status", dd: jobLabels[selectedJob.status] },
        { dt: "Chunk", dd: String(selectedJob.result?.chunk_count ?? "-") },
      ]
    : [];

  return (
    <div className="space-y-6">
      <Toaster position="bottom-right" richColors />

      <PageHeader
        eyebrow="Pipeline pemrosesan"
        title="Ingestion"
        description={loadStatus}
        actions={
          <Select value={filter} onValueChange={setFilter}>
            <SelectTrigger aria-label="Filter job ingestion" className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua status</SelectItem>
              <SelectItem value="completed">Selesai</SelectItem>
              <SelectItem value="needs_review">Perlu review</SelectItem>
              <SelectItem value="failed">Gagal</SelectItem>
            </SelectContent>
          </Select>
        }
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Job terakhir</CardTitle>
            <CardDescription>
              {filtered.length} job ditampilkan dari total {jobs.length}
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <ul className="divide-y">
              {filtered.map((job) => {
                const selected = job.job_id === selectedJobId;
                return (
                  <li
                    key={job.job_id}
                    className={cn(
                      "flex cursor-pointer flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 transition-colors",
                      selected
                        ? "bg-teal-soft/40 shadow-[inset_3px_0_0_var(--teal)]"
                        : "hover:bg-surface-soft"
                    )}
                    onClick={() => setSelectedJobId(job.job_id)}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{job.document_id}</p>
                      <p className="truncate font-mono text-xs text-muted-text">{job.job_id}</p>
                    </div>
                    <StatusBadge tone={jobTones[job.status]} pulse={job.status === "running"}>
                      {jobLabels[job.status]}
                    </StatusBadge>
                    <span className="text-xs text-muted-text tabular-nums">
                      {formatDateTime(job.updated_at)}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Jalankan ulang ${job.document_id}`}
                      onClick={(event) => {
                        event.stopPropagation();
                        void rerun(job.document_id);
                      }}
                    >
                      <RefreshCw /> Re-ingest
                    </Button>
                  </li>
                );
              })}
              {filtered.length === 0 ? (
                <EmptyState
                  icon={Timer}
                  title="Tidak ada job dengan filter ini"
                  hint="Ubah filter untuk melihat hasil lain."
                />
              ) : null}
            </ul>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Log parsing</CardTitle>
            <CardDescription>Detail job yang dipilih</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {selectedJob ? (
              <>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
                  {detailRows.map((row) => (
                    <div key={row.dt} className="min-w-0">
                      <dt className="text-xs text-muted-text">{row.dt}</dt>
                      <dd className="truncate font-mono text-sm font-medium tabular-nums">
                        {row.dd}
                      </dd>
                    </div>
                  ))}
                </dl>

                <div className="space-y-3">
                  {selectedJob.error ? (
                    <Callout tone="warning" title="Perlu review manual">
                      {selectedJob.error}
                    </Callout>
                  ) : (
                    <Callout tone="success" title="Tidak ada error parsing">
                      Semua tahapan pipeline selesai.
                    </Callout>
                  )}

                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={() => void rerun(selectedJob.document_id)}
                  >
                    <RefreshCw /> Jalankan ulang
                  </Button>
                </div>
              </>
            ) : (
              <EmptyState
                icon={Timer}
                title="Belum ada job dipilih"
                hint="Pilih job di daftar kiri untuk melihat log parsing."
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
