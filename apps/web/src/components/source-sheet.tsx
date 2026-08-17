"use client";

import { useEffect, useRef, type KeyboardEvent as ReactKeyboardEvent } from "react";

import { SourcePanel } from "./source-panel";
import type { Citation } from "@/lib/types";

type SourceSheetProps = {
  open: boolean;
  citations: Citation[];
  question: string;
  onClose: () => void;
};

export function SourceSheet({ open, citations, question, onClose }: SourceSheetProps) {
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
        className="absolute inset-0 w-full border-0 bg-[rgba(10,28,25,0.5)]"
        aria-label="Tutup panel sumber"
        onClick={onClose}
      />
      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-sheet-title"
        onKeyDown={keepFocusInside}
        className="absolute inset-x-0 bottom-0 max-h-[min(82vh,760px)] w-full overflow-y-auto rounded-t-[20px] bg-white p-5 shadow-[0_-24px_70px_rgba(10,28,25,0.2)] max-[760px]:max-h-[72svh] max-[760px]:rounded-t-[14px] max-[760px]:shadow-[0_-12px_32px_rgba(18,42,31,0.14)] max-[560px]:max-h-[88vh] max-[560px]:p-4"
      >
        <span
          className="mx-auto mb-0.5 mt-1 hidden h-1 w-[42px] rounded-[10px] bg-[#c5cec9] max-[760px]:block"
          aria-hidden="true"
        />
        <div className="mb-3 flex items-center justify-between border-b border-[#dce4df] pb-3.5">
          <div>
            <h2
              id="source-sheet-title"
              className="m-0 font-display text-xl font-semibold text-tinta"
            >
              Sumber dan kutipan
            </h2>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="grid size-[42px] place-items-center rounded-full border border-[#dce4df] bg-[#f6faf9] text-2xl leading-none text-tinta transition hover:border-javanese hover:text-javanese"
            onClick={onClose}
            aria-label="Tutup sumber dan kutipan"
          >
            ×
          </button>
        </div>
        <SourcePanel citations={citations} question={question} />
      </section>
    </div>
  );
}