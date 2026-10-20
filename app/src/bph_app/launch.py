"""Point d'entrée de l'exécutable empaqueté (packaging/bottola.spec).

`BottolaAnalyse --engine …` exécute le moteur (bph-engine) sans charger Qt : c'est ainsi
que l'interface lance le moteur dans un processus séparé une fois l'application empaquetée
(voir engine_runner.engine_command). Sans `--engine`, l'interface démarre.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--engine":
        if sys.stdout is None:  # exécutable sans console lancé hors de l'application
            sys.stdout = open(os.devnull, "w")  # noqa: SIM115
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w")  # noqa: SIM115
        from bph_engine.cli import main as engine_main

        return engine_main(sys.argv[2:])
    from bph_app.__main__ import main as app_main

    return app_main()


if __name__ == "__main__":
    sys.exit(main())
