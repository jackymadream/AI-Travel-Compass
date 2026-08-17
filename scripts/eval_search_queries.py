#!/usr/bin/env python3
"""
Golden-query smoke checklist against a running local API.

Usage::

    python scripts/eval_search_queries.py
    python scripts/eval_search_queries.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

EXPECTATIONS: list[tuple[str, set[str]]] = [
    ("anime", {"JP"}),
    ("onsen hot springs", {"JP"}),
    ("northern lights", {"IS", "NO", "FI"}),
    ("tapas paella", {"ES"}),
    ("desert riad", {"MA"}),
]


def search(base: str, query: str, limit: int = 12) -> dict:
    payload = json.dumps(
        {
            "query": query,
            "locale": "en",
            "max_budget": 500,
            "min_safety": 1,
            "limit": limit,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/v1/search",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    failures = 0
    for query, expect_isos in EXPECTATIONS:
        try:
            data = search(args.base_url, query)
        except urllib.error.URLError as exc:
            print(f"FAIL  {query!r}: API unreachable ({exc})")
            return 1

        results = data.get("results") or []
        isos = [r.get("iso_code") for r in results]
        # Country-collapse view: first distinct iso_codes in rank order
        ordered: list[str] = []
        for iso in isos:
            if iso and iso not in ordered:
                ordered.append(iso)
        top = set(ordered[:3])
        intent = data.get("intent") or {}
        interests = intent.get("interests") or []
        scores = [float(r.get("score") or 0) for r in results[:3]]
        ok = bool(top & expect_isos)
        status = "OK  " if ok else "FAIL"
        print(
            f"{status} query={query!r} top_isos={ordered[:5]} "
            f"interests={interests} scores={[round(s, 3) for s in scores]}"
        )
        if not ok:
            failures += 1
            print(f"       expected one of {sorted(expect_isos)} in top 3 countries")

    if failures:
        print(f"\n{failures}/{len(EXPECTATIONS)} golden queries failed.")
        return 1
    print(f"\nAll {len(EXPECTATIONS)} golden queries passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
