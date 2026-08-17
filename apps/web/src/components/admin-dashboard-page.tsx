"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

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
import { clearStoredSession, fetchAdminStats } from "@/lib/api";
import type { AdminStats } from "@/lib/types";

const ingestionStatusLabel: Record<string, string> = {
  completed: "Selesai",
  needs_review: "Perlu review",
  failed: "Gagal",
  running: "Berjalan",
  queued: "Antre",
};

const ingestionBadgeClass: Record<string, string> = {
  completed: "bg-[#e7f3ec] text-forest",
  needs_review: "bg-[#faf3e0] text-[#b8860b]",
  failed: "bg-[#fbeaea] text-[#a94442]",
  running: "bg-[#eaf2ee] text-javanese",
  queued: "bg-[#f1f0ec] text-slate-600",
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

const kpiCards = [
  { key: "documents", label: "Total dokumen", icon: FileIcon, tint: "bg-[#eaf2ee] text-javanese" },
  { key: "published", label: "Dokumen aktif", icon: CheckIcon, tint: "bg-[#e7f3ec] text-forest" },
  { key: "users", label: "Pengguna terdaftar", icon: UserIcon, tint: "bg-[#faf3e0] text-[#b8860b]" },
  { key: "messages", label: "Total pesan", icon: ChatIcon, tint: "bg-[#fbeaea] text-[#a94442]" },
] as const;

export function AdminDashboardPage() {
  const router = useRouter();
  const routerRef = useRef(router);
  routerRef.current = router;
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
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        const message = (err as Error).message || "Gagal memuat data dashboard.";
        if (message === "Invalid or expired token." || message === "Missing bearer token.") {
          clearStoredSession();
          routerRef.current.push("/login-admin");
          return;
        }
        setError(message);
        setLoading(false);
      });
    return () => controller.abort();
  }, []);

  if (loading) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3 text-muted-text">
        <RefreshIcon className="icon size-6 animate-spin" />
        <span className="text-sm">Memuat data...</span>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3 text-muted-text">
        <AlertIcon className="icon size-6 text-[#a94442]" />
        <span className="text-sm">{error ?? "Data tidak tersedia."}</span>
        <button
          type="button"
          className="mt-1 h-10 rounded-xl border border-[#e8e6e1] bg-white px-5 text-sm font-semibold text-forest transition hover:border-emas hover:text-emas"
          onClick={() => window.location.reload()}
        >
          Muat ulang
        </button>
      </div>
    );
  }

  const docPercent =
    stats.documents.total > 0
      ? Math.round((stats.documents.published / stats.documents.total) * 100)
      : 0;

  const kpiValues: Record<string, number> = {
    documents: stats.documents.total,
    published: stats.documents.published,
    users: stats.users,
    messages: stats.messages,
  };
  const kpiFooters: Record<string, string> = {
    documents: `${docPercent}% telah diterbitkan`,
    published: `${stats.documents.needs_review} menunggu review`,
    users: `${stats.conversations} percakapan aktif`,
    messages: `${stats.feedback.total} feedback masuk`,
  };

  const doneDocs =
    stats.documents.total - stats.documents.needs_review - stats.documents.failed;

  const progress = [
    {
      label: "Selesai",
      value: doneDocs,
      fill: "bg-forest",
      pct:
        stats.documents.total > 0 ? (doneDocs / stats.documents.total) * 100 : 0,
    },
    {
      label: "Perlu review",
      value: stats.documents.needs_review,
      fill: "bg-[#c9a227]",
      pct:
        stats.documents.total > 0
          ? (stats.documents.needs_review / stats.documents.total) * 100
          : 0,
    },
    {
      label: "Gagal",
      value: stats.documents.failed,
      fill: "bg-[#a94442]",
      pct:
        stats.documents.total > 0
          ? (stats.documents.failed / stats.documents.total) * 100
          : 0,
    },
  ];

  const satisfaction =
    stats.feedback.total > 0
      ? Math.round((stats.feedback.helpful / stats.feedback.total) * 100)
      : 0;

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold text-javanese">Dashboard</h1>
          <p className="mt-1 text-sm text-muted-text">
            Ringkasan knowledge base, percakapan, dan feedback pengguna
          </p>
        </div>
        <Link
          href="/admin/upload"
          className="inline-flex h-11 items-center gap-2 rounded-xl bg-javanese px-5 text-sm font-semibold text-white transition hover:bg-forest"
        >
          <UploadIcon className="icon size-4" /> Upload dokumen
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
        {kpiCards.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.key}
              className="relative flex flex-col gap-4 overflow-hidden rounded-xl border border-[#e8e6e1] bg-white pb-4 pl-7 pr-5 pt-5 transition hover:-translate-y-0.5 hover:border-[#d5d2c9] hover:shadow-[0_10px_30px_rgba(27,67,50,0.1)]"
            >
              <span
                aria-hidden="true"
                className="absolute inset-y-0 left-0 w-[3px] bg-[repeating-linear-gradient(180deg,#c9a227_0px,#c9a227_4px,transparent_4px,transparent_8px)]"
              />
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-mono text-3xl font-bold leading-none tracking-tight text-javanese">
                    {kpiValues[card.key]}
                  </p>
                  <p className="mt-2 text-xs font-medium uppercase tracking-[0.05em] text-slate-500">
                    {card.label}
                  </p>
                </div>
                <span
                  className={`flex size-10 shrink-0 items-center justify-center rounded-[10px] ${card.tint}`}
                >
                  <Icon className="icon size-[18px]" />
                </span>
              </div>
              <div className="mt-auto flex items-center gap-2 border-t border-[#efede7] pt-3">
                <span className="size-1.5 shrink-0 rounded-full bg-emas" />
                <span className="text-xs text-slate-400">{kpiFooters[card.key]}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-[#e8e6e1] bg-white">
          <div className="border-b border-[#e8e6e1] px-6 py-4">
            <h2 className="text-sm font-semibold text-tinta">Proses dokumen</h2>
          </div>
          <div className="space-y-5 px-6 py-5">
            {progress.map((item) => (
              <div key={item.label}>
                <div className="mb-1.5 flex items-center justify-between text-sm">
                  <span className="text-muted-text">{item.label}</span>
                  <span className="font-mono font-medium text-tinta">{item.value}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-[#f1f0ec]">
                  <div
                    className={`h-full rounded-full ${item.fill}`}
                    style={{ width: `${item.pct}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-[#e8e6e1] bg-white">
          <div className="border-b border-[#e8e6e1] px-6 py-4">
            <h2 className="text-sm font-semibold text-tinta">Feedback pengguna</h2>
          </div>
          <div className="grid grid-cols-3 gap-4 px-6 py-5">
            <div className="rounded-xl bg-[#e7f3ec] p-4 text-center">
              <CheckIcon className="icon mx-auto size-5 text-forest" />
              <strong className="mt-2 block font-mono text-2xl text-javanese">
                {stats.feedback.helpful}
              </strong>
              <span className="text-xs text-muted-text">Membantu</span>
            </div>
            <div className="rounded-xl bg-[#fbeaea] p-4 text-center">
              <AlertIcon className="icon mx-auto size-5 text-[#a94442]" />
              <strong className="mt-2 block font-mono text-2xl text-javanese">
                {stats.feedback.not_helpful}
              </strong>
              <span className="text-xs text-muted-text">Tidak membantu</span>
            </div>
            <div className="rounded-xl bg-[#eaf2ee] p-4 text-center">
              <ChatIcon className="icon mx-auto size-5 text-javanese" />
              <strong className="mt-2 block font-mono text-2xl text-javanese">
                {satisfaction}%
              </strong>
              <span className="text-xs text-muted-text">Tingkat kepuasan</span>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 rounded-xl border border-[#e8e6e1] bg-white">
        <div className="flex items-center justify-between border-b border-[#e8e6e1] px-6 py-4">
          <h2 className="text-sm font-semibold text-tinta">Ingestion terbaru</h2>
          <Link
            href="/admin/ingestion"
            className="text-xs font-semibold text-forest transition hover:text-emas"
          >
            Lihat semua
          </Link>
        </div>
        {stats.ingestion_jobs.recent.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-12 text-muted-text">
            <DatabaseIcon className="icon size-6" />
            <p className="text-sm">Belum ada job ingestion</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-[#f1f0ec] text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-6 py-3 font-semibold">Dokumen</th>
                  <th className="px-6 py-3 font-semibold">Status</th>
                  <th className="px-6 py-3 font-semibold">Waktu</th>
                </tr>
              </thead>
              <tbody>
                {stats.ingestion_jobs.recent.map((job) => (
                  <tr key={job.job_id} className="border-b border-[#f7f6f2] last:border-0">
                    <td className="px-6 py-3.5 font-medium text-tinta">{job.document_id}</td>
                    <td className="px-6 py-3.5">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${ingestionBadgeClass[job.status] ?? "bg-[#f1f0ec] text-slate-600"}`}
                      >
                        {ingestionStatusLabel[job.status] ?? job.status}
                      </span>
                    </td>
                    <td className="px-6 py-3.5 text-xs text-muted-text">
                      {formatDate(job.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="mt-6 rounded-xl border border-[#e8e6e1] bg-white">
        <div className="border-b border-[#e8e6e1] px-6 py-4">
          <h2 className="text-sm font-semibold text-tinta">Aksi cepat</h2>
        </div>
        <div className="grid grid-cols-2 gap-3 px-6 py-5 sm:grid-cols-3 lg:grid-cols-5">
          <Link
            href="/admin/upload"
            className="flex flex-col items-center gap-2 rounded-xl border border-[#e8e6e1] py-5 text-sm font-medium text-tinta transition hover:border-emas hover:text-emas"
          >
            <UploadIcon className="icon size-5" />
            <span>Upload PDF</span>
          </Link>
          <Link
            href="/documents"
            className="flex flex-col items-center gap-2 rounded-xl border border-[#e8e6e1] py-5 text-sm font-medium text-tinta transition hover:border-emas hover:text-emas"
          >
            <FileIcon className="icon size-5" />
            <span>Kelola dokumen</span>
          </Link>
          <Link
            href="/admin/ingestion"
            className="flex flex-col items-center gap-2 rounded-xl border border-[#e8e6e1] py-5 text-sm font-medium text-tinta transition hover:border-emas hover:text-emas"
          >
            <DatabaseIcon className="icon size-5" />
            <span>Ingestion</span>
          </Link>
          <Link
            href="/admin/feedback"
            className="flex flex-col items-center gap-2 rounded-xl border border-[#e8e6e1] py-5 text-sm font-medium text-tinta transition hover:border-emas hover:text-emas"
          >
            <ChatIcon className="icon size-5" />
            <span>Feedback</span>
          </Link>
          <Link
            href="/admin/retrieval"
            className="flex flex-col items-center gap-2 rounded-xl border border-[#e8e6e1] py-5 text-sm font-medium text-tinta transition hover:border-emas hover:text-emas"
          >
            <RefreshIcon className="icon size-5" />
            <span>Retrieval lab</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
