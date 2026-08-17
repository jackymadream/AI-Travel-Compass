#!/usr/bin/env python3
"""
Embed travel destinations into Qdrant for RAG retrieval.

Reads data/seed_data.json, resolves city/country UUIDs from Supabase,
builds multilingual structured text chunks, embeds with Google Cloud
Vertex AI `text-embedding-004` (768-d by default), and upserts into the
`travel_destinations` collection (Cosine distance).

Environment setup
-----------------
1. Ensure .env has (see .env.example):
     SUPABASE_URL
     SUPABASE_SERVICE_ROLE_KEY
     GCP_PROJECT_ID
     GOOGLE_APPLICATION_CREDENTIALS   # path to service-account JSON
     GCP_LOCATION                     # optional, default us-central1
     EMBEDDING_DIMENSIONS             # optional: 768 (default) for text-embedding-004
     QDRANT_URL
     QDRANT_API_KEY                   # optional for local Qdrant

2. Seed Postgres first (so city_id / country_id exist):
     python scripts/seed_countries.py   # Phase 6.1 (preferred)
     # or: python scripts/seed_db.py

3. Install / update dependencies:
     pip install -r requirements.txt

4. Run:
     python scripts/embed_destinations.py

Uses ``data/countries_phase6.json`` when present, otherwise ``data/seed_data.json``.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)
from supabase import Client, create_client

ROOT_DIR = Path(__file__).resolve().parent.parent
LEGACY_SEED_FILE = ROOT_DIR / "data" / "seed_data.json"
PHASE6_SEED_FILE = ROOT_DIR / "data" / "countries_phase6.json"
SEED_FILE = PHASE6_SEED_FILE if PHASE6_SEED_FILE.exists() else LEGACY_SEED_FILE

COLLECTION_NAME = "travel_destinations"
EMBEDDING_MODEL = "text-embedding-004"
DEFAULT_LOCATION = "us-central1"
DEFAULT_DIMENSIONS = 768
# text-embedding-004 native output is 768; Vertex may allow Matryoshka truncation
# to smaller sizes. 1536 is OpenAI-only — not valid for this model.
ALLOWED_DIMENSIONS = {256, 512, 768}
LOCALES = ("en", "zh-HK", "ja")
EMBED_BATCH_SIZE = 16


def load_env() -> None:
    load_dotenv(ROOT_DIR / ".env")


def require_env(*names: str) -> dict[str, str]:
    values: dict[str, str] = {}
    missing: list[str] = []
    for name in names:
        value = os.getenv(name, "").strip()
        if not value:
            missing.append(name)
        else:
            values[name] = value
    if missing:
        print(
            "Missing required environment variables: "
            + ", ".join(missing)
            + "\n\nSee .env.example. For Vertex AI embeddings you need:\n"
            "  GCP_PROJECT_ID\n"
            "  GOOGLE_APPLICATION_CREDENTIALS  (path to service-account JSON)\n"
            "  QDRANT_URL (+ Supabase keys)",
            file=sys.stderr,
        )
        sys.exit(1)
    return values


def resolve_gcp_credentials() -> tuple[str, str, Path]:
    """
    Validate GCP_PROJECT_ID and GOOGLE_APPLICATION_CREDENTIALS.
    Ensures the credentials file exists and is exposed to ADC via os.environ.
    """
    load_env()
    project_id = os.getenv("GCP_PROJECT_ID", "").strip()
    creds_path_raw = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    location = os.getenv("GCP_LOCATION", "").strip() or DEFAULT_LOCATION

    errors: list[str] = []
    if not project_id:
        errors.append("GCP_PROJECT_ID is not set in .env")
    if not creds_path_raw:
        errors.append(
            "GOOGLE_APPLICATION_CREDENTIALS is not set in .env "
            "(path to a GCP service-account JSON key)"
        )

    creds_path: Path | None = None
    if creds_path_raw:
        creds_path = Path(creds_path_raw).expanduser()
        if not creds_path.is_absolute():
            creds_path = (ROOT_DIR / creds_path).resolve()
        if not creds_path.is_file():
            errors.append(
                f"GOOGLE_APPLICATION_CREDENTIALS file not found: {creds_path}"
            )

    if errors:
        print(
            "Vertex AI authentication error:\n  - "
            + "\n  - ".join(errors)
            + "\n\nCreate a service account with Vertex AI User role, download "
            "the JSON key, and set GOOGLE_APPLICATION_CREDENTIALS to its path.",
            file=sys.stderr,
        )
        sys.exit(1)

    assert creds_path is not None
    # ADC reads this env var; force absolute path after resolution
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(creds_path)
    return project_id, location, creds_path


def resolve_vector_size() -> int:
    """Map EMBEDDING_DIMENSIONS for text-embedding-004 (default 768)."""
    load_env()
    raw = os.getenv("EMBEDDING_DIMENSIONS", "").strip()
    if not raw:
        return DEFAULT_DIMENSIONS

    try:
        size = int(raw)
    except ValueError:
        print(
            f"Invalid EMBEDDING_DIMENSIONS={raw!r}; expected an integer "
            f"in {sorted(ALLOWED_DIMENSIONS)}.",
            file=sys.stderr,
        )
        sys.exit(1)

    if size == 1536:
        print(
            "EMBEDDING_DIMENSIONS=1536 is for OpenAI text-embedding-3-small, "
            f"not Vertex AI {EMBEDDING_MODEL}.\n"
            f"Use 768 (native) or one of {sorted(ALLOWED_DIMENSIONS)}.",
            file=sys.stderr,
        )
        sys.exit(1)

    if size not in ALLOWED_DIMENSIONS:
        print(
            f"Unsupported EMBEDDING_DIMENSIONS={size} for {EMBEDDING_MODEL}. "
            f"Allowed: {sorted(ALLOWED_DIMENSIONS)} (default {DEFAULT_DIMENSIONS}).",
            file=sys.stderr,
        )
        sys.exit(1)

    return size


def load_seed_data() -> dict[str, Any]:
    if not SEED_FILE.exists():
        print(f"Seed file not found: {SEED_FILE}", file=sys.stderr)
        sys.exit(1)
    with SEED_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def fetch_id_maps(
    supabase: Client,
) -> tuple[dict[str, str], dict[tuple[str, str], dict[str, Any]]]:
    countries = (
        supabase.table("countries")
        .select("id, iso_code")
        .execute()
        .data
        or []
    )
    countries_by_iso = {row["iso_code"]: row["id"] for row in countries}

    cities = (
        supabase.table("cities")
        .select("id, country_id, slug, avg_daily_cost_usd, safety_index, tags")
        .execute()
        .data
        or []
    )

    country_id_to_iso = {v: k for k, v in countries_by_iso.items()}
    cities_by_iso_slug: dict[tuple[str, str], dict[str, Any]] = {}
    for row in cities:
        iso = country_id_to_iso.get(row["country_id"])
        if not iso:
            continue
        cities_by_iso_slug[(iso, row["slug"])] = row

    return countries_by_iso, cities_by_iso_slug


def build_chunk(
    *,
    locale: str,
    city_name: str,
    country_name: str,
    tags: list[str],
    description: str,
    season_label: str,
    safety_index: int,
    daily_budget: float,
) -> str:
    vibe = ", ".join(tags) if tags else "general travel"
    tag_line = ", ".join(tags) if tags else "none"
    return "\n".join(
        [
            f"City: {city_name}",
            f"Country: {country_name}",
            f"Locale: {locale}",
            f"Vibe: {vibe}",
            f"Tags: {tag_line}",
            f"Best season: {season_label}",
            f"Safety index: {safety_index}",
            f"Daily budget (USD): {daily_budget}",
            f"Description: {description}",
        ]
    )


def point_id(city_id: str, locale: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"travel-compass:{city_id}:{locale}"))


def ensure_collection(qdrant: QdrantClient, vector_size: int) -> None:
    existing = {c.name for c in qdrant.get_collections().collections}
    if COLLECTION_NAME in existing:
        info = qdrant.get_collection(COLLECTION_NAME)
        vectors = info.config.params.vectors
        size = getattr(vectors, "size", None)
        distance = getattr(vectors, "distance", None)
        if size != vector_size or distance != Distance.COSINE:
            print(
                f"Recreating collection '{COLLECTION_NAME}' "
                f"(expected size={vector_size}, Cosine; "
                f"found size={size}, distance={distance})."
            )
            qdrant.delete_collection(COLLECTION_NAME)
        else:
            print(f"Collection '{COLLECTION_NAME}' already exists ({vector_size}-d).")
            ensure_payload_indexes(qdrant)
            return

    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
    print(
        f"Created collection '{COLLECTION_NAME}' "
        f"(size={vector_size}, distance=Cosine)."
    )
    ensure_payload_indexes(qdrant)


def ensure_payload_indexes(qdrant: QdrantClient) -> None:
    """Payload indexes required for filtered search (city_id MatchAny, etc.)."""
    for field_name in ("city_id", "locale", "country_id"):
        try:
            qdrant.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD,
                wait=True,
            )
            print(f"  payload index ready: {field_name} (keyword)")
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            if any(
                token in message
                for token in ("already exists", "duplicate", "exists", "conflict")
            ):
                print(f"  payload index exists: {field_name}")
                continue
            raise


def init_vertex(project_id: str, location: str) -> Any:
    try:
        import vertexai
        from vertexai.language_models import TextEmbeddingModel
    except ImportError:
        print(
            "Missing dependency: google-cloud-aiplatform\n"
            "  pip install -r requirements.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        vertexai.init(project=project_id, location=location)
        model = TextEmbeddingModel.from_pretrained(EMBEDDING_MODEL)
    except Exception as exc:  # noqa: BLE001 — surface ADC / project errors cleanly
        print(
            "Failed to initialize Vertex AI TextEmbeddingModel.\n"
            f"  project={project_id}  location={location}  model={EMBEDDING_MODEL}\n"
            f"  cause: {exc}\n\n"
            "Check that:\n"
            "  - GOOGLE_APPLICATION_CREDENTIALS points to a valid service-account JSON\n"
            "  - the account has roles/aiplatform.user on GCP_PROJECT_ID\n"
            "  - Vertex AI API is enabled in the project",
            file=sys.stderr,
        )
        sys.exit(1)

    return model


def embed_texts(model: Any, texts: list[str], vector_size: int) -> list[list[float]]:
    """Embed texts in batches via Vertex AI text-embedding-004."""
    from vertexai.language_models import TextEmbeddingInput

    all_vectors: list[list[float]] = []
    kwargs: dict[str, Any] = {}
    # Only pass output_dimensionality when truncating below native 768
    if vector_size != DEFAULT_DIMENSIONS:
        kwargs["output_dimensionality"] = vector_size

    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        inputs = [TextEmbeddingInput(text=text, task_type="RETRIEVAL_DOCUMENT") for text in batch]
        try:
            embeddings = model.get_embeddings(inputs, **kwargs)
        except TypeError:
            # Older SDK builds may not accept output_dimensionality / TextEmbeddingInput
            try:
                embeddings = model.get_embeddings(batch, **kwargs)
            except TypeError:
                embeddings = model.get_embeddings(batch)
        except Exception as exc:  # noqa: BLE001
            print(
                f"Vertex AI embedding request failed (batch starting at {start}): {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

        for item in embeddings:
            vector = list(item.values)
            if len(vector) != vector_size:
                print(
                    f"Unexpected embedding size {len(vector)}; "
                    f"expected {vector_size}. "
                    "Adjust EMBEDDING_DIMENSIONS or recreate the Qdrant collection.",
                    file=sys.stderr,
                )
                sys.exit(1)
            all_vectors.append(vector)

    return all_vectors


def build_points(
    seed: dict[str, Any],
    cities_by_iso_slug: dict[tuple[str, str], dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    skipped: list[str] = []

    for country in seed.get("countries", []):
        iso = country["iso_code"]
        country_names = country["name"]
        for city in country.get("cities", []):
            slug = city["slug"]
            db_row = cities_by_iso_slug.get((iso, slug))
            if not db_row:
                skipped.append(
                    f"{iso}/{slug}: not found in Supabase "
                    "(run scripts/seed_countries.py or seed_db.py first)"
                )
                continue

            city_id = db_row["id"]
            country_id = db_row["country_id"]
            tags = city.get("tags") or db_row.get("tags") or []
            if not isinstance(tags, list):
                tags = []
            daily_budget = float(
                city.get("avg_daily_cost_usd", db_row["avg_daily_cost_usd"])
            )
            safety_index = int(
                city.get("safety_index", db_row.get("safety_index", 3))
            )
            season = city.get("best_travel_season") or {}
            season_labels = season.get("label") or {}

            for locale in LOCALES:
                city_name = city["name"].get(locale) or city["name"]["en"]
                country_name = country_names.get(locale) or country_names["en"]
                description = (
                    city["description"].get(locale) or city["description"]["en"]
                )
                season_label = (
                    season_labels.get(locale)
                    or season_labels.get("en")
                    or ", ".join(season.get("seasons") or [])
                )
                chunk = build_chunk(
                    locale=locale,
                    city_name=city_name,
                    country_name=country_name,
                    tags=tags,
                    description=description,
                    season_label=season_label,
                    safety_index=safety_index,
                    daily_budget=daily_budget,
                )
                records.append(
                    {
                        "id": point_id(city_id, locale),
                        "vector_text": chunk,
                        "payload": {
                            "city_id": city_id,
                            "country_id": country_id,
                            "country_iso": iso,
                            "city_slug": slug,
                            "locale": locale,
                            "city_name": city_name,
                            "country_name": country_name,
                            "tags": tags,
                            "daily_budget": daily_budget,
                            "safety_index": safety_index,
                            "text": chunk,
                        },
                    }
                )

    return records, skipped


def main() -> None:
    load_env()
    project_id, location, creds_path = resolve_gcp_credentials()
    vector_size = resolve_vector_size()

    print("GenAI Travel Compass — destination embedder (Vertex AI)")
    print(f"Seed file: {SEED_FILE.relative_to(ROOT_DIR)}")
    print(f"GCP project: {project_id}  location: {location}")
    print(f"Credentials: {creds_path}")
    print(f"Model: {EMBEDDING_MODEL} ({vector_size}-d)")
    print(f"Collection: {COLLECTION_NAME}")

    env = require_env(
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "QDRANT_URL",
    )
    qdrant_api_key = os.getenv("QDRANT_API_KEY", "").strip() or None

    supabase = create_client(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])
    qdrant = QdrantClient(url=env["QDRANT_URL"], api_key=qdrant_api_key)
    model = init_vertex(project_id, location)

    seed = load_seed_data()
    _, cities_by_iso_slug = fetch_id_maps(supabase)

    records, skipped = build_points(seed, cities_by_iso_slug)
    for warning in skipped:
        print(f"  skip: {warning}", file=sys.stderr)

    if not records:
        print("No points to embed. Aborting.", file=sys.stderr)
        sys.exit(1)

    ensure_collection(qdrant, vector_size)

    texts = [r["vector_text"] for r in records]
    print(
        f"\nEmbedding {len(texts)} chunks "
        f"({len(texts) // len(LOCALES)} cities × {len(LOCALES)} locales)..."
    )
    vectors = embed_texts(model, texts, vector_size)

    points = [
        PointStruct(
            id=record["id"],
            vector=vector,
            payload=record["payload"],
        )
        for record, vector in zip(records, vectors, strict=True)
    ]

    qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
    print(
        f"Done. Upserted {len(points)} points into '{COLLECTION_NAME}' "
        f"(payload: city_id, country_id, tags, daily_budget, locale, …)."
    )


if __name__ == "__main__":
    main()
