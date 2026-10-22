"""A neutral sample document for store screenshots (dev tool)."""

from __future__ import annotations

from pathlib import Path

import pymupdf

INK = (0.13, 0.13, 0.16)
ACCENT = (0.0, 0.0, 205 / 255)  # the icon blue
CLAUSES = [
    (
        "1. Premises",
        "The landlord lets to the tenant the residential unit described in the "
        "schedule, together with the right to use the shared garden and one parking bay.",
    ),
    (
        "2. Term",
        "The lease starts on the commencement date and runs for twelve months. It "
        "continues month to month afterwards until either party gives written notice.",
    ),
    (
        "3. Rent and deposit",
        "Rent is payable monthly in advance on the first day of each "
        "month. The deposit is held in an interest-bearing account and repaid, with interest, "
        "within fourteen days after the tenant moves out.",
    ),
    (
        "4. Maintenance",
        "The tenant keeps the premises clean and in good order. The landlord "
        "repairs structural defects, roofing, plumbing and electrical faults within a "
        "reasonable time after being told about them.",
    ),
    (
        "5. Inspection",
        "Both parties inspect the premises together at the start and at the "
        "end of the lease and record any defects on the inspection list.",
    ),
]


def field(page: pymupdf.Page, kind: int, name: str, rect: tuple[float, ...], label: str) -> None:
    page.insert_text((rect[0], rect[1] - 4), label, fontsize=8, color=(0.42, 0.42, 0.45))
    w = pymupdf.Widget()
    w.field_type, w.field_name, w.rect = kind, name, pymupdf.Rect(rect)  # type: ignore[misc]
    w.field_label = label
    if kind == pymupdf.PDF_WIDGET_TYPE_TEXT:  # type: ignore[attr-defined]
        w.text_fontsize = 10
    page.add_widget(w)


def make(path: Path, pages: int = 6) -> Path:
    doc = pymupdf.open()
    T = pymupdf  # noqa: N806
    for n in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((60, 70), "Residential Lease Agreement", fontsize=20, color=INK)
        page.draw_rect(pymupdf.Rect(60, 82, 535, 84), color=None, fill=ACCENT)
        y = 110.0
        if n == 0:
            field(page, T.PDF_WIDGET_TYPE_TEXT, "landlord", (60, y + 12, 290, y + 30), "Landlord")
            field(page, T.PDF_WIDGET_TYPE_TEXT, "tenant", (305, y + 12, 535, y + 30), "Tenant")
            field(
                page,
                T.PDF_WIDGET_TYPE_TEXT,
                "address",
                (60, y + 52, 535, y + 70),
                "Address of the premises",
            )
            field(page, T.PDF_WIDGET_TYPE_TEXT, "rent", (60, y + 92, 200, y + 110), "Monthly rent")
            field(
                page,
                T.PDF_WIDGET_TYPE_TEXT,
                "start",
                (215, y + 92, 355, y + 110),
                "Commencement date",
            )
            field(
                page,
                T.PDF_WIDGET_TYPE_CHECKBOX,
                "pets",
                (370, y + 94, 384, y + 108),
                "Pets allowed",
            )
            y += 140
        for title, text in CLAUSES:
            page.insert_text((60, y), title, fontsize=11, color=INK)
            rect = pymupdf.Rect(60, y + 6, 535, y + 70)
            page.insert_textbox(rect, text + " " + text, fontsize=9.5, color=INK, lineheight=1.35)
            y += 82
        if n == 0:
            field(page, T.PDF_WIDGET_TYPE_TEXT, "place", (60, 742, 230, 760), "Signed at")
            # A signature line drawn as a text field, as many real forms do.
            field(
                page,
                T.PDF_WIDGET_TYPE_TEXT,
                "tenant_signature",
                (300, 742, 535, 792),
                "Tenant signature",
            )
        page.insert_text((280, 820), f"Page {n + 1} of {pages}", fontsize=8, color=(0.5, 0.5, 0.5))
    doc.set_toc(
        [
            [1, "Residential Lease Agreement", 1],
            [2, "Premises and term", 1],
            [2, "Rent and deposit", 2],
            [2, "Maintenance", 3],
            [2, "Inspection", 4],
        ]
    )
    doc.set_metadata({"title": "Residential Lease Agreement"})
    doc.save(path)
    return path
