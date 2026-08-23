"use client";

import Link from "next/link";
import { type DragEvent, useRef, useState } from "react";
import { ArrowLeft, CheckCircle2, FileText, Loader2, PlayCircle, Upload, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PageHeader } from "@/components/admin/primitives";
import { cn } from "@/lib/utils";
import { createIngestionJob, uploadAdminDocument, type AdminUploadResult } from "@/lib/api";

const topics: { value: string; label: string }[] = [
  { value: "pkwt", label: "PKWT dan PHK" },
  { value: "pengupahan", label: "Pengupahan dan THR" },
  { value: "bpjs", label: "BPJS dan jaminan sosial" },
  { value: "k3", label: "Keselamatan dan kesehatan kerja" },
  { value: "hubungan_industrial", label: "Hubungan industrial" },
];

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

type StatusTone = "success" | "error" | "info";

export function AdminUpload() {
  const inputRef = useRef<HTMLInputElement>(null);
  const dragCounter = useRef(0);
  const [file, setFile] = useState<File | null>(null);
  const [topic, setTopic] = useState("pkwt");
  const [status, setStatus] = useState<string | null>(null);
  const [statusTone, setStatusTone] = useState<StatusTone | null>(null);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [uploaded, setUploaded] = useState<AdminUploadResult | null>(null);
  const [ingesting, setIngesting] = useState(false);
  const [ingestMessage, setIngestMessage] = useState<string | null>(null);

  function acceptFile(nextFile: File | undefined) {
    if (!nextFile) return;
    if (nextFile.type !== "application/pdf" && !nextFile.name.toLowerCase().endsWith(".pdf")) {
      setStatus("File harus berformat PDF.");
      setStatusTone("error");
      return;
    }
    if (nextFile.size > 50 * 1024 * 1024) {
      setStatus("Ukuran file melebihi batas 50 MB.");
      setStatusTone("error");
      return;
    }
    setFile(nextFile);
    setStatus(null);
    setStatusTone(null);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragCounter.current = 0;
    setDragging(false);
    acceptFile(event.dataTransfer.files[0]);
  }

  async function handleUpload() {
    if (!file) {
      setStatus("Pilih file PDF terlebih dahulu.");
      setStatusTone("error");
      return;
    }
    setSubmitting(true);
    setStatus("Mengunggah dan memvalidasi PDF...");
    setStatusTone("info");
    try {
      const result = await uploadAdminDocument(file, topic);
      setUploaded(result);
      setStatus("PDF berhasil diunggah dan terdaftar di knowledge base.");
      setStatusTone("success");
    } catch (error) {
      setStatus(`Upload gagal: ${(error as Error).message}`);
      setStatusTone("error");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleIngest() {
    if (!uploaded) return;
    setIngesting(true);
    setIngestMessage(null);
    try {
      const job = await createIngestionJob(uploaded.document_id);
      setIngestMessage(`Job selesai dengan status ${job.status}.`);
    } catch (error) {
      setIngestMessage(`Ingestion gagal: ${(error as Error).message}`);
    } finally {
      setIngesting(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Tambah regulasi"
        title="Upload PDF"
        description="Tambahkan dokumen resmi ke knowledge base untuk diproses oleh pipeline ingestion."
        actions={
          <Button asChild variant="outline">
            <Link href="/documents">
              <ArrowLeft /> Kembali ke dokumen
            </Link>
          </Button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <div
          className={cn(
            "flex min-h-80 flex-col items-center justify-center gap-4 rounded-xl border-2 border-dashed p-8 text-center transition-colors",
            dragging
              ? "border-forest bg-[#e7f3ec]"
              : "border-[#e8e6e1] bg-white hover:border-forest/50 hover:bg-[#f1f0ec]/30"
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
          <span
            className={cn(
              "flex size-14 items-center justify-center rounded-full transition-colors",
              dragging ? "bg-white text-forest" : "bg-teal-soft text-forest"
            )}
          >
            <Upload className="size-6" />
          </span>
          <div className="space-y-1">
            <p className="text-base font-medium">
              {dragging ? "Lepaskan file di sini" : "Tarik dan lepas file PDF di sini"}
            </p>
            <p className="text-sm text-muted-text">
              atau pilih file dari komputer — maksimum 50 MB
            </p>
          </div>
          <Button type="button" variant="outline" onClick={() => inputRef.current?.click()}>
            Pilih file
          </Button>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            onChange={(event) => acceptFile(event.target.files?.[0])}
          />
        </div>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Konfigurasi dokumen</CardTitle>
            <CardDescription>Atur topik sebelum dokumen diproses</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {file ? (
              <div className="flex items-center gap-3 rounded-lg border border-line px-3 py-2.5">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-teal-soft text-forest">
                  <FileText className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <strong className="block truncate text-sm">{file.name}</strong>
                  <small className="text-xs text-muted-text">{formatBytes(file.size)}</small>
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Hapus file"
                  onClick={() => {
                    setFile(null);
                    setStatus(null);
                    setStatusTone(null);
                  }}
                >
                  <X />
                </Button>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-line px-3 py-8 text-center">
                <FileText className="size-5 text-muted-text" />
                <p className="text-sm text-muted-text">Belum ada file dipilih.</p>
              </div>
            )}

            <div className="space-y-1.5">
              <Label>Topik utama</Label>
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
            </div>

            <ul className="space-y-2">
              <li className="flex items-center gap-2 text-sm text-muted-text">
                <CheckCircle2 className="size-4 shrink-0 text-forest" />
                Header file PDF akan divalidasi
              </li>
              <li className="flex items-center gap-2 text-sm text-muted-text">
                <CheckCircle2 className="size-4 shrink-0 text-forest" />
                Dokumen baru dibuat sebagai draft
              </li>
              <li className="flex items-center gap-2 text-sm text-muted-text">
                <CheckCircle2 className="size-4 shrink-0 text-forest" />
                Publikasi membutuhkan review admin
              </li>
            </ul>

            <Button
              className="w-full bg-javanese text-white hover:bg-forest"
              disabled={submitting}
              onClick={() => void handleUpload()}
            >
              {submitting ? <Loader2 className="animate-spin" /> : <Upload />}
              {submitting ? "Mengunggah..." : "Mulai upload"}
            </Button>

            {status ? (
              <div
                role="status"
                className={cn(
                  "flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm",
                  statusTone === "error" && "border-red/25 bg-red-soft text-red",
                  statusTone === "success" && "border-forest/25 bg-teal-soft/60 text-forest",
                  statusTone === "info" && "border-line bg-surface-soft text-muted-text"
                )}
              >
                {statusTone === "error" ? (
                  <Badge className="border border-red/25 bg-red-soft text-red">Gagal</Badge>
                ) : statusTone === "success" ? (
                  <Badge className="border border-forest/20 bg-teal-soft/70 text-forest">
                    Berhasil
                  </Badge>
                ) : null}
                <span className="flex-1">{status}</span>
              </div>
            ) : null}

            {uploaded ? (
              <div className="space-y-3 rounded-lg border border-forest/25 bg-teal-soft/30 p-3">
                <div className="flex items-center gap-2 text-sm">
                  <CheckCircle2 className="size-4 shrink-0 text-forest" />
                  <span className="min-w-0">
                    <strong className="block truncate">{uploaded.file_name}</strong>
                    <small className="block font-mono text-xs text-muted-text">
                      {uploaded.document_id}
                    </small>
                  </span>
                </div>
                <Button
                  className="w-full bg-javanese text-white hover:bg-forest"
                  disabled={ingesting}
                  onClick={() => void handleIngest()}
                >
                  {ingesting ? <Loader2 className="animate-spin" /> : <PlayCircle />}
                  {ingesting ? "Memproses..." : "Mulai ingestion"}
                </Button>
                {ingestMessage ? (
                  <p
                    className={cn(
                      "text-xs",
                      ingestMessage.startsWith("Job selesai") ? "text-forest" : "text-[#a94442]"
                    )}
                  >
                    {ingestMessage}
                  </p>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
