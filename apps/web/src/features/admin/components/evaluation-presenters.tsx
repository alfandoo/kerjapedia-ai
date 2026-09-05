import styles from "./admin-ingestion.module.css";
import { AlertTriangle, CheckCircle2, Trophy } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { StatusBadge } from "./primitives";
import { cn } from "@/lib/utils";
import type { EvaluationMetricSet, EvaluationRunDetail } from "@/features/admin/types";
export const modeLabel: Record<string, string> = {
  baseline: "Baseline",
  dense: "Dense",
  hybrid: "Hybrid",
  rerank: "Rerank",
};

export const modeOrder = ["baseline", "dense", "hybrid", "rerank"];

export function sortModes(metrics: Record<string, EvaluationMetricSet>): string[] {
  return Object.keys(metrics).sort((a, b) => modeOrder.indexOf(a) - modeOrder.indexOf(b));
}

export function pct(value: number | null | undefined) {
  if (value == null) return "—";
  return `${Math.round(value * 100)}%`;
}

function safeDate(value: string) {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDateTime(value: string) {
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

export function relativeTime(value: string) {
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

export function scoreColor(value: number) {
  if (value >= 0.8) return "text-forest";
  if (value >= 0.5) return "text-amber";
  return "text-red";
}

export function barColor(value: number) {
  if (value >= 0.8) return "bg-forest";
  if (value >= 0.5) return "bg-amber";
  return "bg-red";
}

function MetricBar({ label, value }: { label: string; value: number }) {
  const width = Math.min(100, Math.round((value ?? 0) * 100));
  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-text">{label}</span>
        <span className={cn("font-mono font-medium tabular-nums", scoreColor(value))}>
          {pct(value)}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-soft">
        <div
          className={cn("h-full rounded-full transition-all", barColor(value))}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

export function ModeMetricsCard({ mode, metrics }: { mode: string; metrics: EvaluationMetricSet }) {
  return (
    <div className="rounded-xl border border-line bg-white p-4">
      <div className="flex items-center justify-between">
        <StatusBadge tone="neutral">{modeLabel[mode] ?? mode}</StatusBadge>
        {metrics.recall_at_5 >= 0.8 && <Trophy className="size-4 text-emas" />}
      </div>
      <div className="mt-3">
        <p
          className={cn(
            "font-mono text-3xl font-semibold tracking-tight tabular-nums",
            scoreColor(metrics.recall_at_5)
          )}
        >
          {pct(metrics.recall_at_5)}
        </p>
        <p className="text-xs text-muted-text">recall@5</p>
      </div>
      <div className="mt-3 space-y-2">
        <MetricBar label="MRR" value={metrics.mean_reciprocal_rank} />
        <MetricBar label="Citation" value={metrics.citation_correctness} />
        <MetricBar label="Faithfulness" value={metrics.faithfulness} />
        <MetricBar label="Refusal acc." value={metrics.refusal_accuracy} />
        <MetricBar label="Hard-neg" value={metrics.hard_negative_recall_at_5} />
      </div>
    </div>
  );
}

export function RunDetailDialog({
  detail,
  open,
  onOpenChange,
  datasetName,
  loading = false,
  error = false,
}: {
  detail: EvaluationRunDetail | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  datasetName?: string;
  loading?: boolean;
  error?: boolean;
}) {
  if (!detail)
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className={`admin-theme ${styles.ingestion} ${styles.detailModal}`}>
          <DialogHeader>
            <DialogTitle>Detail evaluasi</DialogTitle>
            <DialogDescription>
              {error
                ? "Detail belum dapat dimuat. Tutup modal dan pilih Detail untuk mencoba lagi."
                : "Memuat hasil evaluasi…"}
            </DialogDescription>
          </DialogHeader>
          <p role={error ? "alert" : "status"} className="text-sm text-muted-text">
            {loading
              ? "Mengambil laporan dari API…"
              : error
                ? "Gagal memuat laporan."
                : "Laporan tidak tersedia."}
          </p>
        </DialogContent>
      </Dialog>
    );

  const modes = sortModes(detail.metrics);
  const experiments = detail.report?.experiments ?? [];
  const topicSet = new Set<string>();
  for (const experiment of experiments) {
    Object.keys(experiment.per_topic).forEach((topic) => topicSet.add(topic));
  }
  const topics = [...topicSet].sort();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={`admin-theme ${styles.ingestion} ${styles.detailModal} max-h-[85dvh] overflow-y-auto p-6 sm:max-w-4xl`}
      >
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

        {/* Mode cards */}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {modes.map((mode) => (
            <ModeMetricsCard key={mode} mode={mode} metrics={detail.metrics[mode]} />
          ))}
        </div>

        {/* Per-topic table */}
        {experiments.length > 0 && topics.length > 0 ? (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-tinta">Recall per topik</h3>
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-surface-soft">
                    <th className="px-3 py-2.5 text-left text-xs font-semibold text-muted-text">
                      Topik
                    </th>
                    {experiments.map((experiment) => (
                      <th
                        key={experiment.mode}
                        className="px-3 py-2.5 text-right text-xs font-semibold text-muted-text"
                      >
                        {modeLabel[experiment.mode] ?? experiment.mode}
                      </th>
                    ))}
                    <th className="px-3 py-2.5 text-right text-xs font-semibold text-muted-text">
                      n
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {topics.map((topic) => (
                    <tr key={topic} className="border-b last:border-0">
                      <td className="px-3 py-2 font-medium">{topic.replaceAll("_", " ")}</td>
                      {experiments.map((experiment) => {
                        const val = experiment.per_topic[topic]?.recall_at_5;
                        return (
                          <td
                            key={experiment.mode}
                            className={cn(
                              "px-3 py-2 text-right font-mono text-sm tabular-nums",
                              val != null ? scoreColor(val) : "text-muted-text"
                            )}
                          >
                            {pct(val)}
                          </td>
                        );
                      })}
                      <td className="px-3 py-2 text-right text-muted-text tabular-nums">
                        {experiments[0]?.per_topic[topic]?.question_count ?? 0}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {/* Per-question results */}
        {experiments.length > 0 ? (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-tinta">Hasil per pertanyaan</h3>
            <div className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
              {experiments.flatMap((experiment) =>
                experiment.results.map((result) => (
                  <div
                    key={`${experiment.mode}-${result.question_id}`}
                    className="flex items-center gap-3 rounded-lg border border-line px-3 py-2"
                  >
                    <StatusBadge tone="neutral">{modeLabel[experiment.mode]}</StatusBadge>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{result.question_id}</p>
                      <p className="text-xs text-muted-text">
                        {result.category.replaceAll("_", " ")} ·{" "}
                        {result.actual_refuse ? "refuse" : "answer"}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "font-mono text-sm tabular-nums",
                        result.recall_at_5 != null
                          ? scoreColor(result.recall_at_5)
                          : "text-muted-text"
                      )}
                    >
                      {pct(result.recall_at_5)}
                    </span>
                    {result.refusal_correct ? (
                      <CheckCircle2 className="size-4 shrink-0 text-forest" />
                    ) : (
                      <AlertTriangle className="size-4 shrink-0 text-amber" />
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
