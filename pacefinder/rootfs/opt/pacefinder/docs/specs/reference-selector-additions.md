# Reference selector — add Theoretical Best, Last Lap, cross-session laps

## Purpose
The Reference dropdown on the Telemetry tab currently offers only `My Best` (best lap of the current session). The most useful comparison is often *not* "your best in this session" — it's "your fastest possible based on sector splits", "the lap you just did" (live coaching), or "your PB at this circuit ever". Add those references.

## Behavior

### New options in the Reference dropdown
1. **My Best** — current behavior, best lap of current session (unchanged, stays default)
2. **Theoretical Best** — virtual "ideal lap" composed of the fastest S1, S2, S3 sectors in the current session
3. **Last Lap** — most recent completed lap of the current session
4. **Lap from another session…** — opens a chooser to pick any lap from any prior session at the same circuit

Order in dropdown: My Best (default) → Theoretical Best → Last Lap → divider → Lap from another session…

### Theoretical Best
- Sum of fastest sector times across all laps in the session: `min(S1) + min(S2) + min(S3)`
- Display in the Reference dropdown as `Theoretical Best — 1:46.812 (∑ best sectors)` with the calculated time
- For the cumulative DELTA chart, the "reference trace" is a virtual lap: at each x-position, use the data from whichever lap holds the fastest sector containing that x
- Joins between sectors are interpolated cleanly (no visible discontinuity)
- For sector deltas in the table: each sector's reference is its own fastest occurrence (each delta will be ≤ 0 for the lap that owned that sector's best)

### Last Lap
- Most recent completed lap (excluding in-progress and out-laps if those are tagged)
- Shown as `Last Lap — 1:48.213` with the time
- Same data path as `My Best` — just a different lap selection

### Lap from another session
- Opens a modal with:
  - Circuit name (locked to current circuit)
  - List of prior sessions at the same circuit, most recent first: `2026-04-28 · 5 laps · best 1:46.901 · Mugello`
  - Expand a session row → list its laps with sector splits
  - Click a lap → use it as reference and close modal
- The selected cross-session lap is shown in the Reference dropdown as `<date> · L<n> — <time>`
- If no prior sessions exist at this circuit, show "No other sessions at this circuit yet" in the modal

### Edge cases
- **One lap in session** → hide Theoretical Best and Last Lap (both equal My Best); fall back to My Best as default
- **Sectors not yet defined** for the session (rare, but possible if a session is malformed) → hide Theoretical Best
- **Cross-session circuit mismatch** → not possible by construction (modal locks to current circuit)
- **Reference lap deleted** between selection and reload → fall back to My Best with a one-time toast: `Selected reference no longer available — using My Best`

## Scope
- Reference dropdown options + ordering
- Theoretical Best computation (backend or frontend; backend is cleaner since it's per-session data)
- Theoretical Best virtual trace for the cumulative DELTA chart
- Cross-session lap chooser modal
- Persistence of selected reference (URL param? localStorage? — see open question)

## Out of scope
- Reference laps from other users (no multi-user model exists)
- Reference based on car/weather filters (later — would benefit from #2 weather + #3 tyre once those land)
- Editable theoretical best (it's derived; can't be edited)
- Combining multiple reference laps (e.g. "show me both Theoretical Best and Last Lap" — only one reference at a time for v1)

## Cross-repo work
- `pacefinderapp` only

## Open questions
- Where to persist the selected reference: URL param (shareable, copy-link friendly) or localStorage (sticky per user)? Recommend URL param — matches the rest of the dashboard's query-string ethos and lets you share a comparison link.
- Theoretical Best virtual trace — interpolate at sector boundaries with linear blending, or hard cuts? Hard cuts are honest (the virtual lap doesn't actually exist) but visually jarring. Recommend hard cuts with a thin vertical guide at sector lines.
- Cross-session chooser modal — should it filter by car too? E.g. "compare to my best Spa lap in the same car only"? Defer to a v2; for v1, all laps at the circuit regardless of car.
- For `Last Lap` on the *live* session: should it auto-update as new laps complete? Recommend yes when on the live page; static snapshot on the historical session view.
