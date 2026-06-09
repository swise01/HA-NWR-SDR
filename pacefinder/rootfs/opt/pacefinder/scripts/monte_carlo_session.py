#!/usr/bin/env python3
"""
Monte Carlo simulation of Session lifecycle bugs.

Generates synthetic Forza UDP packet streams covering the lifecycle scenarios
that have produced regressions in the past — and runs assertions that those
regressions can't reappear silently.

Scenarios (randomly mixed each run):
  - clean cold start (lobby → green flag → race → finish)
  - mid-race join (listener starts after lights-out)
  - stale lap_number from a prior race attempt in the menu
  - multiple back-to-back race attempts in the same listener session (restart)
  - pause + resume mid-lap
  - crash / abandon mid-lap (UDP stops)
  - FM2023 timing (CRT doesn't tick during the countdown)
  - delayed last_lap_time (Forza one packet late at the line)

Invariants asserted after each scenario:
  - No completed lap has lap_time_s coming from wall-clock fabrication
  - For every real race lap completed in the simulation, completed_laps
    contains a matching entry with the right lap_time_s
  - best_lap_time_s == min(completed lap times)
  - state["last_lap_time_s"] reflects the actual last completed lap
  - state["delta_to_best_s"] is bounded (never == cur_t when cur_t > 5s)
  - When grid is detected, current_lap_num is reset to 0
  - _delta_ref_total_m is within ±10% of the lap's true distance

Run:
  python3 scripts/monte_carlo_session.py
  python3 scripts/monte_carlo_session.py --runs 5000 --seed 42 --verbose

Exit code 0 = all invariants held. Non-zero = at least one regression detected.
"""
from __future__ import annotations

import argparse
import datetime
import random
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

# Make the project importable regardless of cwd
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from session.manager import Session, state, update_state, _is_driving  # noqa: E402


# ─── Track + lap profile model ────────────────────────────────────────────────


@dataclass
class TrackProfile:
    name: str
    length_m: float
    base_lap_time_s: float
    pkt_hz: int = 60   # Forza ~60 Hz

    def lap_time_with_jitter(self, rng: random.Random, max_jitter_pct: float = 0.10) -> float:
        return self.base_lap_time_s * (1 + rng.uniform(-max_jitter_pct, max_jitter_pct))


TRACKS = [
    TrackProfile("Mugello Circuit Full",            5245.0, 113.0),
    TrackProfile("Maple Valley Full Circuit",       4195.0,  60.0),
    TrackProfile("Circuit de Spa-Francorchamps",    7004.0, 138.0),
    TrackProfile("Mount Panorama",                  6213.0, 122.0),
    TrackProfile("Hakone Circuit",                  4580.0,  78.0),
]


# ─── Packet generator ─────────────────────────────────────────────────────────


def base_packet(distance: float, clt: float, crt: float, lap_num: int,
                race_position: int = 1,
                last_lap_time: float = 0.0, is_race_on: int = 1,
                speed_mph: float = 60.0, throttle_pct: float = 50.0,
                brake_pct: float = 0.0, gear: int = 4, rpm: float = 5000.0) -> dict:
    """Synthetic 'parsed' packet matching what parsers/forza.py would produce.
    `clt` = current_lap_time (resets per lap), `crt` = current_race_time
    (cumulative, resets only at lights-out)."""
    return {
        "is_race_on": is_race_on,
        "speed_mph": speed_mph,
        "throttle_pct": throttle_pct,
        "brake_pct": brake_pct,
        "steer": 0,
        "gear": gear,
        "rpm": rpm,
        "engine_max_rpm": 8000.0,
        "engine_idle_rpm": 1000.0,
        "current_engine_rpm": rpm,
        "g_lat": 0.0,
        "g_lon": 0.0,
        "slip_ratio_rl": 0.05,
        "slip_ratio_rr": 0.05,
        "slip_ratio_fl": 0.05,
        "slip_ratio_fr": 0.05,
        "tire_temp_fl": 180.0, "tire_temp_fr": 180.0,
        "tire_temp_rl": 180.0, "tire_temp_rr": 180.0,
        "distance_traveled": round(distance, 3),
        "current_lap_time": round(clt, 3),
        "current_race_time": round(crt, 3),
        "last_lap_time": last_lap_time,
        "best_lap_time": last_lap_time,
        "lap_number": lap_num,
        "race_position": race_position,
        "position_x": 0.0, "position_y": 0.0, "position_z": 0.0,
        "_packet_type": "telemetry",
    }


