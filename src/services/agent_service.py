"""
Tool-calling itinerary agent (Phase 3).

Flow (see docs/AGENT_ARCHITECTURE.md):
  User Input → POI Retrieval Tool → Schedule Evaluator Tool
            → Validated Structured Output (ItineraryResponse)

The default planner is a deterministic tool-calling loop (LLM seam injectable
via ``llm_client``). Live LLM providers can plug in later without changing
the API contract.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Protocol

from src.schemas.country import Locale, localize_i18n
from src.schemas.itinerary import (
    Activity,
    ActivityCategory,
    DailyItinerary,
    ItineraryRequest,
    ItineraryResponse,
    TripPace,
)
from src.services.agent_tools import (
    evaluate_schedule_and_budget_tool,
    search_pois_tool,
)
from src.services import itinerary_i18n as i18n
from src.services.poi_photos import resolve_poi_photo
from src.utils.logger import elapsed_timer, get_logger, log_event

logger = get_logger(__name__)

DEFAULT_MAX_TURNS = 3


def _resolve_city_name(city_id: str, locale: Locale | str | None = None) -> str:
    """Prefer Supabase city name localized by ``locale``; fall back to mock map."""
    loc = locale if isinstance(locale, Locale) else Locale(str(locale or "en"))
    mock = i18n.MOCK_CITY_NAMES.get(city_id)
    if mock:
        return i18n.pick(loc, mock, fallback="City")
    try:
        from src.deps import get_supabase

        rows = (
            get_supabase()
            .table("cities")
            .select("name, slug")
            .eq("id", city_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if rows:
            name = rows[0].get("name") or {}
            if isinstance(name, dict):
                return localize_i18n(name, loc) or str(rows[0].get("slug") or "City")
            return str(name)
    except Exception:  # noqa: BLE001
        pass
    return "Unknown city"


# How many POIs of each category to request when drafting a day.
# Food venue POIs are not used for meal slots — Lunch/Dinner are injected as food types.
_PACE_DRAFT_COUNTS: dict[str, dict[str, int]] = {
    TripPace.RELAXED.value: {"attraction": 1, "food": 0, "rest": 1},
    TripPace.MODERATE.value: {"attraction": 2, "food": 0, "rest": 1},
    TripPace.PACKED.value: {"attraction": 3, "food": 0, "rest": 1},
}


class AgentPlanningError(Exception):
    """Raised when the agent cannot produce a valid itinerary within max turns."""

    def __init__(self, message: str, *, violations: list[str] | None = None) -> None:
        super().__init__(message)
        self.violations = violations or []


class ItineraryLLMClient(Protocol):
    """
    Optional LLM seam: given tool results + request context, propose a day draft.

    Default ``None`` uses the built-in heuristic proposer (still tool-grounded).
    """

    def propose_daily_plan(
        self,
        *,
        request: ItineraryRequest,
        day_number: int,
        poi_pool: list[dict[str, Any]],
        previous_violations: list[str],
        turn: int,
    ) -> dict[str, Any]:
        """Return a daily_plan dict with theme + activities (tool-grounded)."""


ToolFn = Callable[..., Any]


class AgentService:
    """Orchestrates the itinerary tool-calling loop and builds ``ItineraryResponse``."""

    def __init__(
        self,
        *,
        max_turns: int = DEFAULT_MAX_TURNS,
        llm_client: ItineraryLLMClient | None = None,
        search_pois: ToolFn = search_pois_tool,
        evaluate_schedule: ToolFn = evaluate_schedule_and_budget_tool,
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be >= 1")
        self.max_turns = max_turns
        self._llm = llm_client
        self._search_pois = search_pois
        self._evaluate_schedule = evaluate_schedule

    async def plan_itinerary(self, request: ItineraryRequest) -> ItineraryResponse:
        """
        Plan a multi-day itinerary for ``request.city_id``.

        Loop (per day, up to ``max_turns``):
          1. Invoke POI retrieval tool(s).
          2. Draft a daily plan (LLM or heuristic).
          3. Invoke schedule/budget evaluator; refine on violations.
          4. Parse validated days into ``ItineraryResponse``.
        """
        city_id = str(request.city_id)
        city_name = _resolve_city_name(city_id, request.locale)
        log_event(
            logger,
            "agent_plan_started",
            city_id=city_id,
            days=request.days,
            pace=request.pace.value,
            daily_budget_usd=request.daily_budget_usd,
            locale=str(request.locale),
            max_turns=self.max_turns,
        )

        with elapsed_timer() as timer:
            try:
                poi_pool = self._invoke_poi_retrieval(city_id, request.preferences)
                if not poi_pool:
                    raise AgentPlanningError(
                        f"No POIs found for city_id={city_id}",
                        violations=["NO_POIS"],
                    )

                daily_plans: list[DailyItinerary] = []
                reasoning_parts: list[str] = []
                used_names: set[str] = set()
                used_urls: set[str] = set()

                for day_number in range(1, request.days + 1):
                    day, day_reasoning = self._plan_one_day_with_retries(
                        request=request,
                        day_number=day_number,
                        poi_pool=poi_pool,
                        used_names=used_names,
                        used_urls=used_urls,
                    )
                    daily_plans.append(day)
                    reasoning_parts.append(day_reasoning)
                    for act in day.activities:
                        used_names.add(act.poi_name)
                        if act.poi_id:
                            used_names.add(act.poi_id)
                        if act.photo_url:
                            used_urls.add(act.photo_url)

                total_cost = sum(d.estimated_daily_cost for d in daily_plans)
                agent_reasoning = " ".join(reasoning_parts).strip() or (
                    i18n.fallback_agent_reasoning(
                        request.days,
                        request.pace.value,
                        city_name,
                        request.daily_budget_usd,
                        request.locale,
                    )
                )

                response = ItineraryResponse(
                    city_name=city_name,
                    total_cost_usd=float(total_cost),
                    daily_plans=daily_plans,
                    agent_reasoning=agent_reasoning,
                )
            except AgentPlanningError as exc:
                log_event(
                    logger,
                    "agent_plan_failed",
                    duration_ms=timer.duration_ms,
                    status="planning_error",
                    city_id=city_id,
                    violations=exc.violations,
                    error=str(exc),
                )
                raise

        log_event(
            logger,
            "agent_plan_completed",
            duration_ms=timer.duration_ms,
            status="success",
            city_id=city_id,
            city_name=city_name,
            days=len(response.daily_plans),
            total_cost_usd=response.total_cost_usd,
        )
        return response

    def _invoke_poi_retrieval(
        self,
        city_id: str,
        preferences: list[str],
    ) -> list[dict[str, Any]]:
        """Function-call ``search_pois_tool`` for each activity category."""
        expanded = list(preferences or [])
        try:
            from src.services.intent_extraction import extract_interests

            joined = " ".join(expanded)
            for tag in extract_interests(joined):
                if tag not in expanded:
                    expanded.append(tag)
        except Exception:  # noqa: BLE001
            pass

        pool: list[dict[str, Any]] = []
        seen: set[str] = set()
        for category in ("attraction", "food", "rest"):
            hits = self._search_pois(
                city_id=city_id,
                category=category,
                preferences=expanded,
                limit=24,
            )
            for poi in hits:
                name = poi["name"]
                if name in seen:
                    continue
                seen.add(name)
                pool.append(poi)
        return pool

    def _plan_one_day_with_retries(
        self,
        *,
        request: ItineraryRequest,
        day_number: int,
        poi_pool: list[dict[str, Any]],
        used_names: set[str],
        used_urls: set[str],
    ) -> tuple[DailyItinerary, str]:
        previous_violations: list[str] = []
        last_eval: dict[str, Any] | None = None
        draft = self._propose_daily_plan(
            request=request,
            day_number=day_number,
            poi_pool=poi_pool,
            used_names=used_names,
            used_urls=used_urls,
            previous_violations=previous_violations,
            turn=1,
        )

        for turn in range(1, self.max_turns + 1):
            last_eval = self._evaluate_schedule(
                daily_plan=draft,
                daily_budget_usd=request.daily_budget_usd,
                pace=request.pace.value,
            )
            violations = list(last_eval.get("violations") or [])
            log_event(
                logger,
                "agent_loop_turn",
                day_number=day_number,
                turn=turn,
                max_turns=self.max_turns,
                is_valid=bool(last_eval.get("is_valid")),
                violations=violations,
                total_cost_usd=last_eval.get("total_cost_usd"),
                total_duration_minutes=last_eval.get("total_duration_minutes"),
            )
            if last_eval.get("is_valid"):
                daily = self._parse_daily_itinerary(draft, last_eval)
                reasoning = i18n.day_validated_reasoning(
                    day_number,
                    turn,
                    self.max_turns,
                    daily.estimated_daily_cost,
                    last_eval.get("total_duration_minutes"),
                    request.locale,
                )
                return daily, reasoning

            previous_violations = violations
            if any("budget" in v.lower() for v in violations):
                log_event(
                    logger,
                    "agent_budget_violation",
                    day_number=day_number,
                    turn=turn,
                    violations=violations,
                    daily_budget_usd=request.daily_budget_usd,
                )
            if turn >= self.max_turns:
                break

            refined = self._refine_draft_after_violation(draft, previous_violations)
            if refined.get("activities"):
                draft = refined
            else:
                draft = self._propose_daily_plan(
                    request=request,
                    day_number=day_number,
                    poi_pool=poi_pool,
                    used_names=used_names,
                    used_urls=used_urls,
                    previous_violations=previous_violations,
                    turn=turn + 1,
                )

        violations = list((last_eval or {}).get("violations") or previous_violations)
        raise AgentPlanningError(
            f"Could not validate day {day_number} within {self.max_turns} turns",
            violations=violations,
        )

    def _propose_daily_plan(
        self,
        *,
        request: ItineraryRequest,
        day_number: int,
        poi_pool: list[dict[str, Any]],
        used_names: set[str],
        used_urls: set[str],
        previous_violations: list[str],
        turn: int,
    ) -> dict[str, Any]:
        if self._llm is not None:
            try:
                draft = self._llm.propose_daily_plan(
                    request=request,
                    day_number=day_number,
                    poi_pool=poi_pool,
                    previous_violations=previous_violations,
                    turn=turn,
                )
                self._apply_rotated_meals_and_photos(
                    draft,
                    request=request,
                    day_number=day_number,
                    used_names=used_names,
                    used_urls=used_urls,
                    poi_pool=poi_pool,
                )
                return draft
            except Exception as exc:  # noqa: BLE001
                log_event(
                    logger,
                    "agent_llm_fallback",
                    day_number=day_number,
                    turn=turn,
                    error=str(exc),
                )
        return self._heuristic_propose_daily_plan(
            request=request,
            day_number=day_number,
            poi_pool=poi_pool,
            used_names=used_names,
            used_urls=used_urls,
            previous_violations=previous_violations,
            turn=turn,
        )

    def _heuristic_propose_daily_plan(
        self,
        *,
        request: ItineraryRequest,
        day_number: int,
        poi_pool: list[dict[str, Any]],
        used_names: set[str],
        used_urls: set[str],
        previous_violations: list[str],
        turn: int,
    ) -> dict[str, Any]:
        counts = dict(_PACE_DRAFT_COUNTS[request.pace.value])
        # Later turns: prefer fewer / cheaper stops (never drop required meals).
        if turn > 1 or previous_violations:
            counts["attraction"] = max(0, counts["attraction"] - (turn - 1))
            counts["rest"] = max(0, counts["rest"] - (turn - 1))
            counts["food"] = 0
            if request.pace == TripPace.RELAXED or turn >= 2:
                counts = {"attraction": 1, "food": 0, "rest": 0}

        selected = self._select_pois_for_day(
            poi_pool=poi_pool,
            counts=counts,
            used_names=used_names,
            day_number=day_number,
            prefer_cheap=bool(previous_violations) or turn > 1,
            budget=request.daily_budget_usd,
        )
        # Always keep at least one non-meal activity if pool non-empty.
        if not selected and poi_pool:
            non_food = [p for p in poi_pool if p.get("category") != "food"] or poi_pool
            cheapest = sorted(non_food, key=lambda p: float(p["cost_usd"]))[0]
            selected = [cheapest]

        city_name = _resolve_city_name(str(request.city_id), request.locale)
        city_name_en = _resolve_city_name(str(request.city_id), Locale.EN)
        activities = self._merge_with_meal_slots(
            poi_activities=self._pois_to_activities(
                selected,
                locale=request.locale,
                city_hint=city_name_en,
                used_urls=used_urls,
            ),
            city_name=city_name,
            city_name_en=city_name_en,
            preferences=list(request.preferences or []),
            day_number=day_number,
            locale=request.locale,
            used_names=used_names,
        )
        theme = self._day_theme(
            day_number, request.preferences, selected, request.locale
        )
        return {
            "day_number": day_number,
            "theme": theme,
            "activities": activities,
        }

    def _meal_food_types(
        self,
        city_name: str,
        preferences: list[str],
        day_number: int,
        locale: Locale | str | None = None,
        *,
        city_name_en: str | None = None,
        used: set[str] | None = None,
    ) -> tuple[str, str]:
        # Cuisine needles match English place names; include both display forms.
        hay_name = f"{city_name_en or ''} {city_name}".strip()
        return i18n.meal_pair(
            hay_name, preferences, day_number, locale, used=used
        )

    def _merge_with_meal_slots(
        self,
        *,
        poi_activities: list[dict[str, Any]],
        city_name: str,
        preferences: list[str],
        day_number: int,
        locale: Locale | str | None = None,
        city_name_en: str | None = None,
        used_names: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        lunch_name, dinner_name = self._meal_food_types(
            city_name,
            preferences,
            day_number,
            locale,
            city_name_en=city_name_en,
            used=used_names,
        )
        lunch = {
            "time_slot": "12:00-13:30",
            "poi_name": lunch_name,
            "category": "food",
            "cost_usd": 12.0,
            "duration_minutes": 90,
            "description": i18n.meal_description(
                "lunch", city_name, locale, dish=lunch_name
            ),
            "is_food_slot": True,
            "meal_role": "lunch",
            "lat": None,
            "lon": None,
            "poi_id": None,
            "address": None,
            "photo_url": i18n.meal_photo(lunch_name, "lunch"),
            "is_custom": False,
        }
        dinner = {
            "time_slot": "18:30-20:00",
            "poi_name": dinner_name,
            "category": "food",
            "cost_usd": 20.0,
            "duration_minutes": 90,
            "description": i18n.meal_description(
                "dinner", city_name, locale, dish=dinner_name
            ),
            "is_food_slot": True,
            "meal_role": "dinner",
            "lat": None,
            "lon": None,
            "poi_id": None,
            "address": None,
            "photo_url": i18n.meal_photo(dinner_name, "dinner"),
            "is_custom": False,
        }

        morning = [a for a in poi_activities if _slot_start_minutes(a) < 12 * 60]
        afternoon = [a for a in poi_activities if _slot_start_minutes(a) >= 12 * 60]
        if not morning and not afternoon and poi_activities:
            mid = max(1, len(poi_activities) // 2)
            morning = poi_activities[:mid]
            afternoon = poi_activities[mid:]
        elif not morning and poi_activities:
            morning = poi_activities[:1]
            afternoon = poi_activities[1:]

        return _retarget_afternoon_after_lunch([*morning, lunch, *afternoon, dinner])

    def _select_pois_for_day(
        self,
        *,
        poi_pool: list[dict[str, Any]],
        counts: dict[str, int],
        used_names: set[str],
        day_number: int,
        prefer_cheap: bool,
        budget: float,
    ) -> list[dict[str, Any]]:
        by_cat: dict[str, list[dict[str, Any]]] = {
            "attraction": [],
            "food": [],
            "rest": [],
        }
        for poi in poi_pool:
            cat = poi["category"]
            if cat in by_cat:
                by_cat[cat].append(poi)

        def sort_key(p: dict[str, Any]) -> tuple:
            used = p["name"] in used_names or (
                str(p.get("id") or "") in used_names
            )
            cost = float(p["cost_usd"])
            rotate = hash(p["name"]) % 7
            return (
                1 if used else 0,
                _poi_notability_penalty(p),
                cost if prefer_cheap else rotate,
                cost,
            )

        selected: list[dict[str, Any]] = []
        running_cost = 0.0
        for category, want in counts.items():
            if want <= 0:
                continue
            raw = list(by_cat.get(category, []))
            unused = [
                p
                for p in raw
                if p["name"] not in used_names
                and str(p.get("id") or "") not in used_names
            ]
            candidates = unused if unused else raw
            candidates = sorted(candidates, key=sort_key)
            if not prefer_cheap and candidates:
                offset = (day_number - 1) % len(candidates)
                candidates = candidates[offset:] + candidates[:offset]
            taken = 0
            for poi in candidates:
                if taken >= want:
                    break
                cost = float(poi["cost_usd"])
                if running_cost + cost > budget and prefer_cheap:
                    continue
                if any(s["name"] == poi["name"] for s in selected):
                    continue
                selected.append(poi)
                running_cost += cost
                taken += 1
        return selected

    def _refine_draft_after_violation(
        self,
        draft: dict[str, Any],
        violations: list[str],
    ) -> dict[str, Any]:
        activities = list(draft.get("activities") or [])
        if not activities:
            return draft

        text = " ".join(violations).lower()
        if "missing_meals" in text:
            # Ensure meals exist; do not strip them further.
            return draft
        if "overlapping" in text or "overlap" in text:
            activities = _retarget_afternoon_after_lunch(activities)
        if "budget" in text:
            # Drop the most expensive non-meal, non-rest activity first.
            droppable = [
                a
                for a in activities
                if not a.get("is_food_slot") and a.get("category") != "rest"
            ]
            if droppable:
                expensive = max(droppable, key=lambda a: float(a.get("cost_usd") or 0))
                activities = [a for a in activities if a is not expensive]
        if "packed" in text or "pace" in text:
            drop_idx = None
            for i in range(len(activities) - 1, -1, -1):
                act = activities[i]
                if act.get("is_food_slot"):
                    continue
                if act.get("category") == "attraction":
                    drop_idx = i
                    break
            if drop_idx is None:
                for i in range(len(activities) - 1, -1, -1):
                    if not activities[i].get("is_food_slot"):
                        drop_idx = i
                        break
            if drop_idx is not None:
                activities = [a for i, a in enumerate(activities) if i != drop_idx]

        refined = dict(draft)
        refined["activities"] = activities
        return refined

    def _pois_to_activities(
        self,
        pois: list[dict[str, Any]],
        *,
        locale: Locale | str | None = None,
        city_hint: str | None = None,
        used_urls: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        activities: list[dict[str, Any]] = []
        cursor_minutes = 9 * 60  # 09:00
        seen_urls = set(used_urls or ())
        for poi in pois:
            duration = int(poi["duration_minutes"])
            start = cursor_minutes
            end = start + duration
            # Leave room before lunch window when possible.
            if start < 12 * 60 <= end:
                end = 12 * 60
                duration = max(30, end - start)
            city = str(poi.get("city") or city_hint or "")
            photo = resolve_poi_photo(
                str(poi.get("name") or ""),
                city=city or None,
                category=str(poi.get("category") or "attraction"),
                used_urls=seen_urls,
                lat=_as_float(poi.get("lat")),
                lon=_as_float(poi.get("lon")),
                tags=poi.get("tags") or [],
            )
            if photo:
                seen_urls.add(photo)
            desc = i18n.localize_activity_description(
                str(poi.get("description") or poi["name"]),
                poi_name=str(poi["name"]),
                category=str(poi.get("category") or "attraction"),
                locale=locale,
            )
            activities.append(
                {
                    "time_slot": f"{_fmt_hhmm(start)}-{_fmt_hhmm(end)}",
                    "poi_name": poi["name"],
                    "category": poi["category"],
                    "cost_usd": float(poi["cost_usd"]),
                    "duration_minutes": duration,
                    "description": desc,
                    "is_food_slot": False,
                    "meal_role": None,
                    "lat": _as_float(poi.get("lat")),
                    "lon": _as_float(poi.get("lon")),
                    "poi_id": str(poi["id"]) if poi.get("id") else None,
                    "address": poi.get("address"),
                    "photo_url": photo,
                    "is_custom": False,
                }
            )
            cursor_minutes = end + 30  # travel buffer between slots
            if cursor_minutes < 12 * 60 + 90:
                pass
            elif 12 * 60 <= cursor_minutes < 13 * 60 + 30:
                cursor_minutes = 13 * 60 + 45
        return activities

    def _apply_rotated_meals_and_photos(
        self,
        draft: dict[str, Any],
        *,
        request: ItineraryRequest,
        day_number: int,
        used_names: set[str],
        used_urls: set[str],
        poi_pool: list[dict[str, Any]],
    ) -> None:
        """Force rotated meals and Wikipedia/unique photos on an LLM draft."""
        city_name = _resolve_city_name(str(request.city_id), request.locale)
        city_name_en = _resolve_city_name(str(request.city_id), Locale.EN)
        lunch_name, dinner_name = self._meal_food_types(
            city_name,
            list(request.preferences or []),
            day_number,
            request.locale,
            city_name_en=city_name_en,
            used=used_names,
        )
        city_hint = city_name_en
        for poi in poi_pool:
            if poi.get("city"):
                city_hint = str(poi["city"])
                break
        seen_urls = set(used_urls)
        by_name = {str(p.get("name") or ""): p for p in poi_pool}
        activities = list(draft.get("activities") or [])
        for act in activities:
            if act.get("is_food_slot"):
                role = str(act.get("meal_role") or "").lower()
                label = lunch_name if role == "lunch" else dinner_name
                act["poi_name"] = label
                act["photo_url"] = i18n.meal_photo(label, role or "lunch")
                act["description"] = i18n.meal_description(
                    role or "lunch", city_name, request.locale, dish=label
                )
                continue
            name = str(act.get("poi_name") or "")
            cat = str(act.get("category") or "attraction")
            src = by_name.get(name) or {}
            photo = resolve_poi_photo(
                name,
                city=city_hint,
                category=cat,
                used_urls=seen_urls,
                lat=_as_float(act.get("lat") or src.get("lat")),
                lon=_as_float(act.get("lon") or src.get("lon")),
                tags=src.get("tags") or act.get("tags") or [],
            )
            act["photo_url"] = photo
            if photo:
                seen_urls.add(photo)
        draft["activities"] = _retarget_afternoon_after_lunch(activities)

    def _day_theme(
        self,
        day_number: int,
        preferences: list[str],
        selected: list[dict[str, Any]],
        locale: Locale | str | None = None,
    ) -> str:
        return i18n.day_theme(day_number, preferences, selected, locale)

    def _parse_daily_itinerary(
        self,
        draft: dict[str, Any],
        evaluation: dict[str, Any],
    ) -> DailyItinerary:
        activities = [
            Activity(
                time_slot=str(a["time_slot"]),
                poi_name=str(a["poi_name"]),
                category=ActivityCategory(a["category"]),
                cost_usd=float(a["cost_usd"]),
                duration_minutes=int(a["duration_minutes"]),
                description=str(a["description"]),
                is_food_slot=bool(a.get("is_food_slot") or False),
                meal_role=a.get("meal_role") or None,
                lat=_as_float(a.get("lat")),
                lon=_as_float(a.get("lon")),
                poi_id=str(a["poi_id"]) if a.get("poi_id") else None,
                address=str(a["address"]) if a.get("address") else None,
                photo_url=str(a["photo_url"]) if a.get("photo_url") else None,
                is_custom=bool(a.get("is_custom") or False),
            )
            for a in draft.get("activities") or []
        ]
        return DailyItinerary(
            day_number=int(draft["day_number"]),
            theme=str(draft.get("theme") or f"Day {draft['day_number']}"),
            estimated_daily_cost=float(evaluation.get("total_cost_usd", 0)),
            activities=activities,
        )


def _fmt_hhmm(total_minutes: int) -> str:
    total_minutes = max(0, total_minutes) % (24 * 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def _slot_start_minutes(activity: dict[str, Any]) -> int:
    slot = str(activity.get("time_slot") or "")
    start = slot.split("-", 1)[0].strip()
    if ":" not in start:
        return 9 * 60
    try:
        hh, mm = start.split(":", 1)
        return int(hh) * 60 + int(mm)
    except ValueError:
        return 9 * 60


def _retarget_afternoon_after_lunch(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep lunch at 12:00; shift later non-meal stops to 13:45+ so slots do not overlap."""
    cursor = 13 * 60 + 45
    out: list[dict[str, Any]] = []
    for act in activities:
        start = _slot_start_minutes(act)
        if act.get("is_food_slot") or start < 12 * 60:
            out.append(act)
            continue
        duration = int(act.get("duration_minutes") or 60)
        end = cursor + duration
        updated = dict(act)
        updated["time_slot"] = f"{_fmt_hhmm(cursor)}-{_fmt_hhmm(end)}"
        out.append(updated)
        cursor = end + 30
    return out


def _poi_notability_penalty(poi: dict[str, Any]) -> int:
    tags = [str(t).lower() for t in (poi.get("tags") or [])]
    tag_blob = " ".join(tags)
    name = str(poi.get("name") or "").lower()
    hay = f"{name} {tag_blob}"
    if any(t.startswith("wikidata:") or t == "wikipedia" for t in tags):
        return 0
    if any(tok in tag_blob for tok in ("museum", "castle", "sightseeing", "gallery")):
        return 0
    if re.search(r"church|branch|sports ground|place_of_worship", hay):
        return 2
    if "temple" in hay or "shrine" in hay:
        return 1
    return 0


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
