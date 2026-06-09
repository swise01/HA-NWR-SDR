# First-run setup wizard

## Purpose
A user who clones-and-runs Pacefinder for the first time has no obvious next step beyond opening `/`. The dashboard is empty, the listener is silent until Forza starts broadcasting, and the storage path defaults to `/mnt/usb/simtelemetry` (or falls back to `./data/`) without the user being told. Land them in the right place: a one-shot wizard that confirms storage, sets expectations about how much disk it'll use, and points at the game-side setup.

## Behavior

### Trigger
- On every page load, the listener checks "is this a first run?". Definition of first run: `simtelemetry.config.json` does not exist on disk **and** no rows in the `sessions` table. (Both conditions — covers fresh installs and stale-config edge cases.)
- When true, the dashboard's pre-render check redirects to `/setup` (or shows a one-time card on the dashboard, TBD during impl).
- After the wizard completes, `simtelemetry.config.json` is written and the user is never re-prompted. They can revisit `/setup` any time to change settings.

### Wizard steps
Single page at `/setup`, gated by a "first-run" intro card at top when applicable:

1. **Welcome card** — one paragraph explaining what Pacefinder does ("records every Forza race automatically; serves a live dashboard"). Link to the README on GitHub for the long version.
2. **Storage location**
   - Show the current default + a free-text override (existing field). Default = the auto-detected fallback path.
   - **Storage estimate** below the path: short helper line, e.g.
     ```
     A typical race uses ~2 MB. 10 races/week ≈ 100 MB/year.
     A 4-hour endurance session ≈ 30 MB.
     ```
     These are rule-of-thumb numbers from observed data, not live-computed. Keep the copy short — a single line under the path field.
3. **Anthropic API key (optional)**
   - Existing field, marked clearly **Optional**. Wizard does NOT block on missing key. One-line copy: "Adds AI post-race coaching. Costs pennies per session. Skip and add later if you want."
4. **Game-side setup pointer**
   - Short callout: "In Forza Motorsport: Settings → HUD and Gameplay → Data Out → set IP to this machine's IP, port 5300, format Car Dash."
   - Show the listener's bound IPs (already exists at `/setup/ips`) inline so the user can copy.
5. **Save & finish**
   - "Save" button writes `simtelemetry.config.json`, marks first-run as complete, redirects to `/` (the live dashboard).

### Empty-state hooks
After save, the dashboard should still feel useful with no data yet:
- Show the bound port + a "Waiting for telemetry…" hint (the existing dashboard already does most of this — just verify it reads OK on a clean install).

### Acceptance
- Fresh clone + first `python3 listener.py` → opening `/` redirects to `/setup` with the intro card visible at the top.
- After saving a storage path, the user lands on `/` and the wizard does NOT re-trigger on subsequent loads.
- Storage estimate copy renders correctly under the path field.
- Skipping the Anthropic key works fine (no blocking, no error).
- Existing `/setup` users (config exists already) see the page exactly as it is today — no intro card.

## Scope
- "First-run" detection helper in `db/store.py` or `config.py`
- Conditional intro card in `net/pages/setup.py` + driver in `static/js/setup.js`
- Storage estimate copy (static, no compute)
- Dashboard redirect for first-run state (or pinned banner — pick during impl)
- One-time write of `simtelemetry.config.json` on Save

## Out of scope
- Forcing the Anthropic key (user explicitly said no)
- Multi-step modal carousel — single page is enough
- Per-game wizard pages (ACC/F1 are parked)
- Cloud-stored config — local file is the source of truth

## Cross-repo work
- `pacefinderapp` only

## Open questions
- Redirect vs. dashboard banner for first-run? Recommend redirect — fewer ways to miss the wizard, and `/setup` is the natural home for it. Easy to switch later.
- Should "first run" use the config file's existence as the sole signal, or also check the sessions table? Recommend both — covers the stale-config-file-but-no-data case (e.g. user nuked the DB but kept config).
- Storage estimate: rule-of-thumb numbers OK for v1? Or surface live-computed (`du -sh`)? Recommend rule-of-thumb — it's a setup-time hint, not an ongoing dashboard.
