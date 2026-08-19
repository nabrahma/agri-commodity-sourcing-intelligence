"""Phase 3 -- the cleaning pipeline and its invariants."""

from __future__ import annotations

import pandas as pd
import pytest
from freezegun import freeze_time

from ingest.models import RejectReason
from transform.canonicalise import load_commodity_map, load_market_map
from transform.clean import (
    CLEAN_COLUMNS,
    GRAIN,
    REJECTED_COLUMNS,
    clean_dataframe,
    write_data_quality_report,
    write_quarantine,
)

# The fixture is built so every count below is known by hand.
EXPECTED_CLEAN_ROWS = 8
EXPECTED_REJECT_COUNTS = {
    RejectReason.MISSING_REQUIRED_FIELD.value: 1,
    RejectReason.UNPARSEABLE_DATE.value: 1,
    RejectReason.FUTURE_DATE.value: 1,
    RejectReason.UNPARSEABLE_PRICE.value: 1,
    RejectReason.NON_POSITIVE_PRICE.value: 1,
    RejectReason.MIN_GT_MAX.value: 1,
    RejectReason.MODAL_OUT_OF_RANGE.value: 1,
    RejectReason.UNKNOWN_COMMODITY.value: 1,
    RejectReason.UNKNOWN_MARKET.value: 1,
    RejectReason.DUPLICATE_GRAIN.value: 1,
}


@pytest.fixture(scope="session")
def commodity_map(project_root):
    return load_commodity_map(project_root / "seeds" / "commodity_map.csv")


@pytest.fixture(scope="session")
def market_map(project_root):
    return load_market_map(project_root / "seeds" / "market_map.csv")


@pytest.fixture
def dirty_raw(fixtures_dir):
    return pd.read_csv(fixtures_dir / "raw_dirty_sample.csv", dtype=str)


@pytest.fixture
def cleaned(dirty_raw, commodity_map, market_map):
    with freeze_time("2026-08-19"):
        return clean_dataframe(dirty_raw, commodity_map, market_map, outlier_z=4.0)


# --- 3.32 ------------------------------------------------------------------


def test_conservation_invariant(dirty_raw, cleaned):
    clean, rejected = cleaned
    assert len(clean) + len(rejected) == len(dirty_raw)
    assert len(clean) == EXPECTED_CLEAN_ROWS


# --- 3.33 / 3.34 -----------------------------------------------------------


def test_every_reject_has_reason(cleaned):
    _, rejected = cleaned
    assert not rejected.empty
    assert rejected["reject_reason"].notna().all()
    assert (rejected["reject_reason"].str.len() > 0).all()
    assert rejected["rejected_at_utc"].notna().all()


def test_reject_reasons_are_enum_members(cleaned):
    _, rejected = cleaned
    allowed = {reason.value for reason in RejectReason}
    assert set(rejected["reject_reason"]) <= allowed
    assert rejected["reject_reason"].value_counts().to_dict() == EXPECTED_REJECT_COUNTS


# --- 3.35 / 3.36 -----------------------------------------------------------


def test_dedupe_keeps_latest_fetch(cleaned):
    clean, _ = cleaned
    survivor = clean[
        (clean["market_canonical"] == "Lasalgaon")
        & (clean["arrival_date"] == pd.Timestamp("2026-08-10").date())
    ]
    assert len(survivor) == 1
    # The 2026-08-19 fetch says 1600; the older 2026-08-18 fetch said 1500.
    assert survivor["modal_price_inr_qtl"].iloc[0] == 1600.0


def test_dedupe_counts_rejected(cleaned):
    _, rejected = cleaned
    duplicates = rejected[
        rejected["reject_reason"] == RejectReason.DUPLICATE_GRAIN.value
    ]
    assert len(duplicates) == 1
    assert "1500" in duplicates["raw"].iloc[0], "the losing row is the older fetch"


# --- 3.37 ------------------------------------------------------------------


def test_clean_grain_is_unique(cleaned):
    clean, _ = cleaned
    keys = pd.concat([clean[c].astype("string").fillna("") for c in GRAIN], axis=1)
    assert not keys.duplicated().any()


