"use client";

import { useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FlaskConical,
  Loader2,
  Search,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader, StatusBadge } from "./primitives";
import { cn } from "@/lib/utils";
import { runRetrievalPlayground } from "@/features/admin/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import styles from "./admin-ingestion.module.css";
import type { RetrievalPlaygroundResult } from "@/features/admin/types";

function ScoreBadge({ score }: { score: number }) {
  return (
    <span className="font-mono text-sm font-semibold tabular-nums text-forest">
      {Number.isFinite(score) ? score.toFixed(3) : "Belum ada data"}
    </span>
  );
}

export function AdminRetrieval() {
  const [question, setQuestion] = useState("Apakah pekerja PKWT berhak mendapat uang kompensasi?");
  const [topK, setTopK] = useState(5);
  const [regulationType, setRegulationType] = useState("all");
  const [year, setYear] = useState("");
  const [showFilters, setShowFilters] = useState(false);

  const [results, setResults] = useState<RetrievalPlaygroundResult[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [latency, setLatency] = useState<number | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [hasRun, setHasRun] = useState(false);
  const [status, setStatus] = useState("");

  const [detailOpen, setDetailOpen] = useState(false);
  const [failed, setFailed] = useState(false);
  const busy = useRef(false);
  const valid =
    question.trim().length >= 4 &&
    Number.isInteger(topK) &&
    topK >= 1 &&
    topK <= 10 &&
    (!year || (Number.isInteger(Number(year)) && Number(year) >= 1945 && Number(year) <= 2100));
  const selected = results.find((item) => item.chunk_id === selectedId) ?? null;

  async function run() {
    if (busy.current || !valid) return;
    busy.current = true;
    setRunning(true);
    setFailed(false);
    setResults([]);
    setWarnings([]);
    setLatency(null);
    setHasRun(false);
    setDetailOpen(false);
    setStatus("Menjalankan hybrid retrieval dan rerank...");
    try {
      const response = await runRetrievalPlayground(
        question.trim(),
        topK,
        regulationType === "all" ? undefined : regulationType,
        year ? Number(year) : undefined
      );
      setResults(response.results);
      setSelectedId("");
      setLatency(response.latency_ms);
      setWarnings(response.warnings);
      setHasRun(true);
      setStatus(
        response.should_refuse ? "Hasil berada di bawah ambang jawaban." : "Retrieval selesai."
      );
    } catch {
      setFailed(true);
      setStatus("Pencarian gagal. Periksa koneksi lalu jalankan kembali.");
    } finally {
      busy.current = false;
      setRunning(false);
    }
  }

  return (
    <div className={`${styles.ingestion} space-y-6`}>
      <PageHeader
        eyebrow="Evaluasi"
        title="Retrieval Playground"
        description="Uji pertanyaan, periksa sumber yang ditemukan, dan bandingkan skor relevansinya."
      />

      <div className="grid items-start gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
        {/* Left - config */}
        <div className="space-y-4">
          <Card>
            <CardContent className="space-y-4 pt-5">
              {/* Question */}
              <div className="space-y-1.5">
                <Label htmlFor="retrieval-question" className="text-sm font-semibold">
                  Pertanyaan uji
                </Label>
                <Textarea
                  id="retrieval-question"
                  disabled={running}
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  rows={5}
                  placeholder="Tulis pertanyaan tentang regulasi ketenagakerjaan..."
                />
              </div>

              {/* Top K + Run */}
              <div className="flex items-end gap-3">
                <div className="w-24 shrink-0 space-y-1.5">
                  <Label htmlFor="retrieval-count" className="text-sm font-semibold">
                    Jumlah hasil
                  </Label>
                  <Input
                    id="retrieval-count"
                    disabled={running}
                    type="number"
                    min={1}
                    max={10}
                    value={topK}
                    onChange={(event) => setTopK(Number(event.target.value))}
                  />
                </div>
                <Button
                  className="flex-1 bg-javanese text-white hover:bg-forest"
                  disabled={running || !valid}
                  onClick={() => void run()}
                >
                  {running ? <Loader2 className="animate-spin" /> : <Search className="size-4" />}
                  {running ? "Mencari..." : "Cari sumber"}
                </Button>
              </div>

              <p className="text-xs text-muted-text">
                Masukkan minimal 4 karakter. Jumlah hasil 1–10; tahun opsional antara 1945–2100.
              </p>
              {/* Advanced filters toggle */}
              <button
                type="button"
                aria-expanded={showFilters}
                aria-controls="retrieval-filters"
                onClick={() => setShowFilters(!showFilters)}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-muted-text transition-colors hover:bg-surface-soft hover:text-tinta"
              >
                {showFilters ? (
                  <ChevronUp className="size-3.5" />
                ) : (
                  <ChevronDown className="size-3.5" />
                )}
                Filter lanjutan
              </button>

              {/* Advanced filters */}
              {showFilters && (
                <div
                  id="retrieval-filters"
                  className="space-y-3 rounded-lg border border-line bg-surface-soft/50 p-3"
                >
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label htmlFor="retrieval-type" className="text-xs">
                        Jenis regulasi
                      </Label>
                      <Select
                        disabled={running}
                        value={regulationType}
                        onValueChange={setRegulationType}
                      >
                        <SelectTrigger id="retrieval-type" className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className={`admin-theme ${styles.ingestion}`}>
                          <SelectItem value="all">Semua</SelectItem>
                          <SelectItem value="PP">PP</SelectItem>
                          <SelectItem value="UU">UU</SelectItem>
                          <SelectItem value="Permenaker">Permenaker</SelectItem>
                          <SelectItem value="Perpres">Perpres</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="retrieval-year" className="text-xs">
                        Tahun
                      </Label>
                      <Input
                        type="number"
                        id="retrieval-year"
                        disabled={running}
                        min={1945}
                        max={2100}
                        placeholder="Semua"
                        value={year}
                        onChange={(event) => setYear(event.target.value)}
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Status */}
              {status && (
                <p
                  role={failed ? "alert" : "status"}
                  className={cn(
                    "rounded-lg px-3 py-2 text-xs",
                    failed
                      ? "bg-red-soft text-red"
                      : hasRun && !warnings.length
                        ? "bg-teal-soft/50 text-forest"
                        : hasRun && warnings.length
                          ? "bg-amber-soft text-amber"
                          : "bg-surface-soft text-muted-text"
                  )}
                >
                  {status}
                </p>
              )}
            </CardContent>
          </Card>

          {/* Selected quote - integrated */}
          <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
            <DialogContent
              className={`admin-theme ${styles.ingestion} ${styles.detailModal} max-h-[85dvh] overflow-y-auto p-6 sm:max-w-xl`}
            >
              <DialogHeader className="pr-8">
                <DialogTitle>Detail sumber</DialogTitle>
                <DialogDescription>
                  {selected?.short_title} {selected?.article} · Halaman {selected?.page_start}–
                  {selected?.page_end}
                </DialogDescription>
              </DialogHeader>
              {selected && (
                <div className="space-y-4">
                  <blockquote className="rounded-lg border-l-4 border-forest bg-teal-soft/30 px-4 py-3 text-sm leading-relaxed text-tinta">
                    &ldquo;{selected.quote}&rdquo;
                  </blockquote>

                  {/* Score breakdown */}
                  <div className="space-y-2">
                    {[
                      { label: "Lexical", value: selected.lexical_score },
                      { label: "Semantic", value: selected.semantic_score },
                      { label: "Rerank", value: selected.rerank_score },
                      { label: "Final", value: selected.final_score },
                    ].map((m) => (
                      <div key={m.label} className="flex flex-wrap items-center gap-3">
                        <span className="w-14 shrink-0 text-xs text-muted-text">{m.label}</span>
                        <div className="flex-1" />
                        <ScoreBadge score={m.value} />
                      </div>
                    ))}
                  </div>

                  {/* Warnings */}
                  {warnings.length > 0 && (
                    <div className="flex items-start gap-2 rounded-lg border border-amber/25 bg-amber-soft/60 px-3 py-2 text-xs text-amber">
                      <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                      <span>{warnings.join(", ")}</span>
                    </div>
                  )}
                  {hasRun && warnings.length === 0 && (
                    <div className="flex items-center gap-2 rounded-lg border border-forest/20 bg-teal-soft/50 px-3 py-2 text-xs text-forest">
                      <CheckCircle2 className="size-3.5 shrink-0" />
                      <span>Tidak ada peringatan</span>
                    </div>
                  )}
                  <p className="text-xs text-muted-text">
                    Skor dari API, bukan persentase kepastian jawaban. Skala tiap metode dapat
                    berbeda.
                  </p>
                </div>
              )}
            </DialogContent>
          </Dialog>
        </div>

        {/* Right - results */}
        <Card className="min-w-0 h-fit">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-3">
              Hasil retrieval
              {hasRun && (
                <StatusBadge tone="info">
                  {results.length} sumber · {latency} ms
                </StatusBadge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {warnings.length > 0 && (
              <div
                role="status"
                className="mx-4 mb-4 rounded-lg bg-amber-soft p-3 text-xs text-amber"
              >
                {warnings.join(" · ")}
              </div>
            )}
            {results.length === 0 ? (
              <div className="flex flex-col items-center gap-2 px-4 py-16 text-center">
                <span className="flex size-12 items-center justify-center rounded-2xl bg-surface-soft text-muted-text">
                  <FlaskConical className="size-6" />
                </span>
                <p className="text-sm font-semibold text-tinta">
                  {running
                    ? "Mencari sumber…"
                    : failed
                      ? "Pencarian belum berhasil"
                      : hasRun
                        ? "Tidak ada sumber ditemukan"
                        : "Siap menguji pencarian"}
                </p>
                <p className="max-w-xs text-sm text-muted-text">
                  {running
                    ? "Hasil akan muncul setelah pencarian selesai."
                    : hasRun
                      ? "Coba pertanyaan atau filter yang berbeda."
                      : "Isi pertanyaan, lalu pilih Cari sumber untuk melihat hasil dari API."}
                </p>
              </div>
            ) : (
              <ul className="divide-y">
                {results.map((result, index) => {
                  const active = result.chunk_id === selectedId;
                  return (
                    <li key={result.chunk_id} className="flex items-start gap-3 px-4 py-4">
                      {/* Rank */}
                      <span
                        className={cn(
                          "flex size-7 shrink-0 items-center justify-center rounded-lg font-mono text-xs font-semibold",
                          active ? "bg-forest text-white" : "bg-surface-soft text-muted-text"
                        )}
                      >
                        {index + 1}
                      </span>

                      {/* Info */}
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="break-words text-sm font-semibold text-tinta">
                            {result.short_title}
                          </p>
                          {result.article && (
                            <span className="shrink-0 text-xs text-muted-text">
                              {result.article}
                            </span>
                          )}
                        </div>
                        <p className="truncate text-xs text-muted-text">
                          Hal. {result.page_start}–{result.page_end} · {result.chunk_id}
                        </p>
                      </div>

                      {/* Score */}
                      <div className="w-20 shrink-0 space-y-1">
                        <ScoreBadge score={result.final_score} />
                        <p className="text-xs text-muted-text">Skor final</p>
                        <Button
                          size="sm"
                          variant="outline"
                          aria-label={`Detail ${result.short_title}`}
                          onClick={() => {
                            setSelectedId(result.chunk_id);
                            setDetailOpen(true);
                          }}
                        >
                          Detail
                        </Button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
