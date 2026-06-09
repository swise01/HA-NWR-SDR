"""
test_listener.py — automated pipeline tests + optional network smoke test.

Tests run in two modes:

  python3 test_listener.py              # full pipeline tests (no server needed)
  python3 test_listener.py --smoke      # also sends real UDP and polls /status
  python3 test_listener.py --host <ip>  # smoke test against remote host

Pipeline tests exercise parse → datagram_received → state / session directly,
catching regressions without a live server.
"""

import argparse
import json
import socket
import struct
import sys
import time
import urllib.request
from typing import Optional

sys.path.insert(0, ".")

# ── packet builders ───────────────────────────────────────────────────────────

_FM_FORMAT = "<iI" + "f"*51 + "i"*5 + "f"*17 + "H" + "B"*6 + "b"*3


def build_forza_packet(speed_mph: float = 100.0, throttle_pct: float = 80.0,
                       lap: int = 1, last_lap: float = 0.0, steer: int = 0,
                       is_race_on: int = 1, distance_traveled: float = 1500.0,
                       current_lap_time: float = 15.5) -> bytes:
    speed_ms = speed_mph / 2.237
    accel = int(throttle_pct / 100 * 255)
    vals = [
        is_race_on, 12345,
        8000.0, 800.0, 5500.0,
        0.1, 9.5, 0.0,
        speed_ms, 0.0, 0.0,
        0.0, 0.0, 0.0,
        0.0, 0.0, 0.0,
        0.5, 0.5, 0.5, 0.5,
        0.01, 0.01, 0.02, 0.02,
        100.0, 100.0, 100.0, 100.0,
        0.0, 0.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 0.0,
        0.02, 0.02, 0.02, 0.02,
        0.1, 0.1, 0.1, 0.1,
        42, 3, 750, 1, 6,
        100.0, 0.5, 200.0,
        speed_ms, 250000.0, 400.0,   # speed field (m/s) mirrors velocity
        85.0, 85.0, 85.0, 85.0,
        0.5, 0.6, distance_traveled,
        last_lap if last_lap > 0 else 0.0, last_lap, current_lap_time, 305.0,
        lap,
        5, accel, 0, 0, 0, 4,
        steer, 0, 0,
    ]
    data = struct.pack(_FM_FORMAT, *vals)
    assert len(data) == 311
    return data


def build_acc_packet(speed_mph: float = 100.0, throttle_pct: float = 75.0,
                     slip_rl: float = 0.05, slip_rr: float = 0.06) -> bytes:
    speed_kmh = speed_mph * 1.60934
    fields = [
        0,                       # packet_id (physics)
        throttle_pct / 100,      # gas
        0.0,                     # brake
        50.0,                    # fuel
        4,                       # gear
        6000,                    # rpm
        -0.2,                    # steer
        speed_kmh,               # speed_kmh
        0.0, 0.0, speed_kmh / 3.6,  # velocity
        8.5, 0.0, 0.2,           # accG
        0.01, 0.01, slip_rl, slip_rr,  # wheelSlip
    ]
    data = struct.pack("<ifffiiffffffffffff", *fields)
    return data.ljust(200, b'\x00')


def build_acc_graphics_packet(session_type: int = 4, position: int = 3) -> bytes:
    """ACC graphics packet (packet_id=1)."""
    data = struct.pack("<i", 1)           # packet_id = 1
    data += struct.pack("<i", 2)          # status = LIVE
    data += struct.pack("<i", session_type)  # session type (4=race)
    data += b'\x00' * (136 - len(data))   # pad to position field
    data += struct.pack("<i", position)
    data += b'\x00' * 4
    return data


def _f1_header(packet_id: int, session_uid: int = 0xDEADBEEFCAFE,
               player_idx: int = 0) -> bytes:
    """29-byte F1 2024 header. packet_id at offset 6 (where parse_f1 reads it)."""
    return struct.pack(
        "<HBBBBBQfIIBB",
        2024,          # packetFormat (H, offsets 0-1)
        24, 1, 0,      # gameYear, major, minor (B, offsets 2-4)
        1,             # packetVersion (B, offset 5) — not read by parser
        packet_id,     # packetId (B, offset 6) ← what parse_f1 reads
        session_uid,   # Q, offsets 7-14
        0.0,           # sessionTime
        0, 0,          # frameIdentifier, overallFrameIdentifier
        player_idx,    # playerCarIndex (B, offset 27)
        255,           # secondaryPlayerCarIndex
    )


def build_f1_session_packet(track_id: int = 11, session_type: int = 10,
                            uid: int = 0xDEADBEEFCAFE) -> bytes:
    header = _f1_header(packet_id=1, session_uid=uid)
    payload = struct.pack("<BbbBHBb", 0, 25, 20, 50, 5793, session_type, track_id)
    return header + payload


