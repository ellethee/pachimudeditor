"""Archivio dei file di un mondo Diku Modificato: cache per file (mtime+size), indici per vnum, scrittura atomica.

Vedi la docstring di `adapters.dikumod.adapter` per le convenzioni di `id`. Regole di risoluzione (come `boot_db`):

- **stanze**: `dikumoddata.wld` poi `rooms/<vnum>`; il file per-vnum vince; con vnum doppio nel `.wld` vince l'ultimo;
- **oggetti**: `dikumoddata.obj` poi `objects/<vnum>`; il file per-vnum vince;
- **mob**: solo `dikumoddata.mob` (`mobiles/` e' vestigiale); con vnum doppio il primo (il gioco usa una ricerca binaria);
- **zone**: posizione nel `dikumoddata.zon` (`id` = indice); i comandi vengono da `zones/<indice>.zon` se esiste.
"""

from __future__ import annotations

import bisect
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pachimudeditor_adapter_dikumod.dikumod_lib import (
    DikumodPaths,
    Obj,
    Raw,
    RecordFile,
    Room,
    ScriptEntry,
    Shop,
    Zone,
    ZoneCmd,
    ZoneOverride,
    load_mob,
    load_obj,
    load_shp,
    load_wld,
    load_zon,
    load_zone_override,
    DEFAULT_PREFIX,
    resolve_lib,
    save,
    save_zone_override,
)
from pachimudeditor_adapter_dikumod.dikumod_lib.files import read_text
from pachimudeditor_adapter_dikumod.dikumod_lib.parser import parse_scripts_dat
from pachimudeditor_adapter_dikumod.dikumod_lib.writer import atomic_write_bytes, encode_latin1, write_text

log = logging.getLogger(__name__)

Stamp = tuple[int, int] | None


def resolve(path: str | None, prefix: str = DEFAULT_PREFIX) -> Path:
    """La cartella `lib/` del mondo; `ValueError` se `path` manca o non e' un mondo Diku Modificato."""
    if not path:
        raise ValueError("Il mondo dikumod richiede `path` (la cartella lib/ o la sua radice)")
    try:
        lib = resolve_lib(path, prefix)
    except Exception as error:  # DikumodParseError
        raise ValueError(str(error)) from error
    missing = [n for n in (f"{prefix}.mob", f"{prefix}.obj", f"{prefix}.zon") if not (lib / n).is_file()]
    if missing:
        raise ValueError(f"Mondo dikumod incompleto in {lib}: mancano {', '.join(missing)} (params.data_prefix)")
    return lib


@dataclass(eq=False)
class Ref:
    """Un'entita' con il file che la contiene (`override`: file per-vnum)."""

    vnum: int
    rf: RecordFile
    item: Any
    override: bool = False


@dataclass(eq=False)
class ZoneRef:
    """Una zona: posizione (`index` = id), elemento (`Zone`/`Raw`), eventuale override dei comandi."""

    index: int
    item: Zone | Raw
    override: ZoneOverride | None = None
    override_path: Path | None = None

    @property
    def raw(self) -> bool:
        """Zona illeggibile (conservata ma non modificabile)."""
        return isinstance(self.item, Raw)

    def commands(self) -> list[ZoneCmd]:
        """I comandi effettivi: dell'override se c'e', altrimenti della zona."""
        if self.override is not None:
            return self.override.commands
        return self.item.commands if isinstance(self.item, Zone) else []

    def items(self) -> list[Any]:
        """Elementi (comandi e righe di testo) della sorgente dei comandi effettiva."""
        if self.override is not None:
            return self.override.items
        return self.item.items if isinstance(self.item, Zone) else []


