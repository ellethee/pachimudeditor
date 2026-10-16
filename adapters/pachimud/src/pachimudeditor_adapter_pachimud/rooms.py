"""Stanze, uscite ed extra description sul database di pachimud (mixin di `PachimudAdapter`)."""

from typing import Any

from pachifast.i18n import api_error
from pachifast.schemas.responses import PaginatedResponse
from sqlalchemy import delete as sa_delete
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.base import PachimudSupport
from pachimudeditor_adapter_pachimud.schema import models_of
from pachimudeditor.sdk import rules
from pachimudeditor.common.adapters.models import (
    ExitIn,
    ExitOut,
    ExitPatch,
    ExtraDescriptionIn,
    ExtraDescriptionOut,
    ExtraDescriptionPatch,
    ResetUsage,
    RoomCloneIn,
    RoomDetail,
    RoomGraph,
    RoomIn,
    RoomOut,
    RoomPageParams,
    RoomPatch,
)
from pachimudeditor_adapter_pachimud.editor import crud
from pachimudeditor.sdk import conflict
from pachimudeditor_adapter_pachimud.editor.instances import ensure_room_has_no_occupants
from pachimudeditor_adapter_pachimud.editor.reset_usage import ensure_not_used, ensure_not_used_by_resets, find_reset_usage
from pachimudeditor.common.enums import Direction, DoorFlag, SectorType


async def _ensure_room_vnum_free(session: AsyncSession, vnum: int, *, ignore_id: int | None = None) -> None:
    """409 `rooms.vnum_taken` se un'altra stanza usa già `vnum`."""
    Room = models_of(session).Room  # noqa: N806
    existing = (await session.execute(select(Room).where(Room.vnum == vnum))).scalars().first()
    if existing is not None and existing.id != ignore_id:
        raise conflict("rooms.vnum_taken", vnum=vnum)


async def _exit_out_one(session: AsyncSession, exit_row: Any) -> ExitOut:
    """Un'uscita, con vnum/nome della destinazione risolti quando presente."""
    m = models_of(session)
    target = await session.get(m.Room, exit_row.target_room_id) if exit_row.target_room_id else None
    return ExitOut.model_validate(
        {
            **{c.name: getattr(exit_row, c.name) for c in m.Exit.__table__.c},
            "target_room_vnum": target.vnum if target else None,
            "target_room_name": target.name if target else None,
        }
    )


async def _exits_out(session: AsyncSession, room_id: int) -> list[ExitOut]:
    """Le uscite di una stanza, con vnum/nome della destinazione risolti."""
    Exit = models_of(session).Exit  # noqa: N806
    exits = (await session.execute(select(Exit).where(Exit.room_id == room_id))).scalars().all()
    return [await _exit_out_one(session, exit_row) for exit_row in exits]


async def _extras(session: AsyncSession, room_id: int) -> list[Any]:
    """Le extra description della stanza (nessuna se la tabella non esiste nel DB)."""
    Extra = models_of(session).RoomExtraDescription  # noqa: N806
    if Extra is None:
        return []
    return list((await session.execute(select(Extra).where(Extra.room_id == room_id))).scalars().all())


async def _room_detail(session: AsyncSession, room: Any) -> RoomDetail:
    """Una stanza completa di uscite ed extra description."""
    extra_descriptions = await _extras(session, room.id)
    return RoomDetail(
        **RoomOut.model_validate(room).model_dump(by_alias=False),
        exits=await _exits_out(session, room.id),
        extra_descriptions=[ExtraDescriptionOut.model_validate(e) for e in extra_descriptions],
    )


async def _check_exit(session: AsyncSession, room_id: int, final: dict[str, object], touched: set[str]) -> None:
    """Coerenza di un'uscita (regole in `rules.check_exit`; la chiave deve esistere come oggetto)."""

    async def key_exists(vnum: int) -> bool:
        """Esiste un oggetto con quel vnum?"""
        ObjectPrototype = models_of(session).ObjectPrototype  # noqa: N806
        return (await session.execute(select(ObjectPrototype.id).where(ObjectPrototype.vnum == vnum))).first() is not None

    await rules.check_exit(room_id, final, touched, key_exists)


