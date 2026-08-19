"""Shared fixtures.

Nothing here touches the network or the real warehouse.  Anything that
looks like data lives under ``tests/fixtures/`` -- the only directory in
the project where hand-written records are permitted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def settings() -> dict[str, Any]:
    """Parsed ``config/settings.yaml``."""
    with open(PROJECT_ROOT / "config" / "settings.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="session")
def assumptions() -> dict[str, Any]:
    """Parsed ``config/assumptions.yaml``."""
    with open(PROJECT_ROOT / "config" / "assumptions.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="session")
def api_response_ok() -> dict[str, Any]:
    """A well-formed API payload, shaped exactly as build-spec §1.2."""
    with open(FIXTURES_DIR / "api_response_ok.json", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def api_response_empty() -> dict[str, Any]:
    with open(FIXTURES_DIR / "api_response_empty.json", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def api_response_malformed() -> dict[str, Any]:
    """A payload with no ``records`` key -- must provoke SchemaError."""
    with open(FIXTURES_DIR / "api_response_malformed.json", encoding="utf-8") as fh:
        return json.load(fh)
