"""Campi `extra` "semplici" aggiunti dal gioco (Clessidra, F10): una tabella (chiave di `extra` -> chiave del file, default) per zone, stanze, mob e oggetti.

Lettura (`out`) e scrittura (`apply`/`values`) sono guidate dalla stessa tabella; la validazione finale e' quella dei loader (`loaders.py`).
`spec` si valida contro il catalogo del gioco (`schemas/specs.json`).
"""

import json
from functools import cache
from pathlib import Path
from typing import Any

from pachifast.i18n import api_error

SPECS_FILE = Path(__file__).with_name("schemas") / "specs.json"
"""Copia di `json-schema/specs.json` del gioco (`pachimud json-schema`)."""

TABLE: dict[str, dict[str, tuple[str, Any]]] = {
    "zone": {"email": ("email", ""), "difficulty": ("difficulty", ""), "civilized": ("civilized", False)},
    "room": {"spec": ("spec", None), "current": ("current", None), "teleport": ("teleport", None)},
    "mob": {
        "mobPosition": ("position", "STANDING"),
        "clanId": ("clan_id", None),
        "noise": ("noise", None),
        "permAffects": ("affects", []),
        "immunities": ("immunity", []),
        "resistances": ("resistance", []),
        "vulnerabilities": ("vulnerability", []),
        "spec": ("spec", None),
    },
    "object": {
        "durability": ("durability", -1),
        "minLevel": ("min_level", None),
        "maxLevel": ("max_level", None),
        "objectSex": ("sex", "NEUTRAL"),
        "objectMaterial": ("material", None),
        "spec": ("spec", None),
    },
}
"""Risorsa -> {chiave di `extra`: (chiave del file, valore di default che il file omette)}."""


@cache
def specs() -> dict[str, list[dict[str, Any]]]:
    """Il catalogo delle spec_proc: `{mob|object|room: [{name, status, requires, description{it,en}, ...}]}`."""
    return json.loads(SPECS_FILE.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def keys(kind: str) -> frozenset[str]:
    """Le chiavi di `extra` di una risorsa gestite da questa tabella."""
    return frozenset(TABLE[kind])


def _clean(kind: str, key: str, value: Any, default: Any) -> Any:
    """Il valore da scrivere: vuoto -> `None` (chiave tolta) per i campi senza default; `spec` validata sul catalogo (422 `pachimud.invalid_choice`)."""
    if default is None and value in ("", None):
        return None
    if isinstance(default, list):
        return [str(v) for v in value or []]
    if key == "spec" and value not in {s["name"] for s in specs()[kind]}:
        raise api_error(422, "pachimud.invalid_choice", field="extra.spec", limit=", ".join(s["name"] for s in specs()[kind]))
    return value


def out(kind: str, model: Any) -> dict[str, Any]:
    """I valori di `extra` letti dal modello del loader."""
    result: dict[str, Any] = {}
    for key, (name, _default) in TABLE[kind].items():
        value = getattr(model, name)
        result[key] = (
            value.model_dump(exclude_none=True) if hasattr(value, "model_dump") else list(value) if isinstance(value, list) else value
        )
    return result


def apply(kind: str, raw: Any, extra: dict[str, Any]) -> None:
    """Scrive in `raw` (la voce del file, modifica selettiva) i campi presenti in `extra`."""
    from pachimudeditor_adapter_pachimud.mapping import put

    for key, (name, default) in TABLE[kind].items():
        if key in extra:
            put(raw, name, _clean(kind, key, extra[key], default), default=default)


def values(kind: str, extra: dict[str, Any]) -> dict[str, Any]:
    """I campi di `extra` come `{chiave del file: valore}` per un documento nuovo (i default non si scrivono)."""
    result: dict[str, Any] = {}
    for key, (name, default) in TABLE[kind].items():
        if key in extra:
            value = _clean(kind, key, extra[key], default)
            if value is not None and value != default:
                result[name] = value
    return result
