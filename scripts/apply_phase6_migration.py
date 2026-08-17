#!/usr/bin/env python3
"""
Apply Phase 6.1 DDL to Postgres when a direct DB URL is available.

Requires one of:
  DATABASE_URL
  SUPABASE_DB_URL
  POSTGRES_URL

Get the URI from: Supabase Dashboard → Project Settings → Database → Connection string (URI).
Use the session-mode / direct connection (port 5432), not the pooler, for DDL.

If no DB URL is set, prints the SQL path and exits non-zero so you can paste it
into the Supabase SQL Editor, then re-run seed_countries.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SQL_FILE = ROOT / "scripts" / "migrate_phase6_countries.sql"


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
            "  3. Run, then: python scripts/seed_countries.py\n\n"
            "Option B — add DATABASE_URL to .env (Settings → Database → URI),\n"
            "  then re-run: python scripts/apply_phase6_migration.py\n",
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
    print("Migration applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
