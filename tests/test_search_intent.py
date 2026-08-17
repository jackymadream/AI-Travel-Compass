"""Unit tests for rule-based intent extraction and honest match percent helpers."""

from __future__ import annotations

from src.schemas.country import Locale
from src.schemas.search import SearchRequest
from src.services.intent_extraction import (
    expand_semantic_query,
    extract_budget,
    extract_intent_from_request,
    extract_interests,
    extract_safety,
)


def test_extract_interests_anime() -> None:
    interests = extract_interests("I want an anime trip")
    assert "anime" in interests


def test_extract_interests_northern_lights() -> None:
    interests = extract_interests("chase the northern lights")
    assert "northern-lights" in interests


def test_expand_semantic_includes_japan_cues_for_anime() -> None:
    expanded = expand_semantic_query("anime", ["anime"])
    lower = expanded.lower()
    assert "anime" in lower
    assert "japan" in lower or "tokyo" in lower or "akihabara" in lower


def test_extract_budget_and_safety_from_nl() -> None:
    assert extract_budget("cozy food under $100/day") == 100.0
    assert extract_safety("safe trip safety 4+") == 4


def test_extract_intent_keeps_interests_soft() -> None:
    request = SearchRequest(
        query="anime pilgrimage under $150/day safety 4+",
        locale=Locale.EN,
        max_budget=200,
        min_safety=3,
    )
    intent = extract_intent_from_request(request)
    assert "anime" in intent.interests
    assert "japan" in intent.semantic_query.lower() or "tokyo" in intent.semantic_query.lower()
    # NL-extracted budget/safety land in hard_filters; request still wins later in merge.
    assert intent.hard_filters.get("max_budget") == 150.0
    assert intent.hard_filters.get("min_safety") == 4
    # Soft interests must not be copied into hard tags.
    assert "anime" not in (intent.hard_filters.get("tags") or [])
