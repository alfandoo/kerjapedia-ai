"use client";

import { memo, useEffect, useState } from "react";

import { AlertTriangle, Copy, FileText, Pencil, Share2, ThumbsDown, ThumbsUp } from "lucide-react";
import type { ChatMessage } from "../types";
import type { FeedbackIssue, FeedbackRating } from "@/features/chat/api";
import type { TranslationKey } from "@/lib/translations";
import { useSettings } from "@/features/settings";

type FeedbackDetail = {
  issue: FeedbackIssue;
  comment: string;
};

type ConversationThreadProps = {
  messages: ChatMessage[];
  feedback: Record<string, FeedbackRating>;
  onShowSources: (message: ChatMessage) => void;
  onFeedback: (message: ChatMessage, rating: FeedbackRating, detail?: FeedbackDetail) => void;
  onEditMessage: (message: ChatMessage) => void;
};

const FEEDBACK_ISSUE_LABELS: { value: FeedbackIssue; labelKey: TranslationKey }[] = [
  { value: "citation_incorrect", labelKey: "answer.feedbackCitation" },
  { value: "answer_incomplete", labelKey: "answer.feedbackIncomplete" },
  { value: "outdated_regulation", labelKey: "answer.feedbackOutdated" },
  { value: "other", labelKey: "answer.feedbackOther" },
];

const WARNING_LABEL_KEYS: Record<string, TranslationKey> = {
  retrieved_source_status_needs_verification: "answer.warningNeedsVerification",
  retrieved_source_contains_historical_or_revoked_document: "answer.warningHistorical",
  retrieved_source_superseded_by_newer_document: "answer.warningSuperseded",
  retrieved_source_revoked_or_superseded_document: "answer.warningRevoked",
  answer_degraded_extractive: "answer.warningDegradedExtractive",
};

const LEGACY_FALLBACK_WARNING = "groq_answer_fallback_used";

