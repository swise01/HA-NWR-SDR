import gzip
import json
import math as _math
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import MIN_VALID_LAP_S
from net.perf import _TimedLock

# ─── Module-level context (set by initialize()) ───────────────────────────────

# Wrapped so per-request DB time is attributed to _perf_ctx when called from
# the HTTP router; transparent (no timing) when called from the listener.
# See docs/specs/perf-audit-and-instrument.md.
_db_lock = _TimedLock(threading.Lock())
_learned_ordinals_cache: Optional[dict] = None
_DOWNSAMPLE_TARGET = 500

_demo_db_path_ref: list = [None]   # mutable ref so main() can set it after import
_storage_path = None               # callable: () -> Path
_forza_tracks: dict = {}           # shared dict ref — mutations visible in listener.py
_forza_cars:   dict = {}
_log = None


def initialize(demo_db_path_ref: list, storage_path_fn, forza_tracks: dict,
               forza_cars: dict, log_fn):
    global _demo_db_path_ref, _storage_path, _forza_tracks, _forza_cars, _log
    _demo_db_path_ref = demo_db_path_ref
    _storage_path     = storage_path_fn
    _forza_tracks     = forza_tracks
    _forza_cars       = forza_cars
    _log              = log_fn


# ─── Connection ───────────────────────────────────────────────────────────────

