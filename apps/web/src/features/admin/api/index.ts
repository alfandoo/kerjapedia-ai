import { API_URL, parseJsonResponse } from "@/lib/api-client";
import { fetchWithAuthRetry } from "@/features/auth";
import type {
  AdminMetrics,
  AdminOverview,
  AlertEvent,
  AlertRule,
  DailyUsagePoint,
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
  SystemLogEntry,
  SystemOverview,
  SystemServiceStatus,
  SystemTraceDetail,
  SystemTraceSummary,
} from "../types";
function adminHeaders(contentType = true): HeadersInit {
  return {
    ...(contentType ? { "Content-Type": "application/json" } : {}),
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

export async function fetchDailyUsage(
  days = 30,
  signal?: AbortSignal
): Promise<{ days: number; points: DailyUsagePoint[] }> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/usage/daily?days=${days}`,
    { headers: adminHeaders() },
    signal
  );
  return parseJsonResponse<{ days: number; points: DailyUsagePoint[] }>(response);
}

export async function fetchAdminMetrics(signal?: AbortSignal): Promise<AdminMetrics> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/metrics`,
    { headers: adminHeaders(), signal },
    signal
  );
  return parseJsonResponse<AdminMetrics>(response);
}

export async function fetchAdminSettings(signal?: AbortSignal): Promise<AdminSettings> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/settings`,
    { headers: adminHeaders() },
    signal
  );
  return parseJsonResponse<AdminSettings>(response);
}

export async function fetchAuditLogs(
  page = 1,
  limit = 10,
  signal?: AbortSignal
): Promise<{ entries: AuditLogEntry[]; total: number }> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/audit-logs?page=${page}&limit=${limit}`,
    { headers: adminHeaders() },
    signal
  );
  return parseJsonResponse<{ entries: AuditLogEntry[]; total: number }>(response);
}

export async function fetchRecentAuditLogs(
  limit = 5,
  signal?: AbortSignal
): Promise<AuditLogEntry[]> {
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
  payload: {
    legal_status: string;
    verification_status: string;
    topics: string[];
    source_url: string;
  }
): Promise<void> {
  const response = await fetchWithAuthRetry(`${API_URL}/admin/documents/${documentId}`, {
    method: "PATCH",
    headers: adminHeaders(),
    body: JSON.stringify(payload),
  });
  await parseJsonResponse(response);
}

export async function verifyDocument(
  documentId: string,
  verificationType: "source" | "legal",
  status: "verified" | "pending" | "rejected",
  evidenceUrl: string,
  notes?: string
): Promise<void> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/documents/${documentId}/verification`,
    {
      method: "POST",
      headers: adminHeaders(),
      body: JSON.stringify({
        verification_type: verificationType,
        status,
        evidence_url: evidenceUrl,
        notes,
      }),
    }
  );
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

export async function createIngestionJob(documentId: string, force = false): Promise<IngestionJob> {
  const response = await fetchWithAuthRetry(`${API_URL}/ingestion/jobs`, {
    method: "POST",
    headers: adminHeaders(),
    body: JSON.stringify({ document_id: documentId, persist_db: false, force }),
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

export async function fetchSystemOverview(
  sinceHours = 24,
  signal?: AbortSignal
): Promise<SystemOverview> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/system/overview?since_hours=${sinceHours}`,
    { headers: adminHeaders(), signal },
    signal
  );
  return parseJsonResponse<SystemOverview>(response);
}

export async function fetchSystemServices(
  signal?: AbortSignal
): Promise<{ services: SystemServiceStatus[] }> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/system/services`,
    { headers: adminHeaders(), signal },
    signal
  );
  return parseJsonResponse<{ services: SystemServiceStatus[] }>(response);
}

export async function fetchSystemLogs(
  params: {
    search?: string;
    level?: string;
    service?: string;
    status?: string;
    sinceHours?: number;
    limit?: number;
    offset?: number;
  } = {},
  signal?: AbortSignal
): Promise<{ entries: SystemLogEntry[]; total: number; response: Response }> {
  const query = new URLSearchParams();
  if (params.search) query.set("search", params.search);
  if (params.level) query.set("level", params.level);
  if (params.service) query.set("service", params.service);
  if (params.status) query.set("status", params.status);
  query.set("since_hours", String(params.sinceHours ?? 24));
  query.set("limit", String(params.limit ?? 50));
  query.set("offset", String(params.offset ?? 0));
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/system/logs?${query}`,
    { headers: adminHeaders(), signal },
    signal
  );
  const entries = await parseJsonResponse<SystemLogEntry[]>(response);
  return {
    entries,
    total: Number(response.headers.get("X-Total-Count") ?? entries.length),
    response,
  };
}

export async function fetchSystemLog(
  logId: string,
  signal?: AbortSignal
): Promise<SystemLogEntry> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/system/logs/${encodeURIComponent(logId)}`,
    { headers: adminHeaders(), signal },
    signal
  );
  return parseJsonResponse<SystemLogEntry>(response);
}

export async function fetchSystemTraces(
  params: {
    route?: string;
    status?: string;
    sinceHours?: number;
    limit?: number;
    offset?: number;
  } = {},
  signal?: AbortSignal
): Promise<{ entries: SystemTraceSummary[]; total: number }> {
  const query = new URLSearchParams();
  if (params.route) query.set("route", params.route);
  if (params.status) query.set("status", params.status);
  query.set("since_hours", String(params.sinceHours ?? 24));
  query.set("limit", String(params.limit ?? 50));
  query.set("offset", String(params.offset ?? 0));
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/system/traces?${query}`,
    { headers: adminHeaders(), signal },
    signal
  );
  const entries = await parseJsonResponse<SystemTraceSummary[]>(response);
  return {
    entries,
    total: Number(response.headers.get("X-Total-Count") ?? entries.length),
  };
}

export async function fetchSystemTrace(
  traceId: string,
  signal?: AbortSignal
): Promise<SystemTraceDetail> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/system/traces/${encodeURIComponent(traceId)}`,
    { headers: adminHeaders(), signal },
    signal
  );
  return parseJsonResponse<SystemTraceDetail>(response);
}

export async function fetchSystemAlerts(signal?: AbortSignal): Promise<{
  rules: AlertRule[];
  active: { rule: string; severity: string; message: string }[];
  recent: AlertEvent[];
}> {
  const response = await fetchWithAuthRetry(
    `${API_URL}/admin/system/alerts`,
    { headers: adminHeaders(), signal },
    signal
  );
  return parseJsonResponse<{
    rules: AlertRule[];
    active: { rule: string; severity: string; message: string }[];
    recent: AlertEvent[];
  }>(response);
}

export { clearStoredSession } from "@/features/auth";
export { signOut } from "@/features/auth";

export type { AdminSettings, AdminUploadResult, AuditLogEntry } from "../types";
