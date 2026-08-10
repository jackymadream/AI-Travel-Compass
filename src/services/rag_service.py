"""
RAG vector pipeline: Vertex AI query embeddings + Qdrant scoped search.

Phase 2 Step 2 — used by hybrid search after SQL produces candidate city IDs.
Points in ``travel_destinations`` use payload ``city_id`` (not point id = city id);
scoping therefore uses payload ``MatchAny`` on ``city_id``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
COLLECTION_NAME = "travel_destinations"
EMBEDDING_MODEL = "text-embedding-004"
DEFAULT_LOCATION = "us-central1"
DEFAULT_DIMENSIONS = 768
DEFAULT_VERTEX_TIMEOUT_SEC = 30.0


class RagServiceError(Exception):
    """Base error for RAG embedding / vector search failures."""


class EmbeddingError(RagServiceError):
    """Vertex AI embedding failed (timeout, auth, quota, or API error)."""


class VectorSearchError(RagServiceError):
    """Qdrant query failed."""


@dataclass(frozen=True)
class VectorHit:
    """Structured Qdrant hit with cosine similarity score."""

    city_id: str
    score: float
    country_id: str | None = None
    locale: str | None = None
    tags: list[str] = field(default_factory=list)
    daily_budget: float | None = None
    text: str | None = None
    point_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


def _load_env() -> None:
    load_dotenv(ROOT_DIR / ".env")


def _resolve_credentials_path() -> Path:
    _load_env()
    raw = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not raw:
        raise EmbeddingError(
            "GOOGLE_APPLICATION_CREDENTIALS is not set. "
            "Point it at a GCP service-account JSON key."
        )
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (ROOT_DIR / path).resolve()
    if not path.is_file():
        raise EmbeddingError(f"GOOGLE_APPLICATION_CREDENTIALS file not found: {path}")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(path)
    return path


def _embedding_dimensions() -> int:
    _load_env()
    raw = os.getenv("EMBEDDING_DIMENSIONS", "").strip()
    if not raw:
        return DEFAULT_DIMENSIONS
    try:
        size = int(raw)
    except ValueError as exc:
        raise EmbeddingError(
            f"Invalid EMBEDDING_DIMENSIONS={raw!r}; expected an integer."
        ) from exc
    if size not in {256, 512, 768}:
        raise EmbeddingError(
            f"Unsupported EMBEDDING_DIMENSIONS={size} for {EMBEDDING_MODEL}."
        )
    return size


@lru_cache
def _get_embedding_model() -> Any:
    _load_env()
    project_id = os.getenv("GCP_PROJECT_ID", "").strip()
    location = os.getenv("GCP_LOCATION", "").strip() or DEFAULT_LOCATION
    if not project_id:
        raise EmbeddingError("GCP_PROJECT_ID is not set in .env")

    _resolve_credentials_path()

    try:
        import vertexai
        from vertexai.language_models import TextEmbeddingModel
    except ImportError as exc:
        raise EmbeddingError(
            "Missing dependency google-cloud-aiplatform. "
            "Run: pip install -r requirements.txt"
        ) from exc

    try:
        vertexai.init(project=project_id, location=location)
        return TextEmbeddingModel.from_pretrained(EMBEDDING_MODEL)
    except Exception as exc:  # noqa: BLE001
        raise EmbeddingError(
            f"Failed to init Vertex AI model {EMBEDDING_MODEL} "
            f"(project={project_id}, location={location}): {exc}"
        ) from exc


@lru_cache
def _get_qdrant_client() -> Any:
    _load_env()
    url = os.getenv("QDRANT_URL", "").strip()
    if not url:
        raise VectorSearchError("QDRANT_URL is not set in .env")
    api_key = os.getenv("QDRANT_API_KEY", "").strip() or None

    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise VectorSearchError(
            "Missing dependency qdrant-client. Run: pip install -r requirements.txt"
        ) from exc

    try:
        return QdrantClient(url=url, api_key=api_key, timeout=30)
    except Exception as exc:  # noqa: BLE001
        raise VectorSearchError(f"Failed to connect to Qdrant at {url}: {exc}") from exc


def ensure_payload_indexes(client: Any | None = None) -> None:
    """
    Create payload indexes required for filtered vector search.

    Qdrant Cloud requires an index on ``city_id`` before MatchAny filters.
    Uses KEYWORD (not UUID) so ``MatchAny`` / IN-style candidate scoping works.
    """
    from qdrant_client.http import models as qmodels

    qdrant = client or _get_qdrant_client()
    indexes = (
        ("city_id", qmodels.PayloadSchemaType.KEYWORD),
        ("locale", qmodels.PayloadSchemaType.KEYWORD),
        ("country_id", qmodels.PayloadSchemaType.KEYWORD),
    )
    for field_name, schema in indexes:
        try:
            qdrant.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field_name,
                field_schema=schema,
                wait=True,
            )
            logger.info(
                "Ensured Qdrant payload index %s.%s (%s)",
                COLLECTION_NAME,
                field_name,
                schema,
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            # Already exists / concurrent create — safe to continue
            if any(
                token in message
                for token in ("already exists", "duplicate", "exists", "conflict")
            ):
                logger.debug(
                    "Payload index %s.%s already present: %s",
                    COLLECTION_NAME,
                    field_name,
                    exc,
                )
                continue
            raise VectorSearchError(
                f"Failed to create payload index on {field_name}: {exc}"
            ) from exc


@lru_cache
def _ensure_indexes_once() -> bool:
    ensure_payload_indexes()
    return True


def get_query_embedding(text: str) -> list[float]:
    """
    Embed a user / semantic query with Vertex AI ``text-embedding-004``.

    Uses task type ``RETRIEVAL_QUERY`` (documents were indexed as RETRIEVAL_DOCUMENT).
    Raises ``EmbeddingError`` on timeout, auth, or API failures.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        raise EmbeddingError("Cannot embed empty query text.")

    dims = _embedding_dimensions()
    model = _get_embedding_model()

    try:
        from vertexai.language_models import TextEmbeddingInput
    except ImportError:
        TextEmbeddingInput = None  # type: ignore[misc, assignment]

    kwargs: dict[str, Any] = {}
    if dims != DEFAULT_DIMENSIONS:
        kwargs["output_dimensionality"] = dims

    timeout_sec = float(
        os.getenv("VERTEX_EMBEDDING_TIMEOUT_SEC", str(DEFAULT_VERTEX_TIMEOUT_SEC))
    )

    try:
        if TextEmbeddingInput is not None:
            inputs = [
                TextEmbeddingInput(text=cleaned, task_type="RETRIEVAL_QUERY")
            ]
            embeddings = model.get_embeddings(inputs, **kwargs)
        else:
            embeddings = model.get_embeddings([cleaned], **kwargs)
    except TypeError:
        try:
            embeddings = model.get_embeddings([cleaned], **kwargs)
        except Exception as exc:  # noqa: BLE001
            _raise_embedding_failure(exc, timeout_sec)
    except Exception as exc:  # noqa: BLE001
        _raise_embedding_failure(exc, timeout_sec)

    if not embeddings:
        raise EmbeddingError("Vertex AI returned no embeddings.")

    vector = list(embeddings[0].values)
    if len(vector) != dims:
        raise EmbeddingError(
            f"Embedding dim mismatch: expected {dims}, got {len(vector)}."
        )
    return vector


