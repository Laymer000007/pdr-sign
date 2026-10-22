# Roadmap additions

Items the owner added on top of the build spec's phase list. Check this file at the start
of each phase.

## Carried over

- **Phase 3 check on the owner's real forms:** `samples/private/` didn't exist yet when
  Phase 3 was built. Once it does, run `tools/fill_check.py samples/private/*.pdf`
  and view the copies in Firefox. Every field type must fill, and every value must
  show after save.

## Phase 5 – Save pipeline (additions) — done

- **Settings dialog** (overflow menu → Settings…): theme (System / Light / Dark, applied
  live), default zoom, default text colour, signature store location, "Open links
  without asking". Backed by `services/settings.py`; saved on change.

## Phase 6 – Packaging and release (checklist additions)

- [ ] **Make the GitHub repository public, just before the release.** It stays private
      until then. Afterwards, check that the About dialog's "Source code" link
      (`SOURCE_URL`) opens without a login, as AGPL requires.
- [ ] Under the strict snap, confirm single instance works: a second launch hands over
      its files through `$XDG_RUNTIME_DIR` (`/run/user/<uid>/snap.pdr-sign`).
