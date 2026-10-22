"""Signature images: turn drawings, scans and phone photos into clean transparent PNGs.

Pillow only (no numpy), Qt-free. The photo pipeline:

1. honour EXIF orientation, shrink to a working size, and crop to the sheet of paper
   when it lies on a darker surface;
2. estimate the paper (a blurred local maximum at low resolution), so shadows and
   uneven light drop out, then measure ink as darkness *relative to the paper*;
3. stretch contrast, pick a threshold (Otsu) and build a soft alpha mask;
4. drop specks and solid dark borders (table edges, the photo's frame);
5. straighten by the ink's principal axis (signatures are wide), within ±15°;
6. recolour to the chosen ink and trim to the ink with a small margin.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageChops, ImageFilter, ImageMath, ImageOps
from PIL.PngImagePlugin import PngInfo

WORK_SIZE = 1600  # longest side while processing
OUTPUT_MAX_WIDTH = 1200
MAX_AUTO_ANGLE = 15.0
INK_COLORS = {"black": (0, 0, 0), "blue": (29, 78, 216), "red": (200, 30, 30)}
BAKE_DPI = 600  # rotated/faded stamps are re-rendered at least this sharp...
BAKE_MAX_PX = 5000  # ...but never larger than this on their longest side
LOW_RES_PX = 400  # narrower than this prints soft at stamp sizes
WIDTH_KEY = "pdr:width_mm"  # PNG text chunk holding a stamp's real width


@dataclass(frozen=True)
class PhotoOptions:
    ink: str = "black"  # "black", "blue" or "original" (keep the photo's ink colour)
    strength: float = 0.5  # 0 = keep faint strokes, 1 = aggressive cleanup
    rotation: int = 0  # extra quarter turns, clockwise: 0, 90, 180, 270
    straighten: float | None = None  # degrees; None = automatic
    crop: tuple[float, float, float, float] | None = None  # fractions of the source
    # Stamps: round and boxy shapes have no baseline to straighten by, and a stamp's
    # own frame lines must not be mistaken for a table edge.
    auto_straighten: bool = True
    keep_frames: bool = False


@dataclass(frozen=True)
class CleanResult:
    png: bytes
    angle: float  # the straightening applied, degrees
    size: tuple[int, int]


# --- small helpers -------------------------------------------------------------------


def load(data: bytes) -> Image.Image:
    opened = Image.open(io.BytesIO(data))
    image: Image.Image = ImageOps.exif_transpose(opened) or opened
    image.load()
    return image


def to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def levels(gray: Image.Image) -> list[int]:
    """The pixel values of a single-band image, as ints."""
    return [int(v) for v in gray.get_flattened_data()]  # type: ignore[arg-type]


def has_real_transparency(image: Image.Image) -> bool:
    """True when the image already has a meaningful alpha channel (a prepared PNG)."""
    if image.mode not in ("RGBA", "LA", "PA") and "transparency" not in image.info:
        return False
    alpha = image.convert("RGBA").getchannel("A")
    low = alpha.getextrema()[0]
    return isinstance(low, int | float) and low < 128


def otsu(histogram: list[int]) -> int:
    total = sum(histogram)
    if total == 0:
        return 128
    weighted = sum(i * h for i, h in enumerate(histogram))
    best, best_var, w0, sum0 = 0, -1.0, 0, 0.0
    for t, h in enumerate(histogram):
        w0 += h
        if w0 == 0 or w0 == total:
            continue
        sum0 += t * h
        m0, m1 = sum0 / w0, (weighted - sum0) / (total - w0)
        var = w0 * (total - w0) * (m0 - m1) ** 2
        if var > best_var:
            best, best_var = t, var
    return best


def trim(image: Image.Image, margin: float = 0.04, min_alpha: int = 24) -> Image.Image:
    """Crop an RGBA image to its visible ink plus a small margin."""
    alpha = image.getchannel("A").point(lambda a: 255 if a >= min_alpha else 0)
    box = alpha.getbbox()
    if box is None:
        return image
    x0, y0, x1, y1 = box
    pad = round(max(x1 - x0, y1 - y0) * margin)
    return image.crop(
        (
            max(0, x0 - pad),
            max(0, y0 - pad),
            min(image.width, x1 + pad),
            min(image.height, y1 + pad),
        )
    )


def fit_width(image: Image.Image, max_width: int = OUTPUT_MAX_WIDTH) -> Image.Image:
    if image.width <= max_width:
        return image
    height = round(image.height * max_width / image.width)
    return image.resize((max_width, height), Image.Resampling.LANCZOS)


# --- the photo pipeline ------------------------------------------------------------------


def _paper(gray: Image.Image) -> Image.Image:
    """Estimate the paper brightness everywhere: local maximum, blurred, at low res."""
    small = gray.resize((max(8, gray.width // 8), max(8, gray.height // 8)), Image.Resampling.BOX)
    small = small.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(4))
    return small.resize(gray.size, Image.Resampling.BILINEAR)


def paper_box(gray: Image.Image, inset: float = 0.02) -> tuple[int, int, int, int]:
    """The sheet of paper in a photo: the band of rows and columns that are mostly bright.

    When the paper fills the frame this is the whole image.
    """
    small = gray.copy()
    small.thumbnail((300, 300))
    cut = otsu(small.histogram())
    bright = small.point(lambda v: 255 if v > cut else 0)
    rows = levels(bright.resize((1, bright.height), Image.Resampling.BOX))
    cols = levels(bright.resize((bright.width, 1), Image.Resampling.BOX))

    def band(profile: list[int]) -> tuple[int, int]:
        inside = [i for i, v in enumerate(profile) if v > 255 * 0.5]
        return (inside[0], inside[-1] + 1) if inside else (0, len(profile))

    top, bottom = band(rows)
    left, right = band(cols)
    sx, sy = gray.width / small.width, gray.height / small.height
    x0, x1, y0, y1 = left * sx, right * sx, top * sy, bottom * sy
    # Only crop when there's a real surround; then step inside the paper's edge.
    if (x1 - x0) * (y1 - y0) > 0.92 * gray.width * gray.height:
        return 0, 0, gray.width, gray.height
    dx, dy = (x1 - x0) * inset, (y1 - y0) * inset
    return round(x0 + dx), round(y0 + dy), round(x1 - dx), round(y1 - dy)


def ink_mask(gray: Image.Image, strength: float = 0.5) -> Image.Image:
    """Soft mask (L): 255 = ink, 0 = paper."""
    darkness = ImageChops.subtract(_paper(gray), gray)  # ink is darker than its paper
    darkness = ImageOps.autocontrast(darkness, cutoff=(0, 0.5))
    threshold = otsu(darkness.histogram())
    # Strength moves the cut: weaker keeps faint strokes, stronger drops grain and grey.
    cut = max(8, min(240, round(threshold * (0.55 + 0.9 * strength))))
    soft = max(6, cut // 3)
    lo, hi = cut - soft, cut + soft
    mask = darkness.point(
        lambda v: 0 if v <= lo else 255 if v >= hi else (v - lo) * 255 // (hi - lo)
    )
    return mask.filter(ImageFilter.MedianFilter(3))  # specks


def strip_borders(mask: Image.Image, solid: float = 0.45) -> Image.Image:
    """Clear rows/columns at the edges that are mostly ink (a table, the photo frame)."""
    w, h = mask.size
    rows = levels(mask.resize((1, h), Image.Resampling.BOX))
    cols = levels(mask.resize((w, 1), Image.Resampling.BOX))

    def inner(profile: list[int]) -> tuple[int, int]:
        limit = 255 * solid
        start, end = 0, len(profile)
        while start < end and profile[start] > limit:
            start += 1
        while end > start and profile[end - 1] > limit:
            end -= 1
        return start, end

    top, bottom = inner(rows)
    left, right = inner(cols)
    if (top, bottom, left, right) == (0, h, 0, w):
        return mask
    margin = max(2, round(min(w, h) * 0.01))  # also drop the soft edge of the border
    cleaned = Image.new("L", mask.size, 0)
    box = (
        left + margin if left else 0,
        top + margin if top else 0,
        right - margin if right < w else w,
        bottom - margin if bottom < h else h,
    )
    if box[2] > box[0] and box[3] > box[1]:
        cleaned.paste(mask.crop(box), box[:2])
    return cleaned


def principal_angle(mask: Image.Image) -> float:
    """The ink's long-axis angle in degrees (positive = rising to the right)."""
    small = mask.copy()
    small.thumbnail((400, 400))
    w = small.width
    n = sx = sy = sxx = syy = sxy = 0.0
    for i, v in enumerate(levels(small)):
        if v < 128:
            continue
        x, y = i % w, i // w
        n += 1
        sx += x
        sy += y
        sxx += x * x
        syy += y * y
        sxy += x * y
    if n < 20:
        return 0.0
    mx, my = sx / n, sy / n
    mu20, mu02, mu11 = sxx / n - mx * mx, syy / n - my * my, sxy / n - mx * my
    if mu20 <= mu02:  # taller than wide: no reliable baseline
        return 0.0
    # Image y grows downwards, so a negative slope in pixels is a rising line.
    return -math.degrees(0.5 * math.atan2(2 * mu11, mu20 - mu02))


