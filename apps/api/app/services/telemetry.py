from __future__ import annotations

from contextlib import contextmanager

try:
    from prometheus_client import Counter, Histogram
except ImportError:  # pragma: no cover - optional in minimal development installs
    Counter = Histogram = None

if Histogram is not None:
    RAG_STAGE_LATENCY = Histogram(
        "kerjapedia_rag_stage_seconds",
        "Latency for each RAG pipeline stage.",
        ["stage", "provider"],
    )
    RAG_OUTCOMES = Counter(
        "kerjapedia_rag_outcomes_total",
        "RAG answers, refusals, failures, and verification outcomes.",
        ["outcome"],
    )
    RAG_PROVIDER_ERRORS = Counter(
        "kerjapedia_rag_provider_errors_total",
        "Provider failures by pipeline stage and provider.",
        ["stage", "provider"],
    )
    RAG_REQUESTS = Counter(
        "kerjapedia_rag_requests_total",
        "Completed RAG requests by verified answer and release version.",
        ["status", "prompt_version", "answer_version", "index_release"],
    )
    RAG_TOKEN_USAGE = Counter(
        "kerjapedia_rag_tokens_total",
        "LLM token usage by kind and model.",
        ["kind", "model"],
    )
    RAG_CLAIM_VERIFICATION = Counter(
        "kerjapedia_rag_claim_verification_total",
        "Claim verification decisions.",
        ["result", "verifier"],
    )
    RAG_RETRIEVED_VERSIONS = Counter(
        "kerjapedia_rag_retrieved_versions_total",
        "Retrieved source versions and legal status.",
        ["document_version", "legal_status", "index_release"],
    )
    RAGAS_FAITHFULNESS = Histogram(
        "kerjapedia_ragas_faithfulness_score",
        "RAGAS faithfulness score from online evaluation.",
        buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    )
    RAGAS_EVAL_TOTAL = Counter(
        "kerjapedia_ragas_eval_total",
        "RAGAS online evaluation attempts.",
        ["status"],
    )
    RAG_USER_BEHAVIOR = Counter(
        "kerjapedia_rag_user_behavior_total",
        "User behavior signals per request.",
        ["topic", "is_followup"],
    )
    RAG_REQUEST_LATENCY = Histogram(
        "kerjapedia_rag_request_seconds",
        "End-to-end request latency.",
        buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 15.0, 30.0],
    )
else:
    RAG_STAGE_LATENCY = None
    RAG_OUTCOMES = None
    RAG_PROVIDER_ERRORS = None
    RAG_REQUESTS = None
    RAG_TOKEN_USAGE = None
    RAG_CLAIM_VERIFICATION = None
    RAG_RETRIEVED_VERSIONS = None
    RAGAS_FAITHFULNESS = None
    RAGAS_EVAL_TOTAL = None
    RAG_USER_BEHAVIOR = None
    RAG_REQUEST_LATENCY = None


def record_ragas_faithfulness(score: float) -> None:
    if RAGAS_FAITHFULNESS is not None:
        RAGAS_FAITHFULNESS.observe(score)


def record_ragas_eval(status: str) -> None:
    if RAGAS_EVAL_TOTAL is not None:
        RAGAS_EVAL_TOTAL.labels(status=status).inc()


def record_user_behavior(topic: str, is_followup: bool) -> None:
    if RAG_USER_BEHAVIOR is not None:
        RAG_USER_BEHAVIOR.labels(
            topic=topic or "unknown",
            is_followup=str(is_followup).lower(),
        ).inc()


def observe_request_latency(elapsed_seconds: float) -> None:
    if RAG_REQUEST_LATENCY is not None:
        RAG_REQUEST_LATENCY.observe(elapsed_seconds)


def observe_stage(stage: str, provider: str, elapsed_seconds: float) -> None:
    if RAG_STAGE_LATENCY is not None:
        RAG_STAGE_LATENCY.labels(stage=stage, provider=provider).observe(elapsed_seconds)


def record_outcome(outcome: str) -> None:
    if RAG_OUTCOMES is not None:
        RAG_OUTCOMES.labels(outcome=outcome).inc()


def record_provider_error(stage: str, provider: str) -> None:
    if RAG_PROVIDER_ERRORS is not None:
        RAG_PROVIDER_ERRORS.labels(stage=stage, provider=provider).inc()


def observe_rag_completion(answer, retrieval) -> None:
    release_id = retrieval.index_release_id if retrieval else None
    release_label = release_id or "development"
    if RAG_REQUESTS is not None:
        RAG_REQUESTS.labels(
            status=answer.answer_status,
            prompt_version=answer.prompt_version_id,
            answer_version=answer.answer_version,
            index_release=release_label,
        ).inc()
    if RAG_TOKEN_USAGE is not None:
        usage = answer.debug.get("token_usage", {})
        model = answer.debug.get("llm_model", "non_llm")
        for kind in ("prompt_tokens", "completion_tokens"):
            RAG_TOKEN_USAGE.labels(kind=kind, model=model).inc(int(usage.get(kind, 0) or 0))
    if RAG_CLAIM_VERIFICATION is not None:
        verifier = answer.debug.get("verifier_model", "configured")
        for claim in answer.claims:
            result = "supported" if claim.supported else "unsupported"
            RAG_CLAIM_VERIFICATION.labels(result=result, verifier=verifier).inc()
    if RAG_RETRIEVED_VERSIONS is not None and retrieval is not None:
        for item in retrieval.results:
            RAG_RETRIEVED_VERSIONS.labels(
                document_version=str(item.document.document_version or "unknown"),
                legal_status=item.document.legal_status,
                index_release=release_label,
            ).inc()


def configure_telemetry(service_name: str, endpoint: str = "") -> None:
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return
    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)


@contextmanager
def trace_stage(stage: str, provider: str):
    try:
        from opentelemetry import trace
    except ImportError:
        trace = None
    if trace is None:
        yield
        return
    tracer = trace.get_tracer("kerjapedia.rag")
    with tracer.start_as_current_span(
        f"rag.{stage}",
        attributes={"rag.stage": stage, "rag.provider": provider},
    ):
        yield
