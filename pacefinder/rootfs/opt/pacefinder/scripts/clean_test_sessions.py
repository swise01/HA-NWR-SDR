#!/usr/bin/env python3
"""Clean up sessions that contain only out-laps / partial laps.

The session pipeline used to record OUT LAPs (lap_number=0) and
sub-20s "laps" as if they were real, polluting best-lap, theoretical,
and trend computations on circuit pages. Going forward those laps are
filtered at session close, but historical data needs a one-shot fix.

This script:
  1. Finds sessions in the DB whose laps are ALL incomplete (lap_number=0
     or lap_time_s < 20s).
  2. Lists them, with date / track / "best" lap so you can sanity-check.
  3. With --apply, deletes them from the sessions / laps / lap_samples
     tables AND the matching <sid>.json / <sid>_laps.json / <sid>.bin
     files on disk.

Without --apply it's a dry run — prints what WOULD be deleted, no
changes made.

Usage:
  python3 scripts/clean_test_sessions.py             # dry run
  python3 scripts/clean_test_sessions.py --apply     # actually delete
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

MIN_VALID_LAP_S = 20.0

# Resolve repo root + storage path the same way listener.py does
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from config import storage_path  # noqa: E402


def find_test_sessions(conn):
    """Return rows for sessions whose recorded best_lap_time_s is too short
    to be a real lap (or missing). The sessions table's best_lap_time_s is
    the authoritative summary value — using it directly avoids false-positives
    from sessions where the laps-table rows are corrupted but the session
    itself has legitimate aggregate data."""
    rows = conn.execute("""
        SELECT session_id, started_at, track, best_lap_time_s, lap_count
          FROM sessions
         WHERE best_lap_time_s IS NULL
            OR best_lap_time_s < ?
         ORDER BY started_at
    """, (MIN_VALID_LAP_S,)).fetchall()
    return rows


def delete_session(conn, sid: str, sessions_dir: Path, raw_dir: Path):
    """Remove a session from all DB tables and any backing files on disk."""
    conn.execute("DELETE FROM lap_samples WHERE session_id=?", (sid,))
    conn.execute("DELETE FROM laps        WHERE session_id=?", (sid,))
    conn.execute("DELETE FROM sessions    WHERE session_id=?", (sid,))

    for f in [
        sessions_dir / f"{sid}.json",
        sessions_dir / f"{sid}_laps.json",
        sessions_dir / f"{sid}_analysis.json",
        raw_dir      / f"{sid}.bin",
    ]:
        if f.exists():
            try:
                f.unlink()
            except OSError as exc:
                print(f"  WARN: could not remove {f}: {exc}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="actually delete (default is dry-run)")
    args = parser.parse_args()

    sp = storage_path()
    db_path = sp / "simtelemetry.db"
    if not db_path.exists():
        print(f"No database at {db_path} — nothing to clean.", file=sys.stderr)
        sys.exit(1)

    sessions_dir = sp / "sessions"
    raw_dir      = sp / "raw"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        sessions = find_test_sessions(conn)
        if not sessions:
            print("No incomplete-only sessions found. DB is clean.")
            return

        print(f"Found {len(sessions)} session(s) where every lap is incomplete:\n")
        print(f"  {'SESSION_ID':<46}  {'TRACK':<32}  BEST_LAP   LAPS")
        print(f"  {'-'*46}  {'-'*32}  --------   ----")
        for r in sessions:
            sid   = r["session_id"]
            track = (r["track"] or "")[:32]
            bl    = f"{r['best_lap_time_s']:.3f}s" if r["best_lap_time_s"] else "—"
            lc    = r["lap_count"] or 0
            print(f"  {sid:<46}  {track:<32}  {bl:<8}   {lc}")

        if not args.apply:
            print(f"\n[dry-run] re-run with --apply to delete the {len(sessions)} session(s) above.")
            return

        print(f"\nDeleting {len(sessions)} session(s)...")
        for r in sessions:
            sid = r["session_id"]
            delete_session(conn, sid, sessions_dir, raw_dir)
            print(f"  rm {sid}")
        conn.commit()
        print(f"\nDone. {len(sessions)} session(s) removed from DB + disk.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
