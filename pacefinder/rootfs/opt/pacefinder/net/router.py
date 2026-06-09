import asyncio
import gzip
import json
import socket
import time
import urllib.parse
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from net.perf import _perf_ctx, _perf_ring, _perf_client_ring, _PERF_LOG_THRESHOLD_MS


_accept_encoding_ctx: ContextVar = ContextVar("pf_accept_encoding", default="")

# Cap concurrent /stream clients so a tab-leaving or buggy poller can't
# spawn unbounded SSE coroutines on the Pi. 32 is generous for a household.
_STREAM_CLIENT_CAP = 32
_stream_clients = 0


def _redact_config(cfg: dict) -> dict:
    """Strip secrets before serializing config to a network client.

    The Anthropic key only lives on the server. With Access-Control-Allow-Origin
    set to '*' (so the dashboard works from any LAN host), returning the key
    over /config would let any web page the user visits on the same network
    exfiltrate it. Setup UI uses anthropic_api_key_set to render a 'key set'
    placeholder without ever receiving the value.
    """
    out = dict(cfg)
    key = out.get("anthropic_api_key") or ""
    out["anthropic_api_key"] = ""
    out["anthropic_api_key_set"] = bool(key)
    return out


def _safe_sid(sid: str) -> bool:
    """Reject session IDs that could escape the sessions/raw directories.

    sid flows into f-strings that become file paths (e.g. {sid}_laps.json).
    Without this guard, '../../etc/passwd' would resolve to an arbitrary read.
    Real sids look like '2026-05-01T14-32-00_forza_motorsport' — no slashes,
    no dots-leading, bounded length.
    """
    if not sid or len(sid) > 128:
        return False
    if "/" in sid or "\\" in sid or ".." in sid or sid.startswith("."):
        return False
    return True


def _csrf_ok(host_header: str, origin_header: str) -> bool:
    """Allow same-origin POSTs (Origin host == Host) or no Origin (curl, native).

    With Access-Control-Allow-Origin: *, browsers will happily send
    state-changing POSTs from any web page the user visits while on the LAN.
    This gate blocks that drive-by attack without breaking the dashboard
    (which is same-origin) or native callers (curl, pytest, the listener
    itself) that don't set an Origin header.
    """
    if not origin_header:
        return True
    try:
        origin_host = urlparse(origin_header).hostname or ""
    except ValueError:
        return False
    if not origin_host:
        return False
    host_only = (host_header or "").split(":", 1)[0].strip().lower()
    return origin_host.lower() == host_only

# Compress JSON/text bodies above this size when the client advertises gzip.
# Smaller payloads aren't worth the round-trip cost on a Pi.
_GZIP_MIN_BYTES = 860
_GZIP_TYPES = ("application/json", "text/", "application/javascript")


def _http_response(status: str, content_type: str, body: bytes, extra_headers: str = "") -> bytes:
    enc_header = ""
    if (
        len(body) >= _GZIP_MIN_BYTES
        and any(content_type.startswith(t) for t in _GZIP_TYPES)
        and "gzip" in _accept_encoding_ctx.get().lower()
    ):
        body = gzip.compress(body, compresslevel=6)
        enc_header = "Content-Encoding: gzip\r\nVary: Accept-Encoding\r\n"
    return (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"{enc_header}"
        f"Access-Control-Allow-Origin: *\r\n"
        f"Access-Control-Allow-Private-Network: true\r\n"
        f"Connection: close\r\n"
        f"{extra_headers}\r\n"
    ).encode() + body


