"""Synthetic "phone photo of a signature on paper" for testing the cleanup pipeline."""

from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFilter


def signature_strokes(width: int = 900, height: int = 300) -> list[list[tuple[float, float]]]:
    """A loopy, wide, signature-like scribble (three strokes)."""
    strokes = []
    pts = []
    for i in range(400):
        t = i / 399
        x = 60 + t * (width - 160)
        y = height / 2 + math.sin(t * 9 * math.pi) * 55 * (1 - 0.4 * t) + math.cos(t * 3) * 20
        pts.append((x, y))
    strokes.append(pts)
    strokes.append([(120 + i, 70 + i * 0.4) for i in range(0, 120, 3)])  # a flourish
    strokes.append([(width - 140 + i * 0.3, height - 60 - i * 0.6) for i in range(0, 90, 3)])
    return strokes


def phone_photo(angle: float = 8.0, ink: tuple[int, int, int] = (20, 30, 90)) -> bytes:
    paper = Image.new("RGB", (900, 300), (238, 236, 230))
    draw = ImageDraw.Draw(paper)
    for stroke in signature_strokes():
        draw.line(stroke, fill=ink, width=6, joint="curve")
    paper = paper.filter(ImageFilter.GaussianBlur(1.2)).rotate(
        angle, expand=True, fillcolor=(238, 236, 230)
    )
    # Lay the sheet on a dark table with a margin, like a hand-held photo.
    photo = Image.new("RGB", (paper.width + 260, paper.height + 260), (70, 55, 45))
    photo.paste(paper, (130, 150))
    # A shadow sweeping across (darker on the left), then sensor noise.
    shade = Image.linear_gradient("L").rotate(90).resize(photo.size)
    shade = shade.point(lambda v: 150 + v * 105 // 255)
    photo = Image.composite(photo, Image.new("RGB", photo.size, (0, 0, 0)), shade)
    noise = Image.effect_noise(photo.size, 18).convert("RGB")
    photo = Image.blend(photo, noise, 0.06)
    buffer = io.BytesIO()
    photo.save(buffer, "JPEG", quality=80)
    return buffer.getvalue()
