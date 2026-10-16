"""Zone e script di reset sul database di pachimud (mixin di `PachimudAdapter`)."""

from typing import Any

from pachifast.i18n import api_error
from pachifast.schemas.responses import PaginatedResponse
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.base import PachimudSupport
from pachimudeditor_adapter_pachimud.schema import models_of, strip_unsupported
from pachimudeditor.sdk import rules
from pachimudeditor.common.adapters.models import (
    EntityKind,
    NextZoneVnum,
    ResetCommandDraft,
    ResetCommandOut,
    ResetDraftScriptIn,
    ResetScriptIn,
    ResetValidation,
    ZoneCloneIn,
    ZoneIn,
    ZoneOut,
    ZonePageParams,
    ZonePatch,
    ZoneSummary,
)
from pachimudeditor_adapter_pachimud.editor import crud
from pachimudeditor.sdk import conflict
from pachimudeditor.common.enums import DoorFlag


class PachimudResetLookup:
    """`rules.ResetLookup` sul database di pachimud."""

    def __init__(self, session: AsyncSession) -> None:
        """Usa la sessione data per le verifiche di esistenza."""
        self.session = session

    async def existing_vnums(self, kind: EntityKind, vnums: set[int]) -> set[int]:
        """Quali tra `vnums` esistono come stanza/mob/oggetto."""
        m = models_of(self.session)
        model = {"room": m.Room, "mob": m.MobPrototype, "object": m.ObjectPrototype}[kind]
        if not vnums:
            return set()
        rows = (await self.session.execute(select(model.vnum).where(model.vnum.in_(vnums)))).scalars().all()  # type: ignore[attr-defined]
        return set(rows)

    async def exit_has_door(self, room_vnum: int, direction: int) -> bool | None:
        """`None` se la stanza non ha l'uscita, altrimenti se ha una porta (`door_flag` != NONE)."""
        m = models_of(self.session)
        row = (
            await self.session.execute(
                select(m.Exit.door_flag)
                .join(m.Room, m.Room.id == m.Exit.room_id)
                .where(m.Room.vnum == room_vnum, m.Exit.direction == int(direction))
            )
        ).first()
        return None if row is None else row[0] != DoorFlag.NONE


async def reset_commands(session: AsyncSession, zone_id: int) -> list[Any]:
    """I reset di una zona in ordine di esecuzione."""
    ZoneResetCommand = models_of(session).ZoneResetCommand  # noqa: N806
    result = await session.execute(
        select(ZoneResetCommand).where(ZoneResetCommand.zone_id == zone_id).order_by(ZoneResetCommand.order_index)
    )
    return list(result.scalars().all())


async def _ensure_zone_vnum_free(session: AsyncSession, vnum: int, *, ignore_id: int | None = None) -> None:
    """409 `zones.vnum_taken` se un'altra zona usa gia' `vnum`."""
    Zone = models_of(session).Zone  # noqa: N806
    existing = (await session.execute(select(Zone).where(Zone.vnum == vnum))).scalars().first()
    if existing is not None and existing.id != ignore_id:
        raise conflict("zones.vnum_taken", vnum=vnum)


async def _count(session: AsyncSession, model: type, zone_id: int) -> int:
    """Numero di righe di `model` (con colonna `zone_id`) appartenenti alla zona."""
    return (
        await session.execute(select(func.count()).select_from(model).where(model.zone_id == zone_id))  # type: ignore[attr-defined]
    ).scalar_one()


async def _summary(session: AsyncSession, zone_id: int) -> ZoneSummary:
    """I conteggi di stanze, mob e oggetti della zona."""
    m = models_of(session)
    return ZoneSummary(
        room_count=await _count(session, m.Room, zone_id),
        mob_count=await _count(session, m.MobPrototype, zone_id),
        object_count=await _count(session, m.ObjectPrototype, zone_id),
    )