def _raise_embedding_failure(exc: BaseException, timeout_sec: float) -> None:
    name = type(exc).__name__
    message = str(exc).lower()
    is_timeout = (
        name in {"DeadlineExceeded", "TimeoutError", "RetryError"}
        or "timeout" in message
        or "deadline" in message
        or "timed out" in message
    )
    if is_timeout:
        raise EmbeddingError(
            f"Vertex AI embedding timed out after ~{timeout_sec:.0f}s: {exc}"
        ) from exc
    raise EmbeddingError(f"Vertex AI embedding failed ({name}): {exc}") from exc


def search_vector_candidates(
    query_vector: list[float],
    candidate_ids: list[str],
    limit: int = 10,
) -> list[VectorHit]:
    """
    Cosine search in ``travel_destinations``, ranked only within ``candidate_ids``.

    Scopes via payload filter on ``city_id`` (MatchAny). Point IDs in this
    collection are locale-specific UUID5s, so ``HasIdCondition`` on city UUIDs
    would not match; payload filtering is the correct scope mechanism.

    Returns structured hits with Qdrant cosine similarity ``score`` (higher = closer).
    Raises ``VectorSearchError`` on Qdrant failures.
    """
    if not query_vector:
        raise VectorSearchError("query_vector must be a non-empty embedding.")
    if limit < 1:
        raise VectorSearchError("limit must be >= 1.")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_ids: list[str] = []
    for cid in candidate_ids:
        value = str(cid).strip()
        if value and value not in seen:
            seen.add(value)
            unique_ids.append(value)

    if not unique_ids:
        return []

    from qdrant_client.http import models as qmodels

    # Ensure payload indexes exist (required on Qdrant Cloud for filtered search).
    _ensure_indexes_once()

    # Payload scope: only rank destinations that passed SQL hard filters.
    # Equivalent intent to HasIdCondition, adapted to our point-id scheme.
    query_filter = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="city_id",
                match=qmodels.MatchAny(any=unique_ids),
            )
        ]
    )

    client = _get_qdrant_client()
    try:
        # qdrant-client >=1.10: query_points; fall back to search for older APIs
        if hasattr(client, "query_points"):
            response = client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
            points = response.points
        else:
            points = client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
    except Exception as exc:  # noqa: BLE001
        raise VectorSearchError(
            f"Qdrant search failed on '{COLLECTION_NAME}': {exc}"
        ) from exc

    hits: list[VectorHit] = []
    for point in points:
        payload = dict(point.payload or {})
        city_id = payload.get("city_id")
        if not city_id:
            logger.warning("Skipping Qdrant point without city_id: %s", point.id)
            continue
        tags_raw = payload.get("tags") or []
        tags = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
        daily = payload.get("daily_budget")
        hits.append(
            VectorHit(
                city_id=str(city_id),
                country_id=str(payload["country_id"])
                if payload.get("country_id")
                else None,
                locale=str(payload["locale"]) if payload.get("locale") else None,
                tags=tags,
                daily_budget=float(daily) if daily is not None else None,
                text=str(payload["text"]) if payload.get("text") else None,
                score=float(point.score),
                point_id=str(point.id),
                payload=payload,
            )
        )
    return hits


class RagService:
    """Convenience wrapper around module-level embedding + search helpers."""

    def get_query_embedding(self, text: str) -> list[float]:
        return get_query_embedding(text)

    def search_vector_candidates(
        self,
        query_vector: list[float],
        candidate_ids: list[str],
        limit: int = 10,
    ) -> list[VectorHit]:
        return search_vector_candidates(query_vector, candidate_ids, limit)

    def search_by_query(
        self,
        text: str,
        candidate_ids: list[str],
        limit: int = 10,
    ) -> list[VectorHit]:
        """Embed ``text`` then run scoped Qdrant search."""
        vector = self.get_query_embedding(text)
        return self.search_vector_candidates(vector, candidate_ids, limit=limit)
