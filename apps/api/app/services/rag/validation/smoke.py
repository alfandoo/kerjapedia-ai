"""Post-deploy smoke probes: the live namespace must answer spot checks.

Scheduled by the operator (cron/CI), not by the index: same probe
shapes as build validation, sampled chunk expectations, latency caps.
Failures name names — paging content, not archaeology.
"""

from __future__ import annotations

from collections.abc import Callable

from app.services.rag.validation.schemas import Probe, ProbeResult

# smoke_fn(question, top_k) -> (ranked chunk IDs, latency_ms).
SmokeFn = Callable[[str, int], tuple[list[str], int]]


def run_smoke(
    check: SmokeFn,
    probes: list[Probe],
    top_k: int = 3,
    max_latency_ms: int = 30000,
) -> list[ProbeResult]:
    """Run live spot checks; slowness fails like absence does."""
    results = []
    for probe in probes:
        ranked, latency_ms = check(probe.query, top_k)
        hit = next(
            (chunk_id for chunk_id in probe.expected_chunk_ids if chunk_id in ranked),
            None,
        )
        if hit is None:
            results.append(
                ProbeResult(
                    probe_id=probe.probe_id,
                    passed=False,
                    detail=f"live index missed {list(probe.expected_chunk_ids)}",
                    latency_ms=latency_ms,
                )
            )
        elif latency_ms > max_latency_ms:
            results.append(
                ProbeResult(
                    probe_id=probe.probe_id,
                    passed=False,
                    detail=f"hit {hit} but {latency_ms}ms over {max_latency_ms}ms",
                    latency_ms=latency_ms,
                )
            )
        else:
            results.append(
                ProbeResult(
                    probe_id=probe.probe_id,
                    passed=True,
                    detail=f"{hit} live in {latency_ms}ms",
                    latency_ms=latency_ms,
                )
            )
    return results
