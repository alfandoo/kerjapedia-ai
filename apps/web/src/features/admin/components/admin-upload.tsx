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
import styles from "./admin-upload.module.css";
import detailStyles from "./document-detail.module.css";
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
  const [topic, setTopic] = useState("");
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
    if (!nextFile || submitting || ingesting || uploaded) return;
    if (nextFile.size === 0) {
      setUploadError("File kosong. Pilih PDF yang memiliki isi.");
      return;
    }
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
    if (submitting || ingesting || uploaded) return;
    if (event.dataTransfer.files.length > 1) {
      setUploadError("Unggah satu PDF dalam satu proses.");
      return;
    }
    acceptFile(event.dataTransfer.files[0]);
  }

  function clearFile() {
    if (submitting || ingesting) return;
    if (inputRef.current) inputRef.current.value = "";
    setFile(null);
    setUploadError(null);
    setUploaded(null);
    setIngestDone(false);
    setIngestError(null);
  }

  async function handleUpload() {
    if (!file || !topic || submitting || uploaded) return;
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
    if (!uploaded || ingesting || ingestDone) return;
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
    <div className={`${styles.upload} space-y-6`}>
      <PageHeader
        eyebrow="Tambah regulasi"
        title="Upload PDF"
        description="Unggah PDF resmi, pilih topiknya, lalu proses dokumen untuk ditinjau sebelum diterbitkan."
        actions={
          <Button asChild variant="outline">
            <Link href="/documents">
              <ArrowLeft /> Daftar dokumen
            </Link>
          </Button>
        }
      />

      {/* Step indicator */}
      <div
        className="flex flex-wrap items-center gap-x-3 gap-y-3"
        aria-label="Tahapan unggah dokumen"
      >
        {(["select", "configure", "done"] as const).map((s, i) => {
          const active = step === s;
          const completed =
            (s === "select" && (step === "configure" || step === "done")) ||
            (s === "configure" && step === "done");
          return (
            <div
              key={s}
              aria-current={active ? "step" : undefined}
              className="flex items-center gap-3"
            >
              {i > 0 && (
                <span
                  className={cn(
                    "h-px w-3 sm:w-8 transition-colors",
                    completed ? "bg-forest" : "bg-line"
                  )}
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
                  {s === "select" ? "Pilih dokumen" : s === "configure" ? "Proses" : "Selesai"}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        {/* Left — upload zone */}
        <div className="space-y-4">
          <div
            className={cn(
              styles.dropzone,
              dragging && styles.dragging,
              "relative flex min-h-[300px] min-w-0 flex-col items-center justify-center gap-5 rounded-2xl border-2 border-dashed p-6 text-center sm:p-8",
              dragging
                ? "border-forest bg-teal-soft/50 scale-[1.01]"
                : file
                  ? "border-forest/40 bg-white"
                  : "border-line bg-white hover:border-forest/40 hover:bg-surface-soft/50"
            )}
            onDragEnter={(event) => {
              event.preventDefault();
              if (submitting || ingesting || uploaded) return;
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
            {file ? (
              /* File selected state */
              <div className="flex w-full max-w-md flex-col items-center gap-4">
                <span className="flex size-16 items-center justify-center rounded-2xl bg-teal-soft text-forest">
                  <FileText className="size-7" />
                </span>
                <div className="min-w-0 w-full space-y-1 text-center">
                  <p title={file.name} className="break-words text-base font-semibold text-tinta">
                    {file.name}
                  </p>
                  <p className="text-sm text-muted-text">{formatBytes(file.size)}</p>
                </div>
                {!uploaded && (
                  <Button
                    type="button"
                    disabled={submitting || ingesting}
                    variant="ghost"
                    size="sm"
                    className="text-muted-text hover:text-red"
                    onClick={clearFile}
                  >
                    <X className="size-4" /> Ganti file
                  </Button>
                )}
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
                <p className="text-xs text-muted-text">Format PDF, maksimum 50 MB</p>
              </>
            )}

            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              className="sr-only"
              aria-label="Pilih dokumen PDF"
              tabIndex={-1}
              disabled={submitting || ingesting || !!uploaded}
              onChange={(event) => {
                acceptFile(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </div>

          {/* Error */}
          {uploadError ? (
            <div
              role="alert"
              className="rounded-xl border border-red/25 bg-red-soft px-4 py-3 text-sm text-red"
            >
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
                <Label htmlFor="upload-topic" className="text-sm font-semibold">
                  Topik regulasi
                </Label>
                <p className="text-xs text-muted-text">
                  Pilih kategori yang paling sesuai untuk dokumen ini.
                </p>
              </div>
              <Select value={topic} onValueChange={setTopic} disabled={submitting || !!uploaded}>
                <SelectTrigger id="upload-topic" className="min-h-11 w-full">
                  <SelectValue placeholder="Pilih topik regulasi" />
                </SelectTrigger>
                <SelectContent className={detailStyles.popup}>
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
                    "Format dan ukuran PDF diperiksa",
                    "File disimpan sebagai dokumen draft",
                    "Tinjau dokumen sebelum diterbitkan",
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

          {!uploaded && (
            <p className="text-xs leading-relaxed text-muted-text" role="status">
              {!file
                ? "Pilih satu PDF untuk melanjutkan."
                : !topic
                  ? "Pilih topik sebelum mengunggah."
                  : "Dokumen siap diunggah. Pemrosesan dimulai setelah unggahan selesai."}
            </p>
          )}
          {/* Upload button */}
          {!uploaded && (
            <Button
              className={`${styles.primary} w-full bg-javanese text-white hover:bg-forest`}
              size="lg"
              disabled={!file || !topic || submitting}
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
                  className={`${styles.primary} w-full bg-javanese text-white hover:bg-forest`}
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
                      <PlayCircle /> Proses dokumen
                    </>
                  )}
                </Button>
                {ingestError && (
                  <p role="alert" className="text-xs text-red">
                    {ingestError}
                  </p>
                )}
                <Link
                  href="/admin/ingestion"
                  className="block text-center text-xs font-semibold text-forest underline underline-offset-4"
                >
                  Lihat status pemrosesan
                </Link>
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
                  <p className="font-semibold text-tinta">Pemrosesan selesai</p>
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
