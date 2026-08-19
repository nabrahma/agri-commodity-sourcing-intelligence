"""Phase 9 -- CI configuration is itself checked in and tested."""

from __future__ import annotations

import re

import pytest
import yaml

from tests.conftest import walk_source_files

WORKFLOWS = ("ci.yml", "daily-pull.yml")

# Anything that looks like a real data.gov.in key: 32+ hex characters.
KEY_LIKE = re.compile(r"\b[0-9a-f]{32,}\b", re.IGNORECASE)


@pytest.fixture
def workflows(project_root):
    directory = project_root / ".github" / "workflows"
    return {name: (directory / name) for name in WORKFLOWS}


def test_ci_workflow_valid_yaml(workflows):
    parsed = yaml.safe_load(workflows["ci.yml"].read_text(encoding="utf-8"))

    assert parsed["name"] == "ci"
    assert "test" in parsed["jobs"]
    steps = parsed["jobs"]["test"]["steps"]
    assert any("ruff check" in str(step.get("run", "")) for step in steps)
    assert any("pytest" in str(step.get("run", "")) for step in steps)


def test_daily_workflow_valid_yaml(workflows):
    parsed = yaml.safe_load(workflows["daily-pull.yml"].read_text(encoding="utf-8"))

    assert parsed["name"] == "daily-pull"
    # PyYAML parses a bare `on:` key as the boolean True.
    triggers = parsed.get("on", parsed.get(True))
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers, "must be manually triggerable"

    steps = parsed["jobs"]["pull"]["steps"]
    env = [step.get("env", {}) for step in steps]
    assert any(
        entry.get("DATA_GOV_API_KEY") == "${{ secrets.DATA_GOV_API_KEY }}"
        for entry in env
    ), "the key must come from repository secrets"


def test_no_secrets_in_workflows(workflows):
    for name, path in workflows.items():
        text = path.read_text(encoding="utf-8")
        assert not KEY_LIKE.search(text), f"{name} contains a key-like literal"
        assert "DATA_GOV_API_KEY=" not in text, f"{name} assigns the key inline"


def test_ci_runs_full_suite(workflows):
    text = workflows["ci.yml"].read_text(encoding="utf-8")
    pytest_lines = [line for line in text.splitlines() if "pytest" in line]

    assert len(pytest_lines) == 1
    command = pytest_lines[0]
    assert " -k " not in command, "CI must not filter the suite"
    assert "--cov-fail-under=85" in command
    assert "-x" not in command.split(), "CI reports every failure, not just the first"


def test_no_secrets_anywhere_in_tracked_source(project_root):
    """A key-shaped literal must not appear in any tracked text file."""
    suffixes = {".py", ".yml", ".yaml", ".toml", ".md", ".cfg", ".txt", ".sql"}

    for path in walk_source_files(project_root, suffixes):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in KEY_LIKE.findall(text):
            # The public resource id is not a secret.
            assert "9ef84268" in match or len(match) < 32, f"{path}: {match[:8]}..."


def test_daily_workflow_does_not_rebuild_derived_artefacts(workflows):
    """The runner only ever has the day it just pulled.

    An earlier version of this workflow ran clean/warehouse/analytics after
    the pull and committed the result. With no archive on the runner that
    regenerated docs/data_quality.md from ~1,900 rows and overwrote the
    report covering 1.31M, which is a silent loss: the workflow goes green
    while the committed numbers become wrong.
    """
    text = workflows["daily-pull.yml"].read_text(encoding="utf-8")

    for module in ("transform.clean", "transform.warehouse", "analytics.queries"):
        assert module not in text, (
            f"daily-pull runs {module}, which would rebuild committed outputs "
            "from a single day of data"
        )

    parsed = yaml.safe_load(text)
    steps = parsed["jobs"]["pull"]["steps"]
    commit = next(s for s in steps if "git commit" in str(s.get("run", "")))
    run = commit["run"]

    assert "data/raw/source=api" in run, "the daily pull must commit its partitions"
    assert "docs/" not in run, "generated docs must not be committed from CI"
    assert (
        "git add -f" not in run
    ), "a force-add hides the policy; the path is un-ignored in .gitignore"
