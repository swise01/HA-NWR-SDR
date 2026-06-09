# Inline the Telemetry tab + add race-themed loading screens

## Purpose
The Telemetry tab on the session detail page is currently rendered inside an `<iframe>` pointing at `/sessions/telemetry?embed=1&id=…`. Iframes are the wrong primitive for tabs in a single-page app:

- The user reports double scrollbars on small screens — symptom of an iframe whose body scrolls inside a parent container that also scrolls.
- `tokens.css` and `base.css` are re-parsed inside the iframe.
- Keyboard focus gets trapped (e.g. spacebar pan only works when the chart is focused).
- URL params and cross-tab state need awkward workarounds (`postMessage` for the Deep Dive spec's "click event marker → jump to Telemetry pre-zoomed" interaction).
- A second JS load + init on every tab switch.

This spec covers two related changes:

1. **Inline the Telemetry tab** — render the markup directly into `<div id="tab-telemetry">` and lazy-init a `Telemetry.init()` namespace on first switch. Same pattern Deep Dive already uses.
2. **Race-themed loaders** — replace the current plain "Loading…" text with five small thematic loader components, picked per loading context.

## Inline migration

### Behavior

- Move the markup currently inside `net/pages/telemetry.py` (the breadcrumb is dropped, the standalone `.tb` is dropped, the rest is the `.tele-layout` block) into a new container in `net/pages/sessions.py` under the existing `<div id="tab-telemetry">`.
- Wrap `static/js/telemetry.js` in an IIFE that exposes `window.Telemetry = { init }`.
- `Telemetry.init(sessionId, game, track)` does what the current top-of-file initialisation does — fetch session/data, render charts, attach event handlers.
- `switchTab('telemetry')` in `static/js/sessions_session.js` calls `Telemetry.init()` lazily on first switch, identical to the Deep Dive lazy-init pattern.
- `?embed=1` branch in telemetry.py is removed — there's only one mount point now.
- Move `static/telemetry.css` (currently empty) and the inline `<style>` block from telemetry.py into a real stylesheet `static/sessions_telemetry.css` linked from sessions.py.

### Standalone route handling
`/sessions/telemetry?id=…` is the standalone route the iframe currently targets. Two options:

- **A.** Keep the route as a 301 redirect to `/sessions/session?id=…&tab=telemetry`. Preserves any external bookmarks.
- **B.** Drop the route entirely; assume nothing links to it externally.

**Lean A.** Trivial to add and prevents broken links if the user shared one.

### Acceptance
- Telemetry tab loads with no iframe in the DOM tree.
- One vertical scrollbar maximum on the session detail page (the page body); `.ctrl-col` may still have its own when there are too many laps to fit.
- Browser back/forward across tabs preserves selected lap state.
- The `keydown` listeners (`Space` for pan, `←`/`→` for nudge, `esc` for unlock) work as soon as the user clicks anywhere in the chart area — no iframe focus trap.
- `/sessions/telemetry?id=…` (option A) redirects to the session detail page with the right tab pre-selected.

## Race-themed loaders

Five loader variants, each animated with vanilla CSS keyframes (no JS animation loop), each ≤ 3 KB rendered HTML+CSS. The choice of loader per context is in **Loader contexts** below.

Live previews of all five are rendered in [`docs/mockups/race-loaders.html`](../mockups/race-loaders.html) — open the file in a browser.

### 1. Rev counter sweep
A small semi-circular tachometer (~80 px wide) with a needle that sweeps from idle (left) past the green / amber / red zones to redline (right) and back, in a 1.2-second loop. The redline glows on each peak.

**Use for**: short loads (< 1 s expected). Headline strip on Deep Dive, lap-times table on Overview, sessions list on the home page. Background ambient — visible but doesn't shout.

**Visual**:
```
        🔘
    ╱   │   ╲
   ╱  6│7   ╲   ← needle sweeping toward 7 redline
  │ 4  │  8 │
  │ 2  │  10│
  │ 0──┴──12│
   ╲       ╱
    ╲_____╱
```

### 2. Christmas tree (starting lights)
Five horizontal lights stacked vertically, lighting up red one-by-one (1-2-3-4-5) over ~3 seconds, then all flicking green together for 0.4 seconds, then resetting. Mirrors a real F1 / FM2023 race start sequence.

**Use for**: medium loads (1–3 s expected). The Deep Dive tab on first switch (lap_samples decompression + analysis takes a beat), the Telemetry tab on first switch.

**Visual**:
```
     ┌──────┐
     │  ●   │   red 1 ─┐
     ├──────┤          │
     │  ●   │   red 2  │
     ├──────┤          │ → all green for 0.4s
     │  ●   │   red 3  │   then reset
     ├──────┤          │
     │  ●   │   red 4  │
     ├──────┤          │
     │  ●   │   red 5 ─┘
     └──────┘
```

### 3. Pit-stop tyre change
Four corner-positioned tyre icons that fill clockwise (FL → FR → RR → RL) with an amber arc, then all flash green when the "pit crew" finishes. Total cycle ~3 seconds.

**Use for**: long loads (≥ 3 s expected). AI Coaching analysis (already visibly slow), the post-race modal opening on session-end if we add session-summary computation later.

**Visual**:
```
        ⏱
   ╔═══════════╗
   ║ 🛞      🛞 ║   ← FL filling clockwise
   ║           ║
   ║ 🛞      🛞 ║
   ╚═══════════╝
```

### 4. Lap counter tick
A monospaced lap number that ticks up `L1 → L2 → L3 …` with a slot-machine-style rolling animation per digit, looping back to L1 after L9. Subtle, used as a skeleton placeholder.

**Use for**: in-row loaders inside tables that haven't loaded yet. Lap-times table while waiting for `/sessions/session/data`. Per-lap rows in the Mistakes & Events list.

**Visual**:
```
  ┌─────┐
  │ L 3 │   ← L digit fixed, number rolls
  └─────┘
```

### 5. Tyre warming
A small four-corner tyre grid where each corner cycles through cold (blue) → optimal (green) → hot (amber) → cold over ~2 seconds. The corners are slightly out of phase so the colors ripple through the grid.

**Use for**: ambient page-level loaders where multiple things are loading at once and we want a non-distracting anchor — e.g. the session detail page on initial load before any tab content is ready.

**Visual**:
```
       ┌────┬────┐
       │ FL │ FR │
       │ 🟢 │ 🟡 │
       ├────┼────┤
       │ 🔵 │ 🟢 │
       │ RL │ RR │
       └────┴────┘
```

### Loader contexts

| Context | Loader | Why |
|---|---|---|
| Sessions home / track / game pages | Rev counter | Quick fetch, single-purpose |
| Session detail initial load | Tyre warming | Multiple subsystems loading; ambient anchor |
| Overview tab — Lap Times table rows | Lap counter | Fits in-row; reads as "counting up" |
| Deep Dive tab first switch | Christmas tree | Computation takes a beat; thematic |
| Telemetry tab first switch | Christmas tree | Same; biggest payload |
| AI Coaching | Pit-stop tyre | Slow; deserves the elaborate one |
| Live dashboard reconnect | Rev counter | Quick; minimal |

### Implementation notes

- One CSS file `static/loaders.css` holds the keyframes + styles for all five.
- One HTML helper file `static/js/loaders.js` exposing `Loaders.show(target, kind)` / `Loaders.hide(target)` — kind is `'rev' | 'tree' | 'pit' | 'lap' | 'warm'`. The function injects the right markup, returns a token; hide takes the token. Doesn't replace the existing per-page "Loading…" strings — wraps them.
- Loaders should respect `prefers-reduced-motion: reduce` — collapse to a static colored bar with a barber-pole CSS gradient. Not optional, accessibility table stakes.
- Loaders should auto-fade-out over 200 ms when removed, even if the content under them is already painted, so the transition feels deliberate.
- All loaders are pure CSS animations — no `requestAnimationFrame`, no JS `setInterval`. Cheap and never desyncs.

### Acceptance for loaders
- Each loader renders correctly in [`docs/mockups/race-loaders.html`](../mockups/race-loaders.html) (the spec mockup file checked in alongside).
- Rev counter cycles in ≤ 1.2 s, christmas tree in ~3 s including the green flash, pit-stop in ~3 s including the green flash, lap counter ticks at 1 Hz, tyre warming at 2 s per cycle.
- `prefers-reduced-motion: reduce` collapses every loader to a static barber-pole bar.
- Replacing the existing `<div>Loading…</div>` strings with `Loaders.show(el, 'tree')` does not regress paint time on the slow Pi (target: first paint within 50 ms of the JS call).

## Out of scope
- **New visual identity / brand work**. The loaders use the existing token palette — no new colors, no new fonts.
- **Tab-tab transitions / route animations**. The loader is for content not yet present; the tab switch itself stays instant.
- **Sound / haptic feedback**. Tempting (engine rev sample on rev-counter loader, "lights out and away we go" callout on christmas tree) but adds an audio dependency and most race-engineers run the page muted.
- **Replacing the existing dashboard live-status indicator** — that's a state, not a loader.

## Open questions
- **Christmas tree timing**. Real F1 lights have variable hold (random 0.2–3 s) before going green. For a loader we want predictability. Lean: fixed 3 s total, all five lights up, then green, then reset.
- **Loader for fast loads**. If a fetch returns in < 200 ms, do we even show the loader, or skip it to avoid flicker? Lean: 200 ms minimum delay before showing, then minimum 400 ms display once shown — anti-flicker pattern.
- **Pit-stop crew vs. just tyres**. The mockup shows tyres only. Adding a "crew" SVG figure might be cute but is a lot of art. Lean: tyres only.
- **Lap-counter loop count**. Does it loop forever, or stop at L9 with a "—" placeholder? Lean: loop forever — the loader is going to be replaced by real content the moment data arrives.