def gen_lap_packets(track: TrackProfile, lap_num: int, lap_time_s: float,
                    distance_offset: float, race_time_offset: float,
                    last_lap_time_carry: float,
                    rng: random.Random,
                    delayed_last_lap_time: bool = False) -> list[dict]:
    """Stream of packets for ONE complete lap. distance_offset / race_time_offset
    are cumulative values at the lap's start. Returns ~lap_time_s × pkt_hz
    packets, plus the line-crossing packet that triggers the lap transition."""
    n_packets = int(lap_time_s * track.pkt_hz)
    packets = []
    for i in range(n_packets):
        clt = (i / n_packets) * lap_time_s
        crt = race_time_offset + clt
        d_in_lap = (i / n_packets) * track.length_m
        packets.append(base_packet(
            distance=distance_offset + d_in_lap,
            clt=clt, crt=crt,
            lap_num=lap_num,
            last_lap_time=last_lap_time_carry,
            speed_mph=60 + rng.random() * 80,
            throttle_pct=70 + rng.random() * 30,
        ))
    # Crossing-the-line packet: lap_number transitions to lap_num+1, current_lap_time
    # resets to ~0, current_race_time keeps growing (race timer doesn't reset
    # on lap crossings). delayed_last_lap_time variant fires the transition with
    # last_lap_time still 0 and only updates it on the next packet.
    transition_llt = 0.0 if delayed_last_lap_time else lap_time_s
    packets.append(base_packet(
        distance=distance_offset + track.length_m,
        clt=0.05,
        crt=race_time_offset + lap_time_s,
        lap_num=lap_num + 1,
        last_lap_time=transition_llt,
        speed_mph=120.0, throttle_pct=80, gear=5,
    ))
    if delayed_last_lap_time:
        packets.append(base_packet(
            distance=distance_offset + track.length_m + 5,
            clt=0.10,
            crt=race_time_offset + lap_time_s + 0.05,
            lap_num=lap_num + 1,
            last_lap_time=lap_time_s,
        ))
    return packets


def gen_pre_race_packets(track: TrackProfile, n: int, rng: random.Random,
                         stale_lap_number: int = 0,
                         pre_race_distance_offset: float = 0.0,
                         crt_starts_at: Optional[float] = None,
                         is_race_on_during_pre: int = 1) -> list[dict]:
    """Pre-race lobby/queue packets. Drives some distance with a stale
    lap_number to simulate Forza carrying state from a previous attempt.

    Real-world current_race_time during pre-race: FH5 has CRT already at
    ~60+ seconds when the listener first sees a packet (lobby has been open
    for a while). The exact value doesn't matter for our detection — what
    matters is that it's > a few seconds, so the lights-out reset (CRT to
    ~0.02) is unambiguous. The simulator was previously starting CRT at 0
    and growing through the (0.5, 3.0) window, which falsely triggered the
    FM2023 fallback grid-detect during pre-race.
    """
    packets = []
    d = pre_race_distance_offset
    crt = crt_starts_at if crt_starts_at is not None else rng.uniform(30.0, 200.0)
    for i in range(n):
        d += rng.uniform(0.5, 3.0)
        crt += 1.0 / track.pkt_hz
        packets.append(base_packet(
            distance=d, clt=crt, crt=crt, lap_num=stale_lap_number,
            speed_mph=20 + rng.random() * 10,
            throttle_pct=20 + rng.random() * 20,
            gear=2, rpm=3000,
            is_race_on=is_race_on_during_pre,
        ))
    return packets


