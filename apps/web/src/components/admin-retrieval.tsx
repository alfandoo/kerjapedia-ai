"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, FlaskConical, Loader2, Play } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { PageHeader } from "@/components/admin/primitives";
import { cn } from "@/lib/utils";
import { runRetrievalPlayground } from "@/lib/api";
import { fallbackRetrievalResults } from "@/lib/sample-data";
import type { RetrievalPlaygroundResult } from "@/lib/types";

function ScoreBar({ score }: { score: number }) {
  return (
    <div className="h-1 w-16 overflow-hidden rounded-full bg-muted">
      <div
        className="h-full rounded-full bg-teal"
        style={{ width: `${Math.min(100, score * 100)}%` }}
      />
    </div>
  );
}

function RetrievalQuote({
  result,
  warnings,
}: {
  result: RetrievalPlaygroundResult;
  warnings: string[];
}) {
  const metrics = [
    { label: "Chunk ID", value: result.chunk_id },
    { label: "Halaman", value: String(result.page_start) },
    { label: "Lexical", value: result.lexical_score.toFixed(2) },
    { label: "Vector", value: result.semantic_score.toFixed(2) },
    { label: "Rerank", value: result.rerank_score.toFixed(2) },
  ];

  return (
    <div className="space-y-4">
      <blockquote className="rounded-lg border bg-muted/40 p-4 text-sm leading-relaxed">
        &ldquo;{result.quote}&rdquo;
      </blockquote>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-5">
        {metrics.map((metric) => (
          <div key={metric.label} className="min-w-0">
            <dt className="text-xs text-muted-foreground">{metric.label}</dt>
            <dd className="truncate font-mono text-sm font-medium tabular-nums">{metric.value}</dd>
          </div>
        ))}
      </dl>

      <div
        className={cn(
          "flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-sm",
          warnings.length
            ? "border-amber/30 bg-amber-soft/60 text-amber"
            : "border-teal/30 bg-teal-soft/60 text-teal"
        )}
      >
        {warnings.length ? (
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
        ) : (
          <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
        )}
        <span>{warnings.length ? warnings.join(", ") : "Tidak ada peringatan"}</span>
      </div>
    </div>
  );
}

export function AdminRetrieval() {
  const [question, setQuestion] = useState("Apakah pekerja PKWT berhak mendapat uang kompensasi?");
  const [topK, setTopK] = useState(5);
  const [regulationType, setRegulationType] = useState<string>("all");
  const [year, setYear] = useState<number | null>(null);
  const [legalStatus, setLegalStatus] = useState<string>("all");
  const [results, setResults] = useState(fallbackRetrievalResults);
  const [selectedId, setSelectedId] = useState(fallbackRetrievalResults[0].chunk_id);
  const [latency, setLatency] = useState(184);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
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
        year ?? undefined,
        legalStatus === "all" ? undefined : legalStatus
      );
      setResults(response.results);
      setSelectedId(response.results[0]?.chunk_id ?? "");
      setLatency(response.latency_ms);
      setWarnings(response.warnings);
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
        description="Uji retrieval sebelum perubahan dipublikasikan."
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Konfigurasi uji</CardTitle>
            <CardDescription>Pertanyaan dan parameter pencarian</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label>Pertanyaan uji</Label>
              <Textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                rows={4}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Top K</Label>
              <Input
                type="number"
                min={1}
                max={10}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
              />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label>Jenis</Label>
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
                <Label>Tahun</Label>
                <Input
                  type="number"
                  min={1945}
                  max={2100}
                  placeholder="Semua"
                  value={year ?? ""}
                  onChange={(event) =>
                    setYear(event.target.value ? Number(event.target.value) : null)
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label>Status</Label>
                <Select value={legalStatus} onValueChange={setLegalStatus}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Semua</SelectItem>
                    <SelectItem value="active">Aktif</SelectItem>
                    <SelectItem value="needs_verification">Perlu verifikasi</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>Mode retrieval</Label>
              <Select defaultValue="hybrid">
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="hybrid">Hybrid + rerank</SelectItem>
                  <SelectItem value="dense">Dense</SelectItem>
                  <SelectItem value="lexical">Lexical</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Topik</Label>
              <Select defaultValue="pkwt">
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="pkwt">PKWT</SelectItem>
                  <SelectItem value="phk">PHK</SelectItem>
                  <SelectItem value="pengupahan">Pengupahan</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Status hukum</Label>
              <Select defaultValue="active">
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Berlaku</SelectItem>
                  <SelectItem value="all">Semua status</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Button
              className="w-full bg-teal text-white hover:bg-teal-strong"
              disabled={running || question.trim().length < 4}
              onClick={() => void run()}
            >
              {running ? <Loader2 className="animate-spin" /> : <Play />}
              {running ? "Menjalankan..." : "Jalankan retrieval"}
            </Button>

            {status ? <p className="text-sm text-muted-foreground">{status}</p> : null}
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Hasil retrieval</CardTitle>
            <CardDescription className="flex items-center gap-2">
              {results.length} chunk ditemukan
              <Badge variant="secondary" className="font-mono tabular-nums">
                {latency} ms
              </Badge>
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <ul className="divide-y">
              {results.map((result, index) => {
                const selectedRow = result.chunk_id === selectedId;
                return (
                  <li
                    key={result.chunk_id}
                    className={cn(
                      "flex cursor-pointer flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 transition-colors",
                      selectedRow ? "bg-teal-soft/40" : "hover:bg-muted/50"
                    )}
                    onClick={() => setSelectedId(result.chunk_id)}
                  >
                    <span className="w-5 shrink-0 font-mono text-sm text-muted-foreground tabular-nums">
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{result.short_title}</p>
                      <p className="truncate font-mono text-xs text-muted-foreground">
                        {result.chunk_id}
                      </p>
                    </div>
                    <span className="w-24 shrink-0 text-sm">
                      {result.article ?? "-"}
                      <small className="block text-xs text-muted-foreground">
                        Hal. {result.page_start}
                      </small>
                    </span>
                    <span className="flex w-24 shrink-0 flex-col items-end gap-1">
                      <strong className="font-mono text-sm tabular-nums">
                        {result.final_score.toFixed(2)}
                      </strong>
                      <ScoreBar score={result.final_score} />
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={(event) => {
                        event.stopPropagation();
                        setSelectedId(result.chunk_id);
                      }}
                    >
                      Lihat kutipan
                    </Button>
                  </li>
                );
              })}
              {results.length === 0 ? (
                <li className="flex flex-col items-center gap-2 px-4 py-12 text-center">
                  <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                    <FlaskConical className="size-5" />
                  </span>
                  <p className="text-sm font-medium">Tidak ada chunk yang melewati filter</p>
                  <p className="text-sm text-muted-foreground">
                    Jalankan retrieval dengan kata kunci lain.
                  </p>
                </li>
              ) : null}
            </ul>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Kutipan terpilih</CardTitle>
          <CardDescription>Detail chunk yang sedang ditinjau</CardDescription>
        </CardHeader>
        <CardContent>
          {selected ? (
            <RetrievalQuote result={selected} warnings={warnings} />
          ) : (
            <p className="text-sm text-muted-foreground">Pilih chunk untuk melihat kutipan.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
