#!/usr/bin/env python3
"""Apply scripts/migrate_pois_rls.sql when a direct DB URL is available."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SQL_FILE = ROOT / "scripts" / "migrate_pois_rls.sql"


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
            "Open Supabase → SQL → New query and paste "
            f"{SQL_FILE.relative_to(ROOT)}",
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
            SELECT c.relrowsecurity,
                   EXISTS (
                     SELECT 1 FROM pg_policies p
                     WHERE p.schemaname = 'public'
                       AND p.tablename = 'pois'
                       AND p.policyname = 'pois_select_active'
                   )
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = 'pois'
            """
        ).fetchone()
    print(
        "Done. RLS enabled =",
        bool(row[0]) if row else False,
        "; pois_select_active =",
        bool(row[1]) if row else False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
