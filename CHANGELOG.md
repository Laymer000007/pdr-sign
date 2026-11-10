# Changelog

All notable changes to PDR Sign. Versions follow [Semantic Versioning](https://semver.org/).

## [1.1.0] – 2026-11-10

Feedback from two weeks of daily use.

### Added

- **Several windows** in one app: New Window in the main menu (Ctrl+N), right-click a tab →
  Move to New Window, or drag a tab out of the tab bar. "New Window" is also in the
  launcher's right-click menu. Files from the file manager open in the window you used
  last; each window has its own Fill & Sign panel, documents, undo history and title.
- **Copy, cut, paste, duplicate** placed items (Ctrl+C / Ctrl+X / Ctrl+V / Ctrl+D, or
  right-click). Paste lands at the pointer, across pages, tabs and windows, keeping
  size, rotation, colour and opacity; images and text copied from other apps paste as a
  stamp or a text item. Select several items with Shift- or Ctrl-click, or by dragging
  a box around them on empty space while Fill & Sign is open.
- **Click to type:** a click on empty page space opens Fill & Sign and starts a text
  box right there. Dragging still selects the PDF's text.
- **Signatures, initials and stamps stay editable after Save** (move, resize, turn,
  fade, delete). Save signed copy still fixes everything into the pages.

### Changed

- With a placing tool on (check, dot, line, …), clicking an item that's already placed
  selects it instead of stacking another on top. A hint under the tools says how to
  stop (Esc, or click the tool again).

### Fixed

- Text in a signed copy sat slightly higher (about a third of the font size) than on
  screen; long 24 pt lines could be cut short. Screen, Save and signed copy now match,
  form-field values included.
- An item could get stuck selected — not movable or deletable — after switching tabs
  in the middle of a drag.
- A blue highlight stayed on a text item after selecting part of its text while typing.
- A line saved at a fractional thickness reopened at the default one.

## [1.0.0] – 2026-10-26

First release.

### Reading

- Continuous, smooth scrolling with crisp HiDPI rendering; fit width, fit page and zoom.
- Thumbnails, outline and full-text search in the sidebar; text selection and copy.
- Tabs, recent files, drag and drop, and "Open With" from the file manager (a second
  PDF opens as a new tab in the running window).
- Light and dark themes that follow the desktop, with an override in Settings.

### Fill & Sign

- Click any form field to open Fill & Sign and start typing: text, multi-line, combs,
  check boxes, radio buttons, dropdowns and lists.
- Add text, ✓, ✗, dots, lines and dates anywhere on the page; undo and redo.
- Signatures and initials: draw, type in a handwriting font, or clean up a phone photo.
  Saved signatures stay on your computer (private folder, owner-only files).
- Company stamps from a scan or photo: background removed, colours kept, real size,
  turn and fade.

### Saving and printing

- Save keeps entries editable in PDR Sign and visible in every PDF reader; it writes a
  copy, checks it by reopening, then replaces the file.
- Save signed copy writes "<name> - signed with PDR-sign.pdf" (numbered, never
  overwritten) with everything fixed into the pages.
- One print dialog: printer or Save as PDF, all / current / page ranges, copies,
  paper, orientation, Fit to page / Actual size, two-sided and colour.

### Packages

- Snap (strict), .deb (Ubuntu 22.04 and newer) and AppImage, each checked in CI on
  Ubuntu 22.04 and 24.04 with `pdr-sign --self-test`.

### Free forever

- No ads, subscriptions or paywalled features. A welcome window (once, and from the
  coffee button) explains how to support development with a donation.

[1.1.0]: https://github.com/Laymer000007/pdr-sign/releases/tag/v1.1.0
[1.0.0]: https://github.com/Laymer000007/pdr-sign/releases/tag/v1.0.0
