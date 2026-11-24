"""Descrizione delle chiavi di `extra` e dei campi derivati di pachimud (per `describe()`).

Ogni tabella va tenuta allineata a cio' che `mapping.py` emette in `extra`: lo verifica `tests/test_describe.py`.
"""

from __future__ import annotations

from pachimudeditor.sdk import ExtraFieldDescriptor, ResourceType, xf

FLAG_LISTS: dict[tuple[str, str], str] = {
    ("room", "flags"): "pachimudRoomFlags",
    ("mob", "flags"): "pachimudMobFlags",
    ("object", "extraFlags"): "pachimudObjectExtraFlags",
    ("object", "wearFlags"): "pachimudObjectWearFlags",
}
"""(risorsa, campo) -> lista in `enums()` (dal catalogo `flags.json`) da cui prendere i nomi dei flag; nel file restano stringhe, anche sconosciute."""

UNSUPPORTED: dict[str, frozenset[str]] = {"zone": frozenset({"minLevel"})}
"""Risorsa -> campi del DTO che il gioco non ha (valore neutro in lettura, solo il neutro in scrittura): `Zone.min_level` e' stato tolto."""

READ_ONLY: dict[str, frozenset[str]] = {"object": frozenset({"value0", "value1", "value2", "value3"})}
"""Campi del DTO derivati da altri (i `value_N` degli oggetti: si modifica `extra.typeFields`)."""

EXTRA: dict[ResourceType, list[ExtraFieldDescriptor]] = {
    "zone": [
        xf("zoneId"), xf("description", "text"), xf("folder", ro=True), xf("climate", "enum", "climate"), xf("prototypesOnly", "boolean"),
        xf("extendsZone", "number", nullable=True),
    ],
    "room": [xf("enabled", "boolean"), xf("area"), xf("climate", "enum", "climate", nullable=True)],
    "mob": [
        xf("area"), xf("name"), xf("attacks", "number"), xf("persona", "text"), xf("strength", "number"), xf("dexterity", "number"), xf("constitution", "number"),
        xf("intelligence", "number"), xf("wisdom", "number"), xf("charisma", "number"),
        xf("postmaster", "boolean"), xf("receptionist", "boolean"), xf("weaponImmunity", "number", nullable=True),
        xf("breath", "flags"), xf("breathCost", "number"), xf("shop", "json"), xf("triggers", "json"),
    ],
    "object": [xf("area"), xf("extraDescriptions", "json"), xf("typeFields", "json")],
    "exit": [xf("isMale", "boolean"), xf("openCmd", "enum", "openCmd", nullable=True), xf("climb", "boolean")],
}  # fmt: skip
"""Risorsa -> chiavi di `extra` emesse."""
