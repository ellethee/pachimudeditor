"""Accesso ai file di una cartella `lib/` di Diku Modificato: individuazione, lettura, override per-vnum, salvataggio atomico."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .errors import Diagnostic, DikumodParseError
from .model import RecordFile, ZoneOverride
from .parser import (
    parse_mob,
    parse_obj,
    parse_scripts_dat,
    parse_shp,
    parse_wld,
    parse_zon,
    parse_zone_override,
)
from .writer import atomic_write_bytes, encode_latin1, format_zone_override, write_file

OVERRIDE_NAME = re.compile(r"[0-9]+")
"""Nome ammesso per i file per-vnum (`atoi(nome)` del gioco: i backup `40033~` sono rumore)."""


DEFAULT_PREFIX = "dikumoddata"
"""Prefisso predefinito dei file dati (`<prefisso>.wld`, `.mob`, `.obj`, `.zon`, `.shp`, `.gui`)."""
_PREFIX_RE = re.compile(r"[A-Za-z0-9_-]+")


def validate_prefix(prefix: object) -> str:
    """Il prefisso dei file dati, se valido (solo `[A-Za-z0-9_-]`, nessun percorso).

    Raises:
        ValueError: prefisso non stringa, vuoto o con caratteri non ammessi.
    """
    if not isinstance(prefix, str) or not _PREFIX_RE.fullmatch(prefix):
        raise ValueError(f"params.data_prefix non valido: {prefix!r} (ammessi solo lettere, cifre, `_` e `-`, nessun percorso)")
    return prefix


def resolve_lib(path: str | Path, prefix: str = DEFAULT_PREFIX) -> Path:
    """La cartella `lib/`: `path` stesso se contiene `<prefisso>.wld`, altrimenti `path/lib`.

    Raises:
        DikumodParseError: nessuna cartella dati Diku Modificato.
    """
    prefix = validate_prefix(prefix)
    root = Path(path).expanduser()
    for candidate in (root, root / "lib"):
        if (candidate / f"{prefix}.wld").is_file():
            return candidate.resolve()
    raise DikumodParseError(f"nessun file {prefix}.wld in {root}: imposta params.data_prefix")


def read_text(path: Path) -> str:
    """Il file come testo `latin-1` (un carattere per byte: round-trip esatto)."""
    return path.read_bytes().decode("latin-1")


@dataclass
class DikumodPaths:
    """I percorsi dei file di un mondo Diku Modificato."""

    lib: Path
    prefix: str = DEFAULT_PREFIX

    def named(self, ext: str) -> Path:
        """`<prefisso>.<ext>` nella cartella `lib/`."""
        return self.lib / f"{self.prefix}.{ext}"

    @property
    def gui(self) -> Path:
        """`<prefisso>.gui` (gilde)."""
        return self.named("gui")

    @property
    def wld(self) -> Path:
        """`dikumoddata.wld`."""
        return self.named("wld")

    @property
    def mob(self) -> Path:
        """`dikumoddata.mob`."""
        return self.named("mob")

    @property
    def obj(self) -> Path:
        """`dikumoddata.obj`."""
        return self.named("obj")

    @property
    def zon(self) -> Path:
        """`dikumoddata.zon`."""
        return self.named("zon")

    @property
    def shp(self) -> Path:
        """`dikumoddata.shp`."""
        return self.named("shp")

    @property
    def scripts_dat(self) -> Path:
        """`scripts.dat`."""
        return self.lib / "scripts.dat"

    def override_dir(self, kind: str) -> Path:
        """`rooms/`, `objects/` o `zones/`."""
        return self.lib / {"room": "rooms", "obj": "objects", "zone": "zones"}[kind]

    def overrides(self, kind: str) -> dict[int, Path]:
        """`{vnum o indice: file}` dei file per-vnum (solo nomi interamente numerici, `0` escluso come nel gioco)."""
        folder = self.override_dir(kind)
        if not folder.is_dir():
            return {}
        out: dict[int, Path] = {}
        for p in sorted(folder.iterdir()):
            if p.is_file() and OVERRIDE_NAME.fullmatch(p.name) and int(p.name) != 0:
                out[int(p.name)] = p
        return out

    def script_file(self, name: str) -> Path:
        """`scripts/<Nome>` (solo nomi semplici)."""
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name.startswith("."):
            raise ValueError(f"nome di script non valido: {name!r}")
        return self.lib / "scripts" / name


def load_wld(path: Path, *, vnum: int | None = None) -> RecordFile:
    """`dikumoddata.wld` oppure `rooms/<vnum>` (con `vnum`)."""
    rf = parse_wld(read_text(path), path.name, force_vnum=vnum)
    rf.path = path
    return rf


def load_mob(path: Path) -> RecordFile:
    """`dikumoddata.mob`."""
    rf = parse_mob(read_text(path), path.name)
    rf.path = path
    return rf


def load_obj(path: Path, *, vnum: int | None = None) -> RecordFile:
    """`dikumoddata.obj` oppure `objects/<vnum>` (con `vnum`: l'identita' e' il nome del file, l'header `#N` e' ignorato)."""
    rf = parse_obj(read_text(path), path.name, force_vnum=vnum)
    rf.path = path
    return rf


def load_zon(path: Path) -> RecordFile:
    """`dikumoddata.zon`."""
    rf = parse_zon(read_text(path), path.name)
    rf.path = path
    return rf


def load_shp(path: Path) -> RecordFile:
    """`dikumoddata.shp`."""
    rf = parse_shp(read_text(path), path.name)
    rf.path = path
    return rf


def load_zone_override(path: Path) -> ZoneOverride:
    """`zones/<n>.zon` (l'indice e' `atoi(nome)`)."""
    return parse_zone_override(read_text(path), int(re.match(r"\d+", path.name).group()), path.name)  # type: ignore[union-attr]


@dataclass
class DikumodWorld:
    """Tutto il mondo letto da una cartella `lib/` (comodo per strumenti e test; l'adapter usa una cache per file)."""

    paths: DikumodPaths
    wld: RecordFile
    mob: RecordFile
    obj: RecordFile
    zon: RecordFile
    shp: RecordFile | None = None
    scripts: RecordFile | None = None
    room_overrides: dict[int, RecordFile] = field(default_factory=dict)
    object_overrides: dict[int, RecordFile] = field(default_factory=dict)
    zone_overrides: dict[int, ZoneOverride] = field(default_factory=dict)

    @property
    def diagnostics(self) -> list[Diagnostic]:
        """Tutte le diagnostiche dei file letti."""
        files = [self.wld, self.mob, self.obj, self.zon, self.shp, self.scripts]
        files += [*self.room_overrides.values(), *self.object_overrides.values()]
        return [d for f in files if f is not None for d in f.diagnostics]


def load_world(path: str | Path, prefix: str = DEFAULT_PREFIX) -> DikumodWorld:
    """Legge `dikumoddata.{wld,mob,obj,zon,shp}`, `scripts.dat` e gli override di `rooms/`, `objects/`, `zones/`."""
    paths = DikumodPaths(resolve_lib(path, prefix), prefix)
    world = DikumodWorld(paths, load_wld(paths.wld), load_mob(paths.mob), load_obj(paths.obj), load_zon(paths.zon))
    if paths.shp.is_file():
        world.shp = load_shp(paths.shp)
    if paths.scripts_dat.is_file():
        world.scripts = parse_scripts_dat(read_text(paths.scripts_dat), "scripts.dat")
        world.scripts.path = paths.scripts_dat
    world.room_overrides = {v: load_wld(p, vnum=v) for v, p in paths.overrides("room").items()}
    world.object_overrides = {v: load_obj(p, vnum=v) for v, p in paths.overrides("obj").items()}
    world.zone_overrides = {n: load_zone_override(p) for n, p in paths.overrides("zone").items()}
    return world


def save(rf: RecordFile, path: Path | None = None, *, canonical: bool = False, ensure_terminator: bool = True) -> None:
    """Scrive un `RecordFile` (atomico, `latin-1`). Per i file per-vnum passare `ensure_terminator=False`."""
    target = path or rf.path
    if target is None:
        raise ValueError("percorso mancante")
    write_file(target, rf, canonical=canonical, ensure_terminator=ensure_terminator)


def save_zone_override(path: Path, zone: ZoneOverride, *, canonical: bool = False) -> None:
    """Scrive `zones/<n>.zon` (atomico, `latin-1`): invariato = stessi byte, altrimenti righe canoniche e `S`."""
    if zone._src is not None and zone._fp == repr(zone) and not canonical:
        text = zone._src
    else:
        text = format_zone_override(zone, canonical=canonical)
    atomic_write_bytes(path, encode_latin1(text))
