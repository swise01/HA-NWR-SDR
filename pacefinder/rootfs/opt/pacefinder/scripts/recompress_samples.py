#!/usr/bin/env python3
"""Compress legacy uncompressed samples_json blobs.

After PR #60 lap_samples and track_references store gzipped JSON. New writes
are always compressed; reads sniff the magic byte and fall back to legacy
JSON text. This script walks every row that's still in legacy format and
rewrites it as gzip — purely a storage optimization, no behavior change.

Idempotent: skips rows that are already gzipped.

Usage:
  python3 scripts/recompress_samples.py             # dry run
  python3 scripts/recompress_samples.py --apply     # actually rewrite
"""

import argparse
import gzip
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import storage_path  # noqa: E402

_GZIP_MAGIC = b"\x1f\x8b"


def is_gzip(raw) -> bool:
    if raw is None:
        return True  # nothing to do
    if isinstance(raw, str):
        return False
    if isinstance(raw, (bytes, bytearray, memoryview)):
        return bytes(raw)[:2] == _GZIP_MAGIC
    return True


def to_gzip(raw) -> bytes:
    """Encode an uncompressed payload as gzip. Accepts str (legacy text) or
    bytes-that-aren't-gzip (also legacy)."""
    if isinstance(raw, str):
        text = raw
    elif isinstance(raw, (bytes, bytearray, memoryview)):
        text = bytes(raw).decode("utf-8")
    else:
        raise TypeError(f"unexpected type: {type(raw).__name__}")
    return gzip.compress(text.encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true",
                        help="actually rewrite (default is dry-run)")
    args = parser.parse_args()

    sp = storage_path()
    db_path = sp / "simtelemetry.db"
    if not db_path.exists():
        print(f"No database at {db_path} — nothing to do.", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        # ── lap_samples ──────────────────────────────────────────────────────
        rows = conn.execute(
            "SELECT session_id, lap_number, samples_json, distance_m_json "
            "FROM lap_samples"
        ).fetchall()
        legacy_lap = [(r["session_id"], r["lap_number"],
                       r["samples_json"], r["distance_m_json"])
                      for r in rows
                      if not is_gzip(r["samples_json"])
                         or not is_gzip(r["distance_m_json"])]
        print(f"lap_samples: {len(legacy_lap)} legacy row(s) of {len(rows)} total")

        # ── track_references ─────────────────────────────────────────────────
        ref_rows = conn.execute(
            "SELECT track, reference_type, samples_json FROM track_references"
        ).fetchall()
        legacy_ref = [(r["track"], r["reference_type"], r["samples_json"])
                      for r in ref_rows
                      if not is_gzip(r["samples_json"])]
        print(f"track_references: {len(legacy_ref)} legacy row(s) of {len(ref_rows)} total")

        if not legacy_lap and not legacy_ref:
            print("All rows already compressed. Nothing to do.")
            return

        if not args.apply:
            print("[dry-run] re-run with --apply to rewrite.")
            return

        for sid, lap_n, raw_s, raw_d in legacy_lap:
            conn.execute(
                "UPDATE lap_samples SET samples_json=?, distance_m_json=? "
                "WHERE session_id=? AND lap_number=?",
                (to_gzip(raw_s), to_gzip(raw_d), sid, lap_n),
            )
        for track, rtype, raw in legacy_ref:
            conn.execute(
                "UPDATE track_references SET samples_json=? "
                "WHERE track=? AND reference_type=?",
                (to_gzip(raw), track, rtype),
            )
        conn.commit()
        print(f"Rewrote {len(legacy_lap)} lap_samples row(s) "
              f"and {len(legacy_ref)} track_references row(s).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