def _db_connect() -> sqlite3.Connection:
    db_path = Path(_demo_db_path_ref[0]) if _demo_db_path_ref[0] else _storage_path() / "simtelemetry.db"
    conn = sqlite3.connect(str(db_path), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─── Schema Init & Migration ──────────────────────────────────────────────────

def _db_init():
    with _db_lock:
        conn = _db_connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id       TEXT PRIMARY KEY,
                    game             TEXT,
                    track            TEXT,
                    car              TEXT,
                    session_type     TEXT,
                    race_type        TEXT,
                    started_at       TEXT,
                    ended_at         TEXT,
                    packet_count     INTEGER DEFAULT 0,
                    best_lap_time_s  REAL,
                    lap_count        INTEGER DEFAULT 0,
                    ai_analysis      TEXT,
                    ai_analyzed_at   TEXT,
                    ai_model         TEXT,
                    grid_pos         INTEGER,
                    finish_pos       INTEGER
                );
                CREATE TABLE IF NOT EXISTS laps (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id    TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    lap_number    INTEGER,
                    lap_time_s    REAL,
                    max_speed_mph REAL,
                    sample_count  INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS track_tips (
                    track        TEXT PRIMARY KEY,
                    tip          TEXT,
                    generated_at TEXT,
                    model        TEXT
                );
                CREATE TABLE IF NOT EXISTS track_references (
                    track                      TEXT NOT NULL,
                    reference_type             TEXT NOT NULL,
                    session_id                 TEXT,
                    lap_number                 INTEGER,
                    samples_json               TEXT NOT NULL,
                    theoretical_s1_s           REAL,
                    theoretical_s1_session_id  TEXT,
                    theoretical_s1_lap         INTEGER,
                    theoretical_s2_s           REAL,
                    theoretical_s2_session_id  TEXT,
                    theoretical_s2_lap         INTEGER,
                    theoretical_s3_s           REAL,
                    theoretical_s3_session_id  TEXT,
                    theoretical_s3_lap         INTEGER,
                    theoretical_best_s         REAL,
                    updated_at                 TEXT,
                    PRIMARY KEY (track, reference_type)
                );
                CREATE TABLE IF NOT EXISTS lap_samples (
                    session_id    TEXT NOT NULL,
                    lap_number    INTEGER NOT NULL,
                    samples_json  TEXT NOT NULL,
                    distance_m_json TEXT NOT NULL,
                    created_at    TEXT,
                    PRIMARY KEY (session_id, lap_number)
                );
                CREATE TABLE IF NOT EXISTS learned_track_ordinals (
                    ordinal     INTEGER NOT NULL,
                    game        TEXT    NOT NULL,
                    track_name  TEXT    NOT NULL,
                    created_at  TEXT,
                    PRIMARY KEY (ordinal, game)
                );
                CREATE TABLE IF NOT EXISTS car_nicknames (
                    ordinal    INTEGER PRIMARY KEY,
                    nickname   TEXT NOT NULL,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS discarded_sessions (
                    session_id  TEXT PRIMARY KEY,
                    game        TEXT,
                    track       TEXT,
                    started_at  TEXT,
                    reason      TEXT,
                    culled_at   TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS lap_events (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id     TEXT NOT NULL,
                    lap_number     INTEGER NOT NULL,
                    event_type     TEXT NOT NULL,
                    distance_m     REAL,
                    distance_norm  REAL,
                    severity       REAL,
                    description    TEXT,
                    detected_at    TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_lap_events_session
                    ON lap_events(session_id);
                CREATE INDEX IF NOT EXISTS idx_laps_session  ON laps(session_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_track ON sessions(track);
                CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(started_at);
                CREATE INDEX IF NOT EXISTS idx_lap_samples_session ON lap_samples(session_id);
                CREATE INDEX IF NOT EXISTS idx_track_refs_track ON track_references(track);
            """)
            conn.commit()
            for col, defn in [
                ("grid_pos", "INTEGER"), ("finish_pos", "INTEGER"),
                ("track_ordinal", "INTEGER"), ("car_class", "INTEGER"), ("car_pi", "INTEGER"),
                ("weather_condition", "TEXT"), ("track_temp_c", "REAL"), ("air_temp_c", "REAL"),
                ("car_manufacturer", "TEXT"), ("car_year", "INTEGER"),
                ("closed_reason", "TEXT"), ("tyre_compound", "TEXT"),
                # Bundle 2 (cars): keep the raw Forza ordinal even when name
                # lookup fails so the UI can show "Unknown Car (#641)", and
                # capture drivetrain + cylinders for richer car badges.
                ("car_ordinal", "INTEGER"),
                ("drivetrain_type", "INTEGER"),
                ("num_cylinders", "INTEGER"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} {defn}")
                    conn.commit()
                except Exception:
                    pass
            # Per-lap precomputed aggregates so /sessions/session/data can be
            # served by a single SQL query instead of re-reading <sid>_laps.json
            # from disk and iterating every sample on each request.
            # See docs/specs/perf-session-data-precompute.md.
            for col, defn in [
                ("avg_throttle",   "REAL"),
                ("avg_brake",      "REAL"),
                ("avg_slip",       "REAL"),
                ("peak_slip",      "REAL"),
                ("slip_above_pct", "REAL"),
                # Per-lap sector times. Boundaries are fixed at 1/3 and 2/3 of
                # lap distance, matching the theoretical-best computation in
                # update_track_references(). Written at session close by the
                # same loop; backfilled by scripts/backfill_lap_sectors.py.
                ("s1_time_s",      "REAL"),
                ("s2_time_s",      "REAL"),
                ("s3_time_s",      "REAL"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE laps ADD COLUMN {col} {defn}")
                    conn.commit()
                except Exception:
                    pass
        finally:
            conn.close()
    _db_migrate()
    _db_backfill_race_types()


def _db_migrate():
    """Import existing session JSON files not yet in the database. Idempotent."""
    sessions_dir = _storage_path() / "sessions"
    if not sessions_dir.exists():
        return
    imported = 0
    with _db_lock:
        conn = _db_connect()
        try:
            for f in sorted(sessions_dir.glob("*.json")):
                if f.name.endswith("_laps.json") or f.name.endswith("_analysis.json"):
                    continue
                try:
                    data = json.loads(f.read_text())
                    sid = data.get("session_id")
                    if not sid:
                        continue
                    if conn.execute("SELECT 1 FROM sessions WHERE session_id=?", (sid,)).fetchone():
                        continue
                    if conn.execute("SELECT 1 FROM discarded_sessions WHERE session_id=?", (sid,)).fetchone():
                        try:
                            f.unlink(missing_ok=True)
                        except OSError:
                            pass
                        continue
                    ai_text = ai_at = ai_model = None
                    af = sessions_dir / f"{sid}_analysis.json"
                    if af.exists():
                        try:
                            a = json.loads(af.read_text())
                            ai_text  = a.get("analysis")
                            ai_at    = a.get("analyzed_at")
                            ai_model = a.get("model")
                        except Exception:
                            pass
                    laps = data.get("laps", [])
                    conn.execute("""
                        INSERT OR IGNORE INTO sessions
                        (session_id,game,track,car,session_type,race_type,
                         started_at,ended_at,packet_count,best_lap_time_s,lap_count,
                         ai_analysis,ai_analyzed_at,ai_model)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (sid,
                          data.get("game"), data.get("track"), data.get("car"),
                          data.get("session_type"), data.get("race_type"),
                          data.get("started_at"), data.get("ended_at"),
                          data.get("packet_count", 0), data.get("best_lap_time_s"),
                          len(laps), ai_text, ai_at, ai_model))
                    for lap in laps:
                        conn.execute("""
                            INSERT INTO laps (session_id,lap_number,lap_time_s,max_speed_mph,sample_count)
                            VALUES (?,?,?,?,?)
                        """, (sid, lap.get("lap_number"), lap.get("lap_time_s"),
                              lap.get("max_speed_mph"), lap.get("sample_count", 0)))
                    imported += 1
                except Exception as e:
                    _log.warning(f"DB migration: skipping {f.name}: {e}")
            conn.commit()
        finally:
            conn.close()
    if imported:
        _log.info(f"SQLite: migrated {imported} session(s) from JSON files")


# ─── Learned Track Ordinals ───────────────────────────────────────────────────

def _load_learned_track_ordinals() -> dict:
    """Return {ordinal: track_name} from the learned_track_ordinals table."""
    with _db_lock:
        conn = _db_connect()
        try:
            rows = conn.execute(
                "SELECT ordinal, track_name FROM learned_track_ordinals"
            ).fetchall()
            return {row["ordinal"]: row["track_name"] for row in rows}
        finally:
            conn.close()


def _db_write_learned_ordinal(ordinal: int, game: str, track_name: str):
    global _learned_ordinals_cache
    with _db_lock:
        conn = _db_connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO learned_track_ordinals (ordinal, game, track_name, created_at) "
                "VALUES (?,?,?,?)",
                (ordinal, game, track_name, datetime.now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
    _learned_ordinals_cache = None  # invalidate
    _forza_tracks[ordinal] = track_name


def _effective_tracks() -> dict:
    """Return merged {ordinal: track_name} combining _forza_tracks and learned ordinals."""
    global _learned_ordinals_cache
    if _learned_ordinals_cache is None:
        _learned_ordinals_cache = _load_learned_track_ordinals()
    result = dict(_forza_tracks)
    result.update(_learned_ordinals_cache)
    return result


# ─── Car nicknames (per ordinal) ─────────────────────────────────────────────


def _db_get_car_nickname(ordinal: int) -> Optional[str]:
    with _db_lock:
        conn = _db_connect()
        try:
            row = conn.execute(
                "SELECT nickname FROM car_nicknames WHERE ordinal=?", (ordinal,)
            ).fetchone()
            return row["nickname"] if row else None
        finally:
            conn.close()


def _db_get_car_nicknames() -> dict:
    """Return {ordinal: nickname} for every car the user has named."""
    with _db_lock:
        conn = _db_connect()
        try:
            rows = conn.execute("SELECT ordinal, nickname FROM car_nicknames").fetchall()
            return {r["ordinal"]: r["nickname"] for r in rows}
        finally:
            conn.close()


def _db_set_car_nickname(ordinal: int, nickname: Optional[str]):
    """Insert/replace a nickname; pass nickname=None or '' to delete."""
    with _db_lock:
        conn = _db_connect()
        try:
            if nickname:
                conn.execute(
                    "INSERT OR REPLACE INTO car_nicknames (ordinal, nickname, updated_at) "
                    "VALUES (?,?,?)",
                    (int(ordinal), nickname.strip(), datetime.now().isoformat()),
                )
            else:
                conn.execute("DELETE FROM car_nicknames WHERE ordinal=?", (int(ordinal),))
            conn.commit()
        finally:
            conn.close()


# ─── Race Type Classification ─────────────────────────────────────────────────

def _classify_race_type(positions: list, lap_count: int) -> Optional[str]:
    """
    Derive race_type from sampled race positions and completed lap count.

    'real'       — position changed at least once (human opponents present)
    'time_trial' — lap count <= 3 and position never changed (solo / practice)
    'ai'         — more than 3 laps and position was always 1 (led wire-to-wire, AI grid)
    None         — not enough data to classify
    """
    if not positions:
        return "time_trial" if lap_count <= 3 else None
    unique = set(positions)
    if len(unique) > 1:
        return "real"
    if lap_count <= 3:
        return "time_trial"
    if next(iter(unique)) == 1:
        return "ai"
    return None


# ─── Startup Maintenance ──────────────────────────────────────────────────────

def _db_cull_ghost_sessions():
    """
    Move sessions with lap_count<=1 AND best_lap_time_s IS NULL to
    discarded_sessions — these are Forza menu-browse artifacts.
    Deletes the source <sid>.json and <sid>_laps.json so migration
    won't re-import them on next boot. Keeps .bin files.
    Runs once at startup; idempotent.
    """
    sessions_dir = _storage_path() / "sessions"
    with _db_lock:
        conn = _db_connect()
        try:
            ghosts = conn.execute(
                "SELECT session_id, game, track, started_at "
                "FROM sessions WHERE lap_count <= 1 AND best_lap_time_s IS NULL"
            ).fetchall()
            if not ghosts:
                return
            conn.executemany(
                "INSERT OR IGNORE INTO discarded_sessions "
                "(session_id, game, track, started_at, reason) VALUES (?,?,?,?,?)",
                [(r["session_id"], r["game"], r["track"], r["started_at"],
                  "lap_count<=1 and no lap time") for r in ghosts],
            )
            ids = [r["session_id"] for r in ghosts]
            conn.execute(
                f"DELETE FROM sessions WHERE session_id IN ({','.join('?'*len(ids))})", ids
            )
            conn.commit()
        finally:
            conn.close()

    if sessions_dir.exists():
        for sid in ids:
            for name in (f"{sid}.json", f"{sid}_laps.json"):
                try:
                    (sessions_dir / name).unlink(missing_ok=True)
                except OSError:
                    pass
    _log.info(f"Culled {len(ghosts)} ghost session(s) to discarded_sessions table")


def _db_backfill_track_names():
    """
    For sessions stored as 'Track #<N>' or 'unknown' with a known track_ordinal,
    update track name from _forza_tracks.  Also backfills car name/manufacturer/year
    from _forza_cars where car column is a raw ordinal string.
    Idempotent.
    """
    with _db_lock:
        conn = _db_connect()
        try:
            rows = conn.execute(
                "SELECT session_id, track, track_ordinal FROM sessions "
                "WHERE track_ordinal IS NOT NULL "
                "AND (track = 'unknown' OR track LIKE 'Track #%')"
            ).fetchall()
            distinct_ords = {r["track_ordinal"] for r in rows}
            if distinct_ords:
                hits   = {o for o in distinct_ords if _forza_tracks.get(o)}
                misses = distinct_ords - hits
                _log.info(
                    f"Track ordinal backfill: {len(distinct_ords)} distinct ordinals "
                    f"({len(hits)} hits, {len(misses)} misses). "
                    f"Misses: {sorted(misses)[:10]}"
                )
            track_updates = []
            for row in rows:
                name = _forza_tracks.get(row["track_ordinal"])
                if name:
                    track_updates.append((name, row["session_id"]))
            if track_updates:
                conn.executemany("UPDATE sessions SET track=? WHERE session_id=?", track_updates)
                conn.commit()
                _log.info(f"Backfilled track names for {len(track_updates)} session(s)")

            if _forza_cars:
                car_rows = conn.execute(
                    "SELECT session_id, car FROM sessions "
                    "WHERE car GLOB '[0-9]*' OR car = 'unknown'"
                ).fetchall()
                car_updates = []
                for row in car_rows:
                    try:
                        ordinal = int(row["car"]) if row["car"] != "unknown" else None
                    except (ValueError, TypeError):
                        ordinal = None
                    if ordinal is None:
                        continue
                    info = _forza_cars.get(ordinal)
                    if info:
                        car_updates.append((
                            info["name"], info["manufacturer"], info["year"],
                            row["session_id"]
                        ))
                if car_updates:
                    conn.executemany(
                        "UPDATE sessions SET car=?, car_manufacturer=?, car_year=? "
                        "WHERE session_id=?",
                        car_updates
                    )
                    conn.commit()
                    _log.info(f"Backfilled car names for {len(car_updates)} session(s)")
        finally:
            conn.close()


def _db_backfill_race_types():
    """
    Classify sessions whose race_type is NULL.
    Runs at startup and re-runs safely (idempotent — only touches NULL rows).
    """
    with _db_lock:
        conn = _db_connect()
        try:
            rows = conn.execute(
                "SELECT session_id, session_type, grid_pos, finish_pos, lap_count "
                "FROM sessions WHERE race_type IS NULL"
            ).fetchall()
            if not rows:
                return
            updates = []
            for row in rows:
                sid        = row["session_id"]
                stype      = row["session_type"] or "unknown"
                grid_pos   = row["grid_pos"]
                finish_pos = row["finish_pos"]
                lap_count  = row["lap_count"] or 0

                if grid_pos is not None and finish_pos is not None:
                    positions = [grid_pos, finish_pos]
                else:
                    positions = []
                rt = _classify_race_type(positions, lap_count)

                if rt is None:
                    if stype == "time_trial" or lap_count <= 3:
                        rt = "time_trial"
                    elif stype == "race" or lap_count > 5:
                        if grid_pos is not None and finish_pos is not None and grid_pos == finish_pos and finish_pos != 1:
                            rt = "real"
                        elif grid_pos is None or finish_pos is None:
                            rt = "real"

                if rt is not None:
                    updates.append((rt, sid))

            if updates:
                conn.executemany(
                    "UPDATE sessions SET race_type=? WHERE session_id=?", updates
                )
                conn.commit()
                _log.info(f"SQLite: backfilled race_type for {len(updates)} session(s)")
        finally:
            conn.close()


# ─── Session Write ────────────────────────────────────────────────────────────

def _db_write_session(session_data: dict):
    """Insert/replace a session and its lap summaries."""
    sid  = session_data["session_id"]
    laps = session_data.get("laps", [])
    with _db_lock:
        conn = _db_connect()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO sessions
                (session_id,game,track,car,session_type,race_type,
                 started_at,ended_at,packet_count,best_lap_time_s,lap_count,
                 grid_pos,finish_pos,track_ordinal,car_class,car_pi,
                 weather_condition,track_temp_c,air_temp_c,
                 car_manufacturer,car_year,closed_reason,tyre_compound,
                 car_ordinal,drivetrain_type,num_cylinders)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (sid,
                  session_data.get("game"), session_data.get("track"),
                  session_data.get("car"), session_data.get("session_type"),
                  session_data.get("race_type"),
                  session_data.get("started_at"), session_data.get("ended_at"),
                  session_data.get("packet_count", 0), session_data.get("best_lap_time_s"),
                  len(laps),
                  session_data.get("grid_pos"), session_data.get("finish_pos"),
                  session_data.get("track_ordinal"),
                  session_data.get("car_class"), session_data.get("car_pi"),
                  session_data.get("weather_condition"),
                  session_data.get("track_temp_c"), session_data.get("air_temp_c"),
                  session_data.get("car_manufacturer"), session_data.get("car_year"),
                  session_data.get("closed_reason"), session_data.get("tyre_compound"),
                  session_data.get("car_ordinal"),
                  session_data.get("drivetrain_type"),
                  session_data.get("num_cylinders")))
            conn.execute("DELETE FROM laps WHERE session_id=?", (sid,))
            for lap in laps:
                conn.execute("""
                    INSERT INTO laps (session_id,lap_number,lap_time_s,max_speed_mph,sample_count,
                                      avg_throttle,avg_brake,avg_slip,peak_slip,slip_above_pct)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (sid, lap.get("lap_number"), lap.get("lap_time_s"),
                      lap.get("max_speed_mph"), lap.get("sample_count", 0),
                      lap.get("avg_throttle"), lap.get("avg_brake"),
                      lap.get("avg_slip"), lap.get("peak_slip"),
                      lap.get("slip_above_pct")))
            conn.commit()
        finally:
            conn.close()


# ─── Per-lap aggregates (precomputed at session close) ───────────────────────


def compute_lap_aggregates(samples: list) -> dict:
    """Compute the per-lap aggregates served by /sessions/session/data.

    Same numbers the old in-handler iteration produced — just hoisted out
    so they can be precomputed at session close (and during backfill) and
    served by a pure SQL query instead of recomputing on every request.
    See docs/specs/perf-session-data-precompute.md.
    """
    n = len(samples)
    if not n:
        return {
            "avg_throttle": None, "avg_brake": None,
            "avg_slip": None, "peak_slip": None, "slip_above_pct": None,
        }
    throttle  = [s.get("throttle_pct", 0) for s in samples]
    brake     = [s.get("brake_pct", 0)    for s in samples]
    slip_vals = [(abs(s.get("slip_rl", 0)) + abs(s.get("slip_rr", 0))) / 2
                 for s in samples]
    sv_sorted = sorted(slip_vals)
    p99_idx   = max(0, int(n * 0.99) - 1)
    return {
        "avg_throttle":   round(sum(throttle)  / n, 1),
        "avg_brake":      round(sum(brake)     / n, 1),
        "avg_slip":       round(sum(slip_vals) / n, 4),
        "peak_slip":      round(sv_sorted[p99_idx], 4),
        "slip_above_pct": round(sum(1 for v in slip_vals if v > 0.1) / n * 100, 1),
    }


# ─── Session Queries ──────────────────────────────────────────────────────────

_NEEDS_REVIEW_SQL = """
  track IS NULL OR track='unknown' OR track LIKE 'Track #%'
  OR car IS NULL OR car='unknown' OR car LIKE 'Unknown Car%'
  OR (race_type IS NULL AND (session_type IS NULL OR session_type='unknown'))
  OR ((race_type IN ('race','race_ai','race_online','real','ai')
       OR session_type='race')
      AND (grid_pos IS NULL OR finish_pos IS NULL))
"""


def _db_sessions_since_count(iso: str) -> int:
    """Count sessions recorded since the given ISO timestamp — drives
    the "N new since last visit" rail badge so unattended captures are
    visible. See docs/specs/unattended-capture-confirmation.md."""
    if not iso:
        return 0
    with _db_lock:
        conn = _db_connect()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE started_at > ?", (iso,)
            ).fetchone()[0]
        finally:
            conn.close()


def _db_needs_review_count() -> int:
    """Count sessions where the user's input would materially improve the
    data: unresolved track, unmapped car, unknown type, or a race missing
    grid→finish. Predicate mirrored client-side in sessions_list.js —
    keep the two in sync. See docs/specs/ia.md."""
    with _db_lock:
        conn = _db_connect()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE" + _NEEDS_REVIEW_SQL
            ).fetchone()[0]
        finally:
            conn.close()


def _db_sessions_list(limit: int = 100) -> list:
    """Return sessions newest-first — summary stats only, no sample data.

    Includes a chronological lap_times array per session (powers the
    per-row lap-time sparkline on /sessions). Pulled in a single batch
    query rather than N subqueries so adding 25 sparklines to the page
    costs one extra SELECT, not 25.
    """
    with _db_lock:
        conn = _db_connect()
        try:
            rows = [dict(r) for r in conn.execute(
                "SELECT session_id,game,track,car,car_ordinal,car_class,car_pi,"
                "session_type,race_type,started_at,ended_at,packet_count,"
                "best_lap_time_s,lap_count,finish_pos,grid_pos,"
                "weather_condition,tyre_compound,track_temp_c "
                "FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()]
            if rows:
                sids = [r["session_id"] for r in rows]
                placeholders = ",".join("?" for _ in sids)
                lap_rows = conn.execute(
                    f"SELECT session_id, lap_number, lap_time_s FROM laps "
                    f"WHERE session_id IN ({placeholders}) "
                    f"  AND lap_time_s IS NOT NULL "
                    f"ORDER BY session_id, lap_number",
                    sids
                ).fetchall()
                from collections import defaultdict
                lap_times: dict = defaultdict(list)
                for r in lap_rows:
                    lap_times[r["session_id"]].append(r["lap_time_s"])
                for r in rows:
                    r["lap_times"] = lap_times.get(r["session_id"], [])
            return rows
        finally:
            conn.close()


def _db_games_index() -> list:
    """Return per-game aggregate stats, newest-first.

    Only Forza is active. ACC + F1 are parked — see docs/specs/park-acc-f1.md.
    """
    all_games = ["forza_motorsport"]
    with _db_lock:
        conn = _db_connect()
        try:
            rows = conn.execute("""
                SELECT game,
                       COUNT(*) as session_count,
                       COUNT(DISTINCT CASE WHEN track IS NOT NULL AND track != 'unknown'
                                           THEN track END) as track_count,
                       MAX(started_at) as last_played
                FROM sessions
                GROUP BY game
            """).fetchall()
            by_game = {r["game"]: dict(r) for r in rows}
            result = []
            for g in all_games:
                r = by_game.get(g, {"game": g, "session_count": 0, "track_count": 0, "last_played": None})
                bl = conn.execute("""
                    SELECT best_lap_time_s, track FROM sessions
                    WHERE game=? AND best_lap_time_s IS NOT NULL
                    ORDER BY best_lap_time_s ASC LIMIT 1
                """, (g,)).fetchone()
                r["best_lap_time_s"] = bl["best_lap_time_s"] if bl else None
                r["best_lap_track"]  = bl["track"] if bl else None
                lp = conn.execute(
                    "SELECT track FROM sessions WHERE game=? ORDER BY started_at DESC LIMIT 1", (g,)
                ).fetchone()
                r["last_played_track"] = lp["track"] if lp else None
                spark_rows = conn.execute("""
                    SELECT best_lap_time_s FROM sessions
                    WHERE game=? AND best_lap_time_s IS NOT NULL
                    ORDER BY started_at DESC LIMIT 8
                """, (g,)).fetchall()
                r["spark"] = [s[0] for s in reversed(spark_rows)]
                result.append(r)
            result.sort(key=lambda x: (x["last_played"] is None, x["last_played"] or ""), reverse=False)
            result.sort(key=lambda x: x["last_played"] is None)
            return result
        finally:
            conn.close()


def _db_career_kpis(game: Optional[str] = None) -> dict:
    """Return career-level KPI aggregates. Optionally filtered to a single game."""
    with _db_lock:
        conn = _db_connect()
        try:
            where = "WHERE game=?" if game else ""
            params = [game] if game else []
            row = conn.execute(f"""
                SELECT
                  COUNT(*) as total_sessions,
                  SUM(CASE WHEN race_type='real' THEN 1 ELSE 0 END) as real_count,
                  SUM(CASE WHEN race_type='ai'   THEN 1 ELSE 0 END) as ai_count,
                  AVG(CASE WHEN race_type='real' AND session_type='race' AND finish_pos IS NOT NULL
                           THEN CAST(finish_pos AS REAL) END) as avg_finish_real,
                  AVG(CASE WHEN race_type='real' AND session_type='race'
                                AND grid_pos IS NOT NULL AND grid_pos > 0 AND finish_pos IS NOT NULL
                           THEN CAST(grid_pos AS REAL) - finish_pos END) as avg_pos_gained,
                  100.0 * SUM(CASE WHEN race_type='real' AND session_type='race' AND finish_pos=1 THEN 1 ELSE 0 END)
                        / NULLIF(SUM(CASE WHEN race_type='real' AND session_type='race' THEN 1 ELSE 0 END), 0) as win_rate,
                  100.0 * SUM(CASE WHEN race_type='real' AND session_type='race' AND finish_pos<=3 THEN 1 ELSE 0 END)
                        / NULLIF(SUM(CASE WHEN race_type='real' AND session_type='race' THEN 1 ELSE 0 END), 0) as podium_rate,
                  SUM(lap_count) as total_laps,
                  MIN(best_lap_time_s) as best_lap_time_s,
                  COUNT(DISTINCT CASE WHEN track IS NOT NULL AND track != 'unknown' THEN track END) as circuit_count,
                  COUNT(DISTINCT CASE WHEN car_ordinal IS NOT NULL THEN car_ordinal END) as cars_driven,
                  SUM(CASE WHEN race_type='real' AND session_type='race' AND finish_pos IS NOT NULL THEN 1 ELSE 0 END) as real_race_count
                FROM sessions {where}
            """, params).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()


def _db_form_data(race_type_filter: Optional[str] = None, last_n: int = 10,
                  game: Optional[str] = None) -> list:
    """Return last N race sessions for the Current Form bar chart."""
    with _db_lock:
        conn = _db_connect()
        try:
            where = "WHERE session_type='race'"
            params: list = []
            if race_type_filter and race_type_filter != "all":
                where += " AND race_type=?"
                params.append(race_type_filter)
            if game:
                where += " AND game=?"
                params.append(game)
            params.append(last_n)
            rows = conn.execute(f"""
                SELECT session_id, track, started_at, finish_pos, grid_pos,
                       best_lap_time_s, lap_count, race_type, game
                FROM sessions {where}
                ORDER BY started_at DESC LIMIT ?
            """, params).fetchall()
            return [dict(r) for r in reversed(rows)]
        finally:
            conn.close()


def _db_recent_sessions(limit: int = 8, game: Optional[str] = None) -> list:
    """Return last N sessions, optionally filtered by game."""
    with _db_lock:
        conn = _db_connect()
        try:
            where = "WHERE game=?" if game else ""
            params = [game, limit] if game else [limit]
            rows = conn.execute(f"""
                SELECT session_id, game, track, started_at, best_lap_time_s,
                       lap_count, finish_pos, grid_pos, race_type, session_type,
                       weather_condition, track_temp_c
                FROM sessions {where} ORDER BY started_at DESC LIMIT ?
            """, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def _db_tracks_index(game: Optional[str] = None) -> list:
    """Return aggregate stats per track, newest-first. Optionally filter by game."""
    with _db_lock:
        conn = _db_connect()
        try:
            where = "WHERE track IS NOT NULL"
            params: list = []
            if game:
                where += " AND game=?"
                params.append(game)
            rows = conn.execute(f"""
                SELECT track,
                       COUNT(*) as session_count,
                       MIN(best_lap_time_s) as best_lap_time_s,
                       MAX(started_at) as last_raced
                FROM sessions {where}
                GROUP BY track
                ORDER BY last_raced DESC
            """, params).fetchall()
            result = []
            for row in rows:
                r = dict(row)
                extra_where = (" AND game=?" if game else "")
                extra_params_base = [r["track"]] + (([game]) if game else [])
                last3 = conn.execute(
                    f"SELECT best_lap_time_s FROM sessions WHERE track=? AND best_lap_time_s IS NOT NULL{extra_where} ORDER BY started_at DESC LIMIT 3",
                    extra_params_base,
                ).fetchall()
                times = [l[0] for l in last3]
                if len(times) >= 2 and times[0] is not None and times[1] is not None:
                    diff = times[0] - times[1]
                    r["trend"] = "dn" if diff > 0.5 else ("up" if diff < -0.5 else "fl")
                else:
                    r["trend"] = "fl"
                spark_rows = conn.execute(
                    f"SELECT best_lap_time_s FROM sessions WHERE track=? AND best_lap_time_s IS NOT NULL{extra_where} ORDER BY started_at ASC LIMIT 20",
                    extra_params_base,
                ).fetchall()
                r["spark_laps"] = [sr[0] for sr in spark_rows]
                finish_row = conn.execute(
                    f"SELECT AVG(finish_pos) FROM sessions WHERE track=? AND finish_pos IS NOT NULL{extra_where}",
                    extra_params_base,
                ).fetchone()
                avg_f = finish_row[0] if finish_row else None
                r["avg_finish"] = round(avg_f, 1) if avg_f is not None else None
                gained_row = conn.execute(
                    f"SELECT AVG(CAST(grid_pos AS REAL) - finish_pos) FROM sessions "
                    f"WHERE track=? AND grid_pos IS NOT NULL AND grid_pos > 0 "
                    f"AND finish_pos IS NOT NULL{extra_where}",
                    extra_params_base,
                ).fetchone()
                avg_g = gained_row[0] if gained_row else None
                r["avg_gained"] = round(avg_g, 1) if avg_g is not None else None
                best_car_row = conn.execute(
                    f"SELECT session_id, car, car_class, car_pi FROM sessions WHERE track=? AND best_lap_time_s=?{extra_where} ORDER BY started_at DESC LIMIT 1",
                    [r["track"], r["best_lap_time_s"]] + (([game]) if game else []),
                ).fetchone()
                r["best_car"] = best_car_row["car"] if best_car_row else None
                r["best_car_class"] = best_car_row["car_class"] if best_car_row else None
                r["best_car_pi"] = best_car_row["car_pi"] if best_car_row else None
                # Outline source: the PB lap of the PB session — the row UI
                # uses these to lazy-load /sessions/lap-samples and draw the
                # racing line as a faint thumbnail.
                if best_car_row:
                    pb_lap = conn.execute(
                        "SELECT lap_number FROM laps WHERE session_id=? "
                        "AND lap_time_s IS NOT NULL ORDER BY lap_time_s ASC LIMIT 1",
                        (best_car_row["session_id"],),
                    ).fetchone()
                    r["pb_session_id"] = best_car_row["session_id"]
                    r["pb_lap_number"] = pb_lap["lap_number"] if pb_lap else None
                else:
                    r["pb_session_id"] = None
                    r["pb_lap_number"] = None
                result.append(r)
            return result
        finally:
            conn.close()


def _db_track_sessions(track: str, game: Optional[str] = None) -> list:
    """Return all sessions for a track, newest-first, with lap time arrays for spark graphs."""
    with _db_lock:
        conn = _db_connect()
        try:
            where = "WHERE track=?"
            params: list = [track]
            if game:
                where += " AND game=?"
                params.append(game)
            rows = conn.execute(f"""
                SELECT session_id,game,track,car,session_type,race_type,
                       started_at,ended_at,best_lap_time_s,lap_count,
                       ai_analyzed_at,ai_model,car_class,car_pi,finish_pos,grid_pos
                FROM sessions {where} ORDER BY started_at DESC
            """, params).fetchall()
            result = []
            for row in rows:
                s = dict(row)
                lap_rows = conn.execute(
                    "SELECT lap_time_s FROM laps WHERE session_id=? ORDER BY lap_number",
                    (s["session_id"],)
                ).fetchall()
                s["lap_times"] = [l[0] for l in lap_rows if l[0] is not None]
                result.append(s)
            return result
        finally:
            conn.close()


def _db_get_track_tip(track: str) -> Optional[dict]:
    """Return cached coaching tip for a track, or None."""
    with _db_lock:
        conn = _db_connect()
        try:
            row = conn.execute(
                "SELECT tip,generated_at,model FROM track_tips WHERE track=?", (track,)
            ).fetchone()
            return dict(row) if row and row["tip"] else None
        finally:
            conn.close()


def _db_save_track_tip(track: str, tip: str, model: str):
    with _db_lock:
        conn = _db_connect()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO track_tips (track,tip,generated_at,model)
                VALUES (?,?,?,?)
            """, (track, tip, datetime.now().isoformat(), model))
            conn.commit()
        finally:
            conn.close()


def _db_update_session(sid: str, **kwargs):
    """Update arbitrary columns on a session row."""
    if not kwargs:
        return
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [sid]
    with _db_lock:
        conn = _db_connect()
        try:
            conn.execute(f"UPDATE sessions SET {cols} WHERE session_id=?", vals)
            conn.commit()
        finally:
            conn.close()


def _db_delete_session(sid: str) -> bool:
    """Remove a session and all its dependent rows from every table.

    Used by the /sessions/delete endpoint and the bulk-cleanup script
    (scripts/clean_test_sessions.py). Does NOT touch JSON / .bin files
    on disk — caller is responsible for those.
    """
    if not sid:
        return False
    with _db_lock:
        conn = _db_connect()
        try:
            conn.execute("DELETE FROM lap_samples WHERE session_id=?", (sid,))
            conn.execute("DELETE FROM laps        WHERE session_id=?", (sid,))
            res = conn.execute("DELETE FROM sessions    WHERE session_id=?", (sid,))
            conn.commit()
            return res.rowcount > 0
        finally:
            conn.close()


def _db_drop_last_lap(sid: str):
    """Remove the last lap row and recalculate best_lap_time_s."""
    with _db_lock:
        conn = _db_connect()
        try:
            last = conn.execute(
                "SELECT id FROM laps WHERE session_id=? ORDER BY lap_number DESC LIMIT 1",
                (sid,)
            ).fetchone()
            if last:
                conn.execute("DELETE FROM laps WHERE id=?", (last["id"],))
                best = conn.execute(
                    "SELECT MIN(lap_time_s) FROM laps WHERE session_id=? AND lap_time_s IS NOT NULL",
                    (sid,)
                ).fetchone()[0]
                count = conn.execute(
                    "SELECT COUNT(*) FROM laps WHERE session_id=?", (sid,)
                ).fetchone()[0]
                conn.execute(
                    "UPDATE sessions SET best_lap_time_s=?, lap_count=? WHERE session_id=?",
                    (best, count, sid)
                )
                conn.commit()
        finally:
            conn.close()


def _db_get_ai_analysis(sid: str) -> Optional[dict]:
    """Return cached AI analysis from DB, or None if not yet analyzed."""
    with _db_lock:
        conn = _db_connect()
        try:
            row = conn.execute(
                "SELECT ai_analysis,ai_analyzed_at,ai_model FROM sessions WHERE session_id=?",
                (sid,)
            ).fetchone()
            if row and row["ai_analysis"]:
                return {
                    "session_id":  sid,
                    "analysis":    row["ai_analysis"],
                    "analyzed_at": row["ai_analyzed_at"],
                    "model":       row["ai_model"],
                    "cached":      True,
                }
            return None
        finally:
            conn.close()


def _db_save_ai_analysis(sid: str, analysis: str, model: str):
    """Persist AI analysis text to the sessions row."""
    _db_update_session(sid,
                       ai_analysis=analysis,
                       ai_analyzed_at=datetime.now().isoformat(),
                       ai_model=model)


# ─── Lap Normalization & Sample Storage ───────────────────────────────────────

def normalize_lap_samples(samples: list) -> tuple:
    """
    Normalise a lap's raw sample list to distance-based coordinates.

    Returns (normalised_samples, cumulative_distances_m) where each sample
    gains a `distance_norm` field (0.0 lap-start → 1.0 lap-end).
    """
    if not samples:
        return [], []

    has_position = all("px" in s and "py" in s and "pz" in s for s in samples)

    cum_dist: list = [0.0]
    if has_position:
        for i in range(1, len(samples)):
            dx = samples[i]["px"] - samples[i - 1]["px"]
            dy = samples[i]["py"] - samples[i - 1]["py"]
            dz = samples[i]["pz"] - samples[i - 1]["pz"]
            cum_dist.append(cum_dist[-1] + _math.sqrt(dx * dx + dy * dy + dz * dz))
    else:
        for s in samples[1:]:
            cum_dist.append(s["t"])

    total = cum_dist[-1]
    if total <= 0:
        total = len(samples) - 1 or 1
        cum_dist = [i for i in range(len(samples))]

    step = max(1, len(samples) // _DOWNSAMPLE_TARGET)
    indices = list(range(0, len(samples), step))
    if indices[-1] != len(samples) - 1:
        indices.append(len(samples) - 1)

    norm_samples = []
    dist_m_out = []
    for i in indices:
        s = dict(samples[i])
        s["distance_norm"] = round(cum_dist[i] / total, 6)
        norm_samples.append(s)
        dist_m_out.append(round(cum_dist[i], 2))

    return norm_samples, dist_m_out


# ─── gzip wrappers for samples blobs ──────────────────────────────────────────
# Per docs/specs/storage-compression-and-field-expansion.md.
#
# The lap_samples and track_references columns are declared TEXT (legacy) but
# SQLite stores BLOBs in TEXT columns just fine when given bytes. We sniff the
# first byte on read: 0x1f = gzip magic, otherwise treat as legacy uncompressed
# JSON text. New writes are always gzipped. No schema migration needed.
_GZIP_MAGIC = b"\x1f\x8b"


def _encode_samples(payload: list) -> bytes:
    """JSON → gzip bytes. Use compresslevel=6 (default) — good ratio, fast."""
    return gzip.compress(json.dumps(payload).encode("utf-8"))


def _decode_samples(raw) -> list:
    """Decode whatever's in the row: gzip bytes (new) or JSON text (legacy)."""
    if raw is None:
        return []
    if isinstance(raw, str):
        # Legacy uncompressed JSON text — pre-compression rows.
        return json.loads(raw)
    if isinstance(raw, (bytes, bytearray, memoryview)):
        b = bytes(raw)
        if b.startswith(_GZIP_MAGIC):
            return json.loads(gzip.decompress(b).decode("utf-8"))
        # Bytes-but-not-gzip = legacy text stored as bytes (sqlite can do that)
        return json.loads(b.decode("utf-8"))
    raise TypeError(f"unexpected samples_json type: {type(raw).__name__}")


def _db_save_lap_samples(session_id: str, lap_number: int,
                          samples: list, dist_m: list):
    with _db_lock:
        conn = _db_connect()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO lap_samples
                   (session_id, lap_number, samples_json, distance_m_json, created_at)
                   VALUES (?,?,?,?,?)""",
                (session_id, lap_number,
                 _encode_samples(samples), _encode_samples(dist_m),
                 datetime.now().isoformat())
            )
            conn.commit()
        finally:
            conn.close()


def _db_get_lap_samples(session_id: str, lap_number: int) -> Optional[dict]:
    with _db_lock:
        conn = _db_connect()
        try:
            row = conn.execute(
                "SELECT samples_json, distance_m_json FROM lap_samples "
                "WHERE session_id=? AND lap_number=?",
                (session_id, lap_number)
            ).fetchone()
            if row:
                return {
                    "samples": _decode_samples(row["samples_json"]),
                    "distance_m": _decode_samples(row["distance_m_json"]),
                }
            return None
        finally:
            conn.close()


def _db_get_all_lap_samples(session_id: str) -> list:
    """Fetch every stored lap's samples for a session in lap-number order.

    Returns a list of {lap_number, samples, distance_m} dicts. Used by the
    Deep Dive endpoint which needs every valid lap at once.
    """
    with _db_lock:
        conn = _db_connect()
        try:
            rows = conn.execute(
                "SELECT lap_number, samples_json, distance_m_json FROM lap_samples "
                "WHERE session_id=? ORDER BY lap_number",
                (session_id,)
            ).fetchall()
            return [
                {
                    "lap_number": r["lap_number"],
                    "samples":    _decode_samples(r["samples_json"]),
                    "distance_m": _decode_samples(r["distance_m_json"]),
                }
                for r in rows
            ]
        finally:
            conn.close()


def _store_session_lap_samples(session_id: str, completed_laps: list):
    """
    Normalise and persist lap_samples rows for every lap within 102% of
    the session best lap time. Called from Session.close().
    """
    if not completed_laps:
        return

    valid = [lap for lap in completed_laps
             if lap.lap_time_s and lap.lap_time_s > 0]
    if not valid:
        return

    for lap in valid:
        if lap.samples:
            try:
                norm, dist_m = normalize_lap_samples(lap.samples)
                _db_save_lap_samples(session_id, lap.lap_number, norm, dist_m)
            except Exception as exc:
                _log.warning(f"lap_samples write failed lap {lap.lap_number}: {exc}")


def _backfill_lap_samples():
    """
    Back-fill lap_samples + track_references from existing _laps.json files
    for sessions that have no stored samples yet.  Runs once at startup in a
    daemon thread so it never blocks the listener.
    """
    sessions_dir = _storage_path() / "sessions"
    if not sessions_dir.exists():
        return

    with _db_lock:
        conn = _db_connect()
        try:
            rows = conn.execute(
                """SELECT s.session_id, s.track, s.game
                   FROM sessions s
                   WHERE s.lap_count > 0
                   AND s.lap_count > (
                       SELECT COUNT(*) FROM lap_samples ls WHERE ls.session_id = s.session_id
                   )
                   ORDER BY s.started_at DESC LIMIT 500"""
            ).fetchall()
        finally:
            conn.close()

    if not rows:
        return

    tracks_to_update: set = set()
    filled = 0
    for row in rows:
        sid = row["session_id"]
        laps_file = sessions_dir / f"{sid}_laps.json"
        if not laps_file.exists():
            continue
        try:
            laps_data = json.loads(laps_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(laps_data, list):
            continue
        valid = [l for l in laps_data
                 if l.get("lap_number") and l.get("lap_time_s") and l["lap_time_s"] > 0]
        if not valid:
            continue
        for lap in valid:
            samples = lap.get("samples", [])
            if not samples:
                continue
            try:
                norm, dist_m = normalize_lap_samples(samples)
                _db_save_lap_samples(sid, lap["lap_number"], norm, dist_m)
                filled += 1
            except Exception as exc:
                _log.warning(f"backfill lap_samples {sid} L{lap['lap_number']}: {exc}")
        track = row["track"] or ""
        game  = row["game"]  or ""
        if track and track != "unknown":
            tracks_to_update.add((track, game))

    for track, game in tracks_to_update:
        try:
            update_track_references(track, game)
        except Exception as exc:
            _log.warning(f"backfill track_references {track!r}: {exc}")

    _log.info(
        f"backfill_lap_samples: {filled} laps stored, "
        f"{len(tracks_to_update)} track references updated"
    )


# ─── Sector Utilities ─────────────────────────────────────────────────────────

def _sector_time_from_samples(samples: list, lo: float, hi: float) -> Optional[float]:
    """
    Time spent between two distance_norm boundaries.

    Linearly interpolates t between the two samples that bracket each boundary
    so sector-time precision isn't bound by sample spacing (~5–6 m of jitter at
    racing speed with 10 Hz samples).
    """
    if not samples:
        return None

    def t_at(target: float) -> Optional[float]:
        # Bracket the target with the first sample whose distance_norm >= target.
        for i in range(1, len(samples)):
            a = samples[i - 1].get("distance_norm", 0.0)
            b = samples[i].get("distance_norm", 0.0)
            if a <= target <= b and b > a:
                f = (target - a) / (b - a)
                return samples[i - 1]["t"] + f * (samples[i]["t"] - samples[i - 1]["t"])
        # Fallback: nearest sample (covers degenerate / non-monotonic cases).
        closest = min(samples, key=lambda s: abs(s.get("distance_norm", 0.0) - target))
        return closest["t"]

    t_lo = samples[0]["t"] if lo <= 0.0 else t_at(lo)
    t_hi = samples[-1]["t"] if hi >= 1.0 else t_at(hi)
    if t_lo is None or t_hi is None:
        return None
    delta = t_hi - t_lo
    return round(delta, 3) if delta > 0 else None


def _stitch_sector_samples(
    s1_samples: list, s2_samples: list, s3_samples: list,
    s1_t: float, s2_t: float,
) -> list:
    """
    Combine three sector-best laps into one stitched trace.
    """
    def _slice(samples, lo, hi):
        return [dict(s) for s in samples if lo <= s.get("distance_norm", 0.0) <= hi]

    part1 = _slice(s1_samples, 0.0,   0.334)
    part2 = _slice(s2_samples, 0.332, 0.668)
    part3 = _slice(s3_samples, 0.666, 1.0)

    if part2:
        off = s1_t - part2[0]["t"]
        for s in part2:
            s["t"] = round(s["t"] + off, 3)
    if part3:
        off = (s1_t + s2_t) - part3[0]["t"]
        for s in part3:
            s["t"] = round(s["t"] + off, 3)

    def _blend(left, right, norm):
        if not left or not right:
            return []
        skip = {"distance_norm", "t", "px", "py", "pz"}
        shared = {k for k in left[-1] if k not in skip} & {k for k in right[0] if k not in skip}
        mid: dict = {
            "distance_norm": norm,
            "t": round((left[-1]["t"] + right[0]["t"]) / 2, 3),
        }
        for k in shared:
            try:
                mid[k] = round((left[-1][k] + right[0][k]) / 2, 4)
            except (TypeError, ValueError):
                mid[k] = right[0][k]
        return [mid]

    mid12 = _blend(part1, part2, 0.333)
    mid23 = _blend(part2, part3, 0.667)

    p1 = part1[:-1] if mid12 and part1 else part1
    p2 = part2[1:-1] if mid12 and mid23 and part2 else (
         part2[1:]  if mid12 and part2 else
         part2[:-1] if mid23 and part2 else part2)
    p3 = part3[1:] if mid23 and part3 else part3

    return p1 + mid12 + p2 + mid23 + p3


# ─── Track References ─────────────────────────────────────────────────────────

def update_track_references(track: str, game: str):
    """
    Recompute best-lap and theoretical-best references for *track*.
    """
    if not track or track == "unknown":
        return

    with _db_lock:
        conn = _db_connect()
        try:
            # Filter out-laps and obviously partial laps (lap_time_s < MIN_VALID_LAP_S)
            # so a 5s out-lap "S1" can't poison the theoretical-best calc.
            rows = conn.execute(
                """SELECT l.session_id, l.lap_number, l.lap_time_s, s.started_at
                   FROM laps l
                   JOIN sessions s ON l.session_id = s.session_id
                   WHERE s.track=? AND s.game=?
                     AND l.lap_number > 0
                     AND l.lap_time_s IS NOT NULL AND l.lap_time_s >= ?
                   ORDER BY l.lap_time_s ASC""",
                (track, game, MIN_VALID_LAP_S),
            ).fetchall()
        finally:
            conn.close()

    if not rows:
        return

    best_row = rows[0]
    best_data = _db_get_lap_samples(best_row["session_id"], best_row["lap_number"])
    if best_data:
        with _db_lock:
            conn = _db_connect()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO track_references
                       (track, reference_type, session_id, lap_number,
                        samples_json, updated_at)
                       VALUES (?,?,?,?,?,?)""",
                    (track, "best_lap",
                     best_row["session_id"], best_row["lap_number"],
                     _encode_samples(best_data["samples"]),
                     datetime.now().isoformat()),
                )
                conn.commit()
            finally:
                conn.close()

    best_s = [None, None, None]
    best_meta = [None, None, None]
    sector_bounds = [(0.0, 0.333), (0.333, 0.667), (0.667, 1.0)]
    # Per-lap sector writes collected during the loop and flushed in a
    # single transaction at the end. Same validation as theoretical-best
    # (sector sum within 5% of lap_time_s); failing laps stay NULL.
    per_lap_writes: list[tuple] = []

    for row in rows:
        lap_data = _db_get_lap_samples(row["session_id"], row["lap_number"])
        if not lap_data or not lap_data["samples"]:
            continue
        samples = lap_data["samples"]
        # Sanity: compute all three sectors first and skip the entire lap if
        # their sum diverges meaningfully from the recorded lap_time_s. A
        # paused-mid-lap or glitched-sample lap can still have lap_time_s
        # >= MIN_VALID_LAP_S (passes the SQL filter) but produce nonsensical
        # sector times (e.g. 6.7s × 3 = 20s for a 51s lap on Maple Valley).
        # Letting those through poisons the theoretical-best calc.
        sec_times = [_sector_time_from_samples(samples, lo, hi)
                     for (lo, hi) in sector_bounds]
        if any(st is None for st in sec_times):
            continue
        sec_sum = sum(sec_times)
        lap_time = row["lap_time_s"]
        # Allow up to 5% drift between Σsectors and lap_time_s — covers
        # sampling jitter at the 1/3 and 2/3 boundaries. Beyond that the
        # samples can't be trusted as a representative full-lap trace.
        if lap_time and abs(sec_sum - lap_time) > 0.05 * lap_time:
            _log.info(
                f"track_references: skipping {row['session_id']} L{row['lap_number']} "
                f"— sector sum {sec_sum:.2f}s diverges from lap {lap_time:.2f}s "
                f"(probably partial / glitched samples)"
            )
            continue
        per_lap_writes.append(
            (round(sec_times[0], 3), round(sec_times[1], 3), round(sec_times[2], 3),
             row["session_id"], row["lap_number"])
        )
        for i, st in enumerate(sec_times):
            if best_s[i] is None or st < best_s[i]:
                best_s[i] = st
                best_meta[i] = {
                    "session_id": row["session_id"],
                    "lap": row["lap_number"],
                    "samples": samples,
                }

    if per_lap_writes:
        with _db_lock:
            conn = _db_connect()
            try:
                conn.executemany(
                    "UPDATE laps SET s1_time_s=?, s2_time_s=?, s3_time_s=? "
                    "WHERE session_id=? AND lap_number=?",
                    per_lap_writes,
                )
                conn.commit()
            finally:
                conn.close()

    # ── Mistakes & Events detection ─────────────────────────────────
    # Run for every session whose laps we just iterated. Stores results
    # in lap_events; replaces any prior rows for the same (session, lap)
    # so re-runs are idempotent. See analysis/events.py.
    try:
        from analysis.events import detect_lap_events
        # Group writes by session so we can wipe-and-replace cleanly.
        events_by_session: dict = {}
        # Pull engine_max_rpm per session (needed for the bad-shift detector)
        session_ids = sorted({row["session_id"] for row in rows})
        engine_rpms: dict = {}
        if session_ids:
            with _db_lock:
                conn = _db_connect()
                try:
                    qs = ",".join("?" * len(session_ids))
                    for r in conn.execute(
                        f"SELECT session_id, MAX(rpm) as max_rpm FROM lap_samples "
                        f"WHERE session_id IN ({qs}) GROUP BY session_id",
                        session_ids
                    ):
                        # Approximation: peak observed RPM is close to
                        # engine_max_rpm. Real engine_max_rpm isn't stored
                        # per session today; this lets the detector work
                        # without a schema change.
                        engine_rpms[r["session_id"]] = r["max_rpm"]
                except Exception:
                    pass
                finally:
                    conn.close()

        for row in rows:
            sid = row["session_id"]
            ln = row["lap_number"]
            lap_data = _db_get_lap_samples(sid, ln)
            if not lap_data or not lap_data.get("samples"):
                continue
            try:
                ev = detect_lap_events(
                    lap_data["samples"],
                    lap_data.get("distance_m") or [],
                    engine_rpms.get(sid),
                )
            except Exception as exc:
                _log.warning(f"event detection failed for {sid} L{ln}: {exc}")
                continue
            if ev:
                events_by_session.setdefault(sid, []).append((ln, ev))

        if events_by_session:
            with _db_lock:
                conn = _db_connect()
                try:
                    for sid, pairs in events_by_session.items():
                        # Wipe prior events for these (session, lap) combos
                        for ln, _ in pairs:
                            conn.execute(
                                "DELETE FROM lap_events WHERE session_id=? AND lap_number=?",
                                (sid, ln)
                            )
                        # Insert fresh detections
                        rows_to_write = [
                            (sid, ln, e["event_type"], e["distance_m"],
                             e["distance_norm"], e["severity"], e["description"])
                            for ln, evs in pairs for e in evs
                        ]
                        if rows_to_write:
                            conn.executemany(
                                "INSERT INTO lap_events "
                                "(session_id, lap_number, event_type, distance_m, "
                                " distance_norm, severity, description) "
                                "VALUES (?,?,?,?,?,?,?)",
                                rows_to_write,
                            )
                    conn.commit()
                finally:
                    conn.close()
            total = sum(len(evs) for pairs in events_by_session.values() for _, evs in pairs)
            _log.info(f"lap_events: detected {total} events across "
                      f"{sum(len(p) for p in events_by_session.values())} laps")
    except Exception as exc:
        _log.warning(f"lap_events: detector pass failed: {exc}")

    if not all(best_meta):
        return

    s1_t, s2_t, s3_t = best_s
    theoretical_best = round(s1_t + s2_t + s3_t, 3)
    stitched = _stitch_sector_samples(
        best_meta[0]["samples"], best_meta[1]["samples"], best_meta[2]["samples"],
        s1_t, s2_t,
    )

    with _db_lock:
        conn = _db_connect()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO track_references
                   (track, reference_type, session_id, lap_number,
                    samples_json,
                    theoretical_s1_s, theoretical_s1_session_id, theoretical_s1_lap,
                    theoretical_s2_s, theoretical_s2_session_id, theoretical_s2_lap,
                    theoretical_s3_s, theoretical_s3_session_id, theoretical_s3_lap,
                    theoretical_best_s, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (track, "theoretical",
                 None, None,
                 _encode_samples(stitched),
                 s1_t, best_meta[0]["session_id"], best_meta[0]["lap"],
                 s2_t, best_meta[1]["session_id"], best_meta[1]["lap"],
                 s3_t, best_meta[2]["session_id"], best_meta[2]["lap"],
                 theoretical_best,
                 datetime.now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    _log.info(
        f"track_references: {track!r} | "
        f"best={best_row['lap_time_s']:.3f}s | theoretical={theoretical_best:.3f}s"
    )


def _update_track_references_bg(track: str, game: str):
    try:
        update_track_references(track, game)
    except Exception as exc:
        _log.warning(f"track_references update failed ({track!r}): {exc}")
