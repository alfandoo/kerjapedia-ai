"use client";

import type { KeyboardEvent, RefObject } from "react";

import { Send, Square } from "lucide-react";

type ChatComposerProps = {
  question: string;
  loading: boolean;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  onQuestionChange: (question: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
};

export function ChatComposer({
  question,
  loading,
  inputRef,
  onQuestionChange,
  onSubmit,
  onCancel,
}: ChatComposerProps) {
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <form
      className="relative z-10 mx-auto mb-4 w-full max-w-[800px] px-4 max-[760px]:px-3"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label
        htmlFor="question-input"
        className="sr-only"
      >
        Ketik pertanyaan Anda
      </label>
      <div className="relative rounded-2xl border border-[#dce4df] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04)] transition focus-within:border-emas/50 focus-within:shadow-[0_0_0_3px_rgba(201,162,39,0.08)]">
        <textarea
          ref={inputRef}
          id="question-input"
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Tanyakan regulasi ketenagakerjaan…"
          maxLength={2000}
          rows={2}
          disabled={loading}
          className="w-full resize-none rounded-2xl bg-transparent p-4 pb-11 text-[14px] leading-[1.65] text-tinta outline-none placeholder:text-[#9ca39e] disabled:cursor-not-allowed disabled:opacity-50"
        />
        <div className="absolute bottom-0 inset-x-0 flex items-center justify-between px-4 pb-3">
          <span className="text-[10px] font-medium tabular-nums text-[#b0b8b3]">
            {question.length}/2000
          </span>
          {loading ? (
            <button
              className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-[#e8e4dc] bg-white px-3.5 text-xs font-semibold text-[#68736c] transition hover:bg-[#f5f3ef] hover:text-[#26312b]"
              type="button"
              onClick={onCancel}
            >
              <Square className="size-4" />
              Batalkan
            </button>
          ) : (
            <button
              className="inline-flex h-9 items-center gap-1.5 rounded-xl bg-javanese px-4 text-xs font-semibold text-white transition hover:bg-forest disabled:cursor-not-allowed disabled:bg-[#c9d3cb]"
              type="submit"
              disabled={!question.trim()}
            >
              <Send className="size-4" />
              Kirim
            </button>
          )}
        </div>
      </div>
    </form>
  );
}