class RoomsMixin(PachimudSupport):
    """Operazioni su stanze, uscite ed extra description."""

    @staticmethod
    def _extra_model(session: AsyncSession) -> Any:
        """La classe delle extra description (409 `world.capability_missing` se il DB non ha la tabella)."""
        model = models_of(session).RoomExtraDescription
        if model is None:
            raise api_error(409, "world.capability_missing", capability="supports_extra_descriptions")
        return model

    async def list_rooms(self, params: RoomPageParams) -> PaginatedResponse[RoomOut]:
        """Stanze paginate, filtrabili per zona (`zoneId`), cercabili per nome/vnum; ordine di default per vnum."""
        async with self.session() as session:
            return await self.page(session, models_of(session).Room, params, RoomOut)

    async def get_room(self, room_id: int) -> RoomDetail:
        """Una stanza, con uscite ed extra description."""
        async with self.session() as session:
            room = await crud.get_or_404(session, models_of(session).Room, room_id, code="rooms.not_found")
            return await _room_detail(session, room)

    async def create_room(self, data: RoomIn) -> RoomDetail:
        """Crea una stanza (il vnum deve essere libero)."""
        self.ensure_writable()
        values = self.values(data)
        async with self.session() as session:
            await _ensure_room_vnum_free(session, data.vnum)
            room = await crud.create(session, models_of(session).Room, values)
            return await _room_detail(session, room)

    async def update_room(self, room_id: int, data: RoomPatch) -> RoomDetail:
        """Aggiornamento parziale. Cambiare il vnum e' rifiutato (409 `rooms.vnum_in_use`) finche' un reset lo usa."""
        self.ensure_writable()
        changes = self.values(data, exclude_unset=True)
        async with self.session() as session:
            Room = models_of(session).Room  # noqa: N806
            current = await crud.get_or_404(session, Room, room_id, code="rooms.not_found")
            if data.vnum is not None:
                await _ensure_room_vnum_free(session, data.vnum, ignore_id=room_id)
                if data.vnum != current.vnum:
                    await ensure_not_used(session, "room", current.vnum, code="rooms.vnum_in_use")
            room = await crud.update(session, Room, room_id, changes, code="rooms.not_found")
            return await _room_detail(session, room)

    async def delete_room(self, room_id: int) -> None:
        """Elimina stanza, uscite ed extra description (le uscite altrui verso di lei restano senza destinazione).
        409 `rooms.in_reset_usage` se un reset la referenzia, `rooms.has_instances` se ha occupanti."""
        self.ensure_writable()
        async with self.session() as session:
            m = models_of(session)
            room = await crud.get_or_404(session, m.Room, room_id, code="rooms.not_found")
            await ensure_not_used_by_resets(session, "room", room.vnum, code="rooms.in_reset_usage")
            await ensure_room_has_no_occupants(session, room_id)
            # Il DB non ha ON DELETE: cascade e "SET NULL" sono espliciti. Stessa transazione di `crud.delete`:
            # se questa fallisce, il rollback ripristina anche uscite/extra appena eliminate.
            await session.execute(sa_update(m.Exit).where(m.Exit.target_room_id == room_id).values(target_room_id=None))
            await session.execute(sa_delete(m.Exit).where(m.Exit.room_id == room_id))
            if m.RoomExtraDescription is not None:
                await session.execute(sa_delete(m.RoomExtraDescription).where(m.RoomExtraDescription.room_id == room_id))
            await crud.delete(session, m.Room, room_id, code="rooms.not_found")

    async def clone_room(self, room_id: int, data: RoomCloneIn) -> RoomDetail:
        """Duplica una stanza (non le uscite) con un nuovo vnum; copia le extra description."""
        self.ensure_writable()
        async with self.session() as session:
            m = models_of(session)
            Room = m.Room  # noqa: N806
            source = await crud.get_or_404(session, Room, room_id, code="rooms.not_found")
            await _ensure_room_vnum_free(session, data.vnum)
            clone = Room(
                vnum=data.vnum,
                zone_id=source.zone_id,
                name=data.name or source.name,
                description=source.description,
                sector_type=source.sector_type,
                flags=list(source.flags),
                heal_rate=source.heal_rate,
                mana_rate=source.mana_rate,
                clan_id=source.clan_id,
                owner=source.owner,
            )
            session.add(clone)
            await session.flush()
            for extra in await _extras(session, room_id):
                session.add(m.RoomExtraDescription(room_id=clone.id, keywords=extra.keywords, text=extra.text))
            await session.commit()
            return await _room_detail(session, clone)

    async def room_graph(self, zone_id: int) -> RoomGraph:
        """Le stanze di una zona e le uscite tra loro, con layout a bussola calcolato dal server."""
        async with self.session() as session:
            m = models_of(session)
            Room, Exit = m.Room, m.Exit  # noqa: N806
            rooms = (await session.execute(select(Room).where(Room.zone_id == zone_id))).scalars().all()
            room_ids = {room.id for room in rooms}
            exits = (await session.execute(select(Exit).where(Exit.room_id.in_(room_ids)))).scalars().all() if room_ids else []
            return rules.build_room_graph(
                [rules.GraphRoom(r.id, r.vnum, r.name, SectorType(r.sector_type), list(r.flags)) for r in rooms],
                [rules.GraphExit(e.id, e.room_id, Direction(e.direction), DoorFlag(e.door_flag), e.target_room_id) for e in exits],
            )

    async def room_usage(self, room_id: int) -> list[ResetUsage]:
        """I comandi di reset (di qualsiasi zona) che referenziano questa stanza per vnum."""
        async with self.session() as session:
            room = await crud.get_or_404(session, models_of(session).Room, room_id, code="rooms.not_found")
            return await find_reset_usage(session, "room", room.vnum)

    async def create_exit(self, room_id: int, data: ExitIn) -> ExitOut:
        """Crea un'uscita dalla stanza (una per direzione)."""
        self.ensure_writable()
        async with self.session() as session:
            m = models_of(session)
            Exit = m.Exit  # noqa: N806
            await crud.get_or_404(session, m.Room, room_id, code="rooms.not_found")
            existing = (
                (await session.execute(select(Exit).where(Exit.room_id == room_id, Exit.direction == int(data.direction))))
                .scalars()
                .first()
            )
            if existing is not None:
                raise conflict("rooms.exit_direction_taken", direction=data.direction.name)
            await _check_exit(session, room_id, data.model_dump(by_alias=False), set(ExitIn.model_fields))
            exit_row = await crud.create(session, Exit, {**data.model_dump(by_alias=False), "room_id": room_id})
            return await _exit_out_one(session, exit_row)

    async def update_exit(self, room_id: int, exit_id: int, data: ExitPatch) -> ExitOut:
        """Aggiornamento parziale di un'uscita."""
        self.ensure_writable()
        async with self.session() as session:
            Exit = models_of(session).Exit  # noqa: N806
            exit_row = await crud.get_or_404(session, Exit, exit_id, code="rooms.exit_not_found")
            if exit_row.room_id != room_id:
                raise conflict("rooms.exit_not_in_room")
            if data.direction is not None and data.direction != exit_row.direction:
                clash = (
                    (await session.execute(select(Exit).where(Exit.room_id == room_id, Exit.direction == int(data.direction))))
                    .scalars()
                    .first()
                )
                if clash is not None:
                    raise conflict("rooms.exit_direction_taken", direction=data.direction.name)
            if data.extra:
                raise api_error(422, "world.extra_unsupported")
            changes = data.model_dump(exclude_unset=True, by_alias=False, exclude={"extra"})
            final = {name: changes.get(name, getattr(exit_row, name)) for name in ExitIn.model_fields}
            await _check_exit(session, room_id, final, set(changes))
            exit_row = await crud.update(session, Exit, exit_id, changes, code="rooms.exit_not_found")
            return await _exit_out_one(session, exit_row)

    async def delete_exit(self, room_id: int, exit_id: int) -> None:
        """Elimina un'uscita."""
        self.ensure_writable()
        async with self.session() as session:
            Exit = models_of(session).Exit  # noqa: N806
            exit_row = await crud.get_or_404(session, Exit, exit_id, code="rooms.exit_not_found")
            if exit_row.room_id != room_id:
                raise conflict("rooms.exit_not_in_room")
            await crud.delete(session, Exit, exit_id, code="rooms.exit_not_found")

    async def create_extra_description(self, room_id: int, data: ExtraDescriptionIn) -> ExtraDescriptionOut:
        """Crea un'extra description."""
        self.ensure_writable()
        async with self.session() as session:
            m = models_of(session)
            await crud.get_or_404(session, m.Room, room_id, code="rooms.not_found")
            row = await crud.create(session, self._extra_model(session), {**data.model_dump(by_alias=False), "room_id": room_id})
            return ExtraDescriptionOut.model_validate(row)

    async def update_extra_description(self, room_id: int, extra_id: int, data: ExtraDescriptionPatch) -> ExtraDescriptionOut:
        """Aggiornamento parziale di un'extra description."""
        self.ensure_writable()
        async with self.session() as session:
            Extra = self._extra_model(session)  # noqa: N806
            row = await crud.get_or_404(session, Extra, extra_id, code="rooms.extra_not_found")
            if row.room_id != room_id:
                raise conflict("rooms.extra_not_in_room")
            row = await crud.update(session, Extra, extra_id, data, code="rooms.extra_not_found")
            return ExtraDescriptionOut.model_validate(row)

    async def delete_extra_description(self, room_id: int, extra_id: int) -> None:
        """Elimina un'extra description."""
        self.ensure_writable()
        async with self.session() as session:
            Extra = self._extra_model(session)  # noqa: N806
            row = await crud.get_or_404(session, Extra, extra_id, code="rooms.extra_not_found")
            if row.room_id != room_id:
                raise conflict("rooms.extra_not_in_room")
            await crud.delete(session, Extra, extra_id, code="rooms.extra_not_found")
