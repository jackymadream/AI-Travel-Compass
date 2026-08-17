"""Wikipedia / unique stock photo resolution for itinerary POIs."""

from src.services.cache_service import CacheService, reset_cache_service
from src.services.poi_photos import (
    is_allowed_photo_url,
    resolve_poi_photo,
    titles_related,
    unique_stock_photo,
)


def setup_function() -> None:
    reset_cache_service(CacheService.memory())


def teardown_function() -> None:
    reset_cache_service(None)


def test_wiki_hit_returns_thumbnail() -> None:
    thumb = "https://upload.wikimedia.org/wikipedia/commons/thumb/x/osaka.jpg"

    def fetch(url: str, params: dict | None = None):
        if "page/summary" in url:
            return {"type": "standard", "title": "Osaka Castle", "thumbnail": {"source": thumb}}
        return None

    url = resolve_poi_photo("Osaka Castle", city="Osaka", fetch=fetch)
    assert url == thumb


def test_wiki_miss_uses_hashed_stock() -> None:
    def fetch(url: str, params: dict | None = None):
        if "page/summary" in url:
            return {"type": "disambiguation"}
        return ["q", [], [], []]

    url = resolve_poi_photo("Unknown Spot 123", city="Osaka", category="attraction", fetch=fetch)
    assert "unsplash.com" in url
    assert is_allowed_photo_url(url)


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
    assert "fuji" not in url.lower()
    assert is_allowed_photo_url(url)
    assert not titles_related("Tenrikyo Harajuku Branch Church", "Mount Fuji")


def test_invalid_unsplash_id_not_allowed() -> None:
    assert not is_allowed_photo_url(
        "https://images.unsplash.com/photo-000000000000-deadbeefdead?auto=format&fit=crop&w=800"
    )
    assert is_allowed_photo_url(
        "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?auto=format&fit=crop&w=800&q=80"
    )
    assert is_allowed_photo_url("https://upload.wikimedia.org/wikipedia/commons/x.jpg")
    assert not is_allowed_photo_url("https://upload.wikimedia.org/wikipedia/commons/x.svg")


def test_wikidata_p18_preferred() -> None:
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
        raise AssertionError("should not fall through to Wikipedia")

    url = resolve_poi_photo("Senso-ji Temple", city="Tokyo", wikidata="Q235130", fetch=fetch)
    assert "commons.wikimedia.org" in url
    assert "Sensoji_Asakusa.jpg" in url


def test_unique_stock_skips_used_urls() -> None:
    first = unique_stock_photo("Senso-ji Temple", category="attraction", city="Tokyo")
    second = unique_stock_photo(
        "Senso-ji Temple",
        category="attraction",
        city="Tokyo",
        used_urls={first},
    )
    assert first != second
    other = unique_stock_photo("Meiji Shrine", category="attraction", city="Tokyo")
    sky = unique_stock_photo("Tokyo Skytree", category="attraction", city="Tokyo")
    assert len({first, other, sky}) >= 2
    assert is_allowed_photo_url(first)


def test_worship_stock_is_not_generic_fuji_only() -> None:
    church = unique_stock_photo(
        "Tenrikyo Harajuku Branch Church",
        category="attraction",
        city="Tokyo",
    )
    park = unique_stock_photo("Yoyogi Park Rest", category="rest", city="Tokyo")
    assert is_allowed_photo_url(church)
    assert is_allowed_photo_url(park)
