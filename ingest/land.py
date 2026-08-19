"""Immutable landing zone.

Raw records are written once, partitioned, with lineage columns attached.
A partition file is never rewritten, so a parsing bug is a re-parse rather
than a re-crawl.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import structlog

from ingest.models import SchemaError

log = structlog.get_logger(__name__)

LINEAGE_COLUMNS = ("fetched_at_utc", "source", "ingest_run_id")
VALID_SOURCES = ("api", "backfill", "fixture")
CHECKPOINT_FILENAME = "_checkpoint.json"

STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETE = "complete"


def new_run_id() -> str:
    return str(uuid.uuid4())


def partition_dir(root: Path, source: str, pulled_date: date, commodity: str) -> Path:
    return (
        Path(root)
        / f"source={source}"
        / f"pulled_date={pulled_date.isoformat()}"
        / f"commodity={commodity}"
    )


def _as_text(frame: pd.DataFrame) -> pd.DataFrame:
    """Store every source column as text, preserving nulls.

    The feed is inconsistent about types: the same price column arrives as
    a JSON number in most rows and a string in others, which parquet cannot
    represent in one column. Landing everything as text keeps the payload
    byte-faithful and leaves interpretation to transform/parse.py, which is
    where a malformed value can be rejected with a reason instead of
    silently coerced.
    """
    out = frame.copy()
    for column in out.columns:
        out[column] = out[column].map(
            lambda v: None
            if v is None or (isinstance(v, float) and pd.isna(v))
            else str(v)
        )
    return out


def _next_part_path(directory: Path) -> Path:
    """First unused ``part-NNN.parquet`` in the directory."""
    existing = sorted(directory.glob("part-*.parquet"))
    return directory / f"part-{len(existing):03d}.parquet"


def land_records(
    records: list[dict],
    source: str,
    commodity: str,
    root: Path,
    pulled_date: date | None = None,
    ingest_run_id: str | None = None,
    fetched_at_utc: datetime | None = None,
) -> Path | None:
    """Write records to a new partition file. Returns the path, or None if
    there was nothing to write."""
    if source not in VALID_SOURCES:
        raise SchemaError(f"unknown source {source!r}; expected one of {VALID_SOURCES}")

    if not records:
        log.warning("land.empty", source=source, commodity=commodity)
        return None

    frame = pd.DataFrame(records)
    frame = _as_text(frame)
    frame["fetched_at_utc"] = (fetched_at_utc or datetime.now(UTC)).isoformat()
    frame["source"] = source
    frame["ingest_run_id"] = ingest_run_id or new_run_id()

    directory = partition_dir(
        root, source, pulled_date or datetime.now(UTC).date(), commodity
    )
    directory.mkdir(parents=True, exist_ok=True)
    path = _next_part_path(directory)
    frame.to_parquet(path, index=False)

    log.info(
        "land.write",
        path=str(path),
        rows=len(frame),
        source=source,
        commodity=commodity,
    )
    return path


def read_landed(root: Path, source: str | None = None) -> pd.DataFrame:
    """Read every landed partition under root, optionally one source only."""
    pattern = f"source={source}/**/*.parquet" if source else "**/*.parquet"
    files = sorted(Path(root).glob(pattern))
    if not files:
        return pd.DataFrame()
    frames = [pd.read_parquet(f) for f in files]
    return pd.concat(frames, ignore_index=True)


# -- checkpointing ---------------------------------------------------------


def checkpoint_path(root: Path) -> Path:
    return Path(root) / CHECKPOINT_FILENAME


def read_checkpoint(root: Path) -> dict:
    path = checkpoint_path(root)
    if not path.exists():
        return {"runs": {}}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("runs", {})
    return data


def write_checkpoint(root: Path, commodity: str, last_offset: int, status: str) -> dict:
    """Record progress for one commodity. ``last_offset`` is the next offset
    to fetch, so a resumed run picks up exactly where it stopped."""
    if status not in (STATUS_IN_PROGRESS, STATUS_COMPLETE):
        raise SchemaError(f"unknown checkpoint status: {status!r}")

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    data = read_checkpoint(root)
    data["runs"][commodity] = {
        "last_offset": int(last_offset),
        "last_success_at_utc": datetime.now(UTC).isoformat(),
        "status": status,
    }
    with open(checkpoint_path(root), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)

    log.info(
        "checkpoint.write", commodity=commodity, last_offset=last_offset, status=status
    )
    return data


def resume_offset(root: Path, commodity: str) -> int:
    """Offset a resumed run should start from. Zero once complete."""
    run = read_checkpoint(root)["runs"].get(commodity)
    if not run or run.get("status") == STATUS_COMPLETE:
        return 0
    return int(run.get("last_offset", 0))
