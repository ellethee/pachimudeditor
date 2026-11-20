"""Descrizione delle chiavi di `extra` e dei campi derivati di pachimud (per `describe()`).

Ogni tabella va tenuta allineata a cio' che `mapping.py` emette in `extra`: lo verifica `tests/test_describe.py`.
"""

from __future__ import annotations

from pachimudeditor.sdk import ExtraFieldDescriptor, ResourceType, xf

FLAG_LISTS: dict[tuple[str, str], str] = {}
"""(risorsa, campo) -> lista in `enums()` da cui prendere i nomi dei flag (nel gioco sono stringhe libere MAIUSCOLE)."""

READ_ONLY: dict[str, frozenset[str]] = {"object": frozenset({"value0", "value1", "value2", "value3"})}
"""Campi del DTO derivati da altri (i `value_N` degli oggetti: si modifica `extra.typeFields`)."""

EXTRA: dict[ResourceType, list[ExtraFieldDescriptor]] = {
    "zone": [
        xf("zoneId"), xf("description", "text"), xf("folder", ro=True), xf("climate", "enum", "climate"), xf("prototypesOnly", "boolean"),
        xf("extendsZone", "number", nullable=True),
    ],
    "room": [xf("enabled", "boolean"), xf("area")],
    "mob": [
        xf("area"), xf("name"), xf("attacks", "number"), xf("persona", "text"), xf("strength", "number"), xf("dexterity", "number"), xf("constitution", "number"),
        xf("intelligence", "number"), xf("wisdom", "number"), xf("charisma", "number"),
        xf("postmaster", "boolean"), xf("receptionist", "boolean"), xf("weaponImmunity", "number", nullable=True),
        xf("breath", "flags"), xf("breathCost", "number"), xf("shop", "json"),
    ],
    "object": [xf("area"), xf("extraDescriptions", "json"), xf("typeFields", "json")],
    "exit": [xf("isMale", "boolean"), xf("openCmd", "enum", "openCmd", nullable=True), xf("climb", "boolean")],
}  # fmt: skip
"""Risorsa -> chiavi di `extra` emesse."""
