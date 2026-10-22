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

## Phase 3

- **Field values are keyed by fully qualified field name**, so a radio group's kids and
  a name printed twice stay in step. Check boxes and radios store the selected "on"
  state (`""` = off), list boxes a tuple of export values, and the rest a string.
- **PyMuPDF quirks handled in `forms.apply_values`:** any string (even `"Off"`) checks
  a box or radio, so booleans are written, and only the radio kid being selected is
  touched (MuPDF turns its siblings off). Multiple list selections are written as
  `/V` and `/I` directly. Field data is written to the object that holds it: the
  parent field when the widget is only a kid.
- **Free text in an editable combo is appended to its `/Opt` list.** pdf.js (Firefox's
  viewer) draws combos as a plain `<select>` and only shows listed values. This is
  legal PDF; the cost is that the typed value becomes a choice in that document.
- **Tab order** follows the PDF's widget order: pages in order, then `/Annots` order.
  A page's `/Tabs` entry is not interpreted.
- **Field editors:** text, combo and list fields are real Qt widgets in
  `QGraphicsProxyWidget`s; check boxes and radios are painted. They are children of
  their page item, so they scale with zoom. The fill (`field_fill` token) is opaque,
  to hide the PDF's own, possibly stale, appearance underneath. Font: Helvetica at
  the field's size, or an auto size from the box height. Comb fields edit as
  centred text; the saved appearance (by MuPDF) is a true per-cell comb. Read-only
  and signature fields get no editor.
- **Edits reach the model on `editingFinished` or focus-out.** While typing, Ctrl+Z is
  the editor's own undo; afterwards it's the document's undo stack.
- **Overlay items** are children of their page (page points). A new Text box joins
  the model only once something is typed; an empty one just disappears. Text and Date
  are one-shot tools. Checkmark, Cross and Dot stay active for ticking several boxes,
  keep a square shape when resized, and save their box height as the glyph size
  (ZapfDingbats `4`, `8`, `l`, so no font embedding is needed). Every item saves as a
  FreeText annotation tagged `/PDR 1` and `/PDRKind`. `read_overlays(remove=True)` is
  ready for Phase 5 to reopen them as editable items.
- **Fill & Sign is an app-wide mode** (Ctrl+E, the header pill, Done), like the
  sidebar. Dragging selects text only when no tool is active.
- **Initials and Signature tools are added in Phase 4.** No disabled placeholder
  buttons until then.
