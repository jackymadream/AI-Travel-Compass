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

import asyncio
import re
from dataclasses import dataclass
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
    PACE_LIMITS,
    TRAVEL_BUFFER_MINUTES,
    evaluate_schedule_and_budget_tool,
    pace_only_violations,
    scheduled_total_minutes,
    search_pois_tool,
)
from src.services import itinerary_i18n as i18n
from src.services.cuisine_catalog import (
    # cuisine_photo_url,  # meal stock photos disabled — UI uses icons
    cuisine_tool_dicts,
    is_meal_slot_poi,
    poi_cuisine_family,
)
from src.services.poi_photos import persistable_photo_url
from src.utils.logger import elapsed_timer, get_logger, log_event

logger = get_logger(__name__)

DEFAULT_MAX_TURNS = 3

PlanProgressCallback = Callable[["PlanProgress"], None]


@dataclass(frozen=True)
class PlanProgress:
    """Structured progress event for itinerary generation (UI / SSE)."""

    step: str
    percent: int
    day_number: int | None = None
    total_days: int | None = None
    turn: int | None = None


def _emit_progress(
    callback: PlanProgressCallback | None,
    *,
    step: str,
    percent: int,
    day_number: int | None = None,
    total_days: int | None = None,
    turn: int | None = None,
) -> None:
    if callback is None:
        return
    progress = PlanProgress(
        step=step,
        percent=min(100, max(0, int(percent))),
        day_number=day_number,
        total_days=total_days,
        turn=turn,
    )
    callback(progress)


async def _notify_progress(
    callback: PlanProgressCallback | None,
    *,
    step: str,
    percent: int,
    day_number: int | None = None,
    total_days: int | None = None,
    turn: int | None = None,
) -> None:
    """Emit progress and yield so SSE chunks can flush during long planning."""
    _emit_progress(
        callback,
        step=step,
        percent=percent,
        day_number=day_number,
        total_days=total_days,
        turn=turn,
    )
    await asyncio.sleep(0)


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
# Lunch/Dinner come from cuisine_catalog food POIs, not extra restaurant stops.
_PACE_DRAFT_COUNTS: dict[str, dict[str, int]] = {
    TripPace.RELAXED.value: {"attraction": 1, "food": 0, "rest": 1},
    TripPace.MODERATE.value: {"attraction": 2, "food": 0, "rest": 1},
    TripPace.PACKED.value: {"attraction": 3, "food": 0, "rest": 1},
}

