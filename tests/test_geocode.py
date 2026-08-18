from src.services.geocode_service import resolve_place


def test_resolve_place_uses_name_when_query_empty(monkeypatch) -> None:
    def fake_nominatim(query: str, *, city: str | None = None, timeout: float = 8.0):
        assert "Shibuya Sky" in query
        assert city == "Tokyo"
        return {"lat": 35.6586, "lon": 139.7014, "label": "Shibuya Sky, Tokyo"}

    monkeypatch.setattr(
        "src.services.geocode_service.nominatim_search", fake_nominatim
    )
    hit = resolve_place(name="Shibuya Sky", city="Tokyo")
    assert hit is not None
    assert hit["lat"] == 35.6586
    assert hit["source"] == "nominatim"


def test_resolve_short_maps_url(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.services.geocode_service.expand_maps_url",
        lambda url, timeout=8.0: "https://www.google.com/maps/@35.6595,139.7004,17z",
    )
    hit = resolve_place(query="https://maps.app.goo.gl/abc123")
    assert hit is not None
    assert hit["lat"] == 35.6595
    assert hit["lon"] == 139.7004
    assert hit["source"] == "maps_url"
