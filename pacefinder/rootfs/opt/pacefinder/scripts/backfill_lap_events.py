#!/usr/bin/env python3
"""
Backfill lap_events for every existing session.

The detector runs as part of update_track_references() on session close,
so new sessions get events automatically. This script re-runs the
detection against historical sessions whose lap_samples already exist.

Idempotent — replaces any prior detected events for each (session, lap)
on each run, so re-running after a threshold tweak in
analysis/events.EVENT_THRESHOLDS produces the latest result.

Usage:
  python3 scripts/backfill_lap_events.py            # write
  python3 scripts/backfill_lap_events.py --dry-run  # report counts only
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db.store as store  # noqa: E402
from config import load_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be done without writing.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("backfill_lap_events")

    cfg = load_config()
    storage_path = Path(cfg["storage_path"])
    if not storage_path.exists():
        log.error(f"storage path does not exist: {storage_path}")
        return 1

    store.initialize(
        demo_db_path_ref=[None],
        storage_path_fn=lambda: storage_path,
        forza_tracks={},
        forza_cars={},
        log_fn=log,
    )
    store._db_init()

    conn = store._db_connect()
    try:
        tracks = [
            (r["track"], r["game"]) for r in conn.execute(
                "SELECT DISTINCT track, game FROM sessions "
                "WHERE track IS NOT NULL AND track != '' AND track != 'unknown' "
                "ORDER BY track"
            ).fetchall()
        ]
        before = conn.execute("SELECT COUNT(*) FROM lap_events").fetchone()[0]
        log.info(f"distinct tracks to process: {len(tracks)}")
        log.info(f"lap_events rows before: {before}")

        if args.dry_run:
            log.info("dry-run: no changes written.")
            return 0

        # update_track_references runs the detector as part of its pass.
        for track, game in tracks:
            try:
                store.update_track_references(track, game)
            except Exception as exc:
                log.warning(f"failed for {track!r} ({game}): {exc}")

        after = conn.execute("SELECT COUNT(*) FROM lap_events").fetchone()[0]
        log.info(f"lap_events rows after:  {after}  (Δ {after - before:+})")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
