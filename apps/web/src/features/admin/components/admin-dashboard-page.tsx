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
      <div className="mx-auto max-w-[1200px]">
        <DashboardSkeleton />
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
    { key: "documents", label: "Total dokumen", icon: Files, tone: "text-javanese" },
    { key: "published", label: "Dokumen aktif", icon: BadgeCheck, tone: "text-forest" },
    { key: "users", label: "Pengguna terdaftar", icon: Users, tone: "text-amber" },
    { key: "messages", label: "Total pesan", icon: MessageSquareText, tone: "text-teal" },
  ] as const;

  const doneDocs = stats.documents.total - reviewPending - failedDocs;
  const hasTotal = stats.documents.total > 0;
  const composition = [
    {
      label: "Selesai",
      value: doneDocs,
      fill: "bg-forest",
      pct: hasTotal ? (doneDocs / stats.documents.total) * 100 : 0,
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
    <div className="mx-auto max-w-[1200px] space-y-6">
      <PageHeader
        eyebrow="Ikhtisar knowledge base"
        title="Dashboard"
        description="Ringkasan dokumen, percakapan, dan feedback pengguna."
        actions={
          <Link
            href="/admin/upload"
            className="inline-flex h-11 items-center gap-2 rounded-xl bg-javanese px-5 text-sm font-bold text-white shadow-[0_2px_12px_rgba(27,67,50,0.22)] transition-all hover:bg-javanese-deep hover:shadow-[0_4px_16px_rgba(27,67,50,0.3)] active:translate-y-px motion-reduce:transition-none"
          >
            <FileUp className="size-4" strokeWidth={2} /> Upload dokumen
          </Link>
        }
      />

      {attentionParts.length > 0 ? (
        <Link
          href="/documents"
          className={cn(
            "group flex items-center gap-3 rounded-xl border px-4 py-3 transition",
            failedDocs > 0
              ? "border-red/30 bg-red-soft hover:border-red/60"
              : "border-amber/30 bg-amber-soft hover:border-amber/60"
          )}
        >
          <AlertIcon
            className={cn("size-5 shrink-0", failedDocs > 0 ? "text-red" : "text-amber")}
          />
          <p className="min-w-0 flex-1 text-sm text-tinta">
            <strong className="font-semibold">{attentionParts.join(" dan ")}</strong> oleh pipeline.
          </p>
          <span
            className={cn(
              "hidden shrink-0 text-xs font-semibold group-hover:underline sm:inline",
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
            <div
              key={card.key}
              className="group relative overflow-hidden rounded-xl border border-line bg-white p-5 shadow-[0_1px_2px_rgba(26,26,46,0.04)] transition-all duration-200 hover:-translate-y-0.5 hover:border-javanese/30 hover:shadow-[0_10px_28px_rgba(27,67,50,0.09)] motion-reduce:transition-none motion-reduce:hover:translate-y-0"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-[11px] font-semibold tracking-[0.08em] text-muted-text uppercase">
                  {card.label}
                </p>
                <Icon
                  strokeWidth={1.75}
                  className={cn("size-5 shrink-0 transition-colors", card.tone)}
                />
              </div>
              <p className="mt-3 font-mono text-[30px] leading-none font-bold tracking-tight text-tinta tabular-nums">
                {kpiValues[card.key]}
              </p>
              <div className="mt-4 flex items-center gap-2 border-t border-dashed border-line pt-3">
                <span
                  aria-hidden="true"
                  className={cn(
                    "size-1.5 shrink-0 rounded-full transition-transform group-hover:scale-125",
                    foot.dot
                  )}
                />
                <span className="truncate text-xs text-muted-text">{foot.text}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <section className="rounded-xl border border-line bg-white shadow-[0_1px_2px_rgba(26,26,46,0.04)] lg:col-span-3">
          <header className="flex items-center justify-between border-b border-line px-6 py-4">
            <h2 className="text-sm font-semibold text-tinta">Kondisi knowledge base</h2>
            <Link
              href="/documents"
              className="text-xs font-semibold text-forest transition hover:text-emas"
            >
              Kelola dokumen
            </Link>
          </header>
          <div className="px-6 py-5">
            <p className="font-mono text-3xl leading-none font-bold tracking-tight text-tinta tabular-nums">
              {docPercent}%
              <span className="ml-2 align-middle font-sans text-xs font-normal text-muted-text">
                dokumen aktif dari total {stats.documents.total}
              </span>
            </p>

            {hasTotal ? (
              <>
                <div
                  role="img"
                  aria-label={`Komposisi dokumen: ${doneDocs} selesai, ${reviewPending} perlu review, ${failedDocs} gagal`}
                  className="mt-4 flex h-2.5 overflow-hidden rounded-full bg-muted"
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
                <dl className="mt-4 grid grid-cols-3 gap-3">
                  {composition.map((item) => (
                    <div
                      key={item.label}
                      className="rounded-lg border border-dashed border-line px-3 py-2.5"
                    >
                      <dt className="flex items-center gap-1.5 text-xs text-muted-text">
                        <span
                          aria-hidden="true"
                          className={cn("size-1.5 shrink-0 rounded-full", item.fill)}
                        />
                        {item.label}
                      </dt>
                      <dd className="mt-0.5 font-mono text-lg font-bold text-tinta tabular-nums">
                        {item.value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </>
            ) : (
              <p className="mt-4 rounded-lg border border-dashed border-line bg-surface-soft px-4 py-6 text-center text-sm text-muted-text">
                Belum ada dokumen pada knowledge base. Unggah PDF pertama untuk memulai.
              </p>
            )}
          </div>
        </section>

        <section className="rounded-xl border border-line bg-white shadow-[0_1px_2px_rgba(26,26,46,0.04)] lg:col-span-2">
          <header className="flex items-center justify-between border-b border-line px-6 py-4">
            <h2 className="text-sm font-semibold text-tinta">Umpan balik</h2>
            <Link
              href="/admin/feedback"
              className="text-xs font-semibold text-forest transition hover:text-emas"
            >
              Lihat semua
            </Link>
          </header>
          <div className="flex h-[calc(100%-57px)] flex-col px-6 py-5">
            <div className="flex items-end justify-between gap-4">
              <p className="text-sm text-muted-text">Tingkat kepuasan</p>
              <p className="font-mono text-3xl leading-none font-bold tracking-tight text-javanese tabular-nums">
                {satisfaction}%
              </p>
            </div>
            <div
              role="img"
              aria-label={`${satisfaction}% feedback membantu dari total ${stats.feedback.total}`}
              className="mt-3 flex h-2 overflow-hidden rounded-full bg-muted"
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
          <ul className="divide-y divide-dashed divide-line">
            {stats.ingestion_jobs.recent.map((job) => (
              <li key={job.job_id}>
                <Link
                  href="/admin/ingestion"
                  className="flex items-center gap-4 px-6 py-3.5 transition-colors hover:bg-surface-soft"
                >
                  <span className="min-w-0 flex-1 truncate text-sm font-medium text-tinta">
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
                    className="hidden w-28 shrink-0 text-right text-xs text-muted-text tabular-nums sm:block"
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
