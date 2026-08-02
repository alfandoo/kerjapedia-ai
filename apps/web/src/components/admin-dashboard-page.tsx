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
import { fallbackAdminStats } from "@/lib/sample-data";
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

  useEffect(() => {
    const controller = new AbortController();
    fetchAdminStats(controller.signal)
      .then((data) => {
        setStats(data);
        setLoading(false);
      })
      .catch(() => {
        setStats(fallbackAdminStats);
        setLoading(false);
      });
    return () => controller.abort();
  }, []);

  if (loading) {
    return (
      <div className="admin-loading">
        <RefreshIcon className="icon spin" />
        <span>Memuat data...</span>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="admin-loading">
        <AlertIcon className="icon" />
        <span>Data tidak tersedia.</span>
        <button type="button" className="admin-btn" onClick={() => window.location.reload()}>
          Muat ulang
        </button>
      </div>
    );
  }

  const docPercent =
    stats.documents.total > 0
      ? Math.round((stats.documents.published / stats.documents.total) * 100)
      : 0;

  return (
    <div className="admin-dashboard">
      <div className="admin-page-header">
        <div>
          <h1>Dashboard</h1>
          <p>Ringkasan knowledge base, percakapan, dan feedback pengguna</p>
        </div>
        <Link href="/admin/upload" className="admin-btn admin-btn-primary">
          <UploadIcon className="icon" /> Upload dokumen
        </Link>
      </div>

      <div className="admin-stat-cards">
        <div className="admin-stat-card">
          <div className="admin-stat-card-icon blue">
            <FileIcon className="icon" />
          </div>
          <div className="admin-stat-card-body">
            <h3>{stats.documents.total}</h3>
            <p>Total dokumen</p>
          </div>
          <div className="admin-stat-card-footer">
            <span>{docPercent}% telah diterbitkan</span>
          </div>
        </div>

        <div className="admin-stat-card">
          <div className="admin-stat-card-icon green">
            <CheckIcon className="icon" />
          </div>
          <div className="admin-stat-card-body">
            <h3>{stats.documents.published}</h3>
            <p>Dokumen aktif</p>
          </div>
          <div className="admin-stat-card-footer">
            <span>{stats.documents.needs_review} menunggu review</span>
          </div>
        </div>

        <div className="admin-stat-card">
          <div className="admin-stat-card-icon yellow">
            <UserIcon className="icon" />
          </div>
          <div className="admin-stat-card-body">
            <h3>{stats.users}</h3>
            <p>Pengguna terdaftar</p>
          </div>
          <div className="admin-stat-card-footer">
            <span>{stats.conversations} percakapan aktif</span>
          </div>
        </div>

        <div className="admin-stat-card">
          <div className="admin-stat-card-icon red">
            <ChatIcon className="icon" />
          </div>
          <div className="admin-stat-card-body">
            <h3>{stats.messages}</h3>
            <p>Total pesan</p>
          </div>
          <div className="admin-stat-card-footer">
            <span>{stats.feedback.total} feedback masuk</span>
          </div>
        </div>
      </div>

      <div className="admin-grid-2">
        <div className="admin-card">
          <div className="admin-card-header">
            <h2>Proses dokumen</h2>
          </div>
          <div className="admin-card-body">
            <div className="admin-progress-list">
              <div className="admin-progress-item">
                <div className="admin-progress-label">
                  <span className="admin-progress-name">Selesai</span>
                  <span className="admin-progress-value">
                    {stats.documents.total - stats.documents.needs_review - stats.documents.failed}
                  </span>
                </div>
                <div className="admin-progress-bar">
                  <div
                    className="admin-progress-fill green"
                    style={{
                      width: `${
                        stats.documents.total > 0
                          ? ((stats.documents.total -
                              stats.documents.needs_review -
                              stats.documents.failed) /
                              stats.documents.total) *
                            100
                          : 0
                      }%`,
                    }}
                  />
                </div>
              </div>

              <div className="admin-progress-item">
                <div className="admin-progress-label">
                  <span className="admin-progress-name">Perlu review</span>
                  <span className="admin-progress-value">{stats.documents.needs_review}</span>
                </div>
                <div className="admin-progress-bar">
                  <div
                    className="admin-progress-fill yellow"
                    style={{
                      width: `${
                        stats.documents.total > 0
                          ? (stats.documents.needs_review / stats.documents.total) * 100
                          : 0
                      }%`,
                    }}
                  />
                </div>
              </div>

              <div className="admin-progress-item">
                <div className="admin-progress-label">
                  <span className="admin-progress-name">Gagal</span>
                  <span className="admin-progress-value">{stats.documents.failed}</span>
                </div>
                <div className="admin-progress-bar">
                  <div
                    className="admin-progress-fill red"
                    style={{
                      width: `${
                        stats.documents.total > 0
                          ? (stats.documents.failed / stats.documents.total) * 100
                          : 0
                      }%`,
                    }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="admin-card">
          <div className="admin-card-header">
            <h2>Feedback pengguna</h2>
          </div>
          <div className="admin-card-body">
            <div className="admin-feedback-summary">
              <div className="admin-feedback-box green">
                <CheckIcon className="icon" />
                <div>
                  <strong>{stats.feedback.helpful}</strong>
                  <span>Membantu</span>
                </div>
              </div>
              <div className="admin-feedback-box red">
                <AlertIcon className="icon" />
                <div>
                  <strong>{stats.feedback.not_helpful}</strong>
                  <span>Tidak membantu</span>
                </div>
              </div>
              <div className="admin-feedback-box blue">
                <ChatIcon className="icon" />
                <div>
                  <strong>
                    {stats.feedback.total > 0
                      ? Math.round((stats.feedback.helpful / stats.feedback.total) * 100)
                      : 0}
                    %
                  </strong>
                  <span>Tingkat kepuasan</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="admin-card">
        <div className="admin-card-header">
          <h2>Ingestion terbaru</h2>
          <Link href="/admin/ingestion" className="admin-btn admin-btn-sm">
            Lihat semua
          </Link>
        </div>
        <div className="admin-card-body no-padding">
          {stats.ingestion_jobs.recent.length === 0 ? (
            <div className="admin-empty">
              <DatabaseIcon className="icon" />
              <p>Belum ada job ingestion</p>
            </div>
          ) : (
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Dokumen</th>
                  <th>Status</th>
                  <th>Waktu</th>
                </tr>
              </thead>
              <tbody>
                {stats.ingestion_jobs.recent.map((job) => (
                  <tr key={job.job_id}>
                    <td className="font-medium">{job.document_id}</td>
                    <td>
                      <span
                        className={`admin-badge ${
                          job.status === "completed"
                            ? "green"
                            : job.status === "failed"
                              ? "red"
                              : job.status === "needs_review"
                                ? "yellow"
                                : ""
                        }`}
                      >
                        {ingestionStatusLabel[job.status] ?? job.status}
                      </span>
                    </td>
                    <td className="text-muted">{formatDate(job.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="admin-card">
        <div className="admin-card-header">
          <h2>Aksi cepat</h2>
        </div>
        <div className="admin-card-body">
          <div className="admin-quick-actions">
            <Link href="/admin/upload" className="admin-quick-action">
              <UploadIcon className="icon" />
              <span>Upload PDF</span>
            </Link>
            <Link href="/documents" className="admin-quick-action">
              <FileIcon className="icon" />
              <span>Kelola dokumen</span>
            </Link>
            <Link href="/admin/ingestion" className="admin-quick-action">
              <DatabaseIcon className="icon" />
              <span>Ingestion</span>
            </Link>
            <Link href="/admin/feedback" className="admin-quick-action">
              <ChatIcon className="icon" />
              <span>Feedback</span>
            </Link>
            <Link href="/admin/retrieval" className="admin-quick-action">
              <RefreshIcon className="icon" />
              <span>Retrieval lab</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
