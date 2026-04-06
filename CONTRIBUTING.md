# Contributing to HA-NWR-SDR

First — thank you for being here.

I built this to solve a real problem at my house: I wanted my home to know when a tornado warning was issued before I heard it on TV. It works, my family is safer for it, and I decided to share it.

I am not a professional developer. I am someone who learns by doing, breaks things, fixes them, and keeps going. This project reflects that — the bones are solid, the dashboard needs work, and there are things a more experienced developer would have done differently. I know that, and I am genuinely excited to see where the community takes it.

**If you are more skilled than me — please make this better. I mean that sincerely.**

---

## Where help is most needed

- **Dashboard redesign** — the current Lovelace YAML works but it's rough. If you know Mushroom, card-mod, and layout-card well, it could be beautiful
- **Screenshots** — I haven't added any to the README. If you get this running, a screenshot PR would help everyone who comes after you
- **Testing on different hardware** — RTL-SDR V3, generic dongles, different Pi models, different antennas
- **Audio improvements** — Sonos, Google Home, TTS optimization examples
- **Non-US adaptations** — Canadian Weatheradio uses similar SAME codes; other countries may have equivalents
- **Android notification tuning** — iOS works well; Android has its own quirks with HA notifications
- **HACS packaging** — making this installable as a proper HACS repository

---

## How to contribute

1. **Bugs** — open an issue using the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md)
2. **Ideas** — open an issue and describe what you want to build and why
3. **PRs** — for anything significant, open an issue first so we can talk through the approach. For fixes and doc improvements, just go for it.

---

## Code style

- Python: PEP 8, clear comments, no magic numbers without explanation
- YAML: 2-space indent, descriptive entity names
- Keep `# ← EDIT` markers on every line a user must customize during setup
- Prefer simple and readable over clever

---

## License

By contributing you agree your work will be released under the [MIT License](LICENSE).
