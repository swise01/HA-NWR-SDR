# Searchable autocomplete widget

## Purpose
Make the standard "pick from a long list, with type-to-filter" interaction reusable across the app. Right now we have one-off `<datalist>` (track edit), ad-hoc CSS pills (race type, tyre compound), and a fully custom modal-based picker (cross-session reference). The track datalist does not behave like a dropdown — nothing opens on click, suggestions only appear as the user types — and that bites first-time users. Build the pattern once as a small vanilla-JS widget, prove it on the track field, then standardize on it for cars (next spec) and any future picker.

## Behavior

### Visual + interaction
- A text input with a small dropdown caret on the right edge.
- **Click the input or caret** → dropdown panel opens beneath, showing all options (or top N if list is huge — see below).
- **Type** in the input → the panel filters in real time, case-insensitive, sub-string match (not just prefix). Highlight the matching characters.
- **↑ / ↓** keys move the highlighted option; **Enter** selects; **Esc** closes without selecting.
- **Click an option** → selects, fills the input, closes.
- **Blur / click outside** → closes. If the user typed a value not in the list and `allowFreeText: true`, the typed value is accepted as-is. If `false`, the input reverts to the previous selection.
- The panel is positioned absolutely under the input; pageflow doesn't shift.
- Empty filter result → "No matches" row, or (configurable) "Use as new entry: <typed value>" when `allowFreeText: true`.

### Performance
- Designed to handle up to ~1000 options without virtualization (most pickers in this app are <100). Beyond that, render-on-scroll could be added later.
- Filter is a simple `.filter(o => o.toLowerCase().includes(q))` — no fuzzy matching, no debounce needed at our scale.

### API (vanilla JS, no framework)
```js
import { Autocomplete } from '/static/js/widgets/autocomplete.js';

const ac = Autocomplete.attach(inputEl, {
  options: [...],            // array of strings or {value, label, group}
  allowFreeText: true,       // default false
  emptyText: 'No matches',
  onSelect: (val) => {...},  // fires on pick
  onChange: (val) => {...},  // fires on every input change
  initialValue: 'Spa-Francorchamps',
});
ac.setOptions([...]);        // refresh options after async load
ac.destroy();                // detach event listeners
```

The widget is a single ES module file under `static/js/widgets/autocomplete.js`. Companion CSS in `static/widgets/autocomplete.css`. No external deps.

### First consumer: track field on the session-edit modal
Replace the `<datalist>` in `net/pages/sessions.py` with a plain `<input class="ac-input" id="edit-track">`, wire it via:
```js
Autocomplete.attach(document.getElementById('edit-track'), {
  options: trackList,
  allowFreeText: true,
  initialValue: currentTrack,
});
```

`allowFreeText: true` preserves today's "type a new track name" escape hatch.

### Acceptance
- Click the track field → a panel opens with all known tracks listed
- Type "spa" → list filters to matching options as I type
- Pick one → input fills, panel closes, save persists the choice
- Type a brand-new track name not in the list → save persists the typed string (free-text fallback)
- Keyboard nav works (↑ ↓ Enter Esc)
- Blur with empty input → no error, just an empty selection
- Widget is reusable: car picker (next spec) drops in with a different `options` array

## Scope
- New module `static/js/widgets/autocomplete.js` + `static/widgets/autocomplete.css`
- Replace track `<datalist>` on the session-edit modal with the widget
- One-line readme block (or inline comment) documenting the API

## Out of scope
- Multi-select pickers (none of the current consumers need it)
- Async / remote-search options (`setOptions` after fetch is enough)
- Virtualized scrolling for 10k-row pickers
- A formal "design system" docs site

## Cross-repo work
- `pacefinderapp` only

## Open questions
- Where does the widget CSS live? Recommend `static/widgets/autocomplete.css` (sibling to existing `static/sessions_*.css`). Keeps widget assets isolated under one folder so future widgets follow the same path.
- Bundle the widget into a shared `widgets.js` once we have 2-3? Defer — premature for one widget, easy to refactor later.
- Mobile touch behavior: tap-to-open same as click. iOS Safari quirks (the virtual keyboard hides the panel) — can be handled with `position: fixed` panel below the input on small screens. Verify during impl, doc as known limitation if needed.
