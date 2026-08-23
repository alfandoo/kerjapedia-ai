"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  FlaskConical,
  Gauge,
  Loader2,
  Play,
  RefreshCw,
} from "lucide-react";
import { Toaster, toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PageHeader } from "@/components/admin/primitives";
import { cn } from "@/lib/utils";
import {
  createEvaluationRun,
  fetchEvaluationDatasets,
  fetchEvaluationRun,
  fetchEvaluationRuns,
  seedEvaluationDataset,
} from "@/lib/api";
import { fallbackEvaluationDataset, fallbackEvaluationRuns } from "@/lib/sample-data";
import type {
  EvaluationDataset,
  EvaluationMetricSet,
  EvaluationRunDetail,
  EvaluationRunSummary,
} from "@/lib/types";

const modeLabel: Record<string, string> = {
  baseline: "Baseline",
  dense: "Dense",
  hybrid: "Hybrid",
  rerank: "Rerank",
};

const modeOrder = ["baseline", "dense", "hybrid", "rerank"];

function sortModes(metrics: Record<string, EvaluationMetricSet>): string[] {
  return Object.keys(metrics).sort((a, b) => modeOrder.indexOf(a) - modeOrder.indexOf(b));
}

function pct(value: number | null | undefined) {
  if (value == null) return "-";
  return `${Math.round(value * 100)}%`;
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function MetricBar({ label, value }: { label: string; value: number }) {
  const width = Math.min(100, Math.round((value ?? 0) * 100));
  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono font-medium tabular-nums">{pct(value)}</span>
      </div>
      <div className="mt-1 h-1 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-teal" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function ModeMetricsCard({ mode, metrics }: { mode: string; metrics: EvaluationMetricSet }) {
  return (
    <div className="rounded-lg border p-4">
      <Badge variant="secondary">{modeLabel[mode] ?? mode}</Badge>
      <p className="mt-3 font-mono text-3xl font-semibold tracking-tight tabular-nums">
        {pct(metrics.recall_at_5)}
      </p>
      <p className="text-xs text-muted-foreground">recall@5</p>
      <div className="mt-3 space-y-2">
        <MetricBar label="MRR" value={metrics.mean_reciprocal_rank} />
        <MetricBar label="Citation" value={metrics.citation_correctness} />
        <MetricBar label="Faithfulness" value={metrics.faithfulness} />
        <MetricBar label="Refusal acc." value={metrics.refusal_accuracy} />
        <MetricBar label="Hard-neg recall" value={metrics.hard_negative_recall_at_5} />
      </div>
    </div>
  );
}

function RunDetailDialog({
  detail,
  open,
  onOpenChange,
  datasetName,
}: {
  detail: EvaluationRunDetail | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  datasetName?: string;
}) {
  if (!detail) return null;

  const modes = sortModes(detail.metrics);
  const experiments = detail.report?.experiments ?? [];
  const topicSet = new Set<string>();
  for (const experiment of experiments) {
    Object.keys(experiment.per_topic).forEach((topic) => topicSet.add(topic));
  }
  const topics = [...topicSet].sort();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Detail evaluasi</DialogTitle>
          <DialogDescription>
            <span className="font-mono">{detail.run_id}</span> · {datasetName ?? detail.dataset_id}{" "}
            · {formatDateTime(detail.created_at)}
            {detail.report
              ? ` · ${detail.report.question_count} pertanyaan, top_k=${detail.report.top_k}`
              : ""}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {modes.map((mode) => (
            <ModeMetricsCard key={mode} mode={mode} metrics={detail.metrics[mode]} />
          ))}
        </div>

        {experiments.length > 0 && topics.length > 0 ? (
          <div className="space-y-3">
            <h3 className="text-sm font-medium">Recall@5 per topik</h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Topik</TableHead>
                  {experiments.map((experiment) => (
                    <TableHead key={experiment.mode} className="text-right">
                      {modeLabel[experiment.mode] ?? experiment.mode}
                    </TableHead>
                  ))}
                  <TableHead className="text-right">n</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {topics.map((topic) => (
                  <TableRow key={topic}>
                    <TableCell className="font-medium">{topic.replaceAll("_", " ")}</TableCell>
                    {experiments.map((experiment) => (
                      <TableCell
                        key={experiment.mode}
                        className="text-right font-mono tabular-nums"
                      >
                        {pct(experiment.per_topic[topic]?.recall_at_5)}
                      </TableCell>
                    ))}
                    <TableCell className="text-right text-muted-foreground tabular-nums">
                      {experiments[0]?.per_topic[topic]?.question_count ?? 0}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : null}

        {experiments.length > 0 ? (
          <div className="space-y-3">
            <h3 className="text-sm font-medium">Hasil per pertanyaan</h3>
            <ul className="max-h-64 space-y-2 overflow-y-auto pr-1">
              {experiments.flatMap((experiment) =>
                experiment.results.map((result) => (
                  <li
                    key={`${experiment.mode}-${result.question_id}`}
                    className="flex items-center gap-3 rounded-lg border px-3 py-2"
                  >
                    <Badge variant="secondary">{modeLabel[experiment.mode]}</Badge>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{result.question_id}</p>
                      <p className="text-xs text-muted-foreground">
                        {result.category.replaceAll("_", " ")} ·{" "}
                        {result.actual_refuse ? "refuse" : "answer"}
                      </p>
                    </div>
                    <span className="font-mono text-sm tabular-nums">
                      {pct(result.recall_at_5)}
                    </span>
                    {result.refusal_correct ? (
                      <CheckCircle2 className="size-4 shrink-0 text-teal" />
                    ) : (
                      <AlertTriangle className="size-4 shrink-0 text-amber" />
                    )}
                  </li>
                ))
              )}
            </ul>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

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
          : "Menampilkan data contoh karena API belum tersedia."
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
              <RefreshCw className={seeding ? "animate-spin" : ""} /> Golden questions
            </Button>
            <Button
              className="bg-teal text-white hover:bg-teal-strong"
              onClick={() => setRunDialogOpen(true)}
            >
              <Play /> Jalankan evaluasi
            </Button>
          </div>
        }
      />

      {latestRun ? (
        <Card>
          <CardHeader>
            <CardTitle>Perbandingan mode terakhir</CardTitle>
            <CardDescription>
              {formatDateTime(latestRun.created_at)} · {datasetName(latestRun.dataset_id)} ·{" "}
              {latestRun.run_id}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {latestModes.map((mode) => (
                <ModeMetricsCard key={mode} mode={mode} metrics={latestRun.metrics[mode]} />
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Riwayat evaluasi</CardTitle>
          <CardDescription>{runs.length} run benchmark tercatat</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Waktu</TableHead>
                <TableHead>Dataset</TableHead>
                <TableHead>Mode</TableHead>
                <TableHead className="text-right">Recall@5 terbaik</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((run) => {
                const bestRecall = Math.max(
                  0,
                  ...Object.values(run.metrics).map((metrics) => metrics.recall_at_5)
                );
                return (
                  <TableRow
                    key={run.run_id}
                    className="cursor-pointer"
                    onClick={() => void openDetail(run)}
                  >
                    <TableCell className="text-xs text-muted-foreground tabular-nums">
                      {formatDateTime(run.created_at)}
                    </TableCell>
                    <TableCell className="max-w-56">
                      <span className="block truncate text-sm font-medium">
                        {datasetName(run.dataset_id)}
                      </span>
                      <span className="block font-mono text-xs text-muted-foreground">
                        {run.run_id}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {sortModes(run.metrics).map((mode) => (
                          <Badge key={mode} variant="secondary">
                            {modeLabel[mode] ?? mode}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <span className="font-mono text-sm font-semibold tabular-nums">
                          {pct(bestRecall)}
                        </span>
                        <div className="h-1 w-16 overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full bg-teal"
                            style={{ width: `${Math.min(100, bestRecall * 100)}%` }}
                          />
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={(event) => {
                          event.stopPropagation();
                          void openDetail(run);
                        }}
                      >
                        Detail
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
              {runs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5}>
                    <div className="flex flex-col items-center gap-2 py-10 text-center">
                      <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                        <Gauge className="size-5" />
                      </span>
                      <p className="text-sm font-medium">Belum ada run evaluasi</p>
                      <p className="text-sm text-muted-foreground">
                        Jalankan evaluasi untuk melihat metrik retrieval.
                      </p>
                    </div>
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

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
                        "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors",
                        selected
                          ? "border-teal bg-teal-soft text-teal"
                          : "border-border hover:bg-muted"
                      )}
                    >
                      <span
                        className={cn(
                          "flex size-4 shrink-0 items-center justify-center rounded border",
                          selected ? "border-teal bg-teal text-white" : "border-muted-foreground/40"
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

            {datasets.length === 0 ? (
              <p className="rounded-lg bg-amber-soft px-3 py-2.5 text-sm text-amber">
                Belum ada dataset. Muat golden questions terlebih dahulu.
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRunDialogOpen(false)}>
              Batal
            </Button>
            <Button
              className="bg-teal text-white hover:bg-teal-strong"
              disabled={running || runModes.length === 0 || !runDatasetId}
              onClick={() => void startRun()}
            >
              {running ? <Loader2 className="animate-spin" /> : <FlaskConical />}
              {running ? "Menjalankan..." : "Jalankan evaluasi"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <RunDetailDialog
        detail={detail}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        datasetName={detail ? datasetName(detail.dataset_id) : undefined}
      />
    </div>
  );
}
