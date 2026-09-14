"""Pinecone backend implementing the vector-store interface.

Thin mapping only: all rules (verification, sizing, deletion guards)
live in the interface-level guards and apply unchanged.
"""

from __future__ import annotations

from app.services.rag.indexing.schemas import StoredVector


class PineconeVectorStore:
    """Pinecone index plus fixed namespace."""

    def __init__(
        self,
        api_key: str,
        index_name: str,
        dimension: int,
        metric: str = "dotproduct",
    ) -> None:
        self._api_key = api_key
        self._index_name = index_name
        self._dimension = dimension
        self._metric = metric
        self._index = None

    def _client_index(self):  # type: ignore[no-untyped-def]
        if self._index is None:
            try:
                from pinecone import Pinecone, ServerlessSpec
            except ImportError as exc:
                raise RuntimeError("pinecone is required for PineconeVectorStore.") from exc
            client = Pinecone(api_key=self._api_key)
            names = client.indexes.list().names()
            if self._index_name not in names:
                client.indexes.create(
                    name=self._index_name,
                    dimension=self._dimension,
                    metric=self._metric,
                    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
                )
            self._index = client.index(self._index_name)
        return self._index

    def upsert(self, vectors: list[StoredVector], namespace: str) -> int:
        payload = [
            {
                "id": vector.id,
                "values": list(vector.values),
                **(
                    {
                        "sparse_values": {
                            "indices": list(vector.sparse),
                            "values": list(vector.sparse.values()),
                        }
                    }
                    if vector.sparse
                    else {}
                ),
                "metadata": dict(vector.metadata),
            }
            for vector in vectors
        ]
        upserted = 0
        for start in range(0, len(payload), 100):
            response = self._client_index().upsert(
                vectors=payload[start : start + 100], namespace=namespace
            )
            upserted += int(getattr(response, "upserted_count", 0) or 0)
        return upserted

    def fetch(self, ids: list[str], namespace: str) -> dict[str, StoredVector]:
        response = self._client_index().fetch(ids=ids, namespace=namespace)
        found = getattr(response, "vectors", {}) or {}
        result = {}
        for chunk_id, record in found.items():
            values = getattr(record, "values", None)
            if values is None and isinstance(record, dict):
                values = record.get("values")
            metadata = getattr(record, "metadata", None)
            if metadata is None and isinstance(record, dict):
                metadata = record.get("metadata", {})
            result[chunk_id] = StoredVector(
                id=chunk_id,
                values=tuple(values or ()),
                metadata=dict(metadata or {}),
            )
        return result

    def delete_ids(self, ids: list[str], namespace: str) -> int:
        self._client_index().delete(ids=ids, namespace=namespace)
        return len(ids)

    def delete_by_filter(self, pinecone_filter: dict | None, namespace: str) -> int:
        if pinecone_filter:
            self._client_index().delete(namespace=namespace, filter=pinecone_filter)
            return -1
        self._client_index().delete(namespace=namespace, delete_all=True)
        return -1

    def count(self, namespace: str) -> int:
        stats = self._client_index().describe_index_stats()
        namespaces = getattr(stats, "namespaces", {}) or {}
        entry = namespaces.get(namespace)
        if entry is None:
            return 0
        if isinstance(entry, dict):
            return int(entry.get("vector_count", 0))
        return int(getattr(entry, "vector_count", 0))

    def sample_ids(self, namespace: str, limit: int) -> list[str]:
        ids: list[str] = []
        pagination_token: str | None = None
        while len(ids) < limit:
            args: dict = {"namespace": namespace, "limit": min(100, limit - len(ids))}
            if pagination_token:
                args["pagination_token"] = pagination_token
            response = self._client_index().list(**args)
            vectors = getattr(response, "vectors", None) or []
            for record in vectors:
                record_id = getattr(record, "id", None)
                if record_id is None and isinstance(record, dict):
                    record_id = record.get("id")
                if record_id:
                    ids.append(str(record_id))
            pagination_token = getattr(response, "pagination_token", None)
            if not pagination_token or not vectors:
                break
        return ids[:limit]

    def query(
        self,
        vector: list[float],
        top_k: int,
        namespace: str,
        pinecone_filter: dict | None = None,
    ) -> list[tuple[str, float]]:
        response = self._client_index().query(
            vector=vector,
            top_k=top_k,
            namespace=namespace,
            include_metadata=False,
            include_values=False,
            filter=pinecone_filter,
        )
        matches = getattr(response, "matches", []) or []
        result = []
        for match in matches:
            match_id = getattr(match, "id", None)
            if match_id is None and isinstance(match, dict):
                match_id = match.get("id")
            score = getattr(match, "score", None)
            if score is None and isinstance(match, dict):
                score = match.get("score")
            result.append((str(match_id), float(score or 0.0)))
        return result
