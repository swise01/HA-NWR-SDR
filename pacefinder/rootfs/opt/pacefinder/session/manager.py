import json
import struct
import threading
import time
from collections import Counter
from datetime import datetime
from typing import Optional
import logging

from config import storage_path, SESSION_TIMEOUT_S, IDLE_TIMEOUT_S, MIN_VALID_LAP_S
from db.store import (
    _classify_race_type,
    _db_write_session,
    _store_session_lap_samples,
    _update_track_references_bg,
    compute_lap_aggregates,
)
from reference.loader import FORZA_CARS

_log = logging.getLogger("pacefinder")


def _grid_pos_from_history(positions: list) -> Optional[int]:
    """Derive a stable starting grid position from the captured race_position
    history.

    Forza broadcasts a phantom P1 for the first ~30 packets right at the
    lights-drop moment, before the real grid slot is finalised. Taking
    `positions[0]` therefore lands on the phantom. Strategy: use the
    most-frequent position in the first 60 packets (~1s at 60Hz). The
    phantom only persists for a fraction of that window, so the real
    grid position dominates the count.

    Falls back to the only sample available when fewer than 60 packets
    have been captured.
    """
    if not positions:
        return None
    sample = positions[:60] if len(positions) >= 60 else positions
    return Counter(sample).most_common(1)[0][0]


def _is_driving(parsed: dict) -> bool:
    """True when the player has meaningful input — not parked or in a menu."""
    return (
        parsed.get("speed_mph", 0) > 2 or
        parsed.get("throttle_pct", 0) > 2 or
        parsed.get("brake_pct", 0) > 2 or
        abs(parsed.get("steer", 0)) > 5
    )


class LapRecord:
    def __init__(self, lap_number: int):
        self.lap_number   = lap_number
        self.started_at   = time.time()
        self.ended_at     = None
        self.lap_time_s   = None
        self.samples      = []
        self.max_speed    = 0.0
        self.sector_times = []
        # First packet's distance_traveled (cumulative-since-race-start). Used
        # as the lap-start zero so the live delta can compute "meters into the
        # current lap" each packet without recomputing from positions.
        self.start_distance_m: Optional[float] = None

    def add_sample(self, parsed: dict):
        speed = parsed.get("speed_mph", 0)
        if speed > self.max_speed:
            self.max_speed = speed
        if self.start_distance_m is None and parsed.get("distance_traveled") is not None:
            self.start_distance_m = parsed["distance_traveled"]
        sample = {
            "t":            round(parsed.get("current_lap_time", parsed.get("_t", 0)), 3),
            "speed_mph":    round(parsed.get("speed_mph", 0), 1),
            "throttle_pct": round(parsed.get("throttle_pct", 0), 1),
            "brake_pct":    round(parsed.get("brake_pct", 0), 1),
            "clutch_pct":   round(parsed.get("clutch_pct", 0), 1),
            "gear":         parsed.get("gear", 0),
            "steer":        round(parsed.get("steer", 0), 3),
            "rpm":          parsed.get("rpm", parsed.get("current_engine_rpm", 0)),
            "slip_rl":      round(parsed.get("slip_ratio_rl", 0), 4),
            "slip_rr":      round(parsed.get("slip_ratio_rr", 0), 4),
            "g_lat":        round(parsed.get("g_lat", 0), 3),
            "g_lon":        round(parsed.get("g_lon", 0), 3),
        }
        if parsed.get("distance_traveled") is not None:
            sample["distance_traveled_m"] = round(parsed["distance_traveled"], 2)
        if parsed.get("position_x") is not None:
            sample["px"] = round(parsed["position_x"], 2)
            sample["py"] = round(parsed["position_y"], 2)
            sample["pz"] = round(parsed["position_z"], 2)
        for corner in ("fl", "fr", "rl", "rr"):
            v = parsed.get(f"tire_temp_{corner}")
            if v is not None:
                sample[f"tyre_{corner}"] = round(v, 1)
        # ── Bundle: per-sample field expansion (storage spec) ─────────────
        # Only store when the parser actually populated the field — keeps
        # the JSON compact for FM vs FH variants and skips fields the user's
        # game doesn't broadcast. Short keys to keep the per-sample payload
        # small (gzip handles the rest).
        for corner in ("fl", "fr", "rl", "rr"):
            if (v := parsed.get(f"wheel_on_rumble_strip_{corner}")) is not None:
                sample[f"rumble_{corner}"] = round(v, 3)
            if (v := parsed.get(f"wheel_in_puddle_{corner}")) is not None:
                sample[f"puddle_{corner}"] = round(v, 3)
            if (v := parsed.get(f"surface_rumble_{corner}")) is not None:
                sample[f"surf_rumble_{corner}"] = round(v, 3)
            if (v := parsed.get(f"wheel_rotation_speed_{corner}")) is not None:
                sample[f"wsp_{corner}"] = round(v, 2)
            if (v := parsed.get(f"tire_slip_angle_{corner}")) is not None:
                sample[f"sa_{corner}"] = round(v, 4)
            if (v := parsed.get(f"tire_combined_slip_{corner}")) is not None:
                sample[f"cs_{corner}"] = round(v, 4)
            if (v := parsed.get(f"normalized_suspension_travel_{corner}")) is not None:
                sample[f"sus_n_{corner}"] = round(v, 4)
            if (v := parsed.get(f"suspension_travel_meters_{corner}")) is not None:
                sample[f"sus_m_{corner}"] = round(v, 4)
            # FH5 only — silently absent on FM
            if (v := parsed.get(f"tire_wear_{corner}")) is not None:
                sample[f"wear_{corner}"] = round(v, 4)
        # Front slip ratios — rears already stored above as slip_rl/slip_rr
        if (v := parsed.get("tire_slip_ratio_fl")) is not None:
            sample["slip_fl"] = round(abs(v), 4)
        if (v := parsed.get("tire_slip_ratio_fr")) is not None:
            sample["slip_fr"] = round(abs(v), 4)
        # Driving-line / AI-brake hints (signed bytes from Forza)
        if (v := parsed.get("normalized_driving_lane")) is not None:
            sample["lane"] = int(v)
        if (v := parsed.get("normalized_ai_brake_difference")) is not None:
            sample["ai_brk_diff"] = int(v)
        self.samples.append(sample)

    def close(self, lap_time_s: Optional[float] = None):
        # Honor None as None — the previous `or wall_clock` fallback masked
        # session-close-mid-lap as a fake completed lap. Caller is responsible
        # for passing the real Forza last_lap_time when the lap actually
        # finished. Wall-clock duration was a misleading approximation
        # anyway (inflated by pauses, idle time).
        self.ended_at   = time.time()
        self.lap_time_s = lap_time_s


    def to_dict(self) -> dict:
        return {
            "lap_number":    self.lap_number,
            "lap_time_s":    round(self.lap_time_s, 3) if self.lap_time_s else None,
            "max_speed_mph": round(self.max_speed, 1),
            "sample_count":  len(self.samples),
            "samples":       self.samples,
        }


