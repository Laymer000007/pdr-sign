"""Upload tab: a photo or image of a signature → clean transparent signature.

Tuned for a phone photo of a signature on paper: the photo (left) can be cropped by
dragging a box over it; the result (right) is shown on a checkerboard so you can see
the background really is gone. Ink colour, quarter turns, straightening (auto or by
hand) and cleanup strength are adjustable; work happens off the UI thread.
"""

from __future__ import annotations

from dataclasses import replace
from functools import partial
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QImage,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pdr_sign.services import sigimage
from pdr_sign.services.sigimage import CleanResult, PhotoOptions
from pdr_sign.ui import icons
from pdr_sign.ui.image_views import CropView, ResultView
from pdr_sign.ui.theme import SPACING, Tokens
from pdr_sign.ui.worker import Runner

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"
DEBOUNCE_MS = 150
SIGNATURE_INKS = (("black", "Black"), ("blue", "Blue"), ("original", "Original"))
STAMP_INKS = (("original", "Original"), ("red", "Red"), ("blue", "Blue"), ("black", "Black"))
SIGNATURE_HINT = (
    "A phone photo of your signature on white paper works well. "
    "PNG or JPG; you can also drop a file here."
)
STAMP_HINT = (
    "A scan or phone photo of the stamp on white paper, or a transparent PNG. "
    "You can also drop a file here."
)
# Stamps: keep the frame lines, don't auto-straighten round or boxy shapes, keep
# their colours, and clean a little more gently (thin lettering).
STAMP_OPTIONS = PhotoOptions(ink="original", auto_straighten=False, keep_frames=True, strength=0.4)


