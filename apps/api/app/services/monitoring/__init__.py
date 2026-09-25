"""System Monitoring — application/API/dependency health, not RAG quality.

Boundary: `/admin/system` watches uptime, latency, errors, logs, traces,
dependency latency, and alerts. RAG quality (recall, faithfulness, retrieval
analysis, tokens, cost) stays on `/admin/observability`. Per §15, retrieval
and generation latency may appear in both, with different context: here as
service-performance spans, there as pipeline analysis.
"""

from app.services.monitoring.alerts import ALERT_RULES, evaluate_alerts
from app.services.monitoring.collector import (
    PROCESS_STARTED_AT,
    classify_error,
    cleanup_monitoring,
    histogram_percentile,
    merge_histograms,
    persist_request_observation,
    process_uptime_seconds,
    record_dependency_probe,
    record_http_request,
    record_rate_limited,
    route_template,
    write_system_log,
)
from app.services.monitoring.probes import probe_all_services
from app.services.monitoring.tracing import (
    end_span,
    finish_trace,
    get_trace_id,
    maybe_persist_trace,
    start_span,
    start_trace,
)

__all__ = [
    "ALERT_RULES",
    "PROCESS_STARTED_AT",
    "classify_error",
    "cleanup_monitoring",
    "end_span",
    "evaluate_alerts",
    "finish_trace",
    "get_trace_id",
    "histogram_percentile",
    "maybe_persist_trace",
    "merge_histograms",
    "probe_all_services",
    "persist_request_observation",
    "process_uptime_seconds",
    "record_dependency_probe",
    "record_http_request",
    "record_rate_limited",
    "route_template",
    "start_span",
    "start_trace",
    "write_system_log",
]
