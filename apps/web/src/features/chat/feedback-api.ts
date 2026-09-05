import { API_URL } from "@/lib/api-client";
import { fetchWithAuthRetry } from "@/features/auth";
import { chatHeaders } from "./request-headers";

export type FeedbackRating = "helpful" | "not_helpful";
export type FeedbackIssue =
  "citation_incorrect" | "answer_incomplete" | "outdated_regulation" | "other";

export async function submitFeedback(payload: {
  question: string;
  rating: FeedbackRating;
  answer_id?: string;
  conversation_id?: string;
  issue_category?: FeedbackIssue;
  comment?: string;
}): Promise<void> {
  const response = await fetchWithAuthRetry(`${API_URL}/feedback`, {
    method: "POST",
    headers: chatHeaders(true),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Feedback belum dapat disimpan.");
  }
}
