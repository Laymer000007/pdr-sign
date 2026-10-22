# PDR – Portable Document Read and Sign

Fast PDF reader with Fill & Sign, for the Ubuntu desktop.

PDR is a calm, content-first PDF viewer: continuous scrolling, thumbnails, outline,
search, printing, and a Fill & Sign panel for filling forms, ticking boxes and placing
your signature, all without leaving the document.

![Fill & Sign with a signature and a company stamp](docs/screenshots/fill-sign-light.png)

| Reading | Searching | Dark theme |
|---|---|---|
| ![Reading](docs/screenshots/viewer-light.png) | ![Searching](docs/screenshots/search-light.png) | ![Dark](docs/screenshots/fill-sign-dark.png) |

## Features

- **Read:** continuous scroll, crisp HiDPI rendering, thumbnails, outline, links,
  full-text search, text selection and copy, printing, tabs, recent files.
- **Fill:** type into PDF form fields of every kind; add text, ✓, ✗, dots, lines and
  dates anywhere on the page; undo and redo everything.
- **Sign:** draw a signature, type it in a handwriting font, or clean up a phone photo
  of it; the same for initials. Saved signatures stay on your computer.
- **Stamp:** upload a scan or photo of a company stamp — the background is removed and
  its colours kept; place it at its real size, turn and fade it.
- **Save:** your entries stay editable in PDR and visible in every PDF reader.
  **Save signed copy** writes a new file next to the original with everything fixed
  into the pages; the original stays unchanged for corrections.

## Install

Download from the [Releases](https://github.com/Laymer000007/pdr-sign/releases) page and
check the file against `SHA256SUMS`.

| Format | Install | Remove |
|---|---|---|
| Snap | `sudo snap install pdr-sign` (once in the Snap Store) or `sudo snap install --dangerous pdr-sign_*.snap` | `sudo snap remove pdr-sign` |
| .deb (Ubuntu 22.04+) | `sudo apt install ./pdr-sign_*_amd64.deb` | `sudo apt remove pdr-sign` |
| AppImage | `chmod +x PDR-sign-*-x86_64.AppImage` and run it | delete the file |

To check an installed copy, `pdr-sign --self-test ~/pdr-selftest` saves, signs and
prints test files into that folder and reports what worked.

## Run from source

Requires Python 3.12. With [uv](https://docs.astral.sh/uv/):

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv -e ".[dev]"
.venv/bin/python -m pdr_sign [file.pdf]
```

## Development

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest -m "not slow"
```

Packaging: `pyinstaller packaging/pdr-sign.spec`, then `packaging/appimage/build.sh` and
`packaging/deb/build.sh`; the snap builds in CI from `packaging/snap/snapcraft.yaml`
(`.github/workflows/packages.yml`). Manual release checks: [docs/TESTING.md](docs/TESTING.md).

## Licence

PDR is free software, licensed under the **GNU Affero General Public License v3.0 or
later** (see [LICENSE](LICENSE)). It is built on PyMuPDF/MuPDF, which is AGPL-licensed.
Third-party components and their licences are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
