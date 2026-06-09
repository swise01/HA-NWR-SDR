# Data coverage backlog

> **Status:** Captured for later. Items the data layer already supports (or trivially could) that the UI doesn't yet surface. Prioritised for separate sprints; nothing in this file is in flight.

## Purpose

During the layered-IA design pass we audited what's in the SQLite DB vs what reaches the screen. A small set of the highest-leverage gaps shipped with the mocks (drivetrain + year on car detail, session-profile aggregates strip above the lap table, grid → finish display on race-type sessions). The remainder are catalogued here so they don't get lost.

## Already shipped in the mocks PR

- `drivetrain_type` (RWD/AWD/FWD) — car detail title strip *(already visible)*
- `car_manufacturer` + `car_year` — folded into the canonical name on car detail (e.g. `2019 Porsche 911 GT3 R`)
- `avg_throttle`, `avg_brake`, `avg_slip`, `peak_slip`, `slip_above_pct` — five-cell session-profile strip directly above the lap table on session detail
- `grid_pos` / `finish_pos` — right-aligned `P4 → P2` display in the session-detail page-head, with green/red `↗ N places gained` / `↘ N places lost` caption. Only renders when both values are set; for non-race sessions the right column collapses.

## Backlog — category A (stored but not yet displayed)

Items in this group need no algorithm work — the data exists, just gets read and rendered.

- **`packet_count` per session.** Connection-quality indicator. A long session with sparse packets hints at UDP drop. Suggested surface: tertiary line on session detail under the metadata strip, only shown when packet density is anomalous (e.g. < 30 packets/sec average).
- **`air_temp_c` distinct from `track_temp_c`.** Currently bundled in the Conditions pill. Driver-relevant when air and track diverge sharply (sun-baked tarmac, cold air). Suggested: show separately in the edit modal; combined in the pill stays as-is for density.
- **`closed_reason`.** Why a session ended (UDP timeout / pause / manual close / race-end). Currently internal-only. Worth surfacing only when it's *not* the normal flow — a small chip on session detail like `ended on UDP timeout` so the driver knows they didn't lose a great lap because Forza paused.
- **Race-finish chip pattern for AI Race sessions:** if `race_type == "race"` and `finish_pos == 1`, decorate the result block with a small `🏆 P1` tag. Confidence: should only show when the win is meaningful (more than 4 AI opponents, didn't pause-and-resume).

## Backlog — category B (one query / one heuristic away)

Each item below is a single derived metric or query. Self-contained PRs.

- **Conditions-tagged performance gap.** "Your damp-condition pace is 1.2 s slower than dry, at this track, in this car." Single GROUP BY across `sessions.weather_condition` + best lap per session. Lives on both circuit detail and car detail. Probably the single highest-leverage Category B item — turns the existing Conditions data from a record-keeping artefact into a comparison axis.
- **Out-lap warm-up curve.** Number of laps before "best" was set. Per-session metric. Suggested surface: small inline note in session detail's metadata strip, e.g. `settled in by L3`.
- **Consistency score (std dev of lap times, excluding out/in).** A session with a 1.5 s lap-time spread is meaningfully different from one with a 4 s spread, even at the same best time. Suggested surface: one extra cell in the session-profile strip we just added, or as a chip in the metadata strip (`σ 0.42 s`).
- **Session-level theoretical-vs-actual.** Currently the `+0.473s vs theoretical` figure is *track-level* (best ever sectors). A *session-level* version (best sectors within *this run*) tells the driver "you left X on the table on this run specifically." Catalyst's headline number; trivial to compute from `lap_samples`.
- **Cross-car comparison at same track.** Belongs on circuit detail under the existing sessions list: small callout "in Pink Pig you're 6.3 s faster here than in Cayman GT4."
- **Improvement velocity.** Linear regression on the best-lap-by-session trendline. Replaces or augments the circuit-page progress chart: `improving at 0.2 s per session at Le Mans` / `plateaued at Suzuka`.
- **Tyre-compound impact.** Soft vs Medium vs Hard at the same track in the same car. The data is in `sessions.tyre_compound`; comparison is a small grouped query.
- **Time-of-day pattern.** Group sessions by hour of `started_at`. Probably noise for most users; might be a fun stat for the kind of person who built a Pi telemetry rig in the first place.
- **Streak data.** Consecutive days driven; sessions per week; total hours behind the wheel. Lives on the home page footer, near the existing Pi-stats.

## Backlog — category C (conceptual blanks)

Bigger pieces of work; each is its own page or its own surface.

- **Personal records page.** All track + car PBs in one place, with dates and conditions.
- **Weekly / monthly digest.** Auto-generated summary: sessions driven, PBs set, biggest gains. Could ship as a page or a generated email/markdown file.
- **Fuel data surface.** Forza UDP carries fuel level + fuel-per-lap; we capture but never display. Useful for longer races, especially the deferred Events / meeting work.
- **G-force max per lap / per session.** Peak g-lat and g-lon — small badges, more interesting than essential.
- **Multi-driver context.** Not in current data but the schema would absorb it cleanly — sessions tagged with a driver id.

## Why deferred

- Each Category-A item is small but a distraction from finishing the layered-IA build.
- Each Category-B item is one good metric, and they're each easier to ship as a standalone follow-up PR than to bundle.
- Category-C items are real product decisions, not just data exposes.

## Definition of done (for the items we shipped in the mocks PR)

- Backend writes `drivetrain_type`, `car_manufacturer`, `car_year` to the `sessions` table at race-start (already in `sessions`, just need to make sure listener captures them).
- Per-lap aggregates (`avg_throttle`, `avg_brake`, `avg_slip`, `peak_slip`, `slip_above_pct`) compute to a session-level summary at session close; surfaced in the new `.profile` strip.
- `grid_pos` and `finish_pos` already write at race-start / race-end; the page-head queries both and only renders the result block when both are non-null.
- Backend `closed_reason` column already exists; expose it in the API response so the UI can decide whether to surface.
