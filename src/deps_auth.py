"""Auth dependencies — Supabase JWT Bearer validation (Phase 5.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from supabase import Client

from src.deps import SupabaseDep


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str | None = None


def _parse_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header; expected Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


def get_current_user(
    supabase: SupabaseDep,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthUser:
    """
    Validate Supabase access token via Auth API.

    Requires ``Authorization: Bearer <access_token>`` from the Next.js
    Supabase client session.
    """
    token = _parse_bearer(authorization)
    try:
        result = supabase.auth.get_user(token)
        user = getattr(result, "user", None)
        if user is None and isinstance(result, dict):
            user = result.get("user")
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
        email = getattr(user, "email", None)
        if email is None and isinstance(user, dict):
            email = user.get("email")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing user id",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return AuthUser(id=str(user_id), email=str(email) if email else None)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Auth validation failed: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentUserDep = Annotated[AuthUser, Depends(get_current_user)]
