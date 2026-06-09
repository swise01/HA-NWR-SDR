# Perf baseline

Pre-optimization measurements collected with the instrumentation from
[`perf-audit-and-instrument`](specs/perf-audit-and-instrument.md). Every
optimization PR cites against the most recent row.

How to capture:
1. Stop the listener, restart fresh (clears the ring buffer)
2. Open `/debug/perf` in another tab
3. In your normal browser, hit each "page" once cold (DevTools → Disable cache enabled), then once warm
4. Refresh `/debug/perf` and copy the numbers into the table below

| Date | Git SHA | Hardware | Browser | Page | Cold ms | Warm ms | Server p95 ms | DB ms (avg) | Notes |
|---|---|---|---|---|---|---|---|---|---|
| _fill in_ | _sha_ | Mac M1 | Chrome 14x | `/sessions/telemetry?id=…` | | | | | |
| _fill in_ | _sha_ | Mac M1 | Chrome 14x | `/sessions` | | | | | |
| _fill in_ | _sha_ | Mac M1 | Chrome 14x | `/sessions/track?name=…` | | | | | |
| _fill in_ | _sha_ | Mac M1 | Chrome 14x | `/` (dashboard) | | | | | |
| _fill in_ | _sha_ | Pi 4 | Safari iPad | `/sessions/telemetry?id=…` | | | | | |
| _fill in_ | _sha_ | Pi 4 | Safari iPad | `/sessions` | | | | | |
| _fill in_ | _sha_ | Pi 4 | Safari iPad | `/sessions/track?name=…` | | | | | |
| _fill in_ | _sha_ | Pi 4 | Safari iPad | `/` (dashboard) | | | | | |

## Suspect ranking before measuring (revisit after data lands)

1. `/sessions/track/data` — multi-query stitch, no caching
2. `/sessions/data` — every session every hit, no pagination
3. Telemetry SVG render — large per-lap JSON parse + many SVG paths
4. `/sessions/lap-samples` — large JSON payload per fetch
5. Reference-samples decode on telemetry page

These are guesses; the data decides.
