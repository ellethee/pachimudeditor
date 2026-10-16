"""Genera i `FieldDescriptor` di una risorsa a partire dai modelli Pydantic (Out/In) dei DTO.

Serve a `WorldAdapter.describe()`: un adapter che usa i DTO standard ottiene la descrizione dei campi
senza scriverla a mano; puo' comunque costruire `FieldDescriptor` esplicitamente.
"""

import types
from enum import Enum
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

from pachimudeditor.common.adapters.base import ExtraFieldDescriptor, ExtraKind, FieldDescriptor, ResourceInfo, ResourceType

ENUM_SOURCES: dict[str, str] = {
    "sector_type": "sectorType",
    "direction": "direction",
    "door_flag": "doorFlag",
    "reset_mode": "zoneResetMode",
    "sex": "sex",
    "object_type": "objectType",
    "command_type": "zoneCommandType",
}
"""Nome Python del campo -> chiave in `GET /api/meta/enums` da cui il form prende le opzioni."""

TEXT_FIELDS: frozenset[str] = frozenset({"description", "long_description", "detailed_description", "action_description", "text"})
"""Campi di testo lungo (textarea)."""


def _unwrap(annotation: Any) -> tuple[Any, bool]:
    """`(tipo senza None, nullable)` per un'annotazione `X | None`."""
    if get_origin(annotation) in (Union, types.UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        nullable = len(args) != len(get_args(annotation))
        if len(args) == 1:
            return args[0], nullable
        enums = [a for a in args if isinstance(a, type) and issubclass(a, Enum)]
        if len(enums) == 1 and all(a is int or a is enums[0] for a in args):
            return enums[0], nullable  # `Enum | int`: enum con valori propri del MUD (vedi `ResetCommandType`)
    return annotation, False


def _field_type(name: str, annotation: Any) -> str:
    """Il tipo di descrittore per un campo."""
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return "enum"
    origin = get_origin(annotation)
    if origin is list:
        return "flags" if name.endswith("flags") else "list"
    if origin is dict or annotation is dict:
        return "dict"
    if annotation is bool:
        return "bool"
    if annotation is int:
        return "int"
    if annotation is float:
        return "number"
    return "text" if name in TEXT_FIELDS else "string"


def describe_resource(
    resource: ResourceType,
    out_model: type[BaseModel],
    in_model: type[BaseModel] | None = None,
    *,
    read_only: frozenset[str] = frozenset({"id"}),
    skip: frozenset[str] = frozenset({"extra"}),
) -> ResourceInfo:
    """Descrittori dei campi di `out_model`; `required` viene da `in_model` (campi senza default)."""
    fields: list[FieldDescriptor] = []
    for name, info in out_model.model_fields.items():
        if name in skip:
            continue
        annotation, nullable = _unwrap(info.annotation)
        required = bool(in_model and name in in_model.model_fields and in_model.model_fields[name].is_required())
        kind = _field_type(name, annotation)
        fields.append(
            FieldDescriptor(
                name=info.alias or name,
                type=kind,  # type: ignore[arg-type]
                required=required,
                read_only=name in read_only or in_model is None or name not in in_model.model_fields,
                enum=ENUM_SOURCES.get(name) if kind == "enum" else None,
                nullable=nullable,
            )
        )
    return ResourceInfo(type=resource, fields=fields)


def xf(
    name: str,
    type: ExtraKind = "text",  # noqa: A002
    enum: str | None = None,
    *,
    ro: bool = False,
    nullable: bool = False,
    group: str | None = None,
) -> ExtraFieldDescriptor:
    """Descrittore (abbreviato) di una chiave di `extra`; l'etichetta e' `extra.labels.<name>`."""
    return ExtraFieldDescriptor(
        name=name, label_key=f"extra.labels.{name}", type=type, enum=enum, read_only=ro, nullable=nullable, group=group
    )


def diagnostic(*names: str) -> list[ExtraFieldDescriptor]:
    """Chiavi di diagnostica (`warning`, `corrupted`, ...): sola lettura, gruppo `diagnostic`."""
    return [xf(n, "boolean" if n == "corrupted" else "number" if n == "line" else "text", ro=True, group="diagnostic") for n in names]


def finish_resource(
    info: ResourceInfo,
    extra_fields: list[ExtraFieldDescriptor] | None = None,
    *,
    enums: dict[str, str] | None = None,
    unsupported: frozenset[str] = frozenset(),
    read_only: frozenset[str] = frozenset(),
    create_at_end: bool = False,
) -> ResourceInfo:
    """Completa una risorsa con i dati del mondo: tabelle dei flag, campi non supportati/derivati, chiavi di `extra`.

    `enums`: nome del campo -> lista di `enums()`; `unsupported`: campi che il mondo non ha (disabilitati);
    `read_only`: campi derivati; il campo `extra` (dict) si aggiunge per zone/stanze/mob/oggetti o se ha chiavi.
    """
    enums = enums or {}
    fields = [
        f.model_copy(
            update={
                "enum": enums.get(f.name, f.enum),
                "unsupported": f.name in unsupported,
                "read_only": f.read_only or f.name in read_only or f.name in unsupported,
            }
        )
        for f in info.fields
    ]
    if extra_fields or info.type in ("zone", "room", "mob", "object"):
        fields.append(FieldDescriptor(name="extra", type="dict"))
    return info.model_copy(update={"fields": fields, "extra_fields": extra_fields or [], "create_at_end": create_at_end})
