"""Procedure speciali dei mob di Diku Modificato, lette in SOLA LETTURA da `src/spec_assign.c`.

Nei file dati non c'e' nessun flag "maestro": il gioco assegna per vnum una procedura speciale in C
(`specials[] = { { 30, MageGuildMaster }, ... }` in `assign_mobiles()`). Questo modulo non compila ne' esegue nulla:
legge il testo, toglie commenti e blocchi `#if 0`, e raccoglie le coppie `{ vnum, Procedura }` della tabella dei mob.

Percorso del file: `params.spec_assign` (assoluto) oppure `<radice>/src/spec_assign.c`, con la radice = genitore di `lib/`.
Se il file manca o non e' leggibile le procedure sono sconosciute (`SpecAssign.procs()` e' `None`): l'adapter funziona
come prima, senza il filtro `trainer`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

MAX_BYTES = 1024 * 1024
"""Dimensione massima di `spec_assign.c` (quello di leu pesa ~9 KB): oltre, il file non si legge."""

TEACHING_PROCS = frozenset(
    {
        "MageGuildMaster", "ClericGuildMaster", "ThiefGuildMaster", "WarriorGuildMaster",  # spec_procs.c
        "DruidGuildMaster", "monk_master", "barbarian_guildmaster", "RangerGuildmaster",  # spec_procs2.c
        "PsiGuildmaster", "PaladinGuildmaster", "mage_specialist_guildmaster",
    }
)  # fmt: skip
"""Procedure speciali che fanno insegnare: rispondono a `practice`/`practise` e/o `gain` (maestri di gilda).

Questo e' l'UNICO posto da riallineare. Si ricava cosi': in `src/spec_procs*.c` cercare le procedure che gestiscono
`CMD_GAIN`/`CMD_PRACTICE`/`CMD_PRACTISE` (in leu: le 11 elencate; `spec_procs2.c` usa i numeri di comando 164/170/243 =
practice/practise/gain, quindi cercare anche `cmd == 164|170|243` e risalire alla funzione). `MonkChallenger` NON conta (sfidanti, non maestri). `PlayersGuildMaster` (`gilde.c`) NON conta: gestisce le gilde
dei giocatori, non l'allenamento delle classi, e non e' assegnata in `spec_assign.c`."""

_COMMENTS = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)
_DIRECTIVE = re.compile(r"^\s*#\s*(ifdef|ifndef|if|elif|else|endif)\b(.*)$")
_TABLE = re.compile(r"special_proc_entry\s+\w+\s*\[\s*\]\s*=\s*\{")
_ENTRY = re.compile(r"\{\s*(-?\d+)\s*,\s*([A-Za-z_]\w*)\s*\}")


class SpecAssignError(ValueError):
    """`spec_assign.c` non leggibile (troppo grande, binario, illeggibile)."""


def _active_lines(text: str) -> str:
    """Il testo senza commenti e senza i rami `#if 0` / `#else` spenti (le altre condizioni valgono come vere: primo ramo)."""
    stack: list[list[bool]] = []  # per ogni #if: [ramo attivo, ramo gia' preso]
    out: list[str] = []
    for line in _COMMENTS.sub(" ", text).splitlines():
        m = _DIRECTIVE.match(line)
        if m is None:
            if all(top[0] for top in stack):
                out.append(line)
            continue
        kind, cond = m[1], m[2].strip()
        if kind in ("if", "ifdef", "ifndef"):
            on = not (kind == "if" and cond == "0")  # `#if 0` e' l'unico ramo spento in partenza
            stack.append([on, on])
        elif stack and kind == "elif":
            top = stack[-1]
            top[0] = not top[1] and cond != "0"
            top[1] = top[1] or top[0]
        elif stack and kind == "else":
            top = stack[-1]
            top[0] = not top[1]
            top[1] = True
        elif stack and kind == "endif":
            stack.pop()
    return "\n".join(out)


def parse_spec_assign(text: str) -> dict[int, str]:
    """`{vnum: procedura}` della tabella `special_proc_entry` dei mob (la riga con vnum negativo chiude, come nel C).

    Righe non valide e voci `NULL` si ignorano; con un vnum doppio vale l'ultima assegnazione (come nel gioco).
    """
    code = _active_lines(text)
    start = _TABLE.search(code)
    if start is None:
        return {}
    depth, end = 1, start.end()
    while end < len(code) and depth:
        depth += {"{": 1, "}": -1}.get(code[end], 0)
        end += 1
    procs: dict[int, str] = {}
    for m in _ENTRY.finditer(code[start.end() : end]):
        vnum, name = int(m[1]), m[2]
        if vnum < 0:
            break
        if name != "NULL":
            procs[vnum] = name
    return procs


def read_spec_assign(path: Path) -> dict[int, str]:
    """Legge e interpreta il file; `SpecAssignError` se e' troppo grande, binario o illeggibile."""
    try:
        if path.stat().st_size > MAX_BYTES:
            raise SpecAssignError(f"{path} supera {MAX_BYTES} byte")
        data = path.read_bytes()
    except OSError as error:
        raise SpecAssignError(f"{path} non leggibile: {error.strerror or error}") from error
    if b"\0" in data:
        raise SpecAssignError(f"{path} non e' un file di testo")
    return parse_spec_assign(data.decode("latin-1"))


