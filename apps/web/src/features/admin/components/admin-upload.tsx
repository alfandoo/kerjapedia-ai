"use client";

import Link from "next/link";
import { type DragEvent, useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileText,
  Loader2,
  PlayCircle,
  Upload,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PageHeader } from "./primitives";
import { cn } from "@/lib/utils";
import {
  createIngestionJob,
  fetchIngestionJob,
  uploadAdminDocument,
  type AdminUploadResult,
} from "@/features/admin/api";

const topics: { value: string; label: string; desc: string }[] = [
  {
    value: "pkwt",
    label: "PKWT dan PHK",
    desc: "Perjanjian kerja waktu tertentu & pemutusan hubungan kerja",
  },
  {
    value: "pengupahan",
    label: "Pengupahan dan THR",
    desc: "Upah minimum, struktur upah, & tunjangan hari raya",
  },
  {
    value: "bpjs",
    label: "BPJS dan jaminan sosial",
    desc: "Jaminan kesehatan, ketenagakerjaan, & sosial",
  },
  {
    value: "k3",
    label: "Keselamatan dan kesehatan kerja",
    desc: "Keselamatan, kesehatan, & standar lingkungan kerja",
  },
  {
    value: "hubungan_industrial",
    label: "Hubungan industrial",
    desc: "Relasi kerja, serikat pekerja, & penyelesaian sengketa",
  },
];

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

type Step = "select" | "configure" | "done";