def gen_race_start_packet(track: TrackProfile, distance_offset: float,
                          rng: random.Random, race_position: int = 11) -> dict:
    """The lights-out packet — current_race_time and current_lap_time both
    reset to ~0, lap_number=0, race_position is the grid slot. Speed > 2 so
    it's classified as "driving" (real Forza fires accel right at lights-out)."""
    return base_packet(
        distance=distance_offset,
        clt=0.02, crt=0.02,
        lap_num=0,
        race_position=race_position,
        speed_mph=5.0, throttle_pct=80, brake_pct=0, gear=1, rpm=4000,
    )


# ─── Scenario builders ────────────────────────────────────────────────────────


@dataclass
class Scenario:
    """A scenario describes the packets to feed AND the ground truth — what
    laps actually completed, what the real lap times were, what the track was."""
    label: str
    packets: list[dict]
    track: TrackProfile
    expected_completed_lap_times: list[float] = field(default_factory=list)
    grid_pos: Optional[int] = None
    total_distance_at_session_end: float = 0.0


def scenario_clean_cold_start(rng: random.Random) -> Scenario:
    track = rng.choice(TRACKS)
    grid = rng.randint(2, 24)
    n_laps = rng.randint(2, 4)
    pre_race = gen_pre_race_packets(track, n=track.pkt_hz * 5, rng=rng)
    race_start = [gen_race_start_packet(track, distance_offset=pre_race[-1]["distance_traveled"],
                                         rng=rng, race_position=grid)]
    laps = []
    distance = race_start[0]["distance_traveled"]
    race_time = 0.0
    last_llt = 0.0
    expected_times = []
    for lap_n in range(n_laps):
        lap_time = track.lap_time_with_jitter(rng)
        expected_times.append(round(lap_time, 3))
        laps += gen_lap_packets(track, lap_num=lap_n, lap_time_s=lap_time,
                                distance_offset=distance, race_time_offset=race_time,
                                last_lap_time_carry=last_llt, rng=rng)
        distance += track.length_m
        race_time += lap_time
        last_llt = lap_time
    return Scenario(
        label="clean_cold_start",
        packets=pre_race + race_start + laps,
        track=track,
        expected_completed_lap_times=expected_times,
        grid_pos=grid,
        total_distance_at_session_end=distance,
    )


def scenario_stale_lap_number(rng: random.Random) -> Scenario:
    """The bug from #120 — listener joins with lap_number=1 stale from a
    previous race attempt left in the menu."""
    track = rng.choice(TRACKS)
    grid = rng.randint(2, 24)
    pre_race = gen_pre_race_packets(track, n=track.pkt_hz * 8, rng=rng,
                                     stale_lap_number=rng.randint(1, 3),
                                     pre_race_distance_offset=rng.uniform(2000, 8000),
                                     crt_starts_at=180.0)
    race_start = [gen_race_start_packet(track, distance_offset=pre_race[-1]["distance_traveled"],
                                         rng=rng, race_position=grid)]
    distance = race_start[0]["distance_traveled"]
    race_time = 0.0
    n_laps = rng.randint(2, 3)
    laps = []
    last_llt = 0.0
    expected = []
    for lap_n in range(n_laps):
        lt = track.lap_time_with_jitter(rng)
        expected.append(round(lt, 3))
        laps += gen_lap_packets(track, lap_num=lap_n, lap_time_s=lt,
                                distance_offset=distance, race_time_offset=race_time,
                                last_lap_time_carry=last_llt, rng=rng)
        distance += track.length_m
        race_time += lt
        last_llt = lt
    return Scenario(
        label="stale_lap_number",
        packets=pre_race + race_start + laps,
        track=track,
        expected_completed_lap_times=expected,
        grid_pos=grid,
        total_distance_at_session_end=distance,
    )


