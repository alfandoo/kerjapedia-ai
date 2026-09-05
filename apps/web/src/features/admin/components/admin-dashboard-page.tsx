"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { EmptyState, PageHeader, StatusBadge } from "./primitives";
import { AlertIcon, DatabaseIcon, ThumbsDownIcon, ThumbsUpIcon } from "@/components/icons";
import { BadgeCheck, FileUp, Files, MessageSquareText, Users } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { clearStoredSession, fetchAdminStats } from "@/features/admin/api";
import type { AdminStats } from "@/features/admin/types";
import { cn } from "@/lib/utils";
import styles from "./admin-dashboard.module.css";

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

function safeDate(value: string) {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatDate(value: string) {
  const d = safeDate(value);
  if (!d) return "—";
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

function formatRelative(value: string) {
  const d = safeDate(value);
  if (!d) return "—";
  const minutes = Math.round((Date.now() - d.getTime()) / 60000);
  if (minutes < 1) return "Baru saja";
  if (minutes < 60) return `${minutes} menit lalu`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} jam lalu`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} hari lalu`;
  return formatDate(value);
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-3 w-44" />
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-4 w-72" />
      </div>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-[128px] rounded-xl" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <Skeleton className="h-60 rounded-xl lg:col-span-3" />
        <Skeleton className="h-60 rounded-xl lg:col-span-2" />
      </div>
      <Skeleton className="h-56 rounded-xl" />
    </div>
  );
}