export function AdminUpload() {
  const inputRef = useRef<HTMLInputElement>(null);
  const dragCounter = useRef(0);

  const [file, setFile] = useState<File | null>(null);
  const [topic, setTopic] = useState("pkwt");
  const [dragging, setDragging] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<AdminUploadResult | null>(null);

  const [ingesting, setIngesting] = useState(false);
  const [ingestDone, setIngestDone] = useState(false);
  const [ingestError, setIngestError] = useState<string | null>(null);
  const ingestPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (ingestPollRef.current) clearInterval(ingestPollRef.current);
    };
  }, []);

  const step: Step = uploaded ? (ingestDone ? "done" : "configure") : "select";
  const selectedTopic = topics.find((t) => t.value === topic);

  function acceptFile(nextFile: File | undefined) {
    if (!nextFile) return;
    if (nextFile.type !== "application/pdf" && !nextFile.name.toLowerCase().endsWith(".pdf")) {
      setUploadError("File harus berformat PDF.");
      return;
    }
    if (nextFile.size > 50 * 1024 * 1024) {
      setUploadError("Ukuran file melebihi batas 50 MB.");
      return;
    }
    setFile(nextFile);
    setUploadError(null);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragCounter.current = 0;
    setDragging(false);
    acceptFile(event.dataTransfer.files[0]);
  }

  function clearFile() {
    setFile(null);
    setUploadError(null);
    setUploaded(null);
    setIngestDone(false);
    setIngestError(null);
  }

  async function handleUpload() {
    if (!file) return;
    setSubmitting(true);
    setUploadError(null);
    try {
      const result = await uploadAdminDocument(file, topic);
      setUploaded(result);
    } catch (error) {
      setUploadError(`Upload gagal: ${(error as Error).message}`);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleIngest() {
    if (!uploaded) return;
    setIngesting(true);
    setIngestError(null);
    try {
      const job = await createIngestionJob(uploaded.document_id);
      // Job starts as "running" — poll until it finishes
      if (job.status === "running" || job.status === "queued") {
        ingestPollRef.current = setInterval(async () => {
          try {
            const updated = await fetchIngestionJob(job.job_id);
            if (updated.status !== "running" && updated.status !== "queued") {
              if (ingestPollRef.current) clearInterval(ingestPollRef.current);
              ingestPollRef.current = null;
              if (updated.status === "completed") {
                setIngestDone(true);
              } else {
                setIngestError(
                  `Ingestion ${updated.status}: ${(updated as Record<string, unknown>).warnings ?? "Lihat log"}`
                );
              }
              setIngesting(false);
            }
          } catch {
            // keep polling
          }
        }, 3000);
      } else if (job.status === "completed") {
        setIngestDone(true);
        setIngesting(false);
      } else {
        setIngestError(`Ingestion gagal: status ${job.status}`);
        setIngesting(false);
      }
    } catch (error) {
      setIngestError(`Ingestion gagal: ${(error as Error).message}`);
      setIngesting(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Tambah regulasi"
        title="Upload PDF"
        description="Unggah dokumen resmi ketenagakerjaan untuk diproses pipeline ingestion."
        actions={
          <Button asChild variant="outline">
            <Link href="/documents">
              <ArrowLeft /> Kembali
            </Link>
          </Button>
        }
      />

      {/* Step indicator */}
      <div className="flex items-center gap-3">
        {(["select", "configure", "done"] as const).map((s, i) => {
          const active = step === s;
          const completed =
            (s === "select" && (step === "configure" || step === "done")) ||
            (s === "configure" && step === "done");
          return (
            <div key={s} className="flex items-center gap-3">
              {i > 0 && (
                <span
                  className={cn("h-px w-8 transition-colors", completed ? "bg-forest" : "bg-line")}
                />
              )}
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "flex size-7 items-center justify-center rounded-full text-xs font-semibold transition-colors",
                    active && "bg-javanese text-white",
                    completed && "bg-forest text-white",
                    !active && !completed && "bg-surface-soft text-muted-text"
                  )}
                >
                  {completed ? <CheckCircle2 className="size-3.5" /> : i + 1}
                </span>
                <span
                  className={cn(
                    "text-sm transition-colors",
                    active
                      ? "font-semibold text-tinta"
                      : completed
                        ? "text-forest"
                        : "text-muted-text"
                  )}
                >
                  {s === "select" ? "Pilih file" : s === "configure" ? "Konfigurasi" : "Selesai"}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        {/* Left — upload zone */}
        <div className="space-y-4">
          <div
            className={cn(
              "relative flex min-h-[320px] flex-col items-center justify-center gap-5 rounded-2xl border-2 border-dashed p-10 text-center transition-all duration-200",
              dragging
                ? "border-forest bg-teal-soft/50 scale-[1.01]"
                : file
                  ? "border-forest/40 bg-white"
                  : "border-line bg-white hover:border-forest/40 hover:bg-surface-soft/50"
            )}
            onDragEnter={(event) => {
              event.preventDefault();
              dragCounter.current += 1;
              setDragging(true);
            }}
            onDragLeave={(event) => {
              event.preventDefault();
              dragCounter.current -= 1;
              if (dragCounter.current <= 0) setDragging(false);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={handleDrop}
          >
            {/* Background pattern */}
            {!file && !dragging && (
              <div
                className="pointer-events-none absolute inset-0 rounded-2xl opacity-[0.03]"
                aria-hidden="true"
              >
                <svg className="size-full" xmlns="http://www.w3.org/2000/svg">
                  <defs>
                    <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">
                      <circle cx="1.5" cy="1.5" r="1" fill="currentColor" />
                    </pattern>
                  </defs>
                  <rect width="100%" height="100%" fill="url(#grid)" />
                </svg>
              </div>
            )}

            {file ? (
              /* File selected state */
              <div className="flex w-full max-w-md flex-col items-center gap-4">
                <span className="flex size-16 items-center justify-center rounded-2xl bg-teal-soft text-forest">
                  <FileText className="size-7" />
                </span>
                <div className="min-w-0 w-full space-y-1 text-center">
                  <p className="truncate text-base font-semibold text-tinta">{file.name}</p>
                  <p className="text-sm text-muted-text">{formatBytes(file.size)}</p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-muted-text hover:text-red"
                  onClick={clearFile}
                >
                  <X className="size-4" /> Hapus file
                </Button>
              </div>
            ) : (
              /* Empty state */
              <>
                <span
                  className={cn(
                    "flex size-16 items-center justify-center rounded-2xl transition-colors duration-200",
                    dragging ? "bg-forest text-white" : "bg-teal-soft text-forest"
                  )}
                >
                  <Upload className="size-7" />
                </span>
                <div className="space-y-1.5">
                  <p className="font-display text-lg font-semibold text-tinta">
                    {dragging ? "Lepaskan file di sini" : "Tarik PDF ke area ini"}
                  </p>
                  <p className="text-sm text-muted-text">
                    atau klik tombol di bawah untuk memilih file
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="lg"
                  onClick={() => inputRef.current?.click()}
                >
                  <FileText className="size-4" /> Pilih file dari komputer
                </Button>
                <p className="text-xs text-muted-text/70">Format PDF, maksimum 50 MB</p>
              </>
            )}

            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              className="sr-only"
              onChange={(event) => acceptFile(event.target.files?.[0])}
            />
          </div>

          {/* Error */}
          {uploadError ? (
            <div className="rounded-xl border border-red/25 bg-red-soft px-4 py-3 text-sm text-red">
              {uploadError}
            </div>
          ) : null}
        </div>

        {/* Right — config & actions */}
        <div className="space-y-4">
          {/* Topic selector */}
          <Card>
            <CardContent className="space-y-4 p-5">
              <div className="space-y-1.5">
                <Label className="text-sm font-semibold">Topik regulasi</Label>
                <p className="text-xs text-muted-text">
                  Pilih kategori yang paling sesuai untuk dokumen ini.
                </p>
              </div>
              <Select value={topic} onValueChange={setTopic}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {topics.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedTopic && <p className="text-xs text-muted-text">{selectedTopic.desc}</p>}

              <div className="border-t border-line pt-3">
                <p className="text-xs font-medium text-tinta">Yang akan terjadi:</p>
                <ul className="mt-2 space-y-1.5">
                  {[
                    "Header PDF akan divalidasi",
                    "Dokumen terdaftar sebagai draft",
                    "Publikasi menunggu review admin",
                  ].map((item) => (
                    <li key={item} className="flex items-center gap-2 text-xs text-muted-text">
                      <CheckCircle2 className="size-3.5 shrink-0 text-forest" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </CardContent>
          </Card>

          {/* Upload button */}
          {!uploaded && (
            <Button
              className="w-full bg-javanese text-white hover:bg-forest"
              size="lg"
              disabled={!file || submitting}
              onClick={() => void handleUpload()}
            >
              {submitting ? (
                <>
                  <Loader2 className="animate-spin" /> Mengunggah…
                </>
              ) : (
                <>
                  <Upload /> Unggah PDF
                </>
              )}
            </Button>
          )}

          {/* Uploaded — ready for ingestion */}
          {uploaded && !ingestDone && (
            <Card className="border-forest/25 bg-teal-soft/30">
              <CardContent className="space-y-3 p-5">
                <div className="flex items-center gap-2.5">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-forest text-white">
                    <CheckCircle2 className="size-4" />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-tinta">
                      {uploaded.file_name}
                    </p>
                    <p className="truncate font-mono text-xs text-muted-text">
                      {uploaded.document_id}
                    </p>
                  </div>
                </div>
                <Button
                  className="w-full bg-javanese text-white hover:bg-forest"
                  size="lg"
                  disabled={ingesting}
                  onClick={() => void handleIngest()}
                >
                  {ingesting ? (
                    <>
                      <Loader2 className="animate-spin" /> Memproses…
                    </>
                  ) : (
                    <>
                      <PlayCircle /> Mulai ingestion
                    </>
                  )}
                </Button>
                {ingestError && <p className="text-xs text-red">{ingestError}</p>}
              </CardContent>
            </Card>
          )}

          {/* Done */}
          {ingestDone && (
            <Card className="border-forest/25 bg-teal-soft/30">
              <CardContent className="space-y-4 p-5 text-center">
                <span className="mx-auto flex size-12 items-center justify-center rounded-full bg-forest text-white">
                  <CheckCircle2 className="size-6" />
                </span>
                <div className="space-y-1">
                  <p className="font-semibold text-tinta">Upload & ingestion selesai</p>
                  <p className="text-xs text-muted-text">
                    Dokumen telah diproses dan siap untuk direview.
                  </p>
                </div>
                <div className="flex flex-col gap-2">
                  <Button asChild variant="outline" className="w-full">
                    <Link href="/documents">
                      Lihat dokumen <ArrowRight className="size-4" />
                    </Link>
                  </Button>
                  <Button variant="ghost" className="w-full text-muted-text" onClick={clearFile}>
                    Upload lagi
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
