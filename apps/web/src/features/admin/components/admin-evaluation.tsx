"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, FlaskConical, Gauge, Loader2, Play, RefreshCw } from "lucide-react";
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
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!running) return;
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [running]);

  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<EvaluationRunDetail | null>(null);

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
      !runModes.length ||
      !datasets.some((item) => item.dataset_id === runDatasetId)
    )
      return;
    runBusy.current = true;
    setRunError("");
    setElapsed(0);
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
      setPage(1);
      setDetailError(false);
      setDetailLoading(false);
      setDetail(next);
      setDetailOpen(true);
      toast.success("Evaluasi selesai dijalankan.");
    } catch {
      setRunError(
        "Hasil evaluasi belum dapat diterima. Periksa koneksi dan muat ulang riwayat sebelum mencoba lagi agar tidak membuat evaluasi ganda."
      );
    } finally {
      runBusy.current = false;
      setRunning(false);
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
              disabled={loading || loadError || seeding || running}
              onClick={() => void seed()}
            >
              <RefreshCw className={seeding ? "animate-spin" : ""} /> Muat dataset
            </Button>
            <Button
              className="bg-javanese text-white hover:bg-forest"
              disabled={loading || loadError || running || seeding || !datasets.length}
              onClick={() => setRunDialogOpen(true)}
            >
              <Play /> Jalankan evaluasi
            </Button>
          </div>
        }
      />

      {loading ? (
        <div aria-busy="true" aria-label="Memuat evaluasi" className="space-y-4">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : loadError ? (
        <div role="alert" className="rounded-xl border border-line bg-white p-6">
          <p className="text-sm text-red">Data evaluasi belum dapat dimuat.</p>
          <Button
            variant="outline"
            className="mt-4"
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
                      {start + 1}–{Math.min(start + pageSize, runs.length)} dari {runs.length}{" "}
                      evaluasi
                    </span>
                    <nav aria-label="Pagination evaluasi" className="flex items-center gap-2">
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
            </CardContent>
          </Card>
        </>
      )}
      {(running || runError) && !runDialogOpen && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-white p-4">
          <p role="status" className="text-sm text-tinta">
            {running
              ? "Evaluasi masih berjalan. Tetap buka halaman ini."
              : "Hasil evaluasi belum dapat diterima."}
          </p>
          <Button variant="outline" onClick={() => setRunDialogOpen(true)}>
            Lihat status
          </Button>
        </div>
      )}
      <section
        aria-labelledby="evaluation-guide-title"
        className="rounded-xl border border-line bg-white p-5 sm:p-6"
      >
        <h2 id="evaluation-guide-title" className="text-base font-semibold text-tinta">
          Memahami mode dan metrik
        </h2>
        <p className="mt-1 text-sm text-muted-text">
          Gunakan panduan ini untuk membaca hasil perbandingan evaluasi.
        </p>
        <div className="mt-6 space-y-6">
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
      </section>

      {/* Run dialog */}
      <Dialog open={runDialogOpen} onOpenChange={setRunDialogOpen}>
        <DialogContent
          className={`admin-theme ${styles.ingestion} ${styles.detailModal} max-h-[85dvh] overflow-y-auto p-6 sm:max-w-lg`}
        >
          <DialogHeader>
            <DialogTitle>{running ? "Evaluasi sedang berjalan" : "Jalankan evaluasi"}</DialogTitle>
            <DialogDescription>
              {running
                ? "Permintaan sudah dikirim. Hasil akan ditampilkan setelah API selesai merespons."
                : "Pilih dataset dan mode pencarian yang ingin dibandingkan."}
            </DialogDescription>
          </DialogHeader>
          {running ? (
            <div className="space-y-5 py-2">
              <div
                className="flex items-center gap-4 rounded-xl border border-line bg-surface-soft p-5"
                role="status"
              >
                <Loader2
                  className="size-7 shrink-0 animate-spin text-forest motion-reduce:animate-none"
                  aria-hidden="true"
                />
                <div>
                  <p className="font-semibold text-tinta">Memproses dataset evaluasi</p>
                  <p className="mt-1 text-sm text-muted-text">
                    Waktu proses bergantung pada jumlah pertanyaan dan mode yang dipilih.
                  </p>
                </div>
              </div>
              <dl className="grid grid-cols-2 gap-4 text-sm">
                <div className="col-span-2">
                  <dt className="text-xs text-muted-text">Dataset</dt>
                  <dd className="mt-1 font-medium break-words">{datasetName(runDatasetId)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-text">Pertanyaan</dt>
                  <dd className="mt-1">
                    {datasets.find((item) => item.dataset_id === runDatasetId)?.questions.length ??
                      "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-text">Jumlah hasil</dt>
                  <dd className="mt-1">{runTopK} per pertanyaan</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-xs text-muted-text">Mode</dt>
                  <dd className="mt-2 flex flex-wrap gap-2">
                    {runModes.map((mode) => (
                      <StatusBadge key={mode} tone="neutral">
                        {modeLabel[mode] ?? mode}
                      </StatusBadge>
                    ))}
                  </dd>
                </div>
              </dl>
              <p className="text-xs text-muted-text">
                Waktu berjalan:{" "}
                <span className="font-mono tabular-nums">
                  {Math.floor(elapsed / 60)}m {elapsed % 60}s
                </span>
                . Tetap buka halaman ini hingga proses selesai.
              </p>
            </div>
          ) : (
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
                <Select disabled={running} value={runDatasetId} onValueChange={setRunDatasetId}>
                  <SelectTrigger id="eval-dataset" className="w-full">
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
                        disabled={running}
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
                <Label htmlFor="eval-top-k">Jumlah hasil (Top K)</Label>
                <Select disabled={running} value={runTopK} onValueChange={setRunTopK}>
                  <SelectTrigger id="eval-top-k" className="w-full">
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
          )}
          <DialogFooter className="mx-0 mb-0 mt-2 rounded-none border-line bg-transparent px-0 pb-0 pt-4">
            <Button variant="outline" onClick={() => setRunDialogOpen(false)}>
              {running ? "Sembunyikan" : "Batal"}
            </Button>
            {!running && (
              <Button
                className="bg-javanese text-white hover:bg-forest"
                disabled={runModes.length === 0 || !runDatasetId}
                onClick={() => void startRun()}
              >
                <FlaskConical />
                {runError ? "Coba lagi" : "Jalankan evaluasi"}
              </Button>
            )}
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
