"""Metadati del mondo BasedMud: enum/tabelle ROM, razze e classi (mixin di `BasedMudAdapter`).

`enums()` restituisce le enum standard dei DTO (valori pachimud, con cui il frontend gia' costruisce le select) piu' le
tabelle ROM `rom*` (`romRoomFlags`, `romMobFlags`, `romSectorType`, `romItemType`, ...): per i flag `value` e' il bit e
`label` il nome simbolico, per le tabelle di tipi `value` e' l'indice. Razze e classi vengono da `<radice>/src/tables.c`
(`race_table`, `class_table`); se il sorgente non c'e' le liste sono vuote.
"""

import re
from enum import Enum
from pathlib import Path

from pachimudeditor_adapter_basedmud.rom_lib.tables import FLAG_TABLES, TYPE_TABLES
from pachimudeditor.common.enums import Sex
from pachimudeditor.common.enums import ObjectType
from pachimudeditor.common.enums import ZoneCommandType, ZoneResetMode
from pachimudeditor.common.enums import Direction, DoorFlag, SectorType

from pachimudeditor_adapter_basedmud.base import BasedMudSupport
from pachimudeditor.common.adapters.models import ContentRef, Option

ROM_FLAG_TABLES: dict[str, str] = {
    "romRoomFlags": "room_flags",
    "romMobFlags": "mob_flags",
    "romAffectFlags": "affect_flags",
    "romOffFlags": "off_flags",
    "romResFlags": "res_flags",
    "romFormFlags": "form_flags",
    "romPartFlags": "part_flags",
    "romExtraFlags": "extra_flags",
    "romWearFlags": "wear_flags",
    "romContainerFlags": "container_flags",
    "romWeaponFlags": "weapon_flags",
}
"""Chiave in `enums()` -> tabella di flag della libreria."""

ROM_TYPE_TABLES: dict[str, str] = {
    "romSectorType": "sector_types",
    "romItemType": "item_types",
    "romSex": "sex_types",
    "romSize": "size_types",
    "romPosition": "position_types",
    "romAffectApply": "affect_apply_types",
    "romWearLoc": "wear_loc_types",
    "romWeaponType": "weapon_types",
    "romDoorReset": "door_resets",
}
"""Chiave in `enums()` -> tabella di tipi (indice = valore)."""


def _options(enum_cls: type[Enum]) -> list[Option]:
    """Opzioni (valore, etichetta) di un'enum dei DTO."""
    return [Option(value=m.value, label=m.name.replace("_", " ").capitalize()) for m in enum_cls]


def _table_block(text: str, marker: str) -> list[str]:
    """Le righe del blocco `marker ... = { ... };` di `tables.c` (vuoto se non trovato)."""
    start = text.find(marker)
    if start < 0:
        return []
    end = text.find("\n};", start)
    return text[start : end if end > 0 else None].splitlines()


class MetaMixin(BasedMudSupport):
    """Liste di opzioni, razze e classi."""

    async def enums(self) -> dict[str, list[Option]]:
        """Enum dei DTO + tabelle ROM (vedi docstring del modulo)."""
        out: dict[str, list[Option]] = {
            "sectorType": _options(SectorType),
            "direction": _options(Direction),
            "doorFlag": _options(DoorFlag),
            "zoneResetMode": _options(ZoneResetMode),
            "sex": _options(Sex),
            "objectType": _options(ObjectType),
            "zoneCommandType": _options(ZoneCommandType),
        }
        for key, table in ROM_FLAG_TABLES.items():
            out[key] = [Option(value=bit, label=name) for name, bit in FLAG_TABLES[table].items() if not name.startswith("unused")]
        for key, table in ROM_TYPE_TABLES.items():
            out[key] = [Option(value=i, label=name) for i, name in enumerate(TYPE_TABLES[table]) if not name.startswith("unused")]
        return out

    def _tables_c(self) -> str:
        """Il testo di `<radice>/src/tables.c` (vuoto se manca o non e' leggibile)."""
        try:
            return (Path(self.store.area_dir).parent / "src" / "tables.c").read_text(encoding="latin-1")
        except OSError:
            return ""

    async def races(self) -> list[ContentRef]:
        """Le razze di `race_table` (id = nome ROM, quello scritto nel campo razza dei mob)."""
        lines = _table_block(self._tables_c(), "const RACE_TYPE race_table[")
        names = [m.group(1) for line in lines if (m := re.match(r'\s*\{"([^"]+)",\s*(?:TRUE|FALSE),', line))]
        return [ContentRef(id=n, name=n.capitalize()) for n in names]

    async def classes(self) -> list[ContentRef]:
        """Le classi di `class_table` (id = nome ROM)."""
        lines = _table_block(self._tables_c(), "const CLASS_TYPE class_table[")
        names = [m.group(1) for line in lines if (m := re.match(r'\s*\{CLASS_\w+,\s*"([^"]+)"', line))]
        return [ContentRef(id=n, name=n.capitalize()) for n in names]
