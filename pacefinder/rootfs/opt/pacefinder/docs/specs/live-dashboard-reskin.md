# Live dashboard reskin

> **Status:** Draft. Cosmetic-only. The live dashboard is the most load-bearing surface in the app — the only one where a regression directly costs the user lap times. **Do not touch functionality or logic during this work.** Visual treatment only.

## Purpose

The current live dashboard (`/`, served from `net/pages/dashboard.py`, with client-side JS in `static/js/dashboard.js`) is functional but predates the visual language established in the recent IA pass. It uses different typography hierarchy, slightly different colour usage, and a layout that doesn't share affordances with the other (post-race) surfaces. A driver who lands on the post-race screens after a session sees a stylistic break.

This reskin brings the live dashboard into the same visual language as the rest of the app — tokens, H1/H2 pattern, topbar, status pills — **without changing any of the wiring underneath.**

The mock lives at [`static/live-mock.html`](static/live-mock.html).

## Scope: what IS in scope

The change is limited to **presentational** layers:

- **HTML template** — `net/pages/dashboard.py` (the inline `DASHBOARD_HTML` constant). Restructure the markup to match `live-mock.html`.
- **CSS** — `static/dashboard.css`. Replace the visual rules. Adopt the design tokens introduced in the mocks PR (`--color-text-tertiary`, `--color-text-quaternary`, plus existing `--color-*` tokens).
- **Client-side rendering only** — `static/js/dashboard.js`. ONLY change the bits that *write to the DOM* (which element gets which value, which class gets toggled on the gear cell to indicate redline). Do not change anything that fetches, decodes, or computes.

## Scope: what is NOT in scope

The following layers are **off limits** in this work:

