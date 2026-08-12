"""
GCP / Vertex credential helpers.

Local: optional ``GOOGLE_APPLICATION_CREDENTIALS`` pointing at a JSON key.
Cloud Run / GCE: leave unset and use Application Default Credentials from the
runtime service account (``K_SERVICE`` is set on Cloud Run).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def load_project_env() -> None:
    load_dotenv(ROOT_DIR / ".env")


def running_on_gcp() -> bool:
    """True on Cloud Run, Cloud Functions, GCE, etc."""
    if os.getenv("K_SERVICE", "").strip():
        return True
    if os.getenv("GCE_METADATA_HOST", "").strip():
        return True
    # Common Cloud Run / Functions markers
    if os.getenv("CLOUD_RUN_JOB", "").strip() or os.getenv("FUNCTION_TARGET", "").strip():
        return True
    return False


def configure_google_credentials() -> Path | None:
    """
    Prepare Google ADC for Vertex / GCP clients.

    Returns the resolved credentials file path when a key file is used,
    or ``None`` when relying on ambient ADC (Cloud Run service account).
    """
    load_project_env()
    raw = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not raw:
        if running_on_gcp():
            return None
        # Local without a key file: still allow ADC (gcloud auth application-default login)
        return None

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (ROOT_DIR / path).resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"GOOGLE_APPLICATION_CREDENTIALS file not found: {path}"
        )
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(path)
    return path
