"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ChatComposer } from "./chat-composer";
import type { ChatMessage } from "./chat-types";
import { ChatWorkspaceShell } from "./chat-workspace-shell";
import { ConversationThread } from "./conversation-thread";
import { AlertTriangle } from "lucide-react";
import { SourcePanel } from "./source-panel";
import { SourceSheet } from "./source-sheet";
import { useStoredSession } from "@/hooks/use-stored-session";
import {
  askQuestionStream,
  deleteConversation,
  fetchConversation,
  fetchConversations,
  renameConversation,
  submitFeedback,
} from "@/lib/api";
import type { AnswerPayload, Citation, ConversationSummary } from "@/lib/types";

const suggestions = [
  { text: "Kapan batas waktu pembayaran THR?", tag: "Pengupahan" },
  { text: "Apakah pekerja PKWT berhak atas uang kompensasi?", tag: "PKWT" },
  { text: "Apa syarat PHK karena efisiensi perusahaan?", tag: "PHK" },
];

const SIDEBAR_STORAGE_KEY = "kerjapedia.chat.sidebar.v1";

export function EditorialChatExperience() {
  const session = useStoredSession();
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [citationQuestion, setCitationQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [isSourceSheetOpen, setIsSourceSheetOpen] = useState(false);
  const [isSourceDrawerOpen, setIsSourceDrawerOpen] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [isSidebarExpanded, setIsSidebarExpanded] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Record<string, "helpful" | "not_helpful">>({});
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const conversationEndRef = useRef<HTMLDivElement>(null);
  const sourceTriggerRef = useRef<HTMLElement | null>(null);
  const streamingMessageRef = useRef<string | null>(null);

  const closeSourceSheet = useCallback(() => {
    setIsSourceSheetOpen(false);
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }, []);
  const refreshHistory = useCallback(async (signal?: AbortSignal) => {
    setConversations(await fetchConversations(signal));
  }, []);

  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    async function loadHistory() {
      try {
        const nextConversations = await fetchConversations(controller.signal);
        setConversations(nextConversations);
      } catch (err) {
        if ((err as Error).name !== "AbortError") setError("Riwayat belum dapat dimuat.");
      } finally {
        setHistoryLoading(false);
      }
    }
    void loadHistory();
    return () => controller.abort();
  }, [session]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setIsSidebarExpanded(window.localStorage.getItem(SIDEBAR_STORAGE_KEY) !== "collapsed");
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (messages.length === 0 && !isLoading) return;
    conversationEndRef.current?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      block: "nearest",
    });
  }, [isLoading, messages.length]);

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
  function showSources(answer: AnswerPayload) {
    sourceTriggerRef.current = document.activeElement as HTMLElement | null;
    setCitations(answer.citations);
    setCitationQuestion(answer.query);
    setIsMobileSidebarOpen(false);
    if (window.matchMedia("(max-width: 760px)").matches) {
      setIsSourceSheetOpen(true);
      setIsSourceDrawerOpen(false);
    } else {
      setIsSourceDrawerOpen(true);
    }
  }
  async function handleConversationSelect(nextId: string) {
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
      setConversationId(detail.conversation_id);
      setMessages(nextMessages);
      setCitations(latest?.citations ?? []);
      setCitationQuestion(latest?.query ?? "");
      setIsSourceSheetOpen(false);
      setIsSourceDrawerOpen(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setHistoryLoading(false);
    }
  }
  function handleNewConversation() {
    if (isLoading) stopRequest();
    setConversationId(null);
    setMessages([]);
    setCitations([]);
    setCitationQuestion("");
    setError(null);
    setIsSourceSheetOpen(false);
    setIsSourceDrawerOpen(false);
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
    if (!trimmed || isLoading) return;
    setError(null);
    setQuestion("");
    setIsLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const assistantMessageId = crypto.randomUUID();
    streamingMessageRef.current = assistantMessageId;
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
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
        status: "Menganalisis pertanyaan",
      },
    ]);
    try {
      const response = await askQuestionStream(trimmed, conversationId, controller.signal, {
        onStart: setConversationId,
        onThinking: (status) =>
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId ? { ...message, status } : message
            )
          ),
        onDelta: (content) =>
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId
                ? { ...message, content: message.content + content, status: undefined }
                : message
            )
          ),
      });
      setConversationId(response.conversation_id);
      setCitations(response.answer.citations);
      setCitationQuestion(trimmed);
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
      await refreshHistory();
    } catch (err) {
      if ((err as Error).name !== "AbortError") setError((err as Error).message);
    } finally {
      setIsLoading(false);
      abortRef.current = null;
      streamingMessageRef.current = null;
    }
  }
  async function handleFeedback(
    message: ChatMessage,
    rating: "helpful" | "not_helpful",
    detail?: { issue: "citation_incorrect" | "answer_incomplete" | "outdated_regulation" | "other"; comment: string }
  ) {
    setFeedback((current) => ({ ...current, [message.id]: rating }));
    await submitFeedback({
      question: message.answer?.query ?? "Feedback chat",
      rating,
      answer_id: message.id,
      conversation_id: conversationId ?? undefined,
      issue_category: detail?.issue,
      comment: detail?.comment || undefined,
    }).catch(() => setError("Feedback belum dapat disimpan."));
  }

  const sourcePanel =
    citations.length > 0 ? (
      <SourcePanel citations={citations} question={citationQuestion} />
    ) : undefined;

  return (
    <ChatWorkspaceShell
      conversations={conversations}
      activeConversationId={conversationId}
      historyLoading={historyLoading}
      sidebarExpanded={isSidebarExpanded}
      mobileSidebarOpen={isMobileSidebarOpen}
      sourceDrawerOpen={isSourceDrawerOpen}
      sourcePanel={sourcePanel}
      onSidebarExpandedChange={(expanded) => {
        setIsSidebarExpanded(expanded);
        window.localStorage.setItem(SIDEBAR_STORAGE_KEY, expanded ? "expanded" : "collapsed");
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
      onConversationRename={handleConversationRename}
      onConversationDelete={handleConversationDelete}
    >
      <section
        className={`relative flex h-full min-h-0 flex-col ${
          messages.length === 0 ? "is-empty" : ""
        }`}
      >
        <div className="min-h-0 flex-1 overflow-y-auto px-[clamp(24px,7vw,100px)] pb-[160px] pt-[36px] [scroll-padding-bottom:20px] [@media(max-height:680px)]:min-[761px]:pt-5 max-[760px]:px-4 max-[760px]:pb-[140px] max-[760px]:pt-[22px]">
          {messages.length === 0 ? (
            <div className="mx-auto mt-[clamp(24px,6vh,72px)] flex max-w-[680px] flex-col items-center text-center max-[760px]:mt-[clamp(28px,7vh,56px)]">
              <span className="mb-4 inline-flex items-center gap-2 rounded-full border border-[#e2ddd3] bg-[#faf8f4] px-4 py-1.5 text-[11px] font-medium tracking-wide text-[#8a7a5e]">
                <span className="size-1.5 rounded-full bg-emas" />
                Asisten Hukum Ketenagakerjaan
              </span>
              <h1 className="font-display text-[clamp(28px,3.5vw,38px)] font-semibold leading-[1.12] tracking-[-0.03em] text-tinta max-[760px]:text-[28px]">
                Apa yang ingin Anda pahami?
              </h1>
              <p className="mb-8 mt-3 max-w-[420px] text-[13px] leading-[1.65] text-muted-text max-[760px]:mb-6 max-[760px]:mt-2.5">
                Tanyakan regulasi ketenagakerjaan Indonesia. Jawaban dilengkapi dasar hukum dan kutipan resmi.
              </p>
              <div className="grid w-full grid-cols-3 gap-3 max-[760px]:grid-cols-1 max-[760px]:gap-2.5">
                {suggestions.map((item) => (
                  <button
                    key={item.text}
                    type="button"
                    onClick={() => void handleSubmit(item.text)}
                    className="group flex min-h-[90px] w-full flex-col justify-between rounded-xl border border-[#e8e4dc] bg-white px-4 py-3.5 text-left transition hover:border-emas/40 hover:shadow-[0_2px_12px_rgba(201,162,39,0.08)] max-[760px]:min-h-[auto] max-[760px]:py-3"
                  >
                    <span className="mb-2 inline-flex self-start rounded-md bg-[#faf8f4] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#8a7a5e]">
                      {item.tag}
                    </span>
                    <span className="text-[13px] leading-[1.45] text-[#303b35] group-hover:text-tinta">
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
              onFeedback={(message, rating) => void handleFeedback(message, rating)}
              onEditMessage={(message) => {
                setQuestion(message.content);
                window.setTimeout(() => inputRef.current?.focus(), 0);
              }}
            />
          )}
          {isLoading && !messages.some((message) => message.streaming) ? (
            <div
              className="mx-auto mb-5 flex max-w-[760px] items-start gap-3 rounded-xl border-l-[3px] border-javanese/20 bg-[#fafbf9] py-3 pl-4 pr-3 text-xs leading-[1.55] text-tinta"
              role="status"
              aria-live="polite"
            >
              <span className="mt-0.5 size-4 shrink-0 animate-spin rounded-full border-2 border-javanese/20 border-t-javanese" />
              <div>
                <strong className="block font-semibold">Menelusuri regulasi yang relevan…</strong>
                <span className="mt-0.5 block text-muted-text">
                  Memeriksa pasal, status, dan sumber pendukung.
                </span>
              </div>
            </div>
          ) : null}
          {error ? (
            <div
              className="mx-auto mb-5 flex max-w-[760px] items-start gap-2.5 rounded-lg border border-[#f0d6d2] bg-[#fef7f5] p-3 text-xs leading-[1.55] text-[#753328]"
              role="alert"
            >
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <span>{error}</span>
            </div>
          ) : null}
          <div ref={conversationEndRef} />
        </div>
        <ChatComposer
          question={question}
          loading={isLoading}
          inputRef={inputRef}
          onQuestionChange={setQuestion}
          onSubmit={() => void handleSubmit()}
          onCancel={stopRequest}
        />
        {messages.length === 0 ? (
          <p className="absolute inset-x-6 bottom-[max(15px,env(safe-area-inset-bottom))] z-[3] mx-auto max-w-[680px] text-center text-[10px] leading-[1.5] text-[#b0b8b3] max-[760px]:inset-x-[18px] max-[760px]:bottom-[max(12px,env(safe-area-inset-bottom))] max-[760px]:text-[9px]">
            KerjaPedia dapat membuat kekeliruan. Periksa selalu sumber resmi. Dengan menggunakan
            layanan ini, Anda menyetujui{" "}
            <Link
              href="/legal/terms"
              className="text-inherit [text-underline-offset:2px] transition-colors hover:text-javanese"
            >
              Ketentuan
            </Link>
            ,{" "}
            <Link
              href="/legal/privacy"
              className="text-inherit [text-underline-offset:2px] transition-colors hover:text-javanese"
            >
              Privasi
            </Link>
            , dan{" "}
            <Link
              href="/legal/disclaimer"
              className="text-inherit [text-underline-offset:2px] transition-colors hover:text-javanese"
            >
              Disclaimer
            </Link>
            .
          </p>
        ) : null}
      </section>
      <SourceSheet
        open={isSourceSheetOpen}
        citations={citations}
        question={citationQuestion}
        onClose={closeSourceSheet}
      />
    </ChatWorkspaceShell>
  );
}
