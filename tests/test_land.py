"""Phase 2 -- landing zone. Immutability and lineage."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from ingest.land import LINEAGE_COLUMNS, land_records, partition_dir, read_landed
from ingest.models import SchemaError

PULLED = date(2026, 8, 20)


def records(n: int = 2, modal: str = "1600") -> list[dict]:
    return [
        {
            "state": "Maharashtra",
            "district": "Nashik",
            "market": "Lasalgaon",
            "commodity": "Onion",
            "variety": "Red",
            "grade": "FAQ",
            "arrival_date": "18/08/2026",
            "min_price": "1200",
            "max_price": "1850",
            "modal_price": modal,
        }
        for _ in range(n)
    ]


# --- 2.1 -------------------------------------------------------------------


def test_land_writes_parquet(tmp_path):
    path = land_records(records(3), "api", "Onion", tmp_path, pulled_date=PULLED)

    assert path is not None and path.exists()
    assert path.name == "part-000.parquet"
    assert path.parent == partition_dir(tmp_path, "api", PULLED, "Onion")
    assert len(pd.read_parquet(path)) == 3


# --- 2.2 -------------------------------------------------------------------


def test_land_adds_lineage_columns(tmp_path):
    path = land_records(records(2), "api", "Onion", tmp_path, pulled_date=PULLED)
    frame = pd.read_parquet(path)

    for column in LINEAGE_COLUMNS:
        assert column in frame.columns
        assert frame[column].notna().all()

    assert frame["source"].unique().tolist() == ["api"]
    assert frame["ingest_run_id"].nunique() == 1


# --- 2.3 -------------------------------------------------------------------


def test_land_never_overwrites(tmp_path):
    first = land_records(records(2), "api", "Onion", tmp_path, pulled_date=PULLED)
    first_bytes = first.read_bytes()

    second = land_records(records(5), "api", "Onion", tmp_path, pulled_date=PULLED)

    assert second != first
    assert second.name == "part-001.parquet"
    assert first.read_bytes() == first_bytes, "existing partition file was modified"
    assert len(sorted(first.parent.glob("part-*.parquet"))) == 2


# --- 2.4 -------------------------------------------------------------------


def test_land_partition_path_format(tmp_path):
    path = land_records(records(1), "api", "Onion", tmp_path, pulled_date=PULLED)
    relative = path.relative_to(tmp_path).as_posix()

    assert re.fullmatch(
        r"source=api/pulled_date=2026-08-20/commodity=Onion/part-\d{3}\.parquet",
        relative,
    ), relative


def test_land_rejects_unknown_source(tmp_path):
    with pytest.raises(SchemaError):
        land_records(records(1), "guesswork", "Onion", tmp_path, pulled_date=PULLED)


# --- 2.5 -------------------------------------------------------------------


def test_land_empty_input_writes_nothing(tmp_path, caplog):
    result = land_records([], "api", "Onion", tmp_path, pulled_date=PULLED)

    assert result is None
    assert not list(tmp_path.rglob("*.parquet"))


def test_read_landed_filters_by_source(tmp_path):
    land_records(records(2), "api", "Onion", tmp_path, pulled_date=PULLED)
    land_records(records(3), "backfill", "Onion", tmp_path, pulled_date=PULLED)

    assert len(read_landed(tmp_path)) == 5
    assert len(read_landed(tmp_path, source="api")) == 2
    assert len(read_landed(tmp_path, source="backfill")) == 3
    assert read_landed(tmp_path / "nothing-here").empty


def test_land_preserves_supplied_fetch_time(tmp_path):
    stamp = datetime(2026, 8, 20, 6, 30, tzinfo=UTC)
    path = land_records(
        records(1), "api", "Onion", tmp_path, pulled_date=PULLED, fetched_at_utc=stamp
    )
    assert pd.read_parquet(path)["fetched_at_utc"].iloc[0] == stamp.isoformat()
