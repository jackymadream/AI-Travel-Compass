"""
Rule-based NL intent extraction for hybrid search.

Hard filters (budget / safety) may be pattern-extracted for SQL.
Interests are soft only — used for ranking + semantic expansion, never as
hard SQL tag gates (CONTEXT.md §5–6).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.schemas.search import ExtractedIntent, SearchRequest

ROOT = Path(__file__).resolve().parent.parent.parent
TAXONOMY_PATH = ROOT / "data" / "interest_taxonomy.json"

_BUDGET_PATTERNS = [
    re.compile(
        r"(?:under|below|max(?:imum)?|up to|less than)\s*\$?\s*(\d{2,4})\s*(?:/?\s*day|usd|dollars)?",
        re.I,
    ),
    re.compile(r"\$\s*(\d{2,4})\s*(?:/?\s*day|per day|daily)", re.I),
    re.compile(r"budget\s*(?:of|under|max)?\s*\$?\s*(\d{2,4})", re.I),
]

_SAFETY_PATTERNS = [
    re.compile(r"safety\s*(?:rating\s*)?(?:of\s*)?(\d)\s*\+?", re.I),
    re.compile(r"(?:at least|min(?:imum)?)\s*safety\s*(\d)", re.I),
    re.compile(r"(\d)\s*\+\s*safety", re.I),
]


@lru_cache(maxsize=1)
def load_taxonomy() -> dict[str, Any]:
    if not TAXONOMY_PATH.is_file():
        return {
            "travel_styles": [],
            "specialty_interests": [],
            "synonyms": {},
            "semantic_expansions": {},
        }
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def extract_budget(query: str) -> float | None:
    for pattern in _BUDGET_PATTERNS:
        match = pattern.search(query)
        if match:
            value = float(match.group(1))
            if 20 <= value <= 2000:
                return value
    return None


def extract_safety(query: str) -> int | None:
    for pattern in _SAFETY_PATTERNS:
        match = pattern.search(query)
        if match:
            value = int(match.group(1))
            if 1 <= value <= 5:
                return value
    return None


def extract_interests(query: str) -> list[str]:
    """Map synonym phrases in the query to canonical interest tags."""
    taxonomy = load_taxonomy()
    synonyms: dict[str, list[str]] = taxonomy.get("synonyms") or {}
    normalized = _normalize(query)
    found: list[str] = []

    # Longer phrases first so "northern lights" wins over "lights".
    ranked: list[tuple[int, str, str]] = []
    for canonical, phrases in synonyms.items():
        for phrase in phrases:
            ranked.append((len(phrase), canonical, phrase.lower()))
    ranked.sort(key=lambda item: (-item[0], item[1]))

    claimed: set[str] = set()
    for _, canonical, phrase in ranked:
        if canonical in claimed:
            continue
        # Word-boundary-ish match for multi-word and single tokens.
        if " " in phrase:
            if phrase in normalized:
                found.append(canonical)
                claimed.add(canonical)
        else:
            if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", normalized):
                found.append(canonical)
                claimed.add(canonical)

    return found


def expand_semantic_query(query: str, interests: list[str]) -> str:
    """Keep user wording and append expansions for matched interests."""
    taxonomy = load_taxonomy()
    expansions: dict[str, str] = taxonomy.get("semantic_expansions") or {}
    parts = [query.strip()]
    query_lower = query.lower()
    for interest in interests:
        extra = (expansions.get(interest) or "").strip()
        if not extra:
            continue
        # Prefer expansion text when it already contains the user query tokens.
        if query_lower in extra.lower():
            parts = [extra]
            break
        if extra.lower() not in query_lower:
            parts.append(extra)
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(part)
    return " ".join(out).strip()


def extract_intent_from_request(request: SearchRequest) -> ExtractedIntent:
    """
    Decompose NL query into hard filters, soft interests, and expanded semantic text.

    Explicit request fields are merged later by SearchService._merge_hard_filters
    (request wins). Extracted budget/safety only fill hard_filters when present
    in the query text.
    """
    query = request.query.strip()
    hard: dict[str, Any] = {}

    budget = extract_budget(query)
    if budget is not None:
        hard["max_budget"] = budget

    safety = extract_safety(query)
    if safety is not None:
        hard["min_safety"] = safety

    # Explicit request tags stay request-level hard/soft elsewhere; do not
    # copy into hard_filters.tags from NL interests (soft only).
    if request.tags:
        hard["tags"] = list(request.tags)

    interests = extract_interests(query)
    semantic = expand_semantic_query(query, interests)

    return ExtractedIntent(
        hard_filters=hard,
        semantic_query=semantic or query,
        interests=interests,
    )
