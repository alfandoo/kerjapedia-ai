"use client";

import { readPreference, writePreference } from "@/lib/preference-cookie";
import { Skeleton } from "@/components/ui/skeleton";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ChatComposer } from "./chat-composer";
import { PersonalizedControls } from "./personalized-controls";
import type { ChatMessage, ReasoningMode, TokenUsageSnapshot } from "../types";
import { ChatWorkspaceShell } from "./chat-workspace-shell";
import { ConversationThread } from "./conversation-thread";
import { AlertTriangle } from "lucide-react";
import { SourcePanel } from "./source-panel";
import { SourceSheet } from "./source-sheet";
import { useConversationHistory } from "@/features/chat/use-conversation-history";
import { useSettings } from "@/features/settings";
import { useStoredSession } from "@/features/auth";
import {
  askQuestionStream,
  deleteMemories,
  fetchMemorySettings,
  updateMemorySettings,
  DailyTokenQuotaError,
  fetchTokenUsage,
  claimGuestConversation,
  deleteConversation,
  fetchConversation,
  fetchConversations,
  renameConversation,
  submitFeedback,
} from "@/features/chat/api";
import type { Citation } from "@/features/chat/types";
import type { TranslationKey } from "@/lib/translations";

const SIDEBAR_STORAGE_KEY = "kerjapedia.chat.sidebar.v1";
const REASONING_MODE_STORAGE_KEY = "kerjapedia.chat.reasoning-mode.v1";
const REASONING_MODES = new Set<ReasoningMode>(["fast", "standard", "deep"]);

const STREAM_STATUS_KEYS: Record<string, TranslationKey> = {
  analyzing_question: "chat.loading.analyzing",
  "Menganalisis pertanyaan": "chat.loading.analyzing",
  checking_request_safety: "chat.loading.security",
  "Memeriksa keamanan permintaan": "chat.loading.security",
  searching_official_regulations: "chat.loading.searching",
  "Menelusuri regulasi resmi": "chat.loading.searching",
  composing_grounded_answer: "chat.loading.composing",
  "Menyusun jawaban berdasarkan sumber": "chat.loading.composing",
};

