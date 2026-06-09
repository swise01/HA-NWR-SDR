# Performance audit & instrumentation

## Purpose
The web UI feels slow on the Pi (and noticeable even on a Mac), but we have no objective measurements of where the time goes. Before optimizing anything, instrument the app so a single page load produces server-side timings and client-side render numbers we can compare. Use the data to pick the actual top-2 worst offenders and fix those — *not* the assumed ones.

## Behavior

### Server-side instrumentation
- Add a lightweight per-request timing middleware-equivalent in `net/router.py` that records:
  - request method + path
  - total wall time
  - DB time (sum of `db_lock` acquisition + query execution)
  - response payload size
- Emit one structured log line per request at INFO when total > 50 ms, at DEBUG otherwise: `perf method=GET path=/sessions/track/data total_ms=312 db_ms=287 bytes=18432`
- Add a `/debug/perf` endpoint that exposes a rolling ring buffer (last 200 requests) as JSON for inspection during a session

### Client-side instrumentation
- Add a tiny module `static/js/perf.js` (no framework) with three primitives: `mark(name)`, `measure(name, startMark)`, `report()`
- Instrument the heavy pages — telemetry, sessions list, track detail, dashboard — at the spots where time actually accumulates: data fetch, JSON parse, layout/render, first chart paint
- `report()` writes a single console.table entry on page-stable (no operations for 500 ms after first interactive); also POSTs the summary to `/debug/perf/client` so the Pi-side log captures Mac/phone client timings

### Baseline measurements
- Capture cold-cache and warm-cache numbers for each instrumented page on (a) Mac dev box, (b) Pi 4 actual deployment
- Record in `docs/perf-baseline.md` with date, git sha, browser, hardware
- This is the "before" — every subsequent optimization PR cites against it

### Optimization targets (decide AFTER baseline)
Pick top 2 from the data. Likely candidates ranked by suspicion:
1. **Sessions list query** — no pagination; loads all sessions every page hit
2. **`/sessions/track/data`** — multi-query stitch with no caching
3. **Telemetry SVG render** — large per-lap JSON parse + many SVG paths
4. **Track index query** — joins + per-row "best car" subquery
5. **Reference samples decode** — large JSON parse on every telemetry page load

But trust the numbers, not this list.

## Scope
- Server timing logger in `net/router.py` (one wrapper around the route dispatch)
- `/debug/perf` GET endpoint serving the ring buffer
- `/debug/perf/client` POST endpoint accepting client timings
- `static/js/perf.js` shared client primitive
- Instrumentation calls on the heavy pages
- `docs/perf-baseline.md` populated with first measurements

## Out of scope
- The actual optimizations (separate spec/PR per target picked from the baseline data)
- Production telemetry / observability stack — this is local-debug only
- Removing the instrumentation later — keep it; the overhead is microseconds and it's invaluable when something regresses

## Cross-repo work
- `pacefinderapp` only

## Open questions
- Sample rate for `/debug/perf/client` — should we accept every report, or rate-limit to once per 5s per page to avoid log spam? Recommend: rate-limit at the server.
- Should the ring buffer survive listener restart? Probably not — in-memory is fine, this is a debug tool.
- For Pi vs Mac comparison, do we want a side-by-side rendering in `/debug/perf`? Nice but defer to v2.
