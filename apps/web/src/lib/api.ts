import type {
  AdminOverview,
  AdminRelationship,
  AdminStats,
  AskResponse,
  ConversationDetail,
  ConversationSummary,
  DocumentSummary,
  EvaluationDataset,
  EvaluationRunDetail,
  EvaluationRunSummary,
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

export function clearStoredSession(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(SESSION_STORAGE_KEY);
  window.dispatchEvent(new Event("kerjapedia-session-change"));
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
    const body = (await response.json().catch(() => null)) as {
      detail?: string | { msg?: string }[];
    } | null;
    let message = `Request failed with status ${response.status}`;
    if (body?.detail) {
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        message = body.detail
          .map((item) => item?.msg)
          .filter(Boolean)
          .join("; ");
      }
    }
    throw new Error(message);
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

export type FeedbackRating = "helpful" | "not_helpful";
export type FeedbackIssue =
  | "citation_incorrect"
  | "answer_incomplete"
  | "outdated_regulation"
  | "other";

export async function submitFeedback(payload: {
  question: string;
  rating: FeedbackRating;
  answer_id?: string;
  conversation_id?: string;
  issue_category?: FeedbackIssue;
  comment?: string;
}): Promise<void> {
  const response = await fetch(`${API_URL}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Feedback belum dapat disimpan.");
  }
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

async function refreshStoredSession(): Promise<UserSession | null> {
  const session = getStoredSession();
  if (!session?.refresh_token) return null;
  const response = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: session.refresh_token }),
  });
  if (!response.ok) return null;
  const fresh = await response.json();
  if (!fresh.access_token) return null;
  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(fresh));
  window.dispatchEvent(new Event("kerjapedia-session-change"));
  return fresh as UserSession;
}

async function fetchWithAuthRetry(
  url: string,
  options: RequestInit,
  signal?: AbortSignal
): Promise<Response> {
  const response = await fetch(url, { ...options, signal });
  if (response.status !== 401) return response;
  const fresh = await refreshStoredSession();
  if (!fresh) return response;
  return fetch(url, {
    ...options,
    signal,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${fresh.access_token}`,
    },
  });
}

export async function fetchAdminStats(signal?: AbortSignal): Promise<AdminStats> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/stats`,
    { headers: adminHeaders() },
    signal
  );
  return parseJsonResponse<AdminStats>(response);
}

export interface AdminSettings {
  app_name: string;
  app_version: string;
  admin_email: string;
  rate_limit_per_minute: number;
  vector_store: string;
  embedding_provider: string;
  llm_provider: string;
  session_expires_in_seconds: number;
}

export async function fetchAdminSettings(signal?: AbortSignal): Promise<AdminSettings> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/settings`,
    { headers: adminHeaders() },
    signal
  );
  return parseJsonResponse<AdminSettings>(response);
}

export interface AuditLogEntry {
  audit_id: string;
  actor: string;
  action: string;
  target_type: string;
  target_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export async function fetchAuditLogs(
  limit = 100,
  signal?: AbortSignal
): Promise<AuditLogEntry[]> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/audit-logs?limit=${limit}`,
    { headers: adminHeaders() },
    signal
  );
  return parseJsonResponse<AuditLogEntry[]>(response);
}

export async function signOut(): Promise<void> {
  const session = getStoredSession();
  if (!session) return;
  try {
    await fetch(`${API_URL}/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${session.access_token}` },
    });
  } catch {
    // Local cleanup below still runs when the API is unreachable.
  }
  clearStoredSession();
}

export interface DocumentSearchFilters {
  q?: string;
  regulation_type?: string;
  year?: number;
  legal_status?: string;
}

export async function searchDocuments(
  filters: DocumentSearchFilters,
  signal?: AbortSignal
): Promise<DocumentSummary[]> {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.regulation_type) params.set("regulation_type", filters.regulation_type);
  if (filters.year) params.set("year", String(filters.year));
  if (filters.legal_status) params.set("legal_status", filters.legal_status);
  const query = params.toString();
  const response = await fetch(`${API_URL}/documents${query ? `?${query}` : ""}`, { signal });
  const documents = await parseJsonResponse<DocumentSummary[]>(response);
  return documents.map((document) => ({
    ...document,
    pdf_url: new URL(document.pdf_url, `${API_URL}/`).toString(),
  }));
}

export async function fetchDocumentDetail(documentId: string): Promise<Record<string, unknown>> {
  const response = await fetch(
    `${API_URL}/documents/${encodeURIComponent(documentId)}`,
    { cache: "no-store" }
  );
  return parseJsonResponse<Record<string, unknown>>(response);
}

export async function fetchAdminOverview(signal?: AbortSignal): Promise<AdminOverview> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/documents`,
    { headers: adminHeaders() },
    signal
  );
  return parseJsonResponse<AdminOverview>(response);
}

