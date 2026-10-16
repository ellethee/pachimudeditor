"""Hook registrati in codice, richiamabili per nome dal file di mappatura (che non importa mai codice).

Tre famiglie:

- `field`: `FieldHook(read, write)` per un campo del DTO che la mappatura dichiarativa non sa esprimere
  (`read(fields) -> valore`, `write(fields, valore) -> None`, `fields` e' il dict del record);
- `record`: `RecordHook(parse, write)` che sostituisce parsing e scrittura dei `steps` di un record
  (`parse(cursor) -> dict | None`, `None` = terminatore; `write(fields) -> str`);
- `zone_range`: `(lista_campi_zone) -> [(bottom, top)]`, un range per zona nell'ordine dato.

La mappatura deve dichiarare ogni hook usato nella lista `hooks:`.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Fields = dict[str, Any]


@dataclass(frozen=True)
class FieldHook:
    """Lettura/scrittura di un campo del DTO su un record."""

    read: Callable[[Fields], Any]
    write: Callable[[Fields, Any], None]


@dataclass(frozen=True)
class RecordHook:
    """Parsing e scrittura personalizzati di un tipo di record."""

    parse: Callable[[Any], Fields | None]
    write: Callable[[Fields], str]


_FIELD: dict[str, FieldHook] = {}
_RECORD: dict[str, RecordHook] = {}
_ZONE_RANGE: dict[str, Callable[[list[Fields]], list[tuple[int, int]]]] = {}


def register_field_hook(name: str, read: Callable[[Fields], Any], write: Callable[[Fields, Any], None]) -> None:
    """Registra un hook di campo."""
    _FIELD[name] = FieldHook(read, write)


def register_record_hook(name: str, parse: Callable[[Any], Fields | None], write: Callable[[Fields], str]) -> None:
    """Registra un hook di record."""
    _RECORD[name] = RecordHook(parse, write)


def register_zone_range_hook(name: str, fn: Callable[[list[Fields]], list[tuple[int, int]]]) -> None:
    """Registra un hook per il range delle zone."""
    _ZONE_RANGE[name] = fn


def registered(family: str) -> list[str]:
    """Nomi registrati per la famiglia `field`, `record` o `zone_range`."""
    return sorted({"field": _FIELD, "record": _RECORD, "zone_range": _ZONE_RANGE}[family])


def field_hook(name: str) -> FieldHook:
    """L'hook di campo `name`."""
    return _FIELD[name]


def record_hook(name: str) -> RecordHook:
    """L'hook di record `name`."""
    return _RECORD[name]


def zone_range_hook(name: str) -> Callable[[list[Fields]], list[tuple[int, int]]]:
    """L'hook di range `name`."""
    return _ZONE_RANGE[name]


# --------------------------------------------------------------------------- hook inclusi


def zone_from_top(zones: list[Fields]) -> list[tuple[int, int]]:
    """Range "a catena" dei Diku classici: ogni zona finisce a `top` e inizia dopo il `top` della precedente.

    Ogni zona e' un dict con (almeno) `top`; la prima parte da 0.
    """
    out: list[tuple[int, int]] = []
    previous = -1
    for zone in zones:
        top = int(zone.get("top") or 0)
        out.append((previous + 1, top))
        previous = top
    return out


_LEVELS = re.compile(r"^\s*\{\s*(\d+)\s+(\d+)\s*\}")
_BRACES = re.compile(r"^\s*\{[^}]*\}")
MAX_LEVEL = 60


def _credits(credits: str) -> tuple[int, int, str]:
    """`(livello_min, livello_max, autore)` dai credits ROM `{ 5 35 } Autore  Titolo` (assenti: 1..60)."""
    credits = credits or ""
    match = _LEVELS.match(credits)
    low, high = (int(match.group(1)), int(match.group(2))) if match else (1, MAX_LEVEL)
    rest = _BRACES.sub("", credits, count=1).strip()
    return low, high, rest.split()[0] if rest else ""


def _with_levels(credits: str, low: int, high: int, author: str | None = None) -> str:
    """I credits con il blocco `{ low high }` sostituito e, se dato, l'autore (prima parola) cambiato."""
    rest = _BRACES.sub("", credits or "", count=1).strip()
    if author is not None:
        words = rest.split(None, 1)
        rest = " ".join([author, *words[1:]]) if words else author
    return f"{{ {low} {high} }} {rest}".rstrip()


def _write_min_level(fields: Fields, value: int) -> None:
    """Imposta il livello minimo nei credits."""
    _, high, _ = _credits(fields.get("credits", ""))
    fields["credits"] = _with_levels(fields.get("credits", ""), value, high)


def _write_max_level(fields: Fields, value: int) -> None:
    """Imposta il livello massimo nei credits."""
    low, _, _ = _credits(fields.get("credits", ""))
    fields["credits"] = _with_levels(fields.get("credits", ""), low, value)


def _read_builder(fields: Fields) -> str:
    """`Builders` (stile `#AREADATA`) oppure l'autore nei credits."""
    return (fields.get("builders") or "").strip() or _credits(fields.get("credits", ""))[2]


def _write_builder(fields: Fields, value: str) -> None:
    """Scrive `Builders` se l'intestazione lo ha (`#AREADATA`), altrimenti l'autore nei credits (`#AREA`)."""
    if "builders" in fields:
        fields["builders"] = value
    else:
        low, high, _ = _credits(fields.get("credits", ""))
        fields["credits"] = _with_levels(fields.get("credits", ""), low, high, value)


register_zone_range_hook("zone_from_top", zone_from_top)
register_field_hook("rom_credits_min_level", lambda f: _credits(f.get("credits", ""))[0], _write_min_level)
register_field_hook("rom_credits_max_level", lambda f: max(_credits(f.get("credits", ""))[:2]), _write_max_level)
register_field_hook("rom_credits_builder", _read_builder, _write_builder)
