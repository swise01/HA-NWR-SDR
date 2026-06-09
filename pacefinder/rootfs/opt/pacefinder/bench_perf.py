#!/usr/bin/env python3
"""
bench_perf.py — back-end performance bench for Pacefinder.

Seeds a deterministic synthetic SQLite DB in a temp dir and times the
hot DB / JSON paths the audit flagged. Stdlib only; no Pi required.

Usage:
  python3 bench_perf.py               # run, print table
  python3 bench_perf.py --baseline    # save current numbers to bench_baseline.json
  python3 bench_perf.py --check       # compare against baseline; nonzero exit on regression
  python3 bench_perf.py --check --threshold 0.30  # tolerate up to +30% median drift
  python3 bench_perf.py --sessions 500 --tracks 25  # bigger synthetic dataset

The numbers are NOT Pi numbers — they're whatever the runner machine
delivers. The point is *relative* tracking: detect regressions in the
hot paths, and have ground-truth before/after data for optimisations.
See docs/specs/ ... and CONTRIBUTING (Testing) for when to run.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config
from db import store


# ── Fixture setup ─────────────────────────────────────────────────────────────

def _temp_store() -> str:
    tmp = tempfile.mkdtemp(prefix="pf_bench_")
    config.config["storage_path"] = tmp
    (Path(tmp) / "sessions").mkdir(parents=True, exist_ok=True)
    store.initialize([str(Path(tmp) / "bench.db")], config.storage_path,
                     {}, {}, logging.getLogger("pacefinder"))
    store._db_init()
    return tmp


# Mix designed to exercise tracks_index sub-queries (multiple sessions per
# track), needs-review predicate (some unknowns), real-race counters
# (race_type=real with finish_pos), and trend (≥3 best laps per track).
_TRACKS = [
    "Circuit de Spa-Francorchamps", "Suzuka Circuit East", "Maple Valley Full Circuit",
    "Mount Panorama Circuit", "Hockenheimring Full Circuit", "Nürburgring Nordschleife",
    "Circuit of the Americas", "Road America", "Sebring International Raceway",
    "Daytona Road Course", "Watkins Glen Long", "Laguna Seca",
    "Brands Hatch Indy", "Silverstone GP", "Monza Full Circuit",
]
_CARS = [
    (12345, "1997 Porsche 911 GT1 Strassenversion", 7, 996),
    (23456, "2023 Porsche 911 GT3 R",               6, 850),
    (34567, "2015 Radical RXC Turbo",                5, 730),
    (45678, "1998 BMW M3 E36",                       3, 612),
    (56789, "2018 Honda Civic Type R",               2, 510),
    (67890, "2017 Ford Focus RS",                    2, 488),
    (78901, "2020 Ferrari 488 GT3",                  6, 845),
    (89012, "1965 Shelby Cobra 427 S/C",             1, 401),
]
_RACE_TYPES = ["real", "real", "real", "ai", "ai", "time_trial", None]


def _seed(n_sessions: int, n_tracks: int, n_cars: int) -> None:
    """Insert n_sessions synthetic rows. Deterministic from (i)."""
    tracks = _TRACKS[:n_tracks]
    cars = _CARS[:n_cars]
    base = datetime(2025, 1, 1)
    for i in range(n_sessions):
        track = tracks[i % len(tracks)]
        car_ord, car_name, car_class, car_pi = cars[i % len(cars)]
        race_type = _RACE_TYPES[i % len(_RACE_TYPES)]
        # ~3s of best-lap drift per track over time so trend has signal.
        base_time = 60 + (i % len(tracks)) * 4.0
        best_lap = base_time + (i // len(tracks)) * 0.3 - (i % 7) * 0.2
        started = (base + timedelta(hours=i)).isoformat()
        is_race = race_type in ("real", "ai") and i % 3 == 0
        # Some rows intentionally lack track/car/finish to hit the
        # needs-review predicate (~1 in 9 sessions).
        bad = (i % 9 == 0)
        store._db_write_session({
            "session_id":   f"bench-{i:06d}",
            "game":         "forza_motorsport",
            "track":        None if bad else track,
            "car":          None if bad else car_name,
            "car_ordinal":  None if bad else car_ord,
            "car_class":    car_class, "car_pi": car_pi,
            "session_type": "race" if is_race else "practice",
            "race_type":    race_type,
            "started_at":   started,
            "ended_at":     started,
            "packet_count": 40000,
            "best_lap_time_s": round(best_lap, 3),
            "grid_pos":     (i % 24 + 1) if is_race and not bad else None,
            "finish_pos":   ((i * 7) % 24 + 1) if is_race and not bad else None,
            "weather_condition": ["Dry", "Damp", "Wet"][i % 3],
            "tyre_compound": ["Soft", "Medium", "Hard"][i % 3],
            "track_temp_c": 22.0,
            "closed_reason": "timeout",
            "laps": [{"lap_number": k, "lap_time_s": best_lap + k * 0.4,
                      "max_speed_mph": 180, "sample_count": 5000,
                      "avg_throttle": 70, "avg_brake": 12, "avg_slip": 0.03,
                      "peak_slip": 0.18, "slip_above_pct": 4.0}
                     for k in range(5)],
        })


# ── Bench ─────────────────────────────────────────────────────────────────────

def _time(fn, iters: int) -> list[float]:
    out = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1000)  # ms
    return out


def _stats(times: list[float]) -> tuple[float, float]:
    times_sorted = sorted(times)
    median = statistics.median(times_sorted)
    p95 = times_sorted[max(0, int(len(times_sorted) * 0.95) - 1)]
    return median, p95


def _bench(iters: int) -> dict:
    """Return {op: {median_ms, p95_ms, bytes?}}. Warm up briefly first."""
    since_iso = "2025-06-01T00:00:00"  # mid-range marker for new-since

    # Warmup (page cache / SQLite plan).
    for _ in range(3):
        store._db_tracks_index()
        store._db_sessions_list(2000)
        store._db_career_kpis()

    ops = {}

    times = _time(lambda: store._db_tracks_index(), iters)
    ops["db_tracks_index"] = {"median_ms": _stats(times)[0], "p95_ms": _stats(times)[1]}

    times = _time(lambda: store._db_sessions_list(2000), iters)
    med, p95 = _stats(times)
    payload = json.dumps(store._db_sessions_list(2000)).encode()
    ops["db_sessions_list(2000)"] = {"median_ms": med, "p95_ms": p95, "bytes": len(payload)}

    times = _time(lambda: store._db_career_kpis(), iters)
    ops["db_career_kpis"] = {"median_ms": _stats(times)[0], "p95_ms": _stats(times)[1]}

    times = _time(lambda: store._db_recent_sessions(8), iters)
    ops["db_recent_sessions(8)"] = {"median_ms": _stats(times)[0], "p95_ms": _stats(times)[1]}

    times = _time(lambda: store._db_needs_review_count(), iters)
    ops["db_needs_review_count"] = {"median_ms": _stats(times)[0], "p95_ms": _stats(times)[1]}

    times = _time(lambda: store._db_sessions_since_count(since_iso), iters)
    ops["db_sessions_since_count"] = {"median_ms": _stats(times)[0], "p95_ms": _stats(times)[1]}

    # /sessions/tracks payload (the heaviest JSON the listener emits today).
    tracks_payload = json.dumps(store._db_tracks_index()).encode()
    ops["db_tracks_index"]["bytes"] = len(tracks_payload)

    return ops


# ── Render / IO ──────────────────────────────────────────────────────────────

def _fmt_table(ops: dict, ref: dict | None) -> str:
    cols = ("op", "median", "p95", "bytes", "Δ median")
    widths = (32, 10, 10, 10, 11)
    out = ["  ".join(c.ljust(w) for c, w in zip(cols, widths))]
    out.append("  ".join("-" * w for w in widths))
    for name, v in ops.items():
        m = f"{v['median_ms']:.2f}ms"
        p = f"{v['p95_ms']:.2f}ms"
        b = f"{v['bytes']/1024:.1f}KB" if "bytes" in v else "—"
        delta = "—"
        if ref and name in ref:
            old = ref[name]["median_ms"]
            if old > 0:
                pct = (v["median_ms"] - old) / old * 100
                arrow = "↑" if pct > 0 else "↓" if pct < 0 else "·"
                delta = f"{arrow} {pct:+.1f}%"
        out.append("  ".join(s.ljust(w) for s, w in zip((name, m, p, b, delta), widths)))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters",     type=int, default=30)
    ap.add_argument("--sessions",  type=int, default=200)
    ap.add_argument("--tracks",    type=int, default=15)
    ap.add_argument("--cars",      type=int, default=8)
    ap.add_argument("--baseline",  action="store_true", help="save current as bench_baseline.json")
    ap.add_argument("--check",     action="store_true", help="compare against baseline; nonzero if regressed")
    ap.add_argument("--threshold", type=float, default=0.25, help="median regression budget (fraction)")
    ap.add_argument("--baseline-path", default=str(Path(__file__).parent / "bench_baseline.json"))
    args = ap.parse_args()

    tmp = _temp_store()
    try:
        print(f"seeding {args.sessions} sessions across {args.tracks} tracks × {args.cars} cars…")
        _seed(args.sessions, args.tracks, args.cars)
        print(f"running {args.iters} iterations…\n")
        ops = _bench(args.iters)

        ref = None
        bp = Path(args.baseline_path)
        if args.check and bp.exists():
            ref = json.loads(bp.read_text()).get("ops", {})

        print(_fmt_table(ops, ref))
        print()

        if args.baseline:
            bp.write_text(json.dumps({
                "ops": ops,
                "config": {"sessions": args.sessions, "tracks": args.tracks,
                           "cars": args.cars, "iters": args.iters},
            }, indent=2) + "\n")
            print(f"baseline saved → {bp}")
            return 0

        if args.check:
            if not ref:
                print("no baseline to check against. run with --baseline first.")
                return 2
            regressed = []
            for name, v in ops.items():
                old = ref.get(name, {}).get("median_ms")
                if old is None or old <= 0:
                    continue
                pct = (v["median_ms"] - old) / old
                if pct > args.threshold:
                    regressed.append((name, old, v["median_ms"], pct))
            if regressed:
                print(f"REGRESSIONS (>{args.threshold*100:.0f}% over baseline):")
                for n, o, c, p in regressed:
                    print(f"  {n}: {o:.2f}ms → {c:.2f}ms ({p*100:+.1f}%)")
                return 1
            print(f"all medians within +{args.threshold*100:.0f}% of baseline.")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
