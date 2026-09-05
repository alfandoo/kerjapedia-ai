import { API_URL, parseJsonResponse } from "@/lib/api-client";
import { fetchWithAuthRetry } from "@/features/auth/api";
import type { DocumentSearchFilters, DocumentSummary } from "./types";

export async function fetchDocuments(signal?: AbortSignal): Promise<DocumentSummary[]> {
  const response = await fetchWithAuthRetry(`${API_URL}/documents`, {}, signal);
  const documents = await parseJsonResponse<DocumentSummary[]>(response);
  return documents.map((document) => ({
    ...document,
    pdf_url: documentPdfUrl(document.document_id),
  }));
}

export function documentPdfUrl(documentId: string): string {
  return `/api/backend/documents/${encodeURIComponent(documentId)}/pdf`;
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
  const response = await fetchWithAuthRetry(`${API_URL}/documents${query ? `?${query}` : ""}`, {}, signal);
  const documents = await parseJsonResponse<DocumentSummary[]>(response);
  return documents.map((document) => ({
    ...document,
    pdf_url: documentPdfUrl(document.document_id),
  }));
}

export async function fetchDocumentDetail(documentId: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_URL}/documents/${encodeURIComponent(documentId)}`, {
    cache: "no-store",
  });
  return parseJsonResponse<Record<string, unknown>>(response);
}
