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
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <form
      className="editorial-composer"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label htmlFor="question-input">Ketik pertanyaan Anda</label>
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
      />
      <span className="editorial-composer-hint">
        Ctrl + Enter untuk kirim · {question.length}/2000
      </span>
      {loading ? (
        <button className="editorial-cancel-button" type="button" onClick={onCancel}>
          <StopIcon className="icon" />
          Batalkan
        </button>
      ) : (
        <button className="editorial-send-button" type="submit" disabled={!question.trim()}>
          <SendIcon className="icon" />
          Kirim
        </button>
      )}
    </form>
  );
}
