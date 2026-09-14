from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "enrich_poi_photos.py"
SPEC = importlib.util.spec_from_file_location("enrich_poi_photos", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_enrich_row_reuses_stored_google_photo_name(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_grounded(*args, **kwargs):
        return MODULE.PhotoHit(url=None, source="none", confidence="low")

    def fake_places(name, *, city, lat, lon, api_key, google_place_name=None, google_photo_name=None, client=None):
        captured["google_place_name"] = google_place_name
        captured["google_photo_name"] = google_photo_name
        return MODULE.PhotoHit(
            url="https://lh3.googleusercontent.com/p/reused",
            source="places",
            confidence="high",
            google_place_name=google_place_name,
            google_photo_name=google_photo_name,
        )

    monkeypatch.setattr(MODULE, "resolve_grounded_photo", fake_grounded)
    monkeypatch.setattr(MODULE, "resolve_places_photo", fake_places)

    row = {
        "name": "Orinasu-kan",
        "city": "Kyoto",
        "latitude": 35.0116,
        "longitude": 135.7681,
        "tags": [],
        "source": "overpass",
        "google_place_name": "places/abc",
        "google_photo_name": "places/abc/photos/xyz",
    }

    hit = MODULE.enrich_row(row, places_key="test", skip_places=False)

    assert hit.url == "https://lh3.googleusercontent.com/p/reused"
    assert captured == {
        "google_place_name": "places/abc",
        "google_photo_name": "places/abc/photos/xyz",
    }


def test_apply_hit_persists_google_identifiers() -> None:
    payload: dict[str, object] = {}

    class FakeQuery:
        def update(self, values):
            payload.update(values)
            return self

        def eq(self, *args, **kwargs):
            return self

        def execute(self):
            return None

    class FakeSupabase:
        def table(self, name):
            assert name == "pois"
            return FakeQuery()

    hit = MODULE.PhotoHit(
        url="https://lh3.googleusercontent.com/p/reused",
        source="places",
        confidence="high",
        google_place_name="places/abc",
        google_photo_name="places/abc/photos/xyz",
    )

    MODULE.apply_hit(FakeSupabase(), "poi-1", hit)

    assert payload["google_place_name"] == "places/abc"
    assert payload["google_photo_name"] == "places/abc/photos/xyz"
    assert payload["photo_source"] == "places"
