from __future__ import annotations

import json
import shutil
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

    def document_dir(self, document_id: str, version: int) -> Path:
        return self.root / "documents" / document_id / f"v{version}"

    def raw_pdf_path(self, document_id: str, version: int) -> Path:
        return self.document_dir(document_id, version) / "raw" / "source.pdf"

    def write_json(self, relative_path: Path, payload: Any) -> str:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path.as_posix()

    def copy_raw_pdf(self, source: Path, document_id: str, version: int) -> str:
        target = self.raw_pdf_path(document_id, version)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target.as_posix()
