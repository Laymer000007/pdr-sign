# PDR – Portable Document Read and Sign

Fast PDF reader with Fill & Sign, for the Ubuntu desktop.

PDR is a calm, content-first PDF viewer: continuous scrolling, thumbnails, outline,
search, printing, and a Fill & Sign panel for filling forms, ticking boxes and placing
your signature, all without leaving the document.

> Status: early development. Viewing, search, printing, form filling, signing, stamps and saving work; packaging is next.

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

## Licence

PDR is free software, licensed under the **GNU Affero General Public License v3.0 or
later** (see [LICENSE](LICENSE)). It is built on PyMuPDF/MuPDF, which is AGPL-licensed.
Third-party components and their licences are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
