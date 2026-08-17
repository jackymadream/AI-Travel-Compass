"""
Qdrant helpers for Travel Compass collections.

Phase 5.1 — ``travel_pois`` upsert / indexes for city-scoped POI RAG.
Destination discovery continues to use ``travel_destinations`` via ``rag_service``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

from dotenv import load_dotenv

from src.services.embedding import DEFAULT_DIMENSIONS, embedding_dimensions

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

DESTINATIONS_COLLECTION = "travel_destinations"
POIS_COLLECTION = "travel_pois"


class QdrantServiceError(Exception):
    """Qdrant client / collection / upsert failure."""


def _load_env() -> None:
    load_dotenv(ROOT_DIR / ".env")


@lru_cache
def get_qdrant_client() -> Any:
    _load_env()
    url = os.getenv("QDRANT_URL", "").strip()
    if not url:
        raise QdrantServiceError("QDRANT_URL is not set in .env")
    api_key = os.getenv("QDRANT_API_KEY", "").strip() or None

    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise QdrantServiceError(
            "Missing dependency qdrant-client. Run: pip install -r requirements.txt"
        ) from exc

    try:
        return QdrantClient(url=url, api_key=api_key, timeout=60)
    except Exception as exc:  # noqa: BLE001
        raise QdrantServiceError(f"Failed to connect to Qdrant at {url}: {exc}") from exc


def ensure_collection(
    collection_name: str,
    *,
    vector_size: int | None = None,
    client: Any | None = None,
    payload_keyword_fields: Sequence[str] = (),
) -> None:
    """Create collection (Cosine) if missing; ensure KEYWORD payload indexes."""
    from qdrant_client.http.models import Distance, PayloadSchemaType, VectorParams

    qdrant = client or get_qdrant_client()
    size = vector_size if vector_size is not None else embedding_dimensions()
    existing = {c.name for c in qdrant.get_collections().collections}

    if collection_name in existing:
        info = qdrant.get_collection(collection_name)
        vectors = info.config.params.vectors
        found_size = getattr(vectors, "size", None)
        distance = getattr(vectors, "distance", None)
        if found_size != size or distance != Distance.COSINE:
            qdrant.delete_collection(collection_name)
            existing.discard(collection_name)
        else:
            ensure_payload_indexes(
                collection_name,
                payload_keyword_fields,
                client=qdrant,
            )
            return

    if collection_name not in existing:
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=size, distance=Distance.COSINE),
        )

    ensure_payload_indexes(
        collection_name,
        payload_keyword_fields,
        client=qdrant,
    )


def ensure_payload_indexes(
    collection_name: str,
    field_names: Sequence[str],
    *,
    client: Any | None = None,
) -> None:
    from qdrant_client.http.models import PayloadSchemaType

    qdrant = client or get_qdrant_client()
    for field_name in field_names:
        try:
            qdrant.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD,
                wait=True,
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            if any(
                token in message
                for token in ("already exists", "duplicate", "exists", "conflict")
            ):
                continue
            raise QdrantServiceError(
                f"Failed to create payload index {collection_name}.{field_name}: {exc}"
            ) from exc


def ensure_poi_collection(
    *,
    vector_size: int | None = None,
    client: Any | None = None,
) -> None:
    """Ensure ``travel_pois`` exists with city_id / category indexes."""
    ensure_collection(
        POIS_COLLECTION,
        vector_size=vector_size,
        client=client,
        payload_keyword_fields=("city_id", "category", "city"),
    )


def upsert_points(
    collection_name: str,
    points: Iterable[Any],
    *,
    client: Any | None = None,
) -> int:
    """Upsert PointStruct iterable; returns count."""
    point_list = list(points)
    if not point_list:
        return 0
    qdrant = client or get_qdrant_client()
    try:
        qdrant.upsert(collection_name=collection_name, points=point_list)
    except Exception as exc:  # noqa: BLE001
        raise QdrantServiceError(
            f"Qdrant upsert failed on '{collection_name}': {exc}"
        ) from exc
    return len(point_list)


def upsert_poi_vectors(
    records: Sequence[dict[str, Any]],
    vectors: Sequence[Sequence[float]],
    *,
    client: Any | None = None,
) -> int:
    """
    Upsert POI embeddings into ``travel_pois``.

    Each ``records[i]`` must include ``id`` (point id) and ``payload`` dict.
    """
    from qdrant_client.http.models import PointStruct

    if len(records) != len(vectors):
        raise QdrantServiceError(
            f"records/vectors length mismatch: {len(records)} vs {len(vectors)}"
        )

    ensure_poi_collection(
        vector_size=len(vectors[0]) if vectors else DEFAULT_DIMENSIONS,
        client=client,
    )

    points = [
        PointStruct(id=record["id"], vector=list(vector), payload=record["payload"])
        for record, vector in zip(records, vectors, strict=True)
    ]
    return upsert_points(POIS_COLLECTION, points, client=client)


def delete_poi_vectors(
    point_ids: Sequence[str],
    *,
    client: Any | None = None,
) -> int:
    """Delete points from ``travel_pois`` by id. Returns requested count."""
    ids = [str(i) for i in point_ids if i]
    if not ids:
        return 0
    from qdrant_client.http import models as qmodels

    qdrant = client or get_qdrant_client()
    try:
        qdrant.delete(
            collection_name=POIS_COLLECTION,
            points_selector=qmodels.PointIdsList(points=ids),
        )
    except Exception as exc:  # noqa: BLE001
        raise QdrantServiceError(
            f"Qdrant delete failed on '{POIS_COLLECTION}': {exc}"
        ) from exc
    return len(ids)


def search_poi_vectors(
    *,
    query_vector: Sequence[float],
    city_id: str,
    category: str | None = None,
    limit: int = 10,
    min_safety_score: int | None = None,
    min_rating: float | None = None,
    client: Any | None = None,
) -> list[dict[str, Any]]:
    """
    Cosine search in ``travel_pois`` scoped by ``city_id`` (+ optional filters).

    Returns payload dicts merged with ``score`` (higher = closer).
    """
    from qdrant_client.http import models as qmodels

    if not query_vector:
        raise QdrantServiceError("query_vector must be non-empty")
    if limit < 1:
        raise QdrantServiceError("limit must be >= 1")

    must: list[Any] = [
        qmodels.FieldCondition(
            key="city_id",
            match=qmodels.MatchValue(value=str(city_id)),
        )
    ]
    if category:
        must.append(
            qmodels.FieldCondition(
                key="category",
                match=qmodels.MatchValue(value=str(category).strip().lower()),
            )
        )
    if min_safety_score is not None:
        must.append(
            qmodels.FieldCondition(
                key="safety_score",
                range=qmodels.Range(gte=int(min_safety_score)),
            )
        )
    if min_rating is not None:
        must.append(
            qmodels.FieldCondition(
                key="rating",
                range=qmodels.Range(gte=float(min_rating)),
            )
        )

    query_filter = qmodels.Filter(must=must)
    qdrant = client or get_qdrant_client()

    try:
        if hasattr(qdrant, "query_points"):
            response = qdrant.query_points(
                collection_name=POIS_COLLECTION,
                query=list(query_vector),
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
            points = response.points
        else:
            points = qdrant.search(
                collection_name=POIS_COLLECTION,
                query_vector=list(query_vector),
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
    except Exception as exc:  # noqa: BLE001
        raise QdrantServiceError(
            f"Qdrant POI search failed on '{POIS_COLLECTION}': {exc}"
        ) from exc

    results: list[dict[str, Any]] = []
    for point in points:
        payload = dict(point.payload or {})
        payload["score"] = float(point.score)
        payload["point_id"] = str(point.id)
        results.append(payload)
    return results
