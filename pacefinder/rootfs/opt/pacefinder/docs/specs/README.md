# Specs

Home for **product** specs only — features and behavior of the Pacefinder app itself. Marketing-site specs live in the `pacefinder` (marketing) repo, not here.

## What goes where

**This repo (`pacefinderapp`)**
- App code, schema, data, UI inside the app
- Specs for app behavior: features, performance, telemetry, AI inside the app, install/usage docs
- Issues: `feature` / `bug` / `enhancement` / `data` / `documentation` (in-app docs only)
- ✅ References to the marketing site are fine
- ❌ No marketing copy, hero content, growth experiments, brand assets, or marketing specs

**Marketing repo (`pacefinder`, private)**
- Site code, copy, assets, brand
- Specs for marketing content (hero, videos, growth experiments)
- Issues for marketing-only work
- ✅ Pulls feature info from this repo's specs/changelog as needed (one-way reference)

**Cross-cutting work** (a feature touches both repos)
- The spec lives in the repo where the **dominant work** happens.
- The OTHER repo opens its own slim issue referencing the cross-repo spec — no spec duplication.

## Convention

- One file per feature: `<feature-slug>.md` (e.g. `spotter-v2.md`, `acc-tire-pressure.md`)
- Write the spec first, commit it, then implement against it
- Every spec gets a matching GitHub issue with the standard 3-line body:
  ```
  **TL;DR:** <one-sentence summary>
  **Spec:** [`docs/specs/<slug>.md`](https://github.com/Estetika101/pacefinderapp/blob/main/docs/specs/<slug>.md)
  **Status:** specified · not implemented
  ```
- The spec file is the canonical doc (never closed); the issue is the work item (closeable, linkable from PRs via `Closes #N`).

## Template

```markdown
# <Feature Name>

## Purpose
One sentence: what problem this solves and for whom.

## Behavior
What the user sees and what the system does. Be specific.

## Scope
- Bullet list of what's included.

## Out of scope
- Bullet list of what's deliberately not included.

## Cross-repo work
- `pacefinderapp`: <what changes>
- `pacefinder` (marketing): <what changes, or "none">

## Open questions
- Anything not yet decided.
```

Specs are living documents until shipped. Once a feature ships, the spec is historical — leave it as-is rather than editing to match reality (the code is the source of truth post-ship).
