import type { ComponentType, ReactNode } from "react";

import { cn } from "@/lib/utils";

export type IconType = ComponentType<{ className?: string }>;

type Tone = "success" | "warning" | "danger" | "neutral" | "info";

const toneClasses: Record<Tone, string> = {
  success: "border-forest/20 bg-teal-soft/70 text-forest",
  warning: "border-amber/30 bg-amber-soft text-amber",
  danger: "border-red/25 bg-red-soft text-red",
  neutral: "border-line bg-muted/60 text-muted-text",
  info: "border-javanese/25 bg-blue-soft text-javanese",
};

const calloutIconTone: Record<Tone, string> = {
  success: "text-forest",
  warning: "text-amber",
  danger: "text-red",
  neutral: "text-muted-text",
  info: "text-javanese",
};

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="min-w-0 space-y-1">
        <p className="font-mono text-[11px] font-semibold tracking-[0.18em] text-forest uppercase">
          {eyebrow}
        </p>
        <h1 className="font-display text-[26px] leading-tight font-semibold text-javanese">
          {title}
        </h1>
        {description ? <p className="text-sm text-muted-text">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function StatusBadge({
  tone = "neutral",
  pulse = false,
  children,
  className,
}: {
  tone?: Tone;
  pulse?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        toneClasses[tone],
        className
      )}
    >
      {pulse ? (
        <span className="size-1.5 animate-pulse rounded-full bg-current motion-reduce:animate-none" />
      ) : null}
      {children}
    </span>
  );
}

export function Callout({
  tone = "neutral",
  title,
  children,
  className,
}: {
  tone?: Tone;
  title: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  const iconTone = calloutIconTone[tone];
  return (
    <div
      role={tone === "danger" || tone === "warning" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-2.5 rounded-lg border px-3.5 py-3 text-sm",
        toneClasses[tone],
        className
      )}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        className={cn("mt-0.5 size-4 shrink-0", iconTone)}
      >
        {tone === "warning" || tone === "danger" ? (
          <path d="M12 8v5m0 4h.01M10.3 4.8 2.8 18a2 2 0 0 0 1.7 3h15a2 2 0 0 0 1.7-3L13.7 4.8a2 2 0 0 0-3.4 0Z" />
        ) : (
          <path d="m5 12 4 4L19 6" />
        )}
      </svg>
      <span className="min-w-0">
        <strong className="block font-semibold">{title}</strong>
        {children ? <small className="text-xs">{children}</small> : null}
      </span>
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  hint,
  action,
}: {
  icon: IconType;
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-1.5 px-6 py-12 text-center">
      <span className="mb-1.5 flex size-11 items-center justify-center rounded-xl border border-dashed border-line bg-surface-soft text-muted-text">
        <Icon className="size-5" />
      </span>
      <p className="text-sm font-semibold text-tinta">{title}</p>
      {hint ? <p className="max-w-xs text-sm text-muted-text">{hint}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
