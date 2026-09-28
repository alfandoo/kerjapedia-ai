import { API_URL, parseJsonResponse } from "@/lib/api-client";
import { fetchWithAuthRetry } from "@/features/auth";
import type {
  AskResponse,
  ConversationDetail,
  ConversationSummary,
  ReasoningMode,
  TokenUsageSnapshot,
  WorkProfile,
} from "./types";
import { chatHeaders } from "./request-headers";

export class DailyTokenQuotaError extends Error {
  constructor(
    public readonly resetAt: string,
    public readonly duringProcessing = false
  ) {
    super("daily_token_quota_exceeded");
    this.name = "DailyTokenQuotaError";
  }
}

async function throwIfQuotaExceeded(response: Response): Promise<void> {
  if (response.status !== 429) return;
  const payload = (await response
    .clone()
    .json()
    .catch(() => null)) as {
    detail?: { code?: string; reset_at?: string };
  } | null;
  if (payload?.detail?.code === "daily_token_quota_exceeded")
    throw new DailyTokenQuotaError(payload.detail.reset_at ?? "");
}

export async function fetchTokenUsage(signal?: AbortSignal): Promise<TokenUsageSnapshot> {
  const response = await fetchWithAuthRetry(
    API_URL + "/chat/usage",
    { headers: chatHeaders() },
    signal
  );
  return parseJsonResponse<TokenUsageSnapshot>(response);
}

export async function askQuestion(
  question: string,
  conversationId: string | null,
  signal: AbortSignal,
  reasoningMode: ReasoningMode = "standard",
  personalizedMode = false
): Promise<AskResponse> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/chat/ask`,
    {
      method: "POST",
      headers: chatHeaders(true),
      body: JSON.stringify({
        question,
        conversation_id: conversationId,
        top_k: 5,
        reasoning_mode: reasoningMode,
        personalized_mode: personalizedMode,
      }),
    },
    signal
  );
  await throwIfQuotaExceeded(response);
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
  | { event: "ping" }
  | { event: "delta"; content: string }
  | { event: "done"; response: AskResponse }
  | { event: "error"; detail: string; code?: string; reset_at?: string };

export async function askQuestionStream(
  question: string,
  conversationId: string | null,
  signal: AbortSignal,
  handlers: StreamHandlers,
  reasoningMode: ReasoningMode = "standard",
  personalizedMode = false
): Promise<AskResponse> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/chat/ask/stream`,
    {
      method: "POST",
      headers: chatHeaders(true),
      body: JSON.stringify({
        question,
        conversation_id: conversationId,
        top_k: 5,
        reasoning_mode: reasoningMode,
        personalized_mode: personalizedMode,
      }),
    },
    signal
  );
  await throwIfQuotaExceeded(response);
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
        if (event.code === "daily_token_quota_exceeded")
          throw new DailyTokenQuotaError(event.reset_at ?? "", true);
        throw new Error(event.detail);
      }
    }
    if (done) break;
  }
  if (!completed) throw new Error("Streaming jawaban berhenti sebelum selesai.");
  return completed;
}

export async function fetchConversations(signal?: AbortSignal): Promise<ConversationSummary[]> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/chat/conversations`,
    { headers: chatHeaders() },
    signal
  );
  return parseJsonResponse<ConversationSummary[]>(response);
}

export async function fetchConversation(
  conversationId: string,
  signal?: AbortSignal
): Promise<ConversationDetail> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/chat/conversations/${conversationId}`,
    { headers: chatHeaders() },
    signal
  );
  return parseJsonResponse<ConversationDetail>(response);
}

export async function claimGuestConversation(
  conversationId: string,
  signal?: AbortSignal
): Promise<ConversationSummary> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/chat/conversations/${conversationId}/claim`,
    { method: "POST", headers: chatHeaders() },
    signal
  );
  return parseJsonResponse<ConversationSummary>(response);
}

export async function renameConversation(
  conversationId: string,
  title: string
): Promise<ConversationSummary> {
  const response = await fetchWithAuthRetry(`${API_URL}/chat/conversations/${conversationId}`, {
    method: "PATCH",
    headers: chatHeaders(true),
    body: JSON.stringify({ title }),
  });
  return parseJsonResponse<ConversationSummary>(response);
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const response = await fetchWithAuthRetry(`${API_URL}/chat/conversations/${conversationId}`, {
    method: "DELETE",
    headers: chatHeaders(),
  });
  if (!response.ok) await parseJsonResponse(response);
}

export { submitFeedback } from "./feedback-api";
export type { FeedbackIssue, FeedbackRating } from "./feedback-api";
export { documentPdfUrl } from "@/features/documents";

export type UserMemorySettings = {
  enabled: boolean;
  memory_count: number;
};

export async function fetchMemorySettings(): Promise<UserMemorySettings> {
  return parseJsonResponse<UserMemorySettings>(
    await fetchWithAuthRetry(`${API_URL}/auth/memories`, { headers: chatHeaders() })
  );
}

export async function updateMemorySettings(enabled: boolean): Promise<UserMemorySettings> {
  return parseJsonResponse<UserMemorySettings>(
    await fetchWithAuthRetry(`${API_URL}/auth/memories`, {
      method: "PATCH",
      headers: chatHeaders(true),
      body: JSON.stringify({ enabled }),
    })
  );
}

export async function deleteMemories(): Promise<void> {
  const response = await fetchWithAuthRetry(`${API_URL}/auth/memories`, {
    method: "DELETE",
    headers: chatHeaders(),
  });
  if (!response.ok) await parseJsonResponse(response);
}

export async function fetchWorkProfile(): Promise<WorkProfile> {
  return parseJsonResponse<WorkProfile>(
    await fetchWithAuthRetry(`${API_URL}/auth/work-profile`, { headers: chatHeaders() })
  );
}

export async function saveWorkProfile(profile: WorkProfile): Promise<WorkProfile> {
  return parseJsonResponse<WorkProfile>(
    await fetchWithAuthRetry(`${API_URL}/auth/work-profile`, {
      method: "PUT",
      headers: chatHeaders(true),
      body: JSON.stringify(profile),
    })
  );
}

export async function deleteWorkProfile(): Promise<void> {
  const response = await fetchWithAuthRetry(`${API_URL}/auth/work-profile`, {
    method: "DELETE",
    headers: chatHeaders(),
  });
  if (!response.ok) await parseJsonResponse(response);
}

export async function setPersonalizedMode(
  conversationId: string,
  enabled: boolean
): Promise<ConversationSummary> {
  return parseJsonResponse<ConversationSummary>(
    await fetchWithAuthRetry(`${API_URL}/chat/conversations/${conversationId}/personalized-mode`, {
      method: "PATCH",
      headers: chatHeaders(true),
      body: JSON.stringify({ personalized_mode: enabled }),
    })
  );
}