class ZonesMixin(PachimudSupport):
    """Operazioni su zone e script di reset."""

    async def list_zones(self, params: ZonePageParams) -> PaginatedResponse[ZoneOut]:
        """Zone paginate, cercabili per nome/builder/vnum; ordine di default per vnum."""
        async with self.session() as session:
            return await self.page(session, models_of(session).Zone, params, ZoneOut)

    async def get_zone(self, zone_id: int) -> ZoneOut:
        """Una zona (404 `zones.not_found`)."""
        async with self.session() as session:
            return ZoneOut.model_validate(await crud.get_or_404(session, models_of(session).Zone, zone_id, code="zones.not_found"))

    async def create_zone(self, data: ZoneIn) -> ZoneOut:
        """Crea una zona (il vnum deve essere libero)."""
        self.ensure_writable()
        values = self.values(data)
        async with self.session() as session:
            await _ensure_zone_vnum_free(session, data.vnum)
            return ZoneOut.model_validate(await crud.create(session, models_of(session).Zone, values))

    async def update_zone(self, zone_id: int, data: ZonePatch) -> ZoneOut:
        """Aggiornamento parziale; i range finali (vnum e livelli) devono restare coerenti anche se il patch
        ne cambia solo un estremo (422 `zones.invalid_vnum_range` / `zones.invalid_level_range`)."""
        self.ensure_writable()
        changes = self.values(data, exclude_unset=True)
        async with self.session() as session:
            Zone = models_of(session).Zone  # noqa: N806
            zone = await crud.get_or_404(session, Zone, zone_id, code="zones.not_found")
            if data.vnum is not None:
                await _ensure_zone_vnum_free(session, data.vnum, ignore_id=zone_id)
            final = {name: changes.get(name, getattr(zone, name)) for name in ("bottom_vnum", "top_vnum", "min_level", "max_level")}
            rules.check_zone_ranges(final["bottom_vnum"], final["top_vnum"], final["min_level"], final["max_level"])
            return ZoneOut.model_validate(await crud.update(session, Zone, zone_id, changes, code="zones.not_found"))

    async def delete_zone(self, zone_id: int) -> None:
        """Elimina una zona: 409 `zones.not_empty` finche' contiene ancora stanze, mob o oggetti."""
        self.ensure_writable()
        async with self.session() as session:
            m = models_of(session)
            await crud.get_or_404(session, m.Zone, zone_id, code="zones.not_found")
            summary = await _summary(session, zone_id)
            if summary.room_count or summary.mob_count or summary.object_count:
                raise conflict(
                    "zones.not_empty",
                    rooms=summary.room_count,
                    mobs=summary.mob_count,
                    objects=summary.object_count,
                )
            # Lo script di reset appartiene alla zona: va via con lei (altrimenti la FK darebbe un 409 generico).
            # Stessa transazione di `crud.delete`: se questa fallisce, il rollback ripristina anche lo script.
            await session.execute(sa_delete(m.ZoneResetCommand).where(m.ZoneResetCommand.zone_id == zone_id))
            await crud.delete(session, m.Zone, zone_id, code="zones.not_found")

    async def zone_summary(self, zone_id: int) -> ZoneSummary:
        """Conteggi del contenuto di una zona."""
        async with self.session() as session:
            await crud.get_or_404(session, models_of(session).Zone, zone_id, code="zones.not_found")
            return await _summary(session, zone_id)

    async def next_zone_vnum(self, span: int) -> NextZoneVnum:
        """Un vnum di zona libero e un range `span` ampio che non tocca nessun'altra zona."""
        async with self.session() as session:
            Zone = models_of(session).Zone  # noqa: N806
            rows = (await session.execute(select(Zone.vnum, Zone.bottom_vnum, Zone.top_vnum))).all()
        vnum, bottom, top = rules.suggest_zone_range(((r.vnum, r.bottom_vnum, r.top_vnum) for r in rows), span)
        return NextZoneVnum(vnum=vnum, bottom_vnum=bottom, top_vnum=top)

    async def next_content_vnum(self, zone_id: int, kind: EntityKind) -> int:
        """Un vnum libero per una nuova stanza/mob/oggetto: uno oltre il piu' alto della zona (o il vnum minimo
        della zona se vuota), saltando i vnum gia' occupati altrove."""
        async with self.session() as session:
            m = models_of(session)
            zone = await crud.get_or_404(session, m.Zone, zone_id, code="zones.not_found")
            model = {"room": m.Room, "mob": m.MobPrototype, "object": m.ObjectPrototype}[kind]
            highest = (
                await session.execute(select(func.max(model.vnum)).where(model.zone_id == zone_id))  # type: ignore[attr-defined]
            ).scalar_one()
            candidate = highest + 1 if highest is not None else zone.bottom_vnum
            taken = set(
                (await session.execute(select(model.vnum).where(model.vnum >= candidate))).scalars().all()  # type: ignore[attr-defined]
            )
            return rules.first_free_vnum(candidate, taken)

    async def clone_zone(self, zone_id: int, data: ZoneCloneIn) -> ZoneOut:
        """Duplica una zona (non il contenuto); opzionalmente copia lo script di reset (i vnum restano quelli
        originali). Range della copia da `bottomVnum`/`topVnum` (409 `zones.range_overlap`) oppure 0-0."""
        self.ensure_writable()
        async with self.session() as session:
            Zone = models_of(session).Zone  # noqa: N806
            ZoneResetCommand = models_of(session).ZoneResetCommand  # noqa: N806
            source = await crud.get_or_404(session, Zone, zone_id, code="zones.not_found")
            await _ensure_zone_vnum_free(session, data.vnum)
            bottom, top = data.bottom_vnum or 0, data.top_vnum or 0
            if data.bottom_vnum is not None and (bottom, top) != (0, 0):
                others = (await session.execute(select(Zone))).scalars()
                clash = rules.range_clash(((z.name, z.vnum, z.bottom_vnum, z.top_vnum) for z in others), bottom, top)
                if clash is not None:
                    raise conflict("zones.range_overlap", zone=clash[0], zone_vnum=clash[1])
            clone = Zone(
                vnum=data.vnum,
                name=data.name,
                builder=source.builder,
                bottom_vnum=bottom,
                top_vnum=top,
                min_level=source.min_level,
                max_level=source.max_level,
                lifespan_minutes=source.lifespan_minutes,
                reset_mode=source.reset_mode,
                enabled=source.enabled,
            )
            session.add(clone)
            await session.flush()
            if data.copy_reset_commands:
                for command in await reset_commands(session, zone_id):
                    session.add(
                        ZoneResetCommand(
                            zone_id=clone.id,
                            order_index=command.order_index,
                            command_type=command.command_type,
                            if_flag=command.if_flag,
                            arg1=command.arg1,
                            arg2=command.arg2,
                            arg3=command.arg3,
                            arg4=command.arg4,
                            arg_str=command.arg_str,
                        )
                    )
            await session.commit()
            await session.refresh(clone)
            return ZoneOut.model_validate(clone)

    async def list_reset_commands(self, zone_id: int) -> list[ResetCommandOut]:
        """Lo script di reset della zona, in ordine."""
        async with self.session() as session:
            await crud.get_or_404(session, models_of(session).Zone, zone_id, code="zones.not_found")
            return [ResetCommandOut.model_validate(c) for c in await reset_commands(session, zone_id)]

    async def replace_reset_commands(self, zone_id: int, data: ResetScriptIn) -> list[ResetCommandOut]:
        """Sostituisce l'intero script rinumerando `orderIndex` 0..n-1; vnum inesistenti = 422 `zones.reset_unknown_*`."""
        self.ensure_writable()
        async with self.session() as session:
            ZoneResetCommand = models_of(session).ZoneResetCommand  # noqa: N806
            await crud.get_or_404(session, models_of(session).Zone, zone_id, code="zones.not_found")
            for index, c in enumerate(data.commands):
                if c.extra or c.comment is not None or c.if_value is not None or c.command_type in rules.EXTENDED_TYPES:
                    raise api_error(422, "world.extra_unsupported", loc=("body", "commands", index))
            drafts = [ResetCommandDraft.model_validate(c.model_dump(by_alias=False)) for c in data.commands]
            rules.raise_script_errors(await rules.validate_script(PachimudResetLookup(session), drafts))
            await session.execute(sa_delete(ZoneResetCommand).where(ZoneResetCommand.zone_id == zone_id))
            for index, command in enumerate(data.commands):
                values = strip_unsupported(ZoneResetCommand, command.model_dump(by_alias=False, exclude={"if_value", "comment", "extra"}))
                session.add(ZoneResetCommand(zone_id=zone_id, order_index=index, **values))
            await session.commit()
            return [ResetCommandOut.model_validate(c) for c in await reset_commands(session, zone_id)]

    async def validate_reset_commands(self, zone_id: int, data: ResetDraftScriptIn) -> ResetValidation:
        """Controlla uno script senza salvarlo (errori e avvertimenti per passo)."""
        async with self.session() as session:
            await crud.get_or_404(session, models_of(session).Zone, zone_id, code="zones.not_found")
            issues = rules.to_issues(await rules.validate_script(PachimudResetLookup(session), data.commands))
        return ResetValidation(ok=not any(i.severity == "error" for i in issues), issues=issues)
