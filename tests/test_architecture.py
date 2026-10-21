"""Project-wide rules from the spec, enforced as tests."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "src" / "pdr_sign" / "services"
# Built by concatenation so this file doesn't trip its own check.
FORBIDDEN = ("ado" + "be", "acro" + "bat")
SKIP_DIRS = {
    ".git",
    ".venv",
    "build",
    "dist",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}
SKIP_FILES = {"BUILD_PROMPT.md"}  # the brief itself states the rule
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".toml",
    ".yml",
    ".yaml",
    ".txt",
    ".svg",
    ".xml",
    ".desktop",
    ".sh",
    ".spec",
    ".in",
    ".cfg",
    ".json",
    "",
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_services_are_qt_free() -> None:
    offenders = {
        str(p.relative_to(ROOT)): sorted(
            m
            for m in _imported_modules(p)
            if m.split(".")[0] in {"PySide6", "shiboken6"} or m.startswith("pdr_sign.ui")
        )
        for p in SERVICES.rglob("*.py")
    }
    assert not {k: v for k, v in offenders.items() if v}


def test_no_forbidden_brand_names() -> None:
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or path.name in SKIP_FILES
            or SKIP_DIRS.intersection(path.relative_to(ROOT).parts)
            or path.suffix.lower() not in TEXT_SUFFIXES
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        hits.extend(f"{path.relative_to(ROOT)}: {w}" for w in FORBIDDEN if w in text)
    assert not hits


def test_no_oversized_modules() -> None:
    big = [
        str(p.relative_to(ROOT))
        for p in (ROOT / "src").rglob("*.py")
        if len(p.read_text(encoding="utf-8").splitlines()) > 400
    ]
    assert not big
