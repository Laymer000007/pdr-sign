# PyInstaller spec: one-folder bundle in dist/pdr-sign/ (wrapped by the AppImage, the
# .deb and — not used by the snap, which builds from source).
#   .venv/bin/pyinstaller --noconfirm --clean packaging/pdr-sign.spec
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - provided by PyInstaller
SRC = ROOT / "src"

# Qt modules PDR never loads (only QtCore/Gui/Widgets/Svg/PrintSupport are used).
UNUSED_QT = [
    "QtNetwork", "QtQml", "QtQuick", "QtQuickWidgets", "QtOpenGL", "QtOpenGLWidgets",
    "QtSql", "QtTest", "QtXml", "QtConcurrent", "QtDesigner", "QtHelp", "QtUiTools",
    "QtStateMachine", "QtSvgWidgets", "QtDBus",
]

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(SRC)],
    datas=[(str(SRC / "pdr_sign" / "resources"), "pdr_sign/resources")],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtPrintSupport"],
    excludes=[f"PySide6.{m}" for m in UNUSED_QT]
    + ["tkinter", "unittest", "pydoc", "pdb", "doctest", "test", "pytest", "pyhanko"]
    # PyMuPDF 2.0 declares its layout/LLM add-ons as dependencies; PDR never uses them
    # (the whole test suite passes with these modules blocked).
    + ["numpy", "onnxruntime", "networkx", "pymupdf4llm", "pymupdf_layout", "yaml",
       "psutil", "tabulate"],
    noarchive=False,
)
# Qt plugins a desktop PDF reader never loads, and the libraries only they pull in.
# File dialogs go through the desktop portal (xdgdesktopportal theme), not GTK 3.
DROP_PLUGINS = (
    "platforms/libqeglfs", "platforms/libqlinuxfb", "platforms/libqminimal",
    "platforms/libqvnc", "platforms/libqvkkhrdisplay", "egldeviceintegrations/", "generic/",
    "platformthemes/libqgtk3", "imageformats/libqicns", "imageformats/libqtga",
    "imageformats/libqwbmp", "imageformats/libqtiff",
)
DROP_LIBS = (
    "libgtk-3", "libgdk-3", "libatk-1.0", "libatk-bridge", "libatspi", "libcairo-gobject",
    "libgdk_pixbuf", "libglycin", "libepoxy", "libQt6EglFs", "libQt6EglFSDeviceIntegration",
    "libgfortran", "libscipy_openblas", "librsvg", "libXcomposite", "libXdamage", "libXinerama",
    "libXcursor", "libXi.", "libXrandr", "libXRes",
)


def keep(entry: tuple[str, str, str]) -> bool:
    dest = entry[0].replace("\\", "/")
    name = dest.rsplit("/", 1)[-1]
    if any(part in dest for part in DROP_PLUGINS):
        return False
    return not any(name.startswith(prefix) for prefix in DROP_LIBS)


a.binaries = [e for e in a.binaries if keep(e)]
a.datas = [e for e in a.datas if keep(e)]

pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pdr-sign",
    strip=True,  # drop debug symbols (libpython from uv alone carries ~25 MB)
    upx=False,
    console=False,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=True,  # drop debug symbols (libpython from uv alone carries ~25 MB)
    upx=False,
    name="pdr-sign",
)
