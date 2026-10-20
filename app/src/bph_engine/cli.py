"""Interface en ligne de commande du moteur.

    bph-engine probe VIDEO
    bph-engine normalize VIDEO SORTIE.mp4
    bph-engine analyse VIDEO --out DOSSIER [--config analyse.toml] [--reduced]

Codes de sortie : 0 succès · 2 arguments ou configuration invalides · 3 vidéo illisible
· 4 écriture de la sortie impossible.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa

from bph_engine import __version__, contract
from bph_engine.contract import Manifest, Phase, Status
from bph_engine.video import VideoError, normalize, probe

EXIT_OK, EXIT_USAGE, EXIT_VIDEO, EXIT_OUTPUT = 0, 2, 3, 4


@dataclass(frozen=True)
class AnalysisConfig:
    reduced: bool = False
    reduced_fps: float = 5.0
    models_dir: str = "models"

    @classmethod
    def load(cls, path: Path | None, reduced_flag: bool) -> AnalysisConfig:
        data: dict = {}
        if path is not None:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        section = data.get("analyse", {})
        return cls(
            reduced=reduced_flag or section.get("mode", "complet") == "reduit",
            reduced_fps=float(section.get("cadence_reduite", 5)),
            models_dir=str(data.get("modeles", {}).get("dossier", "models")),
        )


def cmd_probe(args: argparse.Namespace) -> int:
    info = probe(args.video)
    out = {k: v for k, v in info.__dict__.items() if k != "fps"}
    out["fps"] = f"{info.fps.numerator}/{info.fps.denominator}"
    out["needs_normalization"] = info.needs_normalization()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return EXIT_OK


def cmd_normalize(args: argparse.Namespace) -> int:
    info = probe(args.video)
    result = normalize(info, args.output, on_progress=lambda p: print(f"progress={p:.3f}", flush=True))
    print(f"ok {result.path} {result.frame_count} images")
    return EXIT_OK


def cmd_analyse(args: argparse.Namespace) -> int:
    out_dir: Path = args.out
    try:
        config = AnalysisConfig.load(args.config, args.reduced)
    except (OSError, tomllib.TOMLDecodeError, ValueError) as e:
        print(f"configuration invalide : {e}", file=sys.stderr)
        return EXIT_USAGE
    status = Status(phase=Phase.PROBE)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        contract.write_status(out_dir, status)
    except OSError as e:
        print(f"dossier de sortie inutilisable : {e}", file=sys.stderr)
        return EXIT_OUTPUT
    try:
        info = probe(args.video)
    except VideoError as e:
        status.phase, status.errors, status.exit_code = Phase.FAILED, [str(e)], EXIT_VIDEO
        contract.write_status(out_dir, status)
        print(e, file=sys.stderr)
        return EXIT_VIDEO

    analysed_fps = min(config.reduced_fps, info.fps_float) if config.reduced else info.fps_float
    step = max(1, round(info.fps_float / analysed_fps))
    status.frames_total = (info.frame_count + step - 1) // step
    Manifest(
        video_path=info.path, fps=info.fps_float, frame_count=info.frame_count,
        analysed_fps=info.fps_float / step, width=info.width, height=info.height,
    ).write(out_dir)

    # Les modèles de vision arrivent avec la phase 5 (P11 et suivantes). D'ici là, le moteur
    # produit une sortie vide mais conforme au contrat, ce qui permet de construire et de
    # tester l'interface, la file d'analyse et la lecture des résultats.
    status.phase = Phase.WRITING
    contract.write_status(out_dir, status)
    contract.write_tracking(out_dir, contract.TRACKING_SCHEMA.empty_table())
    contract.write_calibration(out_dir, pa.Table.from_pylist([], schema=contract.CALIBRATION_SCHEMA))
    (out_dir / contract.MASKS_DIR).mkdir(exist_ok=True)

    status.phase, status.progress, status.exit_code = Phase.DONE, 1.0, EXIT_OK
    contract.write_status(out_dir, status)
    if not Path(config.models_dir).is_dir():
        print("aucun modèle de vision installé : sortie vide conforme au contrat", file=sys.stderr)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bph-engine", description="Moteur d'analyse vidéo football")
    version = f"%(prog)s {__version__} (contrat {contract.CONTRACT_VERSION})"
    p.add_argument("--version", action="version", version=version)
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("probe", help="inspecter une vidéo (JSON)")
    sp.add_argument("video", type=Path)
    sp.set_defaults(func=cmd_probe)

    sn = sub.add_parser("normalize", help="normaliser une vidéo pour la lecture à l'image près")
    sn.add_argument("video", type=Path)
    sn.add_argument("output", type=Path)
    sn.set_defaults(func=cmd_normalize)

    sa = sub.add_parser("analyse", help="analyser une vidéo et écrire la sortie du contrat")
    sa.add_argument("video", type=Path)
    sa.add_argument("--out", type=Path, required=True)
    sa.add_argument("--config", type=Path)
    sa.add_argument("--reduced", action="store_true", help="mode cadence réduite (5 images/s)")
    sa.set_defaults(func=cmd_analyse)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except VideoError as e:
        print(e, file=sys.stderr)
        return EXIT_VIDEO


if __name__ == "__main__":
    sys.exit(main())