def build_f1_telemetry_packet(speed_mph: float = 180.0, throttle: float = 0.85,
                               uid: int = 0xDEADBEEFCAFE) -> bytes:
    header = _f1_header(packet_id=6, session_uid=uid)
    speed_kmh = int(speed_mph / 0.621371)
    car = struct.pack(
        "<HfffBbHBBH4H4B4BH4f4B",
        speed_kmh, throttle, -0.1, 0.0, 0, 7, 11500, 1, 80, 0,
        400, 400, 400, 400,
        90, 90, 88, 88,
        95, 95, 93, 93,
        105,
        23.5, 23.5, 22.8, 22.8,
        0, 0, 0, 0,
    )
    return header + car.ljust(60, b'\x00')


def build_f1_lapdata_packet(lap_num: int = 2, cur_lap_ms: int = 45000,
                             last_lap_ms: int = 90234,
                             uid: int = 0xDEADBEEFCAFE) -> bytes:
    """F1 2024 LapData (packet_id=2). 50 bytes per car."""
    header = _f1_header(packet_id=2, session_uid=uid)
    # Offsets within each car entry (parse_f1 off_* constants):
    #  0  lastLapTimeInMS (I,4)
    #  4  currentLapTimeInMS (I,4)
    #  8  sector1TimeInMS (H,2) + sector1Minutes (B,1)    → 3 bytes
    # 11  sector2TimeInMS (H,2) + sector2Minutes (B,1)    → 3 bytes
    # 14  deltaToCarInFront (I,4) + deltaToLeader (I,4)   → 8 bytes
    # 22  lapDistance (f,4) + totalDistance (f,4)         → 8 bytes  (NOT 3 floats)
    # 30  carPosition (B)
    # 31  currentLapNum (B)
    # 41  gridPosition (B)
    car = struct.pack("<II", last_lap_ms, cur_lap_ms)  # 0-7
    car += struct.pack("<HB", 0, 0)                    # 8-10  sector1
    car += struct.pack("<HB", 0, 0)                    # 11-13 sector2
    car += struct.pack("<II", 0, 0)                    # 14-21 deltas
    car += struct.pack("<ff", 500.0, 5000.0)           # 22-29 distances (2 floats → 8 bytes)
    car += struct.pack("<B", 3)                        # 30 carPosition
    car += struct.pack("<B", lap_num)                  # 31 currentLapNum
    car = car.ljust(50, b'\x00')
    car = car[:41] + struct.pack("<B", 3) + car[42:]   # 41 gridPosition
    return header + car


def build_f1_motionex_packet(slip_rl: float = 0.08, slip_rr: float = 0.09,
                              uid: int = 0xDEADBEEFCAFE) -> bytes:
    """F1 2024 MotionEx (packet_id=13). wheelSlip at hdr+64."""
    header = _f1_header(packet_id=13, session_uid=uid)
    # 4 groups of 4 floats before wheelSlip: suspPos, suspVel, suspAcc, wheelSpeed = 64 bytes
    pre = struct.pack("<" + "f" * 16, *([0.0] * 16))
    slip = struct.pack("<ffff", 0.01, 0.01, slip_rl, slip_rr)
    return header + pre + slip


# ── test helpers ──────────────────────────────────────────────────────────────

def _reset_state():
    """Reset all global listener state between tests."""
    import listener as L
    from parsers import f1 as _f1
    L.active_sessions.clear()
    # F1 session metadata moved into the parsers.f1 module during the
    # session/ package refactor; it's no longer a listener attribute.
    _f1._f1_session_meta.clear()
    L.state.update({
        "status": "idle", "game": None, "session_id": None,
        "track": "unknown", "car": "unknown", "session_type": "unknown",
        "started_at": None, "packet_count": 0, "lap": 0,
        "speed_mph": 0, "throttle_pct": 0, "brake_pct": 0,
        "gear": 0, "rpm": 0, "engine_max_rpm": 8000, "steer": 0,
        "slip_rl": 0, "slip_rr": 0, "g_lat": 0, "g_lon": 0,
        "drs": False, "tyre_compound": None, "fuel_remaining_laps": None,
        "current_lap_time": None, "last_lap_time_s": None,
        "best_lap_time_s": None, "tyre_fl": None, "tyre_fr": None,
        "tyre_rl": None, "tyre_rr": None, "last_packet_at": None,
        "udp_received": {"forza_motorsport": 0, "acc": 0, "f1": 0},
        "udp_rejected": {"forza_motorsport": 0, "acc": 0, "f1": 0},
        "last_rejected_size": {"forza_motorsport": None, "acc": None, "f1": None},
        "udp_last_at": {"forza_motorsport": None, "acc": None, "f1": None},
    })