def decontaminate(image: Image.Image) -> Image.Image:
    """Recover the ink's own colour at every pixel, for "original colours".

    A pixel is ink and paper mixed by the ink's coverage a: c = a*ink + (1-a)*paper.
    Coverage comes from darkness relative to the local paper, scaled so dense ink
    (the 98th percentile) counts as fully covered. Solving for ink removes the pale
    fringe soft edges would otherwise carry, and dividing by the local paper colour
    undoes shadows and the paper's tint.
    """
    gray = image.convert("L")
    darkness = ImageChops.subtract(_paper(gray), gray)
    hist = darkness.histogram()
    total, seen, dense = sum(hist[8:]), 0, 255
    for value in range(255, 7, -1):  # 98th percentile of the inked pixels
        seen += hist[value]
        if seen >= total * 0.02:
            dense = max(value, 16)
            break
    coverage = darkness.convert("F")
    bands = []
    for band in image.split():
        paper = _paper(band).convert("F")

        def unmix(e: dict[str, Any], dense: float = dense) -> Any:
            a = e["min"](e["d"] / dense, 1)
            ink = e["max"]((e["c"] - e["p"] * (1 - a)) / e["max"](a, 0.08), 0)
            return e["min"](ink * 255 / e["max"](e["p"], 1), 255)

        result = ImageMath.lambda_eval(unmix, c=band.convert("F"), p=paper, d=coverage)
        bands.append(result.convert("L"))
    return Image.merge("RGB", bands)


