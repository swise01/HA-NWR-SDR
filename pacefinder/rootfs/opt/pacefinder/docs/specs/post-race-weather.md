# Post-race modal — weather condition selector

## Purpose
Capture weather context for each Forza session at the natural moment (right after the race). Sessions currently lack any weather metadata, which limits both manual review and future AI Spotter context.

## Behavior
- Weather pill selector added to the post-race confirmation modal for Forza sessions
- Options: **Dry / Damp / Wet / Snow**
- Default: **Dry**
- Telemetry-derived ambient/track temperature shown read-only above the selector for context: `Track: 24°C · Air: 18°C` (formatted as a single line)
- On submit, persist as `weather_condition TEXT` on the `sessions` table
- Display as a small badge on:
  - Session list rows (sidebar)
  - Session detail header (next to the existing `real` badge)

## Scope
- Schema: `ALTER TABLE sessions ADD COLUMN weather_condition TEXT`
- Modal: pill selector UI + temperature line
- Render: badge on session row + session header

## Out of scope
- Auto-detection of weather from telemetry (Forza doesn't broadcast condition cleanly; rain accumulation could be inferred but defer)
- Editing weather after submit (covered separately by the existing Edit button if it gets a multi-field editor)
- Non-Forza games — ACC/F1 stay unchanged for now

## Cross-repo work
- `pacefinderapp`: schema, modal UI, badge rendering
- `pacefindermarketing`: none

## Open questions
- Snow is a real Forza condition? Confirm before shipping (FH5 has snow biomes, FM2023 might not).
- Migration strategy for existing rows — leave `NULL` and render no badge, or backfill `Dry` as a reasonable default? Recommend: leave NULL.
