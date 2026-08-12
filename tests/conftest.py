"""Pytest defaults for offline-friendly unit tests."""

from __future__ import annotations

import os

# Prefer mock POI dataset unless a test explicitly opts into live search.
os.environ.setdefault("USE_MOCK_POIS", "true")
# Isolate SlowAPI counters in-process for rate-limit tests.
os.environ.setdefault("REDIS_URL", "")
# Keep main TestClient suites well under the production search cap.
os.environ.setdefault("SEARCH_RATE_LIMIT", "1000/minute")
