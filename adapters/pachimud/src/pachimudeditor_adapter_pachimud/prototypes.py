"""Mob e object prototype sul database di pachimud (mixin di `PachimudAdapter`)."""

from pachifast.schemas.responses import PaginatedResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.base import PachimudSupport
from pachimudeditor_adapter_pachimud.schema import models_of
from pachimudeditor.common.adapters.models import (
    MobIn,
    MobOut,
    MobPageParams,
    MobPatch,
    ObjectIn,
    ObjectOut,
    ObjectPageParams,
    ObjectPatch,
    ResetUsage,
)
from pachimudeditor_adapter_pachimud.editor import crud
from pachimudeditor.sdk import conflict
from pachimudeditor_adapter_pachimud.editor.instances import ensure_mob_has_no_instances, ensure_object_has_no_instances
from pachimudeditor_adapter_pachimud.editor.reset_usage import ensure_not_used, ensure_not_used_by_resets, find_reset_usage


async def _ensure_vnum_free(session: AsyncSession, model: type, code: str, vnum: int, *, ignore_id: int | None = None) -> None:
    """409 `code` se un altro prototipo di `model` usa gia' `vnum`."""
    existing = (await session.execute(select(model).where(model.vnum == vnum))).scalars().first()  # type: ignore[attr-defined]
    if existing is not None and existing.id != ignore_id:
        raise conflict(code, vnum=vnum)


class PrototypesMixin(PachimudSupport):
    """Operazioni su mob e oggetti prototipo."""

    # ---- mob

    async def list_mobs(self, params: MobPageParams) -> PaginatedResponse[MobOut]:
        """Mob paginati, filtrabili per zona (`zoneId`), cercabili per nome/vnum; ordine di default per vnum."""
        async with self.session() as session:
            return await self.page(session, models_of(session).MobPrototype, params, MobOut)

    async def get_mob(self, mob_id: int) -> MobOut:
        """Un mob prototype."""
        async with self.session() as session:
            return MobOut.model_validate(await crud.get_or_404(session, models_of(session).MobPrototype, mob_id, code="mobs.not_found"))

    async def create_mob(self, data: MobIn) -> MobOut:
        """Crea un mob prototype (il vnum deve essere libero)."""
        self.ensure_writable()
        values = self.values(data)
        async with self.session() as session:
            await _ensure_vnum_free(session, models_of(session).MobPrototype, "mobs.vnum_taken", data.vnum)
            return MobOut.model_validate(await crud.create(session, models_of(session).MobPrototype, values))

    async def update_mob(self, mob_id: int, data: MobPatch) -> MobOut:
        """Aggiornamento parziale. Cambiare il vnum e' rifiutato (409 `mobs.vnum_in_use`) finche' un reset lo usa."""
        self.ensure_writable()
        changes = self.values(data, exclude_unset=True)
        async with self.session() as session:
            mob = await crud.get_or_404(session, models_of(session).MobPrototype, mob_id, code="mobs.not_found")
            if data.vnum is not None:
                await _ensure_vnum_free(session, models_of(session).MobPrototype, "mobs.vnum_taken", data.vnum, ignore_id=mob_id)
                if data.vnum != mob.vnum:
                    await ensure_not_used(session, "mob", mob.vnum, code="mobs.vnum_in_use")
            return MobOut.model_validate(
                await crud.update(session, models_of(session).MobPrototype, mob_id, changes, code="mobs.not_found")
            )

    async def delete_mob(self, mob_id: int) -> None:
        """Elimina un mob prototype: 409 `mobs.in_reset_usage` o `mobs.has_instances`."""
        self.ensure_writable()
        async with self.session() as session:
            mob = await crud.get_or_404(session, models_of(session).MobPrototype, mob_id, code="mobs.not_found")
            await ensure_not_used_by_resets(session, "mob", mob.vnum, code="mobs.in_reset_usage")
            await ensure_mob_has_no_instances(session, mob_id)
            await crud.delete(session, models_of(session).MobPrototype, mob_id, code="mobs.not_found")

    async def mob_usage(self, mob_id: int) -> list[ResetUsage]:
        """I comandi di reset (di qualsiasi zona) che referenziano questo mob per vnum."""
        async with self.session() as session:
            mob = await crud.get_or_404(session, models_of(session).MobPrototype, mob_id, code="mobs.not_found")
            return await find_reset_usage(session, "mob", mob.vnum)

    # ---- oggetti

    async def list_objects(self, params: ObjectPageParams) -> PaginatedResponse[ObjectOut]:
        """Oggetti paginati, filtrabili per zona (`zoneId`), cercabili per nome/vnum; ordine di default per vnum."""
        async with self.session() as session:
            return await self.page(session, models_of(session).ObjectPrototype, params, ObjectOut)

    async def get_object(self, object_id: int) -> ObjectOut:
        """Un object prototype."""
        async with self.session() as session:
            return ObjectOut.model_validate(
                await crud.get_or_404(session, models_of(session).ObjectPrototype, object_id, code="objects.not_found")
            )

    async def create_object(self, data: ObjectIn) -> ObjectOut:
        """Crea un object prototype (il vnum deve essere libero)."""
        self.ensure_writable()
        values = self.values(data)
        async with self.session() as session:
            await _ensure_vnum_free(session, models_of(session).ObjectPrototype, "objects.vnum_taken", data.vnum)
            return ObjectOut.model_validate(await crud.create(session, models_of(session).ObjectPrototype, values))

    async def update_object(self, object_id: int, data: ObjectPatch) -> ObjectOut:
        """Aggiornamento parziale. Cambiare il vnum e' rifiutato (409 `objects.vnum_in_use`) finche' un reset o
        la chiave di un'uscita lo referenzia."""
        self.ensure_writable()
        changes = self.values(data, exclude_unset=True)
        async with self.session() as session:
            obj = await crud.get_or_404(session, models_of(session).ObjectPrototype, object_id, code="objects.not_found")
            if data.vnum is not None:
                await _ensure_vnum_free(session, models_of(session).ObjectPrototype, "objects.vnum_taken", data.vnum, ignore_id=object_id)
                if data.vnum != obj.vnum:
                    await ensure_not_used(session, "object", obj.vnum, code="objects.vnum_in_use")
            return ObjectOut.model_validate(
                await crud.update(session, models_of(session).ObjectPrototype, object_id, changes, code="objects.not_found")
            )

    async def delete_object(self, object_id: int) -> None:
        """Elimina un object prototype: 409 `objects.in_reset_usage`, `objects.in_exit_key_usage`, `objects.has_instances`."""
        self.ensure_writable()
        async with self.session() as session:
            obj = await crud.get_or_404(session, models_of(session).ObjectPrototype, object_id, code="objects.not_found")
            await ensure_not_used_by_resets(session, "object", obj.vnum, code="objects.in_reset_usage")
            await ensure_not_used(session, "object", obj.vnum, code="objects.in_exit_key_usage")
            await ensure_object_has_no_instances(session, object_id)
            await crud.delete(session, models_of(session).ObjectPrototype, object_id, code="objects.not_found")

    async def object_usage(self, object_id: int) -> list[ResetUsage]:
        """I comandi di reset (e le chiavi di uscita) che referenziano questo oggetto per vnum."""
        async with self.session() as session:
            obj = await crud.get_or_404(session, models_of(session).ObjectPrototype, object_id, code="objects.not_found")
            return await find_reset_usage(session, "object", obj.vnum)
