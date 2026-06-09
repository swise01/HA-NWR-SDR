import asyncio
import logging

from config import IDLE_TIMEOUT_S, SESSION_TIMEOUT_S
from session.manager import active_sessions, state

_log = logging.getLogger("pacefinder")


async def _clear_race_ended():
    await asyncio.sleep(30)
    if state["status"] == "race_ended" and not active_sessions:
        state["status"] = "idle"


async def session_watchdog():
    while True:
        await asyncio.sleep(2)
        to_close = []
        for game, session in active_sessions.items():
            if session.is_timed_out():
                to_close.append((game, "no packets", "timeout"))
            elif session.is_likely_race_end():
                to_close.append((game, "race ended (cross-line + is_race_on=0)", "race_end"))
            elif session.is_idle_timed_out():
                to_close.append((game, "idle", "idle_timeout"))
        for game, reason, closed_reason in to_close:
            session = active_sessions.pop(game)
            _log.info(f"[{game}] Closing session — {reason} for >{IDLE_TIMEOUT_S if reason == 'idle' else SESSION_TIMEOUT_S}s")
            session.closed_reason = closed_reason
            session.close()
            if not active_sessions:
                state["status"]     = "race_ended"
                state["game"]       = None
                state["session_id"] = None
                # Clear live-only fields so /stream consumers don't see the
                # last active value frozen forever — particularly delta_to_best_s
                # which used to read +91s after a stale-state-on-close bug.
                state["delta_to_best_s"] = None
                state["current_lap_time"] = None
                state["race_position"] = None
                state["grid_pos"] = None
                _log.info("All sessions closed. Listening...")
                asyncio.create_task(_clear_race_ended())
