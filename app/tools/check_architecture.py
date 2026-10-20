"""Garde-fou d'architecture, exécuté par la CI et par pre-commit.

Règles vérifiées :
1. Le moteur (src/bph_engine) n'importe jamais Qt.
2. La zone livrable (src/) n'importe jamais de bibliothèque interdite chez le client :
   code sous AGPL (ultralytics) ou réservé à l'entraînement (torch, torchvision).
3. La zone livrable n'importe jamais la zone d'entraînement (training/).
4. Les dépendances déclarées dans pyproject.toml ne contiennent aucun paquet interdit.

Sortie : code 0 si tout est conforme, 1 sinon, avec la liste des violations.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "src" / "bph_engine"
DELIVERABLE = ROOT / "src"

QT_MODULES = {"PySide6", "PySide2", "PyQt5", "PyQt6", "shiboken6", "qtpy"}
# Paquet -> raison. Toute entrée ici est refusée dans la zone livrable.
FORBIDDEN = {
    "ultralytics": "AGPL-3.0 : imposerait la publication du code et des poids",
    "torch": "PyTorch est réservé à l'entraînement ; le client exécute ONNX Runtime",
    "torchvision": "réservé à l'entraînement",
    "training": "la zone d'entraînement n'est jamais livrée",
}


def imported_roots(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name.split(".")[0]) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.lineno, node.module.split(".")[0]))
    return found


def dependency_name(spec: str) -> str:
    for sep in "<>=!~[; ":
        spec = spec.split(sep)[0]
    return spec.strip().lower()


def check(root: Path = ROOT) -> list[str]:
    engine = root / "src" / "bph_engine"
    deliverable = root / "src"
    errors: list[str] = []

    for py in sorted(engine.rglob("*.py")):
        for line, mod in imported_roots(py):
            if mod in QT_MODULES:
                errors.append(f"{py.relative_to(root)}:{line}: le moteur importe Qt ({mod})")

    for py in sorted(deliverable.rglob("*.py")):
        for line, mod in imported_roots(py):
            if mod in FORBIDDEN:
                errors.append(f"{py.relative_to(root)}:{line}: import interdit '{mod}' — {FORBIDDEN[mod]}")

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        deps = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {}).get("dependencies", [])
        for dep in deps:
            name = dependency_name(dep)
            if name in FORBIDDEN:
                errors.append(f"pyproject.toml: dépendance livrable interdite '{name}' — {FORBIDDEN[name]}")
    return errors


def main() -> int:
    errors = check()
    for e in errors:
        print(e)
    if errors:
        print(f"\n{len(errors)} violation(s) des règles d'architecture.")
        return 1
    print("Architecture conforme : moteur sans Qt, aucune dépendance interdite dans le livrable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