- **The Save UI comes in Phase 5.** In Phase 3 the save path (`apply_values` and
  `write_overlays` into a copy) was checked with `tools/fill_check.py` and pdf.js
  6.4.299 (the engine in Firefox's viewer), rendered in the app's browser pane.
  A headless run of the snap Firefox hung, so pdf.js is used directly.
- **The text-size control is a −/+ stepper.** QSpinBox's arrows don't survive the
  app stylesheet under Fusion.
- **A "• " marker** on the tab and window title shows unsaved Fill & Sign changes.

## Line tool (between Phase 3 and 4)

- **A line item's `rect` holds its two end points as drawn**, not a normalised box,
  because the end-point handles need to know which end is which.
- **Saved as a PDF Line annotation** (`/PDR 1`, `/PDRKind /line`, plus `/PDRSize`, so
  the size setting reopens exactly). Stroke width is 0.75 pt at size 8, rising
  linearly to 3 pt at size 24. Verified in pdf.js, on rotated pages, and after
  `bake()` (flatten).
- **Horizontal unless Shift is held**, both when drawing and when dragging an end
  point. A click (a drag under 3 pt) gives a 40 pt line, to the right or to the left
  when there's no room. Clicks only select a line within 8 screen px of its stroke,
  not anywhere in its bounding box.

## Phase 4

- **Photo cleanup uses Pillow only** (numpy isn't an allowed dependency). Steps: EXIF
  turn, then crop to the sheet of paper (bright row and column bands) when it lies on a
  darker surface. Paper brightness is estimated as a blurred local maximum at 1/8
  scale, so shadows and uneven light cancel out. Ink is measured as darkness relative
  to that paper, with an Otsu threshold moved by the "Cleanup" slider and a soft
  edge. Then a 3×3 median removes specks, solid border bands are cleared, and the
  image is straightened by the ink's principal axis (auto only within ±15°). Finally
  it's recoloured (black, blue or the photo's own ink) and trimmed. A 12 MP photo
  takes about 0.2–0.4 s, off the UI thread.
- **Upload tab controls:** drag a crop box on the photo, quarter turns, a straighten
  slider (shows the auto angle, Auto resets it), and cleanup strength. Uploads that
  already have real transparency are only trimmed and recoloured.
- **Draw tab is tuned for touchpads:** a lazy-brush stabiliser (5 canvas units), a
  centred moving average when a stroke ends (both ends kept), quadratic curves through
  midpoints, slight speed-based thinning, and tablet pressure when present. The canvas
  is a fixed 1000×400 logical area, scaled to the widget. It always looks like white
  paper, even in dark mode, because the ink is black or blue; the Upload preview's
  checkerboard is light for the same reason.
- **Type tab:** Caveat or Dancing Script at 160 px, then trimmed. Ink is shared with
  the Draw tab.
- **Store:** `signature-<µs>-<id>.png` / `initials-…png` in the signature folder
  (`Settings.signature_dir`, default `data_dir()/signatures`, snap-aware). The folder
  is 0700 and files 0600. Saving a sixth of a kind drops the oldest. "Remember"
  unticked keeps it in memory for this session only.
- **Initials are images**, made the same three ways as signatures; they're not text.
- **Placement:** the Signature/Initials tool uses the most recent one, or opens the
  dialog when there's none. Panel thumbnails pick a specific one; right-click deletes.
  Default width is 150 pt for a signature and 56 pt for initials, centred on the click,
  aspect kept, one-shot. Clicking in or within 12 pt of an empty signature field fits
  the image inside it (2 pt inset, centred). A move that ends near a field snaps too;
  a resize doesn't, so shrinking one inside a field sticks. Empty signature fields
  show a dashed "Sign here" box that signs straight into the field.
- **Stamping** uses `insert_image(..., keep_proportion=True, overlay=True,
  rotate=page.rotation)`, so it's upright on rotated pages (tested on all four).
  Signatures become page content: permanent, and they don't reopen as editable items.
- **PySide6 stub quirk:** `QImage.save` / `QImage.fromData` are typed as taking
  `bytes` for the format, but only `str` works at runtime. Those calls carry a
  `type: ignore` with a comment.
- **Worker threads never touch Qt** (`ui/worker.py`). Emitting a signal from a worker
  takes Qt's signal-slot mutex and the GIL; the UI thread takes the same pair in the
  opposite order when it connects signals or creates timers. Under load that
  deadlocked intermittently (the test suite hung on a real X11 display). Rendering,
  search and photo cleanup now run through `Runner`: workers put results on a
  `queue.SimpleQueue`, and the UI thread drains it on an 8 ms timer that runs only
  while jobs are outstanding. Five full xcb runs after the change: no hangs.

## UI polish (before Phase 5)

- **Header, left to right:** Open, Sidebar, Print, Fill & Sign, Save. Fill & Sign is
  now a quiet icon toggle (Lucide "signature") that turns accent while the panel is
  open; the old pill is gone. Save (Lucide "save") stays disabled until Phase 5.
  Print, Fill & Sign and Save remain visible but disabled with no document open.
- **Tool tiles** are a fixed 80×60 px, three per row, so long labels don't stretch
  them. "Checkmark" is now "Check".
- **`paper`, `paper_border` and `paper_muted` tokens** (the same in both themes) cover
  every surface that shows ink outside a page: saved signature tiles, the draw pad and
  the upload checkerboard. Black and blue ink are both ≥ 4.5:1 on paper (tested).

## Stamp tool (before Phase 5)

- **Stamps reuse the signature machinery:** the Upload pad (with stamp presets), the
  cleanup pipeline, the store and library (a third kind, up to 5), the panel strip,
  and image placement. New pieces: `StampGraphic`, `StampControls`, `StampDialog`,
  and `sigimage.bake`.
- **Cleanup presets for stamps:** ink defaults to Original (Red, Blue and Black
  recolour); no auto-straighten (round and boxy shapes have no baseline); frame
  lines kept (`keep_frames`, which skips the edge-band stripping that would delete a
  tightly cropped frame); gentler cleanup (0.4) for thin lettering.
- **Original colours:** each pixel's ink colour is recovered by unmixing it from
  the local paper colour, using a linear coverage estimate (darkness relative to
  the 98th-percentile dense ink), then white-balanced against the local paper. This
  removes the pale fringe and undoes shadows and paper tint. On the synthetic photo,
  red comes out (180, 13, 23) against a drawn (190, 25, 35).
- **Real size:** the dialog's "Actual size" (mm, default 40) is stored in the PNG
  as a `pdr:width_mm` text chunk, so a stamp places at its printed width. Images
  under 400 px wide get a "may print soft" warning.
- **Turning and fading:** the item keeps its unrotated box plus a clockwise
  `rotation` about its centre and an `opacity` (0.5–1.0). On the canvas there's a
  rotate knob above the stamp (Shift snaps to 15°), ⟲/⟳ quarter turns and an opacity
  slider in the panel (a whole slider drag is one undo step). Corner resizing works
  in the stamp's own turned frame, so the opposite corner stays fixed, and moves
  keep the turned outline on the page. The angle reads as −180…180°.
- **Saving:** PDF images only turn in quarter turns and have no opacity, so a
  turned or faded stamp is baked as placed: resampled to at least 600 dpi at its
  placed size (longest side capped at 5000 px, which is 600 dpi up to about 211 mm),
  turned, alpha scaled, then stamped into the page centred on the item. An
  unturned, fully opaque stamp is inserted unchanged at its source resolution.
  Checked in pdf.js and on all four page rotations.
- **Stamps never snap into signature fields.**
- **The Fill & Sign panel now scrolls**, with Done pinned at the bottom, because it
  holds three saved strips plus the contextual Stamp controls.

## Fill & Sign toggle fix

- **Root cause:** `FillSignPanel.setFixedWidth(280)` also pins the minimum width. Hiding
  animates the *maximum* width to 0, but the layout honours the minimum, so the panel
  stayed 280 px wide while the icon, `fill_mode` and the internal flag all said
  "closed". The panel's minimum is now 0 (the content inside carries the fixed width),
  and once collapsed the panel is hidden too. `MainWindow.set_fill_mode` is the only
  path that shows or hides it.

## Phase 5

- **Saving never touches the live document.** `services/saving.py` copies the file,
  writes the current state onto the copy (strip old PDR annotations, apply changed
  field values, write items), saves (incremental when `can_save_incrementally()`,
  otherwise a full rewrite; encryption kept with `PDF_ENCRYPT_KEEP`), **verifies by
  reopening** (page count, every changed field value, every editable item, every
  placed image; for a flattened copy, that no widgets or annotations remain and the
  text is present), and only then `os.replace`s the target, keeping
  `<name>.pdr-backup` until the replace has succeeded. If anything fails, the
  original stays as it was and a clear error says so.
- **After Save (and Save As) the tab reloads from the written file**, keeping its
  place, page and zoom. Text, marks and lines reopen as editable items;
  signatures, initials and stamps are now page content. The undo history starts
  fresh at that point.
- **Reopened items are taken off the in-memory pages before the canvas exists.**
  Otherwise the first tiles render them, and they show twice (pixels plus overlay).
  Found in the end-to-end check; there's a regression test.
- **Flattened copies are always a full rewrite with garbage collection**, so the old
  form data and annotations are really gone, not hidden in an earlier revision. A
  flattened copy can't overwrite the open document, and the open document keeps its
  unsaved changes.
- **List boxes get our own appearance stream** (every option, the selected ones on
  a light band, scrolled to the first selected one), because MuPDF draws them
  empty, so flattening lost the choice.
- **Save:** the header button and Ctrl+S are enabled only with unsaved changes.
  A read-only file or folder falls back to Save As ("This file can't be changed
  here. Save a copy:"). A document with a digital signature first asks:
  Save As… (default) / Cancel / Save anyway. Ctrl+Shift+S is Save As. The overflow
  menu has Save As…, Save flattened copy… and Settings…, and the panel has
  Flatten… next to Done.
- **Closing a tab or the window with unsaved changes** asks Save / Discard / Cancel.
  Cancel keeps the window open.
- **XFA forms** show a dismissible banner; reading, signing and printing still work.
- **The Settings dialog** (roadmap) applies and saves every change immediately: theme
  (live), default zoom (next open), default ink (live in open documents), the
  signature and stamp folder (the library switches to it), and "Open web and email
  links without asking".
- **Saving runs on the UI thread behind a wait cursor.** It's a few hundred ms for
  normal forms. Moving it onto a worker is possible later; the live document is
  never touched, so it would be safe.
- `main_window.py` stays under 400 lines by moving settings, links, printing and the
  tab close button into `ui/window_actions.py`, and the save logic into
  `ui/save_flow.py`.

## Placing tools win over form fields

- **Root cause:** on a left press the canvas first asked "is there an interactive item
  here?" (a field editor, the "Sign here" box, an existing item) and handed the click
  to it before the active tool was considered. With a signature armed, clicking a
  field focused it (text cursor); clicking a real signature field's "Sign here" box
  ran its own "sign with the latest" flow instead of placing the armed one.
- **Now:** while any placing tool is active, a left click places the item first.
  The cursor stays a crosshair over fields, and a quick second click with a sticky
  tool places again (Qt sends the second press as a double-click). With no tool
  active, fields behave as before.
- **Signature-line text fields:** many forms use a plain text field for the
  signature line. Signatures and initials also fit into text fields whose name or
  label says signature (signature/signed, Handtekening, Unterschrift, Firma,
  Assinatura), but not "… date" fields. Initials also fit "Initials"/"Paraaf" fields.
  Real signature fields take precedence.
