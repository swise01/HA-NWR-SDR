# Fix sector DELTA column and cumulative DELTA chart

## Purpose
The Telemetry tab's sector table shows `+0.000` in the DELTA column for every row, and the "DELTA — CUMULATIVE TIME VS REFERENCE" chart at the top renders empty (just a red baseline). Both should show real lap-vs-reference differences. Without this, the comparison view's headline insight is missing.

## Observed (broken)
On a session with Lap 1 = 1:49.308, Lap 2 = 1:47.344 (selected as reference), Lap 3 unselected:

| | L2 | L1 | DELTA |
|---|---|---|---|
| S1 | 0:28.717 | 0:29.329 | **+0.000** ← wrong |
| S2 | 0:38.808 | 0:41.025 | **+0.000** ← wrong |
| S3 | 0:39.806 | 0:38.941 | **+0.000** ← wrong |

Cumulative DELTA chart shows only the zero baseline, no data line.

## Behavior (correct)

### Sector table DELTA column
- DELTA = `lap_sector_time − reference_sector_time`, computed per row
- Sign convention: **negative = faster than reference (good), positive = slower (bad)**
- Format: `−0.612` / `+0.865` (3 decimals, leading sign always shown)
- Color: green for negative, red for positive, neutral for `0.000`
- The reference lap's own row shows `0.000` (it equals itself); other selected laps show real deltas

For the example above with Lap 2 as reference, Lap 1's row would show:
| S1 | 0:29.329 | **+0.612** |
| S2 | 0:41.025 | **+2.217** |
| S3 | 0:38.941 | **−0.865** |

### Cumulative DELTA chart
- X-axis: lap distance (0–100% or meters, matching the other charts)
- Y-axis: cumulative time delta vs reference, in seconds (auto-scaled)
- One line per selected lap (excluding the reference itself, which would be flat at zero)
- Line color matches the lap's color in the lap selector (green for Lap 1, blue for Lap 2, etc.)
- Reference line at `y=0` stays for visual anchor
- Tooltip on hover: `Lap N: +/−X.XXXs at Y% of lap`

### Edge cases
- If only the reference lap is selected → hide the chart (no useful data) and show a single-row sector table without the DELTA column
- If no reference is set → DELTA column shows `—`, chart is hidden
- If a lap is incomplete (missing a sector) → that row's DELTA shows `—` for missing sectors

## Scope
- `pacefinderapp` only — backend delta computation in the session/lap module, plus the dashboard HTML/JS that renders the sector table and cumulative chart.

## Out of scope
- Changing the reference selector itself (covered in a future spec for Theoretical Best, Last Lap, etc.)
- Sector boundaries / how sectors are defined
- Cross-chart cursor sync (separate spec)

## Cross-repo work
- `pacefinderapp`: fix delta math + table/chart rendering
- `pacefindermarketing`: none

## Open questions
- Is the bug in the **calculation** (delta returned as 0 by the backend) or the **rendering** (real values computed but template formats them as `+0.000`)? Verify by inspecting an API response (e.g. `curl localhost:8000/api/session/<id>`) before deciding where to patch.
- Does the cumulative DELTA chart render from per-packet data or interpolated sector points? If it's per-packet, performance for a 60Hz Forza stream over a 2-minute lap = ~7200 points per lap × N laps — should be fine for canvas/SVG, worth confirming.
