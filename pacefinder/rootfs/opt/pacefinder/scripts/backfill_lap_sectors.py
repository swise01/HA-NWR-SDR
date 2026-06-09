#!/usr/bin/env python3
"""
Backfill per-lap sector times (s1_time_s / s2_time_s / s3_time_s) for every
existing lap in the SQLite DB.

The per-lap sector computation runs as part of update_track_references()
during normal session-close. This script invokes the same logic once per
distinct (track, game) pair so historical data — sessions captured before
the per-lap sector columns existed — gets retroactively filled in.

The computation is idempotent. Running this script repeatedly produces the
same result. Failing laps (sector sum diverges from lap_time_s by more than
5%, or samples missing) are left NULL and logged.

Usage:
  python3 scripts/backfill_lap_sectors.py            # report + write
  python3 scripts/backfill_lap_sectors.py --dry-run  # report only, no writes
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

# Repo root on sys.path so we can import db.store
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db.store as store  # noqa: E402
from config import load_config  # noqa: E402


def _setup(storage_path: Path) -> sqlite3.Connection:
    """Bootstrap db.store so update_track_references() works standalone."""
    log = logging.getLogger("backfill_lap_sectors")
    store.initialize(
        demo_db_path_ref=[None],
        storage_path_fn=lambda: storage_path,
        forza_tracks={},
        forza_cars={},
        log_fn=log,
    )
    store._db_init()
    return store._db_connect()


def _distinct_tracks(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    return [
        (r["track"], r["game"])
        for r in conn.execute(
            "SELECT DISTINCT track, game FROM sessions "
            "WHERE track IS NOT NULL AND track != '' AND track != 'unknown' "
            "ORDER BY track"
        ).fetchall()
    ]


def _stats(conn: sqlite3.Connection) -> tuple[int, int]:
    """Return (laps_with_sectors, total_valid_laps)."""
    total = conn.execute(
        "SELECT COUNT(*) FROM laps WHERE lap_number > 0 AND lap_time_s IS NOT NULL"
    ).fetchone()[0]
    filled = conn.execute(
        "SELECT COUNT(*) FROM laps WHERE s1_time_s IS NOT NULL"
    ).fetchone()[0]
    return filled, total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be done without writing.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("backfill_lap_sectors")

    cfg = load_config()
    storage_path = Path(cfg["storage_path"])
    if not storage_path.exists():
        log.error(f"storage path does not exist: {storage_path}")
        return 1

    conn = _setup(storage_path)
    try:
        tracks = _distinct_tracks(conn)
        before_filled, before_total = _stats(conn)

        log.info(f"laps with sectors filled: {before_filled} / {before_total}")
        log.info(f"distinct tracks to process: {len(tracks)}")
        for track, game in tracks:
            log.info(f"  · {track} ({game})")

        if args.dry_run:
            log.info("dry-run: no changes written.")
            return 0

        for track, game in tracks:
            try:
                store.update_track_references(track, game)
            except Exception as exc:
                log.warning(f"failed for {track!r} ({game}): {exc}")

        after_filled, after_total = _stats(conn)
        log.info(
            f"done — laps filled: {before_filled} → {after_filled} "
            f"(of {after_total} valid laps)"
        )
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
