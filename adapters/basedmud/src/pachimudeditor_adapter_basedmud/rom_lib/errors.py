"""Eccezioni della libreria `.are`."""

from __future__ import annotations


class RomParseError(ValueError):
    """Errore di sintassi in un file `.are`, con numero di riga (1-based) e colonna.

    Attributes:
        message: descrizione dell'errore (senza prefisso di posizione).
        line: riga del file in cui e' stato rilevato l'errore (0 se sconosciuta).
        column: colonna (1-based) nella riga (0 se sconosciuta).
        context: contesto logico, es. ``"MOBILES vnum 3001"``.
        filename: nome del file, se noto.
    """

    def __init__(
        self,
        message: str,
        line: int = 0,
        column: int = 0,
        context: str = "",
        filename: str | None = None,
    ) -> None:
        self.message = message
        self.line = line
        self.column = column
        self.context = context
        self.filename = filename
        super().__init__(self._format())

    def _format(self) -> str:
        """Compone il messaggio con riga/colonna/contesto."""
        where = f"riga {self.line}" if self.line else "posizione ignota"
        if self.line and self.column:
            where += f", colonna {self.column}"
        if self.filename:
            where = f"{self.filename}: {where}"
        ctx = f" [{self.context}]" if self.context else ""
        return f"{where}{ctx}: {self.message}"


class RomWriteError(ValueError):
    """Dati del modello non serializzabili in formato `.are`."""


class RomUnencodableError(RomWriteError):
    """Il testo contiene caratteri non rappresentabili nell'encoding del file (es. emoji in un `.are` latin-1)."""
