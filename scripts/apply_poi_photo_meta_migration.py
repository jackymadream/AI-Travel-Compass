#!/usr/bin/env python3
"""
Apply scripts/migrate_poi_photo_meta.sql when a direct DB URL is available.

Requires one of:
  DATABASE_URL
  SUPABASE_DB_URL
  POSTGRES_URL

Get the URI from: Supabase Dashboard → Project Settings → Database → Connection string (URI).
Use the session-mode / direct connection (port 5432), not the pooler, for DDL.

If no DB URL is set, paste the SQL file into Supabase → SQL → New query, then run
enrich/seed scripts.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SQL_FILE = ROOT / "scripts" / "migrate_poi_photo_meta.sql"


def main() -> int:
    load_dotenv(ROOT / ".env")
    db_url = (
        os.getenv("DATABASE_URL", "").strip()
        or os.getenv("SUPABASE_DB_URL", "").strip()
        or os.getenv("POSTGRES_URL", "").strip()
    )
    if not SQL_FILE.exists():
        print(f"Missing {SQL_FILE}", file=sys.stderr)
        return 1

    sql = SQL_FILE.read_text(encoding="utf-8")
    if not db_url:
        print(
            "No DATABASE_URL / SUPABASE_DB_URL / POSTGRES_URL in .env.\n"
            "Service-role REST cannot run ALTER TABLE.\n\n"
            "Option A — SQL Editor:\n"
            "  1. Open Supabase → SQL → New query\n"
            f"  2. Paste contents of {SQL_FILE.relative_to(ROOT)}\n"
            "  3. Run, then: python scripts/enrich_poi_photos.py --city kyoto --force\n\n"
            "Option B — add DATABASE_URL to .env (Settings → Database → URI),\n"
            "  then re-run: python scripts/apply_poi_photo_meta_migration.py\n",
            file=sys.stderr,
        )
        return 2

    try:
        import psycopg
    except ImportError:
        print("Installing psycopg…")
        import subprocess

        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "psycopg[binary]"],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        import psycopg  # type: ignore

    print(f"Applying {SQL_FILE.relative_to(ROOT)} …")
    with psycopg.connect(db_url) as conn:
        conn.execute(sql)
        conn.commit()
        row = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'pois'
              AND column_name IN (
                'photo_url',
                'photo_source',
                'photo_confidence',
                'photo_checked_at',
                'google_place_name',
                'google_photo_name'
              )
            ORDER BY column_name
            """
        ).fetchall()
    cols = [str(r[0]) for r in row]
    print("Migration applied.")
    print("pois columns present:", ", ".join(cols) if cols else "(none — check pois table exists)")
    expected = {
        "photo_url",
        "photo_source",
        "photo_confidence",
        "photo_checked_at",
        "google_place_name",
        "google_photo_name",
    }
    missing = expected - set(cols)
    if missing:
        print("Warning: missing columns:", ", ".join(sorted(missing)), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
