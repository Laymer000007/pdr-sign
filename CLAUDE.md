# PDR – Portable Document Read and Sign

The spec is `BUILD_PROMPT.md`. Owner additions to the phases are in `docs/ROADMAP.md`
(check it at the start of every phase). Choices the spec doesn't cover are logged in
`docs/DECISIONS.md`; add a new entry whenever you make one.

The GitHub repo stays **private** until just before the Phase 6 release.

## Commands

```bash
# one-time setup (uv lives in ~/.local/bin)
uv venv --python 3.12 .venv && uv pip install --python .venv -e ".[dev]"

.venv/bin/python -m pdr_sign [file.pdf]       # run
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy                                 # strict, config in pyproject.toml
.venv/bin/pytest -m "not slow"                 # fast suite
.venv/bin/pytest                               # everything, including slow perf tests
QT_QPA_PLATFORM=offscreen .venv/bin/pytest     # headless (CI uses xvfb-run)
.venv/bin/python tools/fill_check.py some.pdf  # fill every field like Save does; copy in build/verify
```

`samples/private/` holds the owner's real forms with personal data: never commit, copy
into the repo, or publish them. Filled copies go to the git-ignored `build/verify/`.
Check them in Firefox or in `tools/pdfjs-check/viewer.html` (same engine).

## Conventions

- Work in phases (spec section 9). Each phase ends with tests, ruff and mypy all green, a
  launch check, and exactly one commit. Stop and summarise after each phase.
- Never use the competitor brand/product names listed in `BUILD_PROMPT.md` §0, or
  look-alike icons or colours, anywhere. `tests/test_architecture.py` checks for them.
- Ask before adding any dependency not in spec section 2. Pins are exact, in `pyproject.toml`.
- `src/pdr_sign/services/` must never import PySide6. `tests/test_architecture.py`
  enforces this. UI and services talk only through plain dataclasses.
- Type hints everywhere (mypy strict). Small modules, no file over ~400 lines.
- Use `import pymupdf`, never `fitz`. Every PyMuPDF call goes through
  `services.document.MUPDF_LOCK` (MuPDF isn't thread-safe; rendering runs on a worker).
- Scene/item coordinates in the canvas are PDF points in visible (rotated) orientation.
  `get_links()` already returns visible coordinates; `search_for()` does not (apply
  `page.rotation_matrix`).
- Never connect a signal that carries an int straight to `QTimer.start`; the int becomes
  the interval. Use `lambda _: timer.start()`.
- Tests must never open a real modal dialog (it hangs the run). Stub `ui.dialogs`
  functions; `faulthandler_timeout` dumps stacks if one slips through.
- Tests must never touch the real clipboard: use `ui.canvas.clipboard()` in code (the
  autouse `fake_clipboard` fixture replaces it). Trigger shortcuts with
  `tests.conftest.trigger_shortcut` – key clicks need an active window, which xcb/xvfb
  runs don't guarantee.
- Colours come only from tokens in `ui/theme.py`. The QSS is generated from them, so
  never hard-code a colour in a widget. Accent is reserved for the primary action,
  selection, focus rings and the active tool.
- Icons are Lucide SVGs in `resources/icons/`, loaded via `ui/icons.py` (recoloured at
  runtime). Every icon button needs a tooltip and an accessible name.
- `pdr_sign.OWNER` is `Laymer000007`, so the app ID is `io.github.Laymer000007.PdrSign` and
  `SOURCE_URL` is https://github.com/Laymer000007/pdr-sign. Packaging file names and
  contents must use the same app ID; no `OWNER` placeholders remain.
- Do not build licensing or payment code. `Settings.license_key` is only a reserved field.