# --- 3.38 ------------------------------------------------------------------


def test_intraday_spread_computed(commodity_map, market_map):
    raw = pd.DataFrame(
        [
            {
                "state": "Maharashtra",
                "district": "Nashik",
                "market": "Lasalgaon",
                "commodity": "Onion",
                "variety": "Red",
                "grade": "FAQ",
                "arrival_date": "18/08/2026",
                "min_price": "1000",
                "max_price": "2000",
                "modal_price": "1500",
            }
        ]
    )
    with freeze_time("2026-08-19"):
        clean, _ = clean_dataframe(raw, commodity_map, market_map)

    # (2000 - 1000) / 1500 = 66.67%
    assert clean["intraday_spread_pct"].iloc[0] == pytest.approx(66.67, abs=0.01)


# --- 3.39 ------------------------------------------------------------------


def test_outliers_flagged_not_dropped(cleaned):
    clean, _ = cleaned
    assert "is_outlier" in clean.columns

    spike = clean[clean["modal_price_inr_qtl"] == 16000.0]
    assert len(spike) == 1, "the 10x row must still be present, not dropped"
    assert bool(spike["is_outlier"].iloc[0]) is True
    assert int(clean["is_outlier"].sum()) == 1


# --- 3.40 ------------------------------------------------------------------


def test_missing_days_not_interpolated(cleaned):
    """Lasalgaon has no row for 15/08 or 17/08. Those gaps stay gaps."""
    clean, _ = cleaned
    lasalgaon = clean[clean["market_canonical"] == "Lasalgaon"]
    days = {d.day for d in lasalgaon["arrival_date"]}

    assert days == {10, 11, 12, 13, 14, 16}
    assert 15 not in days and 17 not in days
    assert len(lasalgaon) == 6


# --- 3.41 ------------------------------------------------------------------


def test_idempotent(cleaned, commodity_map, market_map):
    clean, _ = cleaned
    with freeze_time("2026-08-19"):
        again, rejected_again = clean_dataframe(clean, commodity_map, market_map)

    assert rejected_again.empty
    pd.testing.assert_frame_equal(
        clean.reset_index(drop=True), again.reset_index(drop=True)
    )


# --- 3.42 / 3.43 -----------------------------------------------------------


def test_empty_input(commodity_map, market_map):
    clean, rejected = clean_dataframe(pd.DataFrame(), commodity_map, market_map)

    assert clean.empty and rejected.empty
    assert list(clean.columns) == list(CLEAN_COLUMNS)
    assert list(rejected.columns) == list(REJECTED_COLUMNS)


def test_all_rows_rejected(commodity_map, market_map):
    raw = pd.DataFrame(
        [
            {
                "state": "Maharashtra",
                "district": "Nashik",
                "market": "Lasalgaon",
                "commodity": "Onion",
                "variety": "Red",
                "grade": "FAQ",
                "arrival_date": "not-a-date",
                "min_price": "1200",
                "max_price": "1850",
                "modal_price": "1600",
            }
        ]
        * 4
    )
    clean, rejected = clean_dataframe(raw, commodity_map, market_map)

    assert clean.empty
    assert len(rejected) == 4
    assert list(clean.columns) == list(CLEAN_COLUMNS)


# --- 3.44 / 3.45 -----------------------------------------------------------


def test_quarantine_file_written(cleaned, tmp_path):
    _, rejected = cleaned
    path = write_quarantine(rejected, tmp_path / "quarantine")

    assert path is not None and path.exists()
    assert len(pd.read_parquet(path)) == len(rejected)
    assert write_quarantine(rejected.iloc[:0], tmp_path / "quarantine") is None


def test_data_quality_report_generated(cleaned, tmp_path):
    clean, rejected = cleaned
    path = write_data_quality_report(clean, rejected, tmp_path / "docs" / "dq.md")
    text = path.read_text(encoding="utf-8")

    assert "Rejections by reason" in text
    for reason, count in EXPECTED_REJECT_COUNTS.items():
        assert f"`{reason}`" in text, reason
        assert f"| {count:,} |" in text
    assert "Coverage by market" in text
    assert f"| {len(clean):,} |" in text
