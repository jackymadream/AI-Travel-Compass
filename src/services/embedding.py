"""
Vertex AI text-embedding-004 helpers for document / query vectors.

Phase 5.1 — used by ``scripts/ingest_real_pois.py`` (and available for future
POI RAG). Destination hybrid search remains in ``rag_service.py``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from src.services.gcp_credentials import configure_google_credentials, load_project_env

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
EMBEDDING_MODEL = "text-embedding-004"
DEFAULT_LOCATION = "us-central1"
DEFAULT_DIMENSIONS = 768
ALLOWED_DIMENSIONS = frozenset({256, 512, 768})
EMBED_BATCH_SIZE = 16

TaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]


class EmbeddingServiceError(Exception):
    """Vertex embedding configuration or API failure."""


def _load_env() -> None:
    load_project_env()


def resolve_credentials_path() -> Path | None:
    """Optional key file locally; Cloud Run uses ambient ADC when unset."""
    try:
        return configure_google_credentials()
    except FileNotFoundError as exc:
        raise EmbeddingServiceError(str(exc)) from exc


def embedding_dimensions() -> int:
    _load_env()
    raw = os.getenv("EMBEDDING_DIMENSIONS", "").strip()
    if not raw:
        return DEFAULT_DIMENSIONS
    try:
        size = int(raw)
    except ValueError as exc:
        raise EmbeddingServiceError(
            f"Invalid EMBEDDING_DIMENSIONS={raw!r}; expected an integer."
        ) from exc
    if size not in ALLOWED_DIMENSIONS:
        raise EmbeddingServiceError(
            f"Unsupported EMBEDDING_DIMENSIONS={size} for {EMBEDDING_MODEL}. "
            f"Allowed: {sorted(ALLOWED_DIMENSIONS)}."
        )
    return size


@lru_cache
def get_embedding_model() -> Any:
    """Initialize Vertex ``TextEmbeddingModel`` (cached per process)."""
    _load_env()
    project_id = os.getenv("GCP_PROJECT_ID", "").strip()
    location = os.getenv("GCP_LOCATION", "").strip() or DEFAULT_LOCATION
    if not project_id:
        raise EmbeddingServiceError("GCP_PROJECT_ID is not set in .env")

    resolve_credentials_path()

    try:
        import vertexai
        from vertexai.language_models import TextEmbeddingModel
    except ImportError as exc:
        raise EmbeddingServiceError(
            "Missing dependency google-cloud-aiplatform. "
            "Run: pip install -r requirements.txt"
        ) from exc

    try:
        vertexai.init(project=project_id, location=location)
        return TextEmbeddingModel.from_pretrained(EMBEDDING_MODEL)
    except Exception as exc:  # noqa: BLE001
        raise EmbeddingServiceError(
            f"Failed to init Vertex AI model {EMBEDDING_MODEL} "
            f"(project={project_id}, location={location}): {exc}"
        ) from exc


def embed_texts(
    texts: list[str],
    *,
    task_type: TaskType = "RETRIEVAL_DOCUMENT",
    dimensions: int | None = None,
    model: Any | None = None,
) -> list[list[float]]:
    """
    Embed a batch of strings with ``text-embedding-004``.

    Documents for Qdrant upserts should use ``RETRIEVAL_DOCUMENT``;
    search queries should use ``RETRIEVAL_QUERY``.
    """
    if not texts:
        return []

    dims = dimensions if dimensions is not None else embedding_dimensions()
    emb_model = model or get_embedding_model()

    try:
        from vertexai.language_models import TextEmbeddingInput
    except ImportError:
        TextEmbeddingInput = None  # type: ignore[misc, assignment]

    kwargs: dict[str, Any] = {}
    if dims != DEFAULT_DIMENSIONS:
        kwargs["output_dimensionality"] = dims

    all_vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        try:
            if TextEmbeddingInput is not None:
                inputs = [
                    TextEmbeddingInput(text=text, task_type=task_type)
                    for text in batch
                ]
                embeddings = emb_model.get_embeddings(inputs, **kwargs)
            else:
                embeddings = emb_model.get_embeddings(batch, **kwargs)
        except TypeError:
            try:
                embeddings = emb_model.get_embeddings(batch, **kwargs)
            except TypeError:
                embeddings = emb_model.get_embeddings(batch)
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingServiceError(
                f"Vertex AI embedding failed (batch @{start}): {exc}"
            ) from exc

        for item in embeddings:
            vector = list(item.values)
            if len(vector) != dims:
                raise EmbeddingServiceError(
                    f"Unexpected embedding size {len(vector)}; expected {dims}."
                )
            all_vectors.append(vector)

    return all_vectors


def embed_documents(texts: list[str], **kwargs: Any) -> list[list[float]]:
    """Convenience: document embeddings for upsert."""
    return embed_texts(texts, task_type="RETRIEVAL_DOCUMENT", **kwargs)


def embed_query(text: str, **kwargs: Any) -> list[float]:
    """Convenience: single query embedding."""
    cleaned = (text or "").strip()
    if not cleaned:
        raise EmbeddingServiceError("Cannot embed empty query text.")
    vectors = embed_texts([cleaned], task_type="RETRIEVAL_QUERY", **kwargs)
    return vectors[0]
