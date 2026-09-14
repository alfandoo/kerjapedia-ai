from app.services.rag.validation import (
    GoldenItem,
    Probe,
    ReleaseThresholds,
    decide_release,
    run_article_coverage_probe,
    run_golden,
    run_smoke,
    run_spot_probe,
    stratified_sample,
)


def search_fn_factory(index):
    def search(question, top_k):
        return index.get(question, [])[:top_k]

    return search


def test_spot_probe_passes_and_fails_on_rank() -> None:
    search = search_fn_factory({"q": ["c1", "c2", "c3"]})
    probe = Probe(probe_id="p1", kind="retrieval_spot", query="q", expected_chunk_ids=("c2",))

    passed = run_spot_probe(search, probe, top_k=3)
    assert passed.passed is True and "#2" in passed.detail

    missed = run_spot_probe(search, probe, top_k=1)
    assert missed.passed is False


def test_article_coverage_probe_rejects_empty_detection() -> None:
    result = run_article_coverage_probe("cov-empty", "DOC", set(), set())

    assert result.passed is False
    assert "no articles detected" in result.detail


def test_article_coverage_probe_catches_lost_pasals() -> None:
    result = run_article_coverage_probe(
        "cov-thr",
        "PERMENAKER-6-2016",
        {"Pasal 1", "Pasal 4", "Pasal 6"},
        {"Pasal 1", "Pasal 4", "Pasal 6"},
    )

    assert result.passed is False
    assert "[2, 3, 5]" in result.detail

    healthy = run_article_coverage_probe(
        "cov-ok", "DOC", {"Pasal 1", "Pasal 2"}, {"Pasal 1", "Pasal 2"}
    )
    assert healthy.passed is True

    amendment = run_article_coverage_probe(
        "cov-amd",
        "PP-51-2023",
        {"Pasal 23", "Pasal 24", "Pasal I"},
        {"Pasal 23", "Pasal 24", "Pasal I"},
        sequential_numbering=False,
    )
    assert amendment.passed is True


def test_golden_scores_recall_mrr_and_refusal() -> None:
    items = [
        GoldenItem(
            question_id="q1", question="kompensasi?", topic="pkwt",
            expected_document_ids=("PP-35-2021",),
        ),
        GoldenItem(
            question_id="q2", question="thr?", topic="thr",
            expected_document_ids=("PERMENAKER-6-2016",),
        ),
        GoldenItem(question_id="q3", question="pajak?", must_refuse=True),
    ]

    def retrieve(question, top_k):
        if question == "kompensasi?":
            return (
                ["PP-35-2021-v7-b27d08f641291-chunk-00021", "UU-6-2023-v1-abc-chunk-00001"],
                False,
            )
        if question == "thr?":
            return (["PP-36-2021-v1-xyz-chunk-00009"], False)
        return ([], True)

    report = run_golden(items, retrieve, top_k=5)

    assert report.recall_at_k == 0.5
    assert report.mrr == 0.5
    assert report.refusal_accuracy == 1.0
    assert report.by_topic == {"pkwt": 1.0, "thr": 0.0}
    assert "q2" in report.failures


def test_release_gate_blocks_on_breach() -> None:
    from app.services.rag.validation import GoldenReport, ProbeResult

    bad = decide_release(
        [ProbeResult(probe_id="p1", passed=False)],
        GoldenReport(recall_at_k=0.1, mrr=0.1, evaluated=4),
        ReleaseThresholds(),
    )
    assert bad.release == "no_go"
    assert any("blocking probes" in reason for reason in bad.reasons)
    assert any("recall_at_k" in reason for reason in bad.reasons)

    good = decide_release(
        [ProbeResult(probe_id="p1", passed=True)],
        GoldenReport(recall_at_k=0.9, mrr=0.8, refusal_accuracy=1.0, evaluated=4),
        ReleaseThresholds(),
    )
    assert good.release == "go"

    empty = decide_release([], GoldenReport(), ReleaseThresholds())
    assert empty.release == "needs_review"


def test_human_sampling_covers_topics_high_risk_first() -> None:
    items = [
        GoldenItem(question_id=f"{topic}-{risk}-{index}", question="?",
                   topic=topic, risk=risk)
        for topic in ("thr", "pkwt")
        for risk in ("low", "high")
        for index in range(3)
    ]

    sampled = stratified_sample(items, per_topic=2)

    assert len(sampled) == 4
    by_topic = {}
    for item in sampled:
        by_topic.setdefault(item.topic, []).append(item.risk)
    assert by_topic["thr"] == ["high", "high"]
    assert by_topic["pkwt"] == ["high", "high"]


def test_smoke_flags_missing_chunks_and_slowness() -> None:
    probes = [
        Probe(probe_id="s1", kind="retrieval_spot", query="q1", expected_chunk_ids=("c1",)),
        Probe(probe_id="s2", kind="retrieval_spot", query="q2", expected_chunk_ids=("c9",)),
        Probe(probe_id="s3", kind="retrieval_spot", query="q3", expected_chunk_ids=("c3",)),
    ]

    def check(question, top_k):
        table = {"q1": (["c1"], 120), "q2": (["c2"], 130), "q3": (["c3"], 99999)}
        return table[question]

    results = run_smoke(check, probes, top_k=3, max_latency_ms=1000)
    by_id = {result.probe_id: result for result in results}

    assert by_id["s1"].passed is True
    assert by_id["s2"].passed is False
    assert by_id["s3"].passed is False and "over 1000ms" in by_id["s3"].detail
