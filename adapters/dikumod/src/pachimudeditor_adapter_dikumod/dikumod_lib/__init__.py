"""Libreria standalone (solo stdlib) per leggere e scrivere i file dati di Diku Modificato (un Diku molto modificato).

Uso tipico::

    from pachimudeditor_adapter_dikumod.dikumod_lib import load_world, save

    world = load_world("/percorso/a/dikumod2")     # cartella lib/ o la sua radice
    mob = world.mob.find(3000)
    mob.level = 30
    save(world.mob)                                         # atomico; solo i record toccati cambiano

Vedi README.md nel pacchetto e `docs/formats/dikumod.md`.
"""

from .cscan import CScan
from .errors import Diagnostic, DikumodParseError, DikumodUnencodableError, DikumodWriteError
from .files import (
    DikumodPaths,
    DikumodWorld,
    load_mob,
    load_obj,
    load_shp,
    load_wld,
    load_world,
    load_zon,
    load_zone_override,
    resolve_lib,
    validate_prefix,
    DEFAULT_PREFIX,
    save,
    save_zone_override,
)
from .model import (
    Dice,
    Exit,
    ExtraDesc,
    Mob,
    Obj,
    ObjAffect,
    Raw,
    RecordFile,
    Room,
    ScriptEntry,
    Shop,
    Tele,
    Zone,
    ZoneCmd,
    ZoneOverride,
    ZoneText,
)
from .parser import parse_mob, parse_obj, parse_scripts_dat, parse_shp, parse_wld, parse_zon, parse_zone_override
from .writer import (
    format_cmd,
    format_mob,
    format_obj,
    format_room,
    format_shop,
    format_zone,
    index_hazard,
    insert_sorted,
    is_sorted,
    is_unchanged,
    needs_fix,
    write_file,
    write_text,
)

__all__ = [
    "CScan", "Diagnostic", "Dice", "Exit", "ExtraDesc", "DikumodParseError", "DikumodPaths", "DikumodWorld", "DikumodUnencodableError", "DikumodWriteError",
    "Mob", "Obj", "ObjAffect", "Raw", "RecordFile", "Room", "ScriptEntry", "Shop", "Tele", "Zone", "ZoneCmd",
    "ZoneOverride", "ZoneText", "format_cmd", "format_mob", "format_obj", "format_room", "format_shop",
    "format_zone", "index_hazard", "insert_sorted", "is_sorted", "is_unchanged", "load_mob", "load_obj",
    "load_shp", "load_wld", "load_world", "load_zon", "load_zone_override", "needs_fix", "parse_mob",
    "parse_obj", "parse_scripts_dat", "parse_shp", "parse_wld", "parse_zon", "parse_zone_override",
    "resolve_lib", "validate_prefix", "DEFAULT_PREFIX", "save", "save_zone_override", "write_file", "write_text",
]  # fmt: skip
