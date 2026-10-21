# Decisions

Choices made where the build spec was silent or needed interpretation. Newest last.

## Phase 0

- **Toolchain: uv + standalone CPython 3.12.** The dev machine (Ubuntu 26.04) only ships
  Python 3.14, so the project venv uses uv's managed CPython 3.12. CI uses
  `actions/setup-python` as the spec says.
- **`PySide6-Essentials` instead of the `PySide6` meta-package.** Essentials contains every
  module we're allowed to use (QtCore, QtGui, QtWidgets, QtSvg, QtPrintSupport). Skipping
  `PySide6-Addons` saves ~60 MB of wheel and helps the ~150 MB bundle target.
- **Pillow 12.3.0, not 13.0.0.** 13.0 was a brand-new major release when we pinned.
- **PySide6 6.12 wheels need glibc ≥ 2.34.** Ubuntu 22.04 (2.35) is the oldest supported
  release; 20.04 is out of scope.
- **Build backend: hatchling** (build-time only, not a runtime dependency).
- **Package uses a `src/` layout** (`src/pdr_sign/`) so tests run against the installed
  package, not the working tree by accident.
- **`on_accent` token added.** White on the dark-mode accent `#818CF8` is only ~2.9:1, so
  dark mode uses `#1E1E1E` on the accent (~6:1). Light mode keeps white on `#4F46E5`.
- **Theme detection order:** user override in Settings → `gsettings get
  org.gnome.desktop.interface color-scheme` (`prefer-dark` → dark, `prefer-light`/`default`
  → light) → `QStyleHints.colorScheme()` → palette lightness. We re-check on
  `QStyleHints.colorSchemeChanged` so live switches are followed. The Qt style is forced
  to `Fusion` so our QSS and palette render the same on every desktop.
- **Settings are a JSON file** at `$XDG_CONFIG_HOME/pdr-sign/settings.json` (snap:
  `$SNAP_USER_DATA`), handled by `services/settings.py` with a dataclass. Not QSettings,
  so the services layer stays Qt-free. Includes a reserved `license_key: str | None`.
- **Qt-free `services/`** is enforced by a test (`tests/test_architecture.py`), which
  parses every module's imports, rather than by a lint rule.
- **Icons:** only the Lucide SVGs we use are vendored (from `lucide-static` 1.52.0). They
  use `stroke="currentColor"`, which `icons.py` replaces with the theme colour before
  rendering through QtSvg.
- **Fonts:** vendored as the variable TTFs from the google/fonts repository.
