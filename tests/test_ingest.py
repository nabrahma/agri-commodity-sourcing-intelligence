"""Phase 2 -- checkpointing, daily pull, CSV backfill and reconciliation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from ingest.backfill import (
    backfill_from_csv,
    map_backfill_columns,
    reconcile,
    run_backfill,
    write_reconciliation_report,
)
from ingest.daily import run_daily
from ingest.land import (
    STATUS_COMPLETE,
    STATUS_IN_PROGRESS,
    read_checkpoint,
    read_landed,
    resume_offset,
    write_checkpoint,
)
from ingest.models import SchemaError

PULLED = date(2026, 8, 20)
COLUMN_MAP = Path("seeds/backfill_column_map.yaml")


def record(market="Lasalgaon", modal="1600", arrival="18/08/2026", variety="Red"):
    return {
        "state": "Maharashtra",
        "district": "Nashik",
        "market": market,
        "commodity": "Onion",
        "variety": variety,
        "grade": "FAQ",
        "arrival_date": arrival,
        "min_price": "1200",
        "max_price": "1850",
        "modal_price": modal,
    }


class FakeClient:
    """Client stand-in that serves pre-canned pages and records its offsets."""

    def __init__(
        self, pages: list[list[dict]], total: int = 0, fail_after: int | None = None
    ):
        self.pages = pages
        self.total = total
        self.fail_after = fail_after
        self.offsets: list[int] = []
        self.calls = 0

    def fetch_page(self, offset, limit, filters=None):
        if self.fail_after is not None and self.calls >= self.fail_after:
            raise ConnectionError("simulated crash mid-run")
        self.offsets.append(offset)
        index = offset // limit
        self.calls += 1
        page = self.pages[index] if index < len(self.pages) else []
        return page, self.total

    def fetch_all(self, filters=None, page_size=1000, max_pages=500):
        out: list[dict] = []
        for page in self.pages:
            if not page:
                break
            out.extend(page)
        return out


# --- 2.6 -------------------------------------------------------------------


def test_checkpoint_created_on_first_run(tmp_path):
    client = FakeClient(pages=[[record()] * 2, []])
    run_backfill(client, ["Onion"], tmp_path, page_size=2, pulled_date=PULLED)

    data = read_checkpoint(tmp_path)
    assert "Onion" in data["runs"]
    assert data["runs"]["Onion"]["status"] == STATUS_COMPLETE
    assert "last_success_at_utc" in data["runs"]["Onion"]


# --- 2.7 -------------------------------------------------------------------


def test_checkpoint_resumes_from_offset(tmp_path):
    write_checkpoint(tmp_path, "Onion", 2000, STATUS_IN_PROGRESS)
    client = FakeClient(pages=[[]])

    run_backfill(client, ["Onion"], tmp_path, page_size=1000, pulled_date=PULLED)

    assert client.offsets[0] == 2000, "resumed run did not start from the checkpoint"


# --- 2.8 -------------------------------------------------------------------


def test_checkpoint_marks_complete(tmp_path):
    client = FakeClient(pages=[[record()] * 1000, []])
    run_backfill(client, ["Onion"], tmp_path, page_size=1000, pulled_date=PULLED)

    assert read_checkpoint(tmp_path)["runs"]["Onion"]["status"] == STATUS_COMPLETE
    assert resume_offset(tmp_path, "Onion") == 0, "a complete run restarts from zero"


# --- 2.9 -------------------------------------------------------------------


def test_crash_midrun_leaves_resumable_checkpoint(tmp_path):
    client = FakeClient(pages=[[record()] * 1000] * 5, fail_after=2)

    with pytest.raises(ConnectionError):
        run_backfill(client, ["Onion"], tmp_path, page_size=1000, pulled_date=PULLED)

    run = read_checkpoint(tmp_path)["runs"]["Onion"]
    assert run["last_offset"] == 2000
    assert run["status"] == STATUS_IN_PROGRESS
    assert resume_offset(tmp_path, "Onion") == 2000


# --- 2.10 ------------------------------------------------------------------


def test_daily_pull_is_idempotent_per_day(tmp_path):
    grain = ["arrival_date", "market", "commodity", "variety", "grade"]
    client = FakeClient(pages=[[record(market="Lasalgaon"), record(market="Pune")], []])

    run_daily(client, ["Onion"], tmp_path, pulled_date=PULLED)
    run_daily(client, ["Onion"], tmp_path, pulled_date=PULLED)

    landed = read_landed(tmp_path)
    assert len(landed) == 4, "the landing zone keeps both pulls"
    assert len(sorted((tmp_path).rglob("part-*.parquet"))) == 2
    assert len(landed.drop_duplicates(subset=grain)) == 2, "dedupe key resolves to 2"


# --- 2.11 ------------------------------------------------------------------


def test_backfill_column_mapping(tmp_path):
    csv = tmp_path / "history.csv"
    csv.write_text(
        "State,District,Market,Commodity,Variety,Grade,Arrival_Date,"
        "Min_Price,Max_Price,Modal_Price\n"
        "Maharashtra,Nashik,Lasalgaon,Onion,Red,FAQ,18/08/2026,1200,1850,1600\n",
        encoding="utf-8",
    )
    backfill_from_csv(csv, COLUMN_MAP, tmp_path / "raw", pulled_date=PULLED)

    landed = read_landed(tmp_path / "raw")
    assert len(landed) == 1
    for column in ("state", "market", "commodity", "arrival_date", "modal_price"):
        assert column in landed.columns
    assert landed["market"].iloc[0] == "Lasalgaon"
    assert landed["source"].iloc[0] == "backfill"


# --- 2.12 ------------------------------------------------------------------


def test_backfill_rejects_unmapped_columns():
    frame = pd.DataFrame({"State": ["Maharashtra"], "Mystery_Column": ["?"]})

    with pytest.raises(SchemaError) as excinfo:
        map_backfill_columns(frame, {"State": "state"})

    assert "Mystery_Column" in str(excinfo.value)


# --- 2.13 ------------------------------------------------------------------


def test_reconcile_computes_match_rate():
    # 8 keys in both sources, 1 only in API, 1 only in backfill -> 8/10.
    shared = [record(market=f"M{i}") for i in range(8)]
    api = pd.DataFrame([*shared, record(market="ApiOnly")])
    back = pd.DataFrame([*shared, record(market="BackfillOnly")])

    report = reconcile(api, back)

    assert report["matched_keys"] == 8
    assert report["api_only_keys"] == 1
    assert report["backfill_only_keys"] == 1
    assert report["overlap_rows"] == 10
    assert report["match_rate_pct"] == 80.0


# --- 2.14 ------------------------------------------------------------------


def test_reconcile_handles_zero_overlap():
    api = pd.DataFrame([record(arrival="01/01/2026")])
    back = pd.DataFrame([])

    report = reconcile(api, back)

    assert report["overlap_rows"] == 0
    assert report["match_rate_pct"] == 0.0
    assert report["divergence"].empty


# --- 2.15 ------------------------------------------------------------------


def test_reconcile_flags_price_divergence(tmp_path):
    shared = [record(market=f"M{i}") for i in range(3)]
    api = pd.DataFrame([*shared, record(market="Diverges", modal="3000")])
    back = pd.DataFrame([*shared, record(market="Diverges", modal="2000")])

    report = reconcile(api, back)

    divergence = report["divergence"]
    assert len(divergence) == 1
    assert divergence["market"].iloc[0] == "diverges"
    assert divergence["abs_diff_pct"].iloc[0] == pytest.approx(50.0)

    path = write_reconciliation_report(
        report, tmp_path / "docs" / "recon.md", "Verdict."
    )
    text = path.read_text(encoding="utf-8")
    assert "Match rate" in text
    assert "Verdict." in text
