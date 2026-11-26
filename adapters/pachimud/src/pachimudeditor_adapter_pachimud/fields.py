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
        xf("extendsZone", "number", nullable=True), xf("email"), xf("difficulty"), xf("civilized", "boolean"),
    ],
    "room": [xf("enabled", "boolean"), xf("area"), xf("climate", "enum", "climate", nullable=True), xf("triggers", "json"),
             xf("spec", "enum", "pachimudRoomSpecs", nullable=True), xf("current", "json"), xf("teleport", "json")],
    "mob": [
        xf("area"), xf("name"), xf("attacks", "number"), xf("persona", "text"), xf("strength", "number"), xf("dexterity", "number"), xf("constitution", "number"),
        xf("intelligence", "number"), xf("wisdom", "number"), xf("charisma", "number"),
        xf("postmaster", "boolean"), xf("receptionist", "boolean"), xf("weaponImmunity", "number", nullable=True),
        xf("breath", "flags"), xf("breathCost", "number"), xf("shop", "json"), xf("triggers", "json"),
        xf("mobPosition", "enum", "mobPosition"), xf("clanId", nullable=True), xf("noise", "json"), xf("permAffects", "flags", "pachimudAffects"),
        xf("immunities", "flags", "pachimudResistance"), xf("resistances", "flags", "pachimudResistance"),
        xf("vulnerabilities", "flags", "pachimudResistance"), xf("spec", "enum", "pachimudMobSpecs", nullable=True),
    ],
    "object": [
        xf("area"), xf("extraDescriptions", "json"), xf("typeFields", "json"), xf("scripts", "json"), xf("durability", "number"),
        xf("minLevel", "number", nullable=True), xf("maxLevel", "number", nullable=True), xf("objectSex", "enum", "pachimudObjectSex"),
        xf("objectMaterial", "enum", "pachimudMaterial", nullable=True), xf("spec", "enum", "pachimudObjectSpecs", nullable=True),
    ],
    "exit": [xf("isMale", "boolean"), xf("openCmd", "enum", "openCmd", nullable=True), xf("climb", "boolean")],
}  # fmt: skip
"""Risorsa -> chiavi di `extra` emesse."""
