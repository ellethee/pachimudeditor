"""I/O su file: caricamento/salvataggio atomico dei `.are` e gestione di `area.lst`."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .model import Area
from .parser import parse_area
from .writer import write_area


# -- utilita' ---------------------------------------------------------------------------------
def decode_bytes(data: bytes) -> tuple[str, str]:
    """Decodifica i byte di un file: UTF-8 se valido, altrimenti latin-1 (lossless). Restituisce (testo, encoding)."""
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def atomic_write_bytes(path: str | os.PathLike[str], data: bytes) -> None:
    """Scrive `data` su `path` in modo atomico (file temporaneo nella stessa cartella + `os.replace`).

    Se `path` esiste ne copia i permessi. Il file temporaneo e' rimosso in caso di errore.
    """
    target = Path(path)
    directory = target.parent
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp_name, target.stat().st_mode & 0o7777)
        except FileNotFoundError:
            os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


# -- file .are --------------------------------------------------------------------------------
def load_area_file(path: str | os.PathLike[str]) -> Area:
    """Legge e interpreta un file `.are` (stile newline, encoding e `#$` finale sono conservati nell'`Area`).

    Raises:
        RomParseError: sintassi non valida (con riga e nome file).
        OSError: file non leggibile.
    """
    p = Path(path)
    text, encoding = decode_bytes(p.read_bytes())
    area = parse_area(text, filename=p.name)
    area.encoding = encoding
    return area


def save_area_file(path: str | os.PathLike[str], area: Area, *, preserve: bool = True) -> None:
    """Scrive l'`Area` su `path` in modo atomico, con lo stile newline/encoding dell'area e il `#$` finale.

    Args:
        path: file di destinazione.
        area: area da serializzare.
        preserve: se True (default) il testo non modificato e' riemesso identico (vedi `write_area`).
    """
    text = write_area(area, preserve=preserve)
    atomic_write_bytes(path, text.encode(area.encoding))


# -- area.lst ---------------------------------------------------------------------------------
@dataclass
class AreaList:
    """Contenuto di `area.lst`: righe (nomi file, commenti `#...`, righe vuote) e terminatore `$`.

    Il server legge parole fino a `$`; le righe che iniziano con `#` sono commenti. `after`
    e' l'eventuale testo dopo la riga `$` (ignorato dal server, conservato).
    """

    lines: list[str] = field(default_factory=list)
    newline: str = "\n"
    after: str = ""
    final_newline: bool = True

    @property
    def names(self) -> list[str]:
        """Nomi dei file area elencati (senza commenti ne' righe vuote)."""
        return [ln.strip() for ln in self.lines if ln.strip() and not ln.strip().startswith("#")]

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name.strip() in self.names

    def add(self, name: str, *, index: int | None = None) -> bool:
        """Aggiunge `name` (prima del `$`, o in posizione `index` tra i nomi). False se gia' presente.

        Raises:
            ValueError: nome vuoto, con spazi o che inizia per `#`/`$`.
        """
        name = name.strip()
        if not name or any(c.isspace() for c in name) or name[0] in "#$":
            raise ValueError(f"nome file area non valido: {name!r}")
        if name in self:
            return False
        if index is None:
            self.lines.append(name)
        else:
            positions = [i for i, ln in enumerate(self.lines) if ln.strip() and not ln.strip().startswith("#")]
            self.lines.insert(positions[index] if index < len(positions) else len(self.lines), name)
        return True

    def remove(self, name: str) -> bool:
        """Rimuove `name` (tutte le occorrenze). False se assente."""
        name = name.strip()
        keep = [ln for ln in self.lines if ln.strip() != name]
        removed = len(keep) != len(self.lines)
        self.lines = keep
        return removed

    def to_text(self) -> str:
        """Serializza con il terminatore `$` sempre presente come ultima riga significativa."""
        nl = self.newline
        body = "".join(ln + nl for ln in self.lines)
        end = "$" + (nl if self.final_newline or self.after else "")
        return body + end + self.after


def parse_area_list(text: str) -> AreaList:
    """Interpreta il testo di `area.lst` (si ferma alla prima riga `$`; senza `$` ne aggiunge uno in scrittura)."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines: list[str] = []
    pos = 0
    n = len(text)
    while pos < n:
        eol = text.find("\n", pos)
        raw_end = n if eol < 0 else eol
        line = text[pos:raw_end].rstrip("\r")
        nxt = n if eol < 0 else eol + 1
        if line.strip().startswith("$"):
            return AreaList(lines, newline, text[nxt:], final_newline=eol >= 0)
        lines.append(line)
        pos = nxt
    return AreaList(lines, newline, "", True)


def read_area_list(path: str | os.PathLike[str]) -> AreaList:
    """Legge `area.lst` da file."""
    text, _ = decode_bytes(Path(path).read_bytes())
    return parse_area_list(text)


def write_area_list(path: str | os.PathLike[str], area_list: AreaList) -> None:
    """Scrive `area.lst` in modo atomico (con `$` finale)."""
    atomic_write_bytes(path, area_list.to_text().encode("utf-8"))


def add_area_to_list(path: str | os.PathLike[str], name: str, *, index: int | None = None) -> bool:
    """Aggiunge `name` ad `area.lst` (se manca) mantenendo il `$`. Restituisce True se il file e' cambiato."""
    lst = read_area_list(path)
    if lst.add(name, index=index):
        write_area_list(path, lst)
        return True
    return False


def remove_area_from_list(path: str | os.PathLike[str], name: str) -> bool:
    """Rimuove `name` da `area.lst`. Restituisce True se il file e' cambiato."""
    lst = read_area_list(path)
    if lst.remove(name):
        write_area_list(path, lst)
        return True
    return False