def clean_photo(data: bytes, options: PhotoOptions | None = None) -> CleanResult:
    """A photo or scan of a signature on paper → transparent, trimmed, recoloured PNG."""
    options = options or PhotoOptions()
    image = load(data).convert("RGB")
    if options.rotation:
        image = image.rotate(-options.rotation, expand=True)
    if options.crop is not None:
        fx0, fy0, fx1, fy1 = options.crop
        image = image.crop(
            (
                round(fx0 * image.width),
                round(fy0 * image.height),
                round(fx1 * image.width),
                round(fy1 * image.height),
            )
        )
    image.thumbnail((WORK_SIZE, WORK_SIZE), Image.Resampling.LANCZOS)
    if options.crop is None:  # a manual crop already says where the signature is
        image = image.crop(paper_box(image.convert("L")))

    mask = ink_mask(image.convert("L"), options.strength)
    if not options.keep_frames:
        mask = strip_borders(mask)
    if options.straighten is not None:
        angle = options.straighten
    elif options.auto_straighten:
        angle = principal_angle(mask)
        if abs(angle) > MAX_AUTO_ANGLE:
            angle = 0.0  # probably not a baseline; let the user turn it by hand
    else:
        angle = 0.0
    if options.ink == "original":
        image = decontaminate(image)
    if abs(angle) >= 0.3:
        mask = mask.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=0)
        image = image.rotate(
            -angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(255, 255, 255)
        )

    if options.ink == "original":
        result = image.convert("RGBA")
    else:
        result = Image.new("RGBA", mask.size, (*INK_COLORS.get(options.ink, (0, 0, 0)), 0))
    result.putalpha(mask)
    result = fit_width(trim(result))
    return CleanResult(to_png(result), round(angle, 2), result.size)


