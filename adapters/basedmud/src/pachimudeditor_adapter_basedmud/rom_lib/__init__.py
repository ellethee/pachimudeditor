"""Libreria standalone per leggere e scrivere i file area `.are` ROM 2.4 / QuickMUD / basedmud.

Uso tipico::

    from pachimudeditor_adapter_basedmud.rom_lib import load_area_file, save_area_file

    area = load_area_file("area/midgaard.are")
    area.find_mobile(3000).level = 30
    save_area_file("/tmp/midgaard.are", area)

Vedi README.md nel pacchetto.
"""

from .errors import RomParseError, RomWriteError
from .files import (
    AreaList,
    add_area_to_list,
    atomic_write_bytes,
    load_area_file,
    parse_area_list,
    read_area_list,
    remove_area_from_list,
    save_area_file,
    write_area_list,
)
from .flags import (
    flag_names,
    flags_to_letters,
    format_flags,
    has_flag,
    letters_to_flags,
    names_to_flags,
    parse_flags,
    set_flag,
)
from .model import (
    Area,
    AreaHeader,
    CommentLine,
    Dice,
    Exit,
    ExtraDescription,
    FlagRemoval,
    Help,
    MobProg,
    MobProgTrigger,
    Mobile,
    Object,
    ObjectAffect,
    Reset,
    Room,
    Section,
    Shop,
    Social,
    Special,
)
from .parser import parse_area
from .writer import format_item, is_unchanged, write_area

__all__ = [
    "Area", "AreaHeader", "AreaList", "CommentLine", "Dice", "Exit", "ExtraDescription", "FlagRemoval",
    "Help", "MobProg", "MobProgTrigger", "Mobile", "Object", "ObjectAffect", "Reset", "Room",
    "RomParseError", "RomWriteError", "Section", "Shop", "Social", "Special",
    "add_area_to_list", "atomic_write_bytes", "flag_names", "flags_to_letters", "format_flags",
    "format_item", "has_flag", "is_unchanged", "letters_to_flags", "load_area_file", "names_to_flags",
    "parse_area", "parse_area_list", "parse_flags", "read_area_list", "remove_area_from_list",
    "save_area_file", "set_flag", "write_area", "write_area_list",
]
