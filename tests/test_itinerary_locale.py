"""Locale wiring for itinerary narratives."""

from __future__ import annotations

from uuid import UUID

import pytest

from src.schemas.itinerary import ItineraryRequest, TripPace
from src.services.agent_service import AgentService
from src.services.agent_tools import MOCK_CITY_TOKYO


@pytest.mark.asyncio
async def test_plan_locale_zh_hk_localizes_narrative() -> None:
    service = AgentService(max_turns=3)
    result = await service.plan_itinerary(
        ItineraryRequest(
            city_id=UUID(MOCK_CITY_TOKYO),
            days=1,
            pace=TripPace.MODERATE,
            daily_budget_usd=150,
            preferences=["culture"],
            locale="zh-HK",
        )
    )
    assert result.city_name == "東京"
    assert "第" in result.daily_plans[0].theme or "天" in result.daily_plans[0].theme
    meals = [a for a in result.daily_plans[0].activities if a.is_food_slot]
    assert any("拉麵" in m.poi_name or "定食" in m.poi_name or "午餐" in m.poi_name for m in meals)
    assert any("\u4e00" <= ch <= "\u9fff" for ch in result.agent_reasoning)


@pytest.mark.asyncio
async def test_plan_locale_ja_localizes_narrative() -> None:
    service = AgentService(max_turns=3)
    result = await service.plan_itinerary(
        ItineraryRequest(
            city_id=UUID(MOCK_CITY_TOKYO),
            days=1,
            pace=TripPace.RELAXED,
            daily_budget_usd=150,
            preferences=["food"],
            locale="ja",
        )
    )
    assert result.city_name == "東京"
    assert "日目" in result.daily_plans[0].theme
    meals = [a for a in result.daily_plans[0].activities if a.is_food_slot]
    assert len(meals) >= 2


def test_localize_activity_description_wraps_english() -> None:
    from src.services.itinerary_i18n import localize_activity_description

    en = "Walk the historic core and signature landmarks."
    zh = localize_activity_description(
        en, poi_name="Osaka Castle", category="attraction", locale="zh-HK"
    )
    assert zh.startswith("Osaka Castle")
    assert "景點" in zh
    assert en in zh
    ja = localize_activity_description(
        en, poi_name="Osaka Castle", category="attraction", locale="ja"
    )
    assert "観光" in ja
    already = localize_activity_description(
        "大阪城の歴史を歩く。",
        poi_name="Osaka Castle",
        category="attraction",
        locale="zh-HK",
    )
    assert already == "大阪城の歴史を歩く。"
