"""Unit contracts for itinerary eval helpers (no live API)."""

from src.services.itinerary_eval import (
    contains_cjk,
    day_meal_families,
    is_denied_stock_photo,
    is_synthetic_poi_name,
    overlapping_activity_pairs,
    unique_lunch_names,
    unique_non_meal_photos,
    unique_non_meal_poi_names,
)


def test_synthetic_osaka_templates() -> None:
    assert is_synthetic_poi_name("Osaka Market Quarter")
    assert is_synthetic_poi_name("Osaka City Museum")
    assert is_synthetic_poi_name("Tokyo Historic District Walk")
    assert not is_synthetic_poi_name("Osaka Castle")
    assert not is_synthetic_poi_name("Dotonbori")


def test_denied_stock_photos() -> None:
    assert is_denied_stock_photo(
        "https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?auto=format&fit=crop&w=800&q=80"
    )
    assert is_denied_stock_photo(
        "https://images.unsplash.com/photo-1499856871958-5b9627545d1a?w=800"
    )
    assert is_denied_stock_photo(
        "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format"
    )
    assert is_denied_stock_photo(
        "https://images.unsplash.com/photo-1505761671935-60b3a7427bad?auto=format&fit=crop&w=800&q=80"
    )
    assert is_denied_stock_photo(
        "https://images.unsplash.com/photo-1523906834658-6e24ef2386f9?auto=format&fit=crop&w=800&q=80"
    )
    assert not is_denied_stock_photo(
        "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?auto=format&fit=crop&w=800&q=80"
    )


def test_cjk_detect() -> None:
    assert contains_cjk("第 1 天：food 主題")
    assert contains_cjk("大阪焼")
    assert not contains_cjk("Day 1: Food focus")


def test_unique_photo_and_lunch_helpers() -> None:
    plans = [
        {
            "activities": [
                {"is_food_slot": False, "photo_url": "https://a.example/1.jpg"},
                {"is_food_slot": True, "meal_role": "lunch", "poi_name": "Ramen"},
            ]
        },
        {
            "activities": [
                {"is_food_slot": False, "photo_url": "https://a.example/2.jpg"},
                {"is_food_slot": True, "meal_role": "lunch", "poi_name": "Sushi"},
            ]
        },
    ]
    unique, total = unique_non_meal_photos(plans)
    assert unique == 2
    assert total == 2
    assert unique_lunch_names(plans) == ["Ramen", "Sushi"]


def test_unique_names_and_overlap_helpers() -> None:
    plans = [
        {
            "activities": [
                {
                    "time_slot": "10:00-11:00",
                    "poi_name": "Senso-ji",
                    "category": "attraction",
                    "is_food_slot": False,
                },
                {
                    "time_slot": "12:00-13:30",
                    "poi_name": "Sushi / Chirashi",
                    "is_food_slot": True,
                    "meal_role": "lunch",
                },
                {
                    "time_slot": "12:00-13:00",
                    "poi_name": "Ueno Park Cafe Rest",
                    "category": "rest",
                    "is_food_slot": False,
                },
                {
                    "time_slot": "18:30-20:00",
                    "poi_name": "Sushi Set",
                    "is_food_slot": True,
                    "meal_role": "dinner",
                },
            ]
        },
        {
            "activities": [
                {
                    "time_slot": "10:00-11:00",
                    "poi_name": "Senso-ji",
                    "category": "attraction",
                    "is_food_slot": False,
                }
            ]
        },
    ]
    unique, total = unique_non_meal_poi_names(plans)
    assert unique == 2
    assert total == 3
    pairs = overlapping_activity_pairs(plans[0]["activities"])
    assert pairs
    families = day_meal_families(plans[0]["activities"])
    assert families.count("sushi") == 2
