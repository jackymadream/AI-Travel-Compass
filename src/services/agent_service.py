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

from typing import Any, Callable, Protocol

from src.schemas.itinerary import (
    Activity,
    ActivityCategory,
    DailyItinerary,
    ItineraryRequest,
    ItineraryResponse,
    TripPace,
)
from src.services.agent_tools import (
    MOCK_CITY_SEOUL,
    MOCK_CITY_TOKYO,
    evaluate_schedule_and_budget_tool,
    search_pois_tool,
)
from src.utils.logger import elapsed_timer, get_logger, log_event

logger = get_logger(__name__)

DEFAULT_MAX_TURNS = 3

CITY_DISPLAY_NAMES: dict[str, str] = {
    MOCK_CITY_TOKYO: "Tokyo",
    MOCK_CITY_SEOUL: "Seoul",
}


def _resolve_city_name(city_id: str) -> str:
    """Prefer Supabase city name; fall back to mock display map."""
    if city_id in CITY_DISPLAY_NAMES:
        return CITY_DISPLAY_NAMES[city_id]
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
                return str(name.get("en") or name.get("ja") or rows[0].get("slug") or "City")
            return str(name)
    except Exception:  # noqa: BLE001
        pass
    return "Unknown city"


# How many POIs of each category to request when drafting a day.
_PACE_DRAFT_COUNTS: dict[str, dict[str, int]] = {
    TripPace.RELAXED.value: {"attraction": 1, "food": 1, "rest": 1},
    TripPace.MODERATE.value: {"attraction": 2, "food": 1, "rest": 1},
    TripPace.PACKED.value: {"attraction": 3, "food": 2, "rest": 1},
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
        city_name = _resolve_city_name(city_id)
        log_event(
            logger,
            "agent_plan_started",
            city_id=city_id,
            days=request.days,
            pace=request.pace.value,
            daily_budget_usd=request.daily_budget_usd,
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

                for day_number in range(1, request.days + 1):
                    day, day_reasoning = self._plan_one_day_with_retries(
                        request=request,
                        day_number=day_number,
                        poi_pool=poi_pool,
                        used_names=used_names,
                    )
                    daily_plans.append(day)
                    reasoning_parts.append(day_reasoning)
                    for act in day.activities:
                        used_names.add(act.poi_name)

                total_cost = sum(d.estimated_daily_cost for d in daily_plans)
                agent_reasoning = " ".join(reasoning_parts).strip() or (
                    f"Built a {request.days}-day {request.pace.value} plan for {city_name} "
                    f"within ${request.daily_budget_usd:.0f}/day."
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
        pool: list[dict[str, Any]] = []
        seen: set[str] = set()
        for category in ("attraction", "food", "rest"):
            hits = self._search_pois(
                city_id=city_id,
                category=category,
                preferences=preferences,
                limit=10,
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
    ) -> tuple[DailyItinerary, str]:
        previous_violations: list[str] = []
        last_eval: dict[str, Any] | None = None
        draft = self._propose_daily_plan(
            request=request,
            day_number=day_number,
            poi_pool=poi_pool,
            used_names=used_names,
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
                reasoning = (
                    f"Day {day_number}: validated on turn {turn}/{self.max_turns} "
                    f"(${daily.estimated_daily_cost:.0f}, "
                    f"{last_eval.get('total_duration_minutes')} min incl. travel)."
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
        previous_violations: list[str],
        turn: int,
    ) -> dict[str, Any]:
        if self._llm is not None:
            try:
                return self._llm.propose_daily_plan(
                    request=request,
                    day_number=day_number,
                    poi_pool=poi_pool,
                    previous_violations=previous_violations,
                    turn=turn,
                )
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
        previous_violations: list[str],
        turn: int,
    ) -> dict[str, Any]:
        counts = dict(_PACE_DRAFT_COUNTS[request.pace.value])
        # Later turns: prefer fewer / cheaper stops.
        if turn > 1 or previous_violations:
            for key in counts:
                counts[key] = max(1 if key != "attraction" else 0, counts[key] - (turn - 1))
            if request.pace == TripPace.RELAXED:
                counts = {"attraction": 1, "food": 1, "rest": 1}
            elif turn >= 2:
                counts = {"attraction": 1, "food": 1, "rest": 1}

        selected = self._select_pois_for_day(
            poi_pool=poi_pool,
            counts=counts,
            used_names=used_names,
            day_number=day_number,
            prefer_cheap=bool(previous_violations) or turn > 1,
            budget=request.daily_budget_usd,
        )
        # Always keep at least one activity if pool non-empty.
        if not selected and poi_pool:
            cheapest = sorted(poi_pool, key=lambda p: float(p["cost_usd"]))[0]
            selected = [cheapest]

        activities = self._pois_to_activities(selected)
        theme = self._day_theme(day_number, request.preferences, selected)
        return {
            "day_number": day_number,
            "theme": theme,
            "activities": activities,
        }

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
            unused_boost = 0 if p["name"] in used_names else -1
            cost = float(p["cost_usd"])
            # Rotate pool by day so multi-day plans diversify.
            rotate = hash(p["name"]) % 7
            return (unused_boost, cost if prefer_cheap else rotate, cost)

        selected: list[dict[str, Any]] = []
        running_cost = 0.0
        for category, want in counts.items():
            candidates = sorted(by_cat.get(category, []), key=sort_key)
            # Offset by day for diversity when not forcing cheap.
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
        if "budget" in text:
            # Drop the most expensive non-rest activity first.
            expensive = max(
                activities,
                key=lambda a: (
                    float(a.get("cost_usd") or 0),
                    0 if a.get("category") == "rest" else 1,
                ),
            )
            activities = [a for a in activities if a is not expensive]
        if "packed" in text or "pace" in text:
            # Drop last attraction if present, else last activity.
            drop_idx = None
            for i in range(len(activities) - 1, -1, -1):
                if activities[i].get("category") == "attraction":
                    drop_idx = i
                    break
            if drop_idx is None and activities:
                drop_idx = len(activities) - 1
            if drop_idx is not None:
                activities = [a for i, a in enumerate(activities) if i != drop_idx]

        refined = dict(draft)
        refined["activities"] = activities
        return refined

    def _pois_to_activities(self, pois: list[dict[str, Any]]) -> list[dict[str, Any]]:
        activities: list[dict[str, Any]] = []
        cursor_minutes = 9 * 60  # 09:00
        for poi in pois:
            duration = int(poi["duration_minutes"])
            start = cursor_minutes
            end = start + duration
            activities.append(
                {
                    "time_slot": f"{_fmt_hhmm(start)}-{_fmt_hhmm(end)}",
                    "poi_name": poi["name"],
                    "category": poi["category"],
                    "cost_usd": float(poi["cost_usd"]),
                    "duration_minutes": duration,
                    "description": poi["description"],
                }
            )
            cursor_minutes = end + 30  # travel buffer between slots
        return activities

    def _day_theme(
        self,
        day_number: int,
        preferences: list[str],
        selected: list[dict[str, Any]],
    ) -> str:
        pref = preferences[0] if preferences else None
        cats = {p["category"] for p in selected}
        if pref:
            return f"Day {day_number}: {pref.title()} focus"
        if "museum" in " ".join(t for p in selected for t in p.get("tags") or []).lower():
            return f"Day {day_number}: Museums & culture"
        if cats == {"food"} or (len(cats) == 2 and "food" in cats and "rest" in cats):
            return f"Day {day_number}: Food crawl"
        return f"Day {day_number}: City highlights"

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
