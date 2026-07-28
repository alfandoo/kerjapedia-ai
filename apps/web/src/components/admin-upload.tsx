"use client";

import Link from "next/link";
import { type DragEvent, useRef, useState } from "react";

import { CheckIcon, FileIcon, UploadIcon } from "./icons";
import { uploadAdminDocument } from "@/lib/api";

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AdminUpload() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [topic, setTopic] = useState("pkwt");
  const [status, setStatus] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  function acceptFile(nextFile: File | undefined) {
    if (!nextFile) return;
    if (nextFile.type !== "application/pdf" && !nextFile.name.toLowerCase().endsWith(".pdf")) {
      setStatus("File harus berformat PDF.");
      return;
    }
    if (nextFile.size > 50 * 1024 * 1024) {
      setStatus("Ukuran file melebihi batas 50 MB.");
      return;
    }
    setFile(nextFile);
    setStatus(null);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    acceptFile(event.dataTransfer.files[0]);
  }

  async function handleUpload() {
    if (!file) {
      setStatus("Pilih file PDF terlebih dahulu.");
      return;
    }
    setSubmitting(true);
    setStatus("Mengunggah dan memvalidasi PDF...");
    try {
      await uploadAdminDocument(file, topic);
      setStatus("PDF berhasil diunggah dan siap masuk antrean ingestion.");
    } catch (error) {
      setStatus(`Upload gagal: ${(error as Error).message}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="admin-standard-page">
      <div className="admin-page-heading">
        <div>
          <h1>Upload PDF</h1>
          <p>Tambahkan dokumen resmi ke knowledge base untuk diproses oleh pipeline ingestion.</p>
        </div>
        <Link href="/documents" className="admin-secondary-button">
          Kembali ke dokumen
        </Link>
      </div>

      <div className="upload-workspace">
        <div
          className={dragging ? "upload-dropzone dragging" : "upload-dropzone"}
          onDragEnter={() => setDragging(true)}
          onDragLeave={() => setDragging(false)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
        >
          <UploadIcon className="icon upload-hero-icon" />
          <h2>Tarik dan lepas file PDF di sini</h2>
          <p>atau pilih file dari komputer, maksimum 50 MB</p>
          <button
            type="button"
            className="admin-secondary-button"
            onClick={() => inputRef.current?.click()}
          >
            Pilih file
          </button>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            onChange={(event) => acceptFile(event.target.files?.[0])}
          />
        </div>

        <aside className="upload-config-panel">
          <h2>Konfigurasi dokumen</h2>
          {file ? (
            <div className="selected-file-row">
              <FileIcon className="icon" />
              <span>
                <strong>{file.name}</strong>
                <small>{formatBytes(file.size)}</small>
              </span>
              <button
                type="button"
                className="icon-button"
                aria-label="Hapus file"
                onClick={() => setFile(null)}
              >
                ×
              </button>
            </div>
          ) : (
            <p className="admin-empty-copy">Belum ada file dipilih.</p>
          )}
          <label>
            Topik utama
            <select value={topic} onChange={(event) => setTopic(event.target.value)}>
              <option value="pkwt">PKWT dan PHK</option>
              <option value="pengupahan">Pengupahan dan THR</option>
              <option value="bpjs">BPJS dan jaminan sosial</option>
              <option value="k3">Keselamatan dan kesehatan kerja</option>
              <option value="hubungan_industrial">Hubungan industrial</option>
            </select>
          </label>
          <div className="upload-checklist">
            <p>
              <CheckIcon className="icon" /> Header file PDF akan divalidasi
            </p>
            <p>
              <CheckIcon className="icon" /> Dokumen baru dibuat sebagai draft
            </p>
            <p>
              <CheckIcon className="icon" /> Publikasi membutuhkan review admin
            </p>
          </div>
          <button
            type="button"
            className="admin-primary-button"
            disabled={submitting}
            onClick={() => void handleUpload()}
          >
            <UploadIcon className="icon" /> {submitting ? "Mengunggah..." : "Mulai upload"}
          </button>
          {status ? (
            <p className="admin-inline-message" role="status">
              {status}
            </p>
          ) : null}
        </aside>
      </div>
    </section>
  );
}
