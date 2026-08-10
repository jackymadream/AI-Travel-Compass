"""Shared FastAPI dependencies."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends
from supabase import Client, create_client

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


@lru_cache
def _supabase_client() -> Client:
    load_dotenv(ROOT_DIR / ".env")
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env"
        )
    return create_client(url, key)


def get_supabase() -> Client:
    return _supabase_client()


SupabaseDep = Annotated[Client, Depends(get_supabase)]
