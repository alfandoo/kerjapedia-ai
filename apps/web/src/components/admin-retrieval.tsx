"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FlaskConical,
  Loader2,
  Play,
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
import { PageHeader, StatusBadge } from "@/components/admin/primitives";
import { cn } from "@/lib/utils";
import { runRetrievalPlayground } from "@/lib/api";
import { fallbackRetrievalResults } from "@/lib/sample-data";
import type { RetrievalPlaygroundResult } from "@/lib/types";

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const tone =
    score >= 0.8 ? "text-forest" : score >= 0.5 ? "text-amber" : "text-muted-text";
  return (
    <span className={cn("font-mono text-sm font-semibold tabular-nums", tone)}>
      {pct}%
    </span>
  );
}

function ScoreBar({ score }: { score: number }) {
  const color =
    score >= 0.8 ? "bg-forest" : score >= 0.5 ? "bg-amber" : "bg-muted-text/40";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-soft">
      <div
        className={cn("h-full rounded-full transition-all", color)}
        style={{ width: `${Math.min(100, score * 100)}%` }}
      />
    </div>
  );
}

export function AdminRetrieval() {
  const [question, setQuestion] = useState(
    "Apakah pekerja PKWT berhak mendapat uang kompensasi?"
  );
  const [topK, setTopK] = useState(5);
  const [regulationType, setRegulationType] = useState("all");
  const [year, setYear] = useState("");
  const [showFilters, setShowFilters] = useState(false);

  const [results, setResults] = useState(fallbackRetrievalResults);
  const [selectedId, setSelectedId] = useState(fallbackRetrievalResults[0]?.chunk_id ?? "");
  const [latency, setLatency] = useState(184);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [hasRun, setHasRun] = useState(false);
  const [status, setStatus] = useState("Hasil contoh siap untuk ditinjau.");

  const selected = results.find((item) => item.chunk_id === selectedId) ?? null;

  async function run() {
    setRunning(true);
    setStatus("Menjalankan hybrid retrieval dan rerank...");
    try {
      const response = await runRetrievalPlayground(
        question,
        topK,
        regulationType === "all" ? undefined : regulationType,
        year ? Number(year) : undefined
      );
      setResults(response.results);
      setSelectedId(response.results[0]?.chunk_id ?? "");
      setLatency(response.latency_ms);
      setWarnings(response.warnings);
      setHasRun(true);
      setStatus(
        response.should_refuse ? "Hasil berada di bawah ambang jawaban." : "Retrieval selesai."
      );
    } catch {
      setStatus("API belum tersedia; hasil contoh tetap ditampilkan.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Pengujian retrieval"
        title="Retrieval Playground"
        description="Uji kualitas retrieval sebelum perubahan dipublikasikan."
      />

      <div className="grid gap-6 lg:grid-cols-[400px_1fr]">
        {/* Left — config */}
        <div className="space-y-4">
          <Card>
            <CardContent className="space-y-4 pt-5">
              {/* Question */}
              <div className="space-y-1.5">
                <Label className="text-sm font-semibold">Pertanyaan uji</Label>
                <Textarea
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  rows={3}
                  placeholder="Tulis pertanyaan tentang regulasi ketenagakerjaan..."
                />
              </div>

              {/* Top K + Run */}
              <div className="flex items-end gap-3">
                <div className="w-24 shrink-0 space-y-1.5">
                  <Label className="text-sm font-semibold">Top K</Label>
                  <Input
                    type="number"
                    min={1}
                    max={10}
                    value={topK}
                    onChange={(event) => setTopK(Number(event.target.value))}
                  />
                </div>
                <Button
                  className="flex-1 bg-javanese text-white hover:bg-forest"
                  disabled={running || question.trim().length < 4}
                  onClick={() => void run()}
                >
                  {running ? (
                    <Loader2 className="animate-spin" />
                  ) : (
                    <Search className="size-4" />
                  )}
                  {running ? "Mencari..." : "Jalankan"}
                </Button>
              </div>

              {/* Advanced filters toggle */}
              <button
                type="button"
                onClick={() => setShowFilters(!showFilters)}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-muted-text transition-colors hover:bg-surface-soft hover:text-tinta"
              >
                {showFilters ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
                Filter lanjutan
              </button>

              {/* Advanced filters */}
              {showFilters && (
                <div className="space-y-3 rounded-lg border border-line bg-surface-soft/50 p-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs">Jenis regulasi</Label>
                      <Select value={regulationType} onValueChange={setRegulationType}>
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">Semua</SelectItem>
                          <SelectItem value="PP">PP</SelectItem>
                          <SelectItem value="UU">UU</SelectItem>
                          <SelectItem value="Permenaker">Permenaker</SelectItem>
                          <SelectItem value="Perpres">Perpres</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">Tahun</Label>
                      <Input
                        type="number"
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
                  className={cn(
                    "rounded-lg px-3 py-2 text-xs",
                    hasRun && !warnings.length
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

          {/* Selected quote — integrated */}
          {selected && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Kutipan terpilih</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
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
                    <div key={m.label} className="flex items-center gap-3">
                      <span className="w-14 shrink-0 text-xs text-muted-text">{m.label}</span>
                      <div className="flex-1">
                        <ScoreBar score={m.value} />
                      </div>
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
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right — results */}
        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="flex items-center gap-3">
              Hasil retrieval
              <StatusBadge tone="info">
                {results.length} chunk · {latency} ms
              </StatusBadge>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {results.length === 0 ? (
              <div className="flex flex-col items-center gap-2 px-4 py-16 text-center">
                <span className="flex size-12 items-center justify-center rounded-2xl bg-surface-soft text-muted-text">
                  <FlaskConical className="size-6" />
                </span>
                <p className="text-sm font-semibold text-tinta">Tidak ada hasil</p>
                <p className="max-w-xs text-sm text-muted-text">
                  Jalankan retrieval dengan pertanyaan atau filter yang berbeda.
                </p>
              </div>
            ) : (
              <ul className="divide-y">
                {results.map((result, index) => {
                  const active = result.chunk_id === selectedId;
                  return (
                    <li
                      key={result.chunk_id}
                      role="button"
                      tabIndex={0}
                      onClick={() => setSelectedId(result.chunk_id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelectedId(result.chunk_id);
                        }
                      }}
                      className={cn(
                        "flex cursor-pointer items-start gap-4 px-4 py-3.5 transition-colors",
                        active
                          ? "bg-teal-soft/40 shadow-[inset_3px_0_0_var(--teal)]"
                          : "hover:bg-surface-soft"
                      )}
                    >
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
                        <div className="flex items-center gap-2">
                          <p className="truncate text-sm font-semibold text-tinta">
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
                        <ScoreBar score={result.final_score} />
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
