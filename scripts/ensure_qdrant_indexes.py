#!/usr/bin/env python3
"""Ensure Qdrant payload indexes exist for filtered hybrid search."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.rag_service import (  # noqa: E402
    COLLECTION_NAME,
    VectorSearchError,
    ensure_payload_indexes,
)


def main() -> None:
    print(f"Ensuring payload indexes on '{COLLECTION_NAME}'...")
    try:
        ensure_payload_indexes()
    except VectorSearchError as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print("Done. city_id / locale / country_id keyword indexes are ready.")


if __name__ == "__main__":
    main()