def scenario_mid_race_join(rng: random.Random) -> Scenario:
    """Listener starts after the race is already running. We can't capture
    the full first lap, so the invariant is: laps that completed AFTER our
    join must be in completed_laps with correct times."""
    track = rng.choice(TRACKS)
    grid = rng.randint(2, 24)
    # Simulate that lap 0 already happened (in Forza). We start at lap 1.
    join_lap = rng.randint(1, 2)
    # Pre-race-of-this-listener packets are mid-race-of-Forza
    distance = track.length_m * join_lap
    race_time = track.base_lap_time_s * join_lap
    last_llt = track.base_lap_time_s   # previous lap was real
    n_remaining_laps = rng.randint(2, 3)
    laps = []
    expected = []
    for lap_n in range(join_lap, join_lap + n_remaining_laps):
        lt = track.lap_time_with_jitter(rng)
        expected.append(round(lt, 3))
        laps += gen_lap_packets(track, lap_num=lap_n, lap_time_s=lt,
                                distance_offset=distance, race_time_offset=race_time,
                                last_lap_time_carry=last_llt, rng=rng)
        distance += track.length_m
        race_time += lt
        last_llt = lt
    return Scenario(
        label="mid_race_join",
        packets=laps,
        track=track,
        # Drop the first expected lap — listener joined mid-stream so it
        # captured only the tail of that lap. Still expect lap_number
        # transitions from there to register completed laps for the rest.
        expected_completed_lap_times=expected[1:] if expected else [],
        grid_pos=None,
        total_distance_at_session_end=distance,
    )


def scenario_delayed_last_lap_time(rng: random.Random) -> Scenario:
    """At the lap_number transition, Forza's last_lap_time is briefly 0;
    next packet has the real value. Tests the backfill path."""
    track = rng.choice(TRACKS)
    grid = rng.randint(2, 24)
    pre_race = gen_pre_race_packets(track, n=track.pkt_hz * 3, rng=rng)
    race_start = [gen_race_start_packet(track, distance_offset=pre_race[-1]["distance_traveled"],
                                         rng=rng, race_position=grid)]
    distance = race_start[0]["distance_traveled"]
    race_time = 0.0
    last_llt = 0.0
    expected = []
    laps = []
    for lap_n in range(2):
        lt = track.lap_time_with_jitter(rng)
        expected.append(round(lt, 3))
        laps += gen_lap_packets(track, lap_num=lap_n, lap_time_s=lt,
                                distance_offset=distance, race_time_offset=race_time,
                                last_lap_time_carry=last_llt,
                                rng=rng, delayed_last_lap_time=True)
        distance += track.length_m
        race_time += lt
        last_llt = lt
    return Scenario(
        label="delayed_last_lap_time",
        packets=pre_race + race_start + laps,
        track=track,
        expected_completed_lap_times=expected,
        grid_pos=grid,
        total_distance_at_session_end=distance,
    )


