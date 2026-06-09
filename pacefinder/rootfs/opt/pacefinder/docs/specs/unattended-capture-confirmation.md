# Unattended-capture confirmation

## Purpose

Capture is browser-independent and works correctly: a race driven with
no browser open is recorded, closed, and finalised by the Pi (verified
2026-05-18 — a 5-lap Spa race persisted with zero clients connected;
journal + DB confirmed, data was never lost).

The problem is **confirmation, not capture**. The only signal a race
recorded is the post-race modal, and that only appears if a browser is
sitting on `/dashboard`. Race unattended → it ends in total silence →
the user reasonably concludes the data vanished. It didn't; they just
had no cue to go look at `/sessions`.

This spec closes that feedback gap. It does **not** touch the capture
path — that is not broken and must not be "fixed" speculatively
(see `feedback_telemetry_diagnosis`).

## Behaviour

A lightweight "recorded while you were away" cue, reusing existing
data — no new capture logic, no notifications.

- Track a **last-seen marker** (timestamp of the most recent session
  the user has actually viewed, or last time they opened Home/Sessions
  — persisted client-side localStorage is enough for a single-user Pi).
- On Home and/or the rail Sessions item, show a count of sessions
  recorded since that marker: e.g. `Sessions · 2 new` (distinct from,
  and stackable with, the existing `N to review` badge).
- Opening `/sessions` (or viewing those sessions) clears the "new"
  count. "Needs review" stays its own separate, persistent signal.
- This is the honest answer to "I didn't know it recorded": the proof
  is now visible without having watched live.

## Scope

- Client-side last-seen marker (localStorage) + a "N new since last
  visit" count derived from `/sessions/data` (already fetched).
- Surface on the rail Sessions item and/or Home, alongside (not
  replacing) the needs-review badge.
- Clearing logic on visit.

## Out of scope

- **Any change to capture / session lifecycle / persistence** — proven
  working; off-limits for this spec.
- Push notifications / audible race-end alert with no UI open
  (heavier; the debug-mode audible hook is a separate precedent).
- A persisted post-race summary card on Home ("last race" recap so the
  fire-once modal is reviewable later) — a good *follow-up*, its own
  spec; this spec is just the "you have un-looked-at races" cue.

## Cross-repo work

- pacefinderapp: all of the above.
- pacefindermarketing: none.

## Open questions

- Marker basis: "last time Sessions was opened" (simple, slightly
  coarse) vs. per-session "viewed" tracking (precise, more state). Lean
  to the former for v1.
- localStorage is per-browser; on a fresh browser everything reads as
  "new" once. Acceptable for a single-user tool, or seed the marker to
  newest-on-first-load? (Lean: seed on first load so it isn't noisy
  day one.)
- Rail badge composition when both signals exist: `2 new · 3 to
  review`, or prioritise one? (Decide in build.)
