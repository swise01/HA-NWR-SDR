# Support / FAQ page

## Purpose
First-time users (and repeat users with a forgotten port number) need an answer to common operational questions without grepping the README or rummaging through GitHub issues. Ship a single in-app page that covers the routine "where is the data / why isn't it showing up / how do I change the storage path / does AI coaching cost money" questions.

## Behavior

### Surface
- New page at `/support` (or `/help` — pick during impl, prefer `/support` for clarity).
- Linked from:
  - Dashboard footer (small unobtrusive link next to the existing footer text)
  - `/setup` page (top of page, near the intro card from the first-run wizard spec)
- Not in the top nav — keeps the main nav focused on Live / Sessions / Setup. Discoverable when needed, invisible otherwise.

### Content (FAQ format)
Single-page list of question-answer pairs. Static markdown, rendered inline. Initial seed:

1. **Pacefinder isn't seeing my game's data — what now?**
   - Check Forza is broadcasting: Settings → HUD and Gameplay → Data Out → ON, IP set to this machine's IP, port 5300, format Car Dash.
   - Check the listener's bound port: visit `/setup` to see live UDP packet count.
   - If packets are arriving but rejected, see the listener log (link to "where are the logs" entry).

2. **Where are my session files stored?**
   - Default `/mnt/usb/simtelemetry` on Pi, falls back to `./data/` if not mounted.
   - Override via the storage path field on `/setup`.
   - SQLite at `<storage_path>/simtelemetry.db`; raw UDP archives at `<storage_path>/raw/`; per-session JSON at `<storage_path>/sessions/`.

3. **How do I view the listener log?**
   - Pi (systemd): `journalctl -u pacefinder -e`
   - Mac (launchd): `~/Library/Logs/pacefinder.log`
   - Run by hand: stdout of the terminal where `python3 listener.py` is running.

4. **The track / car shows as "Unknown" — how do I fix it?**
   - Open the session in `/sessions/session?id=…` and click Edit. Set the right track from the dropdown — that mapping is remembered for future sessions in the same car/track ordinal.
   - For unmapped car ordinals, type the car name in the Car field and (optionally) set a Nickname. The ordinal is stored so the same car gets the same name on future races.

5. **Does AI coaching cost money?**
   - Yes — pennies per session. It uses your own Anthropic API key, set on `/setup`. Skip if you don't want it; nothing else breaks.

6. **How much disk does this use?**
   - Rule of thumb: a typical race ≈ 2 MB. 10 races/week ≈ 100 MB/year. A 4-hour endurance session ≈ 30 MB.

7. **How do I update Pacefinder?**
   - `cd /path/to/pacefinderapp && git pull && sudo systemctl restart pacefinder` (or the equivalent on Mac/Windows).

8. **How do I report a bug or request a feature?**
   - Open an issue at github.com/Estetika101/pacefinderapp/issues. Include `journalctl -u pacefinder -e | tail -50` for crashes, screenshots for UI bugs.

### Format
- Plain HTML list of `<details>`/`<summary>` collapsibles, or simple `<h3>` + `<p>` blocks. Pick whichever reads better; no JS interactivity needed.
- Same `tokens.css` + `base.css` styling as the rest of the app for visual consistency.
- One file: `net/pages/support.py` exporting `SUPPORT_HTML`. Routes added in `net/router.py`.

### Acceptance
- `/support` returns 200 and renders the FAQ
- Footer link on `/` (live dashboard) → `/support`
- `/setup` → small "Stuck? See Support" link near the top
- All eight questions answered with concrete commands / paths
- Updating Pacefinder section matches the actual systemd unit name (`pacefinder.service`)

## Scope
- One new page module: `net/pages/support.py`
- Two new routes: `GET /support` (the page itself) and the static-asset path is already handled
- Footer link addition on the live dashboard template (`net/pages/dashboard.py`)
- Top-of-page support link addition on `net/pages/setup.py`

## Out of scope
- Search across FAQ entries (overkill for ~10 entries)
- Markdown rendering pipeline (write the HTML directly — same pattern as other pages)
- Localization
- Auto-update notifications

## Cross-repo work
- `pacefinderapp` only (the marketing site has its own docs; this is the in-app support reference)

## Open questions
- One long page vs. categorized sections (Getting started / Data / Troubleshooting)? Recommend one long page for v1; if it grows past ~20 entries, split.
- Should the link appear in the top nav alongside Sessions / Setup once it exists? Recommend NOT — keeps the top nav uncluttered. Footer + setup-page link is enough.
- Embed a "Copy command" button on the journalctl/log entries? Nice but defer.
