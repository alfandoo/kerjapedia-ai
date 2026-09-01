from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    return value


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def document_dir(
        self,
        document_id: str,
        version: int,
        build_id: str | None = None,
    ) -> Path:
        version_dir = self.root / "documents" / document_id / f"v{version}"
        return version_dir / "builds" / build_id if build_id else version_dir

    def raw_pdf_path(
        self,
        document_id: str,
        version: int,
        build_id: str | None = None,
    ) -> Path:
        return self.document_dir(document_id, version, build_id) / "raw" / "source.pdf"

    def write_json(self, relative_path: Path, payload: Any) -> str:
        encoded = json.dumps(
            to_jsonable(payload),
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        return self.write_bytes(relative_path, encoded)

    def write_bytes(self, relative_path: Path, content: bytes) -> str:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "wb") as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        return path.as_posix()

    def append_jsonl(self, relative_path: Path, payloads: list[Any]) -> str:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as output:
            for payload in payloads:
                output.write(json.dumps(to_jsonable(payload), ensure_ascii=False) + "\n")
            output.flush()
            os.fsync(output.fileno())
        return path.as_posix()

    def copy_raw_pdf(
        self,
        source: Path,
        document_id: str,
        version: int,
        build_id: str | None = None,
    ) -> str:
        target = self.raw_pdf_path(document_id, version, build_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            temporary = target.with_suffix(".pdf.tmp")
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
        return target.as_posix()
