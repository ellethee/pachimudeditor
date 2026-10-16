"""Metadati del mondo Diku Modificato: enum standard dei DTO + tabelle `dikumod*` (mixin di `DikumodAdapter`).

`enums()` restituisce le sette enum standard (valori pachimud) con `zoneCommandType` esteso ai comandi Diku Modificato 7-10, piu' le
tabelle Diku Modificato: per i flag `value` e' il bit, per i tipi l'indice (`dikumodRoomFlags`, `dikumodExitFlags`, `dikumodActFlags`,
`dikumodAffectFlags`, `dikumodImmuneFlags`, `dikumodExtraFlags`, `dikumodWearFlags`, `dikumodTeleFlags`, `dikumodZoneResetBits`, `dikumodSector`,
`dikumodItemType`, `dikumodPosition`, `dikumodApplyType`, `dikumodWearPos`, `dikumodRace`, `dikumodLiquid`, `dikumodDoorState`, `dikumodHateFearType`,
`dikumodMobKind`).
"""

from __future__ import annotations

from enum import Enum

from pachimudeditor_adapter_dikumod.dikumod_lib import tables as T
from pachimudeditor.common.enums import Sex
from pachimudeditor.common.enums import ObjectType
from pachimudeditor.common.enums import ZoneCommandType, ZoneResetMode
from pachimudeditor.common.enums import Direction, DoorFlag, SectorType

from pachimudeditor_adapter_dikumod.base import DikumodSupport
from pachimudeditor.sdk import rules
from pachimudeditor.common.adapters.models import ContentRef, Option

DIKUMOD_FLAG_TABLES: dict[str, str] = {
    "dikumodRoomFlags": "room_flags",
    "dikumodExitFlags": "exit_flags",
    "dikumodActFlags": "act_flags",
    "dikumodAffectFlags": "affect_flags",
    "dikumodImmuneFlags": "immune_flags",
    "dikumodExtraFlags": "extra_flags",
    "dikumodWearFlags": "wear_flags",
    "dikumodTeleFlags": "tele_flags",
    "dikumodZoneResetBits": "",
}
"""Chiave in `enums()` -> tabella di flag della libreria."""
DIKUMOD_TYPE_TABLES: dict[str, list[str]] = {
    "dikumodSector": T.SECTORS,
    "dikumodItemType": T.ITEM_TYPES,
    "dikumodPosition": T.POSITIONS,
    "dikumodApplyType": T.APPLY_TYPES,
    "dikumodWearPos": T.WEAR_POSITIONS,
    "dikumodRace": T.RACES,
    "dikumodLiquid": T.LIQUIDS,
    "dikumodDoorState": [s.lower() for s in T.DOOR_STATES],
    "dikumodMobKind": ["S", "A", "N", "B", "L"],
}
"""Chiave in `enums()` -> tabella di tipi (indice = valore)."""
DIKUMOD_COMMANDS: list[Option] = [
    Option(value=int(c), label=c.name.replace("_", " ").capitalize()) for c in ZoneCommandType if c is not ZoneCommandType.RANDOMIZE_EXITS
] + [
    Option(value=rules.CHARM_MOB, label="Charm mob"), Option(value=rules.SET_HATE, label="Set hate"),
    Option(value=rules.SET_FEAR, label="Set fear"), Option(value=rules.SET_MOB_ZONE, label="Set mob zone"),
]  # fmt: skip
"""Comandi di reset di Diku Modificato (M O G E P D + C H F Z); `R` non e' implementato dal loader."""


def _options(enum_cls: type[Enum]) -> list[Option]:
    """Opzioni (valore, etichetta) di un'enum dei DTO."""
    return [Option(value=m.value, label=m.name.replace("_", " ").capitalize()) for m in enum_cls]


class MetaMixin(DikumodSupport):
    """Liste di opzioni, razze e classi."""

    async def enums(self) -> dict[str, list[Option]]:
        """Enum dei DTO + tabelle Diku Modificato (vedi docstring del modulo)."""
        out: dict[str, list[Option]] = {
            "sectorType": _options(SectorType), "direction": _options(Direction), "doorFlag": _options(DoorFlag),
            "zoneResetMode": _options(ZoneResetMode), "sex": _options(Sex), "objectType": _options(ObjectType),
            "zoneCommandType": DIKUMOD_COMMANDS,
        }  # fmt: skip
        for key, table in DIKUMOD_FLAG_TABLES.items():
            bits = T.ZONE_RESET_BITS if not table else T.FLAG_TABLES[table]
            out[key] = [Option(value=bit, label=name) for name, bit in bits.items()]
        for key, names in DIKUMOD_TYPE_TABLES.items():
            out[key] = [Option(value=i, label=name) for i, name in enumerate(names)]
        return out

    async def races(self) -> list[ContentRef]:
        """Le razze di `race.h` (id = nome minuscolo, quello che l'API scrive nel campo `raceId` dei mob)."""
        return [ContentRef(id=n, name=n.replace("_", " ").capitalize()) for n in T.RACES]

    async def classes(self) -> list[ContentRef]:
        """Diku Modificato non ha classi per i mob (solo i bit `act` di classe): lista vuota."""
        return []
