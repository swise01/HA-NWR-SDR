# Information Architecture

## Purpose

Pacefinder is a deep dive into telemetry. Recording is passive — the Pi
captures whether or not the app is open, and that path is solid. So the
app is fundamentally an *analysis tool*; being live is a transient
*state*, not a place. The chrome should read like a premium analysis
tool, not a website.

This spec is the reference for any nav or page-structure change.
Screen real-estate / visual polish is designed in Figma against this
frame, validated first as the static prototype at
`/static/rail-proto.html`.

**Supersedes** the shared top-bar component (#156, `static/nav.css` +
`static/js/nav.js`): the top bar is replaced by a left rail. Everything
below about Home, the graph, breadcrumbs, and the post-race modal
carries forward unchanged.

## Behavior

**Left rail — collapsible, no website affordances.** A persistent left
rail, identical on every page (one shared component, replacing the top
bar):

```
[ ● live ]      ← state, top of rail, NOT a nav row
  Home
  Sessions · 3 to review
  Tracks · 18
  Cars · 12
  ─────
  ⚙ Settings    ← bottom
⇆ Collapse       ← top of rail
```

- **Collapsible:** expanded with labels is the default; an opt-in
  icon-only state (Collapse control at the top of the rail) for the
  power user, tooltips mandatory in icon mode. Icon-only is never the
  default.
- **Live is a state, not a nav row.** A live indicator sits at the top
  of the rail, above Home: quiet when idle (`Idle · no session`),
  prominent when hot. It is not a section you browse.
- **Live auto-takes-over on session start.** When telemetry begins, the
  live view takes over the whole surface (single-Pi: packets flowing ≈
  you're about to drive). The takeover carries one quiet, non-blocking
  `‹ back to analysis` affordance — never a confirm dialog, never a
  setting. Bold ≠ trap. Exit is the post-race modal (the seam): race
  ends → modal → back into analysis.
- **Sessions counts what's actionable**, not totals: `Sessions · N to
  review`. Tracks/Cars carry bounded counts (`Tracks · 18`). A raw
  unbounded session total is clutter, not signal.
- **Settings at the bottom** (gear). Debug / Performance / Admin nest
  under Settings — not rail rows.

**Overview / Telemetry are NOT rail children.** They are views of a
*single selected* session — meaningless until one is picked. The rail
is section-level only. Selecting a session enters it with its existing
in-content subnav (`Overview | Full telemetry`). No per-entity views in
the global rail; no flyouts.

**Home is the hub.** Career strip (lifetime KPIs + form), recent feed
(newest emphasized), and entry points to Tracks/Cars. Home keeps those
entry points even though Tracks/Cars are first-class rail items — the
duplication is accepted by choice.

**Sessions is a filter mechanism, not a list.** The H1 stays
"Sessions"; filtering narrows all → the slice you want. v1 facets:
**Car, Track, Condition, Race type**, as removable chips, URL-
addressable (`?car=…&cond=wet`) so a slice is a returnable place.
Default sort is **Recent**. **Fastest** sort unlocks *only when exactly
one Track is selected* — lap time is not comparable across circuits
(Suzuka Club ~0:55 vs Nordschleife ~15:00); within one circuit it
becomes a leaderboard.

**"Needs review"** = sessions where the user's input materially
improves the data, not a backlog of all sessions:
- unresolved track (`Track #1234` — FM2023 doesn't broadcast the name),
- unmapped car (`Unknown Car #N`),
- unknown race type,
- a race missing grid → finish,
- a skipped/deferred post-race modal.

This is the actionable Sessions badge and what makes "skip the modal,
sort later" honest — deferred is reclaimable, never lost.

**Circuit / Car / Session are a graph, not a tree.** The rail is a flat
section switcher; it does nothing for lateral moves. The in-content
breadcrumb (`Sessions › Circuit › this session`) and cross-links
(Session ↔ its Car / Circuit; Circuit → its sessions) stay. The rail
does not replace the breadcrumb.

**Mobile (<760px): bottom bar.** The rail becomes a fixed, thumb-
reachable bottom bar — judged more native than a hamburger drawer on a
phone propped against the rig. Desktop = left rail; phone = bottom bar.
Same items, same component.

**Post-race modal is lossless, deferrable triage — not a transition.**
Race ends → modal offers confirm/tag in seconds. The user can skip it
entirely and stay capture-ready; lap data is already persisted by
`close()`. Skipped/untagged sessions resurface via "needs review."

## Scope

- One shared left-rail component (live indicator · Home · Sessions ·
  Tracks · Cars · Settings), replacing `nav.css`/`nav.js` everywhere.
- Collapsible expanded ↔ icon-only (labels default; tooltips in icon
  mode); Collapse control at the top.
- Live: top-of-rail state indicator + auto-takeover on session start
  with a quiet `‹ back to analysis`.
- Sessions filter (Car/Track/Condition/Type), URL-addressable; Recent
  default; Fastest unlocked only with a single Track facet.
- `Sessions · N to review` actionable badge; the "needs review"
  predicate above.
- Mobile bottom-bar mode at <760px.
- Breadcrumb + Circuit/Car/Session cross-links unchanged.
- Post-race modal: skippable, lossless; deferred sessions resurfaced.

## Out of scope

- Game-selector level — only if a second game (ACC/F1) is unparked.
- Global search — Sessions filters cover it for one Forza driver;
  revisit only if the session list becomes genuinely unnavigable.
- AI Spotter placement — tabled.
- Post-race modal loading/empty state — its own shippable issue.
- Setup split (global vs game-specific) — premature at one game.

## Cross-repo work

- pacefinderapp: all of the above.
- pacefindermarketing: none.

## Open questions

- Mistakes/Opportunities is currently both a full page (from Session
  Overview) and a telemetry modal — to be reconciled to modal-only from
  Telemetry; not yet scoped.
- Does the live takeover animate (slide/fade) or hard-cut? Prototype
  hard-cuts; decide in Figma.
- Icon-only rail: which glyphs read unambiguously for Sessions vs
  Tracks vs Cars? To be resolved in the visual pass.
