"""Utilita' sui DTO neutri (`common.adapters.models`) condivise da schema (controlli al caricamento) e motore."""

from enum import Enum
from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

from pachimudeditor.common.adapters.models import (
    ExitOut,
    ExtraDescriptionOut,
    MobOut,
    ObjectOut,
    RoomOut,
    ZoneOut,
)

DTO_OUT: dict[str, type[BaseModel]] = {
    "zone": ZoneOut,
    "room": RoomOut,
    "mob": MobOut,
    "object": ObjectOut,
    "exit": ExitOut,
    "extra_description": ExtraDescriptionOut,
}
"""Sezione del modello -> DTO in uscita i cui campi la mappatura descrive."""


def annotation_of(annotation: Any) -> tuple[Any, bool]:
    """`(tipo senza None, nullable)` per un'annotazione `X | None`."""
    if get_origin(annotation) in (Union, UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        return (args[0] if len(args) == 1 else annotation), len(args) != len(get_args(annotation))
    return annotation, False


def enum_of(annotation: Any) -> type[Enum] | None:
    """La classe `Enum` di un'annotazione (anche `X | None`)."""
    for arg in getattr(annotation, "__args__", (annotation,)):
        if isinstance(arg, type) and issubclass(arg, Enum):
            return arg
    return None


def neutral_default(annotation: Any, nullable: bool) -> Any:
    """Valore neutro di un campo del DTO per cui il MUD non ha un equivalente."""
    if nullable:
        return None
    origin = getattr(annotation, "__origin__", annotation)
    if origin is list:
        return []
    if origin is dict:
        return {}
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return next(iter(annotation))
    return {bool: False, int: 0, float: 0.0, str: ""}.get(annotation, None)