export function EditorialChatExperience() {
  const {
    conversations,
    setConversations,
    historyLoading,
    historyError,
    retryHistory,
    setHistoryLoading,
  } = useConversationHistory();
  const { t: translate } = useSettings();
  const session = useStoredSession();
  const [question, setQuestion] = useState("");
  const [reasoningMode, setReasoningMode] = useState<ReasoningMode>("standard");
  const [personalizedMode, setPersonalizedModeState] = useState(false);
  const [memoryCount, setMemoryCount] = useState(0);
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [activeSourceMessageId, setActiveSourceMessageId] = useState<string | null>(null);
  const [sourceFeedbackError, setSourceFeedbackError] = useState<string | null>(null);
  const [isSourceSubmitting, setIsSourceSubmitting] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSourceSheetOpen, setIsSourceSheetOpen] = useState(false);
  const [isSourceDrawerOpen, setIsSourceDrawerOpen] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [isSidebarExpanded, setIsSidebarExpanded] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [usage, setUsage] = useState<TokenUsageSnapshot | null>(null);
  const [usageStatus, setUsageStatus] = useState<"loading" | "ready" | "error">("loading");
  const [quotaBlocked, setQuotaBlocked] = useState(false);
  const [quotaStoppedDuringProcessing, setQuotaStoppedDuringProcessing] = useState(false);
  const [quotaResetAt, setQuotaResetAt] = useState<string | null>(null);
  const [pendingClaimId, setPendingClaimId] = useState<string | null>(null);
  const [claimErrorId, setClaimErrorId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Record<string, "helpful" | "not_helpful">>({});
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const conversationScrollRef = useRef<HTMLDivElement>(null);
  const conversationEndRef = useRef<HTMLDivElement>(null);
  const openedFromUrlRef = useRef(false);
  const sourceTriggerRef = useRef<HTMLElement | null>(null);
  const streamingMessageRef = useRef<string | null>(null);
  const shouldStickToBottomRef = useRef(true);

  const closeSourceSheet = useCallback(() => {
    setIsSourceSheetOpen(false);
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }, []);
  const refreshUsage = useCallback(async () => {
    setUsageStatus("loading");
    try {
      const current = await fetchTokenUsage();
      setUsage(current);
      setUsageStatus("ready");
      if (current.remaining_tokens <= 0) setQuotaBlocked(true);
    } catch {
      setUsage(null);
      setUsageStatus("error");
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void refreshUsage(), 0);
    return () => window.clearTimeout(timer);
  }, [refreshUsage]);

  useEffect(() => {
    const resetAt = quotaResetAt ?? usage?.reset_at;
    if (!quotaBlocked || !resetAt) return;
    const delay = Math.max(1000, new Date(resetAt).getTime() - Date.now() + 1000);
    const timer = window.setTimeout(
      () => {
        setQuotaBlocked(false);
        setQuotaStoppedDuringProcessing(false);
        setQuotaResetAt(null);
        void refreshUsage();
      },
      Math.min(delay, 2_147_483_647)
    );
    return () => window.clearTimeout(timer);
  }, [quotaBlocked, quotaResetAt, refreshUsage, usage?.reset_at]);

  const refreshHistory = useCallback(
    async (signal?: AbortSignal) => {
      setConversations(await fetchConversations(signal));
    },
    [setConversations]
  );

  useEffect(() => {
    if (!pendingClaimId || isLoading) return;
    let active = true;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 8000);
    void claimGuestConversation(pendingClaimId, controller.signal)
      .then((claimed) => {
        if (!active) return;
        setConversations((current) => [
          claimed,
          ...current.filter((item) => item.conversation_id !== claimed.conversation_id),
        ]);
        setClaimErrorId(null);
        setPendingClaimId(null);
        void refreshHistory().catch(() => {});
        void refreshUsage();
      })
      .catch(() => {
        if (!active) return;
        setClaimErrorId(pendingClaimId);
        setPendingClaimId(null);
      })
      .finally(() => window.clearTimeout(timeoutId));
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timeoutId);
    };
  }, [pendingClaimId, isLoading, refreshHistory, refreshUsage, setConversations]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setIsSidebarExpanded(readPreference(SIDEBAR_STORAGE_KEY) !== "collapsed");
      const storedMode = readPreference(REASONING_MODE_STORAGE_KEY);
      if (storedMode && REASONING_MODES.has(storedMode as ReasoningMode)) {
        setReasoningMode(storedMode as ReasoningMode);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!session) {
      setPersonalizedModeState(false);
      setMemoryCount(0);
      return;
    }
    let active = true;
    void fetchMemorySettings()
      .then((settings) => {
        if (!active) return;
        setPersonalizedModeState(settings.enabled);
        setMemoryCount(settings.memory_count);
      })
      .catch(() => {
        if (active) setProfileError(translate("chat.personalized.loadError"));
      });
    return () => {
      active = false;
    };
  }, [session, translate]);

  async function handlePersonalizedToggle(enabled: boolean) {
    if (!session || isLoading || profileBusy) return;
    setProfileError(null);
    setProfileBusy(true);
    try {
      const settings = await updateMemorySettings(enabled);
      setPersonalizedModeState(settings.enabled);
      setMemoryCount(settings.memory_count);
    } catch {
      setProfileError(translate("chat.personalized.modeError"));
    } finally {
      setProfileBusy(false);
    }
  }

  async function handleDeleteMemories() {
    if (!window.confirm(translate("chat.personalized.deleteConfirm"))) return;
    setProfileError(null);
    setProfileBusy(true);
    try {
      await deleteMemories();
      setMemoryCount(0);
    } catch {
      setProfileError(translate("chat.personalized.deleteError"));
    } finally {
      setProfileBusy(false);
    }
  }

  const latestMessageContent = messages.at(-1)?.content ?? "";

  useEffect(() => {
    if ((messages.length === 0 && !isLoading) || !shouldStickToBottomRef.current) return;
    const scrollRegion = conversationScrollRef.current;
    if (!scrollRegion) return;

    const frame = window.requestAnimationFrame(() => {
      scrollRegion.scrollTop = scrollRegion.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [isLoading, latestMessageContent, messages.length]);

  function handleConversationScroll() {
    const scrollRegion = conversationScrollRef.current;
    if (!scrollRegion) return;
    const distanceFromBottom =
      scrollRegion.scrollHeight - scrollRegion.scrollTop - scrollRegion.clientHeight;
    shouldStickToBottomRef.current = distanceFromBottom < 96;
  }

  function stopRequest() {
    abortRef.current?.abort();
    abortRef.current = null;
    const messageId = streamingMessageRef.current;
    if (messageId) {
      setMessages((current) =>
        current.map((message) =>
          message.id === messageId ? { ...message, streaming: false, status: undefined } : message
        )
      );
    }
    streamingMessageRef.current = null;
    setIsLoading(false);
    setError("Respons dihentikan. Anda dapat melanjutkan dengan pertanyaan baru.");
  }
  function showSources(message: ChatMessage) {
    if (!message.answer) return;
    sourceTriggerRef.current = document.activeElement as HTMLElement | null;
    setCitations(message.answer.citations);
    setActiveSourceMessageId(message.id);
    setSourceFeedbackError(null);
    setIsMobileSidebarOpen(false);
    if (window.matchMedia("(max-width: 1180px)").matches) {
      setIsSourceSheetOpen(true);
      setIsSourceDrawerOpen(false);
    } else {
      setIsSourceDrawerOpen(true);
    }
  }
  const handleConversationSelect = useCallback(
    async (nextId: string) => {
      if (isLoading || nextId === conversationId) return;
      setError(null);
      setHistoryLoading(true);
      try {
        const detail = await fetchConversation(nextId);
        const nextMessages = detail.messages.flatMap<ChatMessage>((message, index) => {
          if (message.role !== "user" && message.role !== "assistant") return [];
          return [
            {
              id: `${detail.conversation_id}-${index}`,
              role: message.role,
              content: message.content,
              answer: message.metadata.answer,
              createdAt: message.created_at,
            },
          ];
        });
        const latest = [...nextMessages].reverse().find((item) => item.answer)?.answer;
        const latestMessageId = [...nextMessages].reverse().find((item) => item.answer)?.id ?? null;
        shouldStickToBottomRef.current = true;
        setConversationId(detail.conversation_id);
        setMessages(nextMessages);
        setCitations(latest?.citations ?? []);
        setActiveSourceMessageId(latestMessageId);
        setSourceFeedbackError(null);
        setIsSourceSheetOpen(false);
        setIsSourceDrawerOpen(false);
      } catch {
        setError(translate("chat.error.generic"));
      } finally {
        setHistoryLoading(false);
      }
    },
    [conversationId, isLoading, setHistoryLoading, translate]
  );

  useEffect(() => {
    if (openedFromUrlRef.current) return;
    const requestedId = new URLSearchParams(window.location.search).get("conversation");
    if (!requestedId) return;
    const timer = window.setTimeout(() => {
      if (openedFromUrlRef.current) return;
      openedFromUrlRef.current = true;
      void handleConversationSelect(requestedId);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [handleConversationSelect]);

  function handleNewConversation() {
    if (isLoading) stopRequest();
    setPendingClaimId(null);
    setClaimErrorId(null);
    setConversationId(null);
    setPersonalizedModeState(false);
    setMessages([]);
    setCitations([]);
    setActiveSourceMessageId(null);
    setSourceFeedbackError(null);
    setError(null);
    setIsSourceSheetOpen(false);
    setIsSourceDrawerOpen(false);
    shouldStickToBottomRef.current = true;
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }
  async function handleConversationRename(id: string, title: string) {
    setError(null);
    try {
      const updated = await renameConversation(id, title);
      setConversations((current) =>
        current.map((item) => (item.conversation_id === id ? updated : item))
      );
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  }
  async function handleConversationDelete(id: string) {
    setError(null);
    try {
      await deleteConversation(id);
      setConversations((current) => current.filter((item) => item.conversation_id !== id));
      if (id === conversationId) handleNewConversation();
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  }
  async function handleSubmit(nextQuestion = question) {
    const trimmed = nextQuestion.trim();
    if (!trimmed || isLoading || pendingClaimId || claimErrorId || quotaBlocked) return;
    setError(null);
    setQuestion("");
    setIsLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const userMessageId = crypto.randomUUID();
    const assistantMessageId = crypto.randomUUID();
    streamingMessageRef.current = assistantMessageId;
    shouldStickToBottomRef.current = true;
    setMessages((current) => [
      ...current,
      {
        id: userMessageId,
        role: "user",
        content: trimmed,
        createdAt: new Date().toISOString(),
      },
      {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        createdAt: new Date().toISOString(),
        streaming: true,
        status: translate("chat.loading.analyzing"),
      },
    ]);
    try {
      const response = await askQuestionStream(
        trimmed,
        conversationId,
        controller.signal,
        {
          onStart: setConversationId,
          onThinking: (status) => {
            const statusKey = STREAM_STATUS_KEYS[status] ?? "chat.loading.title";
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantMessageId
                  ? { ...message, status: translate(statusKey) }
                  : message
              )
            );
          },
          onDelta: (content) =>
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantMessageId
                  ? { ...message, content, status: undefined }
                  : message
              )
            ),
        },
        reasoningMode,
        personalizedMode
      );
      setConversationId(response.conversation_id);
      setCitations(response.answer.citations);
      setActiveSourceMessageId(assistantMessageId);
      setSourceFeedbackError(null);
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content: response.answer.answer,
                answer: response.answer,
                streaming: false,
                status: undefined,
              }
            : message
        )
      );
      void refreshHistory().catch(() => retryHistory());
      void refreshUsage();
    } catch (err) {
      if ((err as Error).name !== "AbortError" && !controller.signal.aborted) {
        setMessages((current) =>
          current.filter(
            (message) => message.id !== userMessageId && message.id !== assistantMessageId
          )
        );
        setQuestion(trimmed);
        if (err instanceof DailyTokenQuotaError) {
          setError(translate(session ? "chat.quota.userExceeded" : "chat.quota.guestExceeded"));
          setQuotaBlocked(true);
          setQuotaStoppedDuringProcessing(err.duringProcessing);
          setQuotaResetAt(err.resetAt || null);
          void refreshUsage();
        } else {
          setError(translate("chat.error.generic"));
        }
      }
    } finally {
      setIsLoading(false);
      abortRef.current = null;
      streamingMessageRef.current = null;
    }
  }
  async function handleFeedback(
    message: ChatMessage,
    rating: "helpful" | "not_helpful",
    detail?: {
      issue: "citation_incorrect" | "answer_incomplete" | "outdated_regulation" | "other";
      comment: string;
    }
  ): Promise<boolean> {
    const previous = feedback[message.id];
    setFeedback((current) => ({ ...current, [message.id]: rating }));
    setError(null);
    if (message.id === activeSourceMessageId) setSourceFeedbackError(null);
    // Frontend message.id is a client-side UUID, not the DB Message.message_id
    // (msg_...). Sending a fake answer_id makes the backend return 404, so only
    // send answer_id when it looks like a real DB id. Otherwise fall back to
    // conversation_id which the backend resolves to the latest assistant answer.
    const realAnswerId = message.id.startsWith("msg_") ? message.id : undefined;
    try {
      await submitFeedback({
        question: message.answer?.query ?? "Feedback chat",
        rating,
        answer_id: realAnswerId,
        conversation_id: conversationId ?? undefined,
        issue_category: detail?.issue,
        comment: detail?.comment || undefined,
      });
      return true;
    } catch {
      setFeedback((current) => {
        const next = { ...current };
        if (previous) next[message.id] = previous;
        else delete next[message.id];
        return next;
      });
      setError("Feedback belum dapat disimpan.");
      return false;
    }
  }

  async function handleSourceRate(rating: "helpful" | "not_helpful"): Promise<void> {
    if (!activeSourceMessageId || isSourceSubmitting) return;
    const target = messages.find((message) => message.id === activeSourceMessageId);
    if (!target) return;
    setIsSourceSubmitting(true);
    setSourceFeedbackError(null);
    const ok = await handleFeedback(target, rating);
    if (!ok) setSourceFeedbackError("Feedback belum dapat disimpan.");
    setIsSourceSubmitting(false);
  }

  const sourceRating = activeSourceMessageId ? (feedback[activeSourceMessageId] ?? null) : null;

  const sourcePanel =
    citations.length > 0 ? (
      <SourcePanel
        citations={citations}
        rating={sourceRating}
        feedbackError={sourceFeedbackError}
        isSubmitting={isSourceSubmitting}
        onRate={(rating) => void handleSourceRate(rating)}
      />
    ) : undefined;
  const personalizedPanel = session ? (
    <PersonalizedControls
      enabled={personalizedMode}
      memoryCount={memoryCount}
      busy={profileBusy || isLoading}
      error={profileError}
      onToggle={(enabled) => void handlePersonalizedToggle(enabled)}
      onDelete={() => void handleDeleteMemories()}
    />
  ) : undefined;

  return (
    <ChatWorkspaceShell
      conversations={conversations}
      activeConversationId={conversationId}
      historyLoading={historyLoading}
      historyError={historyError}
      onRetryHistory={retryHistory}
      sidebarExpanded={isSidebarExpanded}
      mobileSidebarOpen={isMobileSidebarOpen}
      sourceDrawerOpen={isSourceDrawerOpen}
      sourcePanel={sourcePanel}
      personalizedPanel={personalizedPanel}
      onSidebarExpandedChange={(expanded) => {
        setIsSidebarExpanded(expanded);
        writePreference(SIDEBAR_STORAGE_KEY, expanded ? "expanded" : "collapsed");
      }}
      onMobileSidebarOpenChange={(open) => {
        setIsMobileSidebarOpen(open);
        if (open) setIsSourceSheetOpen(false);
      }}
      onSourceDrawerClose={() => {
        setIsSourceDrawerOpen(false);
        window.setTimeout(() => sourceTriggerRef.current?.focus(), 0);
      }}
      onConversationSelect={(id) => void handleConversationSelect(id)}
      onNewConversation={handleNewConversation}
      onAuthenticated={() => {
        setQuotaBlocked(false);
        setQuotaStoppedDuringProcessing(false);
        setQuotaResetAt(null);
        void refreshUsage();
        if (!conversationId) return;
        setClaimErrorId(null);
        setPendingClaimId(conversationId);
      }}
      onConversationRename={handleConversationRename}
      onConversationDelete={handleConversationDelete}
    >
      <section
        className={`relative flex h-full min-h-0 flex-col ${
          messages.length === 0 ? "is-empty" : ""
        }`}
      >
        <div
          ref={conversationScrollRef}
          className={`chat-scroll-region min-h-0 flex-1 overflow-y-auto overscroll-contain px-[clamp(24px,7vw,100px)] [scroll-padding-bottom:20px] [scrollbar-gutter:stable] max-[760px]:px-4 ${
            messages.length === 0
              ? "flex flex-col py-4 max-[760px]:py-1"
              : "pb-[60px] pt-[36px] [@media(max-height:680px)]:min-[761px]:pt-5 max-[760px]:pb-[50px] max-[760px]:pt-[22px]"
          }`}
          aria-label={translate("chat.scrollRegion")}
          tabIndex={0}
          onScroll={handleConversationScroll}
        >
          {messages.length === 0 ? (
            <div className="mx-auto my-auto flex w-full max-w-[680px] shrink-0 flex-col items-center text-center">
              <h1 className="font-display text-[clamp(28px,3.5vw,38px)] font-semibold leading-[1.12] tracking-[-0.03em] text-javanese-deep max-[760px]:text-[26px]">
                {translate("chat.title")}
              </h1>
              <p className="mb-7 mt-3 max-w-[420px] text-[13px] leading-[1.65] text-muted-text max-[760px]:mb-4 max-[760px]:mt-2">
                {translate("chat.subtitle")}
              </p>
              <div className="grid w-full grid-cols-3 gap-3 max-[760px]:grid-cols-1 max-[760px]:gap-2">
                {[
                  { text: translate("suggestion.thr"), tag: translate("category.pengupahan") },
                  { text: translate("suggestion.pkwt"), tag: translate("category.pkwt") },
                  { text: translate("suggestion.phk"), tag: translate("category.phk") },
                ].map((item) => (
                  <button
                    key={item.text}
                    type="button"
                    onClick={() => void handleSubmit(item.text)}
                    className="chat-suggestion group flex min-h-[90px] w-full flex-col justify-between rounded-xl border border-[#d8e8dc] bg-white px-4 py-3.5 text-left transition focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-javanese hover:border-javanese/40 hover:shadow-[0_2px_12px_rgba(22,128,63,0.1)] max-[760px]:min-h-[auto] max-[760px]:px-3.5 max-[760px]:py-2"
                  >
                    <span className="mb-2 inline-flex self-start rounded-md bg-teal-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-teal-strong max-[760px]:mb-1">
                      {item.tag}
                    </span>
                    <span className="text-[13px] leading-[1.55] text-foreground max-[760px]:text-[12px]">
                      {item.text}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <ConversationThread
              messages={messages}
              feedback={feedback}
              onShowSources={showSources}
              onFeedback={(message, rating, detail) => void handleFeedback(message, rating, detail)}
              onEditMessage={(message) => {
                setQuestion(message.content);
                window.setTimeout(() => inputRef.current?.focus(), 0);
              }}
            />
          )}
          {isLoading && !messages.some((message) => message.streaming) ? (
            <div
              className="mx-auto mb-5 flex max-w-[760px] items-start gap-3 rounded-xl border-l-[3px] border-javanese/30 bg-[#f0f8f2] py-3 pl-4 pr-3 text-xs leading-[1.55] text-tinta"
              role="status"
              aria-live="polite"
            >
              <span className="mt-0.5 size-4 shrink-0 animate-spin rounded-full border-2 border-javanese/20 border-t-javanese" />
              <div>
                <strong className="block font-semibold">{translate("chat.loading.title")}</strong>
                <span className="mt-0.5 block text-muted-text">
                  {translate("chat.loading.subtitle")}
                </span>
              </div>
            </div>
          ) : null}
          {pendingClaimId ? (
            <div
              className="mx-auto mb-4 max-w-[760px] rounded-lg border border-javanese/25 bg-teal-soft p-3 text-[13px] leading-relaxed text-javanese-deep"
              role="status"
              aria-live="polite"
            >
              {translate("chat.claim.saving")}
            </div>
          ) : null}
          {claimErrorId ? (
            <div
              className="mx-auto mb-4 flex max-w-[760px] flex-wrap items-center gap-3 rounded-lg border border-amber/30 bg-amber-soft p-3 text-[13px] text-foreground"
              role="alert"
            >
              <span className="min-w-0 flex-1">{translate("chat.claim.error")}</span>
              <button
                type="button"
                className="min-h-11 rounded-lg bg-javanese px-3 font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-javanese"
                onClick={() => {
                  setPendingClaimId(claimErrorId);
                  setClaimErrorId(null);
                }}
              >
                {translate("chat.claim.retry")}
              </button>
            </div>
          ) : null}
          {error || quotaBlocked ? (
            <div
              className="mx-auto mb-5 flex max-w-[760px] flex-wrap items-center gap-2.5 rounded-lg border border-[#f0d6d2] bg-[#fef7f5] p-3 text-xs leading-[1.55] text-[#753328]"
              role="alert"
            >
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <span className="min-w-0 flex-1">
                {quotaBlocked
                  ? translate(
                      session
                        ? quotaStoppedDuringProcessing
                          ? "chat.quota.userStopped"
                          : "chat.quota.userExceeded"
                        : quotaStoppedDuringProcessing
                          ? "chat.quota.guestStopped"
                          : "chat.quota.guestExceeded"
                    )
                  : error}
              </span>
              {question.trim() && !quotaBlocked ? (
                <button
                  type="button"
                  className="min-h-11 rounded-lg border border-[#d9aaa1] px-3 font-semibold text-[#753328] transition hover:bg-[#fbe9e5] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#753328]"
                  onClick={() => void handleSubmit()}
                >
                  {translate("chat.error.retry")}
                </button>
              ) : null}
            </div>
          ) : null}
          <div ref={conversationEndRef} />
        </div>
        {usage ? (
          <div
            className="relative z-10 mx-auto mb-3 w-[calc(100%-2rem)] max-w-[768px] rounded-xl border border-[#d8e8dc] bg-[#f5faf6] px-4 py-2.5 text-xs leading-5 text-muted-text dark:border-[#294034] dark:bg-[#101713] max-[760px]:w-[calc(100%-1.5rem)] max-[760px]:px-3 max-[420px]:mb-2 max-[420px]:px-2.5 max-[420px]:py-1.5 max-[420px]:leading-4"
            title={usage.estimated_tokens > 0 ? translate("chat.quota.estimated") : undefined}
          >
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <span className="min-w-0">
                <span className="font-semibold text-tinta">
                  <span className="max-[420px]:hidden">{translate("chat.quota.remaining")}</span>
                  <span className="hidden max-[420px]:inline">
                    {translate("chat.quota.remainingShort")}
                  </span>
                  :
                </span>{" "}
                <span className="font-semibold tabular-nums text-tinta">
                  {new Intl.NumberFormat("id-ID").format(usage.remaining_tokens)}
                </span>{" "}
                <span className="max-[420px]:hidden">
                  {translate("chat.quota.of")}{" "}
                  {new Intl.NumberFormat("id-ID").format(usage.limit_tokens)} token
                </span>
                <span className="hidden max-[420px]:inline">
                  / {new Intl.NumberFormat("id-ID").format(usage.limit_tokens)}
                </span>
                {usage.estimated_tokens > 0 ? (
                  <span aria-label={translate("chat.quota.estimated")}> *</span>
                ) : null}
              </span>
              <span
                className="shrink-0 text-[11px] text-muted-text"
                aria-label={translate("chat.quota.reset")}
              >
                <span className="max-[420px]:hidden">{translate("chat.quota.reset")}</span>
                <span className="hidden max-[420px]:inline">
                  {translate("chat.quota.resetShort")}
                </span>
              </span>
            </div>
            <div
              role="progressbar"
              aria-label={translate("chat.quota.remaining")}
              aria-valuemin={0}
              aria-valuemax={usage.limit_tokens}
              aria-valuenow={Math.min(usage.limit_tokens, Math.max(0, usage.remaining_tokens))}
              className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#d8e8dc] dark:bg-[#294034] max-[420px]:mt-1"
            >
              <div
                className="h-full rounded-full bg-javanese transition-[width] dark:bg-[#84c99b]"
                style={{
                  width: `${
                    usage.limit_tokens > 0
                      ? Math.min(
                          100,
                          Math.max(0, (usage.remaining_tokens / usage.limit_tokens) * 100)
                        )
                      : 0
                  }%`,
                }}
              />
            </div>
            {usage.remaining_tokens <= 0 ? (
              <p className="mt-1 text-[#8a382d] dark:text-[#f0a99f]">
                {translate("chat.quota.empty")}
              </p>
            ) : usage.remaining_tokens <= usage.limit_tokens * 0.1 ? (
              <p className="mt-1 text-[#8a382d] dark:text-[#f0a99f]">
                {translate("chat.quota.low")}
              </p>
            ) : null}
          </div>
        ) : usageStatus === "error" ? (
          <div
            className="relative z-10 mx-auto mb-2 flex w-full max-w-[800px] items-center justify-between gap-3 bg-background px-4 text-xs text-muted-text max-[760px]:px-3"
            role="status"
            aria-live="polite"
          >
            <span>{translate("chat.quota.unavailable")}</span>
            <button
              type="button"
              className="min-h-9 rounded-lg px-2 font-semibold text-javanese underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-javanese"
              onClick={() => void refreshUsage()}
            >
              {translate("chat.quota.retry")}
            </button>
          </div>
        ) : (
          <div
            className="relative z-10 mx-auto mb-3 w-[calc(100%-2rem)] max-w-[768px] rounded-xl border border-[#d8e8dc] bg-[#f5faf6] px-4 py-2.5 dark:border-[#294034] dark:bg-[#101713] max-[760px]:w-[calc(100%-1.5rem)] max-[760px]:px-3 max-[420px]:mb-2 max-[420px]:px-2.5 max-[420px]:py-1.5"
            role="status"
            aria-label={translate("chat.quota.loading")}
          >
            <div className="flex items-center justify-between gap-3" aria-hidden="true">
              <Skeleton className="h-4 w-48 max-w-[60%]" />
              <Skeleton className="h-3 w-24 shrink-0 max-[420px]:w-14" />
            </div>
            <Skeleton
              className="mt-2 h-1.5 w-full rounded-full max-[420px]:mt-1"
              aria-hidden="true"
            />
          </div>
        )}
        <ChatComposer
          question={question}
          loading={isLoading}
          disabled={Boolean(pendingClaimId || claimErrorId)}
          quotaBlocked={quotaBlocked}
          reasoningMode={reasoningMode}
          inputRef={inputRef}
          onQuestionChange={setQuestion}
          onReasoningModeChange={(mode) => {
            setReasoningMode(mode);
            writePreference(REASONING_MODE_STORAGE_KEY, mode);
          }}
          onSubmit={() => void handleSubmit()}
          onCancel={stopRequest}
        />
        {messages.length === 0 ? (
          <p className="relative z-[3] mx-auto mb-2 max-w-[680px] px-6 text-center text-xs leading-relaxed text-muted-foreground max-[760px]:px-[18px]">
            {translate("footer.disclaimer")} {translate("footer.agreement")}{" "}
            <Link
              href="/legal/terms"
              className="text-inherit underline underline-offset-4 transition-colors hover:text-javanese"
            >
              {translate("footer.terms")}
            </Link>
            ,{" "}
            <Link
              href="/legal/privacy"
              className="text-inherit underline underline-offset-4 transition-colors hover:text-javanese"
            >
              {translate("footer.privacy")}
            </Link>
            , {translate("footer.and")}{" "}
            <Link
              href="/legal/disclaimer"
              className="text-inherit underline underline-offset-4 transition-colors hover:text-javanese"
            >
              {translate("footer.legalDisclaimer")}
            </Link>
            .
          </p>
        ) : null}
      </section>
      <SourceSheet
        open={isSourceSheetOpen}
        citations={citations}
        rating={sourceRating}
        feedbackError={sourceFeedbackError}
        isSubmitting={isSourceSubmitting}
        onRate={(rating) => void handleSourceRate(rating)}
        onClose={closeSourceSheet}
      />
    </ChatWorkspaceShell>
  );
}
