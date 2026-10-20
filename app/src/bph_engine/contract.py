"""Contrat d'entrée / sortie du moteur (tâche P05).

Le moteur s'appelle comme un programme : une vidéo et une configuration en entrée,
un dossier de sortie au format décrit ici. L'interface ne lit que ce dossier.

Dossier de sortie :
    manifest.json        description de l'analyse (version du contrat, vidéo, cadence…)
    status.json          progression, phase, erreurs, code de sortie — réécrit atomiquement
    tracking.parquet     une ligne par objet et par image
    calibration.parquet  une homographie par image analysée
    masks/               masques d'occlusion, un PNG par image : masks/000123.png

Règle de versionnement : MAJEUR.MINEUR. Un changement qui casse la lecture incrémente
MAJEUR ; un ajout compatible (nouvelle colonne optionnelle) incrémente MINEUR. Un lecteur
refuse tout MAJEUR qu'il ne connaît pas plutôt que d'afficher des données fausses.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from bph_engine import __version__ as ENGINE_VERSION

CONTRACT_VERSION = "1.0"
SUPPORTED_MAJOR = 1

MANIFEST_FILE = "manifest.json"
STATUS_FILE = "status.json"
TRACKING_FILE = "tracking.parquet"
CALIBRATION_FILE = "calibration.parquet"
MASKS_DIR = "masks"

OBJECT_CLASSES = ("player", "goalkeeper", "referee", "ball")

TRACKING_SCHEMA = pa.schema(
    [
        pa.field("frame", pa.int32(), nullable=False),          # numéro d'image dans la vidéo source
        pa.field("object_id", pa.int32(), nullable=False),      # identité stable du tracker
        pa.field("cls", pa.dictionary(pa.int8(), pa.string()), nullable=False),  # OBJECT_CLASSES
        pa.field("team", pa.int8()),                            # 0 / 1, nul pour arbitre et ballon
        pa.field("x_px", pa.float32(), nullable=False),         # point au sol, pixels image
        pa.field("y_px", pa.float32(), nullable=False),
        pa.field("x_cm", pa.float32()),                         # terrain (cm), nul si homographie invalide
        pa.field("y_cm", pa.float32()),
        pa.field("confidence", pa.float32(), nullable=False),
    ]
)

CALIBRATION_SCHEMA = pa.schema(
    [
        pa.field("frame", pa.int32(), nullable=False),
        pa.field("homography", pa.list_(pa.float64(), 9), nullable=False),  # image -> terrain (cm), par lignes
        pa.field("valid", pa.bool_(), nullable=False),
        pa.field("reprojection_error", pa.float32()),
    ]
)


class ContractError(Exception):
    """Sortie de moteur illisible ou d'une version de contrat inconnue."""


class Phase(StrEnum):
    QUEUED = "queued"
    PROBE = "probe"
    DETECTION = "detection"
    TRACKING = "tracking"
    CALIBRATION = "calibration"
    WRITING = "writing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Status:
    phase: Phase = Phase.QUEUED
    progress: float = 0.0          # 0.0 à 1.0
    frames_done: int = 0
    frames_total: int = 0
    errors: list[str] = field(default_factory=list)
    exit_code: int | None = None   # nul tant que l'analyse tourne
    contract_version: str = CONTRACT_VERSION
    engine_version: str = ENGINE_VERSION
    updated_at: float = 0.0

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["phase"] = self.phase.value
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Status:
        check_version(d.get("contract_version"))
        return cls(
            phase=Phase(d["phase"]),
            progress=float(d["progress"]),
            frames_done=int(d["frames_done"]),
            frames_total=int(d["frames_total"]),
            errors=list(d.get("errors", [])),
            exit_code=d.get("exit_code"),
            contract_version=d["contract_version"],
            engine_version=d.get("engine_version", "?"),
            updated_at=float(d.get("updated_at", 0.0)),
        )


def check_version(version: object) -> None:
    if not isinstance(version, str) or "." not in version:
        raise ContractError(f"version de contrat absente ou invalide : {version!r}")
    major = version.split(".")[0]
    if not major.isdigit() or int(major) != SUPPORTED_MAJOR:
        raise ContractError(
            f"version de contrat {version} non prise en charge (attendu {SUPPORTED_MAJOR}.x) : "
            "mettre à jour l'application"
        )


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    """Écrit puis renomme : un lecteur ne voit jamais un fichier à moitié écrit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_status(out_dir: Path, status: Status) -> None:
    status.updated_at = time.time()
    write_json_atomic(out_dir / STATUS_FILE, status.to_json())


def read_status(out_dir: Path) -> Status:
    try:
        data = json.loads((out_dir / STATUS_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ContractError(f"fichier d'état illisible : {e}") from e
    return Status.from_json(data)


@dataclass
class Manifest:
    video_path: str
    fps: float
    frame_count: int
    analysed_fps: float            # cadence d'analyse (25 ou 5 en mode réduit)
    width: int
    height: int
    contract_version: str = CONTRACT_VERSION
    engine_version: str = ENGINE_VERSION

    def write(self, out_dir: Path) -> None:
        write_json_atomic(out_dir / MANIFEST_FILE, asdict(self))

    @classmethod
    def read(cls, out_dir: Path) -> Manifest:
        try:
            data = json.loads((out_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise ContractError(f"manifeste illisible : {e}") from e
        check_version(data.get("contract_version"))
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)


def _write_table(path: Path, table: pa.Table) -> None:
    pq.write_table(table, path, compression="zstd")


def _with_version(schema: pa.Schema) -> pa.Schema:
    return schema.with_metadata({b"contract_version": CONTRACT_VERSION.encode()})


def write_tracking(out_dir: Path, table: pa.Table) -> None:
    _write_table(out_dir / TRACKING_FILE, table.cast(_with_version(TRACKING_SCHEMA)))


def write_calibration(out_dir: Path, table: pa.Table) -> None:
    _write_table(out_dir / CALIBRATION_FILE, table.cast(_with_version(CALIBRATION_SCHEMA)))


def _read_table(path: Path, schema: pa.Schema) -> pa.Table:
    try:
        table = pq.read_table(path)
    except (OSError, pa.ArrowInvalid) as e:
        raise ContractError(f"{path.name} illisible : {e}") from e
    meta = table.schema.metadata or {}
    check_version(meta.get(b"contract_version", b"").decode() or None)
    missing = [f.name for f in schema if f.name not in table.column_names]
    if missing:
        raise ContractError(f"{path.name} : colonnes manquantes {missing}")
    return table


def read_tracking(out_dir: Path) -> pa.Table:
    return _read_table(out_dir / TRACKING_FILE, TRACKING_SCHEMA)


def read_calibration(out_dir: Path) -> pa.Table:
    return _read_table(out_dir / CALIBRATION_FILE, CALIBRATION_SCHEMA)


def mask_path(out_dir: Path, frame: int) -> Path:
    return out_dir / MASKS_DIR / f"{frame:06d}.png"
