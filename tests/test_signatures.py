import io
import stat
import time
from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageDraw

from pdr_sign.services import sigimage, signatures, stamps
from pdr_sign.services.document import Document
from pdr_sign.services.sigimage import PhotoOptions
from pdr_sign.services.stamps import OverlayItem
from tests.sigphoto import phone_photo, signature_strokes


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def open_png(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGBA")


# --- store ------------------------------------------------------------------------


def test_store_default_folder_follows_xdg(tmp_path: Path) -> None:
    assert signatures.SignatureStore().folder == tmp_path / "data" / "pdr-sign" / "signatures"


def test_store_snap_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SNAP_USER_DATA", str(tmp_path / "snap"))
    assert signatures.default_dir() == tmp_path / "snap" / "signatures"


def test_store_add_list_remove_and_privacy(tmp_path: Path) -> None:
    store = signatures.SignatureStore(tmp_path / "sigs")
    png = png_bytes(Image.new("RGBA", (10, 10)))
    first = store.add("signature", png)
    second = store.add("signature", png)
    store.add("initials", png)
    assert [s.id for s in store.list("signature")] == [second.id, first.id]  # newest first
    assert len(store.list("initials")) == 1
    assert stat.S_IMODE(store.folder.stat().st_mode) == 0o700
    assert stat.S_IMODE(first.path.stat().st_mode) == 0o600
    assert first.png() == png
    assert store.remove("signature", first.id)
    assert not store.remove("signature", first.id)
    assert [s.id for s in store.list("signature")] == [second.id]


def test_store_keeps_five_per_kind(tmp_path: Path) -> None:
    store = signatures.SignatureStore(tmp_path)
    png = png_bytes(Image.new("RGBA", (4, 4)))
    ids = [store.add("initials", png).id for _ in range(7)]
    kept = [s.id for s in store.list("initials")]
    assert kept == list(reversed(ids))[:5]
    assert len(list(tmp_path.glob("initials-*.png"))) == 5


def test_store_rejects_non_png(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        signatures.SignatureStore(tmp_path).add("signature", b"GIF89a")


# --- image cleanup ------------------------------------------------------------------


def corners_transparent(image: Image.Image) -> bool:
    w, h = image.size
    return all(image.getpixel(p)[3] == 0 for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)))


def test_phone_photo_is_cleaned_straightened_and_recoloured() -> None:
    start = time.perf_counter()
    result = sigimage.clean_photo(phone_photo(angle=8), PhotoOptions(ink="blue"))
    assert time.perf_counter() - start < 2.0
    assert result.angle == pytest.approx(8, abs=1.5)
    image = open_png(result.png)
    assert corners_transparent(image)  # paper, shadow and table are gone
    w, h = image.size
    assert w > 2.5 * h  # trimmed to a wide signature, not the whole photo
    inked = [p for p in image.get_flattened_data() if p[3] > 200]
    assert len(inked) > 500
    assert all(p[:3] == sigimage.INK_COLORS["blue"] for p in inked)


@pytest.mark.parametrize("angle", [-10, 0, 12])
def test_auto_straighten_tracks_the_tilt(angle: float) -> None:
    result = sigimage.clean_photo(phone_photo(angle=angle))
    assert result.angle == pytest.approx(angle, abs=1.5)