export async function updateAdminDocument(
  documentId: string,
  payload: { legal_status: string; verification_status: string; topics: string[] }
): Promise<void> {
  const response = await fetchWithAuthRetry(`${API_URL}/admin/documents/${documentId}`, {
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
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/documents/${documentId}/relationships`,
    {
      method: "PUT",
      headers: adminHeaders(),
      body: JSON.stringify(relationships),
    }
  );
  await parseJsonResponse(response);
}

export async function updateAdminPublication(
  documentId: string,
  action: "publish" | "unpublish"
): Promise<{ status: "published" | "draft"; version: number }> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/documents/${documentId}/publication`,
    {
      method: "POST",
      headers: adminHeaders(),
      body: JSON.stringify({ action }),
    }
  );
  return parseJsonResponse(response);
}

export async function createIngestionJob(documentId: string): Promise<IngestionJob> {
  const response = await fetchWithAuthRetry(`${API_URL}/ingestion/jobs`, {
    method: "POST",
    headers: adminHeaders(),
    body: JSON.stringify({ document_id: documentId, persist_db: false }),
  });
  return parseJsonResponse<IngestionJob>(response);
}

export async function fetchIngestionJobs(signal?: AbortSignal): Promise<IngestionJob[]> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/ingestion/jobs`,
    { headers: adminHeaders(), signal },
    signal
  );
  return parseJsonResponse<IngestionJob[]>(response);
}

export async function fetchIngestionJob(jobId: string): Promise<IngestionJob> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/ingestion/jobs/${jobId}`,
    { headers: adminHeaders() }
  );
  return parseJsonResponse<IngestionJob>(response);
}

export async function fetchAdminFeedback(signal?: AbortSignal): Promise<FeedbackItem[]> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/feedback`,
    { headers: adminHeaders(), signal },
    signal
  );
  return parseJsonResponse<FeedbackItem[]>(response);
}

export async function runRetrievalPlayground(
  question: string,
  topK: number,
  regulationType?: string,
  year?: number,
  legalStatus?: string
): Promise<RetrievalPlaygroundResponse> {
  const response = await fetchWithAuthRetry(`${API_URL}/admin/retrieval/search`, {
    method: "POST",
    headers: adminHeaders(),
    body: JSON.stringify({
      question,
      top_k: topK,
      regulation_type: regulationType ?? null,
      year: year ?? null,
      legal_status: legalStatus ?? null,
    }),
  });
  return parseJsonResponse<RetrievalPlaygroundResponse>(response);
}

export interface AdminUploadResult {
  upload_id: string;
  document_id: string;
  file_name: string;
  topic: string;
  status: string;
  sha256: string;
  storage_url: string;
}

export async function uploadAdminDocument(
  file: File,
  topic: string
): Promise<AdminUploadResult> {
  const query = new URLSearchParams({ file_name: file.name, topic });
  const response = await fetchWithAuthRetry(`${API_URL}/admin/documents/upload?${query}`, {
    method: "POST",
    headers: adminHeaders(false),
    body: file,
  });
  return parseJsonResponse<AdminUploadResult>(response);
}

export async function fetchEvaluationDatasets(signal?: AbortSignal): Promise<EvaluationDataset[]> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/evaluation/datasets`,
    { headers: adminHeaders(), signal },
    signal
  );
  return parseJsonResponse<EvaluationDataset[]>(response);
}

export async function seedEvaluationDataset(): Promise<EvaluationDataset> {
  const response = await fetchWithAuthRetry(`${API_URL}/evaluation/datasets/seed`, {
    method: "POST",
    headers: adminHeaders(),
  });
  return parseJsonResponse<EvaluationDataset>(response);
}

export async function createEvaluationRun(payload: {
  dataset_id: string;
  experiment_modes: string[];
  top_k: number;
}): Promise<EvaluationRunDetail> {
  const response = await fetchWithAuthRetry(`${API_URL}/evaluation/runs`, {
    method: "POST",
    headers: adminHeaders(),
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<EvaluationRunDetail>(response);
}

export async function fetchEvaluationRuns(signal?: AbortSignal): Promise<EvaluationRunSummary[]> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/evaluation/runs`,
    { headers: adminHeaders(), signal },
    signal
  );
  return parseJsonResponse<EvaluationRunSummary[]>(response);
}

export async function fetchEvaluationRun(
  runId: string,
  signal?: AbortSignal
): Promise<EvaluationRunDetail> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/evaluation/runs/${runId}`,
    { headers: adminHeaders(), signal },
    signal
  );
  return parseJsonResponse<EvaluationRunDetail>(response);
}
