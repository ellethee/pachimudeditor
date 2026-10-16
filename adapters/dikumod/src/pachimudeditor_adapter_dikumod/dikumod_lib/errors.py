"""Eccezioni e diagnostica della libreria Diku Modificato."""

from __future__ import annotations

from dataclasses import dataclass


class DikumodParseError(ValueError):
    """File Diku Modificato non interpretabile nel suo insieme (i record singoli corrotti NON alzano: diventano `Raw`)."""


class DikumodWriteError(ValueError):
    """Dati del modello non serializzabili in modo che il loader del gioco li rilegga correttamente."""


@dataclass(frozen=True)
class Diagnostic:
    """Un problema trovato durante il caricamento di un file: `severity` e' `error` (record `Raw`) o `warning`."""

    file: str
    line: int
    vnum: int | None
    message: str
    severity: str = "error"

    def __str__(self) -> str:
        """Testo leggibile `file:riga [vnum]: messaggio`."""
        where = f"{self.file}:{self.line}" + (f" [{self.vnum}]" if self.vnum is not None else "")
        return f"{where}: {self.message}"
