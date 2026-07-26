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
    <div className="source-sheet-layer">
      <button
        type="button"
        className="source-sheet-backdrop"
        aria-label="Tutup panel sumber"
        onClick={onClose}
      />
      <section
        ref={dialogRef}
        className="source-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-sheet-title"
        onKeyDown={keepFocusInside}
      >
        <span className="source-sheet-handle" aria-hidden="true" />
        <div className="source-sheet-heading">
          <div>
            <h2 id="source-sheet-title">Sumber dan kutipan</h2>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="source-sheet-close"
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
