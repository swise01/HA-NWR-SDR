import asyncio
import logging
import time
from datetime import datetime

from parsers.forza import FM_PACKET_SIZE, FM_PACKET_SIZE_FH, FM_PACKET_SIZE_FH6
from parsers.f1 import F1_HEADER_SIZE
from session.manager import Session, _is_driving, active_sessions, state, update_state

_log = logging.getLogger("pacefinder")


class TelemetryProtocol(asyncio.DatagramProtocol):
    def __init__(self, game: str, parser, debug_push=None):
        self.game         = game
        self.parser       = parser
        self._debug_push  = debug_push or (lambda _: None)
        self._logged_size = False

    def datagram_received(self, data: bytes, addr):
        state["udp_received"][self.game] = state["udp_received"].get(self.game, 0) + 1
        state["udp_last_at"][self.game] = datetime.now().isoformat(timespec="seconds")

        parsed = self.parser(data)
        if not parsed:
            # Discriminate between a real format failure (wrong size or unparseable
            # bytes) and an intentional skip (parser returns None when is_race_on=0,
            # i.e. the user is in a menu / pause / replay). Same-sized Forza packets
            # are valid — we just don't have a race to record into. Silence those
            # to keep the log focused on real problems.
            forza_known_size = (
                self.game == "forza_motorsport"
                and len(data) in (FM_PACKET_SIZE, FM_PACKET_SIZE_FH, FM_PACKET_SIZE_FH6)
            )
            if forza_known_size:
                return
            count = state["udp_rejected"].get(self.game, 0) + 1
            state["udp_rejected"][self.game] = count
            state["last_rejected_size"][self.game] = len(data)
            ts    = datetime.now().strftime("%H:%M:%S")
            hex16 = data[:16].hex(" ") if len(data) >= 16 else data.hex(" ")
            self._debug_push(f"{ts} [REJECTED] {self.game} {len(data)}B from {addr[0]}  hex={hex16}")
            if count == 1 or count % 100 == 0:
                _log.warning(
                    f"[{self.game}] packet #{count} from {addr[0]} rejected — "
                    f"size={len(data)} bytes  first16={hex16}. "
                    f"Forza expects {FM_PACKET_SIZE} (FM2023), {FM_PACKET_SIZE_FH} (FH4/FH5), or {FM_PACKET_SIZE_FH6} (FH6 observed), "
                    f"ACC expects >={100}, F1 expects >={F1_HEADER_SIZE}. "
                    f"Check Data Out settings."
                )
            return

        if parsed.get("_packet_type") == "race_over":
            # Forza's cross-the-final-line packet (is_race_on=0) carries the
            # final lap's time. Hand it to the active session for final-lap
            # recovery; never create a session or treat this as telemetry.
            # Race-end timing itself is unchanged — the watchdog still closes
            # on UDP-stop — but close() now has the real final lap time.
            sess = active_sessions.get(self.game)
            if sess is not None:
                sess.note_race_over(parsed)
            return

        ts    = datetime.now().strftime("%H:%M:%S")
        speed = parsed.get("speed_mph", 0)
        gear  = parsed.get("gear", parsed.get("current_engine_rpm", "?"))
        rpm   = parsed.get("rpm", parsed.get("current_engine_rpm", 0))
        ptype = parsed.get("_packet_type", "telemetry")
        self._debug_push(f"{ts} [UDP OK]  {self.game} {len(data)}B  {speed:.0f}mph  rpm={rpm:.0f}  gear={gear}  type={ptype}")

        driving = _is_driving(parsed)

        if self.game not in active_sessions:
            if not driving:
                return
            session = Session(self.game, datetime.now())
            active_sessions[self.game] = session
            if self.game == "forza_motorsport":
                if len(data) == FM_PACKET_SIZE_FH:
                    fmt_label = "FH5 (331-byte, track ordinal available)"
                elif len(data) == FM_PACKET_SIZE_FH6:
                    fmt_label = "FH6 (324-byte observed dashboard packet)"
                else:
                    fmt_label = "FM2023 (311-byte, no track in UDP)"
                _log.info(f"Forza packet format detected: {fmt_label}")

        session = active_sessions[self.game]

        if not driving:
            session.last_packet = time.time()
            ptype = parsed.get("_packet_type")
            if ptype == "motion":
                session._motion_cache.update(
                    {k: v for k, v in parsed.items() if not k.startswith("_") and v is not None}
                )
            elif ptype == "lap_data":
                session._lap_cache.update(
                    {k: v for k, v in parsed.items() if not k.startswith("_") and v is not None}
                )
                rp = parsed.get("race_position")
                if rp is not None and rp > 0:
                    session._race_positions.append(rp)
            elif ptype == "graphics":
                st = parsed.get("session_type", "unknown")
                if st and st != "unknown":
                    session.session_type = st
                rp = parsed.get("race_position")
                if rp is not None and rp > 0:
                    session._race_positions.append(rp)
            update_state(self.game, session, parsed)
            return

        if parsed.get("_packet_type") == "telemetry":
            if session._motion_cache:
                parsed = {**parsed, **session._motion_cache}
                session._motion_cache = {}
            if session._lap_cache:
                parsed = {**session._lap_cache, **parsed}
                session._lap_cache = {}

        session.ingest(data, parsed)
        update_state(self.game, session, parsed)

        # Restart detection — Session sees current_race_time reset to ~0
        # while a session is already in flight. Close the current session
        # right away so the next packet spawns a fresh one. We do NOT flip
        # state.status to race_ended (that would pop the post-race modal
        # mid-restart); the new session starting on the next packet keeps
        # the dashboard in 'receiving' continuously.
        # Race-end (cross-line, abandon-to-menu) is handled by the watchdog
        # timeout when UDP stops — telemetry alone can't distinguish a long
        # pause from a quiet abandon, so the cheap-and-correct close path is
        # "no packets for SESSION_TIMEOUT_S seconds".
        if session._should_close_for_restart:
            closed = active_sessions.pop(self.game, None)
            if closed is not None:
                _log.info(f"[{self.game}] Closing session — race restarted (CRT reset)")
                closed.close()
                # Clear live-only state so the dashboard doesn't show a
                # stale delta against the just-closed session's reference
                # while the next packet spawns the new one.
                state["delta_to_best_s"] = None

    def error_received(self, exc):
        _log.error(f"[{self.game}] UDP error: {exc}")

    def connection_lost(self, exc):
        _log.warning(f"[{self.game}] Connection lost: {exc}")
