"""URL / coordinate helpers shared by Custom Spot (backend parity tests)."""

from __future__ import annotations

import re


def parse_google_maps_url(text: str) -> tuple[float, float] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    patterns = (
        r"@(-?\d+\.?\d*),(-?\d+\.?\d*)",
        r"!3d(-?\d+\.?\d*)!4d(-?\d+\.?\d*)",
        r"[?&](?:ll|center)=(-?\d+\.?\d*),(-?\d+\.?\d*)",
        r"[?&]q=(-?\d+\.?\d*),(-?\d+\.?\d*)",
        r"[?&]destination=(-?\d+\.?\d*),(-?\d+\.?\d*)",
    )
    for pattern in patterns:
        m = re.search(pattern, raw, flags=re.IGNORECASE)
        if m:
            return float(m.group(1)), float(m.group(2))
    return None
