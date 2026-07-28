"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  AlertIcon,
  CheckIcon,
  ChatIcon,
  DatabaseIcon,
  FileIcon,
  RefreshIcon,
  UploadIcon,
  UserIcon,
} from "./icons";
import { fetchAdminStats } from "@/lib/api";
import type { AdminStats } from "@/lib/types";

const ingestionStatusLabel: Record<string, string> = {
  completed: "Selesai",
  needs_review: "Perlu review",
  failed: "Gagal",
  running: "Berjalan",
  queued: "Antre",
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function AdminDashboardPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchAdminStats(controller.signal)
      .then((data) => {
        setStats(data);
        setLoading(false);
      })
      .catch(() => {
        setError("Gagal memuat data dashboard.");
        setLoading(false);
      });
    return () => controller.abort();
  }, []);

  if (loading) {
    return (
      <div className="admin-page-heading">
        <h1>Dashboard</h1>
        <p>Memuat data dashboard...</p>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="admin-page-heading">
        <h1>Dashboard</h1>
        <p className="admin-inline-message">{error ?? "Data tidak tersedia."}</p>
      </div>
    );
  }

  const docPercent = stats.documents.total > 0
    ? Math.round((stats.documents.published / stats.documents.total) * 100)
    : 0;

  return (
    <div className="admin-dashboard">
      <div className="admin-page-heading">
        <div>
          <h1>Dashboard</h1>
          <p>Ringkasan knowledge base, percakapan, dan feedback</p>
        </div>
        <Link href="/admin/upload" className="admin-primary-button">
          <UploadIcon className="icon" /> Upload dokumen
        </Link>
      </div>

      <div className="admin-summary-strip">
        <div>
          <FileIcon className="icon" />
          <strong>{stats.documents.total}</strong>
          <span>dokumen</span>
          <small>Total regulasi</small>
        </div>
        <div>
          <CheckIcon className="icon" />
          <strong>{stats.documents.published}</strong>
          <span>terbit</span>
          <small>{docPercent}% dari total</small>
        </div>
        <div className={stats.documents.needs_review > 0 ? "warning" : ""}>
          <AlertIcon className="icon" />
          <strong>{stats.documents.needs_review}</strong>
          <span>perlu review</span>
          <small>Dokumen perlu ditinjau</small>
        </div>
        <div className={stats.documents.failed > 0 ? "danger" : ""}>
          <AlertIcon className="icon" />
          <strong>{stats.documents.failed}</strong>
          <span>gagal</span>
          <small>Ingestion gagal</small>
        </div>
      </div>

      <div className="dashboard-grid">
        <section className="dashboard-card">
          <h2>Ringkasan Aktivitas</h2>
          <div className="dashboard-metrics">
            <div className="metric-item">
              <UserIcon className="icon" />
              <div>
                <strong>{stats.users}</strong>
                <span>Pengguna terdaftar</span>
              </div>
            </div>
            <div className="metric-item">
              <ChatIcon className="icon" />
              <div>
                <strong>{stats.conversations}</strong>
                <span>Percakapan</span>
              </div>
            </div>
            <div className="metric-item">
              <ChatIcon className="icon" />
              <div>
                <strong>{stats.messages}</strong>
                <span>Pesan</span>
              </div>
            </div>
            <div className="metric-item">
              <DatabaseIcon className="icon" />
              <div>
                <strong>{stats.ingestion_jobs.total}</strong>
                <span>Job ingestion</span>
              </div>
            </div>
          </div>
        </section>

        <section className="dashboard-card">
          <h2>Feedback</h2>
          <div className="dashboard-metrics">
            <div className="metric-item">
              <CheckIcon className="icon" />
              <div>
                <strong>{stats.feedback.helpful}</strong>
                <span>Membantu</span>
              </div>
            </div>
            <div className="metric-item">
              <AlertIcon className="icon" />
              <div>
                <strong>{stats.feedback.not_helpful}</strong>
                <span>Tidak membantu</span>
              </div>
            </div>
            <div className="metric-item">
              <ChatIcon className="icon" />
              <div>
                <strong>{stats.feedback.total}</strong>
                <span>Total feedback</span>
              </div>
            </div>
            <div className="metric-item">
              <span />
              <div>
                <strong>
                  {stats.feedback.total > 0
                    ? Math.round((stats.feedback.helpful / stats.feedback.total) * 100)
                    : 0}%
                </strong>
                <span>Kepuasan</span>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div className="dashboard-grid">
        <section className="dashboard-card">
          <h2>Status Dokumen</h2>
          <div className="dashboard-bar-chart">
            <div className="bar-item">
              <span className="bar-label">Selesai</span>
              <div className="bar-track">
                <div
                  className="bar-fill success"
                  style={{
                    width: `${stats.documents.total > 0
                      ? ((stats.documents.total - stats.documents.needs_review - stats.documents.failed) / stats.documents.total) * 100
                      : 0}%`,
                  }}
                />
              </div>
              <span className="bar-value">
                {stats.documents.total - stats.documents.needs_review - stats.documents.failed}
              </span>
            </div>
            <div className="bar-item">
              <span className="bar-label">Perlu review</span>
              <div className="bar-track">
                <div
                  className="bar-fill warning"
                  style={{
                    width: `${stats.documents.total > 0
                      ? (stats.documents.needs_review / stats.documents.total) * 100
                      : 0}%`,
                  }}
                />
              </div>
              <span className="bar-value">{stats.documents.needs_review}</span>
            </div>
            <div className="bar-item">
              <span className="bar-label">Gagal</span>
              <div className="bar-track">
                <div
                  className="bar-fill danger"
                  style={{
                    width: `${stats.documents.total > 0
                      ? (stats.documents.failed / stats.documents.total) * 100
                      : 0}%`,
                  }}
                />
              </div>
              <span className="bar-value">{stats.documents.failed}</span>
            </div>
          </div>
        </section>

        <section className="dashboard-card">
          <div className="dashboard-card-header">
            <h2>Ingestion Terbaru</h2>
            <Link href="/admin/ingestion" className="dashboard-card-link">
              Lihat semua
            </Link>
          </div>
          {stats.ingestion_jobs.recent.length === 0 ? (
            <p className="admin-empty-copy">Belum ada job ingestion.</p>
          ) : (
            <div className="dashboard-list">
              {stats.ingestion_jobs.recent.map((job) => (
                <div className="dashboard-list-item" key={job.job_id}>
                  <div className="dashboard-list-item-main">
                    <strong>{job.document_id}</strong>
                    <span className="status-badge">{ingestionStatusLabel[job.status] ?? job.status}</span>
                  </div>
                  <small>{formatDate(job.created_at)}</small>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="dashboard-card dashboard-quick-actions">
        <h2>Aksi Cepat</h2>
        <div className="quick-action-grid">
          <Link href="/admin/upload" className="quick-action-item">
            <UploadIcon className="icon" />
            <span>Upload PDF</span>
          </Link>
          <Link href="/admin" className="quick-action-item">
            <FileIcon className="icon" />
            <span>Kelola Dokumen</span>
          </Link>
          <Link href="/admin/ingestion" className="quick-action-item">
            <DatabaseIcon className="icon" />
            <span>Ingestion</span>
          </Link>
          <Link href="/admin/feedback" className="quick-action-item">
            <ChatIcon className="icon" />
            <span>Feedback</span>
          </Link>
          <Link href="/admin/retrieval" className="quick-action-item">
            <RefreshIcon className="icon" />
            <span>Retrieval Playground</span>
          </Link>
        </div>
      </section>
    </div>
  );
}
