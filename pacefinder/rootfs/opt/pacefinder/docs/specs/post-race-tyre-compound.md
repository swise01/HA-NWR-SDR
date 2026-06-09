# Post-race modal — tyre compound selector

## Purpose
Record tyre compound used per session. Affects nothing computed — pure metadata for review and filtering ("show me all my Race-tyre laps at Spa").

## Behavior
- Tyre compound pill selector added to the post-race modal
- Options: **Street / Sport / Race / Slick / Rally / Off-Road / Drag**
- **No default** — field is optional; user can skip and submit without selecting
- On submit, persist as `tyre_compound TEXT` (nullable) on the `sessions` table
- Display as badge on session detail page (and optionally session row, if it fits)
- Does NOT affect any calculation, sector delta, lap classification, or AI Spotter input

## Scope
- Schema: `ALTER TABLE sessions ADD COLUMN tyre_compound TEXT`
- Modal: pill selector with skip-able state
- Render: badge on session detail

## Out of scope
- Tyre compound auto-detection (not in Forza UDP)
- Compound-specific lap analysis or filtering (later, once data accumulates)
- Compound editing post-submit

## Cross-repo work
- `pacefinderapp`: schema + modal + badge
- `pacefindermarketing`: none

## Open questions
- Should the order match Forza's in-game compound order, or sort by softness (street → slick)? Recommend: softness order, more intuitive.
- Should the badge appear on the session row in the sidebar, or only on the detail header? List rows are cramped; recommend detail-only unless it fits without breaking layout.
