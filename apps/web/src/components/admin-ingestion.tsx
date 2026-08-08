"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw, Timer } from "lucide-react";
import { Toaster, toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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

const jobBadgeClasses: Record<IngestionJob["status"], string> = {
  completed: "bg-teal-soft text-teal",
  needs_review: "bg-amber-soft text-amber",
  failed: "bg-red-soft text-red",
  running: "bg-muted text-muted-foreground",
  queued: "bg-muted text-muted-foreground",
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

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <p className="text-xs font-medium tracking-[0.18em] text-teal uppercase">
            Pipeline pemrosesan
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">Ingestion</h1>
          <p className="text-sm text-muted-foreground">{loadStatus}</p>
        </div>
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger aria-label="Filter job ingestion">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua status</SelectItem>
            <SelectItem value="completed">Selesai</SelectItem>
            <SelectItem value="needs_review">Perlu review</SelectItem>
            <SelectItem value="failed">Gagal</SelectItem>
          </SelectContent>
        </Select>
      </div>

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
                      selected ? "bg-teal-soft/40" : "hover:bg-muted/50"
                    )}
                    onClick={() => setSelectedJobId(job.job_id)}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{job.document_id}</p>
                      <p className="truncate font-mono text-xs text-muted-foreground">
                        {job.job_id}
                      </p>
                    </div>
                    <Badge className={jobBadgeClasses[job.status]}>
                      {jobLabels[job.status]}
                    </Badge>
                    <span className="text-xs text-muted-foreground tabular-nums">
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
                <li className="flex flex-col items-center gap-2 px-4 py-10 text-center">
                  <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                    <Timer className="size-5" />
                  </span>
                  <p className="text-sm font-medium">Tidak ada job dengan filter ini</p>
                  <p className="text-sm text-muted-foreground">Ubah filter untuk melihat hasil.</p>
                </li>
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
                      <dt className="text-xs text-muted-foreground">{row.dt}</dt>
                      <dd className="truncate font-mono text-sm font-medium tabular-nums">
                        {row.dd}
                      </dd>
                    </div>
                  ))}
                </dl>

                <div
                  className={cn(
                    "flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-sm",
                    selectedJob.error
                      ? "border-amber/30 bg-amber-soft/60"
                      : "border-teal/30 bg-teal-soft/60"
                  )}
                >
                  {selectedJob.error ? (
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber" />
                  ) : (
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-teal" />
                  )}
                  <span>
                    <strong className="block">
                      {selectedJob.error ? "Perlu review manual" : "Tidak ada error parsing"}
                    </strong>
                    <small className="text-xs text-muted-foreground">
                      {selectedJob.error ?? "Semua tahapan pipeline selesai."}
                    </small>
                  </span>
                </div>

                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => void rerun(selectedJob.document_id)}
                >
                  <RefreshCw /> Jalankan ulang
                </Button>
              </>
            ) : (
              <div className="flex flex-col items-center gap-2 py-10 text-center">
                <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <Timer className="size-5" />
                </span>
                <p className="text-sm text-muted-foreground">Pilih job untuk melihat log.</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
