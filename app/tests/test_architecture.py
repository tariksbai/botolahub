from pathlib import Path

from tools.check_architecture import check


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_real_project_is_compliant() -> None:
    assert check() == []


def test_detects_qt_import_in_engine(tmp_path: Path) -> None:
    write(tmp_path, "src/bph_engine/bad.py", "from PySide6.QtCore import QObject\n")
    write(tmp_path, "src/bph_engine/bad2.py", "import PyQt6\n")
    errors = check(tmp_path)
    assert len(errors) == 2 and all("Qt" in e for e in errors)


def test_qt_allowed_in_interface(tmp_path: Path) -> None:
    write(tmp_path, "src/bph_app/ui.py", "from PySide6.QtWidgets import QWidget\n")
    assert check(tmp_path) == []


def test_detects_forbidden_dependencies(tmp_path: Path) -> None:
    write(tmp_path, "src/bph_app/det.py", "from ultralytics import YOLO\nimport torch\n")
    write(tmp_path, "pyproject.toml", '[project]\ndependencies = ["ultralytics>=8", "numpy"]\n')
    errors = check(tmp_path)
    assert len(errors) == 3
    assert any("AGPL" in e for e in errors)
