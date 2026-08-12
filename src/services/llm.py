"""
Dual-model Gemini orchestration via Vertex AI (Phase 5.2).

- Gemini 1.5 Flash — fast POI extraction / ranking / routing
- Gemini 1.5 Pro — multi-day itinerary drafting & constraint solving

Implements ``ItineraryLLMClient.propose_daily_plan`` for ``AgentService``.
"""

from __future__ import annotations

import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.schemas.itinerary import ItineraryRequest
from src.utils.logger import get_logger

logger = get_logger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_LOCATION = "us-central1"
# Generative models are often unavailable in asia-* embedding regions.
FLASH_MODEL = os.getenv("GEMINI_FLASH_MODEL", "gemini-1.5-flash").strip() or "gemini-1.5-flash"
PRO_MODEL = os.getenv("GEMINI_PRO_MODEL", "gemini-1.5-pro").strip() or "gemini-1.5-pro"


class LlmServiceError(Exception):
    """Vertex Gemini call failed."""


def _load_env() -> None:
    load_dotenv(ROOT_DIR / ".env")


def _resolve_credentials() -> tuple[str, str]:
    from src.services.gcp_credentials import configure_google_credentials, load_project_env

    load_project_env()
    project_id = os.getenv("GCP_PROJECT_ID", "").strip()
    # Prefer GEMINI_LOCATION so embeddings can stay in asia-southeast1 while
    # Gemini runs in a supported region (typically us-central1).
    location = (
        os.getenv("GEMINI_LOCATION", "").strip()
        or os.getenv("GCP_LOCATION", "").strip()
        or DEFAULT_LOCATION
    )
    if not project_id:
        raise LlmServiceError("GCP_PROJECT_ID is not set")
    try:
        configure_google_credentials()
    except FileNotFoundError as exc:
        raise LlmServiceError(str(exc)) from exc
    return project_id, location


@lru_cache
def _init_vertex() -> tuple[str, str]:
    project_id, location = _resolve_credentials()
    try:
        import vertexai
    except ImportError as exc:
        raise LlmServiceError(
            "Missing google-cloud-aiplatform. pip install -r requirements.txt"
        ) from exc
    vertexai.init(project=project_id, location=location)
    return project_id, location


def _generate(model_name: str, prompt: str, *, temperature: float = 0.2) -> str:
    """
    Call Vertex Gemini with lightweight retries for transient errors.

    Retries on rate limits / 429 / 503 / UNAVAILABLE before raising
    ``LlmServiceError`` (agent then falls back to heuristics).
    """
    _init_vertex()
    try:
        from vertexai.generative_models import GenerativeModel
    except ImportError as exc:
        raise LlmServiceError("vertexai.generative_models unavailable") from exc

    attempts = max(1, int(os.getenv("GEMINI_RETRY_ATTEMPTS", "3")))
    base_delay = float(os.getenv("GEMINI_RETRY_BASE_DELAY_SEC", "0.6"))
    last_exc: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            model = GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": 2048,
                },
            )
            text = getattr(response, "text", None) or ""
            if not text and getattr(response, "candidates", None):
                parts = response.candidates[0].content.parts
                text = "".join(getattr(p, "text", "") or "" for p in parts)
            return (text or "").strip()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= attempts or not _is_transient_llm_error(exc):
                raise LlmServiceError(f"{model_name} failed: {exc}") from exc
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "Transient Gemini error (attempt %s/%s), retry in %.1fs: %s",
                attempt,
                attempts,
                delay,
                exc,
            )
            time.sleep(delay)

    raise LlmServiceError(f"{model_name} failed: {last_exc}")


def _is_transient_llm_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    tokens = (
        "429",
        "503",
        "500",
        "rate limit",
        "resource exhausted",
        "unavailable",
        "deadline",
        "timeout",
        "temporarily",
        "quota",
        "try again",
    )
    return any(token in message for token in tokens)


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


