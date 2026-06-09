# Track map interactivity

## Purpose
The track map at the bottom of the Telemetry tab is the most legible single visualization on the page (per design feedback). Currently it shows one line colored by speed. Make it do more: overlay multiple laps' racing lines, switch the colorization channel, label corners. Independent of cursor sync (#8) but composes well with it.

## Behavior

### Multi-lap line overlay
- When more than one lap is selected, render each selected lap's racing line as its own path
- Line color matches the lap's color in the lap selector (green for L1, blue for L2, etc.)
- Lines are semi-transparent (~60%) so overlap is visible
- Reference lap rendered slightly thicker (~2px vs 1.5px) to give visual anchor
- Where lines diverge significantly (e.g. different lines through a corner), the difference is immediately visible

### Color mode toggle
A small control above the map: `Color: [Speed ▼]` with options:
- **Speed** (default) — blue slow → red fast
- **Brake** — line dims to gray normally, fills red where brake > N% (configurable threshold, default 20%)
- **Throttle** — gray normally, green where throttle > 90%
- **Gear** — discrete colors per gear (categorical palette)
- **Slip** — gray normally, amber/red where slip is in Managed/Excess zones

When color mode is non-Speed and multi-lap overlay is on, only the **reference lap** is colorized; other laps render as thin neutral lines so the colorized data stays legible.

### Corner labels
- Auto-detect corners as local speed minima (downward zero-crossings of d(speed)/d(distance)) on the reference lap
- Label them numerically: T1, T2, … in order of encounter
- Position label slightly outside the racing line on the geometric "outside" of the corner (cross product of tangent + center direction)
- Labels are toggled by a checkbox `Corners` near the color mode control; off by default to avoid clutter

### Click + hover (composes with cursor sync #8)
- Click anywhere on the map → cursor scrubs to that position (already in #8 spec; reiterating for completeness)
- Hover with cursor sync active → map shows the existing position dot from #8

### Edge cases
- One lap selected → no overlay, single line as today
- Lap missing GPS/position data → skip silently, show only valid laps
- Two laps with very different track lengths (e.g. wrong track auto-detected) → render anyway; user will spot the mismatch immediately

## Scope
- Map renderer accepts an array of laps (currently one)
- Color-mode dispatcher per channel
- Corner detection algorithm + label placement
- New UI controls: Color dropdown, Corners checkbox

## Out of scope
- Editable corner numbers / custom corner naming (defer; auto-detect should be good enough)
- Sector boundaries on the map (could be added later — sector starts/ends as colored markers)
- 3D elevation rendering
- Saving/loading custom map color modes per user

## Cross-repo work
- `pacefinderapp` only

## Open questions
- Corner detection — local minima will pick up false positives on bumpy straights. May need a minimum speed-drop threshold (e.g. only count if speed dropped > 15 mph from local max). Tune empirically.
- Brake / throttle / slip color modes — should the threshold be configurable, or hardcoded? Recommend: hardcoded sensible defaults for v1, expose via URL param if anyone asks.
- Categorical gear palette — distinguishable colors for 1–8 (assume 8-speed max for most cars). Use existing palette or pick a colorblind-friendly set?
- For multi-lap overlay with > 4 laps (when the lap selector cap is lifted) — does the visual collapse into mush? Recommend: cap the overlay at 4 laps even if more are selectable elsewhere.
