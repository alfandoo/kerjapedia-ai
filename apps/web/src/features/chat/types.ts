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

export type AnswerClaim = {
  text: string;
  cited_chunk_ids: string[];
  supported?: boolean;
};

export type AnswerPayload = {
  query: string;
  answer: string;
  citations: Citation[];
  claims?: AnswerClaim[];
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

export type AskResponse = {
  conversation_id: string;
  answer: AnswerPayload;
  latency_ms: number;
  retrieval_score: number | null;
  token_usage: {
    prompt_tokens: number;
    completion_tokens: number;
  };
};

export type ConversationSummary = {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
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
