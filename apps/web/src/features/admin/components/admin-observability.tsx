"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import { Activity, ArrowDownLeft, ArrowUpRight, Coins, Gauge, RefreshCw, ShieldCheck, Sigma, Timer, Users } from "lucide-react";

import { EmptyState, PageHeader, StatusBadge } from "./primitives";
import { AlertIcon } from "@/components/icons";
import { Skeleton } from "@/components/ui/skeleton";
import { clearStoredSession, fetchAdminMetrics } from "@/features/admin/api";
import type { AdminMetrics, HistogramStats } from "@/features/admin/types";
import { cn } from "@/lib/utils";
import styles from "./admin-dashboard.module.css";

function formatInt(value: number) {
  return new Intl.NumberFormat("id-ID").format(Math.round(value));
}

function formatSeconds(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "Belum ada data";
  return `${new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(value)} dtk`;
}

function formatScore(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "Belum ada data";
  return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(value);
}

function formatPct(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "Belum ada data";
  return `${new Intl.NumberFormat("id-ID", { maximumFractionDigits: 1 }).format(value * 100)}%`;
}

function topEntries(record: Record<string, number>, limit = 8) {
  return Object.entries(record)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
}

function BarRow({
  label,
  display,
  pct,
  fill,
}: {
  label: string;
  display: string;
  pct: number;
  fill: string;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <dt className="min-w-0 truncate text-sm text-muted-text">{label}</dt>
        <dd className="shrink-0 font-mono text-sm font-semibold text-tinta tabular-nums">
          {display}
        </dd>
      </div>
      <div
        role="img"
        aria-label={`${label}: ${display}`}
        className="mt-1.5 h-2 overflow-hidden rounded-full bg-[#e9edea]"
      >
        <div
          className={cn("h-full rounded-full", fill)}
          style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
        />
      </div>
    </div>
  );
}

function SectionCard({
  title,
  hint,
  icon: Icon,
  children,
}: {
  title: string;
  hint: string;
  icon: ComponentType<{ className?: string }>;
  children: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-[#e5e5e5] bg-white shadow-[0_1px_3px_rgba(27,67,50,0.06)]">
      <header className="border-b border-[#e5e5e5] px-6 py-4">
        <div className="flex items-center gap-3">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-teal-soft/70">
            <Icon className="size-4 text-forest" />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-forest">{title}</h2>
            <p className="mt-0.5 text-xs text-muted-text">{hint}</p>
          </div>
        </div>
      </header>
      <div className="space-y-5 px-6 py-5">{children}</div>
    </section>
  );
}

function ObservabilitySkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-3 w-44" />
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-4 w-72" />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-[112px] rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-64 rounded-xl" />
      <Skeleton className="h-64 rounded-xl" />
    </div>
  );
}

const outcomeStyle: Record<string, { label: string; fill: string; text: string }> = {
  answered: { label: "Dijawab", fill: "bg-forest", text: "text-forest" },
  refused: { label: "Ditolak", fill: "bg-amber", text: "text-amber" },
  failed: { label: "Gagal", fill: "bg-red", text: "text-red" },
  temporarily_unavailable: {
    label: "Tak tersedia",
    fill: "bg-muted-text",
    text: "text-muted-text",
  },
};

