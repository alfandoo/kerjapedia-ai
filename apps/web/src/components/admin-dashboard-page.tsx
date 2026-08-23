"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { EmptyState, PageHeader, StatusBadge } from "./admin/primitives";
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
import { cn } from "@/lib/utils";

const ingestionTone: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
  completed: "success",
  needs_review: "warning",
  failed: "danger",
  running: "info",
  queued: "neutral",
};

const ingestionLabel: Record<string, string> = {
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
  const router = useRouter();
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
          router.push("/login-admin");
          return;
        }
        setError(message);
        setLoading(false);
      });
    return () => controller.abort();
  }, [router]);

  if (loading) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3 text-muted-text">
        <RefreshIcon className="size-6 animate-spin motion-reduce:animate-none" />
        <span className="text-sm">Memuat data...</span>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="w-full max-w-sm rounded-xl border border-line bg-white p-2 shadow-[0_1px_2px_rgba(26,26,46,0.04)]">
          <EmptyState
            icon={AlertIcon}
            title="Data dashboard tidak dapat dimuat"
            hint={error ?? "Coba muat ulang halaman."}
            action={
              <button
                type="button"
                className="h-10 rounded-xl border border-line bg-white px-5 text-sm font-semibold text-forest transition hover:border-emas hover:text-emas"
                onClick={() => window.location.reload()}
              >
                Muat ulang
              </button>
            }
          />
        </div>
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
  const reviewPending = stats.documents.needs_review;
  const failedDocs = stats.documents.failed;
  const kpiFooters: { text: string; dot: string }[] = [
    { text: `${docPercent}% telah diterbitkan`, dot: "bg-emas" },
    {
      text: reviewPending > 0 ? `${reviewPending} menunggu review` : "Semua dokumen ditinjau",
      dot: reviewPending > 0 ? "bg-amber" : "bg-forest",
    },
    { text: `${stats.conversations} percakapan aktif`, dot: "bg-javanese/50" },
    { text: `${stats.feedback.total} feedback masuk`, dot: "bg-teal" },
  ];
  const kpiCards = [
    {
      key: "documents",
      label: "Total dokumen",
      icon: FileIcon,
      tint: "bg-surface-soft text-javanese",
    },
    {
      key: "published",
      label: "Dokumen aktif",
      icon: CheckIcon,
      tint: "bg-teal-soft/70 text-forest",
    },
    {
      key: "users",
      label: "Pengguna terdaftar",
      icon: UserIcon,
      tint: "bg-amber-soft/70 text-amber",
    },
    { key: "messages", label: "Total pesan", icon: ChatIcon, tint: "bg-blue-soft text-javanese" },
  ] as const;

  const doneDocs = stats.documents.total - reviewPending - failedDocs;
  const progress = [
    {
      label: "Selesai",
      value: doneDocs,
      fill: "bg-forest",
      pct: stats.documents.total > 0 ? (doneDocs / stats.documents.total) * 100 : 0,
    },
    {
      label: "Perlu review",
      value: reviewPending,
      fill: "bg-amber",
      pct: stats.documents.total > 0 ? (reviewPending / stats.documents.total) * 100 : 0,
    },
    {
      label: "Gagal",
      value: failedDocs,
      fill: "bg-red",
      pct: stats.documents.total > 0 ? (failedDocs / stats.documents.total) * 100 : 0,
    },
  ];

  const satisfaction =
    stats.feedback.total > 0
      ? Math.round((stats.feedback.helpful / stats.feedback.total) * 100)
      : 0;

  return (
    <div className="mx-auto max-w-[1200px] space-y-6">
      <PageHeader
        eyebrow="Ikhtisar knowledge base"
        title="Dashboard"
        description="Ringkasan dokumen, percakapan, dan feedback pengguna."
        actions={
          <Link
            href="/admin/upload"
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-javanese px-4 text-sm font-semibold text-white transition hover:bg-forest"
          >
            <UploadIcon className="size-4" /> Upload dokumen
          </Link>
        }
      />

      {reviewPending + failedDocs > 0 ? (
        <Link
          href="/documents"
          className="group flex items-center gap-3 rounded-xl border border-amber/30 bg-amber-soft px-4 py-3 transition hover:border-amber/60"
        >
          <AlertIcon className="size-5 shrink-0 text-amber" />
          <p className="min-w-0 flex-1 text-sm text-tinta">
            <strong className="font-semibold">{reviewPending} dokumen</strong> menunggu tinjauan dan{" "}
            <strong className="font-semibold">{failedDocs} gagal</strong> diproses oleh pipeline.
          </p>
          <span className="hidden shrink-0 text-xs font-semibold text-amber group-hover:underline sm:inline">
            Tinjau sekarang
          </span>
        </Link>
      ) : null}

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
        {kpiCards.map((card, index) => {
          const Icon = card.icon;
          const foot = kpiFooters[index];
          return (
            <div
              key={card.key}
              className="relative overflow-hidden rounded-xl border border-line bg-white shadow-[0_1px_2px_rgba(26,26,46,0.04)]"
            >
              <span
                aria-hidden="true"
                className="absolute inset-y-0 left-0 w-[3px] bg-[repeating-linear-gradient(180deg,var(--emas-keraton)_0px,var(--emas-keraton)_5px,transparent_5px,transparent_10px)]"
              />
              <div className="flex items-start justify-between gap-3 p-5 pl-6">
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold tracking-[0.08em] text-muted-text uppercase">
                    {card.label}
                  </p>
                  <p className="mt-1.5 font-mono text-[28px] leading-none font-bold tracking-tight text-tinta tabular-nums">
                    {kpiValues[card.key]}
                  </p>
                </div>
                <span
                  className={cn(
                    "flex size-9 shrink-0 items-center justify-center rounded-lg",
                    card.tint
                  )}
                >
                  <Icon className="size-[18px]" />
                </span>
              </div>
              <div className="mx-5 mb-4 flex items-center gap-2 border-t border-dashed border-line pt-3">
                <span
                  aria-hidden="true"
                  className={cn("size-1.5 shrink-0 rounded-full", foot.dot)}
                />
                <span className="truncate text-xs text-muted-text">{foot.text}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="rounded-xl border border-line bg-white shadow-[0_1px_2px_rgba(26,26,46,0.04)]">
          <header className="border-b border-line px-6 py-4">
            <h2 className="text-sm font-semibold text-tinta">Proses dokumen</h2>
          </header>
          <div className="space-y-5 px-6 py-5">
            {progress.map((item) => (
              <div key={item.label}>
                <div className="mb-1.5 flex items-center justify-between text-sm">
                  <span className="text-muted-text">{item.label}</span>
                  <span className="font-mono font-medium text-tinta tabular-nums">
                    {item.value}
                    <span className="ml-1.5 text-xs text-muted-text">{Math.round(item.pct)}%</span>
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className={cn("h-full rounded-full transition-all duration-500", item.fill)}
                    style={{ width: `${item.pct}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-xl border border-line bg-white shadow-[0_1px_2px_rgba(26,26,46,0.04)]">
          <header className="border-b border-line px-6 py-4">
            <h2 className="text-sm font-semibold text-tinta">Feedback pengguna</h2>
          </header>
          <div className="grid grid-cols-3 gap-3 px-6 py-5">
            <div className="rounded-xl border border-forest/15 bg-teal-soft/40 p-4 text-center">
              <CheckIcon className="mx-auto size-5 text-forest" />
              <strong className="mt-2 block font-mono text-2xl text-tinta tabular-nums">
                {stats.feedback.helpful}
              </strong>
              <span className="text-xs text-muted-text">Membantu</span>
            </div>
            <div className="rounded-xl border border-red/15 bg-red-soft p-4 text-center">
              <AlertIcon className="mx-auto size-5 text-red" />
              <strong className="mt-2 block font-mono text-2xl text-tinta tabular-nums">
                {stats.feedback.not_helpful}
              </strong>
              <span className="text-xs text-muted-text">Tidak membantu</span>
            </div>
            <div className="rounded-xl border border-javanese/15 bg-blue-soft p-4 text-center">
              <ChatIcon className="mx-auto size-5 text-javanese" />
              <strong className="mt-2 block font-mono text-2xl text-tinta tabular-nums">
                {satisfaction}%
              </strong>
              <span className="text-xs text-muted-text">Kepuasan</span>
            </div>
          </div>
        </section>
      </div>

      <section className="rounded-xl border border-line bg-white shadow-[0_1px_2px_rgba(26,26,46,0.04)]">
        <div className="flex items-center justify-between border-b border-line px-6 py-4">
          <h2 className="text-sm font-semibold text-tinta">Ingestion terbaru</h2>
          <Link
            href="/admin/ingestion"
            className="text-xs font-semibold text-forest transition hover:text-emas"
          >
            Lihat semua
          </Link>
        </div>
        {stats.ingestion_jobs.recent.length === 0 ? (
          <EmptyState
            icon={DatabaseIcon}
            title="Belum ada job ingestion"
            hint="Unggah dokumen PDF untuk memulai pipeline pemrosesan."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-line font-mono text-[11px] tracking-[0.12em] text-muted-text uppercase">
                  <th className="px-6 py-3 font-semibold">Dokumen</th>
                  <th className="px-6 py-3 font-semibold">Status</th>
                  <th className="px-6 py-3 text-right font-semibold">Waktu</th>
                </tr>
              </thead>
              <tbody>
                {stats.ingestion_jobs.recent.map((job) => (
                  <tr key={job.job_id} className="border-b border-dashed border-line last:border-0">
                    <td className="px-6 py-3.5 font-medium text-tinta">{job.document_id}</td>
                    <td className="px-6 py-3.5">
                      <StatusBadge
                        tone={ingestionTone[job.status] ?? "neutral"}
                        pulse={job.status === "running"}
                      >
                        {ingestionLabel[job.status] ?? job.status}
                      </StatusBadge>
                    </td>
                    <td className="px-6 py-3.5 text-right text-xs text-muted-text tabular-nums">
                      {formatDate(job.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-line bg-white shadow-[0_1px_2px_rgba(26,26,46,0.04)]">
        <header className="border-b border-line px-6 py-4">
          <h2 className="text-sm font-semibold text-tinta">Aksi cepat</h2>
        </header>
        <div className="grid grid-cols-1 gap-3 px-6 py-5 sm:grid-cols-2 lg:grid-cols-5">
          {(
            [
              { href: "/admin/upload", icon: UploadIcon, label: "Upload PDF" },
              { href: "/documents", icon: FileIcon, label: "Kelola dokumen" },
              { href: "/admin/ingestion", icon: DatabaseIcon, label: "Ingestion" },
              { href: "/admin/feedback", icon: ChatIcon, label: "Feedback" },
              { href: "/admin/retrieval", icon: RefreshIcon, label: "Retrieval lab" },
            ] as const
          ).map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="group flex items-center gap-3 rounded-xl border border-line px-4 py-3.5 text-sm font-medium text-tinta transition hover:border-javanese/40 hover:bg-surface-soft hover:text-javanese"
            >
              <item.icon className="size-[18px] shrink-0 text-muted-text transition group-hover:text-javanese" />
              <span className="truncate">{item.label}</span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
