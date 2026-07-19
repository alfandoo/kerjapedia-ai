"use client";

import { useEffect, useMemo, useState } from "react";

import { AlertIcon, CheckIcon, RefreshIcon } from "./icons";
import { createIngestionJob, fetchIngestionJobs } from "@/lib/api";
import { fallbackIngestionJobs } from "@/lib/sample-data";
import type { IngestionJob } from "@/lib/types";

const jobLabels: Record<IngestionJob["status"], string> = {
  completed: "Selesai",
  needs_review: "Perlu review",
  failed: "Gagal",
  running: "Berjalan",
  queued: "Antre",
};

export function AdminIngestion() {
  const [jobs, setJobs] = useState(fallbackIngestionJobs);
  const [filter, setFilter] = useState("all");
  const [selectedJobId, setSelectedJobId] = useState(fallbackIngestionJobs[1].job_id);
  const [message, setMessage] = useState("Memuat job ingestion...");

  useEffect(() => {
    const controller = new AbortController();
    fetchIngestionJobs(controller.signal)
      .then((items) => {
        if (items.length) {
          setJobs(items);
          setSelectedJobId(items[0].job_id);
        }
        setMessage("Data tersinkron dengan API.");
      })
      .catch(() => setMessage("Menampilkan log contoh karena API belum tersedia."));
    return () => controller.abort();
  }, []);

  const filtered = useMemo(
    () => jobs.filter((job) => filter === "all" || job.status === filter),
    [filter, jobs]
  );
  const selectedJob = jobs.find((job) => job.job_id === selectedJobId) ?? null;

  async function rerun(documentId: string) {
    setMessage(`Menjalankan ulang ingestion ${documentId}...`);
    try {
      const next = await createIngestionJob(documentId);
      setJobs((current) => [next, ...current]);
      setSelectedJobId(next.job_id);
      setMessage(`Ingestion selesai dengan status ${jobLabels[next.status]}.`);
    } catch {
      setMessage("API belum tersedia; re-ingest belum dapat dijalankan.");
    }
  }

  return (
    <section className="admin-standard-page">
      <div className="admin-page-heading">
        <div>
          <h1>Ingestion</h1>
          <p>{message}</p>
        </div>
        <select
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          aria-label="Filter job ingestion"
        >
          <option value="all">Semua status</option>
          <option value="completed">Selesai</option>
          <option value="needs_review">Perlu review</option>
          <option value="failed">Gagal</option>
        </select>
      </div>

      <div className="ingestion-workspace">
        <div className="ingestion-list">
          <div className="ingestion-row table-header">
            <span>Dokumen / Job</span>
            <span>Status</span>
            <span>Diperbarui</span>
            <span>Aksi</span>
          </div>
          {filtered.map((job) => (
            <button
              type="button"
              className={job.job_id === selectedJobId ? "ingestion-row selected" : "ingestion-row"}
              key={job.job_id}
              onClick={() => setSelectedJobId(job.job_id)}
            >
              <span>
                <strong>{job.document_id}</strong>
                <small>{job.job_id}</small>
              </span>
              <span>
                <i className={`status-dot ${job.status}`} />
                {jobLabels[job.status]}
              </span>
              <span>{new Date(job.updated_at).toLocaleString("id-ID")}</span>
              <span
                className="admin-text-link"
                role="button"
                tabIndex={0}
                onClick={(event) => {
                  event.stopPropagation();
                  void rerun(job.document_id);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.stopPropagation();
                    void rerun(job.document_id);
                  }
                }}
              >
                Re-ingest
              </span>
            </button>
          ))}
        </div>

        <aside className="ingestion-detail">
          <h2>Log parsing</h2>
          {selectedJob ? (
            <>
              <dl className="admin-definition-list">
                <div>
                  <dt>Job ID</dt>
                  <dd>{selectedJob.job_id}</dd>
                </div>
                <div>
                  <dt>Dokumen</dt>
                  <dd>{selectedJob.document_id}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{jobLabels[selectedJob.status]}</dd>
                </div>
                <div>
                  <dt>Chunk</dt>
                  <dd>{selectedJob.result?.chunk_count ?? "-"}</dd>
                </div>
              </dl>
              <div className={selectedJob.error ? "parsing-log warning" : "parsing-log success"}>
                {selectedJob.error ? (
                  <AlertIcon className="icon" />
                ) : (
                  <CheckIcon className="icon" />
                )}
                <span>
                  <strong>
                    {selectedJob.error ? "Perlu review manual" : "Tidak ada error parsing"}
                  </strong>
                  <small>{selectedJob.error ?? "Semua tahapan pipeline selesai."}</small>
                </span>
              </div>
              <button
                type="button"
                className="admin-secondary-button"
                onClick={() => void rerun(selectedJob.document_id)}
              >
                <RefreshIcon className="icon" /> Jalankan ulang
              </button>
            </>
          ) : (
            <p className="admin-empty-copy">Pilih job untuk melihat log.</p>
          )}
        </aside>
      </div>
    </section>
  );
}