class LlmService:
    """Flash (routing/rank) + Pro (itinerary) dual-model client."""

    flash_model: str = FLASH_MODEL
    pro_model: str = PRO_MODEL

    def generate_flash(self, prompt: str) -> str:
        return _generate(self.flash_model, prompt, temperature=0.1)

    def generate_pro(self, prompt: str) -> str:
        return _generate(self.pro_model, prompt, temperature=0.3)

    def rank_pois(
        self,
        *,
        preferences: list[str],
        pois: list[dict[str, Any]],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Fast Flash pass: reorder POIs; falls back to input order on failure."""
        if not pois:
            return []
        names = [p.get("name") for p in pois]
        prompt = (
            "You rank travel POIs. Return JSON only: "
            '{"ranked_names": ["..."]} using only names from the list.\n'
            f"Preferences: {preferences}\n"
            f"POIs: {json.dumps(names)}\n"
            f"Return at most {limit} names."
        )
        try:
            raw = self.generate_flash(prompt)
            data = _extract_json_object(raw)
            ranked = data.get("ranked_names") or []
            by_name = {p["name"]: p for p in pois if p.get("name")}
            ordered = [by_name[n] for n in ranked if n in by_name]
            for p in pois:
                if p not in ordered:
                    ordered.append(p)
            return ordered[:limit]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Flash POI rank failed; using original order: %s", exc)
            return pois[:limit]

    def propose_daily_plan(
        self,
        *,
        request: ItineraryRequest,
        day_number: int,
        poi_pool: list[dict[str, Any]],
        previous_violations: list[str],
        turn: int,
    ) -> dict[str, Any]:
        """Pro model drafts one day; must ground activities in ``poi_pool`` names."""
        pool_brief = [
            {
                "name": p.get("name"),
                "category": p.get("category"),
                "cost_usd": p.get("cost_usd"),
                "duration_minutes": p.get("duration_minutes"),
                "description": p.get("description"),
                "tags": p.get("tags") or [],
            }
            for p in poi_pool
        ]
        prompt = f"""
You are a travel itinerary agent. Draft day {day_number} of {request.days}.
Pace: {request.pace.value if hasattr(request.pace, 'value') else request.pace}
Daily budget USD: {request.daily_budget_usd}
Preferences: {list(request.preferences or [])}
Locale: {request.locale}
Previous violations (fix these): {previous_violations}
Retry turn: {turn}

Ground EVERY activity in this POI pool (use exact names):
{json.dumps(pool_brief, ensure_ascii=False)}

Return JSON only:
{{
  "day_number": {day_number},
  "theme": "short theme",
  "activities": [
    {{
      "time_slot": "09:00-11:00",
      "poi_name": "exact name from pool",
      "category": "attraction|food|rest",
      "cost_usd": 0,
      "duration_minutes": 60,
      "description": "short"
    }}
  ]
}}
Rules: stay under daily budget; include mix of categories when possible;
do not invent POIs; cost/duration must match the pool when possible.
""".strip()
        try:
            raw = self.generate_pro(prompt)
            data = _extract_json_object(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Pro itinerary draft failed; re-raising for agent fallback: %s", exc)
            raise LlmServiceError(str(exc)) from exc
        if "day_number" not in data:
            data["day_number"] = day_number
        if "activities" not in data:
            data["activities"] = []
        if "theme" not in data:
            data["theme"] = f"Day {day_number}"
        # Ground costs from pool when names match
        by_name = {p["name"]: p for p in poi_pool}
        grounded: list[dict[str, Any]] = []
        for act in data.get("activities") or []:
            name = act.get("poi_name") or act.get("name")
            if name not in by_name:
                continue
            src = by_name[name]
            grounded.append(
                {
                    "time_slot": act.get("time_slot") or "10:00-12:00",
                    "poi_name": name,
                    "category": src.get("category") or act.get("category") or "attraction",
                    "cost_usd": float(src.get("cost_usd") or act.get("cost_usd") or 0),
                    "duration_minutes": int(
                        src.get("duration_minutes") or act.get("duration_minutes") or 60
                    ),
                    "description": act.get("description")
                    or src.get("description")
                    or name,
                }
            )
        data["activities"] = grounded
        return data


@lru_cache
def get_llm_service() -> LlmService:
    """Lazy singleton; raises ``LlmServiceError`` if Vertex cannot init."""
    _init_vertex()
    return LlmService()


def try_get_llm_service() -> LlmService | None:
    try:
        return get_llm_service()
    except Exception as exc:  # noqa: BLE001
        logger.info("LLM service unavailable; heuristic planner will be used: %s", exc)
        return None
