# Home stats — improvement-first, results gated

## Purpose

The user wants to use more Home real estate for stats (iRacing "My
Stats" as inspo). But Pacefinder is a telemetry **coaching/improvement**
tool fed by a lossy single-player Forza UDP stream — not a race-results
tracker with field/standings data. Mirroring iRacing's results card
(wins, poles, laps led, avg start) produces a wall of zeros, because
that data is exactly what Forza doesn't reliably emit (it's our
"needs review" predicate). See `feedback_competitive_pushback`.

So: expand Home, but lead with what we measure reliably and that
reflects *getting faster*; show results metrics only scoped to sessions
where we actually have valid race classification.

## Behavior

A stats block on Home (the career strip grows into a fuller section),
two tiers:

**Primary — always shown, reliable (telemetry-derived):**
- Total sessions, total laps.
- Circuits driven, cars driven (bounded counts).
- **Circuits improving vs regressing** — from per-track `trend`
  (`/sessions/tracks`): `▲ N improving · ▼ M regressing · — K flat`.
  This is the headline improvement signal and unique to our data.
- Current form sparkline (already present) — keep.

**Secondary — results, GATED + sample-scoped:**
- Avg finish, avg positions gained, podium rate.
- Shown only when there is ≥1 session with valid race classification
  AND grid/finish present. Always carry the sample in the label:
  "Avg finish P4.2 · across 14 real races". Never a bare `0%` /
  `0.0` with no races — if the sample is 0, the metric is omitted
  entirely, not shown as zero.

**Explicitly NOT shown** (Forza can't back them honestly): wins,
poles, laps led, win rate, pole rate, laps-led rate, average start.
These are iRacing-genre metrics; including them = the zero wall.

## Deferred (need new backend work, own follow-up)

- **Consistency** (lap-time stdev / "how repeatable") — arguably the
  strongest coaching metric, but needs a per-lap aggregate query we
  don't have. Spec it separately; it's the natural next stat.
- **Aggregate gap to theoretical** across circuits — needs joining
  `track_references`; defer.
- **Total distance travelled** — only honest if summed from per-lap
  distance; not reliably available. Omit until it is.

## Scope

- Extend `/sessions/career` (or `/home/data`) with: circuits_driven,
  cars_driven, trend tallies (improving/regressing/flat counts),
  real_race_count, and keep existing finish/gained/podium.
- Home renders the two-tier block; results tier hidden when
  real_race_count == 0; every results stat label states the sample.
- No new heavy per-lap queries (consistency is deferred).

## Out of scope

- iRacing-style results metrics (wins/poles/laps-led/avg-start).
- Consistency, theoretical-gap aggregate, distance — deferred above.
- Visual layout polish — Figma; this spec fixes *which* metrics and
  the gating rule, not pixels.

## Cross-repo work

- pacefinderapp: all of the above.
- pacefindermarketing: none.

## Open questions

- "Improving" counts: over what window? `/sessions/tracks` `trend`
  uses last-3 best laps — short. Good enough for a Home tally, or
  widen to a season? (Tally now; revisit with the consistency spec.)
- Live on `/sessions/career` vs `/home/data` — pick whichever already
  carries the session aggregate to avoid a second round-trip.
