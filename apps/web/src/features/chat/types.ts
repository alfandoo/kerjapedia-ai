export type Citation = {
  citation_id: string;
  chunk_id: string;
  document_id: string;
  document_title: string;
  short_title: string;
  legal_status: string;
  chapter: string | null;
  section: string | null;
  article: string | null;
  paragraph: string | null;
  page_start: number;
  page_end: number;
  quote: string;
  source_url: string;
  local_file: string | null;
  retrieval_score: number;
  rerank_score: number;
};

export type RelatedDocument = {
  document_id: string;
  title: string;
  short_title: string;
  legal_status: string;
  source_url: string;
};

export type AnswerPayload = {
  query: string;
  answer: string;
  citations: Citation[];
  confidence: number;
  related_documents: RelatedDocument[];
  refusal_reason: string | null;
  clarification_question: string | null;
  disclaimer: string;
  prompt_version_id: string;
  retrieved_chunk_ids: string[];
  warnings: string[];
  answer_status?: "answered" | "refused" | "clarification" | "temporarily_unavailable";
  answer_version?: string;
  trace_id?: string | null;
};

export type ReasoningMode = "fast" | "standard" | "deep";

export type WorkProfile = {
  province: string | null;
  employment_status: "PKWT" | "PKWTT" | null;
  start_date: string | null;
  monthly_wage: number | null;
};


export type TokenUsageSnapshot = {
  usage_date: string;
  timezone: "Asia/Jakarta";
  reset_at: string;
  limit_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  used_tokens: number;
  reserved_tokens: number;
  remaining_tokens: number;
  estimated_tokens: number;
};

export type AskResponse = {
  conversation_id: string;
  answer: AnswerPayload;
  latency_ms: number;
  retrieval_score: number | null;
  token_usage: {
    prompt_tokens: number;
    completion_tokens: number;
  };
  reasoning_mode: ReasoningMode;
};

export type ConversationSummary = {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  personalized_mode: boolean;
};

export type ConversationMessage = {
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
  metadata: {
    answer?: AnswerPayload;
    retrieval_score?: number | null;
    token_usage?: {
      prompt_tokens: number;
      completion_tokens: number;
    };
  };
};

export type ConversationDetail = {
  conversation_id: string;
  title: string;
  messages: ConversationMessage[];
  personalized_mode: boolean;
  created_at: string;
  updated_at: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  answer?: AnswerPayload;
  streaming?: boolean;
  status?: string;
};
