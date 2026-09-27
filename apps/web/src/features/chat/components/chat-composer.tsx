"use client";

import { useLayoutEffect, type KeyboardEvent, type RefObject } from "react";

import { ChevronDown, Gauge, ListChecks, ScanSearch, Send, Square } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useSettings } from "@/features/settings";
import type { ReasoningMode } from "../types";

type ChatComposerProps = {
  question: string;
  loading: boolean;
  disabled?: boolean;
  quotaBlocked?: boolean;
  reasoningMode: ReasoningMode;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  onQuestionChange: (question: string) => void;
  onReasoningModeChange: (mode: ReasoningMode) => void;
  onSubmit: () => void;
  onCancel: () => void;
};

export function ChatComposer({
  question,
  loading,
  disabled = false,
  quotaBlocked = false,
  reasoningMode,
  inputRef,
  onQuestionChange,
  onReasoningModeChange,
  onSubmit,
  onCancel,
}: ChatComposerProps) {
  const { t: translate } = useSettings();
  const ModeIcon = { fast: Gauge, standard: ListChecks, deep: ScanSearch }[reasoningMode];
  const characterCount = new Intl.NumberFormat("id-ID").format(question.length);
  useLayoutEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
    input.style.overflowY = input.scrollHeight > 180 ? "auto" : "hidden";
  }, [inputRef, question]);

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <form
      className="chat-composer-form relative z-10 mx-auto mb-2 w-full max-w-[800px] px-4 max-[760px]:mb-2 max-[760px]:px-3"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label htmlFor="question-input" className="sr-only">
        {translate("chat.inputLabel")}
      </label>
      <div className="chat-composer-surface relative rounded-2xl border border-[#d8e8dc] bg-white shadow-[0_1px_3px_rgba(23,107,58,0.08)]">
        <textarea
          ref={inputRef}
          id="question-input"
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={translate("chat.placeholder")}
          maxLength={2000}
          rows={1}
          disabled={loading || disabled}
          className="min-h-[88px] max-h-[180px] w-full resize-none rounded-2xl bg-transparent p-3.5 pb-14 text-[16px] leading-[1.55] text-tinta outline-none focus-visible:outline-2 focus-visible:outline-offset-[-3px] focus-visible:outline-javanese dark:focus-visible:outline-[#84c99b] placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50 min-[761px]:text-[14px]"
        />
        <div className="absolute bottom-0 inset-x-0 flex items-center justify-between gap-2 px-4 pb-3">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label={translate("chat.mode.label")}
                disabled={loading || disabled}
                className="inline-flex min-h-11 items-center gap-1 rounded-lg border border-[#b7d3c0] bg-white px-1.5 text-xs font-semibold text-[#31523d] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-javanese disabled:cursor-not-allowed disabled:opacity-50 min-[761px]:min-h-9 min-[761px]:text-[11px]"
              >
                <ModeIcon aria-hidden="true" className="size-3.5" />
                {translate(`chat.mode.${reasoningMode}`)}
                <ChevronDown aria-hidden="true" className="size-3 max-[420px]:hidden" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              side="top"
              align="start"
              sideOffset={8}
              className="w-[min(288px,calc(100vw-24px))] p-1.5"
            >
              <DropdownMenuRadioGroup
                value={reasoningMode}
                onValueChange={(value) => onReasoningModeChange(value as ReasoningMode)}
              >
                {(["fast", "standard", "deep"] as const).map((mode) => {
                  const Icon = { fast: Gauge, standard: ListChecks, deep: ScanSearch }[mode];
                  return (
                    <DropdownMenuRadioItem
                      key={mode}
                      value={mode}
                      className="items-start gap-2 rounded-md px-2 py-2.5"
                    >
                      <Icon aria-hidden="true" className="mt-0.5 size-4 text-javanese" />
                      <span className="flex flex-col gap-0.5">
                        <span className="font-semibold">{translate(`chat.mode.${mode}`)}</span>
                        <span className="text-xs font-normal leading-snug text-muted-foreground">
                          {translate(`chat.mode.${mode}.description`)}
                        </span>
                      </span>
                    </DropdownMenuRadioItem>
                  );
                })}
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
          <div className="flex shrink-0 items-center gap-2">
            {!loading ? (
              <span className="whitespace-nowrap text-[11px] tabular-nums text-muted-foreground">
                {characterCount}/2.000 {translate("chat.input.characters")}
              </span>
            ) : null}
            {loading ? (
              <button
                className="inline-flex min-h-11 items-center gap-1.5 rounded-xl border border-[#d8e8dc] bg-white px-3.5 text-xs font-semibold text-muted-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-javanese"
                type="button"
                onClick={onCancel}
              >
                <Square className="size-4" />
                {translate("chat.cancel")}
              </button>
            ) : (
              <button
                className="chat-no-hover inline-flex min-h-11 items-center gap-1.5 rounded-xl bg-javanese px-4 max-[420px]:px-3 text-xs font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-javanese disabled:cursor-not-allowed disabled:bg-[#b8cfc0] disabled:text-tinta"
                type="submit"
                disabled={!question.trim() || disabled || quotaBlocked}
              >
                <Send className="size-4" />
                {translate("chat.send")}
              </button>
            )}
          </div>
        </div>
      </div>
    </form>
  );
}
