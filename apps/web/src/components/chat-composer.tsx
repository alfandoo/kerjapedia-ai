"use client";

import type { KeyboardEvent, RefObject } from "react";

import { SendIcon, StopIcon } from "./icons";

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
      className="relative z-10 mx-auto w-full max-w-[800px]"
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
        className="w-full resize-none rounded-2xl border border-[#dce4df] bg-white p-4 pb-11 text-sm leading-[1.65] text-tinta shadow-sm outline-none transition placeholder:text-[#8a928d] focus:border-javanese focus:outline-2 focus:outline-offset-1 focus:outline-javanese/40 disabled:cursor-not-allowed disabled:bg-[#f5f7f5]"
      />
      <span className="pointer-events-none absolute bottom-[14px] left-[18px] text-[10px] font-medium tracking-wide text-[#8a928d]">
        {question.length}/2000
      </span>
      {loading ? (
        <button
          className="absolute bottom-[10px] right-[12px] grid h-[38px] shrink-0 cursor-pointer items-center gap-1.5 rounded-xl bg-white px-3.5 text-xs font-semibold text-[#68736c] transition hover:bg-[#f2f5f2] hover:text-[#26312b]"
          type="button"
          onClick={onCancel}
        >
          <StopIcon className="size-[18px] [stroke-width:1.8]" />
          Batalkan
        </button>
      ) : (
        <button
          className="absolute bottom-[10px] right-[12px] grid h-[38px] shrink-0 cursor-pointer items-center gap-1.5 rounded-xl bg-javanese px-3.5 text-xs font-semibold whitespace-nowrap text-white transition hover:bg-forest disabled:cursor-not-allowed disabled:bg-[#c9d3cb]"
          type="submit"
          disabled={!question.trim()}
        >
          <SendIcon className="size-[18px] [stroke-width:1.8]" />
          Kirim
        </button>
      )}
    </form>
  );
}