def _inject(proto, data: bytes, addr: str = "127.0.0.1"):
    proto.datagram_received(data, (addr, 0))


PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✓  {label}")
    else:
        FAIL += 1
        print(f"  ✗  {label}{('  ← ' + detail) if detail else ''}")


# ── parser unit tests ─────────────────────────────────────────────────────────

def test_parsers():
    import listener as L
    print("\n[parsers]")

    # Forza
    r = L.parse_forza(build_forza_packet())
    check("forza parses", r is not None)
    check("forza speed_mph", r and abs(r["speed_mph"] - 100.0) < 1.0, str(r and r.get("speed_mph")))
    check("forza gear",     r and r["gear"] == 4)
    check("forza throttle", r and abs(r["throttle_pct"] - 80.0) < 1.0)
    check("forza slip_rl",  r and r.get("slip_ratio_rl") is not None)
    check("forza tire_temp_fl", r and r.get("tire_temp_fl") == 85.0)

    # ACC physics
    r = L.parse_acc(build_acc_packet(speed_mph=100.0, slip_rl=0.05))
    check("acc physics parses", r is not None)
    check("acc speed_mph",      r and abs(r["speed_mph"] - 100.0) < 1.0, str(r and r.get("speed_mph")))
    check("acc throttle",       r and abs(r["throttle_pct"] - 75.0) < 1.0)
    check("acc slip_rl",        r and abs(r.get("slip_ratio_rl", 0) - 0.05) < 0.001)
    check("acc slip_rr",        r and abs(r.get("slip_ratio_rr", 0) - 0.06) < 0.001)
    check("acc no _packet_type",r and "_packet_type" not in r)

    # ACC graphics
    r = L.parse_acc(build_acc_graphics_packet(session_type=4, position=3))
    check("acc graphics parses",       r is not None)
    check("acc graphics _packet_type", r and r.get("_packet_type") == "graphics")
    check("acc graphics session_type", r and r.get("session_type") == "race")
    check("acc graphics race_position",r and r.get("race_position") == 3)

    # ACC static (packet_id=2) → None
    r = L.parse_acc(struct.pack("<i", 2) + b'\x00' * 100)
    check("acc static → None", r is None)

    # F1 session (packet_id=1) → None (stored in meta, no return value)
    r = L.parse_f1(build_f1_session_packet())
    check("f1 session → None", r is None)

    # F1 CarTelemetry (packet_id=6)
    r = L.parse_f1(build_f1_telemetry_packet(speed_mph=180.0, throttle=0.85))
    check("f1 telemetry parses",     r is not None, str(r))
    check("f1 telemetry _type",      r and r.get("_packet_type") == "telemetry")
    check("f1 telemetry speed_mph",  r and abs(r["speed_mph"] - 180.0) < 2.0, str(r and r.get("speed_mph")))
    check("f1 telemetry throttle",   r and abs(r["throttle_pct"] - 85.0) < 1.0)
    check("f1 tyre_surface_temp_fl", r and r.get("tyre_surface_temp_fl") is not None)

    # F1 LapData (packet_id=2)
    r = L.parse_f1(build_f1_lapdata_packet(lap_num=3, cur_lap_ms=45000, last_lap_ms=90234))
    check("f1 lapdata parses",       r is not None, str(r))
    check("f1 lapdata _type",        r and r.get("_packet_type") == "lap_data")
    check("f1 lapdata lap_number",   r and r.get("lap_number") == 3)
    check("f1 lapdata cur_lap_time", r and abs(r.get("current_lap_time", 0) - 45.0) < 0.1)
    check("f1 lapdata last_lap_time",r and abs(r.get("last_lap_time", 0) - 90.234) < 0.01)

    # F1 MotionEx (packet_id=13)
    r = L.parse_f1(build_f1_motionex_packet(slip_rl=0.08, slip_rr=0.09))
    check("f1 motionex parses",  r is not None, str(r))
    check("f1 motionex _type",   r and r.get("_packet_type") == "motion")
    check("f1 motionex slip_rl", r and abs(r.get("slip_ratio_rl", 0) - 0.08) < 0.001)
    check("f1 motionex slip_rr", r and abs(r.get("slip_ratio_rr", 0) - 0.09) < 0.001)


# ── pipeline tests ────────────────────────────────────────────────────────────

