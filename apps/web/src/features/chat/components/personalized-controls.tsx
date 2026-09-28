"use client";

import { useSettings } from "@/features/settings";
import { LoaderCircle } from "lucide-react";

type Props = {
  enabled: boolean;
  memoryCount: number;
  busy: boolean;
  error: string | null;
  onToggle: (enabled: boolean) => void;
  onDelete: () => void;
};

export function PersonalizedControls({
  enabled,
  memoryCount,
  busy,
  error,
  onToggle,
  onDelete,
}: Props) {
  const { t } = useSettings();

  return (
    <section className="text-card-foreground">
      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="flex items-center justify-between gap-4 px-4 py-4">
          <div className="min-w-0">
            <p className="font-semibold">{t("chat.personalized.enable")}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("chat.personalized.enableDescription")}
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            aria-label={t("chat.personalized.enable")}
            aria-busy={busy}
            disabled={busy}
            onClick={() => onToggle(!enabled)}
            className="relative shrink-0 rounded-full border border-white/20 transition disabled:cursor-not-allowed disabled:opacity-50"
            style={{
              backgroundColor: enabled ? "#16a34a" : "#4b5563",
              flex: "0 0 48px",
              height: "26px",
              width: "48px",
            }}
          >
            {busy ? (
              <LoaderCircle
                className="absolute inset-0 m-auto size-4 animate-spin text-white"
                aria-hidden="true"
              />
            ) : (
              <span
                data-personalized-memory-knob
                className="absolute rounded-full bg-white shadow-sm transition-transform"
                style={{
                  backgroundColor: "#ffffff",
                  height: "20px",
                  left: "2px",
                  top: "2px",
                  transform: enabled ? "translateX(22px)" : "translateX(0)",
                  width: "20px",
                }}
              />
            )}
          </button>
        </div>
        <div className="flex items-center justify-between gap-4 border-t border-border px-4 py-4">
          <div>
            <p className="font-semibold">{t("chat.personalized.deleteTitle")}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {`${memoryCount} ${t("chat.personalized.memoryCount")}`}
            </p>
          </div>
          <button
            type="button"
            disabled={busy || memoryCount === 0}
            onClick={onDelete}
            className="rounded-md bg-destructive/15 px-3 py-1.5 text-sm font-medium text-destructive transition hover:bg-destructive/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t("chat.personalized.delete")}
          </button>
        </div>
        {error ? (
          <p role="alert" className="border-t border-border px-4 py-3 text-sm text-destructive">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
