#!/usr/bin/env python3
"""Reseed Approach A signature cities missing from the already-done set."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIG = ROOT / "data" / "city_signature_pois.json"
DONE = {
    "tokyo",
    "osaka",
    "kyoto",
    "seoul",
    "paris",
    "rome",
    "barcelona",
    "bangkok",
    "london",
    "marrakech",
    "reykjavik",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--skip-places", action="store_true", default=True)
    parser.add_argument("--start-after", default="", help="Skip until after this slug")
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()

    payload = json.loads(SIG.read_text(encoding="utf-8"))
    cities = sorted(k for k in payload.keys() if k not in DONE)
    if args.only:
        want = {s.lower() for s in args.only}
        cities = [c for c in cities if c in want]
    if args.start_after:
        cities = [c for c in cities if c > args.start_after.lower()]

    print(f"Reseeding {len(cities)} cities limit={args.limit}", flush=True)
    failed: list[str] = []
    for i, slug in enumerate(cities, 1):
        print(f"\n==== [{i}/{len(cities)}] SEED {slug} ====", flush=True)
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "seed_city_pois.py"),
            "--city",
            slug,
            "--limit",
            str(args.limit),
        ]
        if args.skip_places:
            cmd.append("--skip-places")
        proc = subprocess.run(cmd, cwd=str(ROOT))
        if proc.returncode != 0:
            print(f"FAILED {slug} exit={proc.returncode}", flush=True)
            # Retry without Overpass so signatures+cuisine still land.
            retry = cmd + ["--no-overpass"]
            print(f"RETRY {slug} --no-overpass", flush=True)
            proc2 = subprocess.run(retry, cwd=str(ROOT))
            if proc2.returncode != 0:
                failed.append(slug)
    print(f"\nDone. failed={failed}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