def _lap_distance(lap: "LapRecord") -> Optional[float]:
    """Metres travelled within this lap = furthest sample distance minus the
    lap-start distance. None if the lap has no usable distance telemetry."""
    if lap is None or lap.start_distance_m is None or not lap.samples:
        return None
    dists = [s["distance_traveled_m"] for s in lap.samples
             if s.get("distance_traveled_m") is not None]
    if not dists:
        return None
    span = max(dists) - lap.start_distance_m
    return span if span > 0 else None


# A final lap that covered at least this fraction of a normal lap's distance
# is treated as completed (the driver crossed the line; the race just ended).
# Below it, the drive was abandoned mid-lap — drop it rather than store a
# bogus partial as a lap (the regression #146 removed).
_FINAL_LAP_COMPLETE_FRAC = 0.90


class Session:
    def __init__(self, game: str, started_at: datetime):
        self.game         = game
        self.started_at   = started_at
        self.session_id   = started_at.strftime("%Y-%m-%dT%H-%M-%S") + f"_{game}"
        self.last_packet  = time.time()
        self.packet_count = 0
        self.track        = "unknown"
        self.car          = "unknown"
        self.session_type = "unknown"

        self.current_lap_num = 0
        self.current_lap: Optional[LapRecord] = None
        self.completed_laps: list = []
        self.best_lap_time_s: Optional[float] = None
        self._last_seen_lap_time: Optional[float] = None
        # Wall-clock when last_lap_time most recently CHANGED (a new lap was
        # completed). Used by is_likely_race_end to detect "user just crossed
        # the final line" — distinguishes from a mid-race pause where the
        # last lap-line crossing was much earlier.
        self._last_lap_completed_at: Optional[float] = None
        # Diagnostic: last last_lap_time logged from a race_over packet, so
        # the journal shows what Forza actually transmits at race end
        # without spamming (these packets stream at ~60Hz post-race).
        self._race_over_diag_last: Optional[float] = -1.0

        self._motion_cache: dict = {}
        self._lap_cache: dict = {}

        self.race_type = None
        self._race_positions: list = []
        self.track_ordinal: Optional[int] = None
        self.car_class: Optional[int] = None
        self.car_pi: Optional[int] = None
        # Raw UDP fields kept verbatim — surface ordinal even when name
        # lookup fails ("Unknown Car (#641)") and let the UI render
        # drivetrain (FWD/RWD/AWD) + cylinders.
        self.car_ordinal: Optional[int] = None
        self.drivetrain_type: Optional[int] = None
        self.num_cylinders: Optional[int] = None
        self.car_manufacturer: Optional[str] = None
        self.car_year: Optional[int] = None
        self.weather_condition: Optional[str] = None
        self.track_temp_c: Optional[float] = None
        self.air_temp_c: Optional[float] = None
        self.tyre_compound: Optional[str] = None

        self.last_activity = time.time()

        # Race-end detection state (see docs/specs/race-end-detection.md)
        self._last_is_race_on: Optional[int] = None
        # Pause / restart awareness — see _update_race_state. Pausing in
        # Forza flips is_race_on 1→0 with current_race_time held steady;
        # restarting flips back to 1 with CRT reset to ~0. Race-end is
        # indistinguishable from a long pause via telemetry alone, so we
        # rely on the UDP-stop watchdog to close at end-of-race instead of
        # an aggressive is_race_on=0 streak counter (which fragmented every
        # AI race that paused for >0.5s).
        self._paused_since: Optional[float] = None
        self._paused_at_crt: Optional[float] = None
        self._should_close_for_restart: bool = False
        self.closed_reason: Optional[str] = None

        # Race-start detection: Forza ticks current_race_time during the
        # pre-race countdown, then RESETS it to ~0 the moment the race
        # actually begins. Real grid_pos is the race_position captured at
        # that reset moment — using that when available, falling back to
        # the mode-of-history helper otherwise.
        self._last_crt: Optional[float] = None
        self._grid_pos_at_start: Optional[int] = None

        # Live in-race delta vs THIS session's best lap — see
        # update_state(). Snapshotted from the session-best lap whenever a
        # new best is set in _transition_lap. None on lap 1 (no reference).
        self._delta_ref_time_s: Optional[float] = None
        self._delta_ref_timeline: list = []   # list[(dist_m_in_lap, t_s)]
        self._delta_ref_total_m: float = 0.0

        raw_path = storage_path() / "raw" / f"{self.session_id}.bin"
        try:
            self.raw_file = open(raw_path, "wb")
        except OSError as e:
            _log.error(f"Cannot open raw archive {raw_path}: {e} — raw recording disabled")
            self.raw_file = None
        _log.info(f"Session started: {self.session_id} (storage: {storage_path()})")

    def ingest(self, raw: bytes, parsed: dict):
        if self.raw_file:
            try:
                self.raw_file.write(struct.pack("<I", len(raw)) + raw)
            except OSError as e:
                _log.error(f"Raw write failed: {e} — closing raw archive")
                self.raw_file = None
        self.last_packet  = time.time()
        self.packet_count += 1

        if self._is_driving(parsed):
            self.last_activity = self.last_packet

        packet_type = parsed.get("_packet_type")

        if packet_type == "motion":
            self._motion_cache.update({
                k: v for k, v in parsed.items() if not k.startswith("_")
            })
            return

        if packet_type == "graphics":
            st = parsed.get("session_type", "unknown")
            if st and st != "unknown":
                self.session_type = st
            rp = parsed.get("race_position")
            # Only capture race_position when the race is actually live — Forza
            # broadcasts a phantom P1 during the pre-race countdown which would
            # otherwise be mis-cached as the grid position.
            if rp is not None and rp > 0 and parsed.get("is_race_on") == 1:
                self._race_positions.append(rp)
            if parsed.get("weather_condition") and self.weather_condition is None:
                self.weather_condition = parsed["weather_condition"]
            return

        if packet_type == "telemetry":
            if self._motion_cache:
                parsed = {**parsed, **self._motion_cache}
                self._motion_cache = {}
            if self._lap_cache:
                parsed = {**self._lap_cache, **parsed}
                self._lap_cache = {}

        if parsed.get("track", "unknown") != "unknown":
            self.track = parsed["track"]
        if parsed.get("track_ordinal") is not None and self.track_ordinal is None:
            self.track_ordinal = parsed["track_ordinal"]
        if parsed.get("car_class") is not None and self.car_class is None:
            _ordinal = parsed.get("car_ordinal")
            if _ordinal is None or _ordinal in FORZA_CARS:
                self.car_class = int(parsed["car_class"])
        if parsed.get("car_performance_index") is not None and self.car_pi is None:
            self.car_pi = int(parsed["car_performance_index"])
        if parsed.get("car_ordinal") is not None and self.car_ordinal is None:
            self.car_ordinal = int(parsed["car_ordinal"])
        if parsed.get("drivetrain_type") is not None and self.drivetrain_type is None:
            self.drivetrain_type = int(parsed["drivetrain_type"])
        if parsed.get("num_cylinders") is not None and self.num_cylinders is None:
            self.num_cylinders = int(parsed["num_cylinders"])
        if parsed.get("weather_condition") and self.weather_condition is None:
            self.weather_condition = parsed["weather_condition"]
        if parsed.get("track_temp_c") is not None and self.track_temp_c is None:
            self.track_temp_c = parsed["track_temp_c"]
        if parsed.get("air_temp_c") is not None and self.air_temp_c is None:
            self.air_temp_c = parsed["air_temp_c"]
        if parsed.get("session_type", "unknown") != "unknown":
            self.session_type = parsed["session_type"]
        if "car_ordinal" in parsed and self.car == "unknown":
            ordinal = parsed["car_ordinal"]
            car_info = FORZA_CARS.get(ordinal)
            if car_info:
                self.car              = car_info["name"]
                self.car_manufacturer = car_info["manufacturer"]
                self.car_year         = car_info["year"]
            else:
                # Unmapped ordinal — show "Unknown Car" in the UI rather than the raw
                # number. The user can override via the edit modal. Log the ordinal
                # once per session so it's easy to grep listener.log for additions
                # to data/fm8_cars_extended.csv. See pacefinderapp issue #6.
                self.car = "Unknown Car"
                _log.info(f"[{self.game}] Unmapped car_ordinal={ordinal} — displayed as 'Unknown Car'")

        rp = parsed.get("race_position")
        # Capture every race_position seen while is_race_on=1. The "real grid"
        # heuristic now lives in _grid_pos_from_history() — see that helper —
        # because Forza broadcasts a phantom P1 during the pre-race countdown
        # AND uses lap_number inconsistently across session types, so neither
        # signal alone gates this reliably.
        # Race-start detection: current_race_time RESETS to ~0 the moment
        # the race actually begins (after the countdown). The race_position
        # at that reset packet is the real grid slot — Forza broadcasts a
        # phantom P1 throughout the entire countdown that we want to skip.
        crt = parsed.get("current_race_time", 0) or 0

        # CRT-reset detection — lights-out fires a current_race_time reset
        # from a meaningful pre-race value (countdown ticks) to ~0. Same
        # signal serves two distinct cases:
        #   1) FIRST race-start in the session: latch grid + wipe LapRecord
        #      so it doesn't carry pre-race lobby/queue distance into the
        #      lap reference (#114).
        #   2) SUBSEQUENT race-start: user restarted from menu → close this
        #      session and let the next packet spawn fresh (#115). The
        #      previous restart detector lived in _update_race_state and
        #      could never fire because _last_crt had been mutated to crt
        #      by the time it ran — moving the check here uses the
        #      pre-update value.
        crt_reset = (self._last_crt is not None
                     and self._last_crt > 1.0
                     and crt < 0.5
                     and parsed.get("is_race_on") == 1)
        if crt_reset:
            if self._grid_pos_at_start is None:
                if rp is not None and rp > 0:
                    self._grid_pos_at_start = rp
                    _log.info(
                        f"[{self.game}] Race start detected — current_race_time "
                        f"reset {self._last_crt:.1f}s→{crt:.2f}s, grid=P{rp}"
                    )
                self._reset_to_race_start()
            elif not self._should_close_for_restart:
                self._should_close_for_restart = True
                self.closed_reason = "restart"
                _log.info(
                    f"[{self.game}] Race restart detected (CRT {self._last_crt:.1f}s→{crt:.2f}s) "
                    f"— closing current session"
                )

        # FM2023 fallback: when CRT didn't tick during the countdown, the
        # reset above never fires. Detect race-start instead via lap_number=0
        # with a small-but-positive CRT (we're inside the actual race lap 1).
        # Reset the LapRecord too — see #114.
        if (self._grid_pos_at_start is None
                and self.game in ("forza_motorsport", "forza_horizon_5")
                and parsed.get("is_race_on") == 1
                and (parsed.get("lap_number") or 0) == 0
                and 0.5 < crt < 3.0
                and rp is not None and rp > 0):
            self._grid_pos_at_start = rp
            self._reset_to_race_start()
            _log.info(
                f"[{self.game}] Race start detected (early-lap fallback) — "
                f"crt={crt:.2f}s, lap_number=0, grid=P{rp}"
            )
        self._last_crt = crt

        if rp is not None and rp > 0 and parsed.get("is_race_on") == 1:
            prev = self._race_positions[-1] if self._race_positions else None
            if not self._race_positions:
                ln = parsed.get("lap_number", 0) or 0
                _log.info(
                    f"[{self.game}] First captured race_position=P{rp} "
                    f"(lap_number={ln}, current_race_time={crt:.2f}s)"
                )
            elif prev is not None and rp != prev:
                ln = parsed.get("lap_number", 0) or 0
                _log.info(
                    f"[{self.game}] Position changed P{prev}→P{rp} "
                    f"(lap_number={ln}, current_race_time={crt:.2f}s, samples={len(self._race_positions)+1})"
                )
            self._race_positions.append(rp)

        llt = parsed.get("last_lap_time")
        if llt and 0 < llt < 600:
            if self._last_seen_lap_time != llt:
                # last_lap_time CHANGED → a new lap just completed at the
                # line. Stamp wall-clock for the race-end heuristic.
                self._last_lap_completed_at = time.time()
            self._last_seen_lap_time = llt
            # Backfill: Forza is sometimes one packet late updating last_lap_time
            # at the finish line, so _transition_lap fired with lap_time_s=0
            # → stored as None → lap stayed unmeasured. The very next packet
            # has the real value. If the most recent completed lap is missing
            # its time, this is the value to fill in.
            if (self.completed_laps
                    and self.completed_laps[-1].lap_time_s is None):
                last_lap = self.completed_laps[-1]
                last_lap.lap_time_s = llt
                if self.best_lap_time_s is None or llt < self.best_lap_time_s:
                    self.best_lap_time_s = llt
                if (llt >= MIN_VALID_LAP_S
                        and (self._delta_ref_time_s is None or llt < self._delta_ref_time_s)):
                    self._rebuild_delta_reference(last_lap, llt)
                _log.info(
                    f"[{self.game}] Backfilled lap {last_lap.lap_number} time: "
                    f"{llt:.3f}s (Forza late on last_lap_time at the line)"
                )

        lap_num = parsed.get("lap_number", 0)
        if lap_num and lap_num != self.current_lap_num:
            self._transition_lap(
                new_lap=lap_num,
                lap_time_s=parsed.get("last_lap_time"),
            )

        if self.current_lap is None:
            self.current_lap = LapRecord(self.current_lap_num)

        parsed["_t"] = time.time() - self.current_lap.started_at
        self.current_lap.add_sample(parsed)

        self._update_race_state(parsed)

    def _update_race_state(self, parsed):
        """Track pause / restart / race-end via is_race_on + current_race_time.

        - **Pause**: is_race_on flips 1→0 with current_race_time held steady
          (Forza freezes the race timer during the pause overlay). The session
          stays open; is_idle_timed_out() honors _paused_since with a long
          grace cap so AI races that pause for a phone call don't fragment.
        - **Restart**: is_race_on=1 with current_race_time just reset to ~0,
          on a session that already had race progress (grid latched). Mark
          _should_close_for_restart so protocol.py closes this session and
          the next packet spawns a fresh one.
        - **Race-end**: telemetry alone can't distinguish "abandoned mid-race"
          from "paused for a long time" until UDP stops, so we let the
          watchdog (UDP-stop timeout) close the session naturally. No early
          close on is_race_on=0 — the previous 0.5s threshold caused
          fragmentation on every AI-race pause.
        """
        new_is_race_on = parsed.get("is_race_on")
        if new_is_race_on is None:
            return

        # Restart detection moved to ingest() so it sees the pre-update
        # _last_crt value — the version that lived here could never fire.

        # Pause / resume tracking.
        if new_is_race_on == 0 and self._last_is_race_on == 1:
            self._paused_since = time.time()
            self._paused_at_crt = self._last_crt
            _log.info(
                f"[{self.game}] is_race_on 1→0 (pause or race-end) — "
                f"crt={self._last_crt or 0:.1f}s, completed_laps={len(self.completed_laps)}"
            )
        elif new_is_race_on == 1 and self._paused_since is not None:
            paused_dur = time.time() - self._paused_since
            _log.info(f"[{self.game}] is_race_on 0→1 — pause ended after {paused_dur:.1f}s")
            self._paused_since = None
            self._paused_at_crt = None

        self._last_is_race_on = new_is_race_on

    def _reset_to_race_start(self):
        """Re-anchor lap counting to Forza's actual lights-out state.
        Called when we detect race-start mid-session lifecycle.

        Two things have to be reset together — they were the cause of the
        'Last lap shows —' bug after #119:

        1. **current_lap_num back to 0.** Forza's lap_number can be stale
           when the listener joins (e.g. lap_number=1 carried over from a
           previous race attempt in the menu). The first packet's
           `if lap_num and lap_num != current_lap_num` gate fires a
           transition, setting current_lap_num to that stale value. After
           the actual race starts and the user completes the real lap 1,
           Forza sets lap_number=1 — but our current_lap_num is already 1,
           so no transition fires, no LapRecord gets closed, and
           completed_laps stays empty.
        2. **A fresh LapRecord(0)**, replacing whatever LapRecord was in
           flight. Resets samples / start_distance_m / etc. (the work the
           old LapRecord.reset_for_race_start did) AND fixes the
           lap_number mismatch above.
        """
        self.current_lap_num = 0
        self.current_lap = LapRecord(0)

    def _transition_lap(self, new_lap: int, lap_time_s: Optional[float] = None):
        # Forza is sometimes one packet late updating last_lap_time at the
        # finish line — the transition packet carries lap_time_s=0.0 and
        # the real value lands on the next packet. Treat 0 as None so the
        # backfill path in ingest can rescue it from _last_seen_lap_time.
        if lap_time_s == 0:
            lap_time_s = None
        if self.current_lap is not None:
            # Log what Forza gave us BEFORE close() applies its wall-clock
            # fallback, so when laps go missing later we can see whether the
            # cause was a bogus last_lap_time, a None, or a sub-MIN_VALID
            # value from Forza itself.
            samples_n = len(self.current_lap.samples)
            wall_dur = time.time() - self.current_lap.started_at
            self.current_lap.close(lap_time_s)
            if lap_time_s:
                if self.best_lap_time_s is None or lap_time_s < self.best_lap_time_s:
                    self.best_lap_time_s = lap_time_s
                # Live-delta reference: rebuild only when an in-session lap
                # beats our prior in-session best. Skip partials (no
                # lap_number guard — Forza uses lap_number=0 for race lap 1).
                if (lap_time_s >= MIN_VALID_LAP_S
                        and (self._delta_ref_time_s is None or lap_time_s < self._delta_ref_time_s)):
                    self._rebuild_delta_reference(self.current_lap, lap_time_s)
            _log.info(
                f"[{self.game}] Lap transition L{self.current_lap.lap_number}->L{new_lap} | "
                f"raw last_lap_time={lap_time_s} | stored lap_time_s={self.current_lap.lap_time_s} | "
                f"wall_clock={wall_dur:.2f}s | samples={samples_n}"
            )
            self.completed_laps.append(self.current_lap)
        self.current_lap_num = new_lap
        self.current_lap = LapRecord(new_lap)

    def _rebuild_delta_reference(self, lap: LapRecord, lap_time_s: float):
        """Snapshot a (dist_in_lap, t) timeline from the new session-best lap
        so update_state() can compute live delta on subsequent packets."""
        samples = lap.samples
        start_d = lap.start_distance_m
        if not samples or start_d is None:
            return
        timeline: list = []
        for s in samples:
            d = s.get("distance_traveled_m")
            if d is None:
                continue
            timeline.append((d - start_d, s["t"]))
        if len(timeline) < 2:
            return
        self._delta_ref_time_s = lap_time_s
        self._delta_ref_timeline = timeline
        self._delta_ref_total_m = timeline[-1][0]
        _log.info(
            f"[{self.game}] live-delta reference rebuilt from lap "
            f"{lap.lap_number} ({lap_time_s:.3f}s, {len(timeline)} pts, "
            f"{self._delta_ref_total_m:.0f}m)"
        )

    def _infer_forza_session_type(self) -> str:
        positions = self._race_positions
        if not positions:
            return "unknown"
        unique = set(positions)
        if len(unique) == 1 and next(iter(unique)) == 1:
            valid_laps = len([l for l in self.completed_laps if l.lap_time_s and l.lap_time_s > 0])
            return "time_trial" if valid_laps <= 3 else "practice"
        return "race"

    def _is_driving(self, parsed: dict) -> bool:
        return _is_driving(parsed)

    def is_timed_out(self) -> bool:
        return time.time() - self.last_packet > SESSION_TIMEOUT_S

    def is_idle_timed_out(self) -> bool:
        # Don't fire idle-timeout while is_race_on=1 — Forza keeps streaming
        # is_race_on=1 throughout pit stops, so a stationary stop in the
        # box must NOT be misread as race-ended.
        if self._last_is_race_on == 1:
            return False
        # Paused (is_race_on flipped 1→0 with race progress in flight). Give
        # a long grace before giving up so a phone call mid-AI-race doesn't
        # fragment the session. Beyond 10 minutes paused, assume abandoned.
        if self._paused_since is not None:
            return time.time() - self._paused_since > 600
        # Non-Forza or pre-race idle: fall through to the time-only check.
        return time.time() - self.last_activity > IDLE_TIMEOUT_S

    def is_likely_race_end(self) -> bool:
        """Heuristic to fire race-end fast (< ~5s) without waiting for the
        UDP-stop or 10-min idle cap. Distinguishes from a mid-race pause:

        - is_race_on must be 0 (user's not actively racing)
        - we must have at least one completed lap
        - is_race_on=0 must have persisted for 2+ s (avoids flicker)
        - last_lap_time must have changed within the last 10 s (i.e. the
          user just crossed a finish line and is_race_on dropped right
          after — that's the cross-the-final-line pattern)

        A mid-race pause fails the last condition: the most recent
        last_lap_time update was at lap N's crossing, many seconds before
        the pause, so the 10s window doesn't match.
        """
        if self._last_is_race_on != 0:
            return False
        if not self.completed_laps:
            return False
        if self._paused_since is None:
            return False
        if time.time() - self._paused_since < 2.0:
            return False
        if self._last_lap_completed_at is None:
            return False
        return time.time() - self._last_lap_completed_at <= 10.0

    def note_race_over(self, parsed: dict):
        """Forza emits the FINAL lap's last_lap_time in the is_race_on=0
        packet sent the instant you cross the line — the packet the parser
        used to drop entirely. Feed that time into the same machinery the
        in-race path uses (fresh-value detection + the missing-time
        backfill) so close()'s final-lap recovery has a real time to work
        with. Deliberately does NOT bump self.last_packet: race-end timing
        stays owned by the UDP-stop watchdog exactly as before."""
        llt = parsed.get("last_lap_time")
        # Diagnostic — log the first race_over packet and any time its
        # last_lap_time changes. This pins down, from the journal alone,
        # whether Forza even transmits the final lap's time post-line
        # (vs. always the prior lap's stale value or 0/None).
        if self._race_over_diag_last != llt:
            self._race_over_diag_last = llt
            _log.info(
                f"[{self.game}] race_over pkt — last_lap_time={llt} "
                f"_last_seen={self._last_seen_lap_time} "
                f"lap_number={parsed.get('lap_number')} "
                f"completed_laps={len(self.completed_laps)}"
            )
        if not (llt and 0 < llt < 600):
            return
        if self._last_seen_lap_time == llt:
            return
        self._last_seen_lap_time = llt
        self._last_lap_completed_at = time.time()
        # If the final lap already transitioned but Forza was late with its
        # time (stored None), fill it in — same as the in-race backfill.
        if self.completed_laps and self.completed_laps[-1].lap_time_s is None:
            self.completed_laps[-1].lap_time_s = llt
            if self.best_lap_time_s is None or llt < self.best_lap_time_s:
                self.best_lap_time_s = llt
        _log.info(
            f"[{self.game}] Race-over packet — final lap last_lap_time="
            f"{llt:.3f}s captured for recovery"
        )

    def _reference_lap_distance(self) -> Optional[float]:
        """Median travelled distance across completed laps — the yardstick
        for deciding whether the in-flight final lap actually finished.
        Median (not mean) so one short/long lap doesn't skew it."""
        dists = sorted(
            d for d in (_lap_distance(l) for l in self.completed_laps)
            if d is not None
        )
        if not dists:
            return None
        n = len(dists)
        return dists[n // 2] if n % 2 else (dists[n // 2 - 1] + dists[n // 2]) / 2

    def close(self) -> dict:
        if self.closed_reason is None:
            self.closed_reason = "timeout"
        if self.raw_file:
            try:
                self.raw_file.close()
            except OSError:
                pass

        if self.current_lap and self.current_lap.samples:
            # Recover the in-flight lap ONLY when Forza confirms it crossed
            # the line. The signal: _last_seen_lap_time differs from the
            # previous completed lap (Forza updates last_lap_time at the
            # finish line, so a fresh value means "this lap just ended"
            # and we missed the lap_number transition).
            #
            # The previous behaviour fell back to current_lap_time when the
            # last_lap_time check failed — but current_lap_time is just
            # "seconds since this lap started", with no statement about
            # whether the lap finished. So a user who stopped racing 35s
            # into a Mugello lap got their incomplete drive stored as a
            # 35s lap, which would beat their real 1:30 lap times and
            # become the session "best". See issue with the recovery path.
            #
            # "Did this final lap cross the line?" is answered by timing,
            # not by value: _last_lap_completed_at is stamped whenever
            # Forza posts a *fresh* last_lap_time (exact != change-detect
            # at the top of ingest). If that fresh value arrived AFTER the
            # final lap started, the lap finished at the line. If the last
            # change predates this lap, llt is stale (the prior lap's time)
            # and the driver stopped mid-lap → don't recover.
            #
            # The earlier guard compared llt to the *previous* completed
            # lap's time and skipped recovery when they were within 0.01s.
            # A consistent driver running the last two laps within 10 ms
            # silently lost the entire final lap (8-lap race stored as 7).
            inferred_time: Optional[float] = None
            recovery_source = "last_lap_time"
            llt = self._last_seen_lap_time
            crossed_line = (
                self._last_lap_completed_at is not None
                and self._last_lap_completed_at >= self.current_lap.started_at
            )
            if llt and 0 < llt < 600 and crossed_line:
                inferred_time = llt

            # Forza Motorsport zeroes last_lap_time the instant the race
            # ends — the final lap's official time is never transmitted
            # (race_over packets carry last_lap_time=0.0). When that's all
            # we have, fall back to the lap's own clock, but ONLY if the
            # distance travelled proves the lap actually completed. A
            # mid-lap abandon covers far less than a normal lap and is
            # still dropped (the partial-lap regression #146 removed).
            if inferred_time is None:
                ref_dist = self._reference_lap_distance()
                final_dist = _lap_distance(self.current_lap)
                if (ref_dist and final_dist
                        and final_dist >= _FINAL_LAP_COMPLETE_FRAC * ref_dist):
                    cand = max((s.get("t", 0) for s in self.current_lap.samples),
                               default=0)
                    if MIN_VALID_LAP_S <= cand < 600:
                        inferred_time = cand
                        recovery_source = "telemetry+distance"
                    else:
                        _log.info(
                            f"[{self.game}] Final lap {self.current_lap.lap_number} "
                            f"looks complete by distance ({final_dist:.0f}m vs "
                            f"ref {ref_dist:.0f}m) but lap clock implausible "
                            f"({cand:.1f}s) — not recovering"
                        )

            self.current_lap.close(inferred_time)
            if inferred_time:
                if self.best_lap_time_s is None or inferred_time < self.best_lap_time_s:
                    self.best_lap_time_s = inferred_time
                _log.info(
                    f"[{self.game}] Final lap {self.current_lap.lap_number} recovered "
                    f"| time={inferred_time:.3f}s (source={recovery_source})"
                )
            else:
                # Lap didn't complete — keep the LapRecord (its samples are
                # still useful for telemetry charts) but lap_time_s stays
                # None so the MIN_VALID_LAP_S filter drops it from
                # completed_laps when we recompute the best lap below.
                cur_t = self.current_lap.samples[-1].get("t", 0) if self.current_lap.samples else 0
                _log.info(
                    f"[{self.game}] Final lap {self.current_lap.lap_number} not recovered "
                    f"— last_lap_time wasn't updated (user stopped mid-lap at ~{cur_t:.1f}s)"
                )
            self.completed_laps.append(self.current_lap)

        # Drop incomplete laps before computing best / best_lap-derived stats.
        # MIN_VALID_LAP_S (config.py) filters anything obviously partial.
        # NOTE: Forza Motorsport uses lap_number=0 for the FIRST race lap
        # (not for an out-lap), so we deliberately do NOT filter on
        # lap_number > 0 here — that bug used to drop the entire first lap
        # of every Forza race. ACC's pit-exit out-lap is not relevant since
        # ACC support is parked (see docs/specs/park-acc-f1.md). If/when ACC
        # comes back, gate the lap_number > 0 check on game == "acc".
        completed_before = len(self.completed_laps)
        kept: list = []
        dropped_detail: list = []
        for lap in self.completed_laps:
            if lap.lap_time_s is not None and lap.lap_time_s >= MIN_VALID_LAP_S:
                kept.append(lap)
            else:
                dropped_detail.append(
                    f"L{lap.lap_number}={lap.lap_time_s if lap.lap_time_s is not None else 'None'}"
                )
        self.completed_laps = kept
        if dropped_detail:
            _log.info(
                f"[{self.game}] Dropped {len(dropped_detail)} incomplete lap(s) "
                f"(<{MIN_VALID_LAP_S}s): {', '.join(dropped_detail)}"
            )

        # Recompute best_lap_time_s from the filtered list — without this,
        # an out-lap's 13s could persist as the session's "best".
        valid_times = [lap.lap_time_s for lap in self.completed_laps if lap.lap_time_s and lap.lap_time_s > 0]
        self.best_lap_time_s = min(valid_times) if valid_times else None

        laps_summary = [
            {
                "lap_number":    lap.lap_number,
                "lap_time_s":    lap.lap_time_s,
                "max_speed_mph": lap.max_speed,
                "sample_count":  len(lap.samples),
                # Per-lap aggregates precomputed once at close so
                # /sessions/session/data is a pure SQL query.
                **compute_lap_aggregates(lap.samples),
            }
            for lap in self.completed_laps
        ]

        if self.game in ("forza_motorsport", "forza_horizon_5") and self.session_type == "unknown":
            self.session_type = self._infer_forza_session_type()

        # Grid + finish are recorded only when the race-start signal fired
        # (current_race_time reset). Without that, we don't know real grid
        # vs phantom — recording None is more honest than guessing.
        if self._grid_pos_at_start is not None and self._race_positions and self.session_type == "race":
            grid_pos   = self._grid_pos_at_start
            finish_pos = self._race_positions[-1]
        else:
            grid_pos   = None
            finish_pos = None

        valid_laps = len([l for l in self.completed_laps if l.lap_time_s and l.lap_time_s > 0])
        self.race_type = _classify_race_type(self._race_positions, valid_laps)

        has_enough_laps = len(self.completed_laps) >= 2
        has_valid_lap   = bool(self.best_lap_time_s and 0 < self.best_lap_time_s < 600)
        if not (has_enough_laps or has_valid_lap):
            _log.info(
                f"Session discarded — insufficient data "
                f"({len(self.completed_laps)} lap(s), "
                f"best_lap={'%.3f' % self.best_lap_time_s if self.best_lap_time_s else 'none'})"
            )
            return {}

        session_data = {
            "session_id":       self.session_id,
            "game":             self.game,
            "track":            self.track,
            "car":              self.car,
            "session_type":     self.session_type,
            "race_type":        self.race_type,
            "started_at":       self.started_at.isoformat(),
            "ended_at":         datetime.now().isoformat(),
            "packet_count":     self.packet_count,
            "best_lap_time_s":  round(self.best_lap_time_s, 3) if self.best_lap_time_s else None,
            "laps":             laps_summary,
            "grid_pos":         grid_pos,
            "finish_pos":       finish_pos,
            "track_ordinal":    self.track_ordinal,
            "car_class":        self.car_class,
            "car_pi":           self.car_pi,
            "car_ordinal":      self.car_ordinal,
            "drivetrain_type":  self.drivetrain_type,
            "num_cylinders":    self.num_cylinders,
            "car_manufacturer": self.car_manufacturer,
            "car_year":         self.car_year,
            "weather_condition": self.weather_condition,
            "track_temp_c":     self.track_temp_c,
            "air_temp_c":       self.air_temp_c,
            "closed_reason":    self.closed_reason,
            "tyre_compound":    self.tyre_compound,
        }

        # Synchronous: write the session row + per-lap aggregates so the
        # post-race modal can populate immediately. Fast (~50–100ms even on
        # the Pi) — single SQLite transaction with the laps in laps_summary.
        _db_write_session(session_data)

        # Background: per-sample compression (gzip + INSERT per lap), JSON
        # file mirrors, and track-reference rebuild. These together can take
        # 5–30s on the Pi for a multi-lap race; running them on a daemon
        # thread lets POST /finish return in ~100ms instead of ~30s, which
        # in turn unblocks the dashboard's "Finishing race…" placeholder.
        threading.Thread(
            target=_close_finalize_async,
            args=(self.session_id, list(self.completed_laps), session_data,
                  self.track, self.game),
            daemon=True,
        ).start()

        _log.info(
            f"Session closed (sync): {self.session_id} | "
            f"{self.packet_count} packets | {len(self.completed_laps)} laps | "
            f"best={self.best_lap_time_s:.3f}s — finalising in background" if self.best_lap_time_s
            else f"Session closed (sync): {self.session_id} | {self.packet_count} packets"
        )
        return session_data


def _close_finalize_async(session_id: str, completed_laps: list,
                          session_data: dict, track: Optional[str],
                          game: str):
    """The slow tail of session.close() — runs on a daemon thread so the
    main close call returns immediately. Order: lap_samples write
    (gzipped), JSON file mirrors, then track-references rebuild."""
    try:
        _store_session_lap_samples(session_id, completed_laps)
    except Exception as e:
        _log.error(f"close_finalize: lap_samples write failed for {session_id}: {e}")

    try:
        sp = storage_path()
        out_path = sp / "sessions" / f"{session_id}.json"
        with open(out_path, "w") as f:
            json.dump(session_data, f, indent=2)
        samples_path = sp / "sessions" / f"{session_id}_laps.json"
        with open(samples_path, "w") as f:
            json.dump([lap.to_dict() for lap in completed_laps], f, indent=2)
    except OSError as e:
        _log.error(f"close_finalize: JSON file write failed for {session_id}: {e}")

    try:
        _update_track_references_bg(track, game)
    except Exception as e:
        _log.error(f"close_finalize: track_references update failed for {session_id}: {e}")

    _log.info(f"Session finalised (async): {session_id}")


# ─── Shared State ─────────────────────────────────────────────────────────────

state = {
    "status":           "idle",
    "game":             None,
    "session_id":       None,
    "track":            None,
    "car":              None,
    "car_class":        None,
    "car_pi":           None,
    "session_type":     None,
    "started_at":       None,
    "packet_count":     0,
    "lap":              0,
    "best_lap_time_s":  None,
    "speed_mph":        0,
    "throttle_pct":     0,
    "brake_pct":        0,
    "gear":             0,
    "rpm":              0,
    "engine_max_rpm":   0,
    "steer":            0,
    "slip_rl":          0,
    "slip_rr":          0,
    "g_lat":            0,
    "g_lon":            0,
    "drs":              False,
    "tyre_compound":    None,
    "race_position":    None,
    "grid_pos":         None,
    "fuel_remaining_laps": None,
    "current_lap_time": None,
    "last_lap_time_s":  None,
    # Live delta vs THIS session's best lap (negative = ahead, positive = behind).
    # Populated when a session-best is set and we're past lap 1; null otherwise.
    "delta_to_best_s":  None,
    "tyre_fl":          None,
    "tyre_fr":          None,
    "tyre_rl":          None,
    "tyre_rr":          None,
    "last_packet_at":   None,
    "udp_received":     {"forza_motorsport": 0, "acc": 0, "f1": 0},
    "udp_rejected":     {"forza_motorsport": 0, "acc": 0, "f1": 0},
    "last_rejected_size": {"forza_motorsport": None, "acc": None, "f1": None},
    "udp_last_at":      {"forza_motorsport": None, "acc": None, "f1": None},
    "bound_ports": {},
}

active_sessions: dict = {}

# Latest fully-parsed packet, exposed via /debug/raw for live field inspection.
# Mutable dict so the router can read it without an import cycle.
last_parsed: dict = {}


def _interp_dist_to_t(timeline: list, target_d: float) -> Optional[float]:
    """Binary-search a sorted (dist_m, t_s) timeline for the bracket
    containing target_d, then linear-interp t between the two samples."""
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


def update_state(game: str, session: Session, parsed: dict):
    if "_packet_type" in parsed and parsed["_packet_type"] in ("motion", "lap_data", "graphics"):
        return
    # Snapshot the raw parsed packet for the /debug/raw inspector.
    last_parsed.clear()
    last_parsed.update({"_game": game, **parsed})
    state["status"]       = "receiving" if session._is_driving(parsed) else "idle"
    state["game"]         = game
    state["session_id"]   = session.session_id
    state["track"]        = session.track
    state["car"]          = session.car
    state["car_class"]    = session.car_class
    state["car_pi"]       = session.car_pi
    state["session_type"] = session.session_type
    state["started_at"]   = session.started_at.isoformat()
    state["packet_count"] = session.packet_count
    state["lap"]          = session.current_lap_num
    # Drive best_lap_time_s purely from THIS session's completed laps.
    # Forza's parsed["best_lap_time"] persists across races (the user's
    # personal best on the track), so trusting it would show a previous
    # race's PB on lap 1 of a new race. Worse for "Last" — shows the
    # last lap of the PREVIOUS race until the current race's lap 1 ends.
    state["best_lap_time_s"] = session.best_lap_time_s
    _driving = session._is_driving(parsed)
    state["speed_mph"]    = parsed.get("speed_mph", state["speed_mph"]) if _driving else 0
    state["throttle_pct"] = parsed.get("throttle_pct", state["throttle_pct"]) if _driving else 0
    state["brake_pct"]    = parsed.get("brake_pct", state["brake_pct"]) if _driving else 0
    state["gear"]         = parsed.get("gear", state["gear"])
    state["rpm"]          = parsed.get("rpm", parsed.get("current_engine_rpm", state["rpm"]))
    if parsed.get("engine_max_rpm", 0) > 2000:
        state["engine_max_rpm"] = parsed["engine_max_rpm"]
    state["steer"]        = round(parsed.get("steer", state["steer"]), 3) if _driving else 0
    state["slip_rl"]      = round(parsed.get("slip_ratio_rl", state["slip_rl"]), 4) if _driving else 0
    state["slip_rr"]      = round(parsed.get("slip_ratio_rr", state["slip_rr"]), 4) if _driving else 0
    state["g_lat"]        = round(parsed.get("g_lat", state["g_lat"]), 3)
    state["g_lon"]        = round(parsed.get("g_lon", state["g_lon"]), 3)
    state["drs"]          = parsed.get("drs", state["drs"])
    state["tyre_compound"]       = parsed.get("tyre_compound", state["tyre_compound"])
    # Race position: latest from packet history; grid is the first non-zero seen.
    # Clear on new sessions that haven't seen a position packet yet so the live
    # dashboard doesn't show stale values from the previous race.
    # Gate the entire position widget on the race-start signal. During
    # the countdown Forza broadcasts a phantom P1 with is_race_on=1, so
    # showing race_position from that window would mislead. Once
    # _grid_pos_at_start is set (current_race_time reset detected), we
    # have real position data and can populate the dashboard.
    # Grid position needs the countdown→race transition (current_race_time
    # reset) to be confident; otherwise we'd lock in the phantom P1 Forza
    # broadcasts during the countdown. Race position is safer — we'll show it
    # whenever we've clearly passed the countdown phase, even if the listener
    # missed the start-of-race packet boundary (e.g. dashboard opened
    # mid-race). "Past countdown" = at least one lap completed, OR
    # current_race_time has been observed > 5s.
    _past_countdown = bool(session.completed_laps) or (session._last_crt or 0) > 5
    if session._race_positions and (session._grid_pos_at_start is not None or _past_countdown):
        state["race_position"] = session._race_positions[-1]
    else:
        state["race_position"] = None
    state["grid_pos"] = session._grid_pos_at_start if session._race_positions else None
    state["fuel_remaining_laps"] = parsed.get("fuel_remaining_laps", state["fuel_remaining_laps"])
    state["current_lap_time"]    = parsed.get("current_lap_time", state["current_lap_time"])
    # Same reasoning as best_lap_time above — Forza broadcasts the previous
    # race's last_lap_time until the current race completes a lap. Source
    # from this session's completed laps only.
    if session.completed_laps and session.completed_laps[-1].lap_time_s:
        state["last_lap_time_s"] = session.completed_laps[-1].lap_time_s
    else:
        state["last_lap_time_s"] = None

    # Live in-race delta vs THIS session's best lap.
    # Reference is rebuilt in _transition_lap whenever a new in-session best
    # is set. We need: a reference timeline, the current lap's start distance,
    # and the current packet's distance_traveled + current_lap_time.
    delta_val = None
    if (_driving
            and session._delta_ref_timeline
            and session.current_lap is not None
            and session.current_lap.start_distance_m is not None):
        cur_d = parsed.get("distance_traveled")
        cur_t = parsed.get("current_lap_time")
        if cur_d is not None and cur_t is not None and cur_t > 0:
            d_in_lap = cur_d - session.current_lap.start_distance_m
            # Allow a small overshoot past lap end (5%) so the delta is visible
            # right at the finish line rather than blanking on the last sample.
            if 0 <= d_in_lap <= session._delta_ref_total_m * 1.05:
                ref_t = _interp_dist_to_t(session._delta_ref_timeline, d_in_lap)
                if ref_t is not None:
                    delta_val = round(cur_t - ref_t, 2)
                    # Defensive guard against the start_distance_m-stale bug:
                    # if we've been on this lap for >5s but d_in_lap is still
                    # tiny (<25m), start_distance_m was set too late or to a
                    # bogus value (e.g. session-start mid-lap). The interp
                    # collapses to ref_t≈0 and produces delta == cur_t, which
                    # reads as "+91s slower than best" when it really means
                    # "we don't know". Suppress + log for diagnosis.
                    if cur_t > 5 and d_in_lap < 25:
                        _log.warning(
                            f"[delta] suppressing suspicious delta — "
                            f"cur_t={cur_t:.1f}s d_in_lap={d_in_lap:.1f}m "
                            f"start_d={session.current_lap.start_distance_m:.1f} "
                            f"cur_d={cur_d:.1f} ref_total_m={session._delta_ref_total_m:.0f} "
                            f"ref_t={ref_t:.2f} timeline_len={len(session._delta_ref_timeline)} "
                            f"current_lap_num={session.current_lap_num} "
                            f"samples={len(session.current_lap.samples)}"
                        )
                        delta_val = None
    state["delta_to_best_s"] = delta_val
    for corner in ("fl", "fr", "rl", "rr"):
        v = parsed.get(f"tire_temp_{corner}")
        if v is None:
            v = parsed.get(f"tyre_surface_temp_{corner}")
        if v is None:
            v = parsed.get(f"tyre_core_temp_{corner}")
        if v is not None:
            state[f"tyre_{corner}"] = round(v, 1)
    state["last_packet_at"] = datetime.now().isoformat()
