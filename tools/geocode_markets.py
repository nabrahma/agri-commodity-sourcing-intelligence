"""Build seeds/market_map.csv from the landed data.

The build spec assigns geocoding to a human with a map. This does the same
job against OpenStreetMap's Nominatim, with three rules that matter:

  1. A market that cannot be located is written with EMPTY coordinates. It
     is never given a guessed or district-centroid position, because a wrong
     coordinate produces a wrong distance and therefore a wrong rupee number.
  2. Every hit is validated against India's bounding box and rejected if it
     lands outside.
  3. Nominatim's usage policy is respected: a real User-Agent and no more
     than one request per second.

Run once, then commit the result. Re-running only fills gaps unless
--refresh is passed.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from pathlib import Path

import duckdb
import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = PROJECT_ROOT / "seeds" / "market_map.csv"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = (
    "agri-commodity-sourcing-intelligence/0.1 "
    "(portfolio project; contact via github.com/nabrahma)"
)
REQUEST_INTERVAL_SECONDS = 1.1

# Generous box around India; anything outside is a mis-hit, not a market.
INDIA_BBOX = {"lat": (6.0, 37.6), "lon": (67.5, 97.6)}

_PARENTHETICAL = re.compile(r"\s*\([^)]*\)")
_WHITESPACE = re.compile(r"\s+")


def canonical_name(raw: str) -> str:
    """Strip parentheticals and collapse whitespace, keeping it recognisable."""
    return _WHITESPACE.sub(" ", _PARENTHETICAL.sub("", str(raw))).strip().title()


def top_markets(raw_glob: str, states: list[str], limit: int) -> list[dict]:
    rows = duckdb.sql(f"""
        SELECT market, district, state, COUNT(*) AS observations
        FROM '{raw_glob}'
        WHERE state IN {tuple(states)}
          AND market IS NOT NULL AND TRIM(market) <> ''
        GROUP BY market, district, state
        ORDER BY observations DESC
        LIMIT {int(limit)}
    """).fetchall()
    return [
        {"market": m, "district": d or "", "state": s, "observations": n}
        for m, d, s, n in rows
    ]


MAX_ATTEMPTS = 4


def _query(client: httpx.Client, text: str):
    """One Nominatim lookup, retried on throttling.

    A throttled request is NOT the same as a place that does not exist, and
    conflating them silently drops real markets from the analysis. Rate
    limits are retried; only a genuine empty result counts as not-found.
    """
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = client.get(
                NOMINATIM,
                params={"q": text, "format": "json", "limit": 1, "countrycodes": "in"},
            )
        except httpx.HTTPError:
            time.sleep(REQUEST_INTERVAL_SECONDS * (attempt + 2))
            continue

        time.sleep(REQUEST_INTERVAL_SECONDS)
        if response.status_code in (429, 503) or response.status_code >= 500:
            time.sleep(REQUEST_INTERVAL_SECONDS * (attempt + 2) * 2)
            continue
        if response.status_code != 200:
            return None, f"http-{response.status_code}"
        try:
            return response.json(), None
        except ValueError:
            return None, "bad-json"
    return None, "throttled"


def geocode(client: httpx.Client, market: str, district: str, state: str):
    """Return ((lat, lon), None) or (None, reason). Most specific query first."""
    name = canonical_name(market)
    attempts = [f"{name}, {district}, {state}, India", f"{name}, {state}, India"]
    last_reason = "no-match"

    for text in attempts:
        hits, reason = _query(client, text)
        if reason:
            last_reason = reason
            continue
        if not hits:
            continue

        lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
        lo_lat, hi_lat = INDIA_BBOX["lat"]
        lo_lon, hi_lon = INDIA_BBOX["lon"]
        if lo_lat <= lat <= hi_lat and lo_lon <= lon <= hi_lon:
            return (lat, lon), None
        last_reason = "outside-india"

    return None, last_reason


def read_existing() -> dict[tuple[str, str], dict]:
    if not OUT_PATH.exists():
        return {}
    with open(OUT_PATH, encoding="utf-8", newline="") as fh:
        return {(row["raw_market"], row["district"]): row for row in csv.DictReader(fh)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=150)
    parser.add_argument(
        "--raw-glob", default=str(PROJECT_ROOT / "data/raw/**/*.parquet")
    )
    parser.add_argument("--refresh", action="store_true", help="re-geocode known rows")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(PROJECT_ROOT))
    from appconfig import load_settings

    states = load_settings()["scope"]["states"]
    markets = top_markets(args.raw_glob.replace("\\", "/"), states, args.limit)
    existing = read_existing()
    print(f"{len(markets)} candidate markets; {len(existing)} already mapped")

    resolved, failed = 0, 0
    reasons: dict[str, int] = {}
    out_rows: list[dict] = []
    with httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT}) as client:
        for i, entry in enumerate(markets, start=1):
            key = (entry["market"], entry["district"])
            previous = existing.get(key)
            if previous and previous.get("lat") and not args.refresh:
                out_rows.append(previous)
                resolved += 1
                continue

            hit, reason = geocode(
                client, entry["market"], entry["district"], entry["state"]
            )
            if hit:
                resolved += 1
                lat, lon = hit
            else:
                failed += 1
                reasons[reason] = reasons.get(reason, 0) + 1
                lat, lon = "", ""
            print(
                f"  [{i:>3}/{len(markets)}] {entry['market'][:34]:34s} "
                f"{entry['observations']:>7,}  {'OK' if hit else reason.upper()}"
            )
            out_rows.append(
                {
                    "raw_market": entry["market"],
                    "district": entry["district"],
                    "market_canonical": canonical_name(entry["market"]),
                    "state": entry["state"],
                    "lat": lat,
                    "lon": lon,
                }
            )

    # Keep any previously mapped market that fell out of the top N.
    seen = {(r["raw_market"], r["district"]) for r in out_rows}
    out_rows.extend(row for key, row in existing.items() if key not in seen)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "raw_market",
                "district",
                "market_canonical",
                "state",
                "lat",
                "lon",
            ],
        )
        writer.writeheader()
        writer.writerows(
            sorted(out_rows, key=lambda r: (r["state"], r["market_canonical"]))
        )

    print(f"\nwrote {len(out_rows)} rows to {OUT_PATH}")
    print(f"located {resolved} | not located {failed} (left blank, never guessed)")
    for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"    {reason}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
