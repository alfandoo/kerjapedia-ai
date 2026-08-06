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

export type DocumentSummary = {
  document_id: string;
  title: string;
  short_title: string;
  regulation_type: string;
  number: number;
  year: number;
  legal_status: string;
  topics: string[];
  source_url: string;
  pdf_url: string;
};

export type UserSession = {
  access_token: string;
  refresh_token?: string;
  user: {
    user_id: string;
    email: string;
    name: string;
    roles: string[];
  };
};

export type AdminRelationship = {
  from_document_id: string;
  to_document_id: string;
  relationship_type: "amended_by" | "implements" | "implemented_by" | "related_to";
  confidence: "low" | "medium" | "high";
  notes?: string | null;
};

export type AdminVersion = {
  version: number;
  status: "draft" | "published";
  created_at: string;
  created_by: string;
};

export type AdminDocument = DocumentSummary & {
  issuer: string;
  verification_status: string;
  ingestion_status: "completed" | "needs_review" | "failed" | "running" | "queued";
  chunk_count: number;
  publication_status: "published" | "draft";
  version: number;
  updated_at: string;
  updated_by: string;
  relationships: AdminRelationship[];
  versions: AdminVersion[];
  last_error: string | null;
};

export type AdminOverview = {
  summary: {
    documents: number;
    published: number;
    needs_review: number;
    failed: number;
  };
  documents: AdminDocument[];
};

export type IngestionJob = {
  job_id: string;
  document_id: string;
  status: "running" | "completed" | "needs_review" | "failed" | "queued";
  created_at: string;
  updated_at: string;
  error?: string | null;
  result?: { chunk_count?: number; warnings?: string[] } | null;
};

export type FeedbackItem = {
  feedback_id: string;
  user_id: string;
  question: string;
  rating: "helpful" | "not_helpful";
  issue_category?: string | null;
  comment?: string | null;
  created_at: string;
};

export type RetrievalPlaygroundResult = {
  chunk_id: string;
  document_id: string;
  short_title: string;
  article: string | null;
  page_start: number;
  page_end: number;
  quote: string;
  lexical_score: number;
  semantic_score: number;
  rerank_score: number;
  final_score: number;
  match_reasons: string[];
};

export type AdminStats = {
  documents: {
    total: number;
    published: number;
    needs_review: number;
    failed: number;
  };
  users: number;
  conversations: number;
  messages: number;
  feedback: {
    total: number;
    helpful: number;
    not_helpful: number;
  };
  ingestion_jobs: {
    total: number;
    recent: {
      job_id: string;
      document_id: string;
      status: string;
      created_at: string;
    }[];
  };
};

export type RetrievalPlaygroundResponse = {
  query: string;
  latency_ms: number;
  warnings: string[];
  should_refuse: boolean;
  results: RetrievalPlaygroundResult[];
};
