"""Ingest-time grounded POI photo resolution (no Unsplash identity fallback)."""

from src.services.cache_service import CacheService, reset_cache_service
from src.services.poi_photos import (
    PhotoHit,
    is_allowed_photo_url,
    persistable_photo_url,
    resolve_grounded_photo,
    resolve_places_photo,
    resolve_poi_photo,
    titles_related,
    unique_stock_photo,
)


def setup_function() -> None:
    reset_cache_service(CacheService.memory())


def teardown_function() -> None:
    reset_cache_service(None)


def test_wiki_hit_returns_thumbnail_when_title_matches() -> None:
    thumb = "https://upload.wikimedia.org/wikipedia/commons/thumb/x/osaka.jpg"

    def fetch(url: str, params: dict | None = None):
        if "page/summary" in url:
            return {
                "type": "standard",
                "title": "Osaka Castle",
                "thumbnail": {"source": thumb},
                "coordinates": {"lat": 34.6873, "lon": 135.5262},
            }
        return None

    url = resolve_poi_photo(
        "Osaka Castle",
        city="Osaka",
        lat=34.6873,
        lon=135.5262,
        fetch=fetch,
    )
    assert url == thumb


def test_wiki_miss_does_not_use_stock() -> None:
    def fetch(url: str, params: dict | None = None):
        if "page/summary" in url:
            return {"type": "disambiguation"}
        return ["q", [], [], []]

    url = resolve_poi_photo("Unknown Spot 123", city="Osaka", category="attraction", fetch=fetch)
    assert url == ""


def test_wiki_rejects_unrelated_fuji_title_for_church() -> None:
    fuji = "https://upload.wikimedia.org/wikipedia/commons/fuji.jpg"

    def fetch(url: str, params: dict | None = None):
        if "page/summary" in url:
            return {
                "type": "standard",
                "title": "Mount Fuji",
                "thumbnail": {"source": fuji},
                "originalimage": {"source": fuji},
                "coordinates": {"lat": 35.3606, "lon": 138.7274},
            }
        return None

    url = resolve_poi_photo(
        "Tenrikyo Harajuku Branch Church",
        city="Tokyo",
        category="attraction",
        lat=35.6700,
        lon=139.7060,
        fetch=fetch,
    )
    assert url == ""
    assert not titles_related("Tenrikyo Harajuku Branch Church", "Mount Fuji")


def test_wiki_rejects_single_token_overlap_portrait() -> None:
    portrait = "https://upload.wikimedia.org/wikipedia/commons/person.jpg"

    def fetch(url: str, params: dict | None = None):
        if "page/summary" in url:
            return {
                "type": "standard",
                "title": "Ryu Takahashi",
                "thumbnail": {"source": portrait},
                "coordinates": {"lat": 35.01, "lon": 135.75},
            }
        return None

    url = resolve_poi_photo(
        "Ryu-hon-ji",
        city="Kyoto",
        lat=35.0116,
        lon=135.7681,
        fetch=fetch,
    )
    assert url == ""
    assert not titles_related("Ryu-hon-ji", "Ryu Takahashi")


def test_wiki_requires_page_coordinates_when_poi_has_coords() -> None:
    street = "https://upload.wikimedia.org/wikipedia/commons/street.jpg"

    def fetch(url: str, params: dict | None = None):
        if "page/summary" in url:
            return {
                "type": "standard",
                "title": "Momiji Tunnel",
                "thumbnail": {"source": street},
            }
        return None

    url = resolve_poi_photo(
        "Momiji Tunnel",
        city="Kyoto",
        lat=35.03,
        lon=135.78,
        fetch=fetch,
    )
    assert url == ""


def test_invalid_unsplash_id_not_allowed() -> None:
    assert not is_allowed_photo_url(
        "https://images.unsplash.com/photo-000000000000-deadbeefdead?auto=format&fit=crop&w=800"
    )
    assert is_allowed_photo_url(
        "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?auto=format&fit=crop&w=800&q=80"
    )
    assert is_allowed_photo_url("https://upload.wikimedia.org/wikipedia/commons/x.jpg")
    assert not is_allowed_photo_url("https://upload.wikimedia.org/wikipedia/commons/x.svg")
    assert persistable_photo_url("https://lh3.googleusercontent.com/p/abc")


