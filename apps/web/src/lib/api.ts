import type {
  AdminOverview,
  AdminRelationship,
  AskResponse,
  DocumentSummary,
  FeedbackItem,
  IngestionJob,
  RetrievalPlaygroundResponse,
  UserSession,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export function getStoredSession(): UserSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem("kerjapedia-session");
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      conversation_id: conversationId,
      top_k: 5,
    }),
    signal,
  });
  return parseJsonResponse<AskResponse>(response);
}

export async function fetchDocuments(signal?: AbortSignal): Promise<DocumentSummary[]> {
  const response = await fetch(`${API_URL}/documents`, { signal });
  return parseJsonResponse<DocumentSummary[]>(response);
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
