"""Archivio dei file `.are` di un mondo BasedMud: cache, indici per vnum e scrittura atomica.

Un'area e' un file `.are`. Sono "zone" i file con un'intestazione (`#AREA`/`#AREADATA`); i file di soli
help/social elencati in `area.lst` (`help.are`, `social.are`, `olc.hlp`, ...) vengono ignorati.

- **Cache**: ogni file e' riletto solo se cambia `(mtime_ns, size)`; anche `area.lst` e la cartella sono
  controllati a ogni richiesta (`refresh`, solo `stat`), quindi modifiche esterne sono viste subito.
- **`id` di zona**: il vnum minimo dell'intestazione (unico). Una zona senza range ("da assegnare", 0-0, oppure
  range non numerico o doppio) riceve un id negativo `-(posizione + 1)` nell'elenco delle zone.
- **Scrittura**: `save` usa `save_area_file(..., preserve=True)` (atomico, gli elementi non toccati restano
  byte per byte); se fallisce la cache del file viene invalidata, cosi' la prossima lettura ricarica da disco.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pachimudeditor_adapter_basedmud.rom_lib import (
    Area,
    AreaList,
    Mobile,
    Object,
    Room,
    RomParseError,
    load_area_file,
    parse_area_list,
    render_area_file,
    save_area_file,
    write_area_list,
)
from pachimudeditor_adapter_basedmud.rom_lib.files import atomic_write_bytes, decode_bytes
from pachifast.i18n import api_error

log = logging.getLogger(__name__)

Kind = Literal["room", "mob", "object"]
_SECTION: dict[str, str] = {"room": "ROOMS", "mob": "MOBILES", "object": "OBJECTS"}
FILE_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,60}\.are$")
"""Nome di file area ammesso: niente separatori ne' `..`, solo `.are`."""


def resolve_area_dir(path: str | None) -> Path:
    """La cartella delle aree: `path` stesso (se contiene `area.lst` o `.are`) oppure `path/area`.

    Raises:
        ValueError: `path` mancante o senza cartella aree.
    """
    if not path:
        raise ValueError("Il mondo basedmud richiede `path` (radice di basedmud o sua cartella area)")
    root = Path(path).expanduser()
    for candidate in (root, root / "area"):
        if candidate.is_dir() and ((candidate / "area.lst").is_file() or any(candidate.glob("*.are"))):
            return candidate.resolve()
    raise ValueError(f"Nessuna cartella di aree basedmud in {root} (serve area.lst o file .are)")


@dataclass(eq=False)
class AreaEntry:
    """Un file `.are` caricato."""

    name: str
    path: Path
    area: Area
    stamp: tuple[int, int] | None
    listed: bool = False
    zone_id: int = 0

    @property
    def header(self) -> Any:
        """L'intestazione (`AreaHeader`); presente per ogni zona."""
        return self.area.header

    def items(self, kind: Kind) -> list[Any]:
        """Gli elementi della sezione `kind` senza crearla se manca (lista vuota)."""
        section = self.area.section(_SECTION[kind], create=False)
        return section.items if section is not None else []

    def remove(self, kind: Kind, item: Any) -> None:
        """Toglie `item` (per identita') dalla sezione `kind`."""
        items = self.items(kind)
        items[:] = [i for i in items if i is not item]

    def writable_items(self, kind: Kind) -> list[Any]:
        """Come `items` ma crea la sezione se manca (per aggiungere elementi)."""
        return getattr(self.area, {"room": "rooms", "mob": "mobiles", "object": "objects"}[kind])


