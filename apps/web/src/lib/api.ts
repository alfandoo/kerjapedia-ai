import type {
  AdminOverview,
  AdminRelationship,
  AdminStats,
  AskResponse,
  ConversationDetail,
  ConversationSummary,
  DocumentSummary,
  FeedbackItem,
  IngestionJob,
  RetrievalPlaygroundResponse,
  UserSession,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
export const SESSION_STORAGE_KEY = "kerjapedia-session-v1";
const GUEST_STORAGE_KEY = "kerjapedia-guest-v1";

export function getStoredSession(): UserSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserSession;
  } catch {
    return null;
  }
}

function adminHeaders(contentType = true): HeadersInit {
  const session = getStoredSession();
  return {
    ...(contentType ? { "Content-Type": "application/json" } : {}),
    ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}),
  };
}

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

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
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

export async function fetchDocuments(signal?: AbortSignal): Promise<DocumentSummary[]> {
  const response = await fetch(`${API_URL}/documents`, { signal });
  const documents = await parseJsonResponse<DocumentSummary[]>(response);
  return documents.map((document) => ({
    ...document,
    pdf_url: new URL(document.pdf_url, `${API_URL}/`).toString(),
  }));
}

export function documentPdfUrl(documentId: string): string {
  return `${API_URL}/documents/${encodeURIComponent(documentId)}/pdf`;
}

export async function submitFeedback(payload: {
  question: string;
  rating: "helpful" | "not_helpful";
  answer_id?: string;
}): Promise<void> {
  await fetch(`${API_URL}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function login(email: string, password: string): Promise<UserSession> {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return parseJsonResponse<UserSession>(response);
}

export async function register(
  name: string,
  email: string,
  password: string
): Promise<UserSession> {
  const response = await fetch(`${API_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
  });
  return parseJsonResponse<UserSession>(response);
}

export async function fetchAdminStats(signal?: AbortSignal): Promise<AdminStats> {
  const response = await fetch(`${API_URL}/admin/stats`, {
    headers: adminHeaders(),
    signal,
  });
  return parseJsonResponse<AdminStats>(response);
}

export async function fetchAdminOverview(signal?: AbortSignal): Promise<AdminOverview> {
  const response = await fetch(`${API_URL}/admin/documents`, {
    headers: adminHeaders(),
    signal,
  });
  return parseJsonResponse<AdminOverview>(response);
}

export async function updateAdminDocument(
  documentId: string,
  payload: { legal_status: string; verification_status: string; topics: string[] }
): Promise<void> {
  const response = await fetch(`${API_URL}/admin/documents/${documentId}`, {
    method: "PATCH",
    headers: adminHeaders(),
    body: JSON.stringify(payload),
  });
  await parseJsonResponse(response);
}

export async function updateAdminRelationships(
  documentId: string,
  relationships: Omit<AdminRelationship, "from_document_id">[]
): Promise<void> {
  const response = await fetch(`${API_URL}/admin/documents/${documentId}/relationships`, {
    method: "PUT",
    headers: adminHeaders(),
    body: JSON.stringify(relationships),
  });
  await parseJsonResponse(response);
}

export async function updateAdminPublication(
  documentId: string,
  action: "publish" | "unpublish"
): Promise<{ status: "published" | "draft"; version: number }> {
  const response = await fetch(`${API_URL}/admin/documents/${documentId}/publication`, {
    method: "POST",
    headers: adminHeaders(),
    body: JSON.stringify({ action }),
  });
  return parseJsonResponse(response);
}

export async function createIngestionJob(documentId: string): Promise<IngestionJob> {
  const response = await fetch(`${API_URL}/ingestion/jobs`, {
    method: "POST",
    headers: adminHeaders(),
    body: JSON.stringify({ document_id: documentId, persist_db: false }),
  });
  return parseJsonResponse<IngestionJob>(response);
}

export async function fetchIngestionJobs(signal?: AbortSignal): Promise<IngestionJob[]> {
  const response = await fetch(`${API_URL}/ingestion/jobs`, {
    headers: adminHeaders(),
    signal,
  });
  return parseJsonResponse<IngestionJob[]>(response);
}

export async function fetchAdminFeedback(signal?: AbortSignal): Promise<FeedbackItem[]> {
  const response = await fetch(`${API_URL}/feedback`, {
    headers: adminHeaders(),
    signal,
  });
  return parseJsonResponse<FeedbackItem[]>(response);
}

export async function runRetrievalPlayground(
  question: string,
  topK: number
): Promise<RetrievalPlaygroundResponse> {
  const response = await fetch(`${API_URL}/admin/retrieval/search`, {
    method: "POST",
    headers: adminHeaders(),
    body: JSON.stringify({ question, top_k: topK }),
  });
  return parseJsonResponse<RetrievalPlaygroundResponse>(response);
}

export async function uploadAdminDocument(file: File, topic: string): Promise<void> {
  const query = new URLSearchParams({ file_name: file.name, topic });
  const response = await fetch(`${API_URL}/admin/documents/upload?${query}`, {
    method: "POST",
    headers: adminHeaders(false),
    body: file,
  });
  await parseJsonResponse(response);
}
