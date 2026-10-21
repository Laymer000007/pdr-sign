# Third-party notices

PDR – Portable Document Read and Sign is distributed under AGPL-3.0-or-later. It uses or
bundles the following third-party components.

| Component | Version | Licence | Source |
|---|---|---|---|
| Qt for Python (PySide6-Essentials, shiboken6) | 6.12.0 | LGPL-3.0-only (or GPL-2.0/3.0) | https://code.qt.io/cgit/pyside/pyside-setup.git |
| Qt 6 libraries (bundled in the PySide6 wheel) | 6.12.0 | LGPL-3.0-only | https://code.qt.io/ |
| PyMuPDF | 2.0 | AGPL-3.0-or-later | https://github.com/pymupdf/PyMuPDF |
| MuPDF (bundled in PyMuPDF) | — | AGPL-3.0-or-later | https://mupdf.com/ |
| Pillow | 12.3.0 | MIT-CMU (HPND) | https://github.com/python-pillow/Pillow |
| pyHanko (v1.1, certificate signatures only) | 0.38.0 | MIT | https://github.com/MatthiasValvekens/pyHanko |
| Inter (UI font) | variable | SIL Open Font License 1.1 | https://github.com/rsms/inter |
| Caveat (typed signatures) | variable | SIL Open Font License 1.1 | https://github.com/googlefonts/caveat |
| Dancing Script (typed signatures) | variable | SIL Open Font License 1.1 | https://github.com/impallari/DancingScript |
| Lucide icons | 1.52.0 | ISC | https://lucide.dev/ |

Full licence texts for the fonts and icons are shipped next to the files in
`src/pdr_sign/resources/fonts/*-OFL.txt` and `src/pdr_sign/resources/icons/LICENSE-lucide.txt`.

## Qt / LGPL

PySide6 and the Qt libraries are used unmodified and loaded as shared libraries. You may
replace them with your own build of the same major version; the source of the exact
versions used is available from the links above.
