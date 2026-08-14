"""Centralized environment configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing {name}. Set it in .env.")
    return value


def chroma_path() -> Path:
    # Runtime state belongs under storage; production deployments can mount this path.
    return Path(os.getenv("CHROMA_PATH", PROJECT_ROOT / "storage" / "chroma_ai_analytics"))