def clean_upload(data: bytes, options: PhotoOptions | None = None) -> CleanResult:
    """An uploaded file: prepared transparent PNGs are only trimmed (and recoloured on
    request); everything else goes through the photo pipeline."""
    options = options or PhotoOptions()
    image = load(data)
    if has_real_transparency(image) and options.crop is None and options.straighten is None:
        rgba = image.convert("RGBA")
        if options.rotation:
            rgba = rgba.rotate(-options.rotation, expand=True)
        if options.ink in INK_COLORS:
            solid = Image.new("RGBA", rgba.size, INK_COLORS[options.ink] + (0,))
            solid.putalpha(rgba.getchannel("A"))
            rgba = solid
        result = fit_width(trim(rgba))
        return CleanResult(to_png(result), 0.0, result.size)
    return clean_photo(data, options)


def with_width_mm(png: bytes, width_mm: float) -> bytes:
    """Store a stamp's real printed width inside its PNG (a text chunk)."""
    info = PngInfo()
    info.add_text(WIDTH_KEY, f"{width_mm:g}")
    buffer = io.BytesIO()
    load(png).save(buffer, "PNG", pnginfo=info, optimize=True)
    return buffer.getvalue()


def width_mm(png: bytes) -> float | None:
    try:
        value = Image.open(io.BytesIO(png)).info.get(WIDTH_KEY)
        return float(value) if value else None
    except (OSError, ValueError):
        return None


def is_low_res(png: bytes) -> bool:
    return load(png).width < LOW_RES_PX


def rotated_size(width: float, height: float, degrees: float) -> tuple[float, float]:
    """Bounding box of a width x height box turned by ``degrees``."""
    rad = math.radians(degrees)
    c, s = abs(math.cos(rad)), abs(math.sin(rad))
    return width * c + height * s, width * s + height * c


def bake(
    png: bytes,
    width_pt: float,
    height_pt: float,
    rotation: float = 0.0,
    opacity: float = 1.0,
    dpi: int = BAKE_DPI,
    max_px: int = BAKE_MAX_PX,
) -> tuple[bytes, tuple[float, float]]:
    """Render a stamp as placed: at ``dpi`` for its size on the page, turned clockwise
    by ``rotation`` degrees and faded to ``opacity``. Returns the PNG and its bounding
    box in points (turning grows the box)."""
    image = load(png).convert("RGBA")
    box_w, box_h = rotated_size(width_pt, height_pt, rotation)
    scale = dpi / 72
    longest = max(box_w, box_h) * scale
    if longest > max_px:  # very large stamps: cap the pixels, not the size
        scale *= max_px / longest
    size = (max(1, round(width_pt * scale)), max(1, round(height_pt * scale)))
    image = image.resize(size, Image.Resampling.LANCZOS)
    if rotation % 360:
        image = image.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=True)
    if opacity < 1:
        alpha = image.getchannel("A").point(lambda a: round(a * max(0.0, opacity)))
        image.putalpha(alpha)
    return to_png(image), (box_w, box_h)


def trim_png(data: bytes) -> bytes:
    """Trim a transparent PNG (drawn or typed signatures) to its ink."""
    return to_png(fit_width(trim(load(data).convert("RGBA"))))
