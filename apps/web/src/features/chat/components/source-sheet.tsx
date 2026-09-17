"use client";

import { useEffect, useRef, type KeyboardEvent as ReactKeyboardEvent } from "react";

import { SourcePanel } from "./source-panel";
import { useSettings } from "@/features/settings";
import type { Citation } from "@/features/chat/types";
import type { FeedbackRating } from "@/features/chat/api";

type SourceSheetProps = {
  open: boolean;
  citations: Citation[];
  rating?: FeedbackRating | null;
  feedbackError?: string | null;
  isSubmitting?: boolean;
  onRate?: (rating: FeedbackRating) => void;
  onClose: () => void;
};

export function SourceSheet({
  open,
  citations,
  rating = null,
  feedbackError = null,
  isSubmitting = false,
  onRate,
  onClose,
}: SourceSheetProps) {
  const { t: translate } = useSettings();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    window.addEventListener("keydown", handleEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleEscape);
    };
  }, [onClose, open]);

  if (!open) return null;

  function keepFocusInside(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable?.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div className="fixed inset-0 z-[110]">
      <button
        type="button"
        className="absolute inset-0 w-full border-0 bg-black/50 backdrop-blur-[1px]"
        aria-label={translate("source.closePanel")}
        onClick={onClose}
      />
      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-sheet-title"
        onKeyDown={keepFocusInside}
        className="absolute inset-x-0 bottom-0 max-h-[min(82vh,760px)] w-full overflow-y-auto rounded-t-[20px] border-t border-border bg-background shadow-[0_-24px_70px_rgba(0,0,0,0.22)] max-[760px]:max-h-[72svh] max-[760px]:rounded-t-[14px] max-[760px]:shadow-[0_-12px_32px_rgba(0,0,0,0.2)] max-[560px]:max-h-[88vh]"
      >
        <span
          className="mx-auto mb-0.5 mt-3 hidden h-1 w-[42px] rounded-full bg-muted-foreground/35 max-[760px]:block"
          aria-hidden="true"
        />
        <div className="sticky top-0 z-10 flex min-h-[58px] items-center justify-between border-b border-border bg-background px-5 py-2 max-[560px]:px-4">
          <div>
            <h2 id="source-sheet-title" className="m-0 text-[15px] font-semibold text-foreground">
              {translate("source.title")}
            </h2>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="grid size-11 place-items-center rounded-lg text-2xl leading-none text-muted-foreground transition hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-javanese"
            onClick={onClose}
            aria-label={translate("source.close")}
          >
            ×
          </button>
        </div>
        <SourcePanel
          citations={citations}
          rating={rating}
          feedbackError={feedbackError}
          isSubmitting={isSubmitting}
          onRate={onRate}
        />
      </section>
    </div>
  );
}
