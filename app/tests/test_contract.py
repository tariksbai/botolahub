import json
from pathlib import Path

import pyarrow as pa
import pytest

from bph_engine import contract
from bph_engine.cli import main
from bph_engine.contract import ContractError, Manifest, Phase, Status


def test_status_roundtrip(tmp_path: Path) -> None:
    contract.write_status(tmp_path, Status(phase=Phase.TRACKING, progress=0.5, frames_done=10, frames_total=20))
    s = contract.read_status(tmp_path)
    assert s.phase is Phase.TRACKING and s.progress == 0.5 and s.exit_code is None
    assert not list(tmp_path.glob("*.tmp")), "écriture atomique : aucun fichier temporaire ne doit rester"


@pytest.mark.parametrize("version", ["2.0", "0.9", None, "x"])
def test_unknown_contract_version_is_refused(tmp_path: Path, version: object) -> None:
    data = Status().to_json()
    data["contract_version"] = version
    (tmp_path / contract.STATUS_FILE).write_text(json.dumps(data))
    with pytest.raises(ContractError):
        contract.read_status(tmp_path)


def test_minor_version_is_accepted(tmp_path: Path) -> None:
    data = Status().to_json()
    data["contract_version"] = "1.7"
    (tmp_path / contract.STATUS_FILE).write_text(json.dumps(data))
    assert contract.read_status(tmp_path).contract_version == "1.7"


def test_tracking_parquet_roundtrip(tmp_path: Path) -> None:
    rows = [
        {"frame": 0, "object_id": 1, "cls": "player", "team": 0, "x_px": 10.0, "y_px": 20.0,
         "x_cm": 100.0, "y_cm": 200.0, "confidence": 0.9},
        {"frame": 0, "object_id": 99, "cls": "ball", "team": None, "x_px": 1.0, "y_px": 2.0,
         "x_cm": None, "y_cm": None, "confidence": 0.5},
    ]
    contract.write_tracking(tmp_path, pa.Table.from_pylist(rows, schema=contract.TRACKING_SCHEMA))
    table = contract.read_tracking(tmp_path)
    assert table.num_rows == 2
    assert table.column("cls").to_pylist() == ["player", "ball"]


def test_parquet_without_version_is_refused(tmp_path: Path) -> None:
    import pyarrow.parquet as pq

    pq.write_table(contract.TRACKING_SCHEMA.empty_table(), tmp_path / contract.TRACKING_FILE)
    with pytest.raises(ContractError):
        contract.read_tracking(tmp_path)


def test_cli_analyse_writes_valid_contract(counter_video: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main(["analyse", str(counter_video), "--out", str(out), "--reduced"]) == 0
    status = contract.read_status(out)
    assert status.phase is Phase.DONE and status.exit_code == 0
    manifest = Manifest.read(out)
    assert manifest.frame_count == 1000 and manifest.fps == 25 and manifest.analysed_fps == 5
    assert contract.read_tracking(out).num_rows == 0
    assert contract.read_calibration(out).num_rows == 0


def test_cli_analyse_reports_unreadable_video(tmp_path: Path) -> None:
    bad = tmp_path / "pas_une_video.mp4"
    bad.write_bytes(b"rien")
    out = tmp_path / "out"
    assert main(["analyse", str(bad), "--out", str(out)]) == 3
    status = contract.read_status(out)
    assert status.phase is Phase.FAILED and status.exit_code == 3 and status.errors