class UploadPad(QWidget):
    changed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        inks: tuple[tuple[str, str], ...] = SIGNATURE_INKS,
        base: PhotoOptions | None = None,
        hint: str = SIGNATURE_HINT,
    ) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.data: bytes | None = None
        self.result: CleanResult | None = None
        self.base = base or PhotoOptions()
        self.options = self.base
        self._token = 0
        self._runner = Runner(threads=1, parent=self)
        self._debounce = QTimer(self, singleShot=True, interval=DEBOUNCE_MS)
        self._debounce.timeout.connect(self._process)

        self.choose = QPushButton("Choose photo or image…")
        self.choose.clicked.connect(self.browse)
        hint_label = QLabel(hint)
        hint_label.setObjectName("Muted")
        hint_label.setWordWrap(True)
        self.status = QLabel("")
        self.status.setObjectName("Muted")

        self.crop_view = CropView()
        self.crop_view.crop_changed.connect(self._on_crop)
        self.result_view = ResultView()
        photo_label, result_label = QLabel("Photo"), QLabel("Result")
        for label in (photo_label, result_label):
            label.setObjectName("SectionTitle")

        self.ink_buttons: dict[str, QToolButton] = {}
        ink_row = QHBoxLayout()
        ink_row.setSpacing(SPACING // 2)
        ink_group = QButtonGroup(self)
        for key, text in inks:
            button = QToolButton()
            button.setText(text)
            button.setCheckable(True)
            button.setAccessibleName(f"{text} ink")
            button.setObjectName("Segment")
            button.clicked.connect(lambda _=False, k=key: self._set(ink=k))
            ink_group.addButton(button)
            ink_row.addWidget(button)
            self.ink_buttons[key] = button
        self.ink_buttons.get(self.base.ink, next(iter(self.ink_buttons.values()))).setChecked(True)

        self.rotate_left = QToolButton()
        self.rotate_left.setProperty("iconName", "rotate-ccw")
        self.rotate_left.setToolTip("Turn left")
        self.rotate_left.setAccessibleName("Turn left")
        self.rotate_left.clicked.connect(lambda: self._turn(-90))
        self.rotate_right = QToolButton()
        self.rotate_right.setProperty("iconName", "rotate-cw")
        self.rotate_right.setToolTip("Turn right")
        self.rotate_right.setAccessibleName("Turn right")
        self.rotate_right.clicked.connect(lambda: self._turn(90))

        self.straighten = QSlider(Qt.Orientation.Horizontal)
        self.straighten.setRange(-150, 150)  # tenths of a degree
        self.straighten.setAccessibleName("Straighten")
        self.straighten.setToolTip("Straighten")
        self.straighten.valueChanged.connect(self._on_straighten)
        self.angle_label = QLabel("Auto")
        self.angle_label.setMinimumWidth(48)
        self.auto_button = QToolButton()
        self.auto_button.setText("Auto")
        self.auto_button.setToolTip("Straighten automatically")
        self.auto_button.clicked.connect(lambda: self._set(straighten=None))
        self.auto_button.setVisible(self.base.auto_straighten)
        if not self.base.auto_straighten:
            self.angle_label.setText("+0.0°")

        self.strength = QSlider(Qt.Orientation.Horizontal)
        self.strength.setRange(0, 100)
        self.strength.setValue(50)
        self.strength.setAccessibleName("Cleanup strength")
        self.strength.setToolTip("Gentle keeps faint strokes; strong removes more paper grain")
        self.strength.valueChanged.connect(lambda v: self._set(strength=v / 100))
        self.reset_crop = QToolButton()
        self.reset_crop.setText("Reset crop")
        self.reset_crop.clicked.connect(lambda: self._on_crop(None))

        controls = QGridLayout()
        controls.setHorizontalSpacing(SPACING)
        controls.setVerticalSpacing(SPACING // 2)
        controls.addWidget(QLabel("Ink"), 0, 0)
        controls.addLayout(ink_row, 0, 1)
        turn = QHBoxLayout()
        turn.addWidget(self.rotate_left)
        turn.addWidget(self.rotate_right)
        turn.addStretch()
        turn.addWidget(self.reset_crop)
        controls.addLayout(turn, 0, 2)
        controls.addWidget(QLabel("Straighten"), 1, 0)
        straight = QHBoxLayout()
        straight.addWidget(self.straighten, 1)
        straight.addWidget(self.angle_label)
        straight.addWidget(self.auto_button)
        controls.addLayout(straight, 1, 1, 1, 2)
        controls.addWidget(QLabel("Cleanup"), 2, 0)
        cleanup = QHBoxLayout()
        cleanup.addWidget(QLabel("Gentle"))
        cleanup.addWidget(self.strength, 1)
        cleanup.addWidget(QLabel("Strong"))
        controls.addLayout(cleanup, 2, 1, 1, 2)

        views = QGridLayout()
        views.addWidget(photo_label, 0, 0)
        views.addWidget(result_label, 0, 1)
        views.addWidget(self.crop_view, 1, 0)
        views.addWidget(self.result_view, 1, 1)

        top = QHBoxLayout()
        top.addWidget(self.choose)
        top.addWidget(hint_label, 1)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.addLayout(top)
        column.addLayout(views, 1)
        column.addLayout(controls)
        column.addWidget(self.status)
        self._enable(False)

    def set_tokens(self, t: Tokens) -> None:
        for button in (self.rotate_left, self.rotate_right):
            button.setIcon(icons.icon(str(button.property("iconName")), t.text))
        self.choose.setIcon(icons.icon("upload", t.text, 16))
        self.crop_view.accent = QColor(t.accent)

    # --- loading ------------------------------------------------------------------

    @property
    def png(self) -> bytes | None:
        return self.result.png if self.result else None

    def browse(self) -> None:
        start = str(Path.home() / "Pictures")
        path, _ = QFileDialog.getOpenFileName(self, "Choose signature image", start, IMAGE_FILTER)
        if path:
            self.load_file(Path(path))

    def load_file(self, path: Path) -> None:
        try:
            self.load_bytes(path.read_bytes())
        except OSError as exc:
            self.status.setText(f"Couldn't read {path.name}: {exc.strerror}")

    def load_bytes(self, data: bytes) -> None:
        try:
            image = sigimage.load(data)
        except Exception:
            self.status.setText("That file isn't an image PDR can read.")
            return
        self.data = data
        self.options = replace(self.base, ink=self._ink())
        self._show_original(image)
        self.straighten.blockSignals(True)
        self.straighten.setValue(0)
        self.straighten.blockSignals(False)
        self._enable(True)
        self._process()

    def _show_original(self, image: object) -> None:
        from PIL import Image

        assert isinstance(image, Image.Image)
        preview = image.convert("RGB")
        if self.options.rotation:
            preview = preview.rotate(-self.options.rotation, expand=True)
        preview.thumbnail((900, 900))
        raw = preview.tobytes("raw", "RGB")
        qimage = QImage(
            raw, preview.width, preview.height, preview.width * 3, QImage.Format.Format_RGB888
        ).copy()
        self.crop_view.set_image(qimage)

    def _enable(self, on: bool) -> None:
        for widget in (
            self.rotate_left,
            self.rotate_right,
            self.straighten,
            self.auto_button,
            self.strength,
            self.reset_crop,
            *self.ink_buttons.values(),
        ):
            widget.setEnabled(on)

    def _ink(self) -> str:
        return next((k for k, b in self.ink_buttons.items() if b.isChecked()), self.base.ink)

    # --- options ----------------------------------------------------------------------

    def _set(self, **changes: object) -> None:
        self.options = replace(self.options, **changes)  # type: ignore[arg-type]
        if "straighten" in changes and changes["straighten"] is None:
            self.angle_label.setText("Auto" if self.base.auto_straighten else "+0.0°")
        self._debounce.start()

    def _turn(self, degrees: int) -> None:
        self.options = replace(
            self.options,
            rotation=(self.options.rotation + degrees) % 360,
            crop=None,
            straighten=None,
        )
        if self.data is not None:
            self._show_original(sigimage.load(self.data))
        self._process()

    def _on_crop(self, crop: object) -> None:
        if crop is None:
            self.crop_view.crop = None
            self.crop_view.update()
        self._set(crop=crop)

    def _on_straighten(self, tenths: int) -> None:
        self.angle_label.setText(f"{tenths / 10:+.1f}°")
        self._set(straighten=tenths / 10)

    # --- processing ------------------------------------------------------------------

    def _process(self) -> None:
        if self.data is None:
            return
        self._token += 1
        self.result_view.busy = True
        self.result_view.update()
        work = partial(sigimage.clean_upload, self.data, self.options)
        self._runner.submit(work, partial(self._on_done, self._token))

    def _on_done(self, token: int, result: object) -> None:
        if token != self._token:
            return  # a newer setting is already being processed
        self.result_view.busy = False
        if isinstance(result, Exception):
            self.result = None
            self.result_view.set_png(None)
            self.status.setText("Couldn't clean up this image. Try cropping closer to the ink.")
        else:
            assert isinstance(result, CleanResult)
            self.result = result
            self.result_view.set_png(result.png)
            if self.options.straighten is None and self.base.auto_straighten:  # what auto chose
                self.straighten.blockSignals(True)
                self.straighten.setValue(round(result.angle * 10))
                self.straighten.blockSignals(False)
                self.angle_label.setText(f"Auto {result.angle:+.1f}°")
            self.status.setText("")
        self.changed.emit()

    def wait_idle(self, msecs: int = 5000) -> bool:
        """Tests: block until processing finished."""
        return self._runner.wait_idle(msecs)

    # --- drag and drop -------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if any(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.load_file(Path(url.toLocalFile()))
                event.acceptProposedAction()
                return