- **`/stream` SSE endpoint** behaviour and contract — `net/router.py` line 983. Same payload shape, same emit rate, same idle-throttle behaviour shipped in PR #124.
- **`/status` endpoint** payload shape — `net/router.py`. The `state` object structure stays as it is. UI reads what's already there; if a value isn't currently in the payload, that's a separate feature, not part of this reskin.
- **UDP listener and parsers** — `listener.py`, `parsers/`. Capture pipeline is untouched.
- **Session lifecycle** — `session/manager.py`, `session/watchdog.py`. Race-start detection, lap recording, session-close logic stays exactly as-is. The recent hardening (#117–#122) is the reason live capture is rock-solid; we are not touching it.
- **State machine for race-state badges** — the conditions that determine "RECORDING" vs "IDLE" vs "PIT" vs "PAUSED" are exactly as they are today. The UI just renders them with new typography.
- **Polling cadence on the client.** If the page polls `/status` at N Hz today, it continues to poll at N Hz tomorrow.
- **`EventSource` reconnect behaviour** introduced in PR #124. The 60 s idle close-and-reconnect stays.
- **Configuration** — `simtelemetry.config.json`, the `/setup` page, the `/admin` page. None of these are touched.

**Practical rule:** if your diff touches any file outside `static/dashboard.css`, `static/js/dashboard.js` (only the DOM-write functions), and the `DASHBOARD_HTML` constant in `net/pages/dashboard.py`, you've gone outside scope. Stop and split the PR.

## Behaviour

### Layout — preserve exactly what's there today

**This is a re-skin, not a redesign.** The existing dashboard's panel structure works and has been hardened over many sessions. Do not move panels, do not split columns differently, do not collapse sections. The mock at `static/live-mock.html` matches the current production layout one-for-one:

1. **Top bar (single flat row).** Status pill · game chip (`FM` / `ACC` / `F1`) · track name · car name · class badge · PI · nav (Live / Sessions / Setup). Live is the active page indicator. The status pill has a red pulse-dot when racing, muted dot when idle. Flat horizontal layout — no H1/H2 hierarchy here, the live view doesn't have screen real estate to spare.

2. **Four-panel main grid (left to right):**

   - **Throttle / RPM panel.** Two vertical bars side-by-side. Throttle in neutral grey, RPM in a green→amber→red gradient scaled to engine_max_rpm. Big value overlay at the bottom of each bar (`100%` / `7,578 rpm`). Header on the panel: `Throttle / RPM` label.

   - **Brake panel.** Single wide vertical bar, red fill, big `0%` value at bottom.

   - **Rear Slip panel.** Two vertical bars (`RL` and `RR`), green fill when in safe range, amber when > 0.10, red when > 0.20. Big numeric values at bottom (`0.079` / `0.077`).

   - **Lap Timing column (right, slightly wider).** Sections stacked vertically, separated by faint dividers, in this order: `Current / Best` → `Last / Lap #` → `Delta` → `Pos / Grid` → 4-corner `Tyres` → `Gear / Speed`. Every section preserved from the existing dashboard.

3. **Bottom UDP strip.** Per-game packet counters (`forza: 557,388 ok` · `acc: 0 ok` · `f1: 0 ok`), last-packet age, polling rate, Debug button. Exactly as today.

### Full viewport, no max-width

The live dashboard is the one page that should use the **entire viewport**: `height: 100vh`, `overflow: hidden`, panels grow to fill vertical space. The post-race pages cap at 1280 px because they're reading documents; the live page is an instrument cluster and should bleed to every edge.

### Responsive

- Above 1100 px: four-column main grid as designed.
- Below 1100 px: panels collapse to 2×2. Lap-timing column stays intact. The top bar wraps; no critical info goes off-screen.

### Motion

Following the v10 fluency directive carried in `CLAUDE.md`:

- The recording-dot pulse is the only animated element. `transform/opacity`-only animation.
- No transitions on the actual data values — they update on the polling cadence and the eye expects them to flick to new numbers, not to ease.
- Input bars use a short `transition: width 60ms linear` so a sudden 0→100% throttle press isn't visually jarring. 60 ms is below the threshold of perceived lag but smooths a single-frame snap.
- `prefers-reduced-motion`: the pulse animation must respect this and become static.

### Colour discipline

- **Red** is reserved for *negative* state: slower delta, hot tyre, high slip, redline RPM, brake fill, recording badge. The recording badge is the most prominent red on the screen — but it should not pulse fast enough to be distracting.
- **Green** for *positive* state: faster delta, throttle fill, in-range RPM, gain in position.
- **Amber** for *warning* state: tyre warming/cooling, mid-slip, mid-RPM, position lost but recoverable.
- **Gold (accent)** is reserved for the *best-of* indicator: `★` next to the session-best lap.

## Concrete migration steps

Suggested order (each is a separate, self-contained commit):

1. **CSS swap.** Replace `static/dashboard.css` with the styling from `live-mock.html`. Inline the styles into `dashboard.css` so the existing template's class references still resolve. At this point the template still has the old structure but the styling shifts — verify nothing breaks.
2. **Markup restructure.** Replace `DASHBOARD_HTML` in `dashboard.py` with the structure from `live-mock.html`. Map every existing `id` and class the JS uses (e.g. `#tb-stat`, `#tb-track`, `#tb-car`, `#dot`, `#current-lap`, etc.) into the new template — keep the **same IDs and the same JS write paths**. The JS file should not need any change.
3. **JS DOM-write polish.** Now (and only now) touch `dashboard.js` to handle the slightly different class toggles (e.g. `.warn` / `.danger` on slip cells, `.faster` / `.slower` on the lap-delta, redline class on the gear cell). Each toggle should be a one-line change. Do not change the `EventSource` setup, the state parsing, or any fetch logic.
4. **Verify against fixtures.** Use the existing `/admin` debug-inject endpoint (Idle / Cruise / Full / Brake / Pit presets) to confirm every state renders correctly. No live sim required.
5. **Drive one real session.** From cold listener startup → Forza game launched → drive to free play → start a session → lap complete → session ends. Confirm:
   - Recording badge appears on first telemetry packet
   - Lap timer counts up smoothly
   - Best/Last/Theo update on lap close
   - Position display only renders for race-type sessions
   - Tyre temps colour correctly across the operating range
   - Recording badge clears on session close

## Acceptance criteria

- Diff is contained to `static/dashboard.css`, `static/js/dashboard.js` (DOM-write functions only), and the `DASHBOARD_HTML` constant.
- No changes to `listener.py`, `session/`, `parsers/`, `db/`, or any `net/router.py` route handler.
- `/stream` and `/status` payload shapes verifiably unchanged (smoke test: `curl http://roger.local:8000/status` returns the same JSON keys before and after).
- Every state in `/admin` debug-inject preset (Idle / Cruise / Full / Brake / Pit) renders without visual regressions.
- One real-sim session start-to-finish, including a pause/resume cycle, completes with the new UI without any console errors or missed renders.

## Why this work is risky and how we mitigate

The live dashboard is the surface a driver looks at *while* doing something time-sensitive. A visual regression that obscures lap timing or speed for a single second is a real cost. Three guardrails:

- **Mock approval first.** The look gets signed off on the static `live-mock.html` before any production code is touched.
- **Cosmetic-only scope, enforced by the file-diff rule above.** If the temptation arises to "while I'm in here, also fix X functional thing," resist — separate PR.
- **Real-session verification before merge.** Not just preset injection. The driver must drive one full session against the new build before the PR closes.

## Definition of done

- [ ] Reskin PR merged; the live dashboard now matches the visual language of home / session detail / circuit / car pages.
- [ ] `git log -- listener.py session/ parsers/ db/ net/router.py` shows no commits added in this PR.
- [ ] `curl /status` payload identical pre and post.
- [ ] One signed-off real session drive end-to-end.
- [ ] User confirmation that all five `/admin` debug presets render correctly.

## Why deferred from the mocks PR

The mocks PR (#125) is design-only — purely static fixtures under `static/*-mock.html`. This is the implementation spec for one of those mocks; production work happens in a separate PR with its own scope discipline. Pulling them together would muddy the line between design exploration and code shipping.

When this is implemented, this spec moves from `Draft` to `In flight` and back to `Shipped` at merge.
