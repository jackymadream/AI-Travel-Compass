from scripts.seed_city_pois import (
    MIN_NIGHTLIFE,
    MIN_POPULAR,
    build_synthetic_pois,
    count_by_tag,
)


def test_synthetic_seed_meets_nightlife_and_popular_quotas() -> None:
    city = {
        "display_name": "Osaka",
        "lat": 34.69,
        "lon": 135.50,
        "safety_index": 4,
        "tags": ["food", "urban"],
        "iso": "jp",
    }
    extras = build_synthetic_pois(
        city=city,
        city_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        existing=[],
    )
    assert count_by_tag(extras, "nightlife") >= MIN_NIGHTLIFE
    assert count_by_tag(extras, "popular") >= MIN_POPULAR
