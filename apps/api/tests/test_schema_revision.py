from __future__ import annotations

import re
from pathlib import Path

from app.db.session import EXPECTED_SCHEMA_REVISION


def test_expected_schema_revision_matches_single_alembic_head() -> None:
    versions = Path(__file__).parents[1] / "alembic" / "versions"
    revisions: set[str] = set()
    down_revisions: set[str] = set()
    for path in versions.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        revision = re.search(r'^revision(?::[^=]+)?\s*=\s*"([^"]+)"', source, re.MULTILINE)
        down_revision = re.search(
            r'^down_revision(?::[^=]+)?\s*=\s*"([^"]+)"',
            source,
            re.MULTILINE,
        )
        if revision:
            revisions.add(revision.group(1))
        if down_revision:
            down_revisions.add(down_revision.group(1))

    assert revisions - down_revisions == {EXPECTED_SCHEMA_REVISION}
