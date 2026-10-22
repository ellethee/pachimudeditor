"""Mob e object prototype sul database di pachimud (mixin di `PachimudAdapter`)."""

from typing import Any

from pachifast.database.pagination import paginate
from pachifast.schemas.responses import PageParams, PaginatedResponse
from sqlalchemy import ColumnElement, Select, select
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
from pachimudeditor_adapter_pachimud.editor.pagination import default_order, order_clause, paginate_filtered, range_clauses
from pachimudeditor.sdk import conflict, mob_query, object_query
from pachimudeditor_adapter_pachimud.editor.instances import ensure_mob_has_no_instances, ensure_object_has_no_instances
from pachimudeditor_adapter_pachimud.editor.reset_usage import ensure_not_used, ensure_not_used_by_resets, find_reset_usage


async def _ensure_vnum_free(session: AsyncSession, model: type, code: str, vnum: int, *, ignore_id: int | None = None) -> None:
    """409 `code` se un altro prototipo di `model` usa gia' `vnum`."""
    existing = (await session.execute(select(model).where(model.vnum == vnum))).scalars().first()  # type: ignore[attr-defined]
    if existing is not None and existing.id != ignore_id:
        raise conflict(code, vnum=vnum)


_OBJECT_QUERY_FIELDS = (
    "object_type", "wear_flag", "extra_flag", "affect", "min_affect",
    *(f"{b}_{f}" for f in object_query.RANGE_FIELDS for b in ("min", "max")),
)  # fmt: skip
"""Parametri di `ObjectPageParams` gestiti qui (non sono filtri di uguaglianza su colonna per pachifast)."""


def _object_clauses(model: Any, params: ObjectPageParams) -> list[ColumnElement[bool]]:
    """Clausole SQL dei filtri scalari (tipo e intervalli, zona): i `valueN` nulli non soddisfano un intervallo."""
    clauses: list[ColumnElement[bool]] = []
    if params.zone_id is not None:
        clauses.append(model.zone_id == params.zone_id)
    if params.object_type:
        clauses.append(model.object_type.in_(params.object_type))
    for field in object_query.RANGE_FIELDS:
        low, high = getattr(params, f"min_{field}"), getattr(params, f"max_{field}")
        if low is not None:
            clauses.append(getattr(model, field) >= low)
        if high is not None:
            clauses.append(getattr(model, field) <= high)
    return clauses


def _order_clause(model: Any, field: str, desc: bool) -> ColumnElement[Any]:
    """ORDER BY di un campo, con i nulli sempre in fondo."""
    column = getattr(model, field)
    return column.desc().nulls_last() if desc else column.asc().nulls_last()


class PrototypesMixin(PachimudSupport):
    """Operazioni su mob e oggetti prototipo."""

    # ---- mob

    async def list_mobs(self, params: MobPageParams) -> PaginatedResponse[MobOut]:
        """Mob paginati, filtrabili per zona (`zoneId`) e per statistiche, cercabili per nome/vnum, ordinabili
        (nulli in fondo); ordine di default per vnum. Gli stessi risultati degli adapter su file (`mob_query`)."""
        mob_query.check(params)
        order = mob_query.parse_order(params)
        async with self.session() as session:
            model = models_of(session).MobPrototype
            clauses = range_clauses(model, params, mob_query.RANGE_FIELDS)
            if params.zone_id is not None:
                clauses.append(model.zone_id == params.zone_id)
            if params.sex:
                clauses.append(model.sex.in_(params.sex))
            if params.race_id:
                clauses.append(model.race_id.in_(params.race_id))
            if params.class_id:
                clauses.append(model.class_id.in_(params.class_id))
            if params.flag:
                # i flag stanno in una colonna JSON: si risolvono in Python (stessa funzione degli adapter su file)
                rows = (await session.execute(select(model.id, model.flags).where(*clauses))).all()
                clauses.append(model.id.in_([r.id for r in rows if mob_query.match_flags(r.flags, params)]))
            ordering = [order_clause(model, field, desc) for field, desc in order]
            return await paginate_filtered(session, model, params, MobOut, clauses, ordering)

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
        """Oggetti paginati, filtrabili per zona (`zoneId`) e per statistiche, cercabili per nome/vnum, ordinabili
        (nulli in fondo); ordine di default per vnum. Gli stessi risultati degli adapter su file (`object_query`)."""
        object_query.check(params)
        order = object_query.parse_order(params)
        async with self.session() as session:
            model = models_of(session).ObjectPrototype
            clauses = _object_clauses(model, params)
            if object_query.needs_json(params):
                # flag e affect stanno in colonne JSON: si risolvono in Python (stessa funzione degli adapter su file)
                rows = (await session.execute(select(model.id, model.extra_flags, model.wear_flags, model.affects).where(*clauses))).all()
                clauses.append(
                    model.id.in_([r.id for r in rows if object_query.match_json(r.extra_flags, r.wear_flags, r.affects, params)])
                )
            ordering = [_order_clause(model, field, desc) for field, desc in order]

            def apply(_params: PageParams, kwargs: dict[str, Any], stmt: Select, _model: type) -> tuple[dict[str, Any], Select]:
                """Aggiunge filtri e ORDER BY (poi il vnum di default come spareggio)."""
                return kwargs, stmt.where(*clauses).order_by(*ordering)

            plain = params.model_copy(update={"orderBy": None, **dict.fromkeys(_OBJECT_QUERY_FIELDS)})
            raw = await paginate(session, model, plain, extra_filters=[apply, default_order("vnum")])
            return PaginatedResponse[ObjectOut](
                items=[ObjectOut.model_validate(r) for r in raw.items],
                total=raw.total,
                page=raw.page,
                pageSize=raw.pageSize,
                pages=raw.pages,
            )

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