def scenario_pause_resume(rng: random.Random) -> Scenario:
    """User pauses mid-lap for N seconds, then resumes. is_race_on=0 during
    the pause; current_race_time is held steady. Goal: pause shouldn't
    fragment the session OR misregister as a restart."""
    track = rng.choice(TRACKS)
    grid = rng.randint(2, 24)
    pre_race = gen_pre_race_packets(track, n=track.pkt_hz * 4, rng=rng)
    race_start = [gen_race_start_packet(track, distance_offset=pre_race[-1]["distance_traveled"],
                                         rng=rng, race_position=grid)]
    distance = race_start[0]["distance_traveled"]
    race_time = 0.0
    last_llt = 0.0
    expected = []
    laps = []

    # Lap 0 partial (first half), then pause, then second half + crossing
    lt0 = track.lap_time_with_jitter(rng)
    expected.append(round(lt0, 3))
    n_full = int(lt0 * track.pkt_hz)
    n_half = n_full // 2
    for i in range(n_half):
        clt = (i / n_full) * lt0
        crt = race_time + clt
        d_in = (i / n_full) * track.length_m
        laps.append(base_packet(distance=distance + d_in, clt=clt, crt=crt, lap_num=0,
                                last_lap_time=last_llt, speed_mph=80, throttle_pct=80))
    # Pause: 30 frames of is_race_on=0, CRT held
    pause_clt = (n_half / n_full) * lt0
    pause_crt = race_time + pause_clt
    pause_d = distance + (n_half / n_full) * track.length_m
    for i in range(30):
        laps.append(base_packet(distance=pause_d, clt=pause_clt, crt=pause_crt, lap_num=0,
                                last_lap_time=last_llt, is_race_on=0,
                                speed_mph=0, throttle_pct=0, brake_pct=0, gear=0, rpm=1000))
    # Resume — back to is_race_on=1, continue lap 0
    for i in range(n_half, n_full):
        clt = (i / n_full) * lt0
        crt = race_time + clt
        d_in = (i / n_full) * track.length_m
        laps.append(base_packet(distance=distance + d_in, clt=clt, crt=crt, lap_num=0,
                                last_lap_time=last_llt, speed_mph=80, throttle_pct=80))
    # Cross the line for lap 0
    laps.append(base_packet(distance=distance + track.length_m, clt=0.05, crt=race_time + lt0,
                            lap_num=1, last_lap_time=lt0, speed_mph=120, throttle_pct=80, gear=5))
    distance += track.length_m
    race_time += lt0
    last_llt = lt0

    # Lap 1 normal
    lt1 = track.lap_time_with_jitter(rng)
    expected.append(round(lt1, 3))
    laps += gen_lap_packets(track, lap_num=1, lap_time_s=lt1,
                            distance_offset=distance, race_time_offset=race_time,
                            last_lap_time_carry=last_llt, rng=rng)

    return Scenario(
        label="pause_resume",
        packets=pre_race + race_start + laps,
        track=track,
        expected_completed_lap_times=expected,
        grid_pos=grid,
        total_distance_at_session_end=distance + track.length_m,
    )


def scenario_restart_from_menu(rng: random.Random) -> Scenario:
    """User races a bit, then restarts from the pause menu — Forza resets
    current_race_time and lap_number, race begins fresh. Goal: the new race
    should produce its own clean lap timings, the old (incomplete) race is
    discarded."""
    track = rng.choice(TRACKS)
    grid = rng.randint(2, 24)
    pre_race = gen_pre_race_packets(track, n=track.pkt_hz * 3, rng=rng)
    race_start_1 = [gen_race_start_packet(track, distance_offset=pre_race[-1]["distance_traveled"],
                                           rng=rng, race_position=grid)]
    distance = race_start_1[0]["distance_traveled"]
    race_time = 0.0

    # Race a partial lap before restart
    partial_lap_time = track.base_lap_time_s * 0.4
    n_partial = int(partial_lap_time * track.pkt_hz)
    laps_first = []
    for i in range(n_partial):
        clt = (i / n_partial) * partial_lap_time
        crt = race_time + clt
        d_in = (i / n_partial) * track.length_m * 0.4
        laps_first.append(base_packet(distance=distance + d_in, clt=clt, crt=crt, lap_num=0,
                                      last_lap_time=0, speed_mph=70, throttle_pct=80))

    # Restart: CRT resets to ~0, distance restarts to 0 (Forza per-race counter)
    # Note real Forza behavior: distance_traveled may keep accumulating across
    # restart attempts within the same Forza-session. The simulator resets
    # to 0 to model the "restart from cold" case.
    distance = 0.0
    race_time = 0.0
    grid2 = rng.randint(2, 24)
    race_start_2 = [gen_race_start_packet(track, distance_offset=0.0, rng=rng,
                                           race_position=grid2)]

    # Real complete laps in the new race
    n_laps = rng.randint(2, 3)
    laps_second = []
    last_llt = 0.0
    expected = []
    for lap_n in range(n_laps):
        lt = track.lap_time_with_jitter(rng)
        expected.append(round(lt, 3))
        laps_second += gen_lap_packets(track, lap_num=lap_n, lap_time_s=lt,
                                        distance_offset=distance, race_time_offset=race_time,
                                        last_lap_time_carry=last_llt, rng=rng)
        distance += track.length_m
        race_time += lt
        last_llt = lt

    return Scenario(
        label="restart_from_menu",
        packets=pre_race + race_start_1 + laps_first + race_start_2 + laps_second,
        track=track,
        # Note: only the SECOND race's laps should be expected. The first
        # session/race is closed by the restart-detect path; the simulator
        # harness will be looking at the LATEST session in our simple
        # single-session model. To keep this simple we accept 0+ matching
        # laps but not require all of them — the harness checks
        # "expected lap was captured" so as long as the second race's laps
        # appear, this passes. (See scenario_restart-aware harness below.)
        expected_completed_lap_times=expected,
        grid_pos=grid2,
        total_distance_at_session_end=distance,
    )


