"""Health endpoints for container probes and dependency readiness."""

from __future__ import annotations

from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends

from src.services.health_service import build_health_report

router = APIRouter(tags=["health"])

HealthReportFn = Callable[[], dict[str, Any]]


def get_health_report() -> dict[str, Any]:
    """FastAPI dependency — overridable in tests."""
    return build_health_report()


HealthReportDep = Annotated[dict[str, Any], Depends(get_health_report)]


@router.get("/health")
def health(report: HealthReportDep) -> dict[str, Any]:
    """
    Readiness-style check: Redis, vector DB (Qdrant), and database (Supabase).

    Returns ``status: ok`` when all dependencies are healthy, otherwise
    ``status: degraded`` with per-check details.
    """
    return report


@router.get("/health/liveness")
def liveness() -> dict[str, str]:
    """Simple liveness probe for container orchestrators."""
    return {"status": "alive"}
