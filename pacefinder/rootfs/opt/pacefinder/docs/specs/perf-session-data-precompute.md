# Perf: precompute per-lap aggregates so /sessions/session/data is pure-DB

## Purpose
`/sessions/session/data` was identified as the #1 perf offender from the [perf-audit baseline](../perf-baseline.md): 500–1450 ms total wall time with only 5–8 ms in the DB lock — 99% of the request is non-DB work. The handler ([net/router.py:386](../../net/router.py#L386)) re-reads the entire `<sid>_laps.json` file from disk on every hit, JSON-parses every sample (~30 laps × ~600 samples × ~13 fields), then sums + sorts to compute `avg_throttle`, `avg_brake`, `avg_slip`, `peak_slip`, `slip_above_pct` per lap. None of those aggregates ever change after the session closes — they should be computed once and stored.

The telemetry page's `init:total` is dominated by `fetch:session` waiting for this endpoint, so this is the single biggest perceived-speed improvement available.

## Behavior

### Schema
Add five columns to the `laps` table (use the existing `ALTER TABLE … ADD COLUMN` pattern in `_db_init`):
- `avg_throttle  REAL`
- `avg_brake     REAL`
- `avg_slip      REAL`
- `peak_slip     REAL`  — p99 of `(|slip_rl| + |slip_rr|) / 2`
- `slip_above_pct REAL` — % of samples where slip > 0.10

### Write path
Compute the aggregates once at session close inside the path that writes `laps` rows ([db/store.py:467](../../db/store.py#L467) and [session/manager.py:420](../../session/manager.py#L420) `laps_summary` builder). Source the per-sample data straight from `LapBuffer.samples` (already in memory) — no need to re-read from disk.

### Read path
Rewrite `/sessions/session/data` to read everything from SQL:
```sql
SELECT lap_number, lap_time_s, max_speed_mph,
       avg_throttle, avg_brake, avg_slip, peak_slip, slip_above_pct
  FROM laps WHERE session_id=? ORDER BY lap_number
```
Drop the `<sid>_laps.json` read entirely. Drop the per-sample iteration. Drop the `_debug` block in the response. Drop the three `log.info` / `log.warning` / `log.error` lines that fire on every request.

### Backfill
One-shot `scripts/backfill_lap_aggregates.py --apply` that walks every row in `laps` lacking the new columns, joins to `lap_samples`, computes the aggregates, and updates the `laps` row. Dry-run by default. Idempotent (skips rows already populated).

For sessions where `lap_samples` is missing (older data with only the `<sid>_laps.json` files), fall back to reading the JSON file. Skip silently if neither source is available.

### What about `<sid>_laps.json`?
Keep writing it for now — `net/api.py:156` and `/sessions/laps` ([net/router.py:476](../../net/router.py#L476)) still depend on it. Removing it is a separate cleanup, not in scope here.

### Acceptance
- `/sessions/session/data` p95 drops from ~500 ms to ≤20 ms (mostly the SQL query + serialization)
- `init:total` on the telemetry page drops correspondingly (was 600–700 ms, expect ~100 ms)
- Existing sessions show identical aggregate numbers after backfill
- New sessions populate the columns at close
- No `_laps.json` disk read on the hot path

## Scope
- Schema: 5 new columns on `laps`
- Write-path: compute aggregates from in-memory samples at session close
- Read-path: pure-SQL `/sessions/session/data` handler
- Drop the stale `_debug` payload and per-request `log.info` lines
- Backfill script

## Out of scope
- Removing `<sid>_laps.json` entirely (still used by other endpoints — separate cleanup)
- Caching the response (precompute makes caching unnecessary; revisit if measurements still show issues)
- The other top-2 offender (`/sessions/lap-samples`) — addressed by the storage-compression spec
- Aggregate UI changes — same numbers, just served faster

## Cross-repo work
- `pacefinderapp` only

## Open questions
- Should `peak_slip` use p99 (current behavior) or true max? p99 is more robust to a single bad sample. Recommend keeping p99.
- Worth pre-computing additional aggregates while we're here (e.g., `avg_speed_mph`, `time_at_throttle`)? Recommend no — only what the current endpoint returns. Adding new fields is cheap later.
- Do we hold the read-side response payload schema stable, or can we drop the `_debug` block as a breaking change? It's debug-only and never consumed by the frontend — drop it.