_NIGHTLIFE_PREF_TOKENS = frozenset(
    {
        "nightlife",
        "bar",
        "pub",
        "club",
        "drinks",
        "drink",
        "drinking",
    }
)
_NIGHTLIFE_POI_TOKENS = frozenset(
    {
        "nightlife",
        "bar",
        "pub",
        "club",
        "drinks",
        "drink",
        "izakaya",
        "golden gai",
        "yokocho",
        "nightclub",
        "kabukicho",
    }
)


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

    async def plan_itinerary(
        self,
        request: ItineraryRequest,
        *,
        on_progress: PlanProgressCallback | None = None,
    ) -> ItineraryResponse:
        """
        Plan a multi-day itinerary for ``request.city_id``.

        Loop (per day, up to ``max_turns``):
          1. Invoke POI retrieval tool(s).
          2. Draft a daily plan (LLM or heuristic).
          3. Invoke schedule/budget evaluator; refine on violations.
          4. Parse validated days into ``ItineraryResponse``.
        """
        city_id = str(request.city_id)
        total_days = int(request.days)
        await _notify_progress(on_progress, step="starting", percent=5)
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
                await _notify_progress(on_progress, step="poi_retrieval", percent=15)
                poi_pool = await asyncio.to_thread(
                    self._invoke_poi_retrieval,
                    city_id,
                    request.preferences,
                )
                await _notify_progress(on_progress, step="poi_retrieval", percent=25)
                if not poi_pool:
                    raise AgentPlanningError(
                        f"No POIs found for city_id={city_id}",
                        violations=["NO_POIS"],
                    )

                daily_plans: list[DailyItinerary] = []
                reasoning_parts: list[str] = []
                used_names: set[str] = set()
                used_urls: set[str] = set()
                uncovered = _coverage_tags(list(request.preferences or []))

                for day_number in range(1, request.days + 1):
                    day_pct = 25 + int((day_number - 1) / max(total_days, 1) * 60)
                    await _notify_progress(
                        on_progress,
                        step="plan_day",
                        percent=day_pct,
                        day_number=day_number,
                        total_days=total_days,
                    )
                    day, day_reasoning = await self._plan_one_day_with_retries(
                        request=request,
                        day_number=day_number,
                        poi_pool=poi_pool,
                        used_names=used_names,
                        used_urls=used_urls,
                        uncovered_tags=uncovered,
                        on_progress=on_progress,
                        total_days=total_days,
                    )
                    await _notify_progress(
                        on_progress,
                        step="plan_day",
                        percent=25 + int(day_number / max(total_days, 1) * 60),
                        day_number=day_number,
                        total_days=total_days,
                    )
                    daily_plans.append(day)
                    reasoning_parts.append(day_reasoning)
                    for act in day.activities:
                        used_names.add(act.poi_name)
                        if act.poi_id:
                            used_names.add(act.poi_id)
                        if act.photo_url:
                            used_urls.add(act.photo_url)
                        uncovered -= _activity_matched_tags(
                            act, list(request.preferences or [])
                        )

                total_cost = sum(d.estimated_daily_cost for d in daily_plans)
                user_summary = i18n.trip_user_summary(
                    city_name,
                    request.days,
                    request.pace.value,
                    list(request.preferences or []),
                    request.locale,
                    missing_tags=sorted(uncovered),
                )
                prep_tips = i18n.trip_prep_tips(
                    city_name,
                    list(request.preferences or []),
                    request.locale,
                )
                await _notify_progress(on_progress, step="finalize", percent=92)
                agent_reasoning = user_summary or (
                    " ".join(reasoning_parts).strip()
                    or i18n.fallback_agent_reasoning(
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
                    user_summary=user_summary,
                    prep_tips=prep_tips,
                )
                await _notify_progress(on_progress, step="complete", percent=100)
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
                limit=32,
            )
            for poi in hits:
                name = poi["name"]
                if name in seen:
                    continue
                seen.add(name)
                pool.append(poi)
        city_en = _resolve_city_name(city_id, Locale.EN)
        for row in cuisine_tool_dicts(
            city_slug=city_en.lower(),
            city_id=city_id,
            city_display=city_en,
        ):
            name = str(row.get("name") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            pool.append(row)
        return pool

    async def _plan_one_day_with_retries(
        self,
        *,
        request: ItineraryRequest,
        day_number: int,
        poi_pool: list[dict[str, Any]],
        used_names: set[str],
        used_urls: set[str],
        uncovered_tags: set[str] | None = None,
        on_progress: PlanProgressCallback | None = None,
        total_days: int | None = None,
    ) -> tuple[DailyItinerary, str]:
        previous_violations: list[str] = []
        last_eval: dict[str, Any] | None = None
        days_total = total_days or int(request.days)
        draft_base_pct = 25 + int((day_number - 1) / max(days_total, 1) * 60)
        await _notify_progress(
            on_progress,
            step="draft_day",
            percent=min(draft_base_pct + 2, 88),
            day_number=day_number,
            total_days=days_total,
            turn=1,
        )
        draft = await asyncio.to_thread(
            self._propose_daily_plan,
            request=request,
            day_number=day_number,
            poi_pool=poi_pool,
            used_names=used_names,
            used_urls=used_urls,
            previous_violations=previous_violations,
            turn=1,
            uncovered_tags=uncovered_tags,
        )

        for turn in range(1, self.max_turns + 1):
            validate_pct = 25 + int(
                ((day_number - 1) + (turn / max(self.max_turns, 1) * 0.4))
                / max(days_total, 1)
                * 60
            )
            await _notify_progress(
                on_progress,
                step="validate_day",
                percent=validate_pct,
                day_number=day_number,
                total_days=days_total,
                turn=turn,
            )
            last_eval = await asyncio.to_thread(
                self._evaluate_schedule,
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
                soft_hints = _soft_preference_coverage_hints(
                    draft,
                    uncovered_tags=uncovered_tags,
                    poi_pool=poi_pool,
                    used_names=used_names,
                    preferences=list(request.preferences or []),
                )
                soft_hints = list(
                    dict.fromkeys(
                        soft_hints
                        + _nightlife_day_quota_hints(
                            draft,
                            preferences=list(request.preferences or []),
                            poi_pool=poi_pool,
                            used_names=used_names,
                        )
                    )
                )
                if soft_hints and turn < self.max_turns:
                    previous_violations = list(
                        dict.fromkeys([*previous_violations, *soft_hints])
                    )
                    log_event(
                        logger,
                        "agent_soft_coverage_retry",
                        day_number=day_number,
                        turn=turn,
                        hints=soft_hints,
                    )
                    draft = await asyncio.to_thread(
                        self._propose_daily_plan,
                        request=request,
                        day_number=day_number,
                        poi_pool=poi_pool,
                        used_names=used_names,
                        used_urls=used_urls,
                        previous_violations=previous_violations,
                        turn=turn + 1,
                        uncovered_tags=uncovered_tags,
                    )
                    continue
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

            previous_violations = violations + [
                str(s) for s in (last_eval.get("suggested_adjustments") or []) if s
            ]
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
                if pace_only_violations(violations) and (draft.get("activities") or []):
                    daily = self._parse_daily_itinerary(
                        draft,
                        last_eval or {},
                        warnings=list(violations),
                    )
                    log_event(
                        logger,
                        "agent_pace_best_effort",
                        day_number=day_number,
                        turn=turn,
                        violations=violations,
                        total_duration_minutes=last_eval.get("total_duration_minutes")
                        if last_eval
                        else None,
                    )
                    mins = (last_eval or {}).get("total_duration_minutes")
                    reasoning = (
                        f"Day {day_number}: kept a best-effort plan after {turn} turns "
                        f"(pace target missed"
                        + (f", {mins} minutes" if mins is not None else "")
                        + ")."
                    )
                    return daily, reasoning
                break

            refined = await asyncio.to_thread(
                self._refine_draft_after_violation,
                draft,
                previous_violations,
                pace=request.pace.value,
                daily_budget_usd=request.daily_budget_usd,
            )
            if refined.get("activities"):
                draft = refined
            else:
                await _notify_progress(
                    on_progress,
                    step="draft_day",
                    percent=min(draft_base_pct + 4, 88),
                    day_number=day_number,
                    total_days=days_total,
                    turn=turn + 1,
                )
                draft = await asyncio.to_thread(
                    self._propose_daily_plan,
                    request=request,
                    day_number=day_number,
                    poi_pool=poi_pool,
                    used_names=used_names,
                    used_urls=used_urls,
                    previous_violations=previous_violations,
                    turn=turn + 1,
                    uncovered_tags=uncovered_tags,
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
        uncovered_tags: set[str] | None = None,
    ) -> dict[str, Any]:
        if self._llm is not None:
            try:
                available = _unused_poi_pool(poi_pool, used_names)
                llm_hints = list(previous_violations)
                if used_names:
                    llm_hints.append(
                        "Do not reuse already-scheduled POI names: "
                        + ", ".join(sorted(str(n) for n in used_names if n)[:40])
                    )
                if uncovered_tags:
                    llm_hints.append(
                        "Still uncovered preference tags — prefer pool POIs whose "
                        "tags/names match: "
                        + ", ".join(sorted(str(t) for t in uncovered_tags if t)[:24])
                    )
                if _wants_nightlife(list(request.preferences or [])):
                    llm_hints.append(
                        "nightlife_day_quota: this day MUST include at least one "
                        "nightlife stop (bar/pub/club/alley/kabukicho) from the pool."
                    )
                draft = self._llm.propose_daily_plan(
                    request=request,
                    day_number=day_number,
                    poi_pool=available,
                    previous_violations=llm_hints,
                    turn=turn,
                )
                self._ground_pool_photos_and_meals(
                    draft,
                    request=request,
                    day_number=day_number,
                    used_names=used_names,
                    used_urls=used_urls,
                    poi_pool=poi_pool,
                )
                draft["activities"] = _ensure_nightlife_in_activities(
                    list(draft.get("activities") or []),
                    poi_pool=poi_pool,
                    used_names=used_names,
                    preferences=list(request.preferences or []),
                )
                draft["activities"] = _geo_cluster_day_activities(
                    list(draft.get("activities") or []),
                    poi_pool=poi_pool,
                    used_names=used_names,
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
            uncovered_tags=uncovered_tags,
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
        uncovered_tags: set[str] | None = None,
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
            preferences=list(request.preferences or []),
            uncovered_tags=uncovered_tags,
        )
        # Always keep at least one non-meal activity if pool non-empty.
        if not selected and poi_pool:
            non_food = [p for p in poi_pool if p.get("category") != "food"] or poi_pool
            cheapest = sorted(non_food, key=lambda p: float(p["cost_usd"]))[0]
            selected = [cheapest]

        selected = _ensure_nightlife_in_selected(
            selected,
            poi_pool=poi_pool,
            used_names=used_names,
            preferences=list(request.preferences or []),
        )

        city_name = _resolve_city_name(str(request.city_id), request.locale)
        city_name_en = _resolve_city_name(str(request.city_id), Locale.EN)
        activities = self._merge_with_meal_slots(
            poi_activities=self._pois_to_activities(
                selected,
                locale=request.locale,
                city_hint=city_name_en,
            ),
            poi_pool=poi_pool,
            city_name=city_name,
            city_name_en=city_name_en,
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
        poi_pool: list[dict[str, Any]],
        city_name: str,
        day_number: int,
        locale: Locale | str | None = None,
        city_name_en: str | None = None,
        used_names: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        lunch_src, dinner_src = _pick_meal_pois(
            poi_pool,
            used_names=used_names or set(),
            day_number=day_number,
        )
        lunch = _meal_activity_from_poi(
            lunch_src,
            role="lunch",
            city_name=city_name,
            locale=locale,
            fallback_label=_fallback_meal_label(
                city_name_en or city_name, day_number, locale, "lunch", used_names
            ),
        )
        dinner = _meal_activity_from_poi(
            dinner_src,
            role="dinner",
            city_name=city_name,
            locale=locale,
            fallback_label=_fallback_meal_label(
                city_name_en or city_name, day_number, locale, "dinner", used_names
            ),
        )

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
        preferences: list[str] | None = None,
        uncovered_tags: set[str] | None = None,
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

        prefs = [p.strip().lower() for p in (preferences or []) if p and str(p).strip()]
        uncovered = {t.lower() for t in (uncovered_tags or set())}
        unconventional = "unconventional" in prefs
        scoring_prefs = [
            p for p in prefs if p not in {"popular", "unconventional"}
        ]
        wants_temple = any(
            p in {"temple", "temples", "religion", "religious", "shrine"}
            for p in prefs
        )
        wants_culture = any(
            p in {"culture", "history", "architecture", "heritage", "traditional"}
            for p in prefs
        )
        temple_like = {"temple", "shrine", "worship", "place_of_worship", "church"}
        culture_non_temple = {
            "architecture",
            "historic",
            "history",
            "heritage",
            "traditional",
            "castle",
            "monument",
            "palace",
            "garden",
            "museum",
            "market",
            "district",
        }
        nightlife_trigger = set(_NIGHTLIFE_PREF_TOKENS)

        def _poi_is_temple_like(poi: dict[str, Any]) -> bool:
            # Detect worship-related POIs using stored tags only.
            tags = " ".join(str(t).lower() for t in (poi.get("tags") or []))
            return any(tok in tags for tok in temple_like) or "religion" in tags

        def _poi_is_culture_non_temple(poi: dict[str, Any]) -> bool:
            hay = " ".join(
                [
                    str(poi.get("name") or ""),
                    str(poi.get("description") or ""),
                    " ".join(str(t) for t in (poi.get("tags") or [])),
                ]
            ).lower()
            return any(tok in hay for tok in culture_non_temple)

        def sort_key(p: dict[str, Any]) -> tuple:
            used = p["name"] in used_names or (
                str(p.get("id") or "") in used_names
            )
            cost = float(p["cost_usd"])
            rotate = hash(p["name"]) % 7
            pref = _preference_match_score(p, scoring_prefs)
            if not wants_temple and _poi_is_temple_like(p):
                # Temple-like stops only get preference credit when user asked for
                # temple/religion — bare ``culture`` should favor architecture/heritage.
                if wants_culture and _poi_is_culture_non_temple(p):
                    pref = max(pref, 1)
                else:
                    pref = 0
            elif wants_culture and not wants_temple and _poi_is_culture_non_temple(p):
                pref = pref + 2
            covers = 1 if uncovered and not _preference_match_score(p, list(uncovered)) else 0
            # Soft coverage: when culture is uncovered, prefer non-temple heritage.
            if (
                uncovered
                and any(t in uncovered for t in ("culture", "architecture", "history"))
                and _poi_is_culture_non_temple(p)
                and not _poi_is_temple_like(p)
            ):
                covers = 0
            notable = _poi_notability_penalty(p)
            discovery = -notable if unconventional else notable
            if not wants_temple and _poi_is_temple_like(p):
                discovery += 5
            return (
                1 if used else 0,
                covers,
                -pref,
                discovery,
                cost if prefer_cheap else rotate,
                cost,
            )

        selected: list[dict[str, Any]] = []
        running_cost = 0.0
        for category, want in counts.items():
            if want <= 0:
                continue
            raw = list(by_cat.get(category, []))
            if category == "attraction" and any(
                p in scoring_prefs for p in nightlife_trigger
            ):
                night_terms = list(nightlife_trigger)
                extra = [
                    p
                    for p in by_cat.get("food", [])
                    if _preference_match_score(p, night_terms) > 0
                ]
                raw = raw + extra
            unused = [
                p
                for p in raw
                if p["name"] not in used_names
                and str(p.get("id") or "") not in used_names
            ]
            notable_unused = [p for p in unused if not _is_junction_named_poi(p)]
            if notable_unused:
                unused = notable_unused
            candidates = unused if unused else raw
            candidates = sorted(candidates, key=sort_key)
            if not prefer_cheap and candidates and not scoring_prefs:
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
        return _geo_cluster_selected_pois(selected, poi_pool=poi_pool, used_names=used_names)

    def _refine_draft_after_violation(
        self,
        draft: dict[str, Any],
        violations: list[str],
        *,
        pace: str,
        daily_budget_usd: float | None = None,
    ) -> dict[str, Any]:
        activities = list(draft.get("activities") or [])
        if not activities:
            return draft

        text = " ".join(violations).lower()
        if "missing_meals" in text:
            # Ensure meals exist; do not strip them further.
            return draft
        if "budget" in text:
            budget = float(daily_budget_usd or 0)
            while budget > 0:
                total = sum(float(a.get("cost_usd") or 0) for a in activities)
                if total <= budget:
                    break
                droppable = [
                    a
                    for a in activities
                    if not a.get("is_food_slot") and a.get("category") != "rest"
                ]
                pool = droppable
                if not pool:
                    pool = [
                        a
                        for a in activities
                        if not a.get("is_food_slot") and a.get("category") == "rest"
                    ]
                if not pool:
                    break
                expensive = max(pool, key=lambda a: float(a.get("cost_usd") or 0))
                activities = [a for a in activities if a is not expensive]
        if "packed" in text or "pace" in text:
            activities = _drop_until_under_pace(activities, pace)
        if "overlapping" in text or "overlap" in text or "packed" in text or "budget" in text:
            # Rebuild slots after drops so afternoon stops do not collide with dinner.
            activities = _retarget_afternoon_after_lunch(activities)

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
        del used_urls
        for poi in pois:
            duration = int(poi["duration_minutes"])
            start = cursor_minutes
            end = start + duration
            # Leave room before lunch window when possible.
            if start < 12 * 60 <= end:
                end = 12 * 60
                duration = max(30, end - start)
            photo = persistable_photo_url(str(poi.get("photo_url") or "") or None)
            desc = i18n.localize_activity_description(
                str(poi.get("description") or poi["name"]),
                poi_name=str(poi["name"]),
                category=str(poi.get("category") or "attraction"),
                locale=locale,
            )
            display = _poi_display_name(poi, locale)
            activities.append(
                {
                    "time_slot": f"{_fmt_hhmm(start)}-{_fmt_hhmm(end)}",
                    "poi_name": poi["name"],
                    "display_name": display,
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

    def _ground_pool_photos_and_meals(
        self,
        draft: dict[str, Any],
        *,
        request: ItineraryRequest,
        day_number: int,
        used_names: set[str],
        used_urls: set[str],
        poi_pool: list[dict[str, Any]],
    ) -> None:
        """Copy persisted POI photos and replace meals with unused cuisine catalog rows."""
        del used_urls
        city_name = _resolve_city_name(str(request.city_id), request.locale)
        city_name_en = _resolve_city_name(str(request.city_id), Locale.EN)
        city_hint = city_name_en
        for poi in poi_pool:
            if poi.get("city"):
                city_hint = str(poi["city"])
                break
        by_name = {str(p.get("name") or ""): p for p in poi_pool}
        activities = self._replace_used_non_meal_activities(
            list(draft.get("activities") or []),
            used_names=used_names,
            poi_pool=poi_pool,
            request=request,
            city_hint=city_hint,
            used_urls=set(),
        )
        lunch_src, dinner_src = _pick_meal_pois(
            poi_pool, used_names=used_names, day_number=day_number
        )
        lunch = _meal_activity_from_poi(
            lunch_src,
            role="lunch",
            city_name=city_name,
            locale=request.locale,
            fallback_label=_fallback_meal_label(
                city_name_en, day_number, request.locale, "lunch", used_names
            ),
        )
        dinner = _meal_activity_from_poi(
            dinner_src,
            role="dinner",
            city_name=city_name,
            locale=request.locale,
            fallback_label=_fallback_meal_label(
                city_name_en, day_number, request.locale, "dinner", used_names
            ),
        )
        grounded: list[dict[str, Any]] = []
        for act in activities:
            if act.get("is_food_slot"):
                role = str(act.get("meal_role") or "").lower()
                meal = lunch if role == "lunch" else dinner
                slot = act.get("time_slot") or meal.get("time_slot")
                meal = dict(meal)
                meal["time_slot"] = slot
                grounded.append(meal)
                continue
            name = str(act.get("poi_name") or "")
            src = by_name.get(name) or {}
            act["photo_url"] = persistable_photo_url(
                str(src.get("photo_url") or act.get("photo_url") or "") or None
            )
            if src:
                act["poi_id"] = str(src["id"]) if src.get("id") else act.get("poi_id")
                act["lat"] = src.get("lat") if src.get("lat") is not None else act.get("lat")
                act["lon"] = src.get("lon") if src.get("lon") is not None else act.get("lon")
            grounded.append(act)
        roles = {
            str(a.get("meal_role") or "").lower()
            for a in grounded
            if a.get("is_food_slot")
        }
        if "lunch" not in roles:
            grounded.append(lunch)
        if "dinner" not in roles:
            grounded.append(dinner)
        draft["activities"] = _retarget_afternoon_after_lunch(grounded)

    def _replace_used_non_meal_activities(
        self,
        activities: list[dict[str, Any]],
        *,
        used_names: set[str],
        poi_pool: list[dict[str, Any]],
        request: ItineraryRequest,
        city_hint: str,
        used_urls: set[str],
    ) -> list[dict[str, Any]]:
        """Drop reused attraction/rest stops and refill from the unused pool."""
        claimed = set(used_names)
        kept: list[dict[str, Any]] = []
        dropped_by_cat: dict[str, int] = {"attraction": 0, "rest": 0}
        for act in activities:
            if act.get("is_food_slot"):
                kept.append(act)
                continue
            name = str(act.get("poi_name") or "")
            pid = str(act.get("poi_id") or "")
            looks_like_junction = _is_junction_named_poi(
                {"name": name, "tags": act.get("tags") or []}
            )
            if name in claimed or (pid and pid in claimed) or looks_like_junction:
                cat = str(act.get("category") or "attraction")
                if cat not in dropped_by_cat:
                    cat = "attraction"
                dropped_by_cat[cat] = dropped_by_cat.get(cat, 0) + 1
                continue
            kept.append(act)
            if name:
                claimed.add(name)
            if pid:
                claimed.add(pid)
        need = dropped_by_cat.get("attraction", 0) + dropped_by_cat.get("rest", 0)
        if need <= 0:
            return kept
        replacements = self._select_pois_for_day(
            poi_pool=poi_pool,
            counts={
                "attraction": dropped_by_cat.get("attraction", 0),
                "food": 0,
                "rest": dropped_by_cat.get("rest", 0),
            },
            used_names=claimed,
            day_number=int(request.days),
            prefer_cheap=False,
            budget=request.daily_budget_usd,
            preferences=list(request.preferences or []),
        )
        extra = self._pois_to_activities(
            replacements,
            locale=request.locale,
            city_hint=city_hint,
            used_urls=used_urls,
        )
        dinners = [
            a for a in kept if str(a.get("meal_role") or "").lower() == "dinner"
        ]
        others = [
            a for a in kept if str(a.get("meal_role") or "").lower() != "dinner"
        ]
        return others + extra + dinners

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
        *,
        warnings: list[str] | None = None,
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
                display_name=str(a["display_name"]) if a.get("display_name") else None,
                is_custom=bool(a.get("is_custom") or False),
            )
            for a in draft.get("activities") or []
        ]
        return DailyItinerary(
            day_number=int(draft["day_number"]),
            theme=str(draft.get("theme") or f"Day {draft['day_number']}"),
            estimated_daily_cost=float(evaluation.get("total_cost_usd", 0)),
            warnings=list(warnings or []),
            activities=activities,
        )


def _is_junction_named_poi(poi: dict[str, Any]) -> bool:
    name = str(poi.get("name") or "")
    tags = " ".join(str(t) for t in (poi.get("tags") or [])).lower()
    if re.search(r"(?i)\b(?:\d+|n|t)[\s-]*way\s+junction\b", name):
        return True
    return "junction" in tags or "highway" in tags


def _unused_poi_pool(
    poi_pool: list[dict[str, Any]], used_names: set[str]
) -> list[dict[str, Any]]:
    unused = [
        p
        for p in poi_pool
        if p.get("name") not in used_names
        and str(p.get("id") or "") not in used_names
    ]
    if not unused:
        unused = list(poi_pool)
    cleaned = [p for p in unused if not _is_junction_named_poi(p)]
    return cleaned or unused


def _drop_last_non_meal(activities: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
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
    if drop_idx is None:
        return None
    return [a for i, a in enumerate(activities) if i != drop_idx]


def _drop_until_under_pace(
    activities: list[dict[str, Any]],
    pace: str,
) -> list[dict[str, Any]]:
    """Drop attractions until both activity-count and duration caps pass, or meals-only."""
    limits = PACE_LIMITS.get((pace or "").strip().lower())
    if not limits:
        return activities
    current = list(activities)
    while True:
        over_count = len(current) > limits["max_activities"]
        over_mins = scheduled_total_minutes(current) > limits["max_duration_minutes"]
        if not over_count and not over_mins:
            break
        dropped = _drop_last_non_meal(current)
        if dropped is None:
            break
        current = dropped
    return current


def _fmt_hhmm(total_minutes: int) -> str:
    total_minutes = max(0, total_minutes) % (24 * 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def _fallback_meal_label(
    city_name: str,
    day_number: int,
    locale: Locale | str | None,
    role: str,
    used: set[str] | None,
) -> str:
    lunch, dinner = i18n.meal_pair(
        city_name, [], day_number, locale, used=used
    )
    return lunch if role == "lunch" else dinner


def _pick_meal_pois(
    poi_pool: list[dict[str, Any]],
    *,
    used_names: set[str],
    day_number: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    slots = [p for p in poi_pool if is_meal_slot_poi(p)]
    unused = [
        p
        for p in slots
        if p.get("name") not in used_names and str(p.get("id") or "") not in used_names
    ]
    candidates = unused or slots
    if not candidates:
        return None, None
    candidates = sorted(candidates, key=lambda p: str(p.get("name") or ""))
    offset = max(0, int(day_number) - 1) % len(candidates)
    lunch = candidates[offset]
    lunch_fam = poi_cuisine_family(lunch)
    dinner = None
    for i in range(len(candidates)):
        cand = candidates[(offset + 1 + i) % len(candidates)]
        if str(cand.get("name") or "") == str(lunch.get("name") or ""):
            continue
        if poi_cuisine_family(cand) != lunch_fam:
            dinner = cand
            break
    if dinner is None:
        for i in range(len(candidates)):
            cand = candidates[(offset + 1 + i) % len(candidates)]
            if str(cand.get("name") or "") != str(lunch.get("name") or ""):
                dinner = cand
                break
    return lunch, dinner


def _meal_activity_from_poi(
    poi: dict[str, Any] | None,
    *,
    role: str,
    city_name: str,
    locale: Locale | str | None,
    fallback_label: str,
) -> dict[str, Any]:
    label = str((poi or {}).get("name") or fallback_label)
    # Meal/food image search disabled — planner shows lunch/dinner icons.
    # Users may set photo_url manually in stop details.
    # photo = persistable_photo_url(str((poi or {}).get("photo_url") or "") or None)
    # if not photo:
    #     photo = persistable_photo_url(cuisine_photo_url(label, role) or None)
    photo = None
    display = _poi_display_name(poi, locale) if poi else label
    return {
        "time_slot": "12:00-13:15" if role == "lunch" else "18:30-20:00",
        "poi_name": label,
        "display_name": display,
        "category": "food",
        "cost_usd": float((poi or {}).get("cost_usd") or (18 if role == "lunch" else 28)),
        "duration_minutes": int((poi or {}).get("duration_minutes") or (75 if role == "lunch" else 90)),
        "description": i18n.meal_description(role, city_name, locale, dish=label),
        "is_food_slot": True,
        "meal_role": role,
        "lat": (poi or {}).get("lat"),
        "lon": (poi or {}).get("lon"),
        "poi_id": str(poi["id"]) if poi and poi.get("id") else None,
        "address": (poi or {}).get("address"),
        "photo_url": photo,
        "is_custom": False,
    }


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
    """Pin lunch at noon, then lay out other stops so no slot overlaps."""
    lunches: list[dict[str, Any]] = []
    dinners: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []
    for act in activities:
        role = str(act.get("meal_role") or "").strip().lower()
        if role == "dinner":
            dinners.append(act)
        elif role == "lunch":
            lunches.append(act)
        elif act.get("is_food_slot"):
            if _slot_start_minutes(act) >= 16 * 60:
                dinners.append(act)
            else:
                lunches.append(act)
        else:
            others.append(act)

    lunch_start = 12 * 60
    placed_lunch: list[dict[str, Any]] = []
    lunch_end = lunch_start
    for lunch in lunches[:1]:
        duration = int(lunch.get("duration_minutes") or 90)
        lunch_end = lunch_start + duration
        updated = dict(lunch)
        updated["time_slot"] = f"{_fmt_hhmm(lunch_start)}-{_fmt_hhmm(lunch_end)}"
        placed_lunch.append(updated)

    morning_src = [a for a in others if _slot_start_minutes(a) < 12 * 60]
    afternoon_src = [a for a in others if _slot_start_minutes(a) >= 12 * 60]

    cursor = 9 * 60
    placed_morning: list[dict[str, Any]] = []
    overflow: list[dict[str, Any]] = []
    for act in morning_src:
        duration = int(act.get("duration_minutes") or 60)
        if placed_lunch and cursor + duration > lunch_start:
            overflow.append(act)
            continue
        end = cursor + duration
        updated = dict(act)
        updated["time_slot"] = f"{_fmt_hhmm(cursor)}-{_fmt_hhmm(end)}"
        placed_morning.append(updated)
        cursor = end + TRAVEL_BUFFER_MINUTES

    after_lunch = (
        lunch_end + TRAVEL_BUFFER_MINUTES if placed_lunch else max(cursor, 13 * 60 + 45)
    )
    acursor = after_lunch
    placed_afternoon: list[dict[str, Any]] = []
    for act in overflow + afternoon_src + lunches[1:]:
        duration = int(act.get("duration_minutes") or 60)
        end = acursor + duration
        updated = dict(act)
        updated["time_slot"] = f"{_fmt_hhmm(acursor)}-{_fmt_hhmm(end)}"
        placed_afternoon.append(updated)
        acursor = end + TRAVEL_BUFFER_MINUTES

    dinner_start = max(18 * 60 + 30, acursor)
    placed_dinners: list[dict[str, Any]] = []
    for act in dinners:
        duration = int(act.get("duration_minutes") or 90)
        end = dinner_start + duration
        updated = dict(act)
        updated["time_slot"] = f"{_fmt_hhmm(dinner_start)}-{_fmt_hhmm(end)}"
        placed_dinners.append(updated)
        dinner_start = end + TRAVEL_BUFFER_MINUTES

    return placed_morning + placed_lunch + placed_afternoon + placed_dinners


def _haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    import math

    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _poi_coords(poi: dict[str, Any]) -> tuple[float, float] | None:
    try:
        lat = poi.get("lat")
        lon = poi.get("lon")
        if lat is None or lon is None:
            return None
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def _neighborhood_token(poi: dict[str, Any]) -> str | None:
    for tag in poi.get("tags") or []:
        text = str(tag)
        if text.lower().startswith("neighborhood:"):
            return text.split(":", 1)[-1].strip().lower() or None
    return None


def _wants_nightlife(preferences: list[str] | None) -> bool:
    prefs = {str(p).strip().lower() for p in (preferences or []) if p}
    return bool(prefs & _NIGHTLIFE_PREF_TOKENS)


def _poi_is_nightlife(poi: dict[str, Any]) -> bool:
    hay = " ".join(
        [
            str(poi.get("name") or ""),
            str(poi.get("description") or ""),
            " ".join(str(t) for t in (poi.get("tags") or [])),
        ]
    ).lower()
    return any(tok in hay for tok in _NIGHTLIFE_POI_TOKENS)


def _draft_nightlife_count(draft: dict[str, Any]) -> int:
    n = 0
    for act in draft.get("activities") or []:
        if act.get("is_food_slot"):
            continue
        faux = {
            "name": act.get("poi_name") or act.get("name"),
            "description": act.get("description"),
            "tags": act.get("tags") or [],
        }
        if _poi_is_nightlife(faux):
            n += 1
    return n


def _unused_nightlife_pois(
    poi_pool: list[dict[str, Any]],
    used_names: set[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in poi_pool:
        if str(p.get("source") or "") == "cuisine_catalog":
            continue
        if p.get("is_food_slot"):
            continue
        name = str(p.get("name") or "")
        if name in used_names or str(p.get("id") or "") in used_names:
            continue
        if _poi_is_nightlife(p):
            out.append(p)
    return out


def _nightlife_day_quota_hints(
    draft: dict[str, Any],
    *,
    preferences: list[str] | None,
    poi_pool: list[dict[str, Any]],
    used_names: set[str],
) -> list[str]:
    """Per-day quota: when nightlife is requested, require >=1 nightlife stop."""
    if not _wants_nightlife(preferences):
        return []
    if _draft_nightlife_count(draft) >= 1:
        return []
    unused = _unused_nightlife_pois(poi_pool, used_names)
    if not unused:
        return []
    samples = ", ".join(str(p.get("name")) for p in unused[:6] if p.get("name"))
    return [
        "nightlife_day_quota: include at least one nightlife stop today"
        + (f" (e.g. {samples})" if samples else "")
    ]


def _ensure_nightlife_in_selected(
    selected: list[dict[str, Any]],
    *,
    poi_pool: list[dict[str, Any]],
    used_names: set[str],
    preferences: list[str] | None,
) -> list[dict[str, Any]]:
    if not _wants_nightlife(preferences):
        return selected
    if any(_poi_is_nightlife(p) for p in selected):
        return selected
    claimed = {str(p.get("name") or "") for p in selected} | set(used_names)
    candidates = [
        p
        for p in _unused_nightlife_pois(poi_pool, used_names)
        if str(p.get("name") or "") not in claimed
    ]
    if not candidates:
        return selected
    pick = candidates[0]
    result = list(selected)
    # Prefer replacing a non-nightlife attraction; else append.
    for i in range(len(result) - 1, -1, -1):
        if not _poi_is_nightlife(result[i]):
            result[i] = pick
            return result
    return [*result, pick]


def _ensure_nightlife_in_activities(
    activities: list[dict[str, Any]],
    *,
    poi_pool: list[dict[str, Any]],
    used_names: set[str],
    preferences: list[str] | None,
) -> list[dict[str, Any]]:
    if not _wants_nightlife(preferences):
        return activities
    draft = {"activities": activities}
    if _draft_nightlife_count(draft) >= 1:
        return activities
    claimed = {
        str(a.get("poi_name") or a.get("name") or "") for a in activities
    } | set(used_names)
    candidates = [
        p
        for p in _unused_nightlife_pois(poi_pool, used_names)
        if str(p.get("name") or "") not in claimed
    ]
    if not candidates:
        return activities
    pick = candidates[0]
    template = next(
        (dict(a) for a in activities if not a.get("is_food_slot")),
        {
            "time_slot": "16:00-17:30",
            "category": "attraction",
            "duration_minutes": 75,
            "cost_usd": float(pick.get("cost_usd") or 0),
            "description": str(pick.get("description") or ""),
            "is_food_slot": False,
            "meal_role": None,
        },
    )
    injected = dict(template)
    injected.update(
        {
            "poi_name": pick.get("name"),
            "category": pick.get("category") or "attraction",
            "cost_usd": pick.get("cost_usd", template.get("cost_usd")),
            "duration_minutes": pick.get(
                "duration_minutes", template.get("duration_minutes")
            ),
            "description": pick.get("description") or template.get("description"),
            "poi_id": pick.get("id"),
            "lat": pick.get("lat"),
            "lon": pick.get("lon"),
            "tags": pick.get("tags") or [],
            "photo_url": pick.get("photo_url"),
            "is_food_slot": False,
            "meal_role": None,
        }
    )
    # Replace last non-meal stop, or insert before dinner.
    for i in range(len(activities) - 1, -1, -1):
        if not activities[i].get("is_food_slot"):
            out = list(activities)
            out[i] = injected
            return _retarget_afternoon_after_lunch(out)
    meals = [a for a in activities if a.get("is_food_slot")]
    non = [a for a in activities if not a.get("is_food_slot")]
    return _retarget_afternoon_after_lunch([*non, injected, *meals])


def _soft_preference_coverage_hints(
    draft: dict[str, Any],
    *,
    uncovered_tags: set[str] | None,
    poi_pool: list[dict[str, Any]],
    used_names: set[str],
    preferences: list[str] | None = None,
) -> list[str]:
    """Soft hints when draft under-covers prefs but matching unused POIs exist."""
    del preferences  # nightlife quota handled separately
    uncovered = {t.lower() for t in (uncovered_tags or set()) if t}
    if not uncovered:
        return []
    remaining = set(uncovered)
    for act in draft.get("activities") or []:
        if act.get("is_food_slot"):
            continue
        faux = {
            "name": act.get("poi_name") or act.get("name"),
            "description": act.get("description"),
            "tags": act.get("tags") or [],
        }
        for tag in list(remaining):
            if _preference_match_score(faux, [tag]) > 0:
                remaining.discard(tag)
    if not remaining:
        return []
    unused = [
        p
        for p in poi_pool
        if not p.get("is_food_slot")
        and str(p.get("source") or "") != "cuisine_catalog"
        and p.get("name") not in used_names
        and str(p.get("id") or "") not in used_names
        and _preference_match_score(p, list(remaining)) > 0
    ]
    if not unused:
        return []
    samples = ", ".join(str(p.get("name")) for p in unused[:6] if p.get("name"))
    return [
        "preference_coverage: still missing "
        + ", ".join(sorted(remaining)[:12])
        + (f"; prefer pool stops like {samples}" if samples else "")
    ]


def _geo_cluster_selected_pois(
    selected: list[dict[str, Any]],
    *,
    poi_pool: list[dict[str, Any]],
    used_names: set[str],
    max_km: float = 8.0,
) -> list[dict[str, Any]]:
    """Prefer same-day stops near an anchor; swap far outliers from the unused pool."""
    if len(selected) < 2:
        return selected
    coords = [(i, _poi_coords(p)) for i, p in enumerate(selected)]
    with_xy = [(i, xy) for i, xy in coords if xy is not None]
    if len(with_xy) < 2:
        return selected
    anchor_i, (alat, alon) = with_xy[0]
    anchor_nbhd = _neighborhood_token(selected[anchor_i])
    claimed = {
        str(p.get("name") or "") for p in selected if p.get("name")
    } | set(used_names)

    result = list(selected)
    for i, poi in enumerate(selected):
        xy = _poi_coords(poi)
        if xy is None:
            continue
        dist = _haversine_km(alat, alon, xy[0], xy[1])
        nbhd = _neighborhood_token(poi)
        same_nbhd = bool(anchor_nbhd and nbhd and nbhd == anchor_nbhd)
        if dist <= max_km or same_nbhd:
            continue
        cat = str(poi.get("category") or "attraction")
        replacements = [
            p
            for p in poi_pool
            if str(p.get("category") or "") == cat
            and str(p.get("name") or "") not in claimed
            and str(p.get("id") or "") not in claimed
            and _poi_coords(p) is not None
        ]
        if not replacements:
            continue

        def _near_key(p: dict[str, Any]) -> tuple:
            pxy = _poi_coords(p)
            assert pxy is not None
            p_nbhd = _neighborhood_token(p)
            nbhd_pen = 0 if (anchor_nbhd and p_nbhd == anchor_nbhd) else 1
            return (nbhd_pen, _haversine_km(alat, alon, pxy[0], pxy[1]))

        replacements.sort(key=_near_key)
        best = replacements[0]
        best_xy = _poi_coords(best)
        if best_xy is None:
            continue
        if _haversine_km(alat, alon, best_xy[0], best_xy[1]) >= dist:
            continue
        claimed.discard(str(poi.get("name") or ""))
        claimed.add(str(best.get("name") or ""))
        result[i] = best
    return result


def _geo_cluster_day_activities(
    activities: list[dict[str, Any]],
    *,
    poi_pool: list[dict[str, Any]],
    used_names: set[str],
) -> list[dict[str, Any]]:
    """Geo-cluster non-meal stops in a drafted day, preserving meal slots."""
    non_meals = [a for a in activities if not a.get("is_food_slot")]
    meals = [a for a in activities if a.get("is_food_slot")]
    if len(non_meals) < 2:
        return activities
    as_pois: list[dict[str, Any]] = []
    for act in non_meals:
        name = str(act.get("poi_name") or act.get("name") or "")
        match = next(
            (p for p in poi_pool if str(p.get("name") or "") == name),
            None,
        )
        row = dict(match or {})
        row["name"] = name or row.get("name")
        row["category"] = act.get("category") or row.get("category") or "attraction"
        row["lat"] = act.get("lat", row.get("lat"))
        row["lon"] = act.get("lon", row.get("lon"))
        row["tags"] = act.get("tags") or row.get("tags") or []
        as_pois.append(row)
    clustered = _geo_cluster_selected_pois(
        as_pois, poi_pool=poi_pool, used_names=used_names
    )
    rebuilt: list[dict[str, Any]] = []
    for i, poi in enumerate(clustered):
        template = dict(non_meals[i])
        name = str(poi.get("name") or "")
        if name and name != str(template.get("poi_name") or ""):
            template["poi_name"] = name
            template["category"] = poi.get("category") or template.get("category")
            template["cost_usd"] = poi.get("cost_usd", template.get("cost_usd"))
            template["duration_minutes"] = poi.get(
                "duration_minutes", template.get("duration_minutes")
            )
            template["description"] = poi.get("description") or template.get(
                "description"
            )
            template["poi_id"] = poi.get("id")
            template["photo_url"] = poi.get("photo_url")
            template["tags"] = poi.get("tags") or []
        template["lat"] = poi.get("lat", template.get("lat"))
        template["lon"] = poi.get("lon", template.get("lon"))
        rebuilt.append(template)
    return _retarget_afternoon_after_lunch([*rebuilt, *meals])


def _preference_match_score(poi: dict[str, Any], preferences: list[str]) -> int:
    if not preferences:
        return 0
    haystack = " ".join(
        [
            str(poi.get("name") or ""),
            str(poi.get("description") or ""),
            " ".join(str(t) for t in (poi.get("tags") or [])),
        ]
    ).lower()
    score = 0
    expanded: list[str] = []
    for pref in preferences:
        token = pref.strip().lower()
        if not token:
            continue
        expanded.append(token)
        expanded.extend(_PREF_ALIASES.get(token, ()))
    for token in expanded:
        if not token:
            continue
        if token in haystack:
            score += 2
        elif token.replace("-", " ") in haystack:
            score += 2
        elif token.replace("-", "") in haystack.replace("-", ""):
            score += 1
    return score


_PREF_ALIASES: dict[str, tuple[str, ...]] = {
    "nature": ("garden", "park", "forest", "bamboo"),
    "kid-friendly": ("family", "kid", "garden", "park", "zoo"),
    "kid friendly": ("family", "kid", "garden", "park", "zoo"),
    "quiet gardens": ("garden", "park", "nature"),
    # Culture is broader than temples: heritage + traditional built environment.
    "culture": (
        "architecture",
        "historic",
        "history",
        "heritage",
        "traditional",
        "castle",
        "monument",
        "palace",
        "museum",
        "garden",
        "market",
        "temple",
        "shrine",
    ),
    "architecture": (
        "historic",
        "heritage",
        "traditional",
        "castle",
        "monument",
        "palace",
        "building",
    ),
    "history": ("historic", "heritage", "castle", "monument", "palace", "museum"),
}


def _coverage_tags(preferences: list[str]) -> set[str]:
    skip = {"popular", "unconventional"}
    return {
        p.strip().lower()
        for p in preferences
        if p and str(p).strip() and p.strip().lower() not in skip
    }


def _activity_matched_tags(act: Activity, preferences: list[str]) -> set[str]:
    hay = " ".join(
        [
            act.poi_name,
            act.display_name or "",
            act.description,
            act.category.value,
        ]
    ).lower()
    matched: set[str] = set()
    for pref in _coverage_tags(preferences):
        if pref in hay or pref.replace("-", " ") in hay:
            matched.add(pref)
    return matched


def _poi_display_name(poi: dict[str, Any], locale: Locale | str | None) -> str:
    name = str(poi.get("name") or "")
    key = locale.value if isinstance(locale, Locale) else str(locale or "en")
    prefixes = {
        "zh-HK": "name_zh-HK:",
        "ja": "name_ja:",
        "en": "name_en:",
    }
    want = prefixes.get(key)
    if want:
        for tag in poi.get("tags") or []:
            text = str(tag)
            if text.startswith(want) and text.split(":", 1)[1].strip():
                return text.split(":", 1)[1].strip()
    tagged_en = str(poi.get("display_name") or "").strip()
    if not tagged_en:
        for tag in poi.get("tags") or []:
            text = str(tag)
            if text.startswith("name_en:") and text.split(":", 1)[1].strip():
                tagged_en = text.split(":", 1)[1].strip()
                break
    if key == "en" and tagged_en:
        return tagged_en
    return name


def _poi_notability_penalty(poi: dict[str, Any]) -> int:
    tags = [str(t).lower() for t in (poi.get("tags") or [])]
    tag_blob = " ".join(tags)
    name = str(poi.get("name") or "").lower()
    hay = f"{name} {tag_blob}"
    if re.search(r"(?i)\b(?:\d+|n|t)[\s-]*way\s+junction\b", name):
        return 4
    if "junction" in hay or "highway" in tag_blob:
        return 4
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