export function AdminObservability() {
  const router = useRouter();
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchAdminMetrics(controller.signal)
      .then((data) => {
        setMetrics(data);
        setLoading(false);
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        const message = (err as Error).message || "Gagal memuat metrik observability.";
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
        aria-label="Memuat observability"
      >
        <ObservabilitySkeleton />
      </div>
    );
  }

  if (error || !metrics) {
    return (
      <div className={`${styles.dashboard} flex min-h-64 items-center justify-center`} role="alert">
        <div className="w-full max-w-sm rounded-xl border border-[#e5e5e5] bg-white p-2 shadow-[0_1px_3px_rgba(27,67,50,0.06)]">
          <EmptyState
            icon={AlertIcon}
            title="Metrik tidak dapat dimuat"
            hint={error ?? "Coba muat ulang halaman."}
            action={
              <button
                type="button"
                className="h-10 rounded-xl border border-[#e5e5e5] bg-white px-5 text-sm font-semibold text-forest transition hover:border-forest hover:text-teal"
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

  const stageEntries = Object.entries(metrics.stage_latency).sort(
    (a, b) => (b[1].avg ?? 0) - (a[1].avg ?? 0)
  );
  const maxStageAvg = Math.max(0, ...stageEntries.map(([, stat]) => stat.avg ?? 0));
  const outcomeEntries = topEntries(metrics.outcomes, 10);
  const outcomeTotal = outcomeEntries.reduce((sum, [, value]) => sum + value, 0);
  const donutSegments = outcomeEntries.map(([key, value]) => {
    const style = outcomeStyle[key] ?? {
      label: key,
      fill: "bg-muted-text",
      text: "text-muted-text",
    };
    return { key, ...style, value };
  });
  let donutOffset = 0;
  const donutGradient =
    outcomeTotal > 0
      ? donutSegments
          .map((segment) => {
            const start = (donutOffset / outcomeTotal) * 100;
            donutOffset += segment.value;
            const end = (donutOffset / outcomeTotal) * 100;
            const color =
              segment.key === "answered"
                ? "#286246"
                : segment.key === "refused"
                  ? "#8a5a10"
                  : segment.key === "failed"
                    ? "#a83126"
                    : "#607067";
            return `${color} ${start}% ${end}%`;
          })
          .join(", ")
      : "#e5e5e5 0% 100%";
  const topicEntries = topEntries(metrics.behavior.by_topic, 8);
  const maxTopic = Math.max(1, ...topicEntries.map(([, value]) => value));
  const openaiUsage = Object.entries(metrics.tokens.by_model).filter(([model]) =>
    model.startsWith("openai/")
  );
  const openaiPrompt = openaiUsage.reduce((sum, [, usage]) => sum + usage.prompt, 0);
  const openaiCompletion = openaiUsage.reduce((sum, [, usage]) => sum + usage.completion, 0);
  const modelEntries = topEntries(
    Object.fromEntries(
      openaiUsage.map(([model, usage]) => [model, usage.prompt + usage.completion])
    ),
    6
  );
  const requestLatency: Partial<HistogramStats> = metrics.request_latency ?? {};
  const faithfulness = metrics.ragas.faithfulness ?? {};
  const evalEntries = topEntries(metrics.ragas.eval_total, 5);
  const evalTotal = evalEntries.reduce((sum, [, value]) => sum + value, 0);

  const kpiCards = [
    {
      key: "requests",
      label: "Total permintaan RAG",
      icon: Activity,
      value: formatInt(metrics.requests.total),
      footer: `${formatInt(metrics.behavior.total)} tercatat perilaku`,
    },
    {
      key: "latency",
      label: "Latensi rata-rata",
      icon: Timer,
      value: formatSeconds(requestLatency.avg),
      footer: `p95 ${formatSeconds(requestLatency.p95)} · n=${formatInt(requestLatency.count ?? 0)}`,
    },
    {
      key: "support",
      label: "Tingkat klaim didukung",
      icon: ShieldCheck,
      value: formatPct(metrics.claims.support_rate),
      footer: `${formatInt(metrics.claims.supported)} didukung · ${formatInt(metrics.claims.unsupported)} tidak`,
    },
    {
      key: "ragas",
      label: "RAGAS faithfulness",
      icon: Gauge,
      value: formatScore(faithfulness.avg),
      footer:
        (faithfulness.count ?? 0) > 0
          ? `n=${formatInt(faithfulness.count ?? 0)} sampel · p50 ${formatScore(faithfulness.p50)}`
          : "Belum ada sampel online",
    },
  ];

  return (
    <div className={`${styles.dashboard} mx-auto max-w-[1200px] space-y-6`}>
      <PageHeader
        eyebrow="Observability"
        title="Kesehatan RAG"
        description="Latensi pipeline, pemakaian token, perilaku pengguna, dan kualitas jawaban (RAGAS online)."
        actions={
          <button
            type="button"
            className={styles.upload}
            onClick={() => {
              setError(null);
              setLoading(true);
              setMetrics(null);
              setReloadKey((value) => value + 1);
            }}
          >
            <RefreshCw className="size-4" strokeWidth={2} /> Muat ulang
          </button>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {kpiCards.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.key}
              className="rounded-xl border border-[#e5e5e5] bg-white px-5 py-4 shadow-[0_1px_3px_rgba(27,67,50,0.06)]"
            >
              <div className="flex items-start gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-teal-soft/70">
                  <Icon strokeWidth={1.75} className="size-5 text-forest" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-muted-text">{card.label}</p>
                  <p className="mt-0.5 font-mono text-xl leading-tight font-bold tracking-tight whitespace-nowrap text-tinta tabular-nums">
                    {card.value}
                  </p>
                  <p className="mt-1 text-[11px] leading-relaxed text-muted-text">{card.footer}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <SectionCard
        title="Kesehatan pipeline RAG"
        hint="Distribusi hasil, latensi tiap tahap, dan verifikasi klaim dari Prometheus."
        icon={Activity}
      >
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div>
            <h3 className="text-sm font-semibold text-tinta">Distribusi hasil</h3>
            {outcomeTotal > 0 ? (
              <div className="mt-3 flex items-center gap-4">
                <div
                  role="img"
                  aria-label={`Distribusi hasil dari ${outcomeTotal} permintaan`}
                  className="size-24 shrink-0 rounded-full"
                  style={{ background: `conic-gradient(${donutGradient})` }}
                />
                <dl className="w-full max-w-56 min-w-0 flex-1 space-y-2">
                  {donutSegments.map((segment) => (
                    <div key={segment.key} className="flex items-center gap-2 text-sm">
                      <span
                        aria-hidden="true"
                        className={cn("size-2 shrink-0 rounded-full", segment.fill)}
                      />
                      <dt className="flex-1 truncate text-muted-text">{segment.label}</dt>
                      <dd className="font-mono font-semibold text-tinta tabular-nums">
                        {formatInt(segment.value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            ) : (
              <p className="mt-3 rounded-lg border border-dashed border-[#e5e5e5] bg-teal-soft/40 px-4 py-6 text-center text-sm text-muted-text">
                Belum ada permintaan RAG yang tercatat.
              </p>
            )}
            {metrics.provider_errors.total > 0 ? (
              <p className="mt-3 text-xs text-red">
                {formatInt(metrics.provider_errors.total)} error provider
                {topEntries(metrics.provider_errors.by_stage, 3)
                  .map(([stage, count]) => ` · ${stage}: ${formatInt(count)}`)
                  .join("")}
              </p>
            ) : null}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-tinta">Latensi per tahap</h3>
            {stageEntries.length > 0 ? (
              <dl className="mt-3 space-y-3.5">
                {stageEntries.map(([stage, stat]) => (
                  <BarRow
                    key={stage}
                    label={stage.replaceAll("_", " ")}
                    display={`rerata ${formatSeconds(stat.avg)} · p95 ${formatSeconds(stat.p95)}`}
                    pct={maxStageAvg > 0 ? ((stat.avg ?? 0) / maxStageAvg) * 100 : 0}
                    fill="bg-forest"
                  />
                ))}
              </dl>
            ) : (
              <p className="mt-3 rounded-lg border border-dashed border-[#e5e5e5] bg-teal-soft/40 px-4 py-6 text-center text-sm text-muted-text">
                Belum ada data latensi tahap.
              </p>
            )}
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Pemakaian token"
        hint="Akumulasi token prompt vs completion model OpenAI."
        icon={Coins}
      >
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-[#e5e5e5] px-4 py-3">
            <dt className="flex items-center gap-1.5 text-xs text-muted-text">
              <ArrowUpRight aria-hidden="true" className="size-3.5 text-forest" />
              Token prompt
            </dt>
            <dd className="mt-1 font-mono text-xl font-bold text-forest tabular-nums">
              {formatInt(openaiPrompt)}
            </dd>
          </div>
          <div className="rounded-lg border border-[#e5e5e5] px-4 py-3">
            <dt className="flex items-center gap-1.5 text-xs text-muted-text">
              <ArrowDownLeft aria-hidden="true" className="size-3.5 text-amber" />
              Token completion
            </dt>
            <dd className="mt-1 font-mono text-xl font-bold text-amber tabular-nums">
              {formatInt(openaiCompletion)}
            </dd>
          </div>
          <div className="rounded-lg border border-[#e5e5e5] px-4 py-3">
            <dt className="flex items-center gap-1.5 text-xs text-muted-text">
              <Sigma aria-hidden="true" className="size-3.5 text-tinta" />
              Total token
            </dt>
            <dd className="mt-1 font-mono text-xl font-bold text-tinta tabular-nums">
              {formatInt(openaiPrompt + openaiCompletion)}
            </dd>
          </div>
        </dl>
        {modelEntries.length > 0 ? (
          <dl className="space-y-3.5">
            {modelEntries.map(([model]) => {
              const usage = metrics.tokens.by_model[model];
              const total = usage.prompt + usage.completion;
              const promptPct = total > 0 ? (usage.prompt / total) * 100 : 0;
              return (
                <div key={model}>
                  <p className="truncate text-sm text-muted-text">{model}</p>
                  <div
                    role="img"
                    aria-label={`${model}: ${formatInt(usage.prompt)} prompt, ${formatInt(usage.completion)} completion`}
                    className="mt-1.5 flex h-2 overflow-hidden rounded-full bg-[#e9edea]"
                  >
                    <div className="h-full bg-forest" style={{ width: `${promptPct}%` }} />
                    <div
                      className="h-full bg-[#c9a227]"
                      style={{ width: `${100 - promptPct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </dl>
        ) : (
          <p className="rounded-lg border border-dashed border-[#e5e5e5] bg-teal-soft/40 px-4 py-6 text-center text-sm text-muted-text">
            Belum ada pemakaian token yang tercatat.
          </p>
        )}
      </SectionCard>

      <SectionCard
        title="Perilaku pengguna & kualitas"
        hint="Rasio follow-up, distribusi topik, dan skor RAGAS faithfulness online (5% sampel)."
        icon={Users}
      >
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div>
            <h3 className="text-sm font-semibold text-tinta">Follow-up & topik</h3>
            <p className="mt-3 font-mono text-3xl leading-none font-bold tracking-tight text-forest tabular-nums">
              {formatPct(metrics.behavior.followup_ratio)}
              <span className="ml-2 align-middle font-sans text-xs font-normal text-muted-text">
                dari {formatInt(metrics.behavior.total)} permintaan
              </span>
            </p>
            {topicEntries.length > 0 ? (
              <dl className="mt-4 space-y-3.5">
                {topicEntries.map(([topic, count]) => (
                  <BarRow
                    key={topic}
                    label={topic === "unknown" ? "Lainnya" : topic}
                    display={formatInt(count)}
                    pct={(count / maxTopic) * 100}
                    fill="bg-teal"
                  />
                ))}
              </dl>
            ) : (
              <p className="mt-3 rounded-lg border border-dashed border-[#e5e5e5] bg-teal-soft/40 px-4 py-6 text-center text-sm text-muted-text">
                Belum ada data topik.
              </p>
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-tinta">RAGAS online</h3>
            <p className="mt-3 flex items-center gap-2 text-sm">
              <span
                className={cn(
                  "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold",
                  metrics.ragas_enabled ? "bg-teal-soft text-forest" : "bg-amber-soft text-amber"
                )}
              >
                {metrics.ragas_enabled
                  ? `Aktif · ${formatPct(metrics.ragas_sample_rate)} sampel`
                  : "Nonaktif"}
              </span>
            </p>
            {(faithfulness.count ?? 0) > 0 ? (
              <dl className="mt-4 space-y-3.5">
                <BarRow
                  label="Rerata faithfulness"
                  display={formatScore(faithfulness.avg)}
                  pct={(faithfulness.avg ?? 0) * 100}
                  fill="bg-forest"
                />
                <BarRow
                  label="Median (p50)"
                  display={formatScore(faithfulness.p50)}
                  pct={(faithfulness.p50 ?? 0) * 100}
                  fill="bg-teal"
                />
              </dl>
            ) : (
              <p className="mt-3 rounded-lg border border-dashed border-[#e5e5e5] bg-teal-soft/40 px-4 py-6 text-center text-sm text-muted-text">
                Belum ada sampel RAGAS. Aktifkan RAGAS dan tunggu permintaan masuk.
              </p>
            )}
            {evalTotal > 0 ? (
              <ul className="mt-3 space-y-2">
                {evalEntries.map(([statusName, count]) => (
                  <li key={statusName} className="flex items-center gap-2 text-xs">
                    <StatusBadge tone={statusName === "success" ? "success" : "danger"}>
                      {statusName === "success" ? "Berhasil" : "Gagal"}
                    </StatusBadge>
                    <span className="font-mono font-semibold text-tinta tabular-nums">
                      {formatInt(count)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