@dataclass(frozen=True)
class SpecIssue:
    """Un avviso per `worlds check`."""

    code: str
    message: str


@dataclass(frozen=True)
class SpecReport:
    """Stato della lettura di `spec_assign.c` (stessa forma del rapporto di schema degli altri adapter per `worlds check`)."""

    path: Path | None
    count: int | None
    warnings: tuple[SpecIssue, ...] = ()

    def summary(self) -> str:
        """Riga di sintesi."""
        return "spec_assign non trovato (filtro `trainer` non disponibile)" if self.count is None else f"{self.count} procedure speciali"


class SpecAssign:
    """Procedure speciali dei mob da `spec_assign.c`, riletto solo quando cambiano data o dimensione del file."""

    def __init__(self, path: Path | None) -> None:
        """`path` = file da leggere (`None`: nessuna ricerca, procedure sconosciute)."""
        self.path = path
        self._key: tuple[int, int] | None = None
        self._procs: dict[int, str] | None = None
        self._error: str | None = None

    @classmethod
    def locate(cls, lib: Path, configured: object) -> SpecAssign:
        """Da `params.spec_assign` (percorso assoluto; `ValueError` se non lo e') o da `<genitore di lib>/src/spec_assign.c`."""
        if configured is not None:
            if not isinstance(configured, str) or not os.path.isabs(configured) or "\0" in configured:
                raise ValueError("params.spec_assign deve essere il percorso ASSOLUTO di spec_assign.c")
            return cls(Path(configured))
        return cls(lib.parent / "src" / "spec_assign.c")

    def procs(self) -> dict[int, str] | None:
        """`{vnum: procedura}`, oppure `None` se il file non esiste o non e' leggibile (filtro non supportato)."""
        if self.path is None:
            return None
        try:
            st = self.path.stat()
        except OSError:
            self._key, self._procs, self._error = None, None, None
            return None
        key = (st.st_mtime_ns, st.st_size)
        if key != self._key:
            self._key = key
            try:
                self._procs, self._error = read_spec_assign(self.path), None
            except SpecAssignError as error:
                self._procs, self._error = None, str(error)
        return self._procs

    @property
    def supported(self) -> bool:
        """`True` se le procedure sono note."""
        return self.procs() is not None

    def proc_of(self, vnum: int) -> str | None:
        """La procedura assegnata al mob (`None` se nessuna o se non si sa)."""
        return (self.procs() or {}).get(vnum)

    def is_trainer(self, vnum: int) -> bool | None:
        """Il mob ha una procedura di insegnamento (`None` = non si sa)."""
        procs = self.procs()
        return None if procs is None else procs.get(vnum) in TEACHING_PROCS

    def report(self) -> SpecReport:
        """Rapporto per `worlds check`."""
        procs = self.procs()
        if procs is not None:
            return SpecReport(self.path, len(procs))
        reason = self._error or (f"{self.path} non esiste" if self.path else "percorso non determinabile")
        return SpecReport(self.path, None, (SpecIssue("spec_assign_missing", f"spec_assign.c non letto: {reason}"),))
