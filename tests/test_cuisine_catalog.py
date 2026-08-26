"""Cuisine catalog food POIs used for itinerary meal slots."""

from src.services.cuisine_catalog import (
    cuisine_photo_url,
    cuisine_records,
    cuisine_tool_dicts,
    is_meal_slot_poi,
    poi_cuisine_family,
)


def test_kyoto_catalog_has_kaiseki_without_stock_photo() -> None:
    records = cuisine_records(
        city_slug="kyoto",
        city_id="00000000-0000-0000-0000-000000000001",
        city_display="Kyoto",
    )
    names = {r.name for r in records}
    assert "Kaiseki / Tofu Cuisine" in names
    assert "Izakaya / Kyo-yasai" in names
    kaiseki = next(r for r in records if r.name == "Kaiseki / Tofu Cuisine")
    assert kaiseki.source == "cuisine_catalog"
    # Meal stock photos disabled — planner uses lunch/dinner icons.
    assert kaiseki.photo_url is None
    assert kaiseki.photo_source == "none"


def test_cuisine_photo_url_disabled() -> None:
    assert cuisine_photo_url("Kaiseki / Tofu Cuisine", "lunch") == ""
    assert cuisine_photo_url("Sushi Set", "dinner") == ""
    assert cuisine_photo_url("Monjayaki / Okonomiyaki", "dinner") == ""


def test_tool_dicts_are_meal_slots() -> None:
    rows = cuisine_tool_dicts(
        city_slug="tokyo",
        city_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        city_display="Tokyo",
    )
    assert rows
    assert all(is_meal_slot_poi(r) for r in rows)
    families = {poi_cuisine_family(r) for r in rows}
    assert "ramen" in families or "sushi" in families
    assert all(not r.get("photo_url") for r in rows)


def test_cuisine_family_prefers_earlier_needle_in_multicuisine_label() -> None:
    # "Matcha Sweets / Soba" contains both "matcha" and "soba" needles.
    # The algorithm should prefer the family that appears earliest in the label.
    from src.services.itinerary_i18n import cuisine_family

    assert cuisine_family("Matcha Sweets / Soba") == "matcha"
