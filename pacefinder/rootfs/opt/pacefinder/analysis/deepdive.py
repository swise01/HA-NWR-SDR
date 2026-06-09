"""Compute the Deep Dive tab payload from a session's stored lap_samples.

See docs/specs/deep-dive-tab.md. One entry point — `compute_deepdive` — that
returns the full JSON payload the endpoint serves. All inputs come from the
db lap_samples blobs (already downsampled at storage time to ~500 points
per lap), plus the session row from the sessions table.

No I/O, no DB calls in this module — pass in pre-fetched data.
"""
from __future__ import annotations

import math
from typing import Optional


# ─── helpers ──────────────────────────────────────────────────────────────────


def _safe(v, default=0.0):
    """None-safe float coercion."""
    return default if v is None else v


def _downsample(points: list, target: int) -> list:
    """Uniform-stride downsample preserving first + last."""
    if len(points) <= target:
        return points
    step = max(1, len(points) // target)
    out = points[::step]
    if out[-1] is not points[-1]:
        out.append(points[-1])
    return out


def _fmt_lap(s: Optional[float]) -> str:
    if s is None:
        return "—"
    m = int(s // 60)
    return f"{m}:{(s % 60):06.3f}"


# ─── panel: track-map + speed-trace + G-G points ──────────────────────────────


def _build_track_map(laps_with_samples: list) -> dict:
    """Returns {laps: [{lap_number, points: [[px, pz, distance_m, speed,
    throttle, brake, gear, slip], ...]}]}. Skipped silently per-lap when a
    lap has no position data (older sessions may have samples without px/pz).
    """
    out_laps = []
    for lap in laps_with_samples:
        samples = lap["samples"]
        dist_m = lap.get("distance_m") or []
        if not samples or not all("px" in s and "pz" in s for s in samples):
            continue
        if len(dist_m) != len(samples):
            # Length mismatch — fall back to index-based distance.
            dist_m = list(range(len(samples)))
        pts = []
        for i, s in enumerate(samples):
            slip = max(_safe(s.get("slip_rl")), _safe(s.get("slip_rr")),
                       _safe(s.get("slip_fl")), _safe(s.get("slip_fr")))
            pts.append([
                round(_safe(s.get("px")), 2),
                round(_safe(s.get("pz")), 2),
                round(_safe(dist_m[i]), 1),
                round(_safe(s.get("speed_mph")), 1),
                round(_safe(s.get("throttle_pct")), 1),
                round(_safe(s.get("brake_pct")), 1),
                int(_safe(s.get("gear"))),
                round(slip, 4),
            ])
        # Already-downsampled at storage; second pass to clamp to ~600 max.
        pts = _downsample(pts, 600)
        out_laps.append({
            "lap_number": lap["lap_number"],
            "points": pts,
        })
    return {"laps": out_laps}


def _build_gg(laps_with_samples: list) -> dict:
    """Scatter points (g_lon, g_lat, distance_m) per lap."""
    out_laps = []
    for lap in laps_with_samples:
        samples = lap["samples"]
        dist_m = lap.get("distance_m") or []
        if not samples:
            continue
        if len(dist_m) != len(samples):
            dist_m = list(range(len(samples)))
        pts = []
        for i, s in enumerate(samples):
            g_lon = s.get("g_lon")
            g_lat = s.get("g_lat")
            if g_lon is None or g_lat is None:
                continue
            pts.append([
                round(g_lon, 3),
                round(g_lat, 3),
                round(_safe(dist_m[i]), 1),
            ])
        if not pts:
            continue
        pts = _downsample(pts, 400)
        out_laps.append({
            "lap_number": lap["lap_number"],
            "points": pts,
        })
    return {"laps": out_laps}


def _build_speed_trace(laps_with_samples: list) -> dict:
    """Distance × speed trace per lap."""
    out_laps = []
    for lap in laps_with_samples:
        samples = lap["samples"]
        dist_m = lap.get("distance_m") or []
        if not samples:
            continue
        if len(dist_m) != len(samples):
            dist_m = list(range(len(samples)))
        pts = [
            [round(_safe(dist_m[i]), 1), round(_safe(s.get("speed_mph")), 1)]
            for i, s in enumerate(samples)
        ]
        pts = _downsample(pts, 400)
        out_laps.append({
            "lap_number": lap["lap_number"],
            "points": pts,
        })
    return {"laps": out_laps}


# ─── panel: events ────────────────────────────────────────────────────────────


def _detect_events(lap: dict) -> list:
    """Heuristic event detection on a single lap's samples. Severity loosely
    scaled so the worst events bubble up first. See spec for thresholds."""
    samples = lap["samples"]
    dist_m = lap.get("distance_m") or list(range(len(samples)))
    events = []
    if len(dist_m) != len(samples):
        dist_m = list(range(len(samples)))

    # Walk samples once, track per-detector windows.
    spin_start = None
    spin_peak = 0.0
    rumble_start = None
    rumble_streak_dist = 0.0
    lockup_start = None
    lockup_peak_brake = 0.0
    last_gear = None
    last_rpm = None

    for i, s in enumerate(samples):
        # Spin / big slide — peak rear combined slip > 1.5 OR rear slip > 0.6
        # with throttle > 50%. Both conditions promote to spin if sustained.
        rear_cs = max(_safe(s.get("cs_rl")), _safe(s.get("cs_rr")))
        rear_slip = max(_safe(s.get("slip_rl")), _safe(s.get("slip_rr")))
        thr = _safe(s.get("throttle_pct"))
        is_spin_frame = (rear_cs > 1.5) or (rear_slip > 0.6 and thr > 50)
        if is_spin_frame:
            if spin_start is None:
                spin_start = i
                spin_peak = max(rear_cs, rear_slip)
            else:
                spin_peak = max(spin_peak, rear_cs, rear_slip)
        else:
            if spin_start is not None and (i - spin_start) >= 3:
                events.append({
                    "lap_number": lap["lap_number"],
                    "distance_m": round(dist_m[spin_start], 1),
                    "kind":   "spin",
                    "label":  "Big slide",
                    "detail": f"rear slip {spin_peak:.2f} for {(i - spin_start)} samples",
                    "severity": round(spin_peak * (i - spin_start), 2),
                })
            spin_start = None
            spin_peak = 0.0

        # Off-track — rumble strip on outside tyres for >0.5s. Approximate
        # via cumulative distance covered while any rumble flag is on.
        rumble = any(_safe(s.get(f"rumble_{c}")) > 0 for c in ("fl", "fr", "rl", "rr"))
        if rumble:
            if rumble_start is None:
                rumble_start = i
            if i + 1 < len(dist_m):
                rumble_streak_dist += abs(dist_m[i + 1] - dist_m[i])
        else:
            if rumble_start is not None and rumble_streak_dist > 25:
                events.append({
                    "lap_number": lap["lap_number"],
                    "distance_m": round(dist_m[rumble_start], 1),
                    "kind":   "off_track",
                    "label":  "Off-track",
                    "detail": f"rumble {rumble_streak_dist:.0f}m",
                    "severity": round(rumble_streak_dist, 1),
                })
            rumble_start = None
            rumble_streak_dist = 0.0

        # Lockup — brake > 70% and any wheel rotation speed << car forward
        # speed. We don't have the raw forward speed in m/s in the sample
        # (speed_mph is mph), but wsp_* is in rad/s. Approximate: if brake
        # is high and the minimum wsp is < 20% of the maximum, that's a wheel
        # locked or close to it.
        brk = _safe(s.get("brake_pct"))
        wsps = [_safe(s.get(f"wsp_{c}")) for c in ("fl", "fr", "rl", "rr")
                if s.get(f"wsp_{c}") is not None]
        if brk > 70 and len(wsps) == 4 and max(wsps) > 5 and min(wsps) < 0.2 * max(wsps):
            if lockup_start is None:
                lockup_start = i
                lockup_peak_brake = brk
            else:
                lockup_peak_brake = max(lockup_peak_brake, brk)
        else:
            if lockup_start is not None and (i - lockup_start) >= 6:
                events.append({
                    "lap_number": lap["lap_number"],
                    "distance_m": round(dist_m[lockup_start], 1),
                    "kind":   "lockup",
                    "label":  "Wheel lockup",
                    "detail": f"brake {lockup_peak_brake:.0f}%",
                    "severity": round(lockup_peak_brake / 10, 1),
                })
            lockup_start = None
            lockup_peak_brake = 0.0

        # Bad shift — RPM jumped 2000+ in the wrong direction at a gear change.
        gear = s.get("gear")
        rpm = _safe(s.get("rpm"))
        if last_gear is not None and gear is not None and gear != last_gear and last_rpm:
            d_rpm = rpm - last_rpm
            # Upshift should drop RPM; if it rose >2000 something's wrong.
            if gear > last_gear and d_rpm > 2000:
                events.append({
                    "lap_number": lap["lap_number"],
                    "distance_m": round(dist_m[i], 1),
                    "kind":   "bad_shift",
                    "label":  "Bad upshift",
                    "detail": f"L{last_gear}→L{gear}, RPM +{d_rpm:.0f}",
                    "severity": round(d_rpm / 1000, 1),
                })
            elif gear < last_gear and d_rpm < -2000:
                events.append({
                    "lap_number": lap["lap_number"],
                    "distance_m": round(dist_m[i], 1),
                    "kind":   "bad_shift",
                    "label":  "Bad downshift",
                    "detail": f"L{last_gear}→L{gear}, RPM {d_rpm:.0f}",
                    "severity": round(abs(d_rpm) / 1000, 1),
                })
        last_gear = gear
        last_rpm = rpm

    return events


def _events_for_session(laps_with_samples: list) -> list:
    """Aggregate detected events across all laps, severity-sorted, capped."""
    all_events: list = []
    for lap in laps_with_samples:
        all_events.extend(_detect_events(lap))
    all_events.sort(key=lambda e: e["severity"], reverse=True)
    return all_events[:20]   # cap; frontend hides past 10 with "+N more"


# ─── panel: lap comparison ────────────────────────────────────────────────────


def _interp(timeline: list, target_d: float) -> Optional[float]:
    """Same logic as session.manager._interp_dist_to_t — duplicated here so
    this module stays import-cycle-free."""
    if not timeline:
        return None
    if target_d <= timeline[0][0]:
        return timeline[0][1]
    if target_d >= timeline[-1][0]:
        return timeline[-1][1]
    lo, hi = 0, len(timeline) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if timeline[mid][0] < target_d:
            lo = mid + 1
        else:
            hi = mid
    d1, t1 = timeline[lo]
    d0, t0 = timeline[lo - 1]
    if d1 == d0:
        return t1
    f = (target_d - d0) / (d1 - d0)
    return t0 + f * (t1 - t0)


def _build_lap_comparison(laps_with_samples: list, ref_lap: int, cmp_lap: int) -> Optional[dict]:
    """Distance-aligned delta between two laps. Returns {reference_lap,
    compare_lap, total_delta_s, segments, top_lost, top_gained}."""
    ref = next((l for l in laps_with_samples if l["lap_number"] == ref_lap), None)
    cmp_ = next((l for l in laps_with_samples if l["lap_number"] == cmp_lap), None)
    if not ref or not cmp_ or not ref["samples"] or not cmp_["samples"]:
        return None
    ref_dist = ref.get("distance_m") or []
    cmp_dist = cmp_.get("distance_m") or []
    if len(ref_dist) != len(ref["samples"]) or len(cmp_dist) != len(cmp_["samples"]):
        return None

    ref_timeline = [(d, s.get("t", 0)) for d, s in zip(ref_dist, ref["samples"])]
    cmp_timeline = [(d, s.get("t", 0)) for d, s in zip(cmp_dist, cmp_["samples"])]
    total_dist = max(ref_dist[-1], cmp_dist[-1])
    if total_dist <= 0:
        return None

    # Sample 100 m windows.
    bin_size = 100.0
    n_bins = max(1, int(total_dist / bin_size))
    segments = []
    for i in range(n_bins):
        d = (i + 0.5) * bin_size
        ref_t = _interp(ref_timeline, d)
        cmp_t = _interp(cmp_timeline, d)
        if ref_t is None or cmp_t is None:
            continue
        # Per-segment delta: change in delta across this 100 m window.
        ref_t_end = _interp(ref_timeline, d + bin_size / 2) or ref_t
        ref_t_start = _interp(ref_timeline, d - bin_size / 2) or ref_t
        cmp_t_end = _interp(cmp_timeline, d + bin_size / 2) or cmp_t
        cmp_t_start = _interp(cmp_timeline, d - bin_size / 2) or cmp_t
        seg_delta = (cmp_t_end - cmp_t_start) - (ref_t_end - ref_t_start)
        segments.append({
            "start_m": round(d - bin_size / 2, 1),
            "end_m":   round(d + bin_size / 2, 1),
            "delta_s": round(seg_delta, 3),
        })

    # Total delta: last sampled time difference.
    total_delta = round(cmp_timeline[-1][1] - ref_timeline[-1][1], 3)
    sorted_loss = sorted(segments, key=lambda s: s["delta_s"], reverse=True)
    sorted_gain = sorted(segments, key=lambda s: s["delta_s"])
    return {
        "reference_lap": ref_lap,
        "compare_lap":   cmp_lap,
        "total_delta_s": total_delta,
        "segments":      segments,
        "top_lost":      [s for s in sorted_loss[:3] if s["delta_s"] > 0.01],
        "top_gained":    [s for s in sorted_gain[:3] if s["delta_s"] < -0.01],
    }


# ─── panel: headline strip ────────────────────────────────────────────────────


def _build_headline(sess: dict, laps: list, laps_with_samples: list) -> list:
    """Up to 5 single-line stats, skipped silently when null. `laps` is the
    sessions/<id>/laps list (per-lap aggregates from the laps table)."""
    out = []
    best = sess.get("best_lap_time_s")
    best_lap_n = next((l["lap_number"] for l in laps
                       if l.get("lap_time_s") and abs(l["lap_time_s"] - best) < 0.001),
                      None) if best else None
    if best:
        suffix = f" (L{best_lap_n + 1})" if best_lap_n is not None else ""
        out.append({"label": "Best", "value": _fmt_lap(best) + suffix})

    # Top speed across stored samples.
    top = 0.0
    for lap in laps_with_samples:
        for s in lap["samples"]:
            v = _safe(s.get("speed_mph"))
            if v > top:
                top = v
    if top > 0:
        out.append({"label": "Top", "value": f"{top:.1f} mph"})

    # Lap-time spread among valid laps.
    times = [l["lap_time_s"] for l in laps if l.get("lap_time_s")]
    if len(times) >= 2:
        spread = max(times) - min(times)
        out.append({"label": "Spread", "value": f"{spread:.2f} s"})

    # Race outcome (race-type sessions only).
    grid = sess.get("grid_pos")
    finish = sess.get("finish_pos")
    if grid and finish:
        gain = grid - finish
        sign = "+" if gain > 0 else ""
        out.append({"label": "Race", "value": f"P{grid} → P{finish} ({sign}{gain})"})

    # Throttle %, session-wide.
    total_n = 0
    thr_open = 0
    for lap in laps_with_samples:
        for s in lap["samples"]:
            total_n += 1
            if _safe(s.get("throttle_pct")) > 95:
                thr_open += 1
    if total_n > 0:
        pct = 100 * thr_open / total_n
        out.append({"label": "Full thr", "value": f"{pct:.1f}%"})

    return out[:5]


# ─── entry point ──────────────────────────────────────────────────────────────


def compute_deepdive(sess: dict, laps: list, laps_with_samples: list,
                     ref_lap: Optional[int] = None,
                     cmp_lap: Optional[int] = None) -> dict:
    """Build the full Deep Dive payload.

    Args:
        sess: row from the sessions table (dict).
        laps: list of lap rows (per-lap aggregates from the laps table).
        laps_with_samples: list of {lap_number, samples, distance_m} as
            returned by db._db_get_all_lap_samples.
        ref_lap: lap_number to use as Lap Comparison reference (defaults to
            session-best lap).
        cmp_lap: lap_number to compare against (defaults to next valid lap).
    """
    # Default ref/cmp picks: session best as reference, next valid lap as cmp.
    if ref_lap is None and laps_with_samples:
        best_n = None
        best_t = None
        for lap in laps:
            t = lap.get("lap_time_s")
            if t and (best_t is None or t < best_t):
                best_t = t
                best_n = lap["lap_number"]
        ref_lap = best_n if best_n is not None else laps_with_samples[0]["lap_number"]
    if cmp_lap is None and ref_lap is not None:
        # Pick next lap_number that has stored samples and isn't the ref.
        avail = [l["lap_number"] for l in laps_with_samples if l["lap_number"] != ref_lap]
        # Prefer the lap immediately after ref; otherwise any other.
        next_higher = sorted([n for n in avail if n > ref_lap])
        cmp_lap = next_higher[0] if next_higher else (avail[0] if avail else None)

    track_map = _build_track_map(laps_with_samples)
    return {
        "headline": _build_headline(sess, laps, laps_with_samples),
        "track_map_available": bool(track_map["laps"]),
        "track_map": track_map,
        "gg":          _build_gg(laps_with_samples),
        "speed_trace": _build_speed_trace(laps_with_samples),
        "events":      _events_for_session(laps_with_samples),
        "lap_comparison": (
            _build_lap_comparison(laps_with_samples, ref_lap, cmp_lap)
            if (ref_lap is not None and cmp_lap is not None) else None
        ),
        "lap_numbers": [l["lap_number"] for l in laps_with_samples],
    }
