"""Release manifests, artifact checksums, and write fencing.

- A release manifest travels with the index: what fills a namespace,
  from which build and model space, counted and signed by whom.
- Artifact files load only when checksums match the manifest.
- Concurrent builds fence per document: a second owner is refused
  explicitly instead of interleaving deletes and upserts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.services.rag.indexing.schemas import ReleaseManifest


def build_release_manifest(
    *,
    index_name: str,
    namespace: str,
    build_id: str,
    model_space: str,
    vector_count: int,
    document_ids: list[str],
    created_by: str = "",
    created_at: datetime | None = None,
) -> ReleaseManifest:
    """Assemble a release receipt for a freshly filled namespace."""
    return ReleaseManifest(
        index_name=index_name,
        namespace=namespace,
        build_id=build_id,
        model_space=model_space,
        vector_count=vector_count,
        document_ids=tuple(sorted(document_ids)),
        created_at=created_at or datetime.now(UTC),
        created_by=created_by,
    )


def verify_release_manifest(
    manifest: ReleaseManifest,
    *,
    vector_count: int,
    model_space: str,
) -> list[str]:
    """Mismatch reasons against live index state. Empty means agreement."""
    problems = []
    if vector_count != manifest.vector_count:
        problems.append(
            f"vector_count drifted: manifest {manifest.vector_count}, index {vector_count}"
        )
    if model_space != manifest.model_space:
        problems.append(
            f"model_space changed: manifest {manifest.model_space}, index {model_space}"
        )
    return problems


def write_artifact_manifest(directory: Path, files: dict[str, bytes]) -> Path:
    """Write files plus a checksum manifest beside them."""
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, content in files.items():
        (directory / name).write_bytes(content)
        manifest[name] = hashlib.sha256(content).hexdigest()
    manifest_path = directory / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def load_verified_artifact(directory: Path, name: str) -> bytes:
    """Load an artifact file only when its checksum matches the manifest."""
    manifest = json.loads((directory / "MANIFEST.json").read_text(encoding="utf-8"))
    content = (directory / name).read_bytes()
    expected = manifest.get(name)
    if expected != hashlib.sha256(content).hexdigest():
        raise ValueError(f"Artifact checksum mismatch: {name}")
    return content


class FenceRegistry:
    """Per-document write fences: one owner at a time, leases expire."""

    def __init__(self) -> None:
        self._holders: dict[str, tuple[str, datetime]] = {}

    def acquire(
        self, document_id: str, owner: str, now: datetime, ttl_seconds: int = 3600
    ) -> bool:
        """Take the fence; False when a live lease belongs to someone else."""
        holder = self._holders.get(document_id)
        if holder is not None:
            holder_owner, expires_at = holder
            if holder_owner != owner and expires_at > now:
                return False
        self._holders[document_id] = (owner, now + timedelta(seconds=ttl_seconds))
        return True

    def release(self, document_id: str, owner: str) -> bool:
        """Release your own fence; strangers cannot release it."""
        holder = self._holders.get(document_id)
        if holder is None or holder[0] != owner:
            return False
        del self._holders[document_id]
        return True
