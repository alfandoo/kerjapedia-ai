"""Document loading: read sources through typed loaders, validate at intake.

Loading bridges raw bytes and the collection records. Validation happens
here — at intake, not minutes later inside an ingestion job — by reusing
the collection eligibility checks.
"""

from app.services.rag.loading.intake import (
    MAX_UPLOAD_BYTES,
    intake_connector_file,
    intake_local_file,
    intake_upload,
)
from app.services.rag.loading.loaders import (
    BytesLoader,
    LoadedFile,
    Loader,
    LocalFileLoader,
)
from app.services.rag.loading.store import (
    sanitize_file_name,
    sanitize_identifier,
    store_layout_for,
)

__all__ = [
    "BytesLoader",
    "LoadedFile",
    "Loader",
    "LocalFileLoader",
    "MAX_UPLOAD_BYTES",
    "intake_connector_file",
    "intake_local_file",
    "intake_upload",
    "sanitize_file_name",
    "sanitize_identifier",
    "store_layout_for",
]