def make_handler(ctx: dict):
    state                  = ctx["state"]
    config                 = ctx["config"]
    log                    = ctx["log"]
    PORTS                  = ctx["PORTS"]
    active_sessions        = ctx["active_sessions"]
    debug_clients          = ctx["debug_clients"]
    debug_buffer           = ctx["debug_buffer"]
    started_at             = ctx["started_at"]          # mutable list [float|None]
    static_dir             = ctx["static_dir"]
    DASHBOARD_HTML         = ctx["DASHBOARD_HTML"]
    SETUP_HTML             = ctx["SETUP_HTML"]
    ADMIN_HTML             = ctx["ADMIN_HTML"]
    TRACK_DETAIL_HTML      = ctx["TRACK_DETAIL_HTML"]
    SESSION_DETAIL_HTML    = ctx["SESSION_DETAIL_HTML"]
    CAR_DETAIL_HTML        = ctx["CAR_DETAIL_HTML"]
    CAR_INDEX_HTML         = ctx["CAR_INDEX_HTML"]
    CIRCUIT_INDEX_HTML     = ctx["CIRCUIT_INDEX_HTML"]
    SESSIONS_HTML          = ctx["SESSIONS_HTML"]
    SESSION_EVENTS_HTML    = ctx["SESSION_EVENTS_HTML"]
    HOME_HTML              = ctx["HOME_HTML"]
    TELEMETRY_HTML         = ctx["TELEMETRY_HTML"]
    DEBUG_RAW_HTML         = ctx["DEBUG_RAW_HTML"]
    DEBUG_PERF_HTML        = ctx["DEBUG_PERF_HTML"]
    last_parsed            = ctx["last_parsed"]
    get_local_ips          = ctx["get_local_ips"]
    disk_info              = ctx["disk_info"]
    save_config            = ctx["save_config"]
    storage_path           = ctx["storage_path"]
    effective_tracks       = ctx["effective_tracks"]
    FM2023_TRACKS          = ctx["FM2023_TRACKS"]
    FORZA_CARS             = ctx["FORZA_CARS"]
    db_sessions_list       = ctx["db_sessions_list"]
    db_needs_review_count  = ctx["db_needs_review_count"]
    db_sessions_since_count = ctx["db_sessions_since_count"]
    db_games_index         = ctx["db_games_index"]
    db_career_kpis         = ctx["db_career_kpis"]
    db_form_data           = ctx["db_form_data"]
    db_recent_sessions     = ctx["db_recent_sessions"]
    db_tracks_index        = ctx["db_tracks_index"]
    db_track_sessions      = ctx["db_track_sessions"]
    db_get_track_tip       = ctx["db_get_track_tip"]
    db_save_track_tip      = ctx["db_save_track_tip"]
    build_track_tip_prompt = ctx["build_track_tip_prompt"]
    call_claude_api        = ctx["call_claude_api"]
    db_connect             = ctx["db_connect"]
    db_lock                = ctx["db_lock"]
    db_get_ai_analysis     = ctx["db_get_ai_analysis"]
    db_save_ai_analysis    = ctx["db_save_ai_analysis"]
    db_update_session      = ctx["db_update_session"]
    db_drop_last_lap       = ctx["db_drop_last_lap"]
    db_delete_session      = ctx["db_delete_session"]
    db_write_learned_ordinal = ctx["db_write_learned_ordinal"]
    db_get_car_nickname = ctx["db_get_car_nickname"]
    db_get_car_nicknames = ctx["db_get_car_nicknames"]
    db_set_car_nickname = ctx["db_set_car_nickname"]
    db_get_lap_samples     = ctx["db_get_lap_samples"]
    db_get_all_lap_samples = ctx["db_get_all_lap_samples"]
    decode_samples         = ctx["decode_samples"]
    build_inject_packets   = ctx["build_inject_packets"]
    build_analysis_prompt  = ctx["build_analysis_prompt"]
    clear_race_ended       = ctx["clear_race_ended"]

    async def handle_status(reader, writer):
        # Per-request perf state — populated once we know the path.
        _perf_token = None
        _perf_started = time.perf_counter()
        _perf_method = "?"
        _perf_path = "?"
        # Wrap writer.write so we can sum response bytes for the perf log.
        _bytes_written = [0]
        _orig_write = writer.write
        def _counting_write(data):
            try:
                _bytes_written[0] += len(data)
            except TypeError:
                pass
            return _orig_write(data)
        writer.write = _counting_write
        try:
            # Read until the end of HTTP headers
            header_buf = b""
            while b"\r\n\r\n" not in header_buf:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=5)
                if not chunk:
                    break
                header_buf += chunk

            header_bytes, _, body_so_far = header_buf.partition(b"\r\n\r\n")
            header_str = header_bytes.decode("utf-8", errors="ignore")
            header_lines = header_str.split("\r\n")
            request_line = header_lines[0] if header_lines else ""
            parts        = request_line.split(" ")
            method       = parts[0] if parts else "GET"
            raw_url      = parts[1] if len(parts) > 1 else "/"
            path         = raw_url.split("?")[0]
            query_string = raw_url.split("?", 1)[1] if "?" in raw_url else ""

            _perf_method = method
            _perf_path = path
            _perf_token = _perf_ctx.set({"db_ms": 0.0})

            # Parse Content-Length so we read the full POST body, and capture
            # Accept-Encoding so _http_response can gzip JSON/text payloads.
            # Host + Origin feed the CSRF gate on POSTs and /browse below.
            content_length = 0
            accept_encoding = ""
            host_header = ""
            origin_header = ""
            for line in header_lines[1:]:
                lower = line.lower()
                if lower.startswith("content-length:"):
                    content_length = int(line.split(":", 1)[1].strip())
                elif lower.startswith("accept-encoding:"):
                    accept_encoding = line.split(":", 1)[1].strip()
                elif lower.startswith("host:"):
                    host_header = line.split(":", 1)[1].strip()
                elif lower.startswith("origin:"):
                    origin_header = line.split(":", 1)[1].strip()
            _accept_encoding_ctx.set(accept_encoding)

            if method == "POST" and not _csrf_ok(host_header, origin_header):
                writer.write(_http_response(
                    "403 Forbidden", "application/json",
                    b'{"error":"cross-origin POST blocked"}',
                ))
                await writer.drain()
                writer.close()
                return

            body_buf = body_so_far
            while len(body_buf) < content_length:
                chunk = await asyncio.wait_for(reader.read(content_length - len(body_buf)), timeout=5)
                if not chunk:
                    break
                body_buf += chunk

            raw_body = body_buf.decode("utf-8", errors="ignore")

            if path.startswith("/static/"):
                rel = path[len("/static/"):]
                static_file = static_dir / rel
                if static_file.is_file() and static_file.resolve().is_relative_to(static_dir.resolve()):
                    ext = static_file.suffix.lower()
                    mime = {"css": "text/css", "js": "application/javascript"}.get(ext.lstrip("."), "application/octet-stream")
                    writer.write(_http_response("200 OK", mime, static_file.read_bytes()))
                else:
                    writer.write(_http_response("404 Not Found", "text/plain", b"Not found"))

            elif path == "/":
                # Idle landing — moved from DASHBOARD_HTML to HOME_HTML.
                # Live dashboard now lives at /dashboard (below). Bookmarks
                # of / will land here; the top nav links to /dashboard.
                writer.write(_http_response("200 OK", "text/html", HOME_HTML.encode()))

            elif path == "/dashboard":
                writer.write(_http_response("200 OK", "text/html", DASHBOARD_HTML.encode()))

            elif path == "/home/data":
                # Single roll-up for the home page. Cheap: 4 queries against
                # already-indexed columns plus a uptime/storage snapshot.
                # See net/pages/home.py for the rendering side.
                with db_lock:
                    conn = db_connect()
                    try:
                        # Top circuits: most-driven first, capped at 5
                        circuits = [dict(r) for r in conn.execute(
                            "SELECT track, COUNT(*) as sessions_count, "
                            "COALESCE(SUM(lap_count), 0) as laps_count, "
                            "MIN(best_lap_time_s) as best_lap_s "
                            "FROM sessions "
                            "WHERE track IS NOT NULL AND track != '' AND track != 'unknown' "
                            "GROUP BY track "
                            "ORDER BY sessions_count DESC "
                            "LIMIT 5"
                        ).fetchall()]
                        # Top cars: same shape as /cars/data but capped
                        car_rows = [dict(r) for r in conn.execute(
                            "SELECT car_ordinal, "
                            "MIN(best_lap_time_s) as best_lap_s, "
                            "MAX(started_at)     as last_driven, "
                            "COUNT(*)            as sessions_count, "
                            "COALESCE(SUM(lap_count), 0) as laps_count, "
                            "MAX(car_class)      as car_class, "
                            "MAX(car_pi)         as car_pi "
                            "FROM sessions "
                            "WHERE car_ordinal IS NOT NULL "
                            "GROUP BY car_ordinal "
                            "ORDER BY sessions_count DESC "
                            "LIMIT 5"
                        ).fetchall()]
                        # Recent sessions: 5 most recent, with the bits the
                        # row template needs
                        recents = [dict(r) for r in conn.execute(
                            "SELECT session_id, started_at, track, car, "
                            "car_ordinal, car_class, car_pi, best_lap_time_s, "
                            "weather_condition, tyre_compound, track_temp_c, "
                            "race_type, session_type "
                            "FROM sessions "
                            "ORDER BY started_at DESC "
                            "LIMIT 5"
                        ).fetchall()]
                        # Last session (the very first recent, if any) gets
                        # extra lookups for the home hero card:
                        #   • PB lap time + session_id at this track in this car
                        #     (so the hero can show ±delta and link to the PB
                        #     session for context)
                        #   • last-session's own best lap_number, so the hero's
                        #     mini track outline can render via track_mini.js
                        last_sess = recents[0] if recents else None
                        pb_here = None
                        pb_here_sid = None
                        if last_sess and last_sess.get("track") and last_sess.get("car_ordinal") is not None:
                            r = conn.execute(
                                "SELECT session_id, best_lap_time_s "
                                "FROM sessions "
                                "WHERE track=? AND car_ordinal=? AND best_lap_time_s IS NOT NULL "
                                "ORDER BY best_lap_time_s ASC LIMIT 1",
                                (last_sess["track"], last_sess["car_ordinal"])
                            ).fetchone()
                            if r:
                                pb_here = r["best_lap_time_s"]
                                pb_here_sid = r["session_id"]
                        if last_sess:
                            blr = conn.execute(
                                "SELECT lap_number FROM laps "
                                "WHERE session_id=? AND lap_time_s IS NOT NULL "
                                "ORDER BY lap_time_s ASC LIMIT 1",
                                (last_sess["session_id"],)
                            ).fetchone()
                            last_sess["best_lap_number"] = blr["lap_number"] if blr else None
                            last_sess["pb_session_id"] = pb_here_sid
                        total_sessions = conn.execute(
                            "SELECT COUNT(*) FROM sessions"
                        ).fetchone()[0]
                    finally:
                        conn.close()

                # Resolve car names + nicknames once for every car we
                # reference (top_cars + recents).
                def _car_payload(ord_):
                    info = FORZA_CARS.get(int(ord_)) or {}
                    return {
                        "name": info.get("name"),
                        "year": info.get("year"),
                        "nickname": db_get_car_nickname(int(ord_)),
                    }

                top_cars = []
                for r in car_rows:
                    cp = _car_payload(r["car_ordinal"])
                    top_cars.append({
                        "ordinal": r["car_ordinal"],
                        "name": cp["name"],
                        "year": cp["year"],
                        "nickname": cp["nickname"],
                        "class": r["car_class"],
                        "pi": r["car_pi"],
                        "sessions_count": r["sessions_count"],
                        "laps_count": r["laps_count"],
                        "best_lap_s": r["best_lap_s"],
                    })

                for r in recents:
                    if r.get("car_ordinal") is not None:
                        cp = _car_payload(r["car_ordinal"])
                        r["car_name"] = cp["name"]
                        r["car_nickname"] = cp["nickname"]

                # Status: read from live `state` object so the home page
                # tells the driver whether to click into /dashboard.
                udp_last = state.get("udp_last_at", {}) if isinstance(state, dict) else {}
                last_pkt_iso = None
                for game_iso in udp_last.values():
                    if game_iso and (not last_pkt_iso or game_iso > last_pkt_iso):
                        last_pkt_iso = game_iso

                # Disk usage for the footer
                try:
                    disk = disk_info() or {}
                except Exception:
                    disk = {}

                udp_rx = state.get("udp_received", {}) if isinstance(state, dict) else {}
                udp_total = sum(int(v) for v in udp_rx.values() if v) if udp_rx else 0

                payload = {
                    "status": state.get("status") if isinstance(state, dict) else "idle",
                    "last_session": dict(last_sess) if last_sess else None,
                    "pb_at_track_s": pb_here,
                    "top_circuits": circuits,
                    "top_cars": top_cars,
                    "recent_sessions": recents,
                    "time_format": config.get("time_format", "24h"),
                    "stats": {
                        "total_sessions": total_sessions,
                        "udp_received_total": udp_total,
                        "last_packet_at": last_pkt_iso,
                        "storage_used_gb": disk.get("used_gb"),
                        "storage_total_gb": disk.get("total_gb"),
                    },
                }
                writer.write(_http_response("200 OK", "application/json",
                                            json.dumps(payload).encode()))

            elif path == "/home/worst-sector":
                # Answers "what's your biggest single leak?" — the
                # (track, sector) combo with the largest average gap
                # between your best sector and the theoretical best at
                # that track. Surfaces ONE focus card on Home; cheaper
                # than the watchlist (one SQL aggregation).
                # See docs/specs/home-worst-sector.md (brainstorm).
                with db_lock:
                    conn = db_connect()
                    try:
                        # Per session, the BEST sector achieved (across all
                        # laps in that session). Then average that across
                        # sessions and compare to track theoretical.
                        agg_rows = [dict(r) for r in conn.execute(
                            "WITH session_best AS ( "
                            "  SELECT s.track AS track, s.session_id AS session_id, "
                            "         MIN(l.s1_time_s) AS bs1, "
                            "         MIN(l.s2_time_s) AS bs2, "
                            "         MIN(l.s3_time_s) AS bs3 "
                            "  FROM sessions s "
                            "  JOIN laps l ON l.session_id = s.session_id "
                            "  WHERE s.track IS NOT NULL AND s.track != '' AND s.track != 'unknown' "
                            "    AND l.s1_time_s IS NOT NULL "
                            "    AND l.s2_time_s IS NOT NULL "
                            "    AND l.s3_time_s IS NOT NULL "
                            "  GROUP BY s.track, s.session_id "
                            ") "
                            "SELECT sb.track, "
                            "       AVG(sb.bs1) AS avg_bs1, "
                            "       AVG(sb.bs2) AS avg_bs2, "
                            "       AVG(sb.bs3) AS avg_bs3, "
                            "       COUNT(*)    AS session_count, "
                            "       tr.theoretical_s1_s AS th1, "
                            "       tr.theoretical_s2_s AS th2, "
                            "       tr.theoretical_s3_s AS th3 "
                            "FROM session_best sb "
                            "JOIN track_references tr "
                            "  ON tr.track = sb.track AND tr.reference_type = 'theoretical' "
                            "WHERE tr.theoretical_s1_s IS NOT NULL "
                            "  AND tr.theoretical_s2_s IS NOT NULL "
                            "  AND tr.theoretical_s3_s IS NOT NULL "
                            "GROUP BY sb.track "
                            "HAVING session_count >= 3"
                        ).fetchall()]
                    finally:
                        conn.close()

                # Find the (track, sector) with the largest avg gap.
                worst = None
                for r in agg_rows:
                    for n, avg_field, th_field in ((1, "avg_bs1", "th1"),
                                                   (2, "avg_bs2", "th2"),
                                                   (3, "avg_bs3", "th3")):
                        gap = r[avg_field] - r[th_field]
                        if gap <= 0.30:  # don't surface trivia
                            continue
                        if worst is None or gap > worst["avg_gap_s"]:
                            worst = {
                                "track": r["track"],
                                "sector": n,
                                "avg_gap_s": round(gap, 3),
                                "avg_sector_s": round(r[avg_field], 3),
                                "theoretical_sector_s": round(r[th_field], 3),
                                "session_count": r["session_count"],
                            }

                # Enrich with the track's PB session for the outline +
                # for a deep-link CTA.
                if worst:
                    with db_lock:
                        conn = db_connect()
                        try:
                            pb_row = conn.execute(
                                "SELECT s.session_id, l.lap_number "
                                "FROM sessions s JOIN laps l ON l.session_id=s.session_id "
                                "WHERE s.track = ? AND s.best_lap_time_s IS NOT NULL "
                                "  AND l.lap_time_s IS NOT NULL "
                                "  AND ABS(l.lap_time_s - s.best_lap_time_s) < 0.001 "
                                "ORDER BY s.best_lap_time_s ASC LIMIT 1",
                                (worst["track"],)
                            ).fetchone()
                        finally:
                            conn.close()
                    if pb_row:
                        worst["pb_session_id"] = pb_row["session_id"]
                        worst["pb_lap_number"] = pb_row["lap_number"]

                writer.write(_http_response("200 OK", "application/json",
                                            json.dumps(worst).encode()))

            elif path == "/home/regression-watchlist":
                # Surfaces (track, car) combos where the user's recent 3
                # sessions are SLOWER than the prior 3 — i.e. they're
                # getting worse. This is the page's "what should I work
                # on?" answer; see docs/specs/home-regression-watchlist.md
                # (brainstorm). Cheap: one SELECT + Python aggregation.
                with db_lock:
                    conn = db_connect()
                    try:
                        sess_rows = [dict(r) for r in conn.execute(
                            "SELECT session_id, track, car_ordinal, car_class, car_pi, "
                            "started_at, best_lap_time_s "
                            "FROM sessions "
                            "WHERE track IS NOT NULL AND track != '' AND track != 'unknown' "
                            "  AND car_ordinal IS NOT NULL "
                            "  AND best_lap_time_s IS NOT NULL "
                            "ORDER BY track, car_ordinal, started_at ASC"
                        ).fetchall()]
                    finally:
                        conn.close()

                # Group by (track, car_ordinal), chronological
                from collections import defaultdict
                combos = defaultdict(list)
                for s in sess_rows:
                    combos[(s["track"], s["car_ordinal"])].append(s)

                candidates = []
                for (track, car_ord), seqs in combos.items():
                    if len(seqs) < 6:
                        continue
                    recent = seqs[-3:]
                    prior  = seqs[-6:-3]
                    rmean = sum(x["best_lap_time_s"] for x in recent) / 3.0
                    pmean = sum(x["best_lap_time_s"] for x in prior)  / 3.0
                    delta = rmean - pmean
                    # Slower by ≥0.2s OR ≥1% of the prior mean (whichever
                    # is bigger) — guards against tracks with very short
                    # laps where small absolute deltas would still flag.
                    thresh = max(0.2, pmean * 0.01)
                    if delta < thresh:
                        continue
                    # Last 6 best laps for the row sparkline (chronological)
                    sparkline = [x["best_lap_time_s"] for x in seqs[-6:]]
                    car_pi    = next((x["car_pi"]    for x in reversed(seqs) if x["car_pi"]    is not None), None)
                    car_class = next((x["car_class"] for x in reversed(seqs) if x["car_class"] is not None), None)
                    candidates.append({
                        "track": track,
                        "car_ordinal": car_ord,
                        "car_pi": car_pi,
                        "car_class": car_class,
                        "delta_s": round(delta, 3),
                        "recent_mean_s": round(rmean, 3),
                        "prior_mean_s":  round(pmean, 3),
                        "sparkline": sparkline,
                        "last_session_id": seqs[-1]["session_id"],
                        "session_count": len(seqs),
                    })

                # Worst regression first; cap so Home doesn't bloat.
                candidates.sort(key=lambda c: c["delta_s"], reverse=True)
                candidates = candidates[:3]

                # Enrich: car name from FORZA_CARS + the track's overall PB
                # lap (any car) so the row outline matches the track shape.
                if candidates:
                    tracks_needed = {c["track"] for c in candidates}
                    with db_lock:
                        conn = db_connect()
                        try:
                            placeholders = ",".join("?" for _ in tracks_needed)
                            track_pb = {}
                            if tracks_needed:
                                pb_rows = conn.execute(
                                    f"SELECT s.track, s.session_id, l.lap_number "
                                    f"FROM sessions s JOIN laps l ON l.session_id=s.session_id "
                                    f"WHERE s.track IN ({placeholders}) "
                                    f"  AND s.best_lap_time_s IS NOT NULL "
                                    f"  AND l.lap_time_s IS NOT NULL "
                                    f"  AND ABS(l.lap_time_s - s.best_lap_time_s) < 0.001 "
                                    f"ORDER BY s.best_lap_time_s ASC",
                                    tuple(tracks_needed)
                                ).fetchall()
                            # Keep the FIRST row per track (= the overall PB)
                            for r in pb_rows:
                                track_pb.setdefault(r["track"], {
                                    "session_id": r["session_id"],
                                    "lap_number": r["lap_number"],
                                })
                        finally:
                            conn.close()
                    for c in candidates:
                        info = FORZA_CARS.get(int(c["car_ordinal"])) or {}
                        c["car_name"]     = info.get("name")
                        c["car_year"]     = info.get("year")
                        c["car_nickname"] = db_get_car_nickname(int(c["car_ordinal"]))
                        pb = track_pb.get(c["track"]) or {}
                        c["pb_session_id"] = pb.get("session_id")
                        c["pb_lap_number"] = pb.get("lap_number")

                writer.write(_http_response("200 OK", "application/json",
                                            json.dumps(candidates).encode()))

            elif path == "/setup":
                writer.write(_http_response("200 OK", "text/html", SETUP_HTML.encode()))

            elif path == "/setup/ips":
                uptime = int(time.time() - started_at[0]) if started_at[0] else 0
                payload = {
                    "ips": get_local_ips(),
                    "ports": config["ports"],
                    "uptime_s": uptime,
                    "udp_received": state["udp_received"],
                    "udp_last_at": state["udp_last_at"],
                }
                writer.write(_http_response("200 OK", "application/json", json.dumps(payload).encode()))

            elif path == "/config" and method == "GET":
                payload = {**_redact_config(config), "disk": disk_info()}
                writer.write(_http_response("200 OK", "application/json", json.dumps(payload, indent=2).encode()))

            elif path == "/config" and method == "POST":
                try:
                    incoming = json.loads(raw_body)
                except (json.JSONDecodeError, ValueError) as exc:
                    err = json.dumps({"error": f"Invalid JSON: {exc}"}).encode()
                    writer.write(_http_response("400 Bad Request", "application/json", err))
                else:
                    new_path = str(incoming.get("storage_path", config["storage_path"])).strip()
                    # Validate: try to create subdirs
                    try:
                        test = Path(new_path)
                        for sub in ["raw", "sessions", "logs"]:
                            (test / sub).mkdir(parents=True, exist_ok=True)
                    except OSError as exc:
                        err = json.dumps({"error": f"Cannot create storage path: {exc}"}).encode()
                        writer.write(_http_response("400 Bad Request", "application/json", err))
                    else:
                        config["storage_path"]      = new_path
                        config["session_timeout_s"] = int(incoming.get("session_timeout_s", config["session_timeout_s"]))
                        if "ports" in incoming:
                            config["ports"].update({
                                k: int(v) for k, v in incoming["ports"].items()
                                if k in config["ports"]
                            })
                        if "anthropic_api_key" in incoming:
                            # null  → explicit clear
                            # ""    → no-op (UI never sends the key it doesn't have)
                            # other → set
                            v = incoming["anthropic_api_key"]
                            if v is None:
                                config["anthropic_api_key"] = ""
                            else:
                                new_key = str(v).strip()
                                if new_key:
                                    config["anthropic_api_key"] = new_key
                        if "anthropic_model" in incoming:
                            config["anthropic_model"] = str(incoming["anthropic_model"]).strip()
                        if "time_format" in incoming:
                            tf = str(incoming["time_format"]).strip()
                            config["time_format"] = tf if tf in ("12h", "24h") else "24h"
                        if "debug_mode" in incoming:
                            config["debug_mode"] = bool(incoming["debug_mode"])
                        save_config(config)
                        msg = "Saved."
                        if incoming.get("ports") and incoming["ports"] != PORTS:
                            msg += " Restart required for port changes to take effect."
                        result = json.dumps({"ok": True, "message": msg, "disk": disk_info()}).encode()
                        writer.write(_http_response("200 OK", "application/json", result))

            elif path == "/status":
                status_payload = {**state, "debug_mode": config.get("debug_mode", False)}
                writer.write(_http_response("200 OK", "application/json", json.dumps(status_payload, indent=2).encode()))

            elif path == "/dashboard/records":
                # Lightweight "what are my records here?" lookup for the live
                # dashboard. Two cheap aggregates against indexed columns:
                #   • best_lap_time_s   — overall PB at this track (any car)
                #   • best_finish_pos   — best finish position ever in races
                # Fired once per track change by dashboard.js, not on every
                # packet — so it stays off the hot path.
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                track = qs.get("track", "")
                if not track or track == "unknown":
                    writer.write(_http_response("200 OK", "application/json",
                        b'{"best_lap_time_s":null,"best_finish_pos":null}'))
                else:
                    with db_lock:
                        conn = db_connect()
                        try:
                            r1 = conn.execute(
                                "SELECT MIN(best_lap_time_s) AS pb FROM sessions "
                                "WHERE track=? AND best_lap_time_s IS NOT NULL",
                                (track,)
                            ).fetchone()
                            r2 = conn.execute(
                                "SELECT MIN(finish_pos) AS bf FROM sessions "
                                "WHERE track=? AND finish_pos IS NOT NULL "
                                "  AND (race_type IN ('race','real','race_ai','ai','race_online') "
                                "       OR session_type='race')",
                                (track,)
                            ).fetchone()
                        finally:
                            conn.close()
                    writer.write(_http_response("200 OK", "application/json", json.dumps({
                        "best_lap_time_s": (r1["pb"] if r1 else None),
                        "best_finish_pos": (r2["bf"] if r2 else None),
                    }).encode()))

            elif path == "/debug/raw":
                writer.write(_http_response("200 OK", "text/html", DEBUG_RAW_HTML.encode()))

            elif path == "/debug/raw.json":
                writer.write(_http_response("200 OK", "application/json", json.dumps(last_parsed).encode()))

            elif path == "/debug/perf":
                # Two flavors: HTML inspector (default) and ?json=1 raw dump.
                if "json=1" in query_string:
                    payload = {
                        "server": list(_perf_ring),
                        "client": list(_perf_client_ring),
                    }
                    writer.write(_http_response("200 OK", "application/json", json.dumps(payload).encode()))
                else:
                    writer.write(_http_response("200 OK", "text/html", DEBUG_PERF_HTML.encode()))

            elif path == "/debug/perf/client" and method == "POST":
                # Rate limit: drop entries that arrive within 200ms of the last
                # entry from the same path. Cheap defense against polling spam.
                try:
                    payload = json.loads(raw_body) if raw_body else {}
                    now = time.time()
                    p = payload.get("path", "?")
                    last = next((e for e in reversed(_perf_client_ring) if e.get("path") == p), None)
                    if last is None or (now - last.get("ts", 0)) > 0.2:
                        _perf_client_ring.append({
                            "ts": now,
                            "path": p,
                            "ua": payload.get("ua", "")[:80],
                            "marks": payload.get("marks", {}),
                        })
                    writer.write(_http_response("204 No Content", "text/plain", b""))
                except Exception:
                    writer.write(_http_response("400 Bad Request", "text/plain", b"bad json"))

            elif path in ("/sessions", "/sessions/"):
                # Sessions is the core content surface — a filter mechanism
                # over every recorded session. See docs/specs/ia.md.
                writer.write(_http_response("200 OK", "text/html", SESSIONS_HTML.encode()))

            elif path == "/sessions/game":
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                name = qs.get("name", "")
                if name in ("acc", "f1"):
                    # ACC + F1 are parked — see docs/specs/park-acc-f1.md
                    writer.write(_http_response(
                        "404 Not Found", "text/plain",
                        b"This game's support is currently parked.",
                    ))
                else:
                    # forza_motorsport (or missing) → 301 to canonical /sessions
                    writer.write(_http_response(
                        "301 Moved Permanently", "text/plain", b"",
                        "Location: /sessions\r\n",
                    ))

            elif path == "/sessions/track":
                writer.write(_http_response("200 OK", "text/html", TRACK_DETAIL_HTML.encode()))

            elif path == "/sessions/session":
                writer.write(_http_response("200 OK", "text/html", SESSION_DETAIL_HTML.encode()))

            elif path == "/sessions/session/events":
                # Modal-only (docs/specs/mistakes-modal.md): served only as
                # the telemetry modal's embed; a direct hit 301s to the
                # telemetry page with the modal open.
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                if qs.get("embed") == "1":
                    writer.write(_http_response("200 OK", "text/html", SESSION_EVENTS_HTML.encode()))
                else:
                    loc = "/sessions/telemetry?id=" + urllib.parse.quote(qs.get("id", "")) + "&events=1"
                    writer.write(_http_response("301 Moved Permanently", "text/plain", b"",
                                                "Location: " + loc + "\r\n"))

            elif path == "/sessions/telemetry":
                writer.write(_http_response("200 OK", "text/html", TELEMETRY_HTML.encode()))

            elif path == "/sessions/data":
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                try:
                    _lim = min(max(int(qs.get("limit", "100") or "100"), 1), 2000)
                except ValueError:
                    _lim = 100
                result = db_sessions_list(_lim)
                writer.write(_http_response("200 OK", "application/json", json.dumps(result).encode()))

            elif path == "/sessions/needs-review":
                writer.write(_http_response("200 OK", "application/json",
                                            json.dumps({"count": db_needs_review_count()}).encode()))

            elif path == "/sessions/new-since":
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                writer.write(_http_response("200 OK", "application/json",
                    json.dumps({"count": db_sessions_since_count(qs.get("ts", ""))}).encode()))

            elif path == "/sessions/games":
                result = db_games_index()
                writer.write(_http_response("200 OK", "application/json", json.dumps(result).encode()))

            elif path == "/sessions/career":
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                game = qs.get("game") or None
                result = db_career_kpis(game)
                # Circuit progression tally (last-3 best laps per circuit) —
                # the headline improvement signal on Home per home-stats.md.
                up = dn = fl = 0
                for t in db_tracks_index(game):
                    tr = t.get("trend")
                    if   tr == "up": up += 1
                    elif tr == "dn": dn += 1
                    elif tr == "fl": fl += 1
                result["trend_improving"]  = up
                result["trend_regressing"] = dn
                result["trend_flat"]       = fl
                writer.write(_http_response("200 OK", "application/json", json.dumps(result).encode()))

            elif path == "/sessions/track-options":
                # Merged unique track-name list for the session edit modal dropdown.
                # Sources combined: FM2023_TRACKS hardcoded list +
                # FORZA_TRACKS values from CSVs (incl. fm8_tracks_extended.csv) +
                # learned_track_ordinals from prior user confirmations.
                # See docs/specs/post-race-track-dropdown.md.
                names = set(FM2023_TRACKS)
                names.update(effective_tracks().values())
                # Filter out the placeholder "unknown" entry — it's reserved for the
                # blank state in the UI and shouldn't appear as a selectable option.
                names.discard("unknown")
                result = sorted(names)
                writer.write(_http_response("200 OK", "application/json",
                                            json.dumps(result).encode()))

            elif path == "/cars":
                writer.write(_http_response("200 OK", "text/html", CAR_INDEX_HTML.encode()))

            elif path == "/circuits":
                writer.write(_http_response("200 OK", "text/html", CIRCUIT_INDEX_HTML.encode()))

            elif path == "/cars/data":
                # One row per distinct car_ordinal: counts, totals, best lap,
                # and the track where that best lap was set. Bounded by the
                # number of cars the user has actually driven (small), so a
                # single GROUP BY + a follow-up per-car lookup is fine.
                with db_lock:
                    conn = db_connect()
                    try:
                        rows = [dict(r) for r in conn.execute(
                            "SELECT car_ordinal, "
                            "MIN(best_lap_time_s) as best_lap_s, "
                            "MAX(started_at)     as last_driven, "
                            "COUNT(*)            as sessions_count, "
                            "COALESCE(SUM(lap_count), 0) as laps_count, "
                            "MAX(car_class)      as car_class, "
                            "MAX(car_pi)         as car_pi, "
                            "MAX(drivetrain_type) as drivetrain_type "
                            "FROM sessions "
                            "WHERE car_ordinal IS NOT NULL "
                            "GROUP BY car_ordinal "
                            "ORDER BY sessions_count DESC"
                        ).fetchall()]
                        # Find the track where each car's best lap was set
                        for row in rows:
                            ord_ = row["car_ordinal"]
                            best = row["best_lap_s"]
                            if best is not None:
                                t = conn.execute(
                                    "SELECT track FROM sessions "
                                    "WHERE car_ordinal=? AND best_lap_time_s=? "
                                    "LIMIT 1", (ord_, best)
                                ).fetchone()
                                row["best_at_track"] = t["track"] if t else None
                            else:
                                row["best_at_track"] = None
                    finally:
                        conn.close()
                # Resolve canonical name + nickname for each ordinal
                cars = []
                for row in rows:
                    ord_ = int(row["car_ordinal"])
                    info = FORZA_CARS.get(ord_) or {}
                    cars.append({
                        "ordinal": ord_,
                        "name": info.get("name"),
                        "manufacturer": info.get("manufacturer"),
                        "year": info.get("year"),
                        "nickname": db_get_car_nickname(ord_),
                        "class": row["car_class"],
                        "pi": row["car_pi"],
                        "drivetrain_type": row["drivetrain_type"],
                        "sessions_count": row["sessions_count"],
                        "laps_count": row["laps_count"],
                        "best_lap_s": row["best_lap_s"],
                        "best_at_track": row["best_at_track"],
                        "last_driven": row["last_driven"],
                    })
                writer.write(_http_response("200 OK", "application/json",
                                            json.dumps({"cars": cars}).encode()))

            elif path == "/cars/nicknames" and method == "GET":
                # Full {ordinal: nickname} map. Cheap lookup; no pagination.
                writer.write(_http_response("200 OK", "application/json",
                                            json.dumps(db_get_car_nicknames()).encode()))

            elif path == "/cars/nickname" and method == "POST":
                # Body: {"ordinal": int, "nickname": "..."}; nickname=""/null deletes.
                try:
                    body = json.loads(raw_body) if raw_body else {}
                    ordinal = int(body.get("ordinal"))
                except (ValueError, TypeError, json.JSONDecodeError):
                    writer.write(_http_response("400 Bad Request", "application/json",
                                                json.dumps({"error": "ordinal required"}).encode()))
                else:
                    nick = body.get("nickname")
                    db_set_car_nickname(ordinal, nick if nick else None)
                    writer.write(_http_response("200 OK", "application/json",
                                                json.dumps({"ok": True, "ordinal": ordinal,
                                                            "nickname": nick or None}).encode()))

            elif path.startswith("/cars/") and (
                path.count("/") == 2 or (path.count("/") == 3 and path.endswith("/data"))
            ):
                # /cars/<ordinal>          → HTML page
                # /cars/<ordinal>/data     → JSON aggregate for that car
                parts = path.split("/")  # ['', 'cars', '<ord>', ...]
                try:
                    ordinal = int(parts[2])
                except (ValueError, IndexError):
                    writer.write(_http_response("404 Not Found", "text/plain", b"Car not found"))
                else:
                    is_data = len(parts) == 4 and parts[3] == "data"
                    if not is_data:
                        writer.write(_http_response("200 OK", "text/html", CAR_DETAIL_HTML.encode()))
                    else:
                        # ── Build the aggregate payload for /cars/<ordinal>/data ──
                        car_info = FORZA_CARS.get(ordinal) or {}
                        nickname = db_get_car_nickname(ordinal)

                        with db_lock:
                            conn = db_connect()
                            try:
                                # All sessions in this car, newest-first for "last
                                # driven" + recent-list rendering. We sort lap-time
                                # ascending in Python after fetching since we also
                                # need recency ordering elsewhere.
                                sessions = [dict(r) for r in conn.execute(
                                    "SELECT session_id,track,car,started_at,ended_at,"
                                    "best_lap_time_s,lap_count,car_class,car_pi,"
                                    "drivetrain_type,num_cylinders,weather_condition,"
                                    "tyre_compound,track_temp_c "
                                    "FROM sessions WHERE car_ordinal=? "
                                    "ORDER BY started_at DESC",
                                    (ordinal,)
                                ).fetchall()]
                                # Sum total lap time across this car (laps with a
                                # recorded lap_time_s). Out-laps are NULL and don't
                                # contribute, which is the right behaviour.
                                total_sec = conn.execute(
                                    "SELECT COALESCE(SUM(l.lap_time_s),0) "
                                    "FROM laps l JOIN sessions s ON l.session_id=s.session_id "
                                    "WHERE s.car_ordinal=? AND l.lap_time_s IS NOT NULL",
                                    (ordinal,)
                                ).fetchone()[0]
                                # Theoretical-best per track for the gap calc.
                                track_names = list({s["track"] for s in sessions if s.get("track")})
                                theo_map = {}
                                if track_names:
                                    qs_ = ",".join("?" * len(track_names))
                                    theo_rows = conn.execute(
                                        f"SELECT track, theoretical_best_s FROM track_references "
                                        f"WHERE reference_type='theoretical' AND track IN ({qs_})",
                                        track_names
                                    ).fetchall()
                                    theo_map = {r["track"]: r["theoretical_best_s"] for r in theo_rows}
                            finally:
                                conn.close()

                        # If we have no sessions in this car AND no FORZA_CARS entry,
                        # treat as 404 — nothing to show.
                        if not sessions and not car_info:
                            writer.write(_http_response("404 Not Found", "application/json",
                                                        json.dumps({"error": "Car not found"}).encode()))
                        else:
                            # Pull class/PI/drivetrain from the most recent session
                            # where they're set — these don't drift across sessions
                            # for a given car_ordinal.
                            meta_src = next((s for s in sessions
                                             if s.get("car_class") is not None
                                                or s.get("car_pi") is not None
                                                or s.get("drivetrain_type") is not None),
                                            sessions[0] if sessions else {})
                            # Best-lap-ever in this car, plus its track
                            best_ever = None
                            for s in sessions:
                                if s.get("best_lap_time_s") is not None:
                                    if best_ever is None or s["best_lap_time_s"] < best_ever["best_lap_time_s"]:
                                        best_ever = {
                                            "session_id": s["session_id"],
                                            "best_lap_time_s": s["best_lap_time_s"],
                                            "track": s["track"],
                                            "started_at": s["started_at"],
                                        }
                            # Average lap across all laps in this car
                            laps_count = sum((s.get("lap_count") or 0) for s in sessions)
                            avg_lap = (total_sec / laps_count) if laps_count else None
                            # Per-track aggregates
                            tracks: dict = {}
                            for s in sessions:
                                t = s.get("track") or "unknown"
                                if t not in tracks:
                                    tracks[t] = {
                                        "track": t,
                                        "sessions_count": 0,
                                        "laps_count": 0,
                                        "last_session": None,
                                        "best_lap_s": None,
                                    }
                                tracks[t]["sessions_count"] += 1
                                tracks[t]["laps_count"] += s.get("lap_count") or 0
                                if not tracks[t]["last_session"] or (s.get("started_at") or "") > tracks[t]["last_session"]:
                                    tracks[t]["last_session"] = s.get("started_at")
                                blt = s.get("best_lap_time_s")
                                if blt is not None and (tracks[t]["best_lap_s"] is None or blt < tracks[t]["best_lap_s"]):
                                    tracks[t]["best_lap_s"] = blt
                            for t, agg in tracks.items():
                                theo = theo_map.get(t)
                                agg["theoretical_best_s"] = theo
                                agg["gap_to_theoretical"] = (
                                    round(agg["best_lap_s"] - theo, 3)
                                    if agg["best_lap_s"] is not None and theo else None
                                )
                            tracks_list = sorted(
                                tracks.values(),
                                key=lambda x: x["sessions_count"], reverse=True
                            )
                            # Resolve canonical name + year
                            payload = {
                                "car": {
                                    "ordinal": ordinal,
                                    "name": car_info.get("name"),
                                    "manufacturer": car_info.get("manufacturer"),
                                    "year": car_info.get("year"),
                                    "nickname": nickname,
                                    "class": meta_src.get("car_class"),
                                    "pi": meta_src.get("car_pi"),
                                    "drivetrain_type": meta_src.get("drivetrain_type"),
                                    "num_cylinders": meta_src.get("num_cylinders"),
                                },
                                "stats": {
                                    "total_sessions": len(sessions),
                                    "total_laps": laps_count,
                                    "total_seconds": round(total_sec, 1),
                                    "tracks_driven": len(tracks),
                                    "avg_lap_s": round(avg_lap, 3) if avg_lap else None,
                                    "last_driven": sessions[0].get("started_at") if sessions else None,
                                    "best_ever": best_ever,
                                },
                                "tracks": tracks_list,
                                "recent": sessions[:10],
                                "time_format": config.get("time_format", "24h"),
                            }
                            writer.write(_http_response("200 OK", "application/json",
                                                        json.dumps(payload).encode()))

            elif path == "/sessions/form":
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                rt   = qs.get("type", "all") or "all"
                last = int(qs.get("last", "10") or "10")
                result = db_form_data(rt if rt != "all" else None, last, qs.get("game") or None)
                writer.write(_http_response("200 OK", "application/json", json.dumps(result).encode()))

            elif path == "/sessions/recent":
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                _limit = int(qs.get("limit", "8") or "8")
                result = db_recent_sessions(_limit, qs.get("game") or None)
                writer.write(_http_response("200 OK", "application/json", json.dumps(result).encode()))

            elif path == "/sessions/tracks":
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                game_filter = qs.get("game", "") or None
                result = db_tracks_index(game_filter)
                writer.write(_http_response("200 OK", "application/json", json.dumps(result).encode()))

            elif path == "/sessions/track/data":
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                track_name = qs.get("name", "")
                game_filter = qs.get("game", "") or None
                sessions = db_track_sessions(track_name, game_filter)
                # Personal best across all sessions at this track + the
                # progress series (best lap per session, chronological) for
                # the hero chart, + theoretical-best with sector provenance.
                pb = None
                for s in sessions:
                    blt = s.get("best_lap_time_s")
                    if blt is not None and (pb is None or blt < pb["best_lap_time_s"]):
                        pb = {"best_lap_time_s": blt,
                              "session_id": s["session_id"],
                              "started_at": s.get("started_at")}
                # Chronological (oldest first) so the chart reads left→right
                progress = sorted(
                    [{"session_id": s["session_id"],
                      "started_at": s.get("started_at"),
                      "best_lap_s": s.get("best_lap_time_s")}
                     for s in sessions if s.get("best_lap_time_s") is not None],
                    key=lambda x: x["started_at"] or ""
                )
                with db_lock:
                    conn = db_connect()
                    try:
                        # Best lap's lap_number in the PB session — lets the
                        # circuit hero draw that lap's racing-line outline.
                        if pb:
                            lr = conn.execute(
                                "SELECT lap_number FROM laps WHERE session_id=? "
                                "AND lap_time_s IS NOT NULL ORDER BY lap_time_s ASC LIMIT 1",
                                (pb["session_id"],)
                            ).fetchone()
                            pb["lap_number"] = lr["lap_number"] if lr else None
                        theo_row = conn.execute(
                            "SELECT theoretical_s1_s, theoretical_s1_session_id, theoretical_s1_lap, "
                            "theoretical_s2_s, theoretical_s2_session_id, theoretical_s2_lap, "
                            "theoretical_s3_s, theoretical_s3_session_id, theoretical_s3_lap, "
                            "theoretical_best_s "
                            "FROM track_references "
                            "WHERE track=? AND reference_type='theoretical'",
                            (track_name,)
                        ).fetchone()
                    finally:
                        conn.close()
                writer.write(_http_response("200 OK", "application/json", json.dumps({
                    "sessions": sessions,
                    "personal_best": pb,
                    "progress": progress,
                    "theoretical": dict(theo_row) if theo_row else None,
                    "time_format": config.get("time_format", "24h"),
                }).encode()))

            elif path == "/sessions/track/tip":
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                track_name = qs.get("name", "")
                generate   = qs.get("generate", "") == "true"
                cached = db_get_track_tip(track_name)
                if cached:
                    writer.write(_http_response("200 OK", "application/json",
                                                json.dumps(cached).encode()))
                elif generate and config.get("anthropic_api_key", "").strip():
                    try:
                        stats = next((t for t in db_tracks_index() if t["track"] == track_name), {})
                        tip_prompt = build_track_tip_prompt(track_name, stats)
                        tip_text   = await asyncio.to_thread(call_claude_api, tip_prompt)
                        tip_text   = tip_text.strip().split("\n")[0][:200]
                        model_name = config.get("anthropic_model", "claude-sonnet-4-6")
                        db_save_track_tip(track_name, tip_text, model_name)
                        writer.write(_http_response("200 OK", "application/json",
                                                    json.dumps({"tip": tip_text, "generated_at": datetime.now().isoformat(), "model": model_name}).encode()))
                    except Exception as exc:
                        log.error(f"Track tip generation error: {exc}")
                        writer.write(_http_response("200 OK", "application/json", b'{"tip":null}'))
                else:
                    writer.write(_http_response("200 OK", "application/json", b'{"tip":null}'))

            elif path == "/sessions/confirm-data":
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                sid = qs.get("id", "")
                with db_lock:
                    conn = db_connect()
                    try:
                        cd_row = conn.execute(
                            "SELECT session_id,game,track,car,session_type,race_type,"
                            "started_at,ended_at,best_lap_time_s,lap_count,track_ordinal,"
                            "weather_condition,tyre_compound "
                            "FROM sessions WHERE session_id=?", (sid,)
                        ).fetchone()
                    finally:
                        conn.close()
                if not cd_row:
                    writer.write(_http_response("404 Not Found", "application/json",
                                                json.dumps({"error": "Session not found"}).encode()))
                else:
                    cd_dict = dict(cd_row)
                    # Merge FM2023's hardcoded canonical circuits with the CSV-backed
                    # FORZA_TRACKS so the post-race dropdown shows every known track,
                    # not just the FH5 ordinals. Same source-of-truth as
                    # /sessions/track-options. See docs/specs/post-race-track-dropdown.md.
                    names = set(FM2023_TRACKS)
                    names.update(effective_tracks().values())
                    names.discard("unknown")
                    track_names = sorted(names)
                    writer.write(_http_response("200 OK", "application/json", json.dumps({
                        "session":       cd_dict,
                        "track_list":    track_names,
                        "track_ordinal": cd_dict.get("track_ordinal"),
                    }).encode()))

            elif path == "/sessions/session/events-map":
                # Everything the all-events page needs in one request:
                # detected events + session meta + a downsampled track
                # outline (px,pz from a lap that has position samples) so
                # the client can draw the loop and place markers by
                # distance_norm. See net/pages/events.py.
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                sid = qs.get("id", "")
                if not sid:
                    writer.write(_http_response("400 Bad Request", "application/json",
                                                json.dumps({"error": "id required"}).encode()))
                else:
                    with db_lock:
                        conn = db_connect()
                        try:
                            srow = conn.execute(
                                "SELECT session_id,track,car,car_ordinal,started_at,"
                                "best_lap_time_s,race_type,session_type "
                                "FROM sessions WHERE session_id=?", (sid,)
                            ).fetchone()
                            ev_rows = [dict(r) for r in conn.execute(
                                "SELECT lap_number,event_type,distance_m,distance_norm,"
                                "severity,description FROM lap_events "
                                "WHERE session_id=? ORDER BY severity DESC", (sid,)
                            ).fetchall()]
                            # Pick a lap that has stored samples — prefer the
                            # best lap, else any. lap_samples rows are one per
                            # (session,lap); grab the lap_numbers present.
                            lap_nums = [r["lap_number"] for r in conn.execute(
                                "SELECT lap_number FROM lap_samples WHERE session_id=? "
                                "ORDER BY lap_number", (sid,)
                            ).fetchall()]
                        finally:
                            conn.close()
                    if not srow:
                        writer.write(_http_response("404 Not Found", "application/json",
                                                    json.dumps({"error": "Session not found"}).encode()))
                    else:
                        sess = dict(srow)
                        # Resolve car name like the other endpoints
                        ord_ = sess.get("car_ordinal")
                        if ord_ is not None:
                            info = FORZA_CARS.get(int(ord_)) or {}
                            if info.get("name"):
                                sess["car"] = f"{info.get('year','')} {info['name']}".strip()
                            nick = db_get_car_nickname(int(ord_))
                            if nick:
                                sess["car_nickname"] = nick
                        # Build a track outline from the first lap that has
                        # px/pz samples. Downsample to ~140 points.
                        track_xy = []
                        for ln in lap_nums:
                            data = db_get_lap_samples(sid, ln)
                            if not data or not data.get("samples"):
                                continue
                            sm = data["samples"]
                            if not all(("px" in s and "pz" in s) for s in sm[:1]):
                                continue
                            step = max(1, len(sm) // 140)
                            for i in range(0, len(sm), step):
                                s = sm[i]
                                if "px" in s and "pz" in s:
                                    track_xy.append({
                                        "x": s["px"], "y": s["pz"],
                                        "d": s.get("distance_norm", 0.0),
                                    })
                            if track_xy:
                                break
                        writer.write(_http_response("200 OK", "application/json",
                                                    json.dumps({
                                                        "session": sess,
                                                        "events": ev_rows,
                                                        "track_xy": track_xy,
                                                        "time_format": config.get("time_format", "24h"),
                                                    }).encode()))

            elif path == "/sessions/session/hero-delta":
                # Compute the delta between this session's best and second-best
                # laps as a function of distance along the lap. Returns ~100
                # (d, dt) pairs for the hero SVG to draw.
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                sid = qs.get("id", "")
                if not sid:
                    writer.write(_http_response("400 Bad Request", "application/json",
                                                json.dumps({"error": "id required"}).encode()))
                else:
                    with db_lock:
                        conn = db_connect()
                        try:
                            laps_rows = conn.execute(
                                "SELECT lap_number, lap_time_s FROM laps "
                                "WHERE session_id=? AND lap_time_s IS NOT NULL "
                                "ORDER BY lap_time_s ASC LIMIT 2",
                                (sid,)
                            ).fetchall()
                        finally:
                            conn.close()
                    if len(laps_rows) < 2:
                        writer.write(_http_response("200 OK", "application/json",
                                                    json.dumps({"available": False,
                                                                "reason": "Need at least 2 completed laps"}).encode()))
                    else:
                        best = dict(laps_rows[0])
                        comp = dict(laps_rows[1])
                        best_data = db_get_lap_samples(sid, best["lap_number"])
                        comp_data = db_get_lap_samples(sid, comp["lap_number"])
                        if not best_data or not comp_data:
                            writer.write(_http_response("200 OK", "application/json",
                                                        json.dumps({"available": False,
                                                                    "reason": "Per-lap samples not available"}).encode()))
                        else:
                            def _t_at(samples, d):
                                # Linear interp on distance_norm-sorted samples
                                lo, hi = 0, len(samples) - 1
                                while lo < hi:
                                    mid = (lo + hi) // 2
                                    if samples[mid].get("distance_norm", 0.0) < d:
                                        lo = mid + 1
                                    else:
                                        hi = mid
                                if lo == 0:
                                    return samples[0].get("t", 0.0)
                                a, b = samples[lo - 1], samples[lo]
                                da, db_ = a.get("distance_norm", 0.0), b.get("distance_norm", 0.0)
                                if db_ <= da:
                                    return a.get("t", 0.0)
                                f = (d - da) / (db_ - da)
                                return a.get("t", 0.0) + f * (b.get("t", 0.0) - a.get("t", 0.0))

                            bs = best_data["samples"]
                            cs = comp_data["samples"]
                            pts = []
                            for i in range(101):
                                d = i / 100.0
                                tb = _t_at(bs, d)
                                tc = _t_at(cs, d)
                                pts.append({"d": d, "dt": round(tc - tb, 3)})
                            writer.write(_http_response("200 OK", "application/json",
                                                        json.dumps({
                                                            "available": True,
                                                            "best": best,
                                                            "compare": comp,
                                                            "points": pts,
                                                        }).encode()))

            elif path == "/sessions/session/data":
                # Pure-SQL handler — per-lap aggregates are precomputed at session
                # close (see compute_lap_aggregates in db/store.py). Was reading
                # <sid>_laps.json from disk and iterating every sample on each
                # request, which made p95 500–1450 ms. See PR #63 / spec
                # docs/specs/perf-session-data-precompute.md.
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                sid = qs.get("id", "")
                with db_lock:
                    conn = db_connect()
                    try:
                        sess_row = conn.execute(
                            "SELECT session_id,game,track,car,session_type,race_type,started_at,ended_at,"
                            "best_lap_time_s,lap_count,ai_analysis,ai_analyzed_at,ai_model,"
                            "car_class,car_pi,car_ordinal,drivetrain_type,num_cylinders,"
                            "finish_pos,grid_pos,weather_condition,tyre_compound,track_temp_c,air_temp_c "
                            "FROM sessions WHERE session_id=?", (sid,)
                        ).fetchone()
                        lap_rows = conn.execute(
                            "SELECT lap_number,lap_time_s,max_speed_mph,"
                            "avg_throttle,avg_brake,avg_slip,peak_slip,slip_above_pct,"
                            "s1_time_s,s2_time_s,s3_time_s "
                            "FROM laps WHERE session_id=? ORDER BY lap_number",
                            (sid,)
                        ).fetchall() if sess_row else []
                        # Theoretical-best sectors for this track — used by the
                        # hero strip to compute "left on the table" against
                        # the lifetime ideal.
                        theo_row = conn.execute(
                            "SELECT theoretical_s1_s,theoretical_s2_s,theoretical_s3_s,"
                            "theoretical_best_s "
                            "FROM track_references WHERE track=? AND reference_type='theoretical'",
                            (sess_row["track"],)
                        ).fetchone() if sess_row else None
                        # Car-context aggregates (Card B): rank of this session
                        # against other sessions in the same car, plus the
                        # best ever in this car at this track.
                        car_ctx = None
                        if sess_row and sess_row["car_ordinal"] is not None:
                            ord_ = int(sess_row["car_ordinal"])
                            # Rank among sessions in this car AT THIS TRACK —
                            # ranking across mixed circuits is meaningless
                            # (a short track always "wins" on raw lap time).
                            same_car = conn.execute(
                                "SELECT session_id,track,best_lap_time_s,started_at "
                                "FROM sessions WHERE car_ordinal=? AND track=? "
                                "AND best_lap_time_s IS NOT NULL "
                                "ORDER BY best_lap_time_s ASC",
                                (ord_, sess_row["track"])
                            ).fetchall()
                            total_in_car = len(same_car)
                            rank_in_car = None
                            for i, r in enumerate(same_car):
                                if r["session_id"] == sid:
                                    rank_in_car = i + 1
                                    break
                            # Fastest in this car at this track (rows sorted asc)
                            best_here = None
                            if same_car:
                                r = same_car[0]
                                best_here = {
                                    "session_id": r["session_id"],
                                    "best_lap_time_s": r["best_lap_time_s"],
                                    "started_at": r["started_at"],
                                }
                            car_ctx = {
                                "rank_in_car": rank_in_car,
                                "total_in_car": total_in_car,
                                "best_in_car_at_track": best_here,
                            }
                    finally:
                        conn.close()
                if not sess_row:
                    writer.write(_http_response("404 Not Found", "application/json",
                                                json.dumps({"error": "Session not found"}).encode()))
                else:
                    sess_dict = dict(sess_row)
                    # Resolve the car name. Two legacy cases + the new
                    # car_ordinal column from Bundle 2:
                    #   1) `car` stored as a numeric string → look up
                    #   2) `car` is "Unknown Car" (or "unknown") AND we now
                    #      have car_ordinal → re-attempt lookup; if still
                    #      unmapped, surface the raw ordinal so the user can
                    #      identify it (see issue #6 / cars bundle)
                    car_val = sess_dict.get("car", "")
                    car_ord = sess_dict.get("car_ordinal")
                    if car_val and isinstance(car_val, str) and car_val.isdigit():
                        car_ord = int(car_val)
                    if car_ord is not None:
                        car_info = FORZA_CARS.get(int(car_ord))
                        if car_info:
                            sess_dict["car"] = f"{car_info.get('year','')} {car_info['name']}".strip()
                        elif not car_val or car_val.lower().startswith("unknown") or (isinstance(car_val, str) and car_val.isdigit()):
                            sess_dict["car"] = f"Unknown Car (#{car_ord})"
                        # Bundle 3: surface user-set nickname for this ordinal
                        # so the UI can display it in priority over the
                        # resolved/fallback name (see Bundle 3 PR).
                        sess_dict["car_nickname"] = db_get_car_nickname(int(car_ord))
                    laps = [dict(r) for r in lap_rows]
                    theo = dict(theo_row) if theo_row else None
                    # Lap events — same connection, cheap. Sorted by
                    # severity DESC so the UI can lift the top-N quickly.
                    with db_lock:
                        conn = db_connect()
                        try:
                            event_rows = [dict(r) for r in conn.execute(
                                "SELECT lap_number, event_type, distance_m, "
                                "distance_norm, severity, description "
                                "FROM lap_events WHERE session_id=? "
                                "ORDER BY severity DESC", (sid,)
                            ).fetchall()]
                        finally:
                            conn.close()
                    writer.write(_http_response("200 OK", "application/json",
                                                json.dumps({
                                                    "session": sess_dict,
                                                    "laps": laps,
                                                    "theoretical": theo,
                                                    "car_context": car_ctx,
                                                    "events": event_rows,
                                                    "time_format": config.get("time_format", "24h"),
                                                }).encode()))

            elif path == "/sessions/laps":
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                sid = qs.get("id", "")
                if not _safe_sid(sid):
                    writer.write(_http_response("400 Bad Request", "application/json", b'{"error":"bad id"}'))
                else:
                    laps_file = storage_path() / "sessions" / f"{sid}_laps.json"
                    try:
                        # Closed sessions are immutable on disk — let the
                        # browser cache aggressively. v0.7.1 perf pass.
                        writer.write(_http_response(
                            "200 OK", "application/json", laps_file.read_bytes(),
                            "Cache-Control: public, max-age=31536000, immutable\r\n",
                        ))
                    except OSError:
                        writer.write(_http_response("404 Not Found", "application/json", b"[]"))

            elif path == "/sessions/references":
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                track_q = qs.get("track", "")
                if not track_q:
                    writer.write(_http_response("400 Bad Request", "application/json",
                                                b'{"error":"track required"}'))
                else:
                    with db_lock:
                        conn = db_connect()
                        try:
                            rows = {
                                row["reference_type"]: row
                                for row in conn.execute(
                                    "SELECT * FROM track_references WHERE track=?", (track_q,)
                                ).fetchall()
                            }
                        finally:
                            conn.close()
                    result: dict = {}
                    if "best_lap" in rows:
                        r = rows["best_lap"]
                        # Fetch session date
                        with db_lock:
                            conn = db_connect()
                            try:
                                srow = conn.execute(
                                    "SELECT started_at FROM sessions WHERE session_id=?",
                                    (r["session_id"],)
                                ).fetchone()
                            finally:
                                conn.close()
                        # Get lap time from laps table
                        with db_lock:
                            conn = db_connect()
                            try:
                                lrow = conn.execute(
                                    "SELECT lap_time_s FROM laps WHERE session_id=? AND lap_number=?",
                                    (r["session_id"], r["lap_number"])
                                ).fetchone()
                            finally:
                                conn.close()
                        result["best_lap"] = {
                            "lap_time_s": lrow["lap_time_s"] if lrow else None,
                            "session_id": r["session_id"],
                            "session_date": (srow["started_at"] or "")[:10] if srow else "",
                            "lap_number": r["lap_number"],
                        }
                    if "theoretical" in rows:
                        r = rows["theoretical"]
                        def _sdate(sid):
                            if not sid:
                                return ""
                            with db_lock:
                                conn = db_connect()
                                try:
                                    row = conn.execute(
                                        "SELECT started_at FROM sessions WHERE session_id=?", (sid,)
                                    ).fetchone()
                                finally:
                                    conn.close()
                            return (row["started_at"] or "")[:10] if row else ""
                        result["theoretical"] = {
                            "theoretical_best_s": r["theoretical_best_s"],
                            "s1_s": r["theoretical_s1_s"],
                            "s1_session_date": _sdate(r["theoretical_s1_session_id"]),
                            "s2_s": r["theoretical_s2_s"],
                            "s2_session_date": _sdate(r["theoretical_s2_session_id"]),
                            "s3_s": r["theoretical_s3_s"],
                            "s3_session_date": _sdate(r["theoretical_s3_session_id"]),
                        }
                    writer.write(_http_response("200 OK", "application/json",
                                                json.dumps(result).encode()))

            elif path == "/sessions/reference-samples":
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                track_q = qs.get("track", "")
                ref_type = qs.get("type", "best_lap")
                if ref_type not in ("best_lap", "theoretical"):
                    ref_type = "best_lap"
                if not track_q:
                    writer.write(_http_response("400 Bad Request", "application/json",
                                                b'{"error":"track required"}'))
                else:
                    with db_lock:
                        conn = db_connect()
                        try:
                            row = conn.execute(
                                "SELECT samples_json FROM track_references "
                                "WHERE track=? AND reference_type=?",
                                (track_q, ref_type)
                            ).fetchone()
                        finally:
                            conn.close()
                    if row:
                        # samples_json is now gzipped (legacy rows are still
                        # accepted via the sniff in _decode_samples).
                        decoded = decode_samples(row["samples_json"])
                        writer.write(_http_response("200 OK", "application/json",
                                                    json.dumps(decoded).encode()))
                    else:
                        # No row yet for this track is normal (first session at
                        # a track, or before track_references is computed) —
                        # not a real "not found." Return an empty array as 200
                        # so it doesn't show up as a red 404 in dev tools. The
                        # client treats [] and 404+[] identically anyway.
                        writer.write(_http_response("200 OK", "application/json", b"[]"))

            elif path == "/sessions/lap-samples":
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                sid = qs.get("session_id", "")
                # Forza UDP lap_number is 0-indexed (race lap 1 = 0),
                # so 0 IS a valid value here — guard only on missing
                # session_id or a negative lap. Previously rejected
                # lap=0 as falsy, which broke per-track mini outlines
                # whenever a track's PB was set on its first lap.
                try:
                    lap_n = int(qs.get("lap", "0"))
                except ValueError:
                    lap_n = -1
                if not sid or lap_n < 0:
                    writer.write(_http_response("400 Bad Request", "application/json",
                                                b'{"error":"session_id required, lap must be >= 0"}'))
                else:
                    data = db_get_lap_samples(sid, lap_n)
                    if data:
                        samples = data["samples"]
                        # ?outline=1 — slim payload for the per-row mini
                        # outline + fingerprint glyphs on /sessions. Decimates
                        # to ≤80 points server-side and drops all fields
                        # except the six the renderers actually read. Cuts
                        # the wire payload (and JSON parse cost) by ~95% vs
                        # the full sample stream.
                        if qs.get("outline") == "1" and samples:
                            _OUTLINE_FIELDS = ("px", "py", "pz", "speed_mph",
                                               "throttle_pct", "brake_pct")
                            n_in = len(samples)
                            n_out = min(80, n_in)
                            step = n_in / n_out
                            slim = []
                            for i in range(n_out):
                                s = samples[int(i * step)]
                                slim.append({k: s[k] for k in _OUTLINE_FIELDS if k in s})
                            writer.write(_http_response("200 OK", "application/json",
                                                        json.dumps(slim).encode()))
                        else:
                            writer.write(_http_response("200 OK", "application/json",
                                                        json.dumps(samples).encode()))
                    else:
                        # Lap with no stored samples is normal for older sessions
                        # that pre-date the lap_samples migration — return an
                        # empty array as 200 so it doesn't read as a real error
                        # in dev tools. Client treats [] and 404+[] identically.
                        writer.write(_http_response("200 OK", "application/json", b"[]"))

            elif path == "/sessions/session/deepdive":
                # Compute the Deep Dive tab payload from a session's stored
                # lap_samples + the sessions/laps rows. Pure compute — no DB
                # writes, no external calls. See docs/specs/deep-dive-tab.md.
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                sid = qs.get("id", "")
                ref_lap = qs.get("ref")
                cmp_lap = qs.get("cmp")
                try:
                    ref_lap = int(ref_lap) if ref_lap is not None else None
                    cmp_lap = int(cmp_lap) if cmp_lap is not None else None
                except ValueError:
                    ref_lap = cmp_lap = None
                with db_lock:
                    conn = db_connect()
                    try:
                        sess_row = conn.execute(
                            "SELECT session_id,game,track,car,session_type,race_type,"
                            "best_lap_time_s,lap_count,grid_pos,finish_pos "
                            "FROM sessions WHERE session_id=?", (sid,)
                        ).fetchone()
                        lap_rows = conn.execute(
                            "SELECT lap_number,lap_time_s,max_speed_mph,"
                            "avg_throttle,avg_brake,avg_slip,peak_slip,slip_above_pct "
                            "FROM laps WHERE session_id=? ORDER BY lap_number",
                            (sid,)
                        ).fetchall() if sess_row else []
                    finally:
                        conn.close()
                if not sess_row:
                    writer.write(_http_response("404 Not Found", "application/json",
                                                json.dumps({"error": "Session not found"}).encode()))
                else:
                    laps_with_samples = db_get_all_lap_samples(sid)
                    from analysis.deepdive import compute_deepdive
                    payload = compute_deepdive(
                        sess=dict(sess_row),
                        laps=[dict(r) for r in lap_rows],
                        laps_with_samples=laps_with_samples,
                        ref_lap=ref_lap,
                        cmp_lap=cmp_lap,
                    )
                    writer.write(_http_response("200 OK", "application/json",
                                                json.dumps(payload).encode()))

            elif path == "/sessions/update" and method == "POST":
                try:
                    body_data = json.loads(raw_body)
                except (json.JSONDecodeError, ValueError) as exc:
                    writer.write(_http_response("400 Bad Request", "application/json",
                                                json.dumps({"error": str(exc)}).encode()))
                else:
                    sid = body_data.get("id", "")
                    if not _safe_sid(sid):
                        writer.write(_http_response("400 Bad Request", "application/json",
                                                    b'{"error":"bad id"}'))
                        await writer.drain()
                        writer.close()
                        return
                    sessions_dir = storage_path() / "sessions"
                    session_file = sessions_dir / f"{sid}.json"
                    laps_file    = sessions_dir / f"{sid}_laps.json"
                    try:
                        session_data = json.loads(session_file.read_text())
                    except OSError:
                        writer.write(_http_response("404 Not Found", "application/json",
                                                    json.dumps({"error": "Session not found"}).encode()))
                    else:
                        # Update track
                        if "track" in body_data:
                            session_data["track"] = body_data["track"]

                        # Update race_type
                        if "race_type" in body_data:
                            session_data["race_type"] = body_data["race_type"]

                        # Update track name
                        if "track" in body_data:
                            session_data["track"] = body_data["track"]

                        # Update car
                        if "car" in body_data:
                            session_data["car"] = body_data["car"]

                        # Update weather condition (Dry / Damp / Wet / Snow)
                        if "weather_condition" in body_data:
                            wc = body_data["weather_condition"]
                            session_data["weather_condition"] = wc if wc else None

                        # Update tyre compound (FM: Soft / Medium / Hard / Wet)
                        if "tyre_compound" in body_data:
                            tc = body_data["tyre_compound"]
                            session_data["tyre_compound"] = tc if tc else None

                        # Manual grid/finish override — Forza assesses penalties
                        # post-race in a screen we never see, so the captured
                        # finish_pos is the on-track result. Allow correction
                        # here so the recorded final classification matches the
                        # official one. Null clears.
                        if "grid_pos" in body_data:
                            v = body_data["grid_pos"]
                            session_data["grid_pos"] = int(v) if v is not None else None
                        if "finish_pos" in body_data:
                            v = body_data["finish_pos"]
                            session_data["finish_pos"] = int(v) if v is not None else None

                        # Learn a new track ordinal mapping
                        if "learned_ordinal" in body_data:
                            lo = body_data["learned_ordinal"]
                            try:
                                db_write_learned_ordinal(
                                    int(lo["ordinal"]),
                                    lo.get("game", "forza_motorsport"),
                                    str(lo["track_name"]),
                                )
                            except (KeyError, TypeError, ValueError):
                                pass

                        # Drop last lap
                        if body_data.get("drop_last_lap") and session_data.get("laps"):
                            session_data["laps"] = session_data["laps"][:-1]
                            # Recalculate best
                            valid = [l["lap_time_s"] for l in session_data["laps"] if l.get("lap_time_s")]
                            session_data["best_lap_time_s"] = round(min(valid), 3) if valid else None
                            # Drop from laps detail file too
                            try:
                                laps_detail = json.loads(laps_file.read_text())
                                if laps_detail:
                                    laps_detail = laps_detail[:-1]
                                    laps_file.write_text(json.dumps(laps_detail, indent=2))
                            except OSError:
                                pass

                        session_file.write_text(json.dumps(session_data, indent=2))

                        # Sync to SQLite
                        db_kwargs = {}
                        if "track" in body_data:
                            db_kwargs["track"] = body_data["track"]
                        if "race_type" in body_data:
                            db_kwargs["race_type"] = body_data["race_type"]
                        if "car" in body_data:
                            db_kwargs["car"] = body_data["car"]
                        if "weather_condition" in body_data:
                            wc = body_data["weather_condition"]
                            db_kwargs["weather_condition"] = wc if wc else None
                        if "tyre_compound" in body_data:
                            tc = body_data["tyre_compound"]
                            db_kwargs["tyre_compound"] = tc if tc else None
                        if "grid_pos" in body_data:
                            v = body_data["grid_pos"]
                            db_kwargs["grid_pos"] = int(v) if v is not None else None
                        if "finish_pos" in body_data:
                            v = body_data["finish_pos"]
                            db_kwargs["finish_pos"] = int(v) if v is not None else None
                        if db_kwargs:
                            db_update_session(sid, **db_kwargs)
                        if body_data.get("drop_last_lap"):
                            db_drop_last_lap(sid)

                        writer.write(_http_response("200 OK", "application/json",
                                                    json.dumps({"ok": True, "session": session_data}).encode()))

            elif path == "/sessions/delete" and method == "POST":
                # Permanently remove a session from DB tables AND backing
                # files on disk. Used by the Edit modal's Delete button and
                # by the bulk-cleanup script. No undo — caller is expected
                # to confirm before posting.
                try:
                    body_data = json.loads(raw_body)
                except (json.JSONDecodeError, ValueError) as exc:
                    writer.write(_http_response("400 Bad Request", "application/json",
                                                json.dumps({"error": str(exc)}).encode()))
                else:
                    sid = body_data.get("id", "")
                    if not _safe_sid(sid):
                        writer.write(_http_response("400 Bad Request", "application/json",
                                                    b'{"error":"bad id"}'))
                    else:
                        deleted = db_delete_session(sid)
                        sessions_dir = storage_path() / "sessions"
                        raw_dir      = storage_path() / "raw"
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
                                    log.warning(f"Could not remove {f}: {exc}")
                        writer.write(_http_response("200 OK", "application/json",
                                                    json.dumps({"ok": True, "deleted": deleted}).encode()))

            elif path == "/analyze":
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                sid   = qs.get("id", "")
                force = qs.get("force", "") == "true"
                if not _safe_sid(sid):
                    writer.write(_http_response("400 Bad Request", "application/json", b'{"error":"bad id"}'))
                    await writer.drain()
                    writer.close()
                    return
                sessions_dir  = storage_path() / "sessions"
                analysis_file = sessions_dir / f"{sid}_analysis.json"

                # Serve cached result unless caller requests a fresh one
                db_cached = db_get_ai_analysis(sid)
                if not force and db_cached:
                    writer.write(_http_response("200 OK", "application/json",
                                                json.dumps(db_cached).encode()))
                elif not force and analysis_file.exists():
                    writer.write(_http_response("200 OK", "application/json", analysis_file.read_bytes()))
                else:
                    # Get session from DB; fall back to JSON file
                    with db_lock:
                        conn = db_connect()
                        try:
                            sess_row = conn.execute(
                                "SELECT * FROM sessions WHERE session_id=?", (sid,)
                            ).fetchone()
                        finally:
                            conn.close()
                    session_data = dict(sess_row) if sess_row else None
                    if not session_data:
                        try:
                            session_data = json.loads((sessions_dir / f"{sid}.json").read_text())
                        except OSError:
                            session_data = None
                    try:
                        laps_data = json.loads((sessions_dir / f"{sid}_laps.json").read_text())
                    except OSError:
                        laps_data = []
                    if not session_data:
                        writer.write(_http_response("404 Not Found", "application/json",
                                                    json.dumps({"error": "Session not found"}).encode()))
                    else:
                        track = session_data.get("track", "unknown")
                        # Pull last 3 historical sessions at same track from DB
                        historical = []
                        if track and track != "unknown":
                            hist_rows = db_track_sessions(track)
                            historical = [h for h in hist_rows if h["session_id"] != sid][:3]
                        try:
                            prompt   = build_analysis_prompt(session_data, laps_data, historical)
                            analysis = await asyncio.to_thread(call_claude_api, prompt)
                            result_obj = {
                                "session_id":  sid,
                                "analyzed_at": datetime.now().isoformat(),
                                "model":       config.get("anthropic_model", "claude-sonnet-4-6"),
                                "cached":      False,
                                "analysis":    analysis,
                            }
                            analysis_file.write_text(json.dumps(result_obj, indent=2))
                            db_save_ai_analysis(sid, analysis,
                                                config.get("anthropic_model", "claude-sonnet-4-6"))
                            writer.write(_http_response("200 OK", "application/json",
                                                        json.dumps(result_obj).encode()))
                        except ValueError as exc:
                            writer.write(_http_response("400 Bad Request", "application/json",
                                                        json.dumps({"error": str(exc)}).encode()))
                        except Exception as exc:
                            log.error(f"Claude API error: {exc}")
                            writer.write(_http_response("502 Bad Gateway", "application/json",
                                                        json.dumps({"error": f"API error: {exc}"}).encode()))

            elif path == "/reset" and method == "POST":
                for game in PORTS:
                    state["udp_received"][game] = 0
                    state["udp_rejected"][game] = 0
                    state["last_rejected_size"][game] = None
                writer.write(_http_response("200 OK", "application/json", b'{"ok":true}'))

            elif path == "/finish" and method == "POST":
                closed = []
                for game, session in list(active_sessions.items()):
                    session.close()
                    active_sessions.pop(game)
                    closed.append(session.session_id)
                if closed:
                    state["status"] = "race_ended"
                    state["game"] = None
                    asyncio.create_task(clear_race_ended())
                writer.write(_http_response("200 OK", "application/json",
                                            json.dumps({"ok": True, "closed": closed}).encode()))

            elif path == "/admin" and method == "GET":
                writer.write(_http_response("200 OK", "text/html", ADMIN_HTML.encode()))

            elif path == "/admin/inject" and method == "POST":
                try:
                    p = json.loads(raw_body)
                except (json.JSONDecodeError, ValueError) as exc:
                    err = json.dumps({"error": f"Invalid JSON: {exc}"}).encode()
                    writer.write(_http_response("400 Bad Request", "application/json", err))
                else:
                    game = p.get("game", "forza_motorsport")
                    if game not in PORTS:
                        err = json.dumps({"error": f"Unknown game: {game}"}).encode()
                        writer.write(_http_response("400 Bad Request", "application/json", err))
                    else:
                        try:
                            packets = build_inject_packets(game, p)
                            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            for pkt in packets:
                                sock.sendto(pkt, ("127.0.0.1", PORTS[game]))
                            sock.close()
                            result = json.dumps({"ok": True, "sent": len(packets)}).encode()
                            writer.write(_http_response("200 OK", "application/json", result))
                        except Exception as exc:
                            err = json.dumps({"error": str(exc)}).encode()
                            writer.write(_http_response("500 Internal Server Error", "application/json", err))

            elif path == "/browse":
                # Path picker on the Setup page — enumerates directories on
                # the Pi, which is information disclosure if hit from a
                # foreign origin. Gate the same way as POSTs: same-origin or
                # no Origin (curl, native test harness).
                if not _csrf_ok(host_header, origin_header):
                    writer.write(_http_response(
                        "403 Forbidden", "application/json",
                        b'{"error":"cross-origin blocked"}',
                    ))
                    await writer.drain()
                    writer.close()
                    return
                qs = {k: urllib.parse.unquote_plus(v)
                      for pair in query_string.split("&") if "=" in pair
                      for k, v in [pair.split("=", 1)]}
                browse_path = qs.get("path", "/") or "/"
                try:
                    p = Path(browse_path)
                    exists = p.is_dir()
                    entries = []
                    if exists:
                        try:
                            for item in sorted(p.iterdir()):
                                if item.is_dir() and not item.name.startswith("."):
                                    entries.append({"name": item.name})
                        except PermissionError:
                            pass
                    result = {
                        "path":          str(p.resolve()) if exists else str(p),
                        "parent":        str(p.parent),
                        "exists":        exists,
                        "parent_exists": p.parent.is_dir(),
                        "entries":       entries,
                    }
                except Exception as exc:
                    result = {
                        "path": browse_path, "parent": None,
                        "exists": False, "parent_exists": False,
                        "entries": [], "error": str(exc),
                    }
                writer.write(_http_response("200 OK", "application/json", json.dumps(result).encode()))

            elif path == "/debug-stream":
                q: asyncio.Queue = asyncio.Queue(maxsize=2000)
                debug_clients.append(q)
                writer.write(
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: text/event-stream\r\n"
                    b"Cache-Control: no-cache\r\n"
                    b"Access-Control-Allow-Origin: *\r\n"
                    b"Connection: keep-alive\r\n\r\n"
                )
                for line in list(debug_buffer):
                    writer.write(f"data: {json.dumps(line)}\n\n".encode())
                await writer.drain()
                try:
                    while True:
                        line = await q.get()
                        writer.write(f"data: {json.dumps(line)}\n\n".encode())
                        await writer.drain()
                finally:
                    if q in debug_clients:
                        debug_clients.remove(q)

            elif path == "/stream":
                global _stream_clients
                if _stream_clients >= _STREAM_CLIENT_CAP:
                    writer.write(_http_response(
                        "503 Service Unavailable", "text/plain",
                        b"too many stream clients",
                    ))
                else:
                    _stream_clients += 1
                    try:
                        writer.write(
                            b"HTTP/1.1 200 OK\r\n"
                            b"Content-Type: text/event-stream\r\n"
                            b"Cache-Control: no-cache\r\n"
                            b"Access-Control-Allow-Origin: *\r\n"
                            b"Connection: keep-alive\r\n\r\n"
                        )
                        # Idle-aware emit: 10 Hz when a session is live, 0.5 Hz
                        # when idle. After 60s continuous idle, close so a
                        # forgotten tab can't stream MBs overnight. Explicit
                        # disconnect handling so a dead client doesn't keep
                        # us busy serializing JSON nobody will read.
                        idle_since = None
                        while True:
                            is_idle = state.get("status") == "idle"
                            if is_idle:
                                if idle_since is None:
                                    idle_since = time.monotonic()
                                elif time.monotonic() - idle_since > 60:
                                    writer.write(b"event: bye\ndata: idle-timeout\n\n")
                                    try:
                                        await writer.drain()
                                    except (ConnectionError, BrokenPipeError):
                                        pass
                                    break
                            else:
                                idle_since = None
                            data = f"data: {json.dumps({**state, 'debug_mode': config.get('debug_mode', False)})}\n\n"
                            writer.write(data.encode())
                            try:
                                await writer.drain()
                            except (ConnectionError, BrokenPipeError):
                                break
                            if writer.is_closing():
                                break
                            await asyncio.sleep(2.0 if is_idle else 0.1)
                    finally:
                        _stream_clients -= 1

            elif path == "/system/load":
                # Pi system stats — CPU%, load avg, memory, temp, disk.
                # Cheap (~1ms): reads /proc + /sys directly. Returns nulls on
                # Mac/Windows so the same widget works in dev. Surfaced in
                # the Debug panel; poll runs only while the panel is open.
                from net.sysinfo import snapshot
                payload = snapshot(str(storage_path()))
                writer.write(_http_response("200 OK", "application/json",
                                            json.dumps(payload).encode()))

            elif path == "/health":
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")

            else:
                writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 9\r\n\r\nNot Found")

            await writer.drain()
        except Exception:
            pass
        finally:
            try:
                total_ms = (time.perf_counter() - _perf_started) * 1000
                ctx_perf = _perf_ctx.get() or {"db_ms": 0.0}
                db_ms = ctx_perf.get("db_ms", 0.0)
                bytes_out = _bytes_written[0]
                # Skip noisy paths (long-lived SSE, polling instrument endpoints)
                # to keep the log signal-rich and the ring buffer representative.
                _perf_skip = (
                    _perf_path.startswith("/events")
                    or _perf_path == "/debug/perf"
                    or _perf_path == "/debug/perf/client"
                    or _perf_path == "/debug/raw.json"
                )
                if not _perf_skip:
                    _perf_ring.append({
                        "ts": time.time(),
                        "method": _perf_method,
                        "path": _perf_path,
                        "total_ms": round(total_ms, 1),
                        "db_ms": round(db_ms, 1),
                        "bytes": bytes_out,
                    })
                    line = (f"perf method={_perf_method} path={_perf_path} "
                            f"total_ms={total_ms:.1f} db_ms={db_ms:.1f} bytes={bytes_out}")
                    if total_ms > _PERF_LOG_THRESHOLD_MS:
                        log.info(line)
                    else:
                        log.debug(line)
            except Exception:
                pass
            if _perf_token is not None:
                try:
                    _perf_ctx.reset(_perf_token)
                except (LookupError, ValueError):
                    pass
            writer.close()

    return handle_status
