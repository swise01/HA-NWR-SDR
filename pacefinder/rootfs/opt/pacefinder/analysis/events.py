"""
Mistakes & Events detector — heuristics for driver-event detection.

Runs against the per-lap sample stream stored in lap_samples and writes
detected events to the lap_events table. Called at session close as part
of update_track_references(), and from scripts/backfill_lap_events.py
for retroactive runs.

Three v1 detectors (conservative; favour false negatives over false
positives so the Card A insights stay credible):

  1. lockup            — heavy braking + front-wheel slip spike
  2. power_oversteer   — high throttle + rear-wheel slip spike at speed
  3. bad_shift         — downshift that immediately drives RPM over redline

Thresholds are intentionally cautious and live in EVENT_THRESHOLDS so
they're tunable without code edits once we see what the user's actual
sessions surface.

Events that fire within MIN_GAP_M of a same-type event on the same lap
are coalesced — a sustained 1-second mistake shouldn't produce ten
duplicate rows.
"""
from __future__ import annotations

from typing import Optional

# Tunable thresholds. Each detector reads from here so the values can
# be lifted into config later without touching detector logic.
EVENT_THRESHOLDS = {
    "lockup": {
        "brake_min":   85.0,   # %
        "slip_min":     0.30,  # front-wheel slip ratio
        "min_speed":   30.0,   # mph; below this even a momentary slip is noise
    },
    "power_oversteer": {
        "throttle_min": 70.0,  # %
        "slip_min":      0.30, # rear-wheel slip ratio
        "min_speed":    50.0,  # mph
    },
    "bad_shift": {
        "rpm_redline_frac": 0.98,  # 98% of engine_max_rpm = over
    },
}

# Minimum distance between two same-type events before they're treated
# as separate occurrences. 80 m at lap-typical speeds is ~2 sec.
MIN_GAP_M = 80.0


def detect_lap_events(samples: list, distance_m: list, engine_max_rpm: Optional[float]) -> list:
    """
    Walk a single lap's normalised samples and emit detected events.

    Each event is a dict:
        {
            "event_type":     "lockup" | "power_oversteer" | "bad_shift",
            "distance_m":     float,   # cumulative metres along the lap
            "distance_norm":  float,   # 0.0–1.0
            "severity":       float,   # 0.0–1.0
            "description":    str,     # short human label
        }
    """
    if not samples or not distance_m:
        return []

    events: list = []

    # ── Detector 1: lockup ──────────────────────────────────────────
    t_lock = EVENT_THRESHOLDS["lockup"]
    last_lockup_m = -1e9
    for i, s in enumerate(samples):
        brake = float(s.get("brake_pct") or 0)
        speed = float(s.get("speed_mph") or 0)
        if brake < t_lock["brake_min"] or speed < t_lock["min_speed"]:
            continue
        slip_f = max(float(s.get("slip_fl") or 0), float(s.get("slip_fr") or 0))
        if slip_f < t_lock["slip_min"]:
            continue
        d_m = float(distance_m[i] if i < len(distance_m) else 0)
        if d_m - last_lockup_m < MIN_GAP_M:
            continue
        sev = min(1.0, (brake / 100.0) * (slip_f / 0.6))
        events.append({
            "event_type": "lockup",
            "distance_m": round(d_m, 1),
            "distance_norm": float(s.get("distance_norm") or 0),
            "severity": round(sev, 3),
            "description": "lockup under braking",
        })
        last_lockup_m = d_m

    # ── Detector 2: power oversteer ─────────────────────────────────
    t_os = EVENT_THRESHOLDS["power_oversteer"]
    last_os_m = -1e9
    for i, s in enumerate(samples):
        thr = float(s.get("throttle_pct") or 0)
        speed = float(s.get("speed_mph") or 0)
        if thr < t_os["throttle_min"] or speed < t_os["min_speed"]:
            continue
        slip_r = max(float(s.get("slip_rl") or 0), float(s.get("slip_rr") or 0))
        if slip_r < t_os["slip_min"]:
            continue
        d_m = float(distance_m[i] if i < len(distance_m) else 0)
        if d_m - last_os_m < MIN_GAP_M:
            continue
        sev = min(1.0, (thr / 100.0) * (slip_r / 0.6))
        events.append({
            "event_type": "power_oversteer",
            "distance_m": round(d_m, 1),
            "distance_norm": float(s.get("distance_norm") or 0),
            "severity": round(sev, 3),
            "description": "rear stepping out on power",
        })
        last_os_m = d_m

    # ── Detector 3: bad shift ───────────────────────────────────────
    # A downshift whose new RPM crosses the redline threshold = wrong gear
    # for the speed (engine over-revs).
    if engine_max_rpm and engine_max_rpm > 0:
        t_bs = EVENT_THRESHOLDS["bad_shift"]
        redline = engine_max_rpm * t_bs["rpm_redline_frac"]
        last_bs_m = -1e9
        prev_gear = None
        for i, s in enumerate(samples):
            g = s.get("gear")
            rpm = float(s.get("rpm") or 0)
            if g is None:
                continue
            if prev_gear is not None and g < prev_gear and g >= 1 and rpm >= redline:
                d_m = float(distance_m[i] if i < len(distance_m) else 0)
                if d_m - last_bs_m >= MIN_GAP_M:
                    sev = min(1.0, (rpm - redline) / (engine_max_rpm - redline + 1e-3))
                    events.append({
                        "event_type": "bad_shift",
                        "distance_m": round(d_m, 1),
                        "distance_norm": float(s.get("distance_norm") or 0),
                        "severity": round(sev, 3),
                        "description": f"downshift to {int(g)} pushed RPM over redline",
                    })
                    last_bs_m = d_m
            prev_gear = g

    return events


def detect_session_events(samples_by_lap: dict, engine_max_rpm: Optional[float]) -> dict:
    """
    Run detect_lap_events for every lap in a session.

    Args:
        samples_by_lap: {lap_number: {"samples": [...], "distance_m": [...]}}
        engine_max_rpm: from session metadata (Forza UDP)

    Returns: {lap_number: [event, event, ...]}
    """
    result: dict = {}
    for lap_n, data in samples_by_lap.items():
        if not data:
            continue
        result[lap_n] = detect_lap_events(
            data.get("samples") or [],
            data.get("distance_m") or [],
            engine_max_rpm,
        )
    return result