export function AdminDashboardPage() {
  const router = useRouter();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);
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
  }, [router, reloadKey]);

  if (loading) {
    return (
      <div
        className={`${styles.dashboard} mx-auto max-w-[1200px]`}
        role="status"
        aria-label="Memuat dashboard"
      >
        <DashboardSkeleton />
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className={`${styles.dashboard} flex min-h-64 items-center justify-center`} role="alert">
        <div className="w-full max-w-sm rounded-xl border border-teal-soft bg-white p-2 shadow-[0_1px_3px_rgba(27,67,50,0.06)]">
          <EmptyState
            icon={AlertIcon}
            title="Data dashboard tidak dapat dimuat"
            hint={error ?? "Coba muat ulang halaman."}
            action={
              <button
                type="button"
                className="h-10 rounded-xl border border-teal-soft bg-white px-5 text-sm font-semibold text-forest transition hover:border-forest hover:text-teal"
                onClick={() => {
                  setError(null);
                  setLoading(true);
                  setReloadKey((value) => value + 1);
                }}
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
    { text: `${docPercent}% telah diterbitkan`, dot: "bg-forest" },
    {
      text: reviewPending > 0 ? `${reviewPending} menunggu review` : "Tidak ada antrean tinjauan",
      dot: reviewPending > 0 ? "bg-amber" : "bg-forest",
    },
    { text: `${stats.conversations} total percakapan`, dot: "bg-teal" },
    { text: `${stats.feedback.total} feedback masuk`, dot: "bg-forest/60" },
  ];
  const kpiCards = [
    { key: "documents", label: "Total dokumen", icon: Files, tone: "text-forest" },
    { key: "published", label: "Dokumen terbit", icon: BadgeCheck, tone: "text-teal" },
    { key: "users", label: "Pengguna terdaftar", icon: Users, tone: "text-javanese" },
    { key: "messages", label: "Total pesan", icon: MessageSquareText, tone: "text-forest/70" },
  ] as const;

  const otherDocs = Math.max(0, stats.documents.total - reviewPending - failedDocs);
  const hasTotal = stats.documents.total > 0;
  const composition = [
    {
      label: "Selesai",
      value: otherDocs,
      fill: "bg-muted-text",
      pct: hasTotal ? (otherDocs / stats.documents.total) * 100 : 0,
    },
    {
      label: "Perlu review",
      value: reviewPending,
      fill: "bg-amber",
      pct: hasTotal ? (reviewPending / stats.documents.total) * 100 : 0,
    },
    {
      label: "Gagal",
      value: failedDocs,
      fill: "bg-red",
      pct: hasTotal ? (failedDocs / stats.documents.total) * 100 : 0,
    },
  ];

  const satisfaction =
    stats.feedback.total > 0
      ? Math.round((stats.feedback.helpful / stats.feedback.total) * 100)
      : 0;

  const attentionParts: string[] = [];
  if (reviewPending > 0) attentionParts.push(`${reviewPending} dokumen menunggu tinjauan`);
  if (failedDocs > 0) attentionParts.push(`${failedDocs} gagal diproses`);

  return (
    <div className={`${styles.dashboard} mx-auto max-w-[1200px] space-y-6`}>
      <PageHeader
        eyebrow="Ikhtisar operasional"
        title="Dashboard"
        description="Ringkasan dokumen, percakapan, dan feedback pengguna."
        actions={
          <Link href="/admin/upload" className={styles.upload}>
            <FileUp className="size-4" strokeWidth={2} /> Upload dokumen
          </Link>
        }
      />

      {attentionParts.length > 0 ? (
        <Link
          href="/documents"
          className={cn(
            "group flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 transition",
            failedDocs > 0
              ? "border-red/30 bg-red-soft hover:border-red/60"
              : "border-amber/30 bg-amber-soft hover:border-amber/60"
          )}
        >
          <AlertIcon
            className={cn("size-5 shrink-0", failedDocs > 0 ? "text-red" : "text-amber")}
          />
          <p className="min-w-0 flex-1 text-sm text-tinta">
            <strong className="font-semibold">{attentionParts.join(" dan ")}</strong>.
          </p>
          <span
            className={cn(
              "shrink-0 text-xs font-semibold group-hover:underline",
              failedDocs > 0 ? "text-red" : "text-amber"
            )}
          >
            Tinjau sekarang
          </span>
        </Link>
      ) : null}

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
        {kpiCards.map((card, index) => {
          const Icon = card.icon;
          const foot = kpiFooters[index];
          return (
            <div key={card.key} className={styles.metric}>
              <div className="flex items-center justify-between gap-3">
                <p className="text-[13px] font-medium text-muted-text">{card.label}</p>
                <span className="flex size-8 items-center justify-center rounded-lg bg-teal-soft/70 text-forest">
                  <Icon
                    strokeWidth={1.75}
                    className={cn("size-4.5 shrink-0 transition-colors", card.tone)}
                  />
                </span>
              </div>
              <p className="mt-3 font-mono text-[30px] leading-none font-bold tracking-tight text-forest tabular-nums">
                {new Intl.NumberFormat("id-ID").format(kpiValues[card.key])}
              </p>
              <div className="mt-4 flex items-center gap-2 border-t border-teal-soft pt-3">
                <span
                  aria-hidden="true"
                  className={cn(
                    "size-1.5 shrink-0 rounded-full transition-transform group-hover:scale-125",
                    foot.dot
                  )}
                />
                <span className="text-xs leading-relaxed text-muted-text">{foot.text}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <section className="rounded-xl border border-teal-soft bg-white shadow-[0_1px_3px_rgba(27,67,50,0.06)] lg:col-span-3">
          <header className="flex items-center justify-between border-b border-teal-soft px-6 py-4">
            <h2 className="text-sm font-semibold text-forest">Kondisi dokumen</h2>
            <Link
              href="/documents"
              className="text-xs font-semibold text-forest transition hover:text-teal"
            >
              Kelola dokumen
            </Link>
          </header>
          <div className="px-6 py-5">
            <p className="font-mono text-3xl leading-none font-bold tracking-tight text-forest tabular-nums">
              {docPercent}%
              <span className="ml-2 align-middle font-sans text-xs font-normal text-muted-text">
                dokumen terbit dari total {stats.documents.total}
              </span>
            </p>

            {hasTotal ? (
              <>
                <div
                  role="img"
                  aria-label={`Status pemrosesan: ${otherDocs} selesai, ${reviewPending} perlu review, ${failedDocs} gagal`}
                  className="mt-4 flex h-2.5 overflow-hidden rounded-full bg-teal-soft/60"
                >
                  {composition.map(
                    (item) =>
                      item.pct > 0 && (
                        <div
                          key={item.label}
                          className={cn(
                            "h-full first:rounded-l-full last:rounded-r-full",
                            item.fill
                          )}
                          style={{ width: `${item.pct}%` }}
                        />
                      )
                  )}
                </div>
                <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
                  {composition.map((item) => (
                    <div key={item.label} className="border-l-2 border-teal-soft pl-3 py-1">
                      <dt className="flex items-center gap-1.5 text-xs text-muted-text">
                        <span
                          aria-hidden="true"
                          className={cn("size-1.5 shrink-0 rounded-full", item.fill)}
                        />
                        {item.label}
                      </dt>
                      <dd className="mt-0.5 font-mono text-lg font-bold text-forest tabular-nums">
                        {item.value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </>
            ) : (
              <p className="mt-4 rounded-lg border border-dashed border-teal-soft bg-teal-soft/40 px-4 py-6 text-center text-sm text-muted-text">
                Belum ada dokumen pada knowledge base. Unggah PDF pertama untuk memulai.
              </p>
            )}
          </div>
        </section>

        <section className="rounded-xl border border-teal-soft bg-white shadow-[0_1px_3px_rgba(27,67,50,0.06)] lg:col-span-2">
          <header className="flex items-center justify-between border-b border-teal-soft px-6 py-4">
            <h2 className="text-sm font-semibold text-forest">Umpan balik</h2>
            <Link
              href="/admin/feedback"
              className="text-xs font-semibold text-forest transition hover:text-teal"
            >
              Lihat semua
            </Link>
          </header>
          <div className="flex flex-col px-6 py-5">
            <div className="flex items-end justify-between gap-4">
              <p className="text-sm text-muted-text">Jawaban dinilai membantu</p>
              <p className="font-mono text-3xl leading-none font-bold tracking-tight text-forest tabular-nums">
                {stats.feedback.total > 0 ? `${satisfaction}%` : "—"}
              </p>
            </div>
            <div
              role="img"
              aria-label={`${stats.feedback.total > 0 ? `${satisfaction}%` : "—"} feedback membantu dari total ${stats.feedback.total}`}
              className="mt-3 flex h-2 overflow-hidden rounded-full bg-teal-soft/60"
            >
              {stats.feedback.total > 0 ? (
                <>
                  <div
                    className="h-full rounded-l-full bg-forest"
                    style={{ width: `${(stats.feedback.helpful / stats.feedback.total) * 100}%` }}
                  />
                  <div
                    className="h-full rounded-r-full bg-red/70"
                    style={{
                      width: `${(stats.feedback.not_helpful / stats.feedback.total) * 100}%`,
                    }}
                  />
                </>
              ) : null}
            </div>
            <dl className="mt-4 space-y-2.5">
              <div className="flex items-center gap-2.5">
                <ThumbsUpIcon className="size-4 shrink-0 text-forest" />
                <dt className="flex-1 text-sm text-muted-text">Membantu</dt>
                <dd className="font-mono text-sm font-semibold text-tinta tabular-nums">
                  {stats.feedback.helpful}
                </dd>
              </div>
              <div className="flex items-center gap-2.5 border-t border-dashed border-line pt-2.5">
                <ThumbsDownIcon className="size-4 shrink-0 text-red" />
                <dt className="flex-1 text-sm text-muted-text">Tidak membantu</dt>
                <dd className="font-mono text-sm font-semibold text-tinta tabular-nums">
                  {stats.feedback.not_helpful}
                </dd>
              </div>
            </dl>
            {stats.feedback.total === 0 ? (
              <p className="mt-auto pt-4 text-xs text-muted-text">
                Belum ada feedback masuk dari pengguna.
              </p>
            ) : null}
          </div>
        </section>
      </div>

      <section className="rounded-xl border border-teal-soft bg-white shadow-[0_1px_3px_rgba(27,67,50,0.06)]">
        <div className="flex items-center justify-between border-b border-teal-soft px-6 py-4">
          <h2 className="text-sm font-semibold text-forest">Pemrosesan terbaru</h2>
          <Link
            href="/admin/ingestion"
            className="text-xs font-semibold text-forest transition hover:text-teal"
          >
            Lihat semua
          </Link>
        </div>
        {stats.ingestion_jobs.recent.length === 0 ? (
          <EmptyState
            icon={DatabaseIcon}
            title="Belum ada pemrosesan dokumen"
            hint="Unggah PDF pertama untuk mulai menyiapkan sumber jawaban."
          />
        ) : (
          <ul className="divide-y divide-dashed divide-line">
            {stats.ingestion_jobs.recent.map((job) => (
              <li key={job.job_id}>
                <Link
                  href="/admin/ingestion"
                  className="flex flex-wrap items-center gap-3 px-6 py-3.5 transition-colors hover:bg-surface-soft"
                >
                  <span
                    title={job.document_id}
                    className="min-w-0 flex-1 truncate text-sm font-medium text-tinta"
                  >
                    {job.document_id}
                  </span>
                  <StatusBadge
                    tone={ingestionTone[job.status] ?? "neutral"}
                    pulse={job.status === "running"}
                  >
                    {ingestionLabel[job.status] ?? job.status}
                  </StatusBadge>
                  <time
                    dateTime={job.created_at}
                    title={formatDate(job.created_at)}
                    className="w-full text-xs text-muted-text tabular-nums sm:w-28 sm:shrink-0 sm:text-right"
                  >
                    {formatRelative(job.created_at)}
                  </time>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
