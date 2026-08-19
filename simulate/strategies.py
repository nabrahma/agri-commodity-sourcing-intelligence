"""Sourcing strategies and the look-ahead firewall.

A strategy only ever sees a PriceView. The view filters its frame to
`as_of_date` on construction and exposes no accessor that can return a
later row, so seeing a future price is structurally impossible rather than
a convention someone has to remember.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from ingest.models import SourcingError

# How stale a quote may be before a market counts as silent. A market that
# did not report this week is not assumed to hold last week's price
# indefinitely.
DEFAULT_MAX_STALENESS_DAYS = 7

REQUIRED_PRICE_COLUMNS = ("date", "market", "modal_price_inr_qtl")


class NoCandidateMarketsError(SourcingError):
    """No market had a usable price on the decision date."""


def _is_date_column(series: pd.Series) -> bool:
    """True when the column already holds plain `date` objects."""
    if series.dtype != object or series.empty:
        return False
    first = series.iloc[0]
    return isinstance(first, date) and not isinstance(first, pd.Timestamp)


@dataclass(frozen=True)
class PriceView:
    """Prices available to a decision-maker AS OF `as_of_date`.

    The frame is filtered on construction; there is no method that returns
    anything after `as_of_date`.
    """

    as_of_date: date
    _frame: pd.DataFrame = field(repr=False)

    def __post_init__(self) -> None:
        missing = [c for c in REQUIRED_PRICE_COLUMNS if c not in self._frame.columns]
        if missing:
            raise SourcingError(f"price frame is missing columns: {missing}")

        frame = self._frame
        # Converting dtypes is the expensive part and the panel does not
        # change between weeks, so skip it when the column is already dates.
        if not _is_date_column(frame["date"]):
            frame = frame.assign(date=pd.to_datetime(frame["date"]).dt.date)

        frame = frame[frame["date"] <= self.as_of_date].reset_index(drop=True)
        object.__setattr__(self, "_frame", frame)

    def current_prices(self) -> pd.DataFrame:
        """Prices on `as_of_date` only."""
        return self._frame[self._frame["date"] == self.as_of_date].reset_index(
            drop=True
        )

    def latest_prices(
        self, max_staleness_days: int = DEFAULT_MAX_STALENESS_DAYS
    ) -> pd.DataFrame:
        """Most recent quote per market, at or before `as_of_date`.

        This is the documented rule for a market that is silent on the
        decision day: fall back to its last quote within the staleness
        window, or treat it as unavailable.
        """
        floor = self.as_of_date - timedelta(days=max_staleness_days)
        window = self._frame[self._frame["date"] >= floor]
        if window.empty:
            return window.reset_index(drop=True)
        return (
            window.sort_values("date")
            .groupby("market", as_index=False)
            .last()
            .reset_index(drop=True)
        )

    def trailing_mean(self, market: str, days: int) -> float | None:
        """Mean modal price over the `days` strictly before `as_of_date`.

        Returns None when fewer than `days // 2` observations exist, so a
        thin history never masquerades as a trend.
        """
        floor = self.as_of_date - timedelta(days=days)
        window = self._frame[
            (self._frame["market"] == market)
            & (self._frame["date"] >= floor)
            & (self._frame["date"] < self.as_of_date)
        ]
        if len(window) < max(1, days // 2):
            return None
        return float(window["modal_price_inr_qtl"].mean())


@dataclass(frozen=True)
class Purchase:
    market: str
    quantity_qtl: float
    modal_price_inr_qtl: float
    transport_inr_qtl: float
    landed_inr_qtl: float
    total_inr: float


@dataclass(frozen=True)
class S3Params:
    dip_trigger_ratio: float = 0.90
    moving_average_days: int = 20
    max_multiple_of_need: float = 2.0


def _purchase(market: str, quantity_qtl: float, modal: float, transport: float):
    landed = modal + transport
    return Purchase(
        market=market,
        quantity_qtl=float(quantity_qtl),
        modal_price_inr_qtl=float(modal),
        transport_inr_qtl=float(transport),
        landed_inr_qtl=float(landed),
        total_inr=float(quantity_qtl) * float(landed),
    )


def _priced_candidates(
    view: PriceView,
    candidates: pd.DataFrame,
    max_staleness_days: int = DEFAULT_MAX_STALENESS_DAYS,
) -> pd.DataFrame:
    """Join candidate markets to their latest available price.

    `candidates` carries `market` and `transport_inr_qtl`.
    """
    if candidates is None or candidates.empty:
        raise NoCandidateMarketsError(
            f"no candidate markets supplied for {view.as_of_date}"
        )

    prices = view.latest_prices(max_staleness_days)
    merged = candidates.merge(
        prices[["market", "modal_price_inr_qtl", "date"]], on="market", how="inner"
    )
    if merged.empty:
        raise NoCandidateMarketsError(
            f"no candidate market had a price on or before {view.as_of_date} "
            f"within {max_staleness_days} days"
        )

    merged["landed_inr_qtl"] = (
        merged["modal_price_inr_qtl"] + merged["transport_inr_qtl"]
    )
    return merged.sort_values(["landed_inr_qtl", "market"]).reset_index(drop=True)


def decide_s1(view: PriceView, need_qtl: float, home_market: str) -> Purchase:
    """Baseline: always buy the exact requirement at the home market."""
    home = pd.DataFrame([{"market": home_market, "transport_inr_qtl": 0.0}])
    best = _priced_candidates(view, home).iloc[0]
    return _purchase(home_market, need_qtl, best["modal_price_inr_qtl"], 0.0)


def decide_s2(view: PriceView, need_qtl: float, candidates: pd.DataFrame) -> Purchase:
    """Spatial: buy the requirement wherever landed cost is lowest.

    Lowest landed cost, not lowest modal price -- a cheap distant market can
    easily be dearer once freight is paid.
    """
    best = _priced_candidates(view, candidates).iloc[0]
    return _purchase(
        best["market"],
        need_qtl,
        best["modal_price_inr_qtl"],
        best["transport_inr_qtl"],
    )


def decide_s3(
    view: PriceView,
    need_qtl: float,
    candidates: pd.DataFrame,
    inventory_qtl: float,
    storage_cap_qtl: float,
    params: S3Params,
) -> Purchase:
    """Spatial plus timing: buy ahead when the price is below its own mean.

    Falls back to S2 behaviour whenever the moving average is unavailable,
    so the first weeks of a run are never driven by a half-formed average.
    """
    best = _priced_candidates(view, candidates).iloc[0]
    market = best["market"]
    modal = float(best["modal_price_inr_qtl"])
    transport = float(best["transport_inr_qtl"])

    # Draw down inventory before buying anything.
    net_need = max(0.0, float(need_qtl) - float(inventory_qtl))

    moving_average = view.trailing_mean(market, params.moving_average_days)
    quantity = net_need

    if moving_average is not None and modal < params.dip_trigger_ratio * moving_average:
        target = params.max_multiple_of_need * float(need_qtl)
        # Carry-out after this week's delivery must fit the store.
        headroom = storage_cap_qtl - float(inventory_qtl) + float(need_qtl)
        quantity = max(net_need, min(target, headroom))

    return _purchase(market, max(0.0, quantity), modal, transport)
