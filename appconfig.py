"""Config and secret loading.

Single place that reads ``config/*.yaml`` and the environment, so no
module has to know where the project root is or hard-code a threshold.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from ingest.models import ConfigError

# Anchored on this file, but overridable so the whole pipeline can be run
# against a throwaway root in tests without touching the real data/ tree.
PROJECT_ROOT_ENV = "SOURCING_PROJECT_ROOT"
PROJECT_ROOT = Path(os.environ.get(PROJECT_ROOT_ENV) or Path(__file__).resolve().parent)
CONFIG_DIR = PROJECT_ROOT / "config"

API_KEY_ENV = "DATA_GOV_API_KEY"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"missing config file: {path}")
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ConfigError(f"config file is not a mapping: {path}")
    return data


@lru_cache(maxsize=1)
def load_settings() -> dict[str, Any]:
    return _load_yaml(CONFIG_DIR / "settings.yaml")


@lru_cache(maxsize=1)
def load_assumptions() -> dict[str, Any]:
    return _load_yaml(CONFIG_DIR / "assumptions.yaml")


def get_api_key() -> str:
    """Read the API key from the environment. Never from a config file."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise ConfigError(
            f"{API_KEY_ENV} is not set. Copy .env.example to .env and add your key."
        )
    return key


def resolve_path(key: str) -> Path:
    """Absolute path for an entry in ``settings.paths``."""
    paths = load_settings()["paths"]
    if key not in paths:
        raise ConfigError(f"unknown path key: {key}")
    return PROJECT_ROOT / paths[key]