def test_wikidata_p18_requires_p625_when_poi_has_coords() -> None:
    def fetch(url: str, params: dict | None = None):
        if "wikidata.org" in url:
            return {
                "entities": {
                    "Q235130": {
                        "claims": {
                            "P18": [
                                {
                                    "mainsnak": {
                                        "datavalue": {"value": "Sensoji_Asakusa.jpg"}
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        return None

    hit = resolve_grounded_photo(
        "Senso-ji Temple",
        city="Tokyo",
        wikidata="Q235130",
        lat=35.7148,
        lon=139.7967,
        fetch=fetch,
    )
    assert hit.url is None
    assert hit.source == "none"


def test_wikidata_p18_accepted_with_matching_p625() -> None:
    def fetch(url: str, params: dict | None = None):
        if "wikidata.org" in url:
            return {
                "entities": {
                    "Q235130": {
                        "claims": {
                            "P18": [
                                {
                                    "mainsnak": {
                                        "datavalue": {"value": "Sensoji_Asakusa.jpg"}
                                    }
                                }
                            ],
                            "P625": [
                                {
                                    "mainsnak": {
                                        "datavalue": {
                                            "value": {
                                                "latitude": 35.7148,
                                                "longitude": 139.7967,
                                            }
                                        }
                                    }
                                }
                            ],
                        }
                    }
                }
            }
        raise AssertionError("should not fall through to Wikipedia")

    url = resolve_poi_photo(
        "Senso-ji Temple",
        city="Tokyo",
        wikidata="Q235130",
        lat=35.7148,
        lon=139.7967,
        fetch=fetch,
    )
    assert "commons.wikimedia.org" in url
    assert "Sensoji_Asakusa.jpg" in url


def test_commons_search_hit_returns_file_when_title_and_coords_match() -> None:
    commons = "https://commons.wikimedia.org/wiki/Special:FilePath/Shiramine_Jingu.jpg?width=800"

    def fetch(url: str, params: dict | None = None):
        if "page/summary" in url:
            return {"type": "disambiguation"}
        if "commons.wikimedia.org/w/api.php" in url:
            return {
                "query": {
                    "pages": {
                        "1": {
                            "title": "File:Shiramine_Jingu.jpg",
                            "coordinates": [{"lat": 35.0301, "lon": 135.7639}],
                            "imageinfo": [{"thumburl": commons}],
                        }
                    }
                }
            }
        return ["q", [], [], []]

    hit = resolve_grounded_photo(
        "Shiramine Jingu",
        city="Kyoto",
        lat=35.0301,
        lon=135.7639,
        fetch=fetch,
    )
    assert hit.url == commons
    assert hit.source == "wikipedia"


def test_places_photo_rejects_far_venue() -> None:
    class FakeResp:
        def __init__(self, payload, status=200, url="https://example"):
            self._payload = payload
            self.status_code = status
            self.url = url
            self.headers = {"content-type": "application/json"}

        def json(self):
            return self._payload

    class FakeClient:
        def post(self, *args, **kwargs):
            return FakeResp(
                {
                    "places": [
                        {
                            "location": {"latitude": 35.6586, "longitude": 139.7454},
                            "photos": [{"name": "places/abc/photos/xyz"}],
                        }
                    ]
                }
            )

        def get(self, *args, **kwargs):
            return FakeResp({"photoUri": "https://lh3.googleusercontent.com/p/wrong-city"})

        def close(self):
            return None

    hit = resolve_places_photo(
        "Kosho-ji Temple",
        city="Kyoto",
        lat=34.89,
        lon=135.80,
        api_key="test",
        client=FakeClient(),
    )
    assert hit.url is None


def test_places_photo_reuses_stored_photo_name_without_search() -> None:
    class FakeResp:
        def __init__(self, payload, status=200, url="https://example"):
            self._payload = payload
            self.status_code = status
            self.url = url
            self.headers = {"content-type": "application/json"}

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self):
            self.post_calls = 0
            self.get_calls = 0

        def post(self, *args, **kwargs):
            self.post_calls += 1
            raise AssertionError("searchText should not run when photo name is stored")

        def get(self, *args, **kwargs):
            self.get_calls += 1
            return FakeResp({"photoUri": "https://lh3.googleusercontent.com/p/reused-photo"})

        def close(self):
            return None

    client = FakeClient()
    hit = resolve_places_photo(
        "Orinasu-kan",
        city="Kyoto",
        lat=35.0116,
        lon=135.7681,
        api_key="test",
        google_place_name="places/abc",
        google_photo_name="places/abc/photos/reused",
        client=client,
    )
    assert hit.source == "places"
    assert hit.url and "googleusercontent.com" in hit.url
    assert hit.google_place_name == "places/abc"
    assert hit.google_photo_name == "places/abc/photos/reused"
    assert client.post_calls == 0
    assert client.get_calls == 1


def test_places_photo_keeps_nearby_google_uri() -> None:
    class FakeResp:
        def __init__(self, payload, status=200, url="https://example"):
            self._payload = payload
            self.status_code = status
            self.url = url
            self.headers = {"content-type": "application/json"}

        def json(self):
            return self._payload

    class FakeClient:
        def post(self, *args, **kwargs):
            return FakeResp(
                {
                    "places": [
                        {
                            "location": {"latitude": 35.0116, "longitude": 135.7681},
                            "photos": [{"name": "places/abc/photos/xyz"}],
                        }
                    ]
                }
            )

        def get(self, *args, **kwargs):
            return FakeResp({"photoUri": "https://lh3.googleusercontent.com/p/orinasu"})

        def close(self):
            return None

    hit = resolve_places_photo(
        "Orinasu-kan",
        city="Kyoto",
        lat=35.0116,
        lon=135.7681,
        api_key="test",
        client=FakeClient(),
    )
    assert hit.source == "places"
    assert hit.url and "googleusercontent.com" in hit.url
    assert hit.google_place_name is None
    assert hit.google_photo_name == "places/abc/photos/xyz"


def test_unique_stock_skips_used_urls() -> None:
    first = unique_stock_photo("Senso-ji Temple", category="attraction", city="Tokyo")
    second = unique_stock_photo(
        "Senso-ji Temple",
        category="attraction",
        city="Tokyo",
        used_urls={first},
    )
    assert first != second
    assert is_allowed_photo_url(first)


def test_kyoto_stock_is_not_london_or_venice_default() -> None:
    from src.services.itinerary_eval import is_denied_stock_photo

    for name in ("Momiji Tunnel", "4-Way Junction", "Orinasu-kan"):
        url = unique_stock_photo(name, category="attraction", city="Kyoto")
        assert is_allowed_photo_url(url)
        assert not is_denied_stock_photo(url)
        assert "photo-1505761671935-60b3a7427bad" not in url
        assert "photo-1523906834658-6e24ef2386f9" not in url
