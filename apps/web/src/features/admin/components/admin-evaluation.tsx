"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, FlaskConical, Gauge, Play, RefreshCw } from "lucide-react";
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
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import styles from "./admin-ingestion.module.css";
import type {
  EvaluationDataset,
  EvaluationRunDetail,
  EvaluationRunSummary,
} from "@/features/admin/types";

import {
  RunDetailDialog,
  modeLabel,
  modeOrder,
  ModeMetricsCard,
  formatDateTime,
  pct,
  scoreColor,
  sortModes,
} from "./evaluation-presenters";

export function AdminEvaluation() {
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([]);
  const [runs, setRuns] = useState<EvaluationRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(false);
  const detailRequest = useRef(0);
  const runBusy = useRef(false);
  const seedBusy = useRef(false);
  const [seeding, setSeeding] = useState(false);

  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [runDatasetId, setRunDatasetId] = useState("");
  const [runModes, setRunModes] = useState<string[]>(["hybrid", "rerank"]);
  const [runTopK, setRunTopK] = useState("5");
  const [submitting, setSubmitting] = useState(false);
  const [runError, setRunError] = useState("");

  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<EvaluationRunDetail | null>(null);
  const detailRef = useRef<EvaluationRunDetail | null>(null);
  useEffect(() => {
    detailRef.current = detail;
  });
  const pollBusy = useRef(false);
  const lastStatuses = useRef<Record<string, string>>({});

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetchEvaluationDatasets(controller.signal),
      fetchEvaluationRuns(controller.signal),
    ])
      .then(([datasetItems, runItems]) => {
        if (controller.signal.aborted) return;
        setDatasets(datasetItems);
        setRuns(runItems);
        for (const item of runItems) lastStatuses.current[item.run_id] = item.status;
        setRunDatasetId((current) =>
          datasetItems.some((item) => item.dataset_id === current)
            ? current
            : (datasetItems[0]?.dataset_id ?? "")
        );
        setLoadError(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadError(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [reloadKey]);

  const datasetName = useMemo(() => {
    const map = new Map(datasets.map((dataset) => [dataset.dataset_id, dataset.name]));
    return (datasetId: string) => map.get(datasetId) ?? datasetId;
  }, [datasets]);

  async function seed() {
    if (seedBusy.current) return;
    seedBusy.current = true;
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
      toast.error("Dataset gagal dimuat. Silakan coba lagi.");
    } finally {
      seedBusy.current = false;
      setSeeding(false);
    }
  }

  function toggleMode(mode: string) {
    setRunModes((current) =>
      current.includes(mode) ? current.filter((item) => item !== mode) : [...current, mode]
    );
  }

  async function startRun() {
    if (
      runBusy.current ||
      submitting ||
      !runModes.length ||
      !datasets.some((item) => item.dataset_id === runDatasetId)
    )
      return;
    runBusy.current = true;
    setRunError("");
    setSubmitting(true);
    try {
      const next = await createEvaluationRun({
        dataset_id: runDatasetId,
        experiment_modes: runModes,
        top_k: Number(runTopK),
      });
      lastStatuses.current[next.run_id] = next.status;
      setRuns((current) => [
        {
          run_id: next.run_id,
          dataset_id: next.dataset_id,
          release_id: next.release_id,
          status: next.status,
          progress_completed: next.progress_completed,
          progress_total: next.progress_total,
          error: next.error,
          created_at: next.created_at,
          metrics: next.metrics,
        },
        ...current,
      ]);
      setRunDialogOpen(false);
      setPage(1);
      setDetailError(false);
      setDetailLoading(false);
      setDetail(next);
      setDetailOpen(true);
    } catch {
      setRunError(
        "Evaluasi belum dapat dimulai. Periksa koneksi lalu coba lagi."
      );
    } finally {
      runBusy.current = false;
      setSubmitting(false);
    }
  }

  async function openDetail(run: EvaluationRunSummary) {
    const request = ++detailRequest.current;
    setDetail(null);
    setDetailError(false);
    setDetailLoading(true);
    setDetailOpen(true);
    try {
      const next = await fetchEvaluationRun(run.run_id);
      if (request === detailRequest.current) setDetail(next);
    } catch {
      if (request === detailRequest.current) setDetailError(true);
    } finally {
      if (request === detailRequest.current) setDetailLoading(false);
    }
  }

  function isActiveRun(status: string | undefined) {
    return status === "pending" || status === "running";
  }

  const refreshActive = useCallback(async () => {
    if (pollBusy.current || document.hidden) return;
    pollBusy.current = true;
    try {
      const liveDetail = detailRef.current;
      const [summaries, freshDetail] = await Promise.all([
        fetchEvaluationRuns(),
        liveDetail && isActiveRun(liveDetail.status)
          ? fetchEvaluationRun(liveDetail.run_id).catch(() => null)
          : Promise.resolve(null),
      ]);
      for (const summary of summaries) {
        const previous = lastStatuses.current[summary.run_id];
        if (previous === "pending" || previous === "running") {
          if (summary.status === "completed") toast.success("Evaluasi selesai dijalankan.");
          else if (summary.status === "failed")
            toast.error("Evaluasi gagal. Buka detail untuk informasinya.");
        }
        lastStatuses.current[summary.run_id] = summary.status;
      }
      setRuns(summaries);
      if (freshDetail) setDetail(freshDetail);
    } catch {
      // keep stale data; next tick retries
    } finally {
      pollBusy.current = false;
    }
  }, []);

  const needsPoll =
    !loading &&
    !loadError &&
    (runs.some((run) => isActiveRun(run.status)) ||
      (detail !== null && isActiveRun(detail.status)));

  useEffect(() => {
    if (!needsPoll) return;
    const id = window.setInterval(() => void refreshActive(), 5000);
    return () => window.clearInterval(id);
  }, [needsPoll, refreshActive]);

  const pageCount = Math.max(1, Math.ceil(runs.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const start = (currentPage - 1) * pageSize;

  const latestRun = runs[0];
  const latestModes = latestRun ? sortModes(latestRun.metrics) : [];

  return (
    <div className={`${styles.ingestion} space-y-6`}>
      <Toaster position="bottom-right" richColors />

      <PageHeader
        eyebrow="Benchmark kualitas"
        title="Evaluasi RAG"
        description="Bandingkan kualitas pencarian, ketepatan kutipan, dan jawaban pada dataset evaluasi."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              className="min-h-11"
              disabled={loading || loadError || seeding || submitting}
              onClick={() => void seed()}
            >
              <RefreshCw className={seeding ? "animate-spin motion-reduce:animate-none" : ""} />{" "}
              Muat dataset
            </Button>
            <Button
              className="min-h-11 bg-javanese text-white hover:bg-forest"
              disabled={loading || loadError || submitting || seeding || !datasets.length}
              onClick={() => setRunDialogOpen(true)}
            >
              <Play /> Jalankan evaluasi
            </Button>
          </div>
        }
      />

      {loading ? (
        <div role="status" aria-label="Memuat evaluasi" aria-busy="true" className="space-y-4">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : loadError ? (
        <div role="alert" className="rounded-xl border border-line bg-white p-6">
          <p className="text-sm text-red">Data evaluasi belum dapat dimuat.</p>
          <Button
            variant="outline"
            className="mt-4 min-h-11"
            onClick={() => {
              setLoading(true);
              setLoadError(false);
              setReloadKey((key) => key + 1);
            }}
          >
            Coba lagi
          </Button>
        </div>
      ) : (
        <>
          {!datasets.length && (
            <p className="rounded-lg bg-surface-soft p-4 text-sm text-muted-text">
              Belum ada dataset. Pilih Muat dataset untuk menyiapkan pertanyaan evaluasi.
            </p>
          )}

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
                <StatusBadge tone="neutral">{runs.length} evaluasi</StatusBadge>
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
                <div>
                  <Table aria-label="Riwayat evaluasi" className="min-w-[650px]">
                    <TableHeader className="bg-surface-soft">
                      <TableRow>
                        {["Dataset", "Mode", "Recall@5 terbaik", "Waktu", "Tindakan"].map(
                          (label) => (
                            <TableHead key={label} scope="col" className="px-4 text-muted-text">
                              {label}
                            </TableHead>
                          )
                        )}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {runs.slice(start, start + pageSize).map((run) => {
                        const values = Object.values(run.metrics)
                          .map((metric) => metric.recall_at_5)
                          .filter(Number.isFinite);
                        const bestRecall = values.length ? Math.max(...values) : null;
                        return (
                          <TableRow key={run.run_id} className="border-line">
                            <TableCell className="max-w-64 whitespace-normal px-4 py-4">
                              <p className="font-medium text-tinta">
                                {datasetName(run.dataset_id)}
                              </p>
                              <p
                                title={run.run_id}
                                className="mt-1 truncate font-mono text-xs text-muted-text"
                              >
                                {run.run_id}
                              </p>
                              {isActiveRun(run.status) ? (
                                <p className="mt-1 text-xs text-muted-text tabular-nums">
                                  {run.status === "pending" ? "Antre" : "Berjalan"} ·{" "}
                                  {run.progress_completed} dari {run.progress_total} pertanyaan
                                </p>
                              ) : run.status === "failed" ? (
                                <p
                                  title={run.error ?? undefined}
                                  className="mt-1 line-clamp-2 text-xs text-red"
                                >
                                  Gagal{run.error ? `: ${run.error}` : ""}
                                </p>
                              ) : null}
                            </TableCell>
                            <TableCell className="px-4">
                              <div className="flex flex-wrap gap-1">
                                {sortModes(run.metrics).map((mode) => (
                                  <StatusBadge key={mode} tone="neutral">
                                    {modeLabel[mode] ?? mode}
                                  </StatusBadge>
                                ))}
                              </div>
                            </TableCell>
                            <TableCell
                              className={cn(
                                "px-4 font-mono",
                                bestRecall === null ? "text-muted-text" : scoreColor(bestRecall)
                              )}
                            >
                              {pct(bestRecall)}
                            </TableCell>
                            <TableCell className="px-4 text-xs text-muted-text">
                              {formatDateTime(run.created_at)}
                            </TableCell>
                            <TableCell className="px-4">
                              <Button
                                variant="outline"
                                size="sm"
                                className="min-h-11"
                                onClick={() => void openDetail(run)}
                                aria-label={`Detail evaluasi ${run.run_id}`}
                              >
                                Detail
                              </Button>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3 text-xs text-muted-text">
                    <label className="flex items-center gap-2">
                      Baris per halaman
                      <select
                        className="min-h-11 rounded-md border border-line bg-white px-2 text-tinta"
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
                      {start + 1} sampai {Math.min(start + pageSize, runs.length)} dari{" "}
                      {runs.length} evaluasi
                    </span>
                    <nav aria-label="Pagination evaluasi" className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
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
            </CardContent>
          </Card>
        </>
      )}
      {runError && !runDialogOpen ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-white p-4">
          <p role="alert" className="text-sm text-tinta">
            {runError}
          </p>
          <Button variant="outline" onClick={() => setRunDialogOpen(true)}>
            Buka dialog
          </Button>
        </div>
      ) : null}
      <details className="group rounded-xl border border-line bg-white">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 p-5 marker:hidden sm:px-6 [&::-webkit-details-marker]:hidden">
          <div>
            <h2
              id="evaluation-guide-title"
              className="text-base font-semibold text-tinta"
            >
              Memahami mode dan metrik
            </h2>
            <p className="mt-1 text-sm text-muted-text">
              Gunakan panduan ini untuk membaca hasil perbandingan evaluasi.
            </p>
          </div>
          <ChevronDown
            aria-hidden="true"
            className="size-5 shrink-0 text-muted-text transition-transform group-open:rotate-180"
          />
        </summary>
        <div className="px-5 pb-5 sm:px-6 sm:pb-6">
          <div className="mt-1 space-y-6">
          <div>
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-text">
              Retrieval modes
            </h3>
            <dl className="grid gap-x-8 gap-y-5 md:grid-cols-2">
              {[
                [
                  "Baseline",
                  "Mengurutkan hasil berdasarkan kecocokan kata atau istilah (lexical score), sebagai pembanding awal.",
                ],
                [
                  "Dense",
                  "Mengurutkan hasil berdasarkan kemiripan makna (semantic score), sehingga tidak harus memakai kata yang sama.",
                ],
                [
                  "Hybrid",
                  "Menggabungkan peringkat lexical dan semantic melalui fusion score untuk memanfaatkan keduanya.",
                ],
                [
                  "Re-rank",
                  "Mengurutkan ulang kandidat menggunakan final score setelah penilaian relevansi lanjutan.",
                ],
              ].map(([label, description]) => (
                <div key={label} className="min-w-0 border-l-2 border-line pl-4">
                  <dt className="text-sm font-semibold text-tinta">{label}</dt>
                  <dd className="mt-1 text-sm leading-relaxed text-muted-text">{description}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div>
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-text">
              Evaluation metrics
            </h3>
            <dl className="grid gap-x-8 gap-y-5 md:grid-cols-2">
              {[
                [
                  "Recall@5",
                  "Proporsi dokumen acuan relevan yang ditemukan dalam lima hasil teratas.",
                ],
                [
                  "MRR (Mean Reciprocal Rank)",
                  "Rata-rata kebalikan posisi hasil relevan pertama. Posisi pertama bernilai 1; posisi kedua bernilai 0,5.",
                ],
                [
                  "Citation correctness",
                  "Kesesuaian kutipan dengan dokumen dan pasal acuan pada dataset evaluasi.",
                ],
                [
                  "Faithfulness",
                  "Dukungan sumber terhadap klaim jawaban. Perhitungan memakai skor dukungan klaim, atau kecocokan kata dengan kutipan jika data klaim tidak tersedia.",
                ],
                [
                  "Refusal accuracy",
                  "Ketepatan keputusan menjawab atau menolak dibandingkan jawaban acuan dalam dataset.",
                ],
                [
                  "Hard-negative recall@5",
                  "Recall@5 khusus pertanyaan yang ditandai hard negative: kasus sulit dengan sumber pengecoh yang tampak relevan.",
                ],
              ].map(([label, description]) => (
                <div key={label} className="min-w-0 border-l-2 border-line pl-4">
                  <dt className="text-sm font-semibold text-tinta">{label}</dt>
                  <dd className="mt-1 text-sm leading-relaxed text-muted-text">{description}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
        <p className="mt-6 rounded-lg bg-surface-soft px-4 py-3 text-xs leading-relaxed text-muted-text">
          Semakin tinggi nilai metrik di atas, semakin baik hasil pada dataset ini. Nilai tersebut
          bukan persentase kepastian jawaban. Top K menentukan jumlah hasil yang diambil; pilih
          minimal 5 untuk membandingkan Recall@5 dengan lima hasil penuh.
        </p>
        </div>
      </details>

      {/* Run dialog */}
      <Dialog open={runDialogOpen} onOpenChange={setRunDialogOpen}>
        <DialogContent
          className={`admin-theme ${styles.ingestion} ${styles.detailModal} max-h-[85dvh] overflow-y-auto p-6 sm:max-w-lg`}
        >
          <DialogHeader>
            <DialogTitle>Jalankan evaluasi</DialogTitle>
            <DialogDescription>
              Pilih dataset dan mode pencarian yang ingin dibandingkan. Hasil menyusul:
              halaman boleh ditinggal, progres dipantau dari riwayat.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
              {runError && (
                <p
                  role="alert"
                  className="rounded-lg border border-line bg-red-soft p-3 text-sm text-red"
                >
                  {runError}
                </p>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="eval-dataset">Dataset</Label>
                <Select disabled={submitting} value={runDatasetId} onValueChange={setRunDatasetId}>
                  <SelectTrigger id="eval-dataset" className="min-h-11 w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className={`admin-theme ${styles.ingestion}`}>
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
                        aria-pressed={selected}
                        disabled={submitting}
                        onClick={() => toggleMode(mode)}
                        className={cn(
                          "flex min-h-11 items-center gap-2 rounded-lg border px-3 py-2.5 text-sm transition-colors",
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
                <Label htmlFor="eval-top-k">Jumlah hasil (Top K)</Label>
                <Select disabled={submitting} value={runTopK} onValueChange={setRunTopK}>
                  <SelectTrigger id="eval-top-k" className="min-h-11 w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className={`admin-theme ${styles.ingestion}`}>
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
              {!runModes.length && (
                <p role="status" className="text-xs text-amber">
                  Pilih minimal satu mode untuk menjalankan evaluasi.
                </p>
              )}
            </div>
          <DialogFooter className="mx-0 mb-0 mt-2 rounded-none border-line bg-transparent px-0 pb-0 pt-4">
            <Button
              variant="outline"
              className="min-h-11"
              onClick={() => setRunDialogOpen(false)}
            >
              Batal
            </Button>
            <Button
              className="min-h-11 bg-javanese text-white hover:bg-forest"
              disabled={runModes.length === 0 || !runDatasetId || submitting}
              onClick={() => void startRun()}
            >
              <FlaskConical />
              {runError ? "Coba lagi" : "Jalankan evaluasi"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail dialog */}
      <RunDetailDialog
        loading={detailLoading}
        error={detailError}
        detail={detail}
        open={detailOpen}
        onOpenChange={(open) => {
          setDetailOpen(open);
          if (!open) detailRequest.current++;
        }}
        datasetName={detail ? datasetName(detail.dataset_id) : undefined}
      />
    </div>
  );
}