def test_manual_rotation_and_straighten() -> None:
    upside = Image.open(io.BytesIO(phone_photo(angle=0))).rotate(180, expand=True)
    buffer = io.BytesIO()
    upside.save(buffer, "JPEG")
    result = sigimage.clean_photo(buffer.getvalue(), PhotoOptions(rotation=180, straighten=0))
    assert result.angle == 0
    # The flourish sits top-left in the original; after turning back it's there again.
    image = open_png(result.png)
    w, h = image.size
    top_left = image.crop((0, 0, w // 3, h // 3))
    bottom_right = image.crop((2 * w // 3, 2 * h // 3, w, h))
    assert top_left.getchannel("A").getbbox() is not None
    assert sum(top_left.getchannel("A").get_flattened_data()) > sum(
        bottom_right.getchannel("A").get_flattened_data()
    )


def test_close_up_scan_without_surround() -> None:
    paper = Image.new("RGB", (900, 300), (250, 250, 248))
    draw = ImageDraw.Draw(paper)
    for stroke in signature_strokes():
        draw.line(stroke, fill=(10, 10, 10), width=5)
    result = sigimage.clean_photo(png_bytes(paper))
    image = open_png(result.png)
    assert corners_transparent(image)
    assert image.width > 600  # the signature itself wasn't cropped away


def test_strength_trades_faint_strokes_for_cleanliness() -> None:
    paper = Image.new("RGB", (600, 200), (245, 245, 245))
    draw = ImageDraw.Draw(paper)
    draw.line([(50, 100), (550, 100)], fill=(20, 20, 20), width=6)  # firm stroke
    draw.line([(50, 150), (550, 160)], fill=(200, 200, 200), width=4)  # faint pencil
    data = png_bytes(paper)
    gentle = open_png(sigimage.clean_photo(data, PhotoOptions(strength=0.0, straighten=0)).png)
    strict = open_png(sigimage.clean_photo(data, PhotoOptions(strength=1.0, straighten=0)).png)
    assert gentle.height > strict.height  # the faint line survives only the gentle pass


def test_prepared_transparent_png_is_kept_and_trimmed() -> None:
    sig = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    ImageDraw.Draw(sig).line([(100, 100), (300, 120)], fill=(200, 0, 0, 255), width=8)
    result = sigimage.clean_upload(png_bytes(sig), PhotoOptions(ink="original"))
    image = open_png(result.png)
    assert image.width < 260 and image.height < 60
    assert max(p[0] for p in image.get_flattened_data() if p[3] > 200) > 180  # still red
    black = open_png(sigimage.clean_upload(png_bytes(sig)).png)
    assert {p[:3] for p in black.get_flattened_data() if p[3] > 200} == {(0, 0, 0)}


def test_exif_orientation_is_honoured() -> None:
    photo = Image.open(io.BytesIO(phone_photo(angle=0))).rotate(90, expand=True)
    exif = Image.Exif()
    exif[0x0112] = 8  # "rotate 90° clockwise to display"
    buffer = io.BytesIO()
    photo.save(buffer, "JPEG", exif=exif)
    image = open_png(sigimage.clean_photo(buffer.getvalue()).png)
    assert image.width > 2 * image.height


def test_trim_png() -> None:
    sig = Image.new("RGBA", (500, 500), (0, 0, 0, 0))
    ImageDraw.Draw(sig).rectangle((200, 240, 300, 260), fill=(0, 0, 0, 255))
    image = open_png(sigimage.trim_png(png_bytes(sig)))
    assert 100 <= image.width <= 112 and 20 <= image.height <= 32


# --- stamping -------------------------------------------------------------------------


def marker_png() -> bytes:
    """A 4:1 image with a blue block at its left end, to check orientation."""
    sig = Image.new("RGBA", (400, 100), (0, 0, 0, 0))
    ImageDraw.Draw(sig).rectangle((0, 0, 80, 100), fill=(0, 0, 255, 255))
    ImageDraw.Draw(sig).rectangle((81, 40, 399, 60), fill=(0, 0, 0, 255))
    return png_bytes(sig)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_signature_is_stamped_upright_where_placed(tmp_path: Path, rotation: int) -> None:
    src = pymupdf.open()
    src.new_page(width=595, height=842).set_rotation(rotation)
    src.save(tmp_path / "blank.pdf")
    doc = Document.open(tmp_path / "blank.pdf")
    item = OverlayItem("signature", 0, (100, 200, 300, 250), image=marker_png())
    stamps.write_overlays(doc, [item])
    with doc.locked() as pdf:
        pdf.save(tmp_path / "signed.pdf")
    doc.close()
    signed = pymupdf.open(tmp_path / "signed.pdf")
    page = signed[0]
    assert list(page.annots()) == []  # page content, not an annotation
    (info,) = page.get_image_info()
    bbox = pymupdf.Rect(info["bbox"]) * page.rotation_matrix
    assert (bbox.x0, bbox.y0, bbox.x1, bbox.y1) == pytest.approx((100, 200, 300, 250), abs=0.5)
    pix = page.get_pixmap(dpi=72)
    assert pix.pixel(110, 225) == (0, 0, 255)  # the blue end is on the left, as drawn
    assert pix.pixel(290, 225) != (0, 0, 255)
    assert stamps.read_overlays(Document.open(tmp_path / "signed.pdf")) == []
