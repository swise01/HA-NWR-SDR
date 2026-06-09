# Shared session-metadata-editor component

## Purpose
Two surfaces today edit the same session-metadata fields with separate UIs that drift out of sync as fields are added: the post-race confirmation modal on the live dashboard (`#fo`) and the session-detail edit modal (`#edit-ovl`). This bundle (PR #98) adds Weather + Tyres to the post-race modal to bring parity, but the underlying duplication remains. Extract one reusable component so future field changes only need to be made once.

## Behavior

### Fields covered
- Track (autocomplete from FORZA_TRACKS + learned ordinals + free text)
- Car (autocomplete from FORZA_CARS + free text + nickname)
- Race type (Practice / Qualifying / Race / AI Race / Hot Lap / Time Trial)
- Weather (Dry / Damp / Wet / Snow)
- Tyres (Soft / Medium / Hard / Wet — per-game once FH5 returns)
- Conditions (read-only telemetry temps)
- Drop last lap (post-race only — tightens the moment of "I crashed on the cool-down")

### Why not just inline-share helpers
Today both modals share `.type-chip` CSS but have independent HTML, independent state vars (`_editTrack` / `_foRaceType`), and independent handlers (`editSelType` / `selType`). PR #98 had to refactor the post-race chip-handler from a global-clear to scoped-clear so picking Type didn't wipe the new Weather chips — exactly the kind of bug the duplication invites.

### Proposed shape
- New `static/js/widgets/session-meta-editor.js` exporting one factory:
  ```js
  const editor = SessionMetaEditor.attach(rootEl, {
    fields: ['track', 'car', 'type', 'weather', 'tyres', 'nickname', 'dropLastLap'],
    initialValues: {...},
    trackOptions: [...],
    carOptions: [...],
    showLapList: true,         // post-race shows lap rows; session-detail does not
    onSave: (values) => {...}, // values = { track, car, race_type, ... }
    onCancel: () => {...},
  });
  ```
- New `static/widgets/session-meta-editor.css` (extracted from sessions_session.css + dashboard.css)
- Both call sites:
  - `dashboard.js openFinish()` constructs an editor, fetches `confirm-data`, populates initial values, sets `onSave` to POST `/sessions/update`
  - `sessions_session.js openEdit()` does the same with the session-detail context

### Per-game tyre/weather sets
Pass an optional `gameProfile` arg with the active game id; the component reads its local table of allowed values per game. FM uses Soft/Medium/Hard/Wet, FH5 uses the broader Street/Sport/Race/Slick/Rally/Off-Road/Drag set, ACC its own. Avoids hardcoding.

### Acceptance
- A field added to the component (e.g. car class override, fuel start) appears on both surfaces with one diff
- Type-chip clear is scoped per-row, no cross-clearing bug possible by construction
- Existing surfaces' regressions tested with a quick before/after of: open → make changes → save → reopen pre-selects from the saved values
- ARIA hooks on the chip groups so screen readers don't regress (`role="radiogroup"`, `aria-checked`)

## Scope
- New widget module + CSS
- Refactor `static/js/dashboard.js` post-race code path to use it
- Refactor `static/js/sessions_session.js` edit-modal code path to use it
- Delete the now-redundant `selType` / `selWeather` / `selTyre` / `editSelType` / etc. handlers
- One end-to-end smoke test on each surface

## Out of scope
- Backend changes (the existing `/sessions/update` endpoint already accepts every field this component will produce)
- Adding new fields — those are separate features
- Mobile-specific layout — desktop-first, mobile follows via existing CSS breakpoints
- A formal design-system docs site

## Cross-repo work
- `pacefinderapp` only

## Open questions
- Track + car autocomplete: do both surfaces use the same `/sessions/track-options` and inlined `CAR_CATALOG` data sources? Yes today; component takes them as args, same source on both surfaces.
- Lap list rendering: post-race shows it, session-detail does not. Component takes a `showLapList: boolean` prop; lap-row markup lives in the host page until/unless we extract a separate lap-list widget.
- Should the autocomplete widget (#82) be a dependency? Yes — track + car fields use it. The component composes existing widgets rather than reimplementing.
