# pdf.js check

`viewer.html` renders a PDF with pdf.js's viewer component and forms enabled — the same
engine and mode as Firefox's built-in PDF viewer — so filled forms can be checked
without touching a real Firefox profile. `tools/fill_check.py` copies it into
`build/verify/` next to the filled copies.

pdf.js is loaded from jsDelivr (pinned to 6.4.299); the PDFs never leave the machine.
