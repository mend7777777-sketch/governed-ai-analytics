"""Application logging configuration without secrets or result payloads."""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import PROJECT_ROOT


def configure_logging() -> None:
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
        ],
    )