def test_session_creation():
    import listener as L
    _reset_state()
    proto = L.TelemetryProtocol("forza_motorsport", L.parse_forza)
    print("\n[session creation]")

    # Idle packet (speed=0) should not create a session
    _inject(proto, build_forza_packet(speed_mph=0, throttle_pct=0))
    check("no session from idle packet", "forza_motorsport" not in L.active_sessions)

    # Driving packet should create a session
    _inject(proto, build_forza_packet(speed_mph=80))
    check("session created on driving", "forza_motorsport" in L.active_sessions)
    check("state game = forza",   L.state["game"] == "forza_motorsport")
    check("state status = receiving", L.state["status"] == "receiving")
    check("state speed > 0",      L.state["speed_mph"] > 0)


def test_acc_pipeline():
    import listener as L
    _reset_state()
    proto = L.TelemetryProtocol("acc", L.parse_acc)
    print("\n[acc pipeline]")

    # Physics packet while driving
    _inject(proto, build_acc_packet(speed_mph=120.0, slip_rl=0.07, slip_rr=0.08))
    check("acc session created",  "acc" in L.active_sessions)
    check("acc game in state",    L.state["game"] == "acc")
    check("acc speed in state",   abs(L.state["speed_mph"] - 120.0) < 2.0,
          str(L.state["speed_mph"]))
    check("acc slip_rl in state", abs(L.state["slip_rl"] - 0.07) < 0.001,
          str(L.state["slip_rl"]))
    check("acc slip_rr in state", abs(L.state["slip_rr"] - 0.08) < 0.001,
          str(L.state["slip_rr"]))

    # Graphics packet — session_type should update, state should NOT be clobbered
    _inject(proto, build_acc_graphics_packet(session_type=4))
    session = L.active_sessions.get("acc")
    check("acc session_type from graphics", session and session.session_type == "race")
    check("acc status not clobbered",       L.state["status"] != "idle")


def test_f1_pipeline():
    import listener as L
    _reset_state()
    proto = L.TelemetryProtocol("f1", L.parse_f1)
    uid = 0xCAFE1234
    print("\n[f1 pipeline]")

    # Session packet primes track metadata
    _inject(proto, build_f1_session_packet(track_id=10, session_type=10, uid=uid))
    from parsers import f1 as _f1
    check("f1 session meta stored", uid in _f1._f1_session_meta)

    # Telemetry creates session and updates state
    _inject(proto, build_f1_telemetry_packet(speed_mph=200.0, uid=uid))
    check("f1 session created",  "f1" in L.active_sessions)
    check("f1 game in state",    L.state["game"] == "f1")
    check("f1 speed in state",   abs(L.state["speed_mph"] - 200.0) < 3.0,
          str(L.state["speed_mph"]))
    check("f1 track from meta",  L.state["track"] != "unknown", L.state["track"])


def test_f1_slip_via_motionex():
    """MotionEx packet (non-driving) should cache slip; next telemetry should merge it."""
    import listener as L
    _reset_state()
    proto = L.TelemetryProtocol("f1", L.parse_f1)
    uid = 0xBEEF0001
    print("\n[f1 rear slip via MotionEx]")

    # Prime session with one telemetry packet
    _inject(proto, build_f1_telemetry_packet(speed_mph=150.0, uid=uid))
    check("f1 session primed", "f1" in L.active_sessions)
    initial_slip = L.state.get("slip_rl", 0)

    # MotionEx with significant slip — should go to motion cache
    _inject(proto, build_f1_motionex_packet(slip_rl=0.12, slip_rr=0.15, uid=uid))
    session = L.active_sessions.get("f1")
    check("motionex cached slip_rl",
          session and abs(session._motion_cache.get("slip_ratio_rl", 0) - 0.12) < 0.001,
          str(session and session._motion_cache))

    # Next telemetry merges motion cache → slip visible in state
    _inject(proto, build_f1_telemetry_packet(speed_mph=150.0, uid=uid))
    check("f1 slip_rl in state after merge",
          abs(L.state.get("slip_rl", 0) - 0.12) < 0.001,
          str(L.state.get("slip_rl")))
    check("f1 slip_rr in state after merge",
          abs(L.state.get("slip_rr", 0) - 0.15) < 0.001,
          str(L.state.get("slip_rr")))
    check("motion cache cleared after merge",
          session and not session._motion_cache)


