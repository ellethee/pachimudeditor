"""Trova quali comandi di reset di zona referenziano un dato vnum di stanza/mob/oggetto.

`zone_reset_command.arg1`..`arg4` sono interi liberi (vnum), senza FK: cancellare una stanza/
un mob/un oggetto ancora referenziato da un reset lascerebbe quel reset a puntare a un vnum
morto senza che nulla lo segnali. Questo modulo cerca quei riferimenti prima di una delete
(o su richiesta esplicita) così l'editor può bloccarla con un messaggio chiaro.

Per gli oggetti conta anche `exit.key_vnum` (la chiave di una porta): in quel caso l'uso ha
`source == "exit_key"`, `exit_id`/`room_id`/`room_vnum` valorizzati e i campi del reset nulli.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.schema import models_of
from pachimudeditor.common.adapters.models import EntityKind as Kind
from pachimudeditor.common.adapters.models import ResetUsage
from pachimudeditor.sdk import rules
from pachimudeditor.common.enums import ZoneCommandType


async def find_reset_usage(session: AsyncSession, kind: Kind, vnum: int, *, include_exit_keys: bool = True) -> list[ResetUsage]:
    """Ogni comando di reset (di qualsiasi zona) che referenzia `vnum` come `kind`; per gli
    oggetti anche le uscite che lo usano come chiave (`include_exit_keys`)."""
    m = models_of(session)
    Zone, ZoneResetCommand, Exit, Room = m.Zone, m.ZoneResetCommand, m.Exit, m.Room  # noqa: N806
    fields = rules.USAGE_FIELDS[kind]
    fields_by_type: dict[ZoneCommandType, list[str]] = {}
    for command_type, field in fields:
        fields_by_type.setdefault(command_type, []).append(field)

    rows = (
        await session.execute(
            select(ZoneResetCommand, Zone.name)
            .join(Zone, Zone.id == ZoneResetCommand.zone_id)
            .where(ZoneResetCommand.command_type.in_(fields_by_type))
        )
    ).all()

    usage: list[ResetUsage] = []
    for command, zone_name in rows:
        if any(getattr(command, field) == vnum for field in fields_by_type[command.command_type]):
            usage.append(
                ResetUsage(
                    zone_id=command.zone_id,
                    zone_name=zone_name,
                    reset_command_id=command.id,
                    order_index=command.order_index,
                    command_type=command.command_type,
                )
            )
    if kind == "object" and include_exit_keys:
        key_rows = (
            await session.execute(
                select(Exit.id, Exit.room_id, Room.vnum, Room.zone_id, Zone.name)
                .join(Room, Room.id == Exit.room_id)
                .join(Zone, Zone.id == Room.zone_id)
                .where(Exit.key_vnum == vnum)
            )
        ).all()
        usage.extend(
            ResetUsage(
                zone_id=zone_id,
                zone_name=zone_name,
                source="exit_key",
                exit_id=exit_id,
                room_id=room_id,
                room_vnum=room_vnum,
            )
            for exit_id, room_id, room_vnum, zone_id, zone_name in key_rows
        )
    return usage


async def ensure_not_used_by_resets(session: AsyncSession, kind: Kind, vnum: int, *, code: str) -> None:
    """409 con il codice `code` (parametri `count`, `zones`) se un *comando di reset* referenzia ancora `vnum`."""
    await _ensure_unused(session, kind, vnum, code=code, include_exit_keys=False)


async def ensure_not_used(session: AsyncSession, kind: Kind, vnum: int, *, code: str) -> None:
    """Come `ensure_not_used_by_resets` ma considera anche le chiavi delle uscite (oggetti)."""
    await _ensure_unused(session, kind, vnum, code=code, include_exit_keys=True)


async def _ensure_unused(session: AsyncSession, kind: Kind, vnum: int, *, code: str, include_exit_keys: bool) -> None:
    """409 `code` (parametri `count`, `zones`) se `find_reset_usage` non e' vuoto."""
    rules.raise_if_used(await find_reset_usage(session, kind, vnum, include_exit_keys=include_exit_keys), code)
