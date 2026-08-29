import { API_URL, parseJsonResponse } from "@/lib/api-client";
import { getStoredSession } from "@/features/auth";
import { fetchWithAuthRetry } from "@/features/auth";
import type {
  AdminOverview,
  AdminRelationship,
  AdminStats,
  AdminSettings,
  AdminUploadResult,
  AuditLogEntry,
  EvaluationDataset,
  EvaluationRunDetail,
  EvaluationRunSummary,
  FeedbackItem,
  IngestionJob,
  RetrievalPlaygroundResponse,
} from "../types";
function adminHeaders(contentType = true): HeadersInit {
  const session = getStoredSession();
  return {
    ...(contentType ? { "Content-Type": "application/json" } : {}),
    ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}),
  };
}

export async function fetchAdminStats(signal?: AbortSignal): Promise<AdminStats> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/stats`,
    { headers: adminHeaders() },
    signal
  );
  return parseJsonResponse<AdminStats>(response);
}

export async function fetchAdminSettings(signal?: AbortSignal): Promise<AdminSettings> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/settings`,
    { headers: adminHeaders() },
    signal
  );
  return parseJsonResponse<AdminSettings>(response);
}

export async function fetchAuditLogs(limit = 100, signal?: AbortSignal): Promise<AuditLogEntry[]> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/audit-logs?limit=${limit}`,
    { headers: adminHeaders() },
    signal
  );
  return parseJsonResponse<AuditLogEntry[]>(response);
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
  const response = await fetchWithAuthRetry(`${API_URL}/ingestion/jobs/${jobId}`, {
    headers: adminHeaders(),
  });
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

export async function uploadAdminDocument(file: File, topic: string): Promise<AdminUploadResult> {
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

export { clearStoredSession } from "@/features/auth";
export { signOut } from "@/features/auth";

export type { AdminSettings, AdminUploadResult, AuditLogEntry } from "../types";
