# Time format preference

> **Status:** Draft. Small, low-risk; ship anytime.

## Purpose

The new landing-page mocks display session start times in 24-hour form (`14:02`, `21:55`). That format is unambiguous and aligns cleanly in tabular columns, but a fraction of users — primarily US-based — will read it as wrong-looking even when it's correct. Make it a preference.

## Behavior

Add a single setting on `/setup`:

```
Time display:  ( ) 12-hour   (•) 24-hour
```

Default: **24-hour**. Reasoning: most sim-racing telemetry conventions are international, and 24-hour tabular alignment is cleaner in dense lists.

Persisted in `simtelemetry.config.json` as:

```json
{ "time_format": "24h" }   // or "12h"
```

Pass the preference to the client either via the existing `/setup/ips` config endpoint (already returns `ports`, `uptime_s`, etc.) or inline in each page's bootstrap. Client-side, a single `fmtTime(date)` helper reads the preference and renders accordingly.

## Surfaces affected

- Session list rows: `14:02` ↔ `2:02 PM`
- Session-detail "when" line: `14:02 – 14:34` ↔ `2:02 – 2:34 PM`
- Live dashboard footer / status pills: any `HH:MM` rendering
- Breadcrumbs on compare / telemetry / future event pages
- The Pi log timestamps stay in 24-hour ISO; this is a UI-only preference.

## Non-goals

- AM/PM display in tables wider than ~6 chars (lowercase `am`/`pm` to keep tabular alignment).
- Per-page overrides. Single global toggle.
- Locale-driven date formatting (`May 11` vs `11 May`). Separate concern; park.

## Definition of done

- `time_format` field added to config + setup form
- Single `fmtTime()` helper in `static/js/` used everywhere times render
- Both formats tested with the densest layout (session-list rows on home page) at 320px width to confirm `2:02 PM` doesn't break the column

## Why deferred from the mocks PR

Pure preference plumbing, no IA implication. The mocks land with 24-hour as the default and prod inherits the same default behavior with one extra setting line.
