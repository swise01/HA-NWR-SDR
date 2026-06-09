# Events: stringing Practice / Qualifying / Race together

> **Status:** Draft. Deferred — too complicated and error-introducing to build alongside other work. Captured here so the design is preserved while shorter-leverage UI work continues.

## Purpose

Pacefinder currently treats every UDP-detected session as a free-standing row. The standard sim-racing pattern — Practice → Qualifying → Race against AI, all at one track in one car in one sitting — therefore scatters into three unconnected sessions, three lap tables, three AI analyses. The relationships between them are invisible.

Real-world motorsport calls the bundle a **meeting**: a single event in which a driver does Practice, sets a Qualifying time, and runs the Race. Casual sim drivers do the same, often inside an hour. This spec introduces an `event` concept that auto-groups related sessions and surfaces the meeting as a first-class object in the UI.

The capture pipeline does not change. Grouping is post-hoc, driven by a detector that runs at session-close time.

## Goals

- Auto-group P/Q/R sessions at the same track in the same car within a configurable time window.
- Give the bundle its own URL, hero view, AI coaching, and breadcrumb lineage.
- Never require the driver to declare an event in advance.
- Allow manual override (unlink, merge) when the detector gets it wrong.

## Non-goals

- Real-time grouping during a session. Detection runs at session-close.
- Multi-driver / multi-car events.
- Calendar import or pre-scheduled events.
- Treating Hot Lap / Time Trial as event-eligible (these stay solo by type).

## Naming

- **Internal model**: `event_id`, `events` table, route `/events/<eid>`.
- **UI label**: "Meeting" (warmer than "Event", matches British motorsport usage, reads well in headlines: "Saturday Le Mans meeting").
- Pick one or the other if consistency outweighs nuance; otherwise this is the only place the divergence is sanctioned.

## Behavior

### Data model

New table:

```sql
CREATE TABLE IF NOT EXISTS events (
    event_id    TEXT PRIMARY KEY,         -- "evt-2026-05-11-le-mans-2989"
    track       TEXT NOT NULL,
    car_ordinal INTEGER,
    started_at  TEXT NOT NULL,            -- earliest child session's started_at
    ended_at    TEXT,                     -- latest child's ended_at; null while open
    name        TEXT,                     -- user-editable; defaults to "<date> <track>"
    closed_at   TEXT                      -- detector closes event once Race completes
);
```

New column on `sessions`:

```sql
ALTER TABLE sessions ADD COLUMN event_id TEXT REFERENCES events(event_id);
```

Existing rows get NULL `event_id` and read as solo runs — no migration risk to historical data.

### Detector — auto-grouping rules

Runs at session-close, after `session_close()` writes the row to `sessions`. A new session **joins the most recent open event** when *all* are true:

1. **Same track** as the event.
2. **Same `car_ordinal`** as the event.
3. **Time gap** from the previous child's `ended_at` to this session's `started_at` ≤ **30 minutes** (configurable in `simtelemetry.config.json` as `event_join_window_s`).
4. **Forward-only type transition.** Valid: `P → P`, `P → Q`, `Q → Q`, `P → R`, `Q → R`. Invalid (creates a new event): `R → P`, `R → Q`, `R → R` (a second Race means a new meeting). `Hot Lap` and `Time Trial` are never event-eligible.

If no open event matches, a new event row is created with this session as its first child.

The event is **closed** (`closed_at` set) as soon as:
- A `Race` session ends and joins it, **or**
- The 30-minute join window expires without a new child, **or**
- A new session arrives that fails any of rules 1–4 and creates its own event.

### Restart handling