def test_f1_lap_timing():
    """LapData cache should feed lap transitions on the next telemetry packet."""
    import listener as L
    _reset_state()
    proto = L.TelemetryProtocol("f1", L.parse_f1)
    uid = 0xBEEF0002
    print("\n[f1 lap timing]")

    # Establish session on lap 1
    _inject(proto, build_f1_telemetry_packet(speed_mph=150.0, uid=uid))
    session = L.active_sessions.get("f1")
    check("f1 session on lap 1", session and session.current_lap_num == 0)

    # LapData announces lap 2 completed with a lap time
    _inject(proto, build_f1_lapdata_packet(lap_num=2, cur_lap_ms=45000,
                                           last_lap_ms=90500, uid=uid))
    check("lapdata cached", session and session._lap_cache.get("lap_number") == 2)

    # Telemetry triggers transition (pre-merge in datagram_received)
    _inject(proto, build_f1_telemetry_packet(speed_mph=150.0, uid=uid))
    check("lap transitioned to 2",
          session and session.current_lap_num == 2,
          str(session and session.current_lap_num))
    check("lap time recorded",
          session and session.best_lap_time_s is not None,
          str(session and session.best_lap_time_s))
    check("best_lap in state",
          L.state.get("best_lap_time_s") is not None)
    check("current_lap_time in state",
          L.state.get("current_lap_time") is not None)


def test_forza_lap_timing():
    """Forza lap transitions via lap_number field in the main packet."""
    import listener as L
    _reset_state()
    proto = L.TelemetryProtocol("forza_motorsport", L.parse_forza)
    print("\n[forza lap timing]")

    _inject(proto, build_forza_packet(speed_mph=100, lap=1))
    session = L.active_sessions.get("forza_motorsport")
    check("forza session created", session is not None)

    _inject(proto, build_forza_packet(speed_mph=100, lap=2, last_lap=90.5))
    check("forza lap transitioned",
          session and session.current_lap_num == 2,
          str(session and session.current_lap_num))
    check("forza lap time recorded",
          session and session.best_lap_time_s == 90.5,
          str(session and session.best_lap_time_s))


_TMP_STORE = None


def _ensure_temp_store():
    """Point the store + storage_path at a throwaway temp dir so a real
    session.close() can persist without touching the configured USB path
    or a live DB. Idempotent — set up once per process."""
    global _TMP_STORE
    if _TMP_STORE is not None:
        return
    import atexit
    import logging
    import shutil
    import tempfile
    from pathlib import Path
    import config
    from db import store

    _TMP_STORE = tempfile.mkdtemp(prefix="simtel_test_")
    atexit.register(shutil.rmtree, _TMP_STORE, ignore_errors=True)
    config.config["storage_path"] = _TMP_STORE
    (Path(_TMP_STORE) / "sessions").mkdir(parents=True, exist_ok=True)
    store.initialize([str(Path(_TMP_STORE) / "test.db")], config.storage_path,
                     {}, {}, logging.getLogger("pacefinder"))
    store._db_init()


def _stored_lap_count(session_id: str) -> int:
    from db import store
    conn = store._db_connect()
    try:
        row = conn.execute(
            "SELECT lap_count FROM sessions WHERE session_id=?",
            (session_id,)).fetchone()
    finally:
        conn.close()
    return row["lap_count"] if row else -1


_LAP_LEN_M = 5000.0   # synthetic track length
_LAP_T_S   = 90.0     # synthetic lap time
_STEPS     = 6        # sample packets per lap


def _drive_forza_race(L, laps: int, final_frac: float = 1.0):
    """Drive a synthetic `laps`-lap Forza race through the real pipeline,
    modelling Forza Motorsport's *actual* behaviour:

      - laps 1..N-1 complete via lap_number transitions, each reporting the
        completed lap's last_lap_time (FM does send it mid-race);
      - distance_traveled accumulates and current_lap_time ticks per lap;
      - at race end FM flips is_race_on=0 AND zeroes last_lap_time (the
        confirmed root cause) — the final lap's official time is never
        transmitted.

    `final_frac` < 1.0 simulates abandoning the final lap partway (less
    distance covered) — that lap must NOT be recovered.
    """
    _ensure_temp_store()
    _reset_state()
    proto = L.TelemetryProtocol("forza_motorsport", L.parse_forza)

    prev_lap_time = 0.0  # FM reports the last *completed* lap throughout
    for k in range(laps):                       # FM lap_number is 0-indexed
        is_final = (k == laps - 1)
        frac_cap = final_frac if is_final else 1.0
        dist0 = k * _LAP_LEN_M
        for i in range(1, _STEPS + 1):
            f = (i / _STEPS) * frac_cap
            _inject(proto, build_forza_packet(
                speed_mph=100, lap=k,
                distance_traveled=dist0 + _LAP_LEN_M * f,
                current_lap_time=_LAP_T_S * f,
                last_lap=prev_lap_time))
        prev_lap_time = _LAP_T_S + 0.001 * k     # this lap's time

    # Race ends — FM zeroes last_lap_time in the is_race_on=0 packet.
    _inject(proto, build_forza_packet(
        speed_mph=0, lap=0, is_race_on=0,
        distance_traveled=(laps - 1) * _LAP_LEN_M + _LAP_LEN_M * final_frac,
        current_lap_time=0.0, last_lap=0.0))

    session = L.active_sessions.get("forza_motorsport")
    session.close()
    return session


