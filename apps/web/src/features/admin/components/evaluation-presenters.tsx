import { useState } from "react";
import { Button } from "@/components/ui/button";
import modalStyles from "./evaluation-detail.module.css";
import styles from "./admin-ingestion.module.css";
import { AlertTriangle, CheckCircle2, Gauge, Loader2, Trophy } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogClose,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { StatusBadge } from "./primitives";
import { Callout } from "./primitives";
import { cn } from "@/lib/utils";
import type { EvaluationMetricSet, EvaluationRunDetail } from "@/features/admin/types";
export const modeLabel: Record<string, string> = {
  baseline: "Baseline",
  dense: "Dense",
  hybrid: "Hybrid",
  rerank: "Rerank",
  upstash: "Upstash Hybrid",
};

export const modeOrder = ["baseline", "dense", "hybrid", "rerank", "upstash"];

export function sortModes(metrics: Record<string, EvaluationMetricSet>): string[] {
  return Object.keys(metrics).sort((a, b) => modeOrder.indexOf(a) - modeOrder.indexOf(b));
}

export function pct(value: number | null | undefined) {
  if (value == null) return "Belum ada data";
  return `${Math.round(value * 100)}%`;
}

function safeDate(value: string) {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDateTime(value: string) {
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

export function relativeTime(value: string) {
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
    <div className="rounded-xl border border-[#e5e5e5] bg-white p-4 shadow-[0_1px_3px_rgba(27,67,50,0.06)]">
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
  const [section, setSection] = useState("summary");
  const [modeFilter, setModeFilter] = useState("all");
  const [page, setPage] = useState(1);
  if (!detail)
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className={`admin-theme ${styles.ingestion} ${styles.detailModal}`}>
          <DialogHeader>
            <div className="flex items-center gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-teal-soft/70">
                <Gauge aria-hidden="true" className="size-5 text-forest" />
              </span>
              <div className="min-w-0">
                <DialogTitle>Detail evaluasi</DialogTitle>
                <DialogDescription>
                  {error ? "Laporan gagal dimuat." : "Memuat hasil evaluasi…"}
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>
          {loading ? (
            <p
              role="status"
              aria-label="Memuat detail evaluasi"
              className="flex items-center justify-center gap-2.5 py-10 text-center text-sm text-muted-text"
            >
              <Loader2
                aria-hidden="true"
                className="size-4 animate-spin text-forest motion-reduce:animate-none"
              />
              Memuat data…
            </p>
          ) : (
            <Callout tone="danger" title="Gagal memuat laporan">
              Tutup dialog ini lalu pilih Detail untuk mencoba lagi.
            </Callout>
          )}
        </DialogContent>
      </Dialog>
    );

  const modes = sortModes(detail.metrics);
  const isActive = detail.status === "pending" || detail.status === "running";
  const isFailed = detail.status === "failed";
  const progressPct =
    detail.progress_total > 0
      ? Math.min(100, Math.round((detail.progress_completed / detail.progress_total) * 100))
      : 0;
  const experiments = detail.report?.experiments ?? [];
  const topicSet = new Set<string>();
  for (const experiment of experiments) {
    Object.keys(experiment.per_topic).forEach((topic) => topicSet.add(topic));
  }
  const topics = [...topicSet].sort();
  const rows = experiments
    .filter((experiment) => modeFilter === "all" || modeFilter === experiment.mode)
    .flatMap((experiment) =>
      experiment.results.map((result) => ({ ...result, mode: experiment.mode }))
    );
  const pageCount = Math.max(1, Math.ceil(rows.length / 5));
  const currentPage = Math.min(page, pageCount);
  const metrics: { label: string; key: keyof EvaluationMetricSet }[] = [
    { label: "Recall@5", key: "recall_at_5" },
    { label: "MRR", key: "mean_reciprocal_rank" },
    { label: "Citation correctness", key: "citation_correctness" },
    { label: "Faithfulness", key: "faithfulness" },
    { label: "Refusal accuracy", key: "refusal_accuracy" },
    { label: "Hard-negative recall@5", key: "hard_negative_recall_at_5" },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={`admin-theme ${styles.ingestion} ${styles.detailModal} ${modalStyles.modal}`}
      >
        <DialogHeader className={modalStyles.header}>
          <div className="flex items-start gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-teal-soft/70">
              <Gauge aria-hidden="true" className="size-5 text-forest" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-widest text-muted-text">
                Laporan pengujian
              </p>
              <DialogTitle className="mt-0.5 text-xl">Detail evaluasi</DialogTitle>
              <DialogDescription className="break-words">
                {datasetName ?? detail.dataset_id}
              </DialogDescription>
            </div>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-text">
            <span>{formatDateTime(detail.created_at)}</span>
            <span>{modes.length} mode</span>
            {detail.report && (
              <>
                <span>{detail.report.question_count} pertanyaan</span>
                <span>Top K: {detail.report.top_k}</span>
              </>
            )}
          </div>
        </DialogHeader>
        {isActive ? (
          <div className="rounded-xl border border-line bg-surface-soft p-4">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold text-tinta">
                {detail.status === "pending" ? "Antre diproses" : "Evaluasi berjalan"}
              </p>
              <p className="text-xs text-muted-text tabular-nums" role="status">
                {detail.progress_completed} dari {detail.progress_total} pertanyaan
              </p>
            </div>
            <div
              role="progressbar"
              aria-label="Progres evaluasi"
              aria-valuemin={0}
              aria-valuemax={detail.progress_total}
              aria-valuenow={detail.progress_completed}
              className="mt-3 h-2 overflow-hidden rounded-full bg-teal-soft"
            >
              <div
                className="h-full rounded-full bg-forest transition-all"
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-muted-text">
              Halaman boleh ditinggal; hasil masuk otomatis.
            </p>
          </div>
        ) : isFailed ? (
          <Callout tone="danger" title="Evaluasi gagal">
            {detail.error ?? "Run berhenti karena kesalahan internal."} Tutup dialog ini lalu
            jalankan ulang dari halaman evaluasi.
          </Callout>
        ) : (
          <>
            <nav aria-label="Bagian laporan evaluasi" className={modalStyles.tabs}>
              {[
                { id: "summary", label: "Ringkasan" },
                { id: "topics", label: "Per topik" },
                { id: "questions", label: "Per pertanyaan" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  aria-pressed={section === tab.id}
                  aria-controls="evaluation-report-section"
                  onClick={() => setSection(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </nav>
            <div id="evaluation-report-section" className={modalStyles.body}>
              {section === "summary" && (
                <section className="space-y-4">
                  <div>
                    <h3 className="font-semibold text-tinta">Perbandingan metrik</h3>
                    <p className="mt-1 text-sm text-muted-text">
                      Bandingkan setiap mode pada dataset dan pengujian yang sama.
                    </p>
                  </div>
                  {modes.length ? (
                    <div className={modalStyles.tableWrap}>
                      <table
                        className={modalStyles.table}
                        aria-label="Perbandingan metrik evaluasi"
                      >
                        <thead>
                          <tr>
                            <th scope="col">Metrik</th>
                            {modes.map((mode) => (
                              <th scope="col" key={mode}>
                                {modeLabel[mode] ?? mode}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {metrics.map((metric) => (
                            <tr key={metric.key}>
                              <th scope="row">{metric.label}</th>
                              {modes.map((mode) => (
                                <td key={mode} className="font-mono tabular-nums">
                                  {pct(detail.metrics[mode][metric.key])}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-text">
                      Metrik belum tersedia untuk evaluasi ini.
                    </p>
                  )}
                  <div className="rounded-lg bg-surface-soft p-4 text-xs leading-relaxed text-muted-text">
                    <p>
                      <strong>Recall@5</strong> menunjukkan cakupan sumber relevan pada lima hasil
                      teratas. <strong>MRR</strong> mengukur posisi hasil relevan pertama.
                    </p>
                    <p className="mt-2">
                      Nilai &quot;Belum ada data&quot; berarti metrik belum tersedia.
                    </p>
                  </div>
                </section>
              )}
              {/* Per-topic table */}
              {section === "topics" &&
                (topics.length > 0 ? (
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
                              Pertanyaan
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {topics.map((topic) => (
                            <tr key={topic} className="border-b last:border-0">
                              <td className="px-3 py-2 font-medium">
                                {topic.replaceAll("_", " ")}
                              </td>
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
                ) : (
                  <p className="py-10 text-center text-sm text-muted-text">
                    Laporan per topik belum tersedia.
                  </p>
                ))}

              {section === "questions" && (
                <section className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h3 className="font-semibold text-tinta">Hasil per pertanyaan</h3>
                    <label className="flex items-center gap-2 text-sm text-muted-text">
                      Mode
                      <select
                        className="min-h-11 rounded-lg border border-line bg-white px-3 text-tinta"
                        value={modeFilter}
                        onChange={(event) => {
                          setModeFilter(event.target.value);
                          setPage(1);
                        }}
                      >
                        <option value="all">Semua mode</option>
                        {experiments.map((experiment) => (
                          <option key={experiment.mode} value={experiment.mode}>
                            {modeLabel[experiment.mode] ?? experiment.mode}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  {rows.length ? (
                    <>
                      <div className={modalStyles.tableWrap}>
                        <table
                          className={modalStyles.table}
                          aria-label="Hasil evaluasi per pertanyaan"
                        >
                          <thead>
                            <tr>
                              {[
                                "Pertanyaan",
                                "Mode",
                                "Respons",
                                "Recall@5",
                                "Keputusan penolakan",
                              ].map((label) => (
                                <th key={label} scope="col">
                                  {label}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {rows.slice((currentPage - 1) * 5, currentPage * 5).map((result) => (
                              <tr key={`${result.mode}-${result.question_id}`}>
                                <th scope="row">
                                  <p className="font-mono text-xs">{result.question_id}</p>
                                  <p className="mt-1 text-xs font-normal text-muted-text">
                                    {result.category.replaceAll("_", " ")}
                                  </p>
                                </th>
                                <td>{modeLabel[result.mode] ?? result.mode}</td>
                                <td>{result.actual_refuse ? "Menolak" : "Menjawab"}</td>
                                <td className="font-mono">{pct(result.recall_at_5)}</td>
                                <td>
                                  <span className="inline-flex items-center gap-2">
                                    {result.refusal_correct ? (
                                      <CheckCircle2 className="size-4 text-forest" />
                                    ) : (
                                      <AlertTriangle className="size-4 text-amber" />
                                    )}
                                    {result.refusal_correct ? "Sesuai" : "Perlu ditinjau"}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-text">
                        <span role="status">
                          {(currentPage - 1) * 5 + 1} sampai{" "}
                          {Math.min(currentPage * 5, rows.length)} dari {rows.length} hasil
                        </span>
                        <nav
                          aria-label="Pagination hasil pertanyaan"
                          className="flex items-center gap-2"
                        >
                          <Button
                            size="sm"
                            variant="outline"
                            className="min-h-11"
                            disabled={currentPage === 1}
                            onClick={() => setPage(currentPage - 1)}
                          >
                            Sebelumnya
                          </Button>
                          <span>
                            {currentPage} / {pageCount}
                          </span>
                          <Button
                            size="sm"
                            variant="outline"
                            className="min-h-11"
                            disabled={currentPage === pageCount}
                            onClick={() => setPage(currentPage + 1)}
                          >
                            Berikutnya
                          </Button>
                        </nav>
                      </div>
                    </>
                  ) : (
                    <p className="py-10 text-center text-sm text-muted-text">
                      Hasil per pertanyaan belum tersedia.
                    </p>
                  )}
                </section>
              )}
            </div>
          </>
        )}
        <footer className={modalStyles.footer}>
          <span
            title={detail.run_id}
            className="min-w-0 truncate font-mono text-xs text-muted-text"
          >
            ID: {detail.run_id}
          </span>
          <DialogClose asChild>
            <Button variant="outline" className="min-h-11">
              Tutup
            </Button>
          </DialogClose>
        </footer>
      </DialogContent>
    </Dialog>
  );
}
