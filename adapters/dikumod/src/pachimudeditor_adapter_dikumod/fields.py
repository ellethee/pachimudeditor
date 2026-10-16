"""Descrizione delle chiavi di `extra` e dei campi non supportati di Diku Modificato (per `describe()`).

Ogni tabella va tenuta allineata a cio' che `mapping.py` emette in `extra`: lo verifica `tests/dikumod/test_describe.py`.
"""

from __future__ import annotations

from pachimudeditor.sdk import ExtraFieldDescriptor, ResourceType
from pachimudeditor.sdk import diagnostic, xf

FLAG_LISTS: dict[tuple[str, str], str] = {
    ("room", "flags"): "dikumodRoomFlags",
    ("mob", "flags"): "dikumodActFlags",
    ("object", "extraFlags"): "dikumodExtraFlags",
    ("object", "wearFlags"): "dikumodWearFlags",
    ("room", "sectorType"): "sectorType",
}
"""(risorsa, campo) -> lista in `enums()` da cui prendere le opzioni."""

UNSUPPORTED: dict[str, frozenset[str]] = {
    "zone": frozenset({"builder", "minLevel", "maxLevel", "enabled"}),
    "room": frozenset({"healRate", "manaRate", "clanId", "owner"}),
    "mob": frozenset({"classId", "debuffSkillId", "shopId", "questIds", "isBanker", "teachesClassIds", "teachesSkillIds"}),
}
"""Risorsa -> campi del DTO che Diku Modificato non ha (valore neutro in lettura, solo il neutro in scrittura)."""

EXTRA: dict[ResourceType, list[ExtraFieldDescriptor]] = {
    "zone": [
        xf("numRaw", "number"),
        xf("resetModeRaw", "number"),
        xf("index", "number", ro=True),
        xf("topRaw", "number", ro=True),
        xf("hasEnd", "boolean", ro=True),
        xf("override", "text", ro=True, nullable=True),
        *diagnostic("corrupted", "warning", "line", "raw"),
    ],
    "room": [
        xf("sector", "select", "dikumodSector"),
        xf("tele", "json"),
        xf("river", "json"),
        xf("moblim", "number", nullable=True),
        xf("light", "json"),
        xf("zoneIgnored", "number"),
        xf("source", "text", ro=True),
        *diagnostic("warning"),
    ],
    "exit": [xf("exitInfo", "number"), xf("openCmd", "number", ro=True, nullable=True), xf("dState", "number", ro=True, nullable=True)],
    "mob": [
        xf("kind", "enum", "dikumodMobKind"),
        xf("multiAttack", "number", nullable=True),
        xf("affectedBy", "flags", "dikumodAffectFlags"),
        xf("position", "select", "dikumodPosition"),
        xf("defaultPos", "select", "dikumodPosition"),
        xf("sexCode", "number", ro=True),
        xf("immune", "flags", "dikumodImmuneFlags"),
        xf("mImmune", "flags", "dikumodImmuneFlags"),
        xf("susc", "flags", "dikumodImmuneFlags"),
        xf("sound", "text", nullable=True),
        xf("distantSound", "text", nullable=True),
        xf("expRaw", "number"),
        xf("shop", "json"),
        xf("script", "json"),
        xf("trailing", "text", ro=True),
        *diagnostic("corrupted", "warning", "line", "raw"),
    ],
    "object": [
        xf("typeRaw", "select", "dikumodItemType"),
        xf("affects", "json"),
        xf("extraDescs", "json"),
        xf("forbiddenWear", "json"),
        xf("source", "text", ro=True),
        *diagnostic("warning"),
    ],
    "reset_command": [xf("letter", "text", ro=True), xf("missingArg4", "boolean", ro=True)],
}
"""Risorsa -> chiavi di `extra` emesse (le diagnostiche compaiono solo quando c'e' il problema)."""