def test_long_race_lap_count():
    """A 40 / 50 / 100-lap race must store every lap — including the final
    one, whose official time Forza never transmits (last_lap_time=0.0 at
    race end). The final lap is recovered from its own telemetry because
    its distance proves it completed. Runs in ms; no server."""
    import listener as L
    print("\n[long race lap count]")
    for n in (40, 50, 100):
        session = _drive_forza_race(L, n)
        got = len(session.completed_laps)
        check(f"{n}-lap race keeps {n} laps in memory", got == n,
              f"got {got}")
        stored = _stored_lap_count(session.session_id)
        check(f"{n}-lap race persists lap_count={n}", stored == n,
              f"db lap_count={stored}")


def test_final_lap_abandoned_not_recovered():
    """The flip side of the fix: if the driver abandons the final lap
    partway (only ~35% distance), it must NOT be stored as a lap — that's
    the partial-lap regression #146 removed and this fix must preserve."""
    import listener as L
    print("\n[final lap abandoned]")
    session = _drive_forza_race(L, 10, final_frac=0.35)
    got = len(session.completed_laps)
    check("abandoned final lap dropped (9 of 10 kept)", got == 9,
          f"got {got}")
    stored = _stored_lap_count(session.session_id)
    check("abandoned final lap not persisted", stored == 9,
          f"db lap_count={stored}")


def test_game_switching():
    """Switching game source: state should reflect the new game, old session must not clobber."""
    import listener as L
    _reset_state()
    forza = L.TelemetryProtocol("forza_motorsport", L.parse_forza)
    f1    = L.TelemetryProtocol("f1",               L.parse_f1)
    uid   = 0xBEEF0003
    print("\n[game switching]")

    # Establish Forza session
    for _ in range(3):
        _inject(forza, build_forza_packet(speed_mph=90))
    check("forza active before switch", "forza_motorsport" in L.active_sessions)
    check("state = forza before switch", L.state["game"] == "forza_motorsport")

    # Switch to F1 — both sessions now coexist until watchdog closes Forza
    _inject(f1, build_f1_telemetry_packet(speed_mph=210.0, uid=uid))
    check("f1 session created alongside forza", "f1" in L.active_sessions)
    check("state = f1 after f1 packet",         L.state["game"] == "f1",
          str(L.state["game"]))
    check("forza session still exists",         "forza_motorsport" in L.active_sessions)

    # Forza session times out (simulate by backdating last_packet)
    L.active_sessions["forza_motorsport"].last_packet -= 20
    import asyncio
    asyncio.get_event_loop().run_until_complete(_run_watchdog_once())

    check("forza session closed", "forza_motorsport" not in L.active_sessions)
    check("f1 session still live", "f1" in L.active_sessions)
    check("state game still f1",   L.state["game"] == "f1",
          str(L.state["game"]))
    check("state status not race_ended",
          L.state["status"] != "race_ended",
          L.state["status"])


def test_tyre_temps_per_game():
    """Each game uses a different tyre temp key — all should map to state tyre_*."""
    import listener as L
    print("\n[tyre temps per game]")

    # Forza: tire_temp_fl
    _reset_state()
    proto = L.TelemetryProtocol("forza_motorsport", L.parse_forza)
    _inject(proto, build_forza_packet(speed_mph=80))
    check("forza tyre_fl in state", L.state.get("tyre_fl") == 85.0,
          str(L.state.get("tyre_fl")))

    # ACC: tyre_core_temp_fl (update_state maps tyre_core_temp_* for ACC)
    _reset_state()
    proto = L.TelemetryProtocol("acc", L.parse_acc)
    _inject(proto, build_acc_packet(speed_mph=80))
    # ACC packet pad is zeros so tyre_core_temp will be 0.0 — just check key exists
    check("acc tyre key exists after packet", "tyre_fl" in L.state)


async def _run_watchdog_once():
    """Run one watchdog check synchronously."""
    import listener as L
    to_close = []
    for game, session in L.active_sessions.items():
        if session.is_timed_out():
            to_close.append((game, "no packets"))
        elif session.is_idle_timed_out():
            to_close.append((game, "idle"))
    for game, reason in to_close:
        session = L.active_sessions.pop(game)
        session.close()
        if not L.active_sessions:
            L.state["status"] = "race_ended"
            L.state["game"]   = None


# ── live UDP tests (requires running listener) ────────────────────────────────

PORTS = {"forza_motorsport": 5300, "acc": 9996, "f1": 20777}

LIVE_PASS = 0
LIVE_FAIL = 0