@dataclass
class DikumodStore:
    """Cartella `lib/` con cache e indici (vedi docstring del modulo)."""

    lib: Path
    prefix: str = DEFAULT_PREFIX
    paths: DikumodPaths = field(init=False)
    _cache: dict[Path, tuple[Stamp, Any]] = field(default_factory=dict)
    _listing: tuple[Any, ...] = ()
    _built: bool = False
    # indici (ricostruiti da `_rebuild`)
    wld: RecordFile | None = None
    mob: RecordFile | None = None
    obj: RecordFile | None = None
    zon: RecordFile | None = None
    shp: RecordFile | None = None
    scripts: RecordFile | None = None
    zones: list[ZoneRef] = field(default_factory=list)
    tops: list[int] = field(default_factory=list)
    rooms: dict[int, Ref] = field(default_factory=dict)
    mobs: dict[int, Ref] = field(default_factory=dict)
    raw_mobs: dict[int, Raw] = field(default_factory=dict)
    objs: dict[int, Ref] = field(default_factory=dict)
    shops: dict[int, Shop] = field(default_factory=dict)
    script_by_vnum: dict[int, ScriptEntry] = field(default_factory=dict)
    duplicates: dict[str, set[int]] = field(default_factory=dict)
    room_overrides: dict[int, Path] = field(default_factory=dict)
    obj_overrides: dict[int, Path] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Calcola i percorsi dei file."""
        self.paths = DikumodPaths(self.lib, self.prefix)

    # ------------------------------------------------------------------ cache

    @staticmethod
    def _stamp(path: Path) -> Stamp:
        """`(mtime_ns, size)` o `None` se manca."""
        try:
            st = path.stat()
        except FileNotFoundError:
            return None
        return st.st_mtime_ns, st.st_size

    def _get(self, path: Path, loader: Callable[[Path], Any]) -> tuple[Any, bool]:
        """`(oggetto caricato o None, ricaricato?)` con cache per `(mtime, size)`."""
        stamp = self._stamp(path)
        cached = self._cache.get(path)
        if stamp is None:
            self._cache.pop(path, None)
            return None, cached is not None
        if cached is not None and cached[0] == stamp:
            return cached[1], False
        try:
            obj = loader(path)
        except (OSError, ValueError) as error:
            log.warning("file %s non leggibile: %s", path.name, error)
            self._cache.pop(path, None)
            return None, True
        self._cache[path] = (stamp, obj)
        return obj, True

    def invalidate(self) -> None:
        """Dimentica tutta la cache (dopo una scrittura fallita o una modifica non salvata)."""
        self._cache.clear()
        self._built = False

    def refresh(self) -> None:
        """Riallinea cache e indici al disco (solo `stat` se nulla e' cambiato)."""
        p = self.paths
        changed = not self._built
        loaded: dict[str, Any] = {}
        for name, path, loader in (
            ("wld", p.wld, load_wld), ("mob", p.mob, load_mob), ("obj", p.obj, load_obj),
            ("zon", p.zon, load_zon), ("shp", p.shp, load_shp),
        ):  # fmt: skip
            obj, did = self._get(path, loader)
            loaded[name] = obj
            changed |= did
        scripts, did = self._get(p.scripts_dat, lambda path: _load_scripts(path))
        loaded["scripts"] = scripts
        changed |= did
        room_files = p.overrides("room")
        obj_files = p.overrides("obj")
        zone_files = p.overrides("zone")
        listing = (tuple(room_files), tuple(obj_files), tuple(zone_files))
        changed |= listing != self._listing
        overrides: dict[str, dict[int, Any]] = {"room": {}, "obj": {}, "zone": {}}
        for v, path in room_files.items():
            obj, did = self._get(path, lambda q, v=v: load_wld(q, vnum=v))
            changed |= did
            if obj is not None:
                overrides["room"][v] = obj
        for v, path in obj_files.items():
            obj, did = self._get(path, lambda q, v=v: load_obj(q, vnum=v))
            changed |= did
            if obj is not None:
                overrides["obj"][v] = obj
        for n, path in zone_files.items():
            obj, did = self._get(path, load_zone_override)
            changed |= did
            if obj is not None:
                overrides["zone"][n] = obj
        keep = {p.wld, p.mob, p.obj, p.zon, p.shp, p.scripts_dat, *room_files.values(), *obj_files.values(), *zone_files.values()}
        for stale in [k for k in self._cache if k not in keep]:
            self._cache.pop(stale)
            changed = True
        if changed:
            self._listing = listing
            self.room_overrides, self.obj_overrides = room_files, obj_files
            self._rebuild(loaded, overrides, zone_files)

    # ------------------------------------------------------------------ indici

    def _rebuild(self, loaded: dict[str, Any], overrides: dict[str, dict[int, Any]], zone_files: dict[int, Path]) -> None:
        """Ricostruisce zone, indici per vnum, negozi e script."""
        self.wld, self.mob, self.obj = loaded["wld"], loaded["mob"], loaded["obj"]
        self.zon, self.shp, self.scripts = loaded["zon"], loaded["shp"], loaded["scripts"]
        self.duplicates = {"room": set(), "mob": set(), "object": set()}
        self.zones = []
        for i, item in enumerate(self.zon.items if self.zon else []):
            ref = ZoneRef(i, item)
            if i in overrides["zone"]:
                ref.override, ref.override_path = overrides["zone"][i], zone_files[i]
            self.zones.append(ref)
        self.tops, last = [], 0
        for z in self.zones:
            last = z.item.top if isinstance(z.item, Zone) else last
            self.tops.append(last)
        self.rooms = {}
        for item in self.wld.items if self.wld else []:
            if isinstance(item, Room):
                if item.vnum in self.rooms:
                    self.duplicates["room"].add(item.vnum)
                self.rooms[item.vnum] = Ref(item.vnum, self.wld, item)  # type: ignore[arg-type]
        for v, rf in overrides["room"].items():
            rooms = [i for i in rf.items if isinstance(i, Room)]
            if rooms:
                self.rooms[v] = Ref(v, rf, rooms[-1], True)
        self.mobs, self.raw_mobs = {}, {}
        for item in self.mob.items if self.mob else []:
            if isinstance(item, Raw):
                self.raw_mobs.setdefault(item.vnum, item)  # type: ignore[arg-type]
            elif item.vnum in self.mobs:
                self.duplicates["mob"].add(item.vnum)
            else:
                self.mobs[item.vnum] = Ref(item.vnum, self.mob, item)  # type: ignore[arg-type]
        self.objs = {}
        for item in self.obj.items if self.obj else []:
            if isinstance(item, Obj):
                if item.vnum in self.objs:
                    self.duplicates["object"].add(item.vnum)
                else:
                    self.objs[item.vnum] = Ref(item.vnum, self.obj, item)  # type: ignore[arg-type]
        for v, rf in overrides["obj"].items():
            objs = [i for i in rf.items if isinstance(i, Obj)]
            if objs:
                self.objs[v] = Ref(v, rf, objs[0], True)
        self.shops = {}
        for item in self.shp.items if self.shp else []:
            if isinstance(item, Shop):
                self.shops.setdefault(item.keeper, item)
        self.script_by_vnum = {}
        for item in self.scripts.items if self.scripts else []:
            if isinstance(item, ScriptEntry):
                self.script_by_vnum.setdefault(item.vnum, item)
        self._built = True

    # ------------------------------------------------------------------ zone

    def zone_of(self, vnum: int) -> int | None:
        """Indice della zona che possiede `vnum` (la prima con `top >= vnum`), `None` se oltre l'ultima."""
        i = bisect.bisect_left(self.tops, vnum)
        return i if i < len(self.tops) else None

    def bounds(self, index: int) -> tuple[int, int]:
        """`(bottom, top)` derivati; `(0, 0)` per una zona che non possiede vnum (top <= top della precedente)."""
        top = self.tops[index]
        bottom = self.tops[index - 1] + 1 if index > 0 else 0
        return (bottom, top) if top >= bottom and (index == 0 or top > self.tops[index - 1]) else (0, 0)

    def zone(self, index: int) -> ZoneRef | None:
        """La zona con quell'indice."""
        return self.zones[index] if 0 <= index < len(self.zones) else None

    def commands_in_zones(self) -> list[tuple[ZoneRef, ZoneCmd]]:
        """Tutti i comandi di tutte le zone (con la zona)."""
        return [(z, c) for z in self.zones for c in z.commands()]

    # ------------------------------------------------------------------ scrittura

    def save(self, *files: RecordFile) -> None:
        """Scrive i `RecordFile` (atomici, `latin-1`) e ricarica; in caso di errore invalida la cache."""
        try:
            for rf in dict.fromkeys(files):  # prima di scrivere il primo file: nessuna scrittura parziale se un testo non e' codificabile
                if not rf.is_clean():
                    encode_latin1(write_text(rf))
            for rf in dict.fromkeys(files):
                if rf.is_clean():
                    continue  # nulla da riscrivere: i byte restano quelli del disco
                main = rf.path in (self.paths.wld, self.paths.mob, self.paths.obj, self.paths.zon, self.paths.shp)
                if rf.path is None:
                    raise ValueError("file senza percorso")
                save(rf, ensure_terminator=main)
        except BaseException:
            self.invalidate()
            raise
        for rf in files:
            self._cache.pop(rf.path, None)  # type: ignore[arg-type]
        self._built = False
        self.refresh()

    def save_zone_override(self, zone: ZoneRef) -> None:
        """Scrive `zones/<n>.zon` della zona."""
        try:
            save_zone_override(zone.override_path, zone.override)  # type: ignore[arg-type]
        except BaseException:
            self.invalidate()
            raise
        self._cache.pop(zone.override_path, None)  # type: ignore[arg-type]
        self._built = False
        self.refresh()

    def write_text_file(self, path: Path, text: str) -> None:
        """Scrive un file di testo qualsiasi della cartella (script) in modo atomico."""
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, encode_latin1(text))
        self._built = False
        self._cache.pop(path, None)

    def delete_file(self, path: Path) -> None:
        """Elimina un file (override) e ricarica."""
        try:
            os.unlink(path)
        finally:
            self._cache.pop(path, None)
            self._built = False
            self.refresh()

    def text_of(self, path: Path) -> str | None:
        """Il testo di un file (script) o `None` se manca."""
        try:
            return read_text(path)
        except FileNotFoundError:
            return None


def _load_scripts(path: Path) -> RecordFile:
    """`scripts.dat`."""
    rf = parse_scripts_dat(read_text(path), path.name)
    rf.path = path
    return rf


def new_scripts_file(path: Path) -> RecordFile:
    """Un `scripts.dat` vuoto (non ancora su disco)."""
    return RecordFile("scripts", path)
