"""Phase 6.1 country seed validation (no live Supabase)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.seed_countries import validate_seed

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "countries_phase6.json"


def test_phase6_seed_file_validates() -> None:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    validate_seed(data)
    assert 25 <= len(data["countries"]) <= 40
    for country in data["countries"]:
        assert 2 <= len(country["cities"]) <= 4
        assert "unsplash.com" in country["photo_url"]
