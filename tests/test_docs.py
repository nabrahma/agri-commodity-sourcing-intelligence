"""Phase 11 -- documentation is checked in and checked."""

from __future__ import annotations

import re

import pytest
import yaml

from tests.conftest import walk_source_files

REQUIRED_DOCS = (
    "README.md",
    "METHOD.md",
    "LIMITATIONS.md",
    "docs/data_quality.md",
    "docs/source_reconciliation.md",
    "docs/brief.md",
    "docs/weekly_log_sample.csv",
)

# Assembled at runtime so this file does not trip its own scanner.
PLACEHOLDERS = ("TBD", "<insert>", "lorem ipsum")
TODO_MARKERS = ("TO" + "DO", "FIX" + "ME", "X" + "XX")

SOURCE_SUFFIXES = {".py", ".sql", ".yml", ".yaml", ".toml", ".md", ".csv"}


def tracked_files(project_root):
    for path in walk_source_files(project_root, SOURCE_SUFFIXES):
        # The build spec is this project's input, not its output; and this
        # module necessarily contains the marker strings it searches for.
        if path.name in ("build-spec.md", "test_docs.py"):
            continue
        yield path


# --- 11.1 ------------------------------------------------------------------


def test_readme_has_headline_number(project_root):
    readme = (project_root / "README.md").read_text(encoding="utf-8")

    assert "₹" in readme, "the README must carry a rupee figure"
    assert re.search(r"₹\s?[\d,]+(\.\d+)?\s*(lakh|crore|/quintal|/qtl)", readme)
    assert re.search(r"\d+(\.\d+)?%", readme), "state the saving as a percentage"
    # Provenance: a headline number without its data behind it is a claim.
    assert re.search(
        r"[\d,]{7,}\s+observed price records", readme
    ), "the README must say how many records the number rests on"


# --- 11.2 ------------------------------------------------------------------


@pytest.mark.parametrize("relative", REQUIRED_DOCS)
def test_all_docs_exist(project_root, relative):
    path = project_root / relative

    assert path.exists(), f"{relative} is missing"
    assert path.stat().st_size > 0, f"{relative} is empty"


# --- 11.3 ------------------------------------------------------------------


def test_no_todo_markers(project_root):
    offenders = []
    for path in tracked_files(project_root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for marker in TODO_MARKERS:
                if marker in line:
                    offenders.append(f"{path.name}:{line_no}: {marker}")

    assert not offenders, "unfinished work markers found:\n" + "\n".join(offenders)


# --- 11.4 ------------------------------------------------------------------


def test_no_placeholder_values(project_root):
    for name in ("README.md", "METHOD.md", "LIMITATIONS.md", "docs/brief.md"):
        text = (project_root / name).read_text(encoding="utf-8")
        for placeholder in PLACEHOLDERS:
            assert placeholder not in text, f"{name} contains {placeholder!r}"


# --- 11.5 ------------------------------------------------------------------


def test_assumptions_documented(project_root):
    """Every key in assumptions.yaml must be named in METHOD.md.

    An assumption that drives the number but is not written down is how a
    reader ends up trusting a figure they cannot interrogate.
    """
    method = (project_root / "METHOD.md").read_text(encoding="utf-8")
    with open(project_root / "config" / "assumptions.yaml", encoding="utf-8") as fh:
        assumptions = yaml.safe_load(fh)

    undocumented = []
    for section, entries in assumptions.items():
        for key, value in entries.items():
            if isinstance(value, dict):
                for nested in value:
                    if nested not in method:
                        undocumented.append(f"{section}.{key}.{nested}")
            elif key not in method:
                undocumented.append(f"{section}.{key}")

    assert not undocumented, f"not documented in METHOD.md: {undocumented}"


def test_settings_thresholds_documented(project_root):
    method = (project_root / "METHOD.md").read_text(encoding="utf-8")
    with open(project_root / "config" / "settings.yaml", encoding="utf-8") as fh:
        settings = yaml.safe_load(fh)

    for key in settings["quality"]:
        assert key in method, f"quality.{key} is not documented in METHOD.md"


def test_limitations_names_the_binding_assumption(project_root):
    limitations = (project_root / "LIMITATIONS.md").read_text(encoding="utf-8")

    assert "binding assumption" in limitations.lower()
    assert "transport" in limitations.lower()
    assert "commission" in limitations.lower()
    assert "survivorship" in limitations.lower()


def test_brief_states_a_range_not_only_a_point(project_root):
    brief = (project_root / "docs" / "brief.md").read_text(encoding="utf-8")

    assert re.search(r"₹\s?[\d,.]+\s*(lakh|crore|/quintal|/qtl)", brief)
    # A point estimate hides the uncertainty; a range is the honest form.
    assert re.search(
        r"\d+(\.\d+)?%\s*(to|–|-)\s*\d+(\.\d+)?%", brief
    ), "state the saving as a range, not only a point"
    assert "Limitations" in brief
    assert "Recommendation" in brief


def test_weekly_log_sample_is_a_real_audit_trail(project_root):
    import pandas as pd

    log = pd.read_csv(project_root / "docs" / "weekly_log_sample.csv")

    assert len(log) == 52
    for column in (
        "week_start",
        "market",
        "modal_price_inr_qtl",
        "purchased_qtl",
        "closing_inventory_qtl",
        "week_cost_inr",
    ):
        assert column in log.columns
        assert log[column].notna().all()