function formatMessageTime(value: string, language: "id" | "en") {
  return new Intl.DateTimeFormat(language === "id" ? "id-ID" : "en-US", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

type AnswerBlock =
  { kind: "paragraph"; text: string } | { kind: "list"; ordered: boolean; items: string[] };

function inlineRendered(text: string) {
  const cleaned = text.replace(/\s+/g, " ").trim();
  return cleaned
    .split(/(\*\*[^*]+\*\*)/g)
    .filter(Boolean)
    .map((part, index) =>
      part.startsWith("**") && part.endsWith("**") ? (
        <strong key={index}>{part.slice(2, -2)}</strong>
      ) : (
        <span key={index}>{part}</span>
      )
    );
}

function answerBlocks(content: string): AnswerBlock[] {
  const blocks: AnswerBlock[] = [];
  let pendingParagraph: string[] = [];
  let listItems: string[] = [];
  let ordered = false;
  let inList = false;

  const flushParagraph = () => {
    if (pendingParagraph.length) {
      const text = pendingParagraph.join(" ").replace(/\s+/g, " ").trim();
      if (text) {
        blocks.push({ kind: "paragraph", text });
      }
      pendingParagraph = [];
    }
  };
  const flushList = () => {
    if (inList) {
      blocks.push({ kind: "list", ordered, items: listItems });
      listItems = [];
      inList = false;
    }
  };

  for (const raw of content.split("\n")) {
    const line = raw.trim();
    if (!line) {
      flushList();
      flushParagraph();
      continue;
    }
    const bulletMatch = line.match(/^(?:[-•∙])\s+(.+)$/);
    const numberMatch = line.match(/^\d+[.)]\s+(.+)$/);
    if (bulletMatch || numberMatch) {
      flushParagraph();
      const isOrdered = Boolean(numberMatch);
      if (inList && ordered !== isOrdered) flushList();
      ordered = isOrdered;
      inList = true;
      const itemText = (bulletMatch ?? numberMatch)![1].replace(/\s+/g, " ").trim();
      listItems.push(itemText);
    } else {
      flushList();
      pendingParagraph.push(line);
    }
  }
  flushList();
  flushParagraph();
  return blocks;
}

const AnswerContent = memo(function AnswerContent({
  content,
  lang,
  streaming,
}: {
  content: string;
  lang: "id" | "en";
  streaming: boolean;
}) {
  const blocks = answerBlocks(content);
  return (
    <div
      lang={lang}
      className="mb-2 mt-1 text-pretty text-[15px] leading-[26px] text-foreground [&_strong]:font-semibold [&_strong]:text-foreground"
    >
      {blocks.map((block, index) =>
        block.kind === "list" ? (
          block.ordered ? (
            <ol
              className="mb-2.5 mt-1.5 max-w-[72ch] list-decimal space-y-1.5 pl-5 marker:text-muted-foreground last:mb-0"
              key={`list-${index}`}
            >
              {block.items.map((item, itemIndex) => (
                <li key={`list-${index}-item-${itemIndex}`} className="pl-0.5">
                  {inlineRendered(item)}
                </li>
              ))}
            </ol>
          ) : (
            <ul
              className="mb-2.5 mt-1.5 max-w-[72ch] list-disc space-y-1.5 pl-5 marker:text-muted-foreground last:mb-0"
              key={`list-${index}`}
            >
              {block.items.map((item, itemIndex) => (
                <li key={`list-${index}-item-${itemIndex}`} className="pl-0.5">
                  {inlineRendered(item)}
                </li>
              ))}
            </ul>
          )
        ) : (
          <p
            className="mb-2.5 max-w-[72ch] break-words text-justify hyphens-auto last:mb-0"
            key={`p-${index}`}
          >
            {inlineRendered(block.text)}
          </p>
        )
      )}
      {streaming ? (
        <span
          className="ml-[3px] inline-block h-[1.05em] w-0.5 bg-javanese align-[-0.14em] [animation:streaming-cursor-blink_0.8s_steps(1)_infinite]"
          aria-hidden="true"
        />
      ) : null}
    </div>
  );
});

function isUnavailableAnswer(message: ChatMessage) {
  return (
    message.answer?.answer_status === "temporarily_unavailable" ||
    message.answer?.warnings?.includes(LEGACY_FALLBACK_WARNING) === true
  );
}

export function ConversationThread({
  messages,
  feedback,
  onShowSources,
  onFeedback,
  onEditMessage,
}: ConversationThreadProps) {
  const { t: translate, resolvedLanguage } = useSettings();
  const [actionStatus, setActionStatus] = useState<{ messageId: string; text: string } | null>(
    null
  );
  const [feedbackPanel, setFeedbackPanel] = useState<{ messageId: string } | null>(null);
  const [issueSelection, setIssueSelection] = useState<FeedbackIssue | null>(null);
  const [issueComment, setIssueComment] = useState("");

  useEffect(() => {
    if (!actionStatus) return;
    const timer = window.setTimeout(() => setActionStatus(null), 1800);
    return () => window.clearTimeout(timer);
  }, [actionStatus]);

  async function copyText(
    messageId: string,
    content: string,
    successText = translate("answer.copied")
  ) {
    try {
      await navigator.clipboard.writeText(content);
      setActionStatus({ messageId, text: successText });
    } catch {
      setActionStatus({ messageId, text: translate("answer.copyFailed") });
    }
  }

  async function shareAnswer(message: ChatMessage) {
    const displayContent = isUnavailableAnswer(message)
      ? translate("answer.temporarilyUnavailable")
      : message.content;
    const shareData = {
      title: translate("answer.shareTitle"),
      text: displayContent,
    };
    if (navigator.share) {
      try {
        await navigator.share(shareData);
        setActionStatus({ messageId: message.id, text: translate("answer.shared") });
        return;
      } catch (error) {
        if ((error as DOMException).name === "AbortError") return;
      }
    }
    await copyText(message.id, displayContent, translate("answer.shareCopied"));
  }

  return (
    <div
      className="mx-auto w-full max-w-[760px]"
      aria-live="polite"
      aria-label={translate("answer.conversationLabel")}
    >
      {messages.map((message) => {
        if (message.role === "user") {
          return (
            <article
              className="mb-5 flex flex-col items-end pl-[68px] max-[760px]:pl-0"
              key={message.id}
            >
              <p className="user-message-bubble max-w-[min(82%,560px)] rounded-[18px_18px_4px_18px] border border-transparent bg-javanese px-4 py-[11px] text-[13px] leading-relaxed text-white">
                {message.content}
              </p>
              <div className="mt-1 flex min-h-[28px] items-center justify-end gap-1">
                <time
                  className="font-mono text-[10px] leading-normal tabular-nums text-muted-foreground"
                  title={formatMessageTime(message.createdAt, resolvedLanguage)}
                >
                  {formatMessageTime(message.createdAt, resolvedLanguage)}
                </time>
                <div className="flex min-h-7 items-center gap-0.5">
                  <button
                    type="button"
                    className="grid size-8 place-items-center rounded-lg border border-transparent text-muted-foreground transition hover:bg-accent hover:text-foreground"
                    aria-label={translate("answer.editMessage")}
                    title={translate("answer.editMessage")}
                    onClick={() => onEditMessage(message)}
                  >
                    <Pencil className="size-[16px]" />
                  </button>
                  <button
                    type="button"
                    className="grid size-8 place-items-center rounded-lg border border-transparent text-muted-foreground transition hover:bg-accent hover:text-foreground"
                    aria-label={translate("answer.copyMessage")}
                    title={translate("answer.copyMessage")}
                    onClick={() => void copyText(message.id, message.content)}
                  >
                    <Copy className="size-[16px]" />
                  </button>
                  {actionStatus?.messageId === message.id ? (
                    <span
                      className="mx-1 whitespace-nowrap text-[11px] text-muted-text"
                      role="status"
                    >
                      {actionStatus.text}
                    </span>
                  ) : null}
                </div>
              </div>
            </article>
          );
        }

        const displayContent = isUnavailableAnswer(message)
          ? translate("answer.temporarilyUnavailable")
          : message.content;
        return (
          <article className="mb-6" key={message.id}>
            <div className="max-w-[74ch]">
              {message.status && !message.content ? (
                <div
                  className="inline-flex min-h-9 items-center gap-2 text-sm text-muted-foreground"
                  role="status"
                  aria-live="polite"
                >
                  <span
                    className="size-2 rounded-full bg-javanese [animation:editorial-thinking-pulse_1.4s_ease-in-out_infinite]"
                    aria-hidden="true"
                  />
                  <span>{message.status}</span>
                </div>
              ) : (
                <AnswerContent
                  content={displayContent}
                  lang={resolvedLanguage}
                  streaming={Boolean(message.streaming)}
                />
              )}
              {message.answer?.citations.length ? (
                <button
                  className="mt-2 inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-transparent bg-javanese px-3 text-[11px] font-semibold text-white transition hover:bg-forest"
                  type="button"
                  onClick={() => onShowSources(message)}
                >
                  <FileText className="size-[16px]" />
                  {message.answer.citations.length} {translate("answer.officialSources")}
                  <span aria-hidden="true" className="text-[10px]">
                    →
                  </span>
                </button>
              ) : null}
              {message.answer?.refusal_reason ? (
                <div className="mt-3 flex items-start gap-2.5 rounded-lg border border-amber/30 bg-amber-soft p-3 text-xs leading-relaxed text-amber">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  <span>
                    {message.answer.refusal_reason === "out_of_scope_query"
                      ? translate("answer.outOfScope")
                      : message.answer.refusal_reason === "prompt_injection_detected"
                        ? translate("answer.promptBlocked")
                        : translate("answer.insufficientSources")}
                  </span>
                </div>
              ) : null}
              {message.answer?.clarification_question ? (
                <div className="mt-3 flex items-start gap-2.5 rounded-lg border border-amber/30 bg-amber-soft p-3 text-xs leading-relaxed text-amber">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  <span>{message.answer.clarification_question}</span>
                </div>
              ) : null}
              {message.answer?.warnings?.length ? (
                <div className="mt-3 grid gap-1.5">
                  {message.answer.warnings.map((code) => {
                    const labelKey = WARNING_LABEL_KEYS[code];
                    if (!labelKey) return null;
                    return (
                      <div
                        className="flex items-start gap-2.5 rounded-lg border border-amber/30 bg-amber-soft p-3 text-xs leading-relaxed text-amber"
                        key={code}
                      >
                        <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                        <span>{translate(labelKey)}</span>
                      </div>
                    );
                  })}
                </div>
              ) : null}
              {!message.streaming ? (
                <footer className="mt-2 flex min-h-8 items-center text-[11px] text-muted-foreground">
                  <div className="flex gap-0.5">
                    <button
                      type="button"
                      className="grid size-8 place-items-center rounded-lg border border-transparent text-muted-foreground transition hover:bg-accent hover:text-foreground"
                      aria-label={translate("answer.copyAnswer")}
                      title={translate("answer.copyAnswer")}
                      onClick={() => void copyText(message.id, displayContent)}
                    >
                      <Copy className="size-[16px]" />
                    </button>
                    <button
                      type="button"
                      className={`grid size-8 place-items-center rounded-lg border transition ${
                        feedback[message.id] === "helpful"
                          ? "border-javanese/40 bg-javanese/10 text-javanese dark:text-[#82d5a9]"
                          : "border-transparent text-muted-foreground hover:bg-accent hover:text-foreground"
                      }`}
                      aria-label={translate("answer.helpful")}
                      aria-pressed={feedback[message.id] === "helpful"}
                      onClick={() => onFeedback(message, "helpful")}
                    >
                      <ThumbsUp className="size-[16px]" />
                    </button>
                    <button
                      type="button"
                      className={`grid size-8 place-items-center rounded-lg border transition ${
                        feedback[message.id] === "not_helpful"
                          ? "border-javanese/40 bg-javanese/10 text-javanese dark:text-[#82d5a9]"
                          : "border-transparent text-muted-foreground hover:bg-accent hover:text-foreground"
                      }`}
                      aria-label={translate("answer.notHelpful")}
                      aria-pressed={feedback[message.id] === "not_helpful"}
                      onClick={() => {
                        if (feedbackPanel?.messageId === message.id) {
                          setFeedbackPanel(null);
                        } else {
                          setFeedbackPanel({ messageId: message.id });
                          setIssueSelection(null);
                          setIssueComment("");
                        }
                      }}
                    >
                      <ThumbsDown className="size-[16px]" />
                    </button>
                    <button
                      type="button"
                      className="grid size-8 place-items-center rounded-lg border border-transparent text-muted-foreground transition hover:bg-accent hover:text-foreground"
                      aria-label={translate("answer.shareAnswer")}
                      title={translate("answer.shareAnswer")}
                      onClick={() => void shareAnswer(message)}
                    >
                      <Share2 className="size-[16px]" />
                    </button>
                  </div>
                  {actionStatus?.messageId === message.id ? (
                    <span
                      className="mx-1 whitespace-nowrap text-[11px] text-muted-text"
                      role="status"
                    >
                      {actionStatus.text}
                    </span>
                  ) : null}
                </footer>
              ) : null}
            </div>
            {feedbackPanel?.messageId === message.id ? (
              <div
                className="mt-3 grid max-w-[420px] gap-2.5 rounded-xl border border-border bg-secondary p-3.5"
                role="group"
                aria-label={translate("answer.feedbackQuestion")}
              >
                <p className="text-[13px] font-semibold text-foreground">
                  {translate("answer.feedbackQuestion")}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {FEEDBACK_ISSUE_LABELS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={`rounded-full border px-2.5 py-1.5 text-xs transition hover:border-javanese hover:text-javanese ${
                        issueSelection === option.value
                          ? "border-javanese bg-accent font-semibold text-javanese"
                          : "border-border bg-background text-foreground"
                      }`}
                      aria-pressed={issueSelection === option.value}
                      onClick={() => setIssueSelection(option.value)}
                    >
                      {translate(option.labelKey)}
                    </button>
                  ))}
                </div>
                <textarea
                  className="w-full resize-y rounded-lg border border-border bg-background p-2.5 text-[13px] leading-normal text-foreground outline-none transition placeholder:text-muted-foreground focus:border-javanese focus:outline-2 focus:outline-offset-1 focus:outline-javanese/40"
                  rows={3}
                  maxLength={1000}
                  placeholder={translate("answer.feedbackOptional")}
                  value={issueComment}
                  onChange={(event) => setIssueComment(event.target.value)}
                />
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    className="rounded-lg px-3 py-[7px] text-[13px] text-muted-foreground transition hover:bg-accent hover:text-foreground"
                    onClick={() => setFeedbackPanel(null)}
                  >
                    {translate("answer.feedbackCancel")}
                  </button>
                  <button
                    type="button"
                    className="rounded-lg bg-javanese px-3.5 py-[7px] text-[13px] font-semibold text-white transition hover:bg-forest disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={!issueSelection}
                    onClick={() => {
                      const detail: FeedbackDetail | undefined = issueSelection
                        ? { issue: issueSelection, comment: issueComment.trim() }
                        : undefined;
                      onFeedback(message, "not_helpful", detail);
                      setFeedbackPanel(null);
                    }}
                  >
                    {translate("answer.feedbackSubmit")}
                  </button>
                </div>
              </div>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
