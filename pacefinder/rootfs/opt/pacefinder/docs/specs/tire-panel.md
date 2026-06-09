# Tire panel — replace single Tyres checkbox with 4-corner panel

## Purpose
Forza UDP carries per-wheel tire data (temperatures always; wear in FH5). The Telemetry tab currently exposes this as a single `Tyres` checkbox in the Channels list — almost no usable info comes out of it. A proper 4-corner tire panel turns this into one of the more important diagnostic views (degradation, fade, balance issues all show up in tire data first).

## Behavior

### Panel layout
- Replace the `Tyres` checkbox with a `Tires` panel toggle (expand/collapse)
- When expanded, show a **2×2 grid** matching the car's top-down view:
  ```
  [FL]  [FR]
  [RL]  [RR]
  ```
- Each cell is its own mini line chart of temperature over the lap (x-axis matches the page-wide Distance/Time mode)
- Cell header shows: corner label + current/avg/peak temp, e.g. `FL — avg 92°C · peak 108°C`
- Selected laps overlay in their colors (same convention as other charts)
- Cells share a y-axis scale across all four corners so balance issues are visible at a glance

### Temperature interpretation
- Optional "ideal zone" band rendered behind the line (e.g. 80–100°C green band, configurable). Off by default for v1; behind a toggle later.
- Hover within a cell respects cross-chart cursor sync (#8) — value badge appears like any other chart

### Wear (FH5 only)
- When the session is FH5 (packet size 331), render a row of **4 horizontal wear bars** below the 2×2 temp grid
- Bars labeled FL/FR/RL/RR; fill represents wear progression over the lap (0% start → end value)
- Wear is end-of-lap value, not over-time chart — single bar per wheel
- For FM2023 (no wear data), hide the wear row entirely; don't show empty placeholders

### Default state
- Panel **collapsed** by default to keep the page short on first load
- User-expanded state persists across sessions (localStorage)

## Scope
- Replace single `Tyres` checkbox with collapsible `Tires` panel
- 2×2 temp chart grid, shared y-axis, multi-lap overlay, cursor-sync compatible
- FH5-only wear bar row, conditionally rendered
- LocalStorage for expand/collapse state

## Out of scope
- Pressure (not in Forza UDP standard format)
- Brake temp (separate channel, separate spec if needed)
- Cross-session tire degradation trends (later — would need history aggregation)
- Editable ideal-zone band

## Cross-repo work
- `pacefinderapp` only

## Open questions
- y-axis scale: shared across all 4 cells (better for spotting balance) vs. per-cell (better for seeing individual variation in absolute terms). Recommend shared.
- Should tires be a top-level panel toggle alongside Speed/Throttle/etc., or moved into its own "Diagnostics" cluster with brake temps, fuel, etc. when those exist? Recommend: top-level panel for now; cluster later if it gets crowded.
- For FH5 wear bars: bar fill direction — left-to-right showing accumulation, or right-to-left showing remaining? Recommend left-to-right showing accumulated wear (matches mental model of "how much did this lap cost me").
- Cell hover badge format — temp at cursor position, or temp + delta vs reference lap? The latter is more useful but more visual noise.