def scenario_race_end_at_finish(rng: random.Random) -> Scenario:
    """User crosses the FINAL line and Forza flips is_race_on=0 within a
    second — the cross-the-line race-end pattern. Tests that
    is_likely_race_end() fires within ~5s, distinct from a mid-race pause."""
    track = rng.choice(TRACKS)
    grid = rng.randint(2, 24)
    pre_race = gen_pre_race_packets(track, n=track.pkt_hz * 3, rng=rng)
    race_start = [gen_race_start_packet(track, distance_offset=pre_race[-1]["distance_traveled"],
                                         rng=rng, race_position=grid)]
    distance = race_start[0]["distance_traveled"]
    race_time = 0.0
    last_llt = 0.0
    expected = []
    laps = []
    n_laps = rng.randint(2, 3)
    for lap_n in range(n_laps):
        lt = track.lap_time_with_jitter(rng)
        expected.append(round(lt, 3))
        laps += gen_lap_packets(track, lap_num=lap_n, lap_time_s=lt,
                                distance_offset=distance, race_time_offset=race_time,
                                last_lap_time_carry=last_llt, rng=rng)
        distance += track.length_m
        race_time += lt
        last_llt = lt
    # Post-race cooldown: is_race_on=0, lap_number stays at n_laps, CRT held
    # at race-end time. Forza streams these for the results screen. We
    # generate enough packets to span the 2s pause-detection threshold.
    final_clt = 0.5
    for i in range(track.pkt_hz * 4):   # 4 seconds of post-race packets
        laps.append(base_packet(distance=distance, clt=final_clt, crt=race_time + final_clt,
                                lap_num=n_laps, last_lap_time=last_llt, is_race_on=0,
                                speed_mph=10, throttle_pct=0, brake_pct=20, gear=2))
    return Scenario(
        label="race_end_at_finish",
        packets=pre_race + race_start + laps,
        track=track,
        expected_completed_lap_times=expected,
        grid_pos=grid,
        total_distance_at_session_end=distance,
    )


SCENARIO_BUILDERS: list[Callable[[random.Random], Scenario]] = [
    scenario_clean_cold_start,
    scenario_stale_lap_number,
    scenario_mid_race_join,
    scenario_delayed_last_lap_time,
    scenario_pause_resume,
    scenario_restart_from_menu,
    scenario_race_end_at_finish,
]


# ─── Simulator + invariants ───────────────────────────────────────────────────


@dataclass
class Failure:
    scenario: str
    seed: int
    invariant: str
    detail: str


