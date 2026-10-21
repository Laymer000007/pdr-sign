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

## Phase 1

- **App identity:** `OWNER = "Laymer000007"`, so the app ID is `io.github.Laymer000007.PdrSign`.
  `SOURCE_URL` is a literal (`https://github.com/Laymer000007/pdr-sign`).
- **One render thread plus a global `MUPDF_LOCK`.** MuPDF isn't thread-safe, and
  PyMuPDF releases the GIL while rendering (measured), so a background render
  doesn't block the UI. The `QThreadPool` has one thread, and every PyMuPDF call
  takes the lock.
- **Render scheduler with replaceable "wants".** Each consumer (a page view, a thumbnail
  list) replaces its whole request list on every scroll or zoom, so stale tiles for
  pages you've scrolled past are dropped, never rendered. Visible tiles come first,
  then ±2 pages of prefetch, then thumbnails.
- **Tiles are RGB, not RGBA.** Pages are opaque, and RGB saves a quarter of the memory.
  `render_tile` returns packed RGB888. The cache budget (300 MB) counts pixmaps at
  32 bpp, which is how Qt stores them.
- **Tile size 1024 device px.** Pages at normal zoom are 1–4 tiles. 400 % on HiDPI
  stays bounded.
- **Scene units are PDF points.** The view transform is the zoom, so later overlay
  items (Fill & Sign) live directly in PDF coordinates. The gap between pages is a
  fixed 16 screen px, recomputed in points on each zoom.
- **Zoom anchoring** stores the point under the cursor as `(page, x, y)` relative to
  its page and restores it after re-layout, because scene y shifts as the gap changes.
- **Fit width uses the median page width**, so one landscape page doesn't shrink
  every portrait page. Fit modes anchor at the top and centre horizontally.
- **Ctrl+0 resets to the default zoom** from Settings (`fit-width` unless changed).
- **Coordinates:** `get_links()` returns rects and targets in visible (rotated)
  coordinates. `search_for()` returns unrotated ones and needs `page.rotation_matrix`
  (Phase 2). Both are covered by tests.
- **Single instance over a Unix socket** at `$XDG_RUNTIME_DIR/<app-id>-<uid>.sock`
  (mode 0600). QtNetwork (QLocalServer) and QtDBus aren't on the allowed module list,
  so the server is Python `socket` with a `QSocketNotifier`. The client is Qt-free
  (`services/instance.py`), so a second launch hands over its files in about 60 ms
  without loading Qt. Under strict snap confinement `$XDG_RUNTIME_DIR` is the snap's
  private `/run/user/<uid>/snap.pdr-sign`, which AppArmor allows. The server creates
  that directory if snapd hasn't, and falls back to a short file name if the path
  would exceed the 107-byte `sun_path` limit.
- **External links:** only `http`, `https` and `mailto` open, after confirmation
  unless "Open links without asking" is on. Any other scheme (`file:`, `javascript:`,
  `launch` actions) is refused.
- **Tabs show the file name** (the PDF title can repeat or be meaningless), with the
  full path as a tooltip. The window title uses the PDF title when there is one.
- **Sidebar visibility** is one app-wide preference (`Settings.show_sidebar`), toggled
  with F9 or the header button.
- **The Settings dialog is deferred** to a later phase. The settings file already
  holds theme, default zoom and the links preference.
- **CI actions bumped** to `actions/checkout@v7` and `actions/setup-python@v7`, because
  Node 20 is deprecated on runners.

## Phase 2

- **Search runs on its own one-thread pool** (separate from rendering), page by page,
  starting at the page being read and wrapping round. Results stream in, are kept in
  document order, and redraw at most every 120 ms. A new query cancels the old job.
  Results stop at 5,000 hits (shown as "5000+").
- **The first match is the first one at or after the current page**, not the first in
  the document.
- **Search highlights are amber** (`search_hit` / `search_current` tokens), not
  accent: the spec keeps the accent for selection, focus and the active tool. They're
  drawn on white pages, so both themes share them.
- **The search result list is the sidebar's third tab.** Searching switches the
  sidebar to it if the sidebar is open, but never opens a closed sidebar.
- **Text selection is word-based**, in MuPDF reading order (`get_text("words")`). It
  can span pages, is painted as one band per line, and is copied with spaces within a
  line and newlines between lines. A double-click selects a word, the context menu
  has Copy and "Select page text", and selections also fill the X11/Wayland primary
  selection (middle-click paste).
- **Click vs. drag:** a press only starts a selection after the platform drag
  distance, so clicking a link still follows it. A plain click clears the selection.
- **`Canvas` (pointer interaction) subclasses `PageView`** (layout, zoom, rendering),
  to keep both files under 400 lines.
- **`reveal()` puts a match a third of the way down the viewport**, the same line
  that decides the "current page", so the page field matches the page the match is on.
- **Printing** renders each page at 300 dpi on the UI thread with a cancellable
  progress dialog. A page whose orientation differs from the paper is turned 90°
  counter-clockwise (the CUPS convention). A "Scaling" tab in the print dialog offers
  Fit to page (default) or Actual size, centred. Page ranges come from Qt's
  `QPageRanges`, so "1-3,7" works. Copies and collation are left to the printer
  driver. The `QPrinter` is kept for the session, so the chosen printer is remembered.