def lcheck(label: str, condition: bool, detail: str = ""):
    global LIVE_PASS, LIVE_FAIL
    if condition:
        LIVE_PASS += 1
        print(f"  ✓  {label}")
    else:
        LIVE_FAIL += 1
        print(f"  ✗  {label}{('  ← ' + detail) if detail else ''}")


def _send(sock: socket.socket, host: str, port: int, packets):
    for pkt in packets:
        sock.sendto(pkt, (host, port))


def poll_status(host: str, status_port: int, timeout: float = 3.0) -> dict:
    url = f"http://{host}:{status_port}/status"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                return json.loads(resp.read())
        except Exception:
            time.sleep(0.1)
    return {}


def poll_until(host: str, port: int, condition, timeout: float = 3.0) -> Optional[dict]:
    """Poll /status until condition(state) is True or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = poll_status(host, port)
        if s and condition(s):
            return s
        time.sleep(0.15)
    return poll_status(host, port)


def live_test_forza(host: str, status_port: int, sock: socket.socket):
    print("\n[live: forza]")
    port = PORTS["forza_motorsport"]

    # Send 5 driving packets at 100 mph, lap 1
    for _ in range(5):
        _send(sock, host, port, [build_forza_packet(speed_mph=100.0, throttle_pct=80.0, lap=1)])
        time.sleep(0.05)

    s = poll_until(host, status_port, lambda st: st.get("game") == "forza_motorsport")
    lcheck("forza: game in state",     s.get("game") == "forza_motorsport",
           str(s.get("game")))
    lcheck("forza: speed_mph ≈ 100",   s.get("speed_mph", 0) > 90,
           str(s.get("speed_mph")))
    lcheck("forza: throttle_pct > 0",  s.get("throttle_pct", 0) > 0)
    lcheck("forza: tyre_fl set",       s.get("tyre_fl") is not None, str(s.get("tyre_fl")))
    lcheck("forza: slip_rl ≥ 0",       s.get("slip_rl") is not None)

    # Lap transition: send lap=2 with a last_lap time
    for _ in range(3):
        _send(sock, host, port, [build_forza_packet(speed_mph=100.0, lap=2, last_lap=91.5)])
        time.sleep(0.05)
    s = poll_until(host, status_port, lambda st: st.get("lap", 0) >= 2, timeout=2.0)
    lcheck("forza: lap number advances",   s.get("lap", 0) >= 2, str(s.get("lap")))
    lcheck("forza: best_lap_time_s set",   s.get("best_lap_time_s") is not None,
           str(s.get("best_lap_time_s")))


def live_test_acc(host: str, status_port: int, sock: socket.socket):
    print("\n[live: acc]")
    port = PORTS["acc"]

    for _ in range(5):
        _send(sock, host, port, [build_acc_packet(speed_mph=120.0, throttle_pct=75.0,
                                                  slip_rl=0.07, slip_rr=0.08)])
        time.sleep(0.05)

    s = poll_until(host, status_port, lambda st: st.get("game") == "acc")
    lcheck("acc: game in state",     s.get("game") == "acc", str(s.get("game")))
    lcheck("acc: speed_mph ≈ 120",   s.get("speed_mph", 0) > 110, str(s.get("speed_mph")))
    lcheck("acc: slip_rl > 0",       s.get("slip_rl", 0) > 0, str(s.get("slip_rl")))
    lcheck("acc: slip_rr > 0",       s.get("slip_rr", 0) > 0, str(s.get("slip_rr")))


def _game_port_bound(host: str, status_port: int, game: str) -> bool:
    """Return True if the listener successfully bound the UDP port for this game."""
    s = poll_status(host, status_port, timeout=1.0)
    if not s:
        return False
    return game in s.get("bound_ports", {})


def live_test_f1(host: str, status_port: int, sock: socket.socket):
    print("\n[live: f1]")
    if not _game_port_bound(host, status_port, "f1"):
        print("  SKIP — F1 port 20777 not bound (another app may be using it)")
        return
    port = PORTS["f1"]
    uid = 0xCAFEBABE1234

    # Prime session meta (track + session_type)
    _send(sock, host, port, [build_f1_session_packet(track_id=10, session_type=10, uid=uid)])
    time.sleep(0.05)

    # Send MotionEx (slip), LapData (lap timing), CarTelemetry (speed/inputs) — repeated
    for i in range(5):
        _send(sock, host, port, [
            build_f1_motionex_packet(slip_rl=0.09, slip_rr=0.11, uid=uid),
            build_f1_lapdata_packet(lap_num=2, cur_lap_ms=30000 + i*1000,
                                    last_lap_ms=88500, uid=uid),
            build_f1_telemetry_packet(speed_mph=200.0, throttle=0.85, uid=uid),
        ])
        time.sleep(0.05)

    s = poll_until(host, status_port, lambda st: st.get("game") == "f1", timeout=3.0)
    lcheck("f1: game in state",        s.get("game") == "f1", str(s.get("game")))
    lcheck("f1: speed_mph ≈ 200",      s.get("speed_mph", 0) > 180, str(s.get("speed_mph")))
    lcheck("f1: throttle_pct > 0",     s.get("throttle_pct", 0) > 0)
    lcheck("f1: tyre_fl set",          s.get("tyre_fl") is not None, str(s.get("tyre_fl")))
    lcheck("f1: slip_rl > 0",          s.get("slip_rl", 0) > 0, str(s.get("slip_rl")))
    lcheck("f1: slip_rr > 0",          s.get("slip_rr", 0) > 0, str(s.get("slip_rr")))
    lcheck("f1: current_lap_time set", s.get("current_lap_time") is not None,
           str(s.get("current_lap_time")))
    lcheck("f1: lap ≥ 2",              s.get("lap", 0) >= 2, str(s.get("lap")))


def live_test_game_switch(host: str, status_port: int, sock: socket.socket):
    """Switch Forza → F1 → ACC and verify state follows each switch."""
    print("\n[live: game switching]")
    uid = 0xDEADBEEF1234
    f1_available = _game_port_bound(host, status_port, "f1")

    # Forza
    for _ in range(3):
        _send(sock, host, PORTS["forza_motorsport"],
              [build_forza_packet(speed_mph=90)])
        time.sleep(0.05)
    s = poll_until(host, status_port, lambda st: st.get("game") == "forza_motorsport")
    lcheck("switch: forza becomes active", s.get("game") == "forza_motorsport",
           str(s.get("game")))

    # Switch to F1 (only if port bound)
    if f1_available:
        _send(sock, host, PORTS["f1"], [
            build_f1_motionex_packet(slip_rl=0.05, uid=uid),
            build_f1_telemetry_packet(speed_mph=210.0, uid=uid),
        ])
        s = poll_until(host, status_port, lambda st: st.get("game") == "f1", timeout=3.0)
        lcheck("switch: f1 takes over", s.get("game") == "f1", str(s.get("game")))
        lcheck("switch: f1 speed correct", s.get("speed_mph", 0) > 190, str(s.get("speed_mph")))
    else:
        print("  SKIP switch→f1 — F1 port 20777 not bound")

    # Switch to ACC
    for _ in range(3):
        _send(sock, host, PORTS["acc"], [build_acc_packet(speed_mph=130.0)])
        time.sleep(0.05)
    s = poll_until(host, status_port, lambda st: st.get("game") == "acc", timeout=3.0)
    lcheck("switch: acc takes over", s.get("game") == "acc", str(s.get("game")))


def run_live_tests(host: str, status_port: int):
    print(f"\n{'═'*44}")
    print(f"  Live UDP tests → {host}:{status_port}")
    print(f"{'═'*44}")

    s = poll_status(host, status_port, timeout=2.0)
    if not s:
        print("  ⚠  Cannot reach /status — start the listener first:")
        print("     python3 listener.py")
        return

    print(f"  Listener online (status={s.get('status')})")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        live_test_forza(host, status_port, sock)
        live_test_acc(host, status_port, sock)
        live_test_f1(host, status_port, sock)
        live_test_game_switch(host, status_port, sock)
    finally:
        sock.close()

    print(f"\n{'─'*44}")
    print(f"  Live: {LIVE_PASS} passed  {LIVE_FAIL} failed")
    print(f"{'─'*44}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="SimTelemetry automated tests")
    ap.add_argument("--live",        action="store_true",
                    help="Also run live UDP tests (requires running listener)")
    ap.add_argument("--host",        default="127.0.0.1")
    ap.add_argument("--status-port", default=8000, type=int)
    args = ap.parse_args()

    print("SimTelemetry test suite\n")

    # Pipeline tests — no server needed, call datagram_received directly
    test_parsers()
    test_session_creation()
    test_acc_pipeline()
    test_f1_pipeline()
    test_f1_slip_via_motionex()
    test_f1_lap_timing()
    test_forza_lap_timing()
    test_long_race_lap_count()
    test_final_lap_abandoned_not_recovered()
    test_game_switching()
    test_tyre_temps_per_game()

    print(f"\n{'═'*44}")
    print(f"  Pipeline: {PASS} passed  {FAIL} failed")
    print(f"{'═'*44}")

    if args.live:
        run_live_tests(args.host, args.status_port)

    sys.exit(1 if (FAIL or LIVE_FAIL) else 0)


if __name__ == "__main__":
    main()
