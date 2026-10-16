"""Descrizione delle chiavi di `extra` e dei campi non supportati di BasedMud (per `describe()`).

Ogni tabella va tenuta allineata a cio' che `mapping.py` emette in `extra`: lo verifica `tests/basedmud/test_describe.py`.
"""

from __future__ import annotations

from pachimudeditor.sdk import ExtraFieldDescriptor, ResourceType
from pachimudeditor.sdk import xf

FLAG_LISTS: dict[tuple[str, str], str] = {
    ("room", "flags"): "romRoomFlags",
    ("mob", "flags"): "romMobFlags",
    ("object", "extraFlags"): "romExtraFlags",
    ("object", "wearFlags"): "romWearFlags",
}
"""(risorsa, campo) -> lista in `enums()` da cui prendere i nomi dei flag."""

UNSUPPORTED: dict[str, frozenset[str]] = {
    "zone": frozenset({"lifespanMinutes", "resetMode"}),
    "mob": frozenset({"experience", "classId", "debuffSkillId", "shopId", "questIds", "isBanker", "teachesClassIds", "teachesSkillIds"}),
    "object": frozenset({"rent", "actionDescription"}),
    "reset_command": frozenset({"ifValue", "comment"}),
}
"""Risorsa -> campi del DTO che ROM non ha (valore neutro in lettura, solo il neutro in scrittura)."""

EXTRA: dict[ResourceType, list[ExtraFieldDescriptor]] = {
    "zone": [xf("file"), xf("style"), xf("vnumRaw", ro=True), xf("credits"), xf("security", "number")],
    "room": [xf("sector", "select", "romSectorType")],
    "mob": [
        xf("affectedBy", "flags", "romAffectFlags"), xf("offFlags", "flags", "romOffFlags"),
        xf("immFlags", "flags", "romResFlags"), xf("resFlags", "flags", "romResFlags"),
        xf("vulnFlags", "flags", "romResFlags"), xf("form", "flags", "romFormFlags"), xf("parts", "flags", "romPartFlags"),
        xf("size", "enum", "romSize"), xf("material"), xf("startPos", "enum", "romPosition"),
        xf("defaultPos", "enum", "romPosition"), xf("group", "number"), xf("damType"), xf("mana"), xf("ac", "json"),
        xf("flagRemovals", "json"), xf("mprogs", "json"), xf("shop", "json"), xf("special", nullable=True),
    ],
    "object": [
        xf("itemType", "enum", "romItemType"), xf("values", "json"), xf("level", "number"), xf("material"),
        xf("condition", "number"), xf("flagAffects", "json"), xf("extraDescs", "json"),
    ],
}  # fmt: skip
"""Risorsa -> chiavi di `extra` emesse."""
