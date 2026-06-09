#!/usr/bin/env python3
"""Backfill per-lap aggregates (avg_throttle / avg_brake / avg_slip /
peak_slip / slip_above_pct) on existing rows in the `laps` table.

Going forward these are computed once at session close and stored on
the row, so /sessions/session/data is a pure SQL query. Pre-existing
sessions don't have them yet — this script fills them in.

Source preference: the `lap_samples` table (already-normalised JSON
blob). If a session has no lap_samples row, fall back to the on-disk
`<sid>_laps.json`. Skip silently if neither is available.

Usage:
  python3 scripts/backfill_lap_aggregates.py             # dry run
  python3 scripts/backfill_lap_aggregates.py --apply     # actually update
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import storage_path                       # noqa: E402
from db.store import compute_lap_aggregates           # noqa: E402


def find_pending(conn) -> list:
    """Return laps rows where any aggregate is still NULL."""
    return conn.execute("""
        SELECT id, session_id, lap_number
          FROM laps
         WHERE avg_throttle IS NULL
            OR avg_brake    IS NULL
            OR avg_slip     IS NULL
            OR peak_slip    IS NULL
            OR slip_above_pct IS NULL
         ORDER BY session_id, lap_number
    """).fetchall()


def samples_from_db(conn, sid: str, lap_n: int):
    row = conn.execute(
        "SELECT samples_json FROM lap_samples WHERE session_id=? AND lap_number=?",
        (sid, lap_n),
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["samples_json"])
    except (json.JSONDecodeError, ValueError):
        return None


_laps_file_cache: dict = {}


def samples_from_disk(sessions_dir: Path, sid: str, lap_n: int):
    """Older sessions only have <sid>_laps.json; lap_samples may be absent."""
    if sid not in _laps_file_cache:
        f = sessions_dir / f"{sid}_laps.json"
        try:
            _laps_file_cache[sid] = json.loads(f.read_text()) if f.exists() else []
        except (OSError, json.JSONDecodeError):
            _laps_file_cache[sid] = []
    for lap in _laps_file_cache[sid]:
        if lap.get("lap_number") == lap_n:
            return lap.get("samples", [])
    return None


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true",
                        help="actually update (default is dry-run)")
    args = parser.parse_args()

    sp = storage_path()
    db_path = sp / "simtelemetry.db"
    if not db_path.exists():
        print(f"No database at {db_path} — nothing to backfill.", file=sys.stderr)
        sys.exit(1)
    sessions_dir = sp / "sessions"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        pending = find_pending(conn)
        if not pending:
            print("All laps already have aggregates. Nothing to do.")
            return
        print(f"Found {len(pending)} lap row(s) missing aggregates.")
        if not args.apply:
            print("[dry-run] re-run with --apply to update.")
            return

        updated = 0
        skipped_no_samples = 0
        for row in pending:
            sid, lap_n = row["session_id"], row["lap_number"]
            samples = samples_from_db(conn, sid, lap_n)
            if samples is None:
                samples = samples_from_disk(sessions_dir, sid, lap_n)
            if not samples:
                skipped_no_samples += 1
                continue
            agg = compute_lap_aggregates(samples)
            conn.execute("""
                UPDATE laps
                   SET avg_throttle=?, avg_brake=?, avg_slip=?,
                       peak_slip=?, slip_above_pct=?
                 WHERE id=?
            """, (agg["avg_throttle"], agg["avg_brake"], agg["avg_slip"],
                  agg["peak_slip"], agg["slip_above_pct"], row["id"]))
            updated += 1
        conn.commit()
        print(f"Updated {updated} lap row(s); "
              f"skipped {skipped_no_samples} (no source samples available).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