The capture layer treats a race restart as a new session (#119, #120). For the detector, a restart inside an event is recognized when:
- Same `event_id` candidate.
- Same session type as the previous child.
- Gap ≤ 2 minutes.

Behavior: the restart **does not** add a fourth child. It either *replaces* the prior child of the same type (if the prior child has no completed laps), or *attaches* to it as a `restart_of` sibling. Open question: how to surface multiple Race attempts in the UI — see §Open questions.

### Three UI surfaces

**1. Sessions list — anywhere it appears (home, circuit page, car page).**

Grouped rows collapse N children into one parent row with a small type-shape strip:

```
▸ May 11 · Le Mans · Pink Pig · meeting   P  Q  R   best 1:42.731   →
```

The `P  Q  R` chips show the meeting shape at a glance — only the types that are actually present render. The collapsed best is the **fastest lap across all children**, regardless of session type.

Expanded:

```
▾ May 11 · Le Mans · Pink Pig · meeting   P  Q  R   best 1:42.731   →
    14:02  Practice   8 laps     1:42.731 ★
    14:38  Qualifying 3 laps     1:42.108
    14:51  Race       12 laps    1:43.204    P4 → P2
```

The Race child's tail shows grid → finish when finish position is set. Each child row is independently clickable into session detail.

Solo sessions (NULL `event_id`) render as today — no parent row, no chevron.

**2. New route — `/events/<eid>` (meeting detail page).**

Anatomy:

- **Header strip.** Track · Car · Conditions (from the *Race* if present, otherwise latest child) · `P · Q · R` shape · result chip if Race finished.
- **Hero.** Three numbers, side by side: Practice best, Qualifying best, Race best. Below: the Quali → Race delta as the headline ("Lost 1.1s under racing conditions"). Missing children render as `—`, not as a gap.
- **"What changed" card.** Compares Quali best vs Race best on a shared delta line (same SVG as Layer 1). Shows which corners the driver progressed in and which regressed under race pressure.
- **"What stayed broken" card.** Cross-references each child's per-lap loss windows; highlights corners that were slow in all three sessions (genuinely weak spots) vs corners that were slow only under pressure.
- **Three child-session cards.** Each shows the session's best lap, lap count, and click-through to the existing session-detail page.
- **AI insight card.** A single Claude analysis scoped to the whole meeting, not per-session. Prompt template differs from session-level analysis: includes all three children's stats, weather/tyre changes between them, and asks the model to comment on *progression* rather than absolute performance.

**3. Session detail — breadcrumb above the title strip.**

When a session has a non-NULL `event_id`, render above the existing header:

```
← Saturday Le Mans meeting · P · Q · ●R
```

The dots are clickable to sibling sessions. The current session is highlighted (`●R`). The back-arrow link goes to the event page, not the circuit page — closer parent wins.

Solo sessions (no event) render no breadcrumb. Their back-arrow stays as today.

### Manual override

Two operations on the meeting detail page:

- **Unlink a child.** Removes `event_id` from a single session; the session becomes solo. If the event has only one child left, the event row is deleted (and its child also becomes solo).
- **Merge a solo session into this event.** A drag target on the event page, or a "Move to meeting…" action in the session-detail edit modal. Validates against rules 1–4 (same track, same car, gap-from-event-end ≤ window, valid type transition); rejects with a one-line explanation if invalid.

No "split this event into two" UI — unlink one child at a time is enough.

## Retroactive grouping

After the schema and detector ship, run a one-shot script against existing sessions:

```
scripts/backfill_events.py [--dry-run] [--confirm]
```

- Walks `sessions` in `started_at` order.
- Applies the detector rules without writing.
- Emits a report of proposed events with their would-be children.
- With `--confirm`, writes the `events` rows and sets `event_id` on the matched sessions.

Expectations from your current data:
- ~5–15 events detected from ~56 sessions (most are probably solo Practice).
- False positives most likely: back-to-back Practice sessions on the same track in different cars that share an ordinal somehow. Mitigated by rule 2.
- False negatives most likely: sessions where the user took longer than 30 min between Practice and Race. Mitigated by leaving the join window configurable and re-running.

## Open questions

1. **Multiple Race attempts in one meeting.** If the driver restarts mid-Race and the restart has completed laps, is that one Race or two? Spec currently says "attach as `restart_of` sibling" but the UI for surfacing two Race children is undesigned. Options:
   - Show both Race siblings, second one badged "restart"
   - Roll into a single Race row with a smaller "+1 restart" annotation
   - Only count the latest Race for the meeting hero; show restarts as drill-down detail
2. **Join window: 30 min vs 45 min.** Lunch breaks, food runs, kid interruptions all push this longer. Recommend starting at 45 min, advisedly.
3. **`P → R` skipping Quali.** Bundles correctly per the rules, but the meeting hero has three slots. Designs need to gracefully degrade: render `P · — · R` with the Q slot as a faint placeholder, or compress the hero to two numbers when only two children exist.
4. **What if track changes between children but car doesn't?** Probably an AI-race series ("Forza Tour"). Out of scope for v1 — would force the detector to allow track changes, which makes the rules a lot looser. Park for v2.
5. **What if the user runs multiple meetings at the same track in the same car on the same day?** First meeting closes at Race-end; second meeting auto-starts on the next Practice. No conflict.
6. **Event naming.** Auto-default proposed: `"<weekday> <track-short>"` — e.g. `"Saturday Le Mans"`. User can edit. Should the date appear in the auto-name, or is "weekday + track" enough given each event already has `started_at`?

## Definition of done (for the future build)

- `events` table created via the standard init schema in `db/store.py`.
- `sessions.event_id` column added; existing rows untouched.
- Detector runs in `session/manager.py` at session-close, after the existing `LapRecord.close` call.
- `/events/<eid>` route serves the meeting detail page with hero, "what changed" card, child cards, AI insight.
- Sessions list components (home, circuit, car) render grouped rows for any `event_id ≠ NULL`.
- Session detail renders the breadcrumb when its `event_id` is set.
- Manual unlink / merge actions are available on the meeting page and session-detail edit modal.
- `scripts/backfill_events.py` produces a clean dry-run on the production dataset before any retroactive write.
- A test session of `P → Q → R` against AI auto-groups into one event without driver intervention.

## What this replaces

Nothing breaks. Solo sessions continue to render as today. The grouping is purely additive — every existing screen keeps working, the new shape just appears for sessions that have an `event_id`.

The current "race_type" column on `sessions` (Practice / Qualifying / Race / AI Race / Hot Lap / Time Trial) is the input the detector uses; no schema change there.

## Why this is deferred

- Detector edge cases are many (restarts, lunch breaks, missing Quali, multiple Races, AI-race series). Each one is a UI decision.
- The retroactive backfill is destructive-ish — once events are written, undoing them is a script-and-prayer affair.
- Two new pages, two new edit operations, three changed pages. Surface area is large for one feature.
- The fixed-cost features above this in the audit (post-race headline, car detail page, lap comparison promotion) deliver more value per hour and don't touch the data model.

When this is built, it'll be its own multi-PR sprint with a backfill, not bolted onto an unrelated PR.
