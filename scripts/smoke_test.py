#!/usr/bin/env python3
"""
E2E smoke test against a live Travel Compass API.

Pipeline: Health (liveness + readiness) → Search → Itinerary generation.

Usage:
  python scripts/smoke_test.py
  python scripts/smoke_test.py --base-url http://127.0.0.1:8000
  SMOKE_BASE_URL=https://api.example.com python scripts/smoke_test.py

Exit codes: 0 = all steps passed, 1 = failure.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover
    print("httpx is required. Run: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

# Phase 3 mock city with POI coverage (see src/services/agent_tools.py).
MOCK_CITY_TOKYO = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class SmokeFailure(Exception):
    """Raised when a smoke step fails."""


def _print_ok(step: str, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"[PASS] {step}{suffix}")


def _print_fail(step: str, detail: str) -> None:
    print(f"[FAIL] {step} — {detail}", file=sys.stderr)


def check_liveness(client: httpx.Client) -> None:
    response = client.get("/health/liveness")
    if response.status_code != 200:
        raise SmokeFailure(f"HTTP {response.status_code}: {response.text[:200]}")
    body = response.json()
    if body.get("status") != "alive":
        raise SmokeFailure(f"unexpected body: {body}")
    _print_ok("GET /health/liveness", f"trace={response.headers.get('x-request-id', '-')}")


def check_readiness(client: httpx.Client, *, allow_degraded: bool) -> None:
    response = client.get("/health")
    if response.status_code != 200:
        raise SmokeFailure(f"HTTP {response.status_code}: {response.text[:200]}")
    body = response.json()
    status = body.get("status")
    checks = body.get("checks") or {}
    summary = ", ".join(
        f"{name}={meta.get('status')}" for name, meta in checks.items()
    )
    if status == "ok":
        _print_ok("GET /health", summary or "ok")
        return
    if status == "degraded" and allow_degraded:
        _print_ok("GET /health", f"degraded allowed ({summary})")
        return
    raise SmokeFailure(f"status={status!r}; checks={checks}")


def check_search(client: httpx.Client) -> dict[str, Any]:
    payload = {
        "query": "cozy food city by the sea",
        "locale": "en",
        "max_budget": 200,
        "min_safety": 3,
        "tags": ["food"],
        "limit": 5,
    }
    started = time.perf_counter()
    response = client.post("/api/v1/search", json=payload)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    if response.status_code != 200:
        raise SmokeFailure(f"HTTP {response.status_code}: {response.text[:400]}")
    body = response.json()
    if "results" not in body:
        raise SmokeFailure(f"missing results key: {body}")
    count = len(body.get("results") or [])
    # Empty results can happen if seed/filters are strict; still treat as API OK.
    _print_ok(
        "POST /api/v1/search",
        f"{count} hit(s), candidate_count={body.get('candidate_count')}, {elapsed_ms}ms",
    )
    return body


def check_itinerary(client: httpx.Client, city_id: str) -> dict[str, Any]:
    payload = {
        "city_id": city_id,
        "days": 2,
        "pace": "moderate",
        "daily_budget_usd": 100,
        "preferences": ["food", "culture"],
        "locale": "en",
    }
    started = time.perf_counter()
    response = client.post("/api/v1/itineraries/generate", json=payload)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    if response.status_code != 200:
        raise SmokeFailure(f"HTTP {response.status_code}: {response.text[:400]}")
    body = response.json()
    plans = body.get("daily_plans") or []
    if len(plans) != 2:
        raise SmokeFailure(f"expected 2 daily_plans, got {len(plans)}")
    if not body.get("city_name") or not body.get("agent_reasoning"):
        raise SmokeFailure("missing city_name or agent_reasoning")
    _print_ok(
        "POST /api/v1/itineraries/generate",
        f"{body.get('city_name')} · total=${body.get('total_cost_usd')} · {elapsed_ms}ms",
    )
    return body


def resolve_itinerary_city_id(search_body: dict[str, Any]) -> str:
    """Prefer a search hit city_id when present; fall back to mock Tokyo POIs."""
    for hit in search_body.get("results") or []:
        city_id = hit.get("city_id")
        if city_id:
            # Planner POIs are only seeded for mock Tokyo/Seoul today.
            if str(city_id) in {
                MOCK_CITY_TOKYO,
                "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            }:
                return str(city_id)
    return MOCK_CITY_TOKYO


def run_smoke(
    base_url: str,
    *,
    timeout: float,
    allow_degraded: bool,
) -> int:
    print(f"Smoke testing {base_url} …")
    try:
        with httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout) as client:
            check_liveness(client)
            check_readiness(client, allow_degraded=allow_degraded)
            search_body = check_search(client)
            city_id = resolve_itinerary_city_id(search_body)
            check_itinerary(client, city_id)
    except (SmokeFailure, httpx.HTTPError) as exc:
        _print_fail("smoke_test", str(exc))
        return 1

    print("All smoke steps passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Travel Compass API E2E smoke test")
    parser.add_argument(
        "--base-url",
        default=os.getenv("SMOKE_BASE_URL", DEFAULT_BASE_URL),
        help=f"API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("SMOKE_TIMEOUT_SEC", "60")),
        help="HTTP timeout seconds (search may call Vertex)",
    )
    parser.add_argument(
        "--allow-degraded",
        action="store_true",
        default=os.getenv("SMOKE_ALLOW_DEGRADED", "").lower() in {"1", "true", "yes"},
        help="Accept GET /health status=degraded (e.g. Redis optional)",
    )
    args = parser.parse_args(argv)
    return run_smoke(
        args.base_url,
        timeout=args.timeout,
        allow_degraded=args.allow_degraded,
    )


if __name__ == "__main__":
    raise SystemExit(main())
