# Session Detail: "Deep Dive" tab

## Purpose
The session detail page today has two tabs: **Overview** (lap-times table, AI coaching button) and **Telemetry** (multi-channel charts vs distance/time). Both are valuable, but neither answers the question a hobbyist actually asks after parking the car: **"What should I do differently?"**

Telemetry charts are time-series traces — they require the user to know what to look at. Lap-times tell you *how* slow you were, not *where* or *why*. We capture a rich per-sample stream including position (`px`, `pz`), four-corner slips, suspension travel, lateral and longitudinal G — enough to answer the question with **shape-led visualisations** the user can read at a glance.

A new **Deep Dive** tab leans on viz that the existing Telemetry tab doesn't do: spatial (track map), shape (G-G diagram), and aggregate (multi-lap overlays). Each panel answers one question and is interactive enough to drill into when something looks off.

## Behavior

### Tab placement
Add a third tab next to **Overview / Telemetry** on `/sessions/session?id=…`, labelled **Deep Dive**. URL param: `?tab=deepdive`. Inherits the same `_id` / `_sgame` / `_strack` query params used by the existing tabs. Loads from a new endpoint `/sessions/session/deepdive` that returns the panel payloads (computed server-side from `lap_samples` so the client doesn't ship raw 60 Hz JSON for thousands of samples just to draw a few charts).

### Layout
Above 1100 px viewport: **Track Map** takes the left half (sticky on scroll); G-G + Speed-trace stack on the right; remaining panels flow below in a two-column grid. Below 1100 px: everything stacks vertically, Track Map first.

A small **headline strip** sits above the panels: 4–5 numbers in a row (best lap, max speed, finish position, gained, fastest sector if available). One-line scan, no full bullet list.

### Panel 1: Track Map (the headline)
Top-down racing line drawn from `(px, pz)` samples, with a channel-driven color overlay. **The defining viz of the tab.**

- **Line drawing**: SVG or Canvas path traced through the lap's `(px, pz)` points. Smoothed with the same downsampling we already do in the Telemetry tab.
- **Channel selector** (top-right of the card): a row of small chips — `Speed` (default), `Throttle`, `Brake`, `Slip`, `Gear`. Switching repaints the line color along its length using a fixed colormap per channel:
  - Speed: viridis-like (dark blue → cyan → yellow → green → red proportional to speed range)
  - Throttle: gray (off) → green (full)
  - Brake: gray (off) → red (full)
  - Slip: gray (low) → amber → red (high) — uses combined slip across all four corners
  - Gear: discrete categorical palette
- **Multi-lap overlay**: ghost lines for every other valid lap drawn at 15% opacity behind the selected lap. The selected lap's line is full opacity and ~3× as thick. Lap selector (chip row above the map) lets the user pick which lap is bold.
- **Event markers**: pinned dots on the line at the position of each detected mistake (see Panel 4). Click a dot → tooltip with event label + jump-to-telemetry button.
- **Hover**: any point along the line → tooltip with `distance · speed · throttle · brake · gear · slip` for that sample.
- **Click**: any point → opens the Telemetry tab pre-zoomed to ±50 m around that distance.

### Panel 2: G-G Diagram
Scatter of `g_lat` vs `g_lon` for every sample of the selected lap, plotted on a square axis with a faint reference circle at the car's expected grip limit (default ±2 g; configurable later).

- **Reveals**: friction-circle usage. A driver pushing the limit fills the diagram out to the circle. A conservative driver clusters near the origin. Common patterns:
  - Vertical streaks at high `g_lon` = late hard braking (good).
  - Horizontal streaks at high `g_lat` = sustained cornering G (good).
  - Empty quadrants = unused capacity (room to push).
  - Spikes outside the reference circle = wheel locking, kerbs, contact.
- **Multi-lap toggle**: show all valid laps with the selected lap colored, others faint.
- **Hover**: any point → tooltip showing `distance @ <m> · <speed> mph · gear`.
- **Click**: jumps to that point on the track map (highlight + autoscroll the map). Closes the loop between shape and place.

### Panel 3: Speed-Trace Overlay
Distance (x) vs speed (y) for every valid lap, semi-transparent traces with the selected lap bold.

- Quick visual identification of where you slow down, where the slow lap got slow, where the fast lap kept its momentum.
- Shaded delta band between the selected lap and the session-best, optional toggle.
- No interactivity needed beyond hover-to-see-distance — this panel earns its keep by being scannable.

### Panel 4: Mistakes & Events
Auto-detected per-lap incidents, surfaced **both as map markers in Panel 1 and as a sortable list here**. Each row: lap number, distance into lap, event label, one-line detail. Click → highlights the event on the map and jumps Panel 1's selected lap to the right one.

**Detectors** (all heuristic, all tunable in a new `analysis/events.py`):
- **Spin / big slide** — peak combined slip on either rear corner > 1.5 for ≥ 0.3 s, OR rear slip ratio > 0.6 with throttle > 50%. Severity = peak slip × duration.
- **Off-track** — `wheel_on_rumble_strip_*` true for ≥ 0.5 s on the *outside* tyres, OR a velocity drop > 30% over < 0.5 s without proportional brake input.
- **Lockup** — brake > 70% and any wheel rotation speed dropped < 20% of the car's forward speed for ≥ 0.2 s.
- **Bad shift** — gear change accompanied by an RPM jump > 2000 in the wrong direction.
- **Power-on oversteer event** — rear slip ratio > 0.5 with throttle > 70%.

**Output**: max 10 events per session, severity-sorted, "+N more" expandable. Empty state: "Clean session — no incidents flagged."

### Panel 5: Lap Comparison
Two-lap variant of the track map, drawn as the same shape but **split-colored** per segment by who was faster.

- **Reference**: defaults to session-best, picker for any other lap.
- **Compare**: defaults to the next lap, picker.
- **Output**:
  - Total delta at the line (signed seconds).
  - Track line colored green where the comparison lap was faster, red where slower; intensity scaled by magnitude. Thicker lines = larger gap.
  - Top 3 lost windows + top 3 gained windows listed below the map with `+0.34 s @ 1820 m`. Click → highlights that segment.
- Reuses `_interp_dist_to_t` plumbing — same logic the live in-race delta uses, applied between two completed laps.

### Headline strip (top of tab)
Four-to-five chips in a row. Not a bullet list — single short stats:
- `Best 1:11.512 · L2`
- `Top 185.7 mph`
- `Spread 5.6 s`
- `P13 → P4 (+9)` *(race only)*
- `Throttle 62.3%`

Skipped silently when null (e.g. no race outcome on a Time Trial).

## Backend

New endpoint `/sessions/session/deepdive?id=<sid>`:
- Returns JSON:
  ```json
  {
    "headline": [{"label": "Best", "value": "1:11.512 (L2)"}, ...],
    "track_map": {
      "laps": [{"lap_number": 0, "points": [[px, pz, t, speed, thr, brk, gear, slip], ...]}]
    },
    "gg": {
      "laps": [{"lap_number": 0, "points": [[g_lon, g_lat, distance], ...]}]
    },
    "speed_trace": {
      "laps": [{"lap_number": 0, "points": [[distance, speed], ...]}]
    },
    "events": [{"lap_number": 0, "distance_m": 920, "kind": "spin", "severity": 0.84, "detail": "Power-on rear slip 0.61"}],
    "lap_comparison": {
      "reference_lap": 1, "compare_lap": 2,
      "total_delta_s": 0.612,
      "segments": [{"start_m": 0, "end_m": 100, "delta_s": -0.05}, ...],
      "top_lost": [...], "top_gained": [...]
    }
  }
  ```
- Reads `lap_samples` (gzipped per-sample) for the session, decompresses, computes everything in one pass.
- Track-map / G-G / speed-trace points are **downsampled** server-side to a target ~600 points per lap for the map (preserving inflection points), ~400 for G-G (uniform stride). Keeps payload manageable; charts don't need 60 Hz to look good.
- p95 target ≤ 250 ms on a typical 4-lap session. Most of the work is decompression + downsampling.
- All computation in a new module `analysis/deepdive.py` so it's importable + unit-testable.

## Frontend

- New file `static/js/sessions_deepdive.js` loaded on the session detail page alongside `sessions_session.js`.
- Renders all panels into `<div id="tab-deepdive">` (added next to existing `tab-overview` / `tab-telemetry`).
- **Drawing**: SVG for the track map (sharp at any zoom, easy hit-testing for hover/click) + Canvas for the G-G diagram (thousands of points cheap to render). Speed trace = SVG. No external charting library — vanilla path/circle/rect, same dark-mono aesthetic as the rest of the app.
- **Inputs**: lap selector (chip row), channel selector (chip row), comparison-mode dropdowns. All other panels are read-only.
- **Click-through to Telemetry**: URL params `?tab=telemetry&zoomStart=<m>&zoomEnd=<m>&overlayLap=<n>` — the Telemetry tab needs to learn those params.
- No new dependencies.

## Data we already have, no schema change

All inputs are in `lap_samples` (gzipped JSON blob per lap, written at session close). No new captures, no migration. Track-map specifically uses `px`, `pz` which we already store conditionally (see `LapRecord.add_sample`).

**Caveat**: position is captured only when the parser populated `position_x` — sessions before the storage-bundle PR may have it absent. Check at endpoint time and skip the track-map panel for those sessions with a graceful "Older session — track map unavailable" message.

## Out of scope (v1)
- **Sector splits**. Would sharpen Lap Comparison and add a per-sector G-G but requires either configured boundaries or auto-segmentation. Track as a follow-up.
- **Tyre & suspension visualisations** (4-corner heatmaps, asymmetry bars). Useful but heat-map readings are hard to interpret without baseline calibration.
- **Cross-session comparison**. Different page, different scope.
- **Distribution histograms** (time-in-gear, throttle bins, steering rose). Cheap to add later if users want them; v1 stays focused on shape.
- **Slip-angle vs slip-ratio scatter**. Powerful for setup analysis but niche; defer.
- **AI driving-line overlay** (`lane`, `ai_brk_diff`). Forza broadcasts the AI's racing line and brake-input delta — would let us draw the ideal line on the map alongside the user's. Stretch goal once AI-race usage is the norm.
- **Setup recommendations / AI coaching of events**. Different feature.
- **Animation / playback**. "Replay the lap on the map at 5× speed." Tempting but a big lift.

## Acceptance
- A session with ≥ 2 completed laps and `position_x` present renders all panels under the **Deep Dive** tab.
- Track map color overlay updates within 100 ms of changing the channel chip.
- G-G diagram has a faint reference circle at ±2 g and renders ~thousands of points without jank.
- Speed-trace overlay shows every valid lap, selected lap bold.
- Mistakes & Events flags at least one event for any session containing a known spin (manual sanity check).
- Lap Comparison's total delta matches `lap_time_s` difference within 0.05 s.
- Clicking a track-map point opens the Telemetry tab pre-zoomed to ±50 m around that distance.
- Hovering on the G-G scatter then clicking jumps the track map to that location.
- The deep-dive endpoint p95 ≤ 250 ms on a typical 4-lap session.
- Sessions without `position_x` show "Older session — track map unavailable" in Panel 1, and the rest of the tab still works.
- Session detail page loads with no JS errors when `car_class` is unset (regression guard for #109).

## Open questions
- **Track-map orientation**. Forza's coordinate system varies; we'll need to test that the line draws right-side-up across the catalogue. Worst case, allow a per-track rotation override (one-time, persisted) — not blocking.
- **G-G reference circle**. ±2 g is a reasonable default for road-going GT cars but R-class may exceed it. Compute from the data instead (e.g. p99 of `sqrt(g_lat² + g_lon²)`) and round up?
- **Channel selector default**. Speed is the safe default but Throttle is more diagnostic ("where am I lifting?"). Worth picking one.
- **Event severity ranking**. A 0.6 rear slip with throttle on at 200 mph is more concerning than the same slip at 50 mph. Should severity weight by speed? Probably yes.
- **Telemetry-tab zoom params**. `?tab=telemetry&zoomStart=<m>&zoomEnd=<m>` is the simplest contract but the Telemetry tab currently zooms by time index, not distance. Small adapter needed, but worth scoping the existing tab's plumbing first.
- **Multi-lap overlay perf**. 60 Hz × 90 s × 4 laps = ~21,600 points per channel. Even downsampled to 600/lap, the map has 2,400 points + event markers. SVG should be fine; benchmark before committing if it bogs down on the Pi-served Pi-rendered… wait, render is client-side. Fine.
