import { API_URL, parseJsonResponse } from "@/lib/api-client";
import { getStoredSession } from "@/features/auth";
import type { AskResponse, ConversationDetail, ConversationSummary } from "./types";
const GUEST_STORAGE_KEY = "kerjapedia-guest-v1";

function getGuestId(): string {
  const existing = window.localStorage.getItem(GUEST_STORAGE_KEY);
  if (existing) return existing;
  const guestId = crypto.randomUUID();
  window.localStorage.setItem(GUEST_STORAGE_KEY, guestId);
  return guestId;
}

function chatHeaders(contentType = false): HeadersInit {
  const session = getStoredSession();
  return {
    ...(contentType ? { "Content-Type": "application/json" } : {}),
    ...(session
      ? { Authorization: `Bearer ${session.access_token}` }
      : { "X-KerjaPedia-Guest-ID": getGuestId() }),
  };
}

export async function askQuestion(
  question: string,
  conversationId: string | null,
  signal: AbortSignal
): Promise<AskResponse> {
  const response = await fetch(`${API_URL}/chat/ask`, {
    method: "POST",
    headers: chatHeaders(true),
    body: JSON.stringify({
      question,
      conversation_id: conversationId,
      top_k: 5,
    }),
    signal,
  });
  return parseJsonResponse<AskResponse>(response);
}

type StreamHandlers = {
  onStart: (conversationId: string) => void;
  onThinking: (status: string) => void;
  onDelta: (content: string) => void;
};

type ChatStreamEvent =
  | { event: "start"; conversation_id: string; status: string }
  | { event: "thinking"; status: string }
  | { event: "delta"; content: string }
  | { event: "done"; response: AskResponse }
  | { event: "error"; detail: string };

export async function askQuestionStream(
  question: string,
  conversationId: string | null,
  signal: AbortSignal,
  handlers: StreamHandlers
): Promise<AskResponse> {
  const response = await fetch(`${API_URL}/chat/ask/stream`, {
    method: "POST",
    headers: chatHeaders(true),
    body: JSON.stringify({
      question,
      conversation_id: conversationId,
      top_k: 5,
    }),
    signal,
  });
  if (!response.ok || !response.body) return parseJsonResponse<AskResponse>(response);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed: AskResponse | null = null;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line) as ChatStreamEvent;
      if (event.event === "start") {
        handlers.onStart(event.conversation_id);
        handlers.onThinking(event.status);
      } else if (event.event === "thinking") {
        handlers.onThinking(event.status);
      } else if (event.event === "delta") {
        handlers.onDelta(event.content);
      } else if (event.event === "done") {
        completed = event.response;
      } else if (event.event === "error") {
        throw new Error(event.detail);
      }
    }
    if (done) break;
  }
  if (!completed) throw new Error("Streaming jawaban berhenti sebelum selesai.");
  return completed;
}

export async function fetchConversations(signal?: AbortSignal): Promise<ConversationSummary[]> {
  const response = await fetch(`${API_URL}/chat/conversations`, {
    headers: chatHeaders(),
    signal,
  });
  return parseJsonResponse<ConversationSummary[]>(response);
}

export async function fetchConversation(
  conversationId: string,
  signal?: AbortSignal
): Promise<ConversationDetail> {
  const response = await fetch(`${API_URL}/chat/conversations/${conversationId}`, {
    headers: chatHeaders(),
    signal,
  });
  return parseJsonResponse<ConversationDetail>(response);
}

export async function renameConversation(
  conversationId: string,
  title: string
): Promise<ConversationSummary> {
  const response = await fetch(`${API_URL}/chat/conversations/${conversationId}`, {
    method: "PATCH",
    headers: chatHeaders(true),
    body: JSON.stringify({ title }),
  });
  return parseJsonResponse<ConversationSummary>(response);
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const response = await fetch(`${API_URL}/chat/conversations/${conversationId}`, {
    method: "DELETE",
    headers: chatHeaders(),
  });
  if (!response.ok) await parseJsonResponse(response);
}

export { submitFeedback } from "./feedback-api";
export type { FeedbackIssue, FeedbackRating } from "./feedback-api";
export { documentPdfUrl } from "@/features/documents";
export { SESSION_STORAGE_KEY } from "@/features/auth";
