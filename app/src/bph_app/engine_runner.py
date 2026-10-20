"""Lancement du moteur dans un processus séparé.

L'interface n'exécute jamais de traitement lourd dans son propre processus : elle lance
`bph-engine` (contrat P05) et suit sa progression ligne par ligne. Une fermeture de
l'application ou une erreur du moteur ne peut donc pas corrompre l'interface.

BPH_ENGINE permet de désigner un exécutable du moteur ; sinon le moteur est lancé avec
l'interpréteur courant (`python -m bph_engine`). Le packaging (P25) fournira l'exécutable.
"""

from __future__ import annotations

import contextlib
import os
import sys

from PySide6.QtCore import QObject, QProcess, Signal


def engine_command(*args: str) -> tuple[str, list[str]]:
    exe = os.environ.get("BPH_ENGINE")
    if exe:
        return exe, list(args)
    return sys.executable, ["-m", "bph_engine", *args]


class EngineJob(QObject):
    progress = Signal(float)
    finished = Signal(bool, str)   # succès, message (stdout final ou erreur)

    def __init__(self, *args: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.proc = QProcess(self)
        program, argv = engine_command(*args)
        self.proc.setProgram(program)
        self.proc.setArguments(argv)
        self._out: list[str] = []
        self._cancelled = False
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._done)
        self.proc.errorOccurred.connect(self._error)

    def start(self) -> None:
        self.proc.start()

    def cancel(self) -> None:
        self._cancelled = True
        self.proc.kill()

    def _read(self) -> None:
        for raw in bytes(self.proc.readAllStandardOutput().data()).decode(errors="replace").splitlines():
            line = raw.strip()
            if line.startswith("progress="):
                with contextlib.suppress(ValueError):
                    self.progress.emit(float(line.split("=", 1)[1]))
            elif line:
                self._out.append(line)

    def _done(self, code: int, _status: QProcess.ExitStatus) -> None:
        self._read()
        if self._cancelled:
            self.finished.emit(False, "opération annulée")
        elif code == 0:
            self.finished.emit(True, "\n".join(self._out))
        else:
            err = bytes(self.proc.readAllStandardError().data()).decode(errors="replace").strip()
            self.finished.emit(False, err or f"le moteur s'est arrêté (code {code})")

    def _error(self, err: QProcess.ProcessError) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self.finished.emit(False, "impossible de lancer le moteur d'analyse")