@dataclass
class AreaStore:
    """Cartella di aree con cache e indici (vedi docstring del modulo)."""

    area_dir: Path
    entries: dict[str, AreaEntry] = field(default_factory=dict)
    zones: list[AreaEntry] = field(default_factory=list)
    _index: dict[str, dict[int, tuple[AreaEntry, Any]]] = field(default_factory=dict)
    _list_stamp: tuple[int, int] | None = None
    _dir_stamp: tuple[str, ...] = ()
    _loaded: bool = False

    # ------------------------------------------------------------------ percorsi e area.lst

    @property
    def list_path(self) -> Path:
        """Il file `area.lst`."""
        return self.area_dir / "area.lst"

    def safe_path(self, name: str) -> Path:
        """Il percorso di un file area dentro la cartella; 422 `basedmud.invalid_file_name` se il nome non e' ammesso."""
        if not FILE_NAME.fullmatch(name or ""):
            raise api_error(422, "basedmud.invalid_file_name", name=str(name))
        path = (self.area_dir / name).resolve()
        if path.parent != self.area_dir:
            raise api_error(422, "basedmud.invalid_file_name", name=name)
        return path

    def read_list(self) -> AreaList:
        """`area.lst` (vuota se il file non esiste)."""
        try:
            text, _ = decode_bytes(self.list_path.read_bytes())
        except FileNotFoundError:
            return AreaList()
        return parse_area_list(text)

    def set_listed(self, name: str, listed: bool) -> None:
        """Aggiunge/toglie `name` da `area.lst` (mantiene il `$` finale)."""
        lst = self.read_list()
        if lst.add(name) if listed else lst.remove(name):
            write_area_list(self.list_path, lst)
        self._loaded = False  # forza la ricostruzione degli indici alla prossima `refresh`

    def add_file(self, name: str, area: Area, *, listed: bool) -> AreaEntry:
        """Scrive un nuovo file area (atomico), lo elenca in `area.lst` se `listed` e restituisce la zona caricata."""
        save_area_file(self.safe_path(name), area, preserve=True)
        self.set_listed(name, listed)
        self.refresh()
        return self.entries[name]

    # ------------------------------------------------------------------ caricamento

    @staticmethod
    def _stamp(path: Path) -> tuple[int, int] | None:
        """`(mtime_ns, size)` del file o `None` se non esiste."""
        try:
            st = path.stat()
        except FileNotFoundError:
            return None
        return st.st_mtime_ns, st.st_size

    def refresh(self) -> None:
        """Riallinea la cache al disco (solo `stat`; ricarica i file cambiati e ricostruisce gli indici se serve)."""
        lst = self.read_list()
        list_stamp = self._stamp(self.list_path)
        listed = [n for n in lst.names if n.endswith(".are")]
        unlisted = sorted(p.name for p in self.area_dir.glob("*.are") if p.name not in listed and FILE_NAME.fullmatch(p.name))
        order = [*listed, *unlisted]
        changed = not self._loaded or list_stamp != self._list_stamp or tuple(order) != self._dir_stamp
        for name in order:
            path = self.area_dir / name
            stamp = self._stamp(path)
            current = self.entries.get(name)
            if stamp is None:
                if current is not None:
                    self.entries.pop(name)
                    changed = True
                continue
            if current is None or current.stamp != stamp:
                try:
                    area = load_area_file(path)
                except (RomParseError, OSError, ValueError) as error:
                    log.warning("area %s non leggibile: %s", name, error)
                    self.entries.pop(name, None)
                    changed = True
                    continue
                self.entries[name] = AreaEntry(name, path, area, stamp)
                changed = True
        for name in [n for n in self.entries if n not in order]:
            self.entries.pop(name)
            changed = True
        if changed:
            self._list_stamp, self._dir_stamp, self._loaded = list_stamp, tuple(order), True
            self._rebuild([n for n in order if n in self.entries], set(listed))

    def invalidate(self) -> None:
        """Scarta tutta la cache: la prossima `refresh` rilegge i file dal disco."""
        self.entries.clear()
        self._loaded = False

    def _rebuild(self, order: list[str], listed: set[str]) -> None:
        """Ricostruisce elenco zone, id di zona e indici per vnum."""
        self.entries = {n: self.entries[n] for n in order}
        self.zones = []
        used: set[int] = set()
        self._index = {"room": {}, "mob": {}, "object": {}}
        for entry in self.entries.values():
            entry.listed = entry.name in listed
            header = entry.area.header
            if header is None:
                continue
            self.zones.append(entry)
            numeric = header.vnum_raw is None and (header.min_vnum, header.max_vnum) != (0, 0)
            if numeric and header.min_vnum not in used:
                entry.zone_id = header.min_vnum
                used.add(header.min_vnum)
            else:
                entry.zone_id = -len(self.zones)
            for kind in ("room", "mob", "object"):
                for item in entry.items(kind):
                    if self._index[kind].setdefault(item.vnum, (entry, item))[1] is not item:
                        log.warning("%s vnum %s duplicato in %s", kind, item.vnum, entry.name)

    def save(self, *entries: AreaEntry) -> None:
        """Scrive i file (atomici, `preserve=True`) e ricarica dal disco quelli scritti (i testi sorgente tornano
        coerenti); se una scrittura fallisce la cache dei file coinvolti e' invalidata."""
        try:
            rendered = [
                (entry.path, render_area_file(entry.area, preserve=True)) for entry in entries
            ]  # tutto verificato prima di scrivere
            for path, data in rendered:
                atomic_write_bytes(path, data)
        except BaseException:
            for entry in entries:
                entry.stamp = None
            raise
        for entry in entries:
            self.entries.pop(entry.name, None)
        self._loaded = False
        self.refresh()

    # ------------------------------------------------------------------ ricerca

    def zone_by_id(self, zone_id: int) -> AreaEntry | None:
        """La zona con quell'id."""
        return next((z for z in self.zones if z.zone_id == zone_id), None)

    def find(self, kind: Kind, vnum: int) -> tuple[AreaEntry, Any] | None:
        """`(zona, elemento)` per vnum, o `None`."""
        return self._index[kind].get(vnum)

    def all_items(self, kind: Kind) -> list[tuple[AreaEntry, Any]]:
        """Tutti gli elementi `kind` di tutte le zone, in ordine di vnum."""
        return sorted(self._index[kind].values(), key=lambda pair: pair[1].vnum)

    def rooms_names(self) -> dict[int, str]:
        """vnum -> nome di tutte le stanze (per risolvere le destinazioni delle uscite)."""
        return {vnum: room.name for vnum, (_, room) in self._index["room"].items()}

    def mob(self, entry: AreaEntry, vnum: int) -> Mobile | None:
        """Il mob `vnum` dell'area."""
        return next((m for m in entry.items("mob") if m.vnum == vnum), None)

    def room(self, entry: AreaEntry, vnum: int) -> Room | None:
        """La stanza `vnum` dell'area."""
        return next((r for r in entry.items("room") if r.vnum == vnum), None)

    def obj(self, entry: AreaEntry, vnum: int) -> Object | None:
        """L'oggetto `vnum` dell'area."""
        return next((o for o in entry.items("object") if o.vnum == vnum), None)
