"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  Check,
  CheckCircle2,
  FlaskConical,
  Gauge,
  Loader2,
  Play,
  RefreshCw,
  Trophy,
} from "lucide-react";
import { Toaster, toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PageHeader, StatusBadge } from "./primitives";
import { cn } from "@/lib/utils";
import {
  createEvaluationRun,
  fetchEvaluationDatasets,
  fetchEvaluationRun,
  fetchEvaluationRuns,
  seedEvaluationDataset,
} from "@/features/admin/api";
import { fallbackEvaluationDataset, fallbackEvaluationRuns } from "@/features/admin/sample-data";
import type {
  EvaluationDataset,
  EvaluationMetricSet,
  EvaluationRunDetail,
  EvaluationRunSummary,
} from "@/features/admin/types";

import {
  RunDetailDialog,
  modeLabel,
  modeOrder,
  ModeMetricsCard,
  barColor,
  formatDateTime,
  pct,
  relativeTime,
  scoreColor,
  sortModes,
} from "./evaluation-presenters";

export function AdminEvaluation() {
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([fallbackEvaluationDataset]);
  const [runs, setRuns] = useState<EvaluationRunSummary[]>(fallbackEvaluationRuns);
  const [loadStatus, setLoadStatus] = useState("Memuat data evaluasi...");
  const [seeding, setSeeding] = useState(false);

  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [runDatasetId, setRunDatasetId] = useState("evalset_golden_v1");
  const [runModes, setRunModes] = useState<string[]>(["hybrid", "rerank"]);
  const [runTopK, setRunTopK] = useState("5");
  const [running, setRunning] = useState(false);

  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<EvaluationRunDetail | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.allSettled([
      fetchEvaluationDatasets(controller.signal),
      fetchEvaluationRuns(controller.signal),
    ]).then(([datasetItems, runItems]) => {
      if (datasetItems.status === "fulfilled" && datasetItems.value.length) {
        setDatasets(datasetItems.value);
      }
      if (runItems.status === "fulfilled" && runItems.value.length) {
        setRuns(runItems.value);
      }
      setLoadStatus(
        datasetItems.status === "fulfilled" && runItems.status === "fulfilled"
          ? "Data tersinkron dengan API."
          : "Menampilkan data contoh — API belum tersedia."
      );
    });
    return () => controller.abort();
  }, []);

  const datasetName = useMemo(() => {
    const map = new Map(datasets.map((dataset) => [dataset.dataset_id, dataset.name]));
    return (datasetId: string) => map.get(datasetId) ?? datasetId;
  }, [datasets]);

  async function seed() {
    setSeeding(true);
    try {
      const dataset = await seedEvaluationDataset();
      setDatasets((current) => {
        const next = current.filter((item) => item.dataset_id !== dataset.dataset_id);
        return [dataset, ...next];
      });
      setRunDatasetId(dataset.dataset_id);
      toast.success(`Dataset "${dataset.name}" dimuat (${dataset.questions.length} pertanyaan).`);
    } catch {
      toast.info("API belum tersedia; dataset contoh tetap digunakan.");
    } finally {
      setSeeding(false);
    }
  }

  function toggleMode(mode: string) {
    setRunModes((current) =>
      current.includes(mode) ? current.filter((item) => item !== mode) : [...current, mode]
    );
  }

  async function startRun() {
    setRunning(true);
    try {
      const next = await createEvaluationRun({
        dataset_id: runDatasetId,
        experiment_modes: runModes,
        top_k: Number(runTopK),
      });
      setRuns((current) => [
        {
          run_id: next.run_id,
          dataset_id: next.dataset_id,
          created_at: next.created_at,
          metrics: next.metrics,
        },
        ...current,
      ]);
      setRunDialogOpen(false);
      setDetail(next);
      setDetailOpen(true);
      toast.success("Evaluasi selesai dijalankan.");
    } catch {
      toast.info("API belum tersedia; hasil contoh ditampilkan.");
      setRunDialogOpen(false);
    } finally {
      setRunning(false);
    }
  }

  async function openDetail(run: EvaluationRunSummary) {
    setDetailOpen(true);
    try {
      setDetail(await fetchEvaluationRun(run.run_id));
    } catch {
      setDetail({ ...run });
    }
  }

  const latestRun = runs[0];
  const latestModes = latestRun ? sortModes(latestRun.metrics) : [];

  return (
    <div className="space-y-6">
      <Toaster position="bottom-right" richColors />

      <PageHeader
        eyebrow="Benchmark kualitas"
        title="Evaluasi RAG"
        description={loadStatus}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={seeding} onClick={() => void seed()}>
              <RefreshCw className={seeding ? "animate-spin" : ""} /> Muat dataset
            </Button>
            <Button
              className="bg-javanese text-white hover:bg-forest"
              onClick={() => setRunDialogOpen(true)}
            >
              <Play /> Jalankan evaluasi
            </Button>
          </div>
        }
      />

      {/* Latest run comparison */}
      {latestRun ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-3">
              Perbandingan mode terakhir
              <StatusBadge tone="info">{formatDateTime(latestRun.created_at)}</StatusBadge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {latestModes.map((mode) => (
                <ModeMetricsCard key={mode} mode={mode} metrics={latestRun.metrics[mode]} />
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* History */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-3">
            Riwayat evaluasi
            <StatusBadge tone="neutral">{runs.length} run</StatusBadge>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {runs.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-14 text-center">
              <span className="flex size-12 items-center justify-center rounded-2xl bg-surface-soft text-muted-text">
                <Gauge className="size-6" />
              </span>
              <p className="text-sm font-semibold text-tinta">Belum ada evaluasi</p>
              <p className="max-w-xs text-sm text-muted-text">
                Jalankan evaluasi untuk melihat metrik retrieval.
              </p>
            </div>
          ) : (
            <div className="divide-y">
              {runs.map((run) => {
                const bestRecall = Math.max(
                  0,
                  ...Object.values(run.metrics).map((m) => m.recall_at_5)
                );
                const modes = sortModes(run.metrics);
                return (
                  <button
                    key={run.run_id}
                    type="button"
                    onClick={() => void openDetail(run)}
                    className="flex w-full items-center gap-4 px-4 py-3.5 text-left transition-colors hover:bg-surface-soft"
                  >
                    {/* Best score */}
                    <div className="w-16 shrink-0 text-center">
                      <p
                        className={cn(
                          "font-mono text-xl font-semibold tabular-nums",
                          scoreColor(bestRecall)
                        )}
                      >
                        {pct(bestRecall)}
                      </p>
                      <p className="text-[10px] text-muted-text">recall@5</p>
                    </div>

                    {/* Bar */}
                    <div className="hidden w-20 shrink-0 sm:block">
                      <div className="h-1.5 overflow-hidden rounded-full bg-surface-soft">
                        <div
                          className={cn("h-full rounded-full", barColor(bestRecall))}
                          style={{ width: `${Math.min(100, bestRecall * 100)}%` }}
                        />
                      </div>
                    </div>

                    {/* Info */}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-tinta">
                        {datasetName(run.dataset_id)}
                      </p>
                      <div className="flex items-center gap-2 text-xs text-muted-text">
                        <span title={formatDateTime(run.created_at)}>
                          {relativeTime(run.created_at)}
                        </span>
                        <span>·</span>
                        <span className="font-mono">{run.run_id}</span>
                      </div>
                    </div>

                    {/* Modes */}
                    <div className="hidden flex-wrap gap-1 lg:flex">
                      {modes.map((mode) => (
                        <StatusBadge key={mode} tone="neutral">
                          {modeLabel[mode] ?? mode}
                        </StatusBadge>
                      ))}
                    </div>

                    {/* Arrow */}
                    <span className="text-xs text-muted-text/50">→</span>
                  </button>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Run dialog */}
      <Dialog open={runDialogOpen} onOpenChange={setRunDialogOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Jalankan evaluasi</DialogTitle>
            <DialogDescription>
              Benchmark retrieval terhadap dataset pertanyaan terverifikasi.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Dataset</Label>
              <Select value={runDatasetId} onValueChange={setRunDatasetId}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {datasets.map((dataset) => (
                    <SelectItem key={dataset.dataset_id} value={dataset.dataset_id}>
                      {dataset.name} ({dataset.questions.length} pertanyaan)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Mode eksperimen</Label>
              <div className="grid grid-cols-2 gap-2">
                {modeOrder.map((mode) => {
                  const selected = runModes.includes(mode);
                  return (
                    <button
                      type="button"
                      key={mode}
                      onClick={() => toggleMode(mode)}
                      className={cn(
                        "flex items-center gap-2 rounded-lg border px-3 py-2.5 text-sm transition-colors",
                        selected
                          ? "border-forest bg-teal-soft text-forest"
                          : "border-line text-muted-text hover:bg-surface-soft"
                      )}
                    >
                      <span
                        className={cn(
                          "flex size-4 shrink-0 items-center justify-center rounded border transition-colors",
                          selected ? "border-forest bg-forest text-white" : "border-muted-text/30"
                        )}
                      >
                        {selected ? <Check className="size-3" /> : null}
                      </span>
                      {modeLabel[mode] ?? mode}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Top K</Label>
              <Select value={runTopK} onValueChange={setRunTopK}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="3">3</SelectItem>
                  <SelectItem value="5">5</SelectItem>
                  <SelectItem value="10">10</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {datasets.length === 0 && (
              <div className="rounded-lg border border-amber/25 bg-amber-soft px-3 py-2.5 text-sm text-amber">
                Belum ada dataset. Muat golden questions terlebih dahulu.
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRunDialogOpen(false)}>
              Batal
            </Button>
            <Button
              className="bg-javanese text-white hover:bg-forest"
              disabled={running || runModes.length === 0 || !runDatasetId}
              onClick={() => void startRun()}
            >
              {running ? <Loader2 className="animate-spin" /> : <FlaskConical />}
              {running ? "Menjalankan..." : "Jalankan evaluasi"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail dialog */}
      <RunDetailDialog
        detail={detail}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        datasetName={detail ? datasetName(detail.dataset_id) : undefined}
      />
    </div>
  );
}
