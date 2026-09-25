import type { DocumentSummary } from "@/features/documents";

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
  source_verification_status: string;
  legal_review_status: string;
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
  elapsed_seconds?: number | null;
  avg_duration_seconds?: number | null;
};

export type FeedbackItem = {
  feedback_id: string;
  user_id: string;
  question: string;
  rating: "helpful" | "not_helpful";
  issue_category?: string | null;
  comment?: string | null;
  conversation_id?: string | null;
  answer_id?: string | null;
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

export type EvaluationMetricSet = {
  question_count: number;
  answerable_count: number;
  refusal_count: number;
  recall_at_5: number;
  mean_reciprocal_rank: number;
  citation_correctness: number;
  faithfulness: number;
  refusal_accuracy: number;
  hard_negative_recall_at_5: number;
};

export type EvaluationDatasetQuestion = {
  question_id: string;
  category: string;
  question: string;
  expected_answer: string;
  expected_document_ids: string[];
  expected_articles: string[];
  expected_topics: string[];
  should_refuse: boolean;
  hard_negative: boolean;
  status: string;
};

export type EvaluationDataset = {
  dataset_id: string;
  name: string;
  questions: EvaluationDatasetQuestion[];
  created_at: string;
};

export type EvaluationRunSummary = {
  run_id: string;
  dataset_id: string;
  release_id?: string | null;
  status: "pending" | "running" | "completed" | "failed" | string;
  progress_completed: number;
  progress_total: number;
  error?: string | null;
  created_at: string;
  metrics: Record<string, EvaluationMetricSet>;
};

export type EvaluationQuestionResult = {
  question_id: string;
  category: string;
  mode: string;
  recall_at_5: number | null;
  reciprocal_rank: number | null;
  citation_correctness: number | null;
  faithfulness: number | null;
  refusal_correct: boolean;
  actual_refuse: boolean;
  retrieved_document_ids: string[];
  retrieved_chunk_ids: string[];
  warnings: string[];
};

export type EvaluationExperiment = {
  mode: string;
  metrics: EvaluationMetricSet;
  per_topic: Record<string, EvaluationMetricSet>;
  results: EvaluationQuestionResult[];
};

export type EvaluationRunDetail = EvaluationRunSummary & {
  report?: {
    question_count: number;
    top_k: number;
    experiments: EvaluationExperiment[];
  };
};

export type HistogramStats = {
  count: number;
  sum: number;
  avg: number | null;
  p50: number | null;
  p95: number | null;
  p99: number | null;
};

export type AdminMetrics = {
  ragas_enabled: boolean;
  ragas_sample_rate: number;
  outcomes: Record<string, number>;
  requests: {
    total: number;
    by_status: Record<string, number>;
  };
  stage_latency: Record<string, HistogramStats>;
  request_latency: Partial<HistogramStats>;
  tokens: {
    prompt: number;
    completion: number;
    total: number;
    by_model: Record<string, { prompt: number; completion: number }>;
  };
  claims: {
    supported: number;
    unsupported: number;
    total: number;
    support_rate: number | null;
  };
  provider_errors: {
    total: number;
    by_stage: Record<string, number>;
    last_7_days: number;
  };
  ragas: {
    eval_total: Record<string, number>;
    faithfulness: Partial<HistogramStats>;
  };
  behavior: {
    total: number;
    followups: number;
    followup_ratio: number | null;
    by_topic: Record<string, number>;
  };
  retrieved: {
    total: number;
    by_legal_status: Record<string, number>;
  };
};

export type SystemOverview = {
  status: "healthy" | "degraded" | "critical" | string;
  uptime_seconds: number;
  window_hours: number;
  requests: {
    total: number;
    rate_per_minute: number;
    successful: number;
    failed_5xx: number;
    count_4xx: number;
    error_rate: number | null;
  };
  latency_ms: {
    avg_ms: number | null;
    p50_ms: number | null;
    p95_ms: number | null;
    p99_ms: number | null;
  };
  dependencies: Record<
    string,
    { status: string; latency_ms: number | null; error: string | null }
  >;
  dependency_latency_ms: Record<
    string,
    { avg_24h_ms: number | null; last_ms: number | null }
  >;
  recent_errors: SystemLogEntry[];
  active_alerts: { rule: string; severity: string; message: string }[];
};

export type SystemServiceStatus = {
  service: string;
  status: "healthy" | "degraded" | "down" | "unknown" | string;
  latency_ms: number | null;
  error: string | null;
  last_checked: string;
  avg_24h_ms: number | null;
  error_rate_24h: number | null;
  recent_incidents: {
    status: string;
    latency_ms: number | null;
    error: string | null;
    checked_at: string;
  }[];
};

export type SystemLogEntry = {
  log_id: string;
  timestamp: string;
  level: "debug" | "info" | "warn" | "error" | string;
  service: string;
  message: string;
  request_id: string | null;
  trace_id: string | null;
  route: string | null;
  status_code: number | null;
  duration_ms: number | null;
  error_type: string | null;
};

export type TraceSpan = {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  service: string;
  started_offset_ms: number;
  duration_ms: number | null;
  status: string;
  error?: string | null;
};

export type SystemTraceSummary = {
  trace_id: string;
  timestamp: string;
  route: string;
  duration_ms: number;
  status: string;
  span_count: number;
};

export type SystemTraceDetail = SystemTraceSummary & {
  spans: TraceSpan[];
};

export type AlertRule = {
  rule: string;
  severity: "warning" | "critical" | string;
  description: string;
};

export type AlertEvent = {
  alert_id: string;
  rule: string;
  severity: string;
  status: "firing" | "resolved" | string;
  message: string;
  created_at: string;
  resolved_at: string | null;
};

export type DailyUsagePoint = {
  date: string;
  messages: number;
  conversations: number;
  active_users: number;
};

export type AdminSettings = {
  app_name: string;
  app_version: string;
  admin_email: string;
  rate_limit_per_minute: number;
  vector_store: string;
  embedding_provider: string;
  llm_provider: string;
  session_expires_in_seconds: number;
};
export type AuditLogEntry = {
  audit_id: string;
  actor: string;
  actor_name: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
};
export type AdminUploadResult = {
  upload_id: string;
  document_id: string;
  file_name: string;
  topic: string;
  status: string;
  sha256: string;
  storage_url: string;
};
