# Car class from PI (game-aware)

## Purpose

Class badges are wrong. We never compute class — we decode Forza's UDP
`car_class` integer through one hard-coded map
(`{0:D,1:C,2:B,3:A,4:S1,5:S2,6:X,7:R,8:P}`) that is a Frankenstein of
two different games: it carries Horizon's `S1/S2` *and* Motorsport's
`R/P`, has no `E`, and no single `S`. For Forza Motorsport 2023 (our
only active game) an `S` car shows as `S1` and `E` cars have no badge
at all. This is the long-standing #103 "FM/FH split".

Fix: derive the class from the car's PI using the official per-game PI
ranges, instead of trusting the ambiguous integer.

## Can we tell which game?

Yes, with one gap:

- **Game** is known from the UDP port / parser → `session.game`:
  `forza_motorsport`, `acc`, `f1`. ACC/F1 are parked.
- **Forza sub-variant** (Motorsport 2023 vs Horizon 4/5) is detected
  *per packet by length* — 311 bytes = FM2023, 331 bytes = FH4/5 — and
  logged, but **not persisted on the session**. The PI ranges differ
  between Motorsport and Horizon, so this variant must be captured and
  stored for class-from-PI to pick the right column.

## PI ranges (reference)

| Class | FM 2023 (Motorsport Series) | Horizon (until 6) |
|------|------------------------------|-------------------|
| E    | 100–300                      | —                 |
| D    | 301–400                      | 100–500           |
| C    | 401–500                      | 501–600           |
| B    | 501–600                      | 601–700           |
| A    | 601–700                      | 701–800           |
| S    | 701–800                      | —                 |
| S1   | —                            | 801–900           |
| S2   | —                            | 901–998           |
| R    | 801–900                      | —                 |
| P    | 901–998                      | —                 |
| X    | 999                          | 999               |

(Forza Motorsport 5 and Forza Horizon 6 have their own columns in the
source table; recorded here for completeness but not active — we cannot
distinguish them from FM2023/FH5 over UDP.)

## Behavior

- On `forza_motorsport`, classify from `car_pi`:
  - 311-byte stream (FM2023) → Motorsport Series ranges (includes `E`,
    `S`, `R`, `P`).
  - 331-byte stream (FH4/5) → Horizon ranges (`D…A`, `S1`, `S2`, `X`).
- If `car_pi` is absent, fall back to the raw `car_class` integer
  through the legacy map (today's behaviour) — never show a worse
  badge than now.
- The class set surfaced in the UI becomes game-correct: an FM2023 `S`
  car reads `S`, not `S1`; sub-300-PI cars read `E`.
- ACC/F1: unchanged (parked; no class logic).

## Scope

- Persist the Forza variant on the session (e.g. `game_variant`:
  `fm` | `fh`), set from the first packet's length.
- A single `pi_to_class(pi, variant)` helper, used everywhere a class
  badge renders (one shared source, not the six copies of
  `CLASS_NAMES` in static/js/*).
- Apply at the point class is displayed/stored so every badge —
  dashboard, session, car, circuit, home, telemetry — is consistent.

## Out of scope

- ACC / F1 class schemes.
- Forza Motorsport 5 / Forza Horizon 6 disambiguation (no UDP signal).
- Re-classifying historical sessions — see open questions.

## Cross-repo work

- pacefinderapp: all of the above.
- pacefindermarketing: none.

## Open questions

- Store a derived `car_class_letter` at session close, or compute from
  `car_pi` + `game_variant` at render time? (Render-time keeps one
  source of truth and auto-fixes history; write-time is cheaper per
  page load.)
- Backfill existing rows? Most have `car_pi`; render-time derivation
  fixes them for free. If we store instead, a one-shot migration is
  needed.
- When Forza's `car_class` integer and the PI bucket disagree, trust
  PI? (Recommended: PI is the authoritative number; the integer is the
  thing we know is mislabelled.)
- Confirm the FM2023 `E` band (≤300) and single-`S` band against real
  telemetry before shipping — instrument-then-fix, per
  `feedback_telemetry_diagnosis`.
