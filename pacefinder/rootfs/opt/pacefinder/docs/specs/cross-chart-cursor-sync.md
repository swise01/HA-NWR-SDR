# Cross-chart cursor sync

## Purpose
Hovering any chart on the Telemetry tab should show a vertical line at the same x-position across **all** charts, plus a position dot on the track map. Standard pattern in MoTeC i2 and AIM Race Studio. Massively multiplies the value of every chart already on the page — without it, comparing channels at a corner takes back-and-forth eyeballing.

## Behavior

### Cursor states
- **Idle** — no cursor visible
- **Hovering** — mouse moved over any chart; cursor follows mouse x-position
- **Locked** — user clicked; cursor stays put even when mouse leaves; clicking again (or pressing `Esc`) returns to idle

### Visual
- Thin vertical line (~1px, ~50% opacity) at the cursor x across every chart in the panel: DELTA, Speed, Throttle, Brake, Gear, Slip
- On the **track map**: a filled circle (~6px) at the spatial position that corresponds to that lap distance; for the reference lap, a second smaller circle in a different color
- Per-chart **inline value badge** at the cursor position showing the channel value(s) for selected laps, e.g. `L2: 102 mph` / `L1: 98 mph`
- **Floating summary** near the cursor (small panel): `63% of lap · 1240m · L2 vs L1: −0.42s`
- All visuals respect the current channel selection (don't show throttle badge if Throttle is unchecked)

### X-axis modes
- Sync works in both **Distance** and **Time** x-axis modes
- Distance is the default and the natural shared coordinate; Time mode requires per-lap time alignment (each lap may differ in length)
- For Time mode: cursor x maps to "elapsed seconds within lap" — applied independently to each lap (so L1 at 30s and L2 at 30s are at different track positions). Track map dot uses the **selected reference lap** as the source of truth for spatial position

### Interaction details
- Mouse leaves all charts (no lock) → cursor disappears
- Mouse leaves and cursor is locked → cursor stays; visual treatment changes slightly (e.g., line becomes solid instead of semi-transparent) so the user knows it's locked
- Click on track map → scrubs cursor to that map position, snapped to nearest data point
- Keyboard (when cursor locked or any chart focused): `←` / `→` to nudge ±1% of lap, `Shift+←` / `Shift+→` for ±10%

### Performance
- Throttle cursor updates to **~30 fps** (use `requestAnimationFrame`); 60 fps was unnecessary and burns battery
- Avoid full re-render — move only the cursor SVG/canvas elements, not the underlying chart data
- Lap data is per-packet (60 Hz × ~110s lap ≈ 6,600 points/lap × N selected laps). A binary search on cached x-arrays for the cursor's nearest data point should be O(log n) per chart per frame

## Scope
- New shared cursor state module in the dashboard's JS (vanilla, stdlib-aligned with the project's "no framework" ethos)
- Cursor overlay rendering for each existing chart type
- Track map: distance → (x, y) lookup table, dot rendering
- Inline value badges + floating summary panel
- Click-to-lock behavior on charts and on the track map

## Out of scope
- Two-finger touch gestures on mobile (defer; basic touch tap-to-lock is fine for v1)
- Cursor sync between sessions / between this page and the live dashboard
- Recording cursor position for later replay/sharing
- Y-axis crosshair (only x is synced; y stays per-chart)

## Cross-repo work
- `pacefinderapp` only

## Open questions
- Floating summary panel — how much info before it gets noisy? Recommend: distance, time-vs-reference, and primary channel (speed). Hide brake/throttle/gear unless explicitly requested.
- Time-mode x alignment when laps have very different lengths (e.g. an in-lap vs a hot lap) — does the cursor "run off" the shorter lap's chart? Recommend: clamp to lap end and dim that lap's badge to indicate "past end of lap".
- For the track map dot in Time mode with multiple selected laps at different track positions — show one dot per lap? Could clutter. Recommend: show only the reference lap's dot in Time mode, all selected laps' dots in Distance mode.
- Should the cursor persist across X-axis mode toggle? E.g., locked at 1240m → toggle to Time → cursor jumps to whatever time corresponds to 1240m on the reference lap. Recommend: yes, preserve.
