# Park ACC + F1 support — Forza-only focus

## Purpose
Pacefinder currently tries to support three games (Forza, ACC, F1). In practice only Forza is being raced, but ACC/F1 surface area still costs us: port conflicts at startup, three sets of UI tabs (two of which are always empty), three parsers to keep working, and a marketing site that promises support we're not actively maintaining. Park ACC + F1 so we can focus on making Forza excellent. **Park, not delete** — code stays in tree, resurrectable when we're ready.

## Behavior

### Listener (`listener.py` + `config.py`)
- Drop `acc` (9996) and `f1` (20777) from the `PORTS` dict so the listener no longer binds those ports at startup
- Side effect: the "Failed to bind f1 on port 20777" startup warning goes away
- ACC/F1 protocol bindings + parsers (`parsers/acc.py`, `parsers/f1.py`, related code in `session/protocol.py`) **stay in tree, untouched**

### Sessions home page (`/sessions`)
- Currently a multi-game overview with tabs (All / Forza / ACC / F1). The "All" view is broken and the Forza-specific view at `/sessions/game?name=forza_motorsport` is the more-tested path.
- **Promote**: `/sessions` becomes the Forza overview directly. Render the same content currently at `/sessions/game?name=forza_motorsport` (KPIs scoped to Forza, Forza tracks list, Forza recent sessions).
- **Remove**: the game tabs row entirely (no point showing tabs when there's only one game)
- **Redirect**: `/sessions/game?name=forza_motorsport` → 301 → `/sessions` (preserves any deep links)
- **Remove**: `/sessions/game?name=acc` and `/sessions/game?name=f1` routes (return 404, not relevant)
- **Remove**: the "By Game" cards section on the home page (was showing 1 active card + 2 empty)

### Other pages
- `/sessions/track?name=...` — unchanged (already game-aware via the track scope)
- `/sessions/session?id=...` — unchanged (sessions are stored regardless of game)
- `/sessions/telemetry?id=...` — unchanged
- `/setup` — remove ACC/F1 port config sections from the setup form

### Database
- **No schema changes.** Existing ACC/F1 sessions in the DB (if any) stay there but are filtered out of all UI listings (since Forza becomes the implicit-and-only filter). They become invisible until F1/ACC support is unparked.
- Filter applied by adding `WHERE game = 'forza_motorsport'` (or game LIKE 'forza%' to also catch FH5) to the relevant queries in `db/store.py`

### `CLAUDE.md`
- Update Architecture + Supported Games sections to note: "Forza is the active game; ACC and F1 support is parked — code remains in tree but is not bound at startup."

### Marketing site (`pacefindermarketing`)
- Marketing site currently advertises all three games. Two options: (a) remove ACC/F1 mentions, replace with "Forza Motorsport / Horizon" focus; (b) add a "coming soon" badge to ACC/F1.
- Recommend (a) — less misleading, easy to revert when un-parked. See open question.

## Scope
- `pacefinderapp`:
  - Config: drop ACC/F1 ports
  - UI: collapse tabs, promote Forza view, redirect old URL
  - DB queries: add Forza filter to the home-page queries
  - Setup page: drop ACC/F1 config UI
  - `CLAUDE.md`: updated note
- `pacefindermarketing`: copy and feature card edits (Forza-focused)

## Out of scope
- **Deleting** `parsers/acc.py`, `parsers/f1.py`, ACC/F1 protocol code, or any DB tables
- Changing the underlying packet parser interface (which is multi-game by design — keep that)
- Rewriting the existing per-game `/sessions/game?name=...` view (just promote it as-is)
- Fixing the "All Sessions" page bug — it gets removed, not fixed

## Cross-repo work
- `pacefinderapp`: listener config + UI consolidation + DB queries
- `pacefindermarketing`: marketing copy update (separate PR; can lag the product change by a day or two without harm)

## Resolved decisions
- **Marketing strategy:** drop ACC/F1 product cards/copy from the main site; add a small "ACC and F1 support coming soon" line as roadmap signal.
- **`/sessions/game?name=forza_motorsport` URL:** 301 redirect to `/sessions`. One canonical URL.
- **Existing ACC/F1 sessions in DB:** filter out of all UI listings (`WHERE game LIKE 'forza%'` or equivalent on home-page queries). Rows stay in DB for future restoration.
- **Un-parking trigger:** "When Forza is rock solid" — qualitative, no pre-defined feature gate. Decision left to a future call.
