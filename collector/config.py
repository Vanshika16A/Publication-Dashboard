"""Paths and settings shared by every collector module."""

from __future__ import annotations

import tomllib
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parent
CONFIG = tomllib.loads((PACKAGE_DIR / "config.toml").read_text(encoding="utf-8"))

GROUP = CONFIG["group"]["number"]
START_YEAR = CONFIG["collection"]["start_year"]
END_YEAR = CONFIG["collection"]["end_year"]

# institution name -> settings (openalex_id, ror, own, confusable)
INSTITUTIONS: dict[str, dict[str, str]] = CONFIG["institutions"]
TARGET_NAMES = {settings["openalex_id"]: name for name, settings in INSTITUTIONS.items()}
TARGET_IDS = set(TARGET_NAMES)

# Everything the collector downloads or produces lives under collector/data (gitignored).
DATA_DIR = PACKAGE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"        # cached API responses (resumable)
OUTPUT_DIR = DATA_DIR / "output"  # CSV deliverables, networks, reports


def resolve(path: str) -> Path:
    """Config paths are relative to the repository root."""
    return ROOT / path