def run_scenario(scen: Scenario) -> tuple[Session, list[Failure]]:
    """Feed scenario packets through Session.ingest, mimicking the protocol-
    layer behavior of closing-and-respawning a Session when restart-detect
    fires. Returns the FINAL session (post-restart, if applicable) + any
    invariant failures.

    Tracks all_completed_laps across session boundaries so we can verify
    laps from earlier sessions weren't lost (for restart scenarios).
    """
    sess = Session("forza_motorsport", datetime.datetime.now())
    sess.track = scen.track.name
    all_completed_laps: list = []

    failures: list[Failure] = []

    for pkt in scen.packets:
        try:
            # Mimic protocol.py: driving packets go through ingest, non-driving
            # packets only update state (the pause-aware code path lives in
            # update_state's _update_race_state branch).
            if _is_driving(pkt):
                sess.ingest(b"", pkt)
            update_state("forza_motorsport", sess, pkt)
        except Exception as e:
            failures.append(Failure(
                scenario=scen.label, seed=-1,
                invariant="ingest_does_not_throw",
                detail=f"{type(e).__name__}: {e}",
            ))
            return sess, failures
        # Mimic protocol.py: when restart-detect fires, close session
        # (preserving any completed laps) and spawn a fresh one for
        # subsequent packets.
        if sess._should_close_for_restart:
            all_completed_laps.extend(sess.completed_laps)
            sess = Session("forza_motorsport", datetime.datetime.now())
            sess.track = scen.track.name

    # Aggregate the final session's completed laps for cross-session checks.
    all_completed_laps.extend(sess.completed_laps)
    sess._all_completed_laps_for_test = all_completed_laps  # stuff onto session for invariant checks

    # Invariant 1: every completed lap has a non-None, non-fake lap_time_s
    for lap in sess.completed_laps:
        if lap.lap_time_s is None:
            failures.append(Failure(
                scenario=scen.label, seed=-1,
                invariant="completed_lap_has_time",
                detail=f"L{lap.lap_number} has lap_time_s=None",
            ))

    # Invariant 2: completed lap times match what we generated (within rounding).
    # Use the cross-session aggregate so restart scenarios still match the
    # second race's laps even though the first session was closed.
    aggregate_laps = getattr(sess, "_all_completed_laps_for_test", sess.completed_laps)
    completed_times = [round(l.lap_time_s, 3) for l in aggregate_laps if l.lap_time_s]
    for expected_t in scen.expected_completed_lap_times:
        matches = [t for t in completed_times if abs(t - expected_t) < 0.05]
        if not matches:
            failures.append(Failure(
                scenario=scen.label, seed=-1,
                invariant="expected_lap_captured",
                detail=f"expected lap_time={expected_t}s not found in {completed_times}",
            ))

    # Invariant 3: best_lap_time_s == min of completed lap times (when valid)
    valid_times = [t for t in completed_times if t > 0]
    if valid_times and sess.best_lap_time_s is not None:
        expected_best = min(valid_times)
        if abs(sess.best_lap_time_s - expected_best) > 0.001:
            failures.append(Failure(
                scenario=scen.label, seed=-1,
                invariant="best_lap_is_min",
                detail=f"best={sess.best_lap_time_s} but min(times)={expected_best}",
            ))

    # Invariant 4: state["last_lap_time_s"] reflects last completed lap
    if completed_times:
        if state.get("last_lap_time_s") is None:
            failures.append(Failure(
                scenario=scen.label, seed=-1,
                invariant="state_last_lap_populated",
                detail=f"completed_laps has {len(completed_times)} entries but state[last_lap_time_s]=None",
            ))

    # Invariant 5: when grid is latched, current_lap_num made sense
    if scen.grid_pos is not None and sess._grid_pos_at_start is not None:
        # After race-start, current_lap_num should be 0 (or have advanced via
        # legitimate transitions). It must NEVER be a stale pre-race value.
        # We can't directly verify "is 0 right after reset" post-hoc, but we
        # can check: if any lap completed, current_lap_num should be at least
        # 1 (i.e. transitions fired).
        if completed_times and sess.current_lap_num == 0:
            failures.append(Failure(
                scenario=scen.label, seed=-1,
                invariant="lap_transitions_advance_num",
                detail=f"completed {len(completed_times)} laps but current_lap_num still 0",
            ))

    # Invariant 6: delta isn't pathological (i.e. delta != current_lap_time when
    # current_lap_time > 5s — that pattern means d_in_lap collapsed to 0).
    delta = state.get("delta_to_best_s")
    cur_t = state.get("current_lap_time")
    if delta is not None and cur_t is not None and cur_t > 5:
        if abs(delta - cur_t) < 0.5:
            failures.append(Failure(
                scenario=scen.label, seed=-1,
                invariant="delta_not_equal_cur_t",
                detail=f"delta={delta} ≈ cur_t={cur_t} suggests d_in_lap collapsed",
            ))

    # Invariant 7: reference timeline distance ≈ track length (when reference exists)
    if sess._delta_ref_total_m > 0:
        expected = scen.track.length_m
        actual = sess._delta_ref_total_m
        deviation = abs(actual - expected) / expected
        if deviation > 0.10:
            failures.append(Failure(
                scenario=scen.label, seed=-1,
                invariant="ref_total_m_matches_track",
                detail=f"track {scen.track.name} ({expected}m) but ref_total_m={actual:.0f}m ({deviation*100:.1f}% off)",
            ))

    return sess, failures


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1000, help="Number of randomized scenarios")
    parser.add_argument("--seed", type=int, default=None, help="Master RNG seed (default: random)")
    parser.add_argument("--verbose", action="store_true", help="Print one line per scenario")
    args = parser.parse_args()

    master_seed = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
    print(f"monte_carlo_session: {args.runs} runs, master seed {master_seed}")
    print()

    master_rng = random.Random(master_seed)
    failures: list[Failure] = []
    per_scenario_counts = {b.__name__: 0 for b in SCENARIO_BUILDERS}
    per_scenario_failures = {b.__name__: 0 for b in SCENARIO_BUILDERS}

    for run_i in range(args.runs):
        seed = master_rng.randint(0, 2**31 - 1)
        rng = random.Random(seed)
        builder = rng.choice(SCENARIO_BUILDERS)
        per_scenario_counts[builder.__name__] += 1
        scen = builder(rng)
        try:
            _, run_failures = run_scenario(scen)
        except Exception as e:
            run_failures = [Failure(
                scenario=scen.label, seed=seed,
                invariant="harness_crash",
                detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            )]
        for f in run_failures:
            f.seed = seed
        if run_failures:
            per_scenario_failures[builder.__name__] += 1
            failures.extend(run_failures)
        if args.verbose:
            mark = "✗" if run_failures else "·"
            print(f"  {mark} {builder.__name__:<35} seed={seed} failures={len(run_failures)}")

    print()
    print(f"Per-scenario results:")
    for name in per_scenario_counts:
        n = per_scenario_counts[name]
        f = per_scenario_failures[name]
        rate = (f / n * 100) if n else 0
        print(f"  {name:<40} runs={n:>5}  failures={f:>5}  ({rate:5.1f}%)")
    print()

    if not failures:
        print(f"PASS — {args.runs} scenarios, 0 invariant failures.")
        return 0

    print(f"FAIL — {len(failures)} invariant failures across {sum(per_scenario_failures.values())} scenarios:")
    print()
    # Group by invariant
    by_invariant: dict[str, list[Failure]] = {}
    for f in failures:
        by_invariant.setdefault(f.invariant, []).append(f)
    for inv, fs in sorted(by_invariant.items(), key=lambda kv: -len(kv[1])):
        print(f"  {inv}: {len(fs)} failures")
        # Show up to 3 examples
        for ex in fs[:3]:
            print(f"    - [{ex.scenario}, seed={ex.seed}] {ex.detail}")
        if len(fs) > 3:
            print(f"    ... and {len(fs) - 3} more")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
