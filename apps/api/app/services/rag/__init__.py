"""Next-generation RAG services (clean-room rewrite).

The legacy ``ingestion`` / ``retrieval`` / ``answering`` packages stay
untouched for review. New code lives here, built from the verified
lessons of the audit:

- collection carries provenance, checksum history, and freshness;
- extraction detects its own broken output and escalates to OCR;
- every destructive step is guarded and audited;
- ingestion ends with a validation stage (recall probes), not hope.
"""
