from datetime import UTC, datetime, timedelta
from pathlib import Path

import fitz
import pytest

from app.services.rag.collection import (
    SourceRecord,
    SourceRegistry,
    check_eligibility,
    collect_document,
    evaluate_freshness,
    merge_collections,
    register_checksum,
    resolve_conflict,
    retrieval_topics,
    suggest_topics,
    verify_topics,
)
from app.services.rag.collection.schemas import ChecksumEvent, CollectedDocument


def make_pdf(path: Path, text: str = "Pasal 1 Ketentuan umum ketenagakerjaan.") -> Path:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()
    return path


def sample_document(**overrides) -> CollectedDocument:
    now = datetime.now(UTC)
    base = {
        "document_id": "PP-35-2021",
        "title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
        "source_id": "bpk",
        "origin": "curated",
        "verification_status": "verified",
        "last_verified_at": now,
        "sha256": "a" * 64,
    }
    base.update(overrides)
    return CollectedDocument(**base)


def test_collects_valid_pdf_with_checksum_history(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "pp35.pdf")

    document, verdict = collect_document(
        pdf, document_id="PP-35-2021", title="PP 35/2021", source_id="bpk"
    )

    assert verdict.eligible is True
    assert verdict.quarantined is False
    assert document.page_count == 1
    assert len(document.checksum_history) == 1
    assert document.checksum_history[0].sha256 == document.sha256


def test_quarantines_non_pdf_without_crashing(tmp_path: Path) -> None:
    fake = tmp_path / "doc.pdf"
    fake.write_text("bukan pdf", encoding="utf-8")

    verdict = check_eligibility(fake)

    assert verdict.eligible is False
    assert verdict.quarantined is True
    assert verdict.issues[0].code == "bad_magic"


def test_quarantines_encrypted_pdf_without_crashing(tmp_path: Path) -> None:
    locked = tmp_path / "locked.pdf"
    document = fitz.open()
    document.new_page()
    document.save(
        locked, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u"
    )
    document.close()

    verdict = check_eligibility(locked)

    assert verdict.eligible is False
    assert verdict.quarantined is True
    assert verdict.issues[0].code == "encrypted"


def test_scanned_pdf_without_text_stays_eligible_for_ocr(tmp_path: Path) -> None:
    document = fitz.open()
    document.new_page()
    blank = tmp_path / "scan.pdf"
    document.save(blank)
    document.close()

    verdict = check_eligibility(blank)

    assert verdict.eligible is True
    assert verdict.issues[0].code == "no_embedded_text"
    assert verdict.issues[0].fatal is False


def test_checksum_history_is_append_only() -> None:
    now = datetime.now(UTC)
    first = ChecksumEvent(
        sha256="a" * 64, size_bytes=10, collected_at=now, origin="curated"
    )
    document = sample_document(checksum_history=(first,))
    updated = register_checksum(document, "b" * 64, 12, "connector", now)

    assert [event.sha256 for event in updated.checksum_history] == ["a" * 64, "b" * 64]
    assert len(document.checksum_history) == 1


def test_verified_record_beats_unverified_upload_with_audit() -> None:
    registry = SourceRegistry(
        [SourceRecord(source_id="bpk", name="BPK", trust_score=0.9)]
    )
    current = sample_document(verification_status="verified", origin="curated")
    incoming = sample_document(verification_status="pending", origin="upload", sha256="c" * 64)

    winner, decision = resolve_conflict(current, incoming, registry)

    assert winner.origin == "curated"
    assert decision.rule == "verified_status"
    assert decision.document_id == "PP-35-2021"


def test_higher_trust_source_wins_between_verified_records() -> None:
    registry = SourceRegistry(
        [
            SourceRecord(source_id="bpk", name="BPK", trust_score=0.9),
            SourceRecord(source_id="mirror", name="Mirror", trust_score=0.4),
        ]
    )
    current = sample_document(source_id="mirror", origin="upload", sha256="d" * 64)
    incoming = sample_document(source_id="bpk", origin="connector", sha256="e" * 64)

    winner, decision = resolve_conflict(current, incoming, registry)

    assert winner.origin == "connector"
    assert decision.rule == "source_trust"


def test_merge_adds_new_documents_and_skips_identical_ones() -> None:
    registry = SourceRegistry()
    base = [sample_document()]
    same = sample_document(origin="upload")
    new = sample_document(document_id="UU-13-2003", origin="upload", sha256="f" * 64)

    merged, decisions = merge_collections(base, [same, new], registry)

    assert {document.document_id for document in merged} == {"PP-35-2021", "UU-13-2003"}
    assert decisions == []


def test_unverified_topics_stay_out_of_retrieval_signals() -> None:
    suggested = suggest_topics("PP Nomor 35 Tahun 2021 tentang PKWT dan kompensasi")

    assert {assignment.topic for assignment in suggested} >= {"pkwt"}
    assert all(assignment.verified is False for assignment in suggested)

    document = sample_document(topics=tuple(suggested))
    assert retrieval_topics(document) == []

    verified = verify_topics(document, ["pkwt"], reviewer="reviewer-1")
    assert retrieval_topics(verified) == ["pkwt"]


def test_waktu_kerja_is_a_first_class_verified_topic() -> None:
    suggested = suggest_topics("UU tentang Waktu Kerja, Lembur, dan Cuti Tahunan")

    assert {assignment.topic for assignment in suggested} >= {"waktu_kerja"}

    document = sample_document(topics=tuple(suggested))
    verified = verify_topics(document, ["waktu_kerja"], reviewer="reviewer-1")
    assert retrieval_topics(verified) == ["waktu_kerja"]


def test_unknown_topic_is_refused() -> None:
    document = sample_document()

    with pytest.raises(ValueError, match="Unknown topics"):
        verify_topics(document, ["hukum_rimba"], reviewer="reviewer-1")


def test_freshness_states_drive_ranking_actions() -> None:
    now = datetime.now(UTC)

    assert evaluate_freshness(now - timedelta(days=10), now).state == "fresh"
    due = evaluate_freshness(now - timedelta(days=120), now)
    assert due.state == "due"
    assert due.action == "schedule_reverification"
    stale = evaluate_freshness(now - timedelta(days=200), now)
    assert stale.state == "stale"
    assert stale.action == "demote_in_ranking"
    never = evaluate_freshness(None, now)
    assert never.state == "due"
    assert never.action == "verify_before_production_use"


def test_official_url_gate_accepts_only_https_government_hosts() -> None:
    registry = SourceRegistry(
        [
            SourceRecord(
                source_id="bpk",
                name="BPK",
                allowed_domains=["peraturan.bpk.go.id"],
            )
        ]
    )

    assert registry.is_official_url("https://peraturan.bpk.go.id/Details/161904") is True
    assert registry.is_official_url("http://peraturan.bpk.go.id/Details/161904") is False
    assert registry.is_official_url("https://example.com/pp-35") is False
    assert registry.is_official_url(None) is False
