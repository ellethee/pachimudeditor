"""Istanze vive: `MobInstance`/`ObjectInstance` presenti nel mondo. Prefisso `/api/instances`.

Sono cio' che il reset di zona (o i giocatori) hanno generato: qui si elencano, si correggono (punti ferita,
cassa, cariche, liquido, posizione), se ne generano di nuove da un prototipo e si eliminano. Il game server tiene
le istanze in memoria: modificare a server fermo. Il DB non ha cascade: eliminare un mob/contenitore richiede di
scegliere cosa farne del contenuto (`?contents=destroy|drop`, default `destroy`).
"""

from typing import Annotated

from fastapi import Depends, Query
from pachifast.i18n import api_error
from pachifast.router_factory import get_router

from pachimudeditor.sdk import require_capability
from pachifast.schemas.responses import PageParams, PaginatedResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.schema import models_of
from pachimudeditor_adapter_pachimud.apps.instances import service
from pachimudeditor_adapter_pachimud.apps.instances.schemas import (
    CONTENTS_POLICIES,
    MobCreate,
    MobDetail,
    MobOut,
    MobPatch,
    ObjectCreate,
    ObjectDetail,
    ObjectOut,
    ObjectPatch,
)
from pachimudeditor_adapter_pachimud.editor import crud
from pachimudeditor_adapter_pachimud.editor.db import SessionDep
from pachimudeditor.sdk import conflict

router = get_router(deps=[Depends(require_capability("supports_instances"))])


class MobInstanceParams(PageParams):
    """Lista mob vivi: `search` su id/prototipo/stanza; filtri `roomId`, `zoneId` (zona della stanza),
    `prototypeId`, `prototypeVnum`. Ordinabile per i campi di `service.MOB_ORDER_COLUMNS`."""

    room_id: int | None = Query(None)
    zone_id: int | None = Query(None)
    prototype_id: int | None = Query(None)
    prototype_vnum: int | None = Query(None)


class ObjectInstanceParams(PageParams):
    """Lista oggetti vivi: `search` su id/prototipo; `roomId`/`zoneId` valgono per la stanza *effettiva*;
    `prototypeId`, `prototypeVnum`, `objectType` (del prototipo), `kind` (room|container|mob|character) con
    `holderId` opzionale (id esatto del possessore)."""

    room_id: int | None = Query(None)
    zone_id: int | None = Query(None)
    prototype_id: int | None = Query(None)
    prototype_vnum: int | None = Query(None)
    object_type: int | None = Query(None)
    kind: str | None = Query(None)
    holder_id: int | None = Query(None)


def _policy(contents: str) -> service.ContentsPolicy:
    """Valida il parametro `contents` (422 `instances.invalid_contents_policy`)."""
    if contents not in CONTENTS_POLICIES:
        raise api_error(422, "instances.invalid_contents_policy", value=contents)
    return contents  # type: ignore[return-value]


async def _mob_detail(session: AsyncSession, mob_id: int) -> MobDetail:
    """Il mob con gli oggetti che porta o indossa (404 `instances.mob_not_found` se manca)."""
    q = service.queries(session)
    rows = list((await session.execute(q.mob_statement().where(q.MobInstance.id == mob_id))).all())
    if not rows:
        raise api_error(404, "instances.mob_not_found", id=mob_id)
    mob = (await service.build_mobs(session, rows))[0]
    held = list(
        (await session.execute(q.object_statement().where(q.ObjectInstance.mob_instance_id == mob_id).order_by(q.ObjectInstance.id))).all()
    )
    return MobDetail(**mob.model_dump(), items=await service.build_objects(session, held))


async def _object_detail(session: AsyncSession, object_id: int) -> ObjectDetail:
    """L'oggetto con il suo contenuto (404 `instances.object_not_found` se manca)."""
    q = service.queries(session)
    rows = list((await session.execute(q.object_statement().where(q.ObjectInstance.id == object_id))).all())
    if not rows:
        raise api_error(404, "instances.object_not_found", id=object_id)
    instance = (await service.build_objects(session, rows))[0]
    inside = list(
        (
            await session.execute(
                q.object_statement().where(q.ObjectInstance.container_instance_id == object_id).order_by(q.ObjectInstance.id)
            )
        ).all()
    )
    return ObjectDetail(**instance.model_dump(), contents=await service.build_objects(session, inside))


async def _commit_delete(session: AsyncSession) -> None:
    """Commit di una delete: un errore di FK diventa 409 `common.editor.in_use`."""
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise conflict("common.editor.in_use") from error


# ------------------------------------------------------------------------------------- mobs


@router.get("/mobs", response_model=PaginatedResponse[MobOut])
async def list_mobs(params: Annotated[MobInstanceParams, Query()], session: SessionDep) -> PaginatedResponse[MobOut]:
    """Mob vivi paginati; ordine di default per id decrescente (i piu' recenti prima)."""
    q = service.queries(session)
    m = models_of(session)
    statement = q.mob_statement()
    if params.room_id is not None:
        statement = statement.where(q.MobInstance.room_id == params.room_id)
    if params.zone_id is not None:
        statement = statement.where(m.Room.zone_id == params.zone_id)
    if params.prototype_id is not None:
        statement = statement.where(q.MobInstance.prototype_id == params.prototype_id)
    if params.prototype_vnum is not None:
        statement = statement.where(m.MobPrototype.vnum == params.prototype_vnum)
    if params.search:
        statement = statement.where(q.mob_search_filter(params.search))
    rows, total, page = await service.paginate(session, statement, params, q.mob_order_columns, [q.MobInstance.id.desc()])
    page.items = await service.build_mobs(session, rows)
    return page


@router.get("/mobs/{mob_id}", response_model=MobDetail)
async def get_mob(mob_id: int, session: SessionDep) -> MobDetail:
    """Un mob vivo con gli oggetti che porta o indossa."""
    return await _mob_detail(session, mob_id)


@router.post("/mobs", response_model=MobDetail, status_code=201)
async def spawn_mob(data: MobCreate, session: SessionDep) -> MobDetail:
    """Genera un mob da un prototipo in una stanza. I PF, se assenti, si tirano dai dadi del prototipo.

    422 se prototipo o stanza non esistono o se PF/oro non sono validi.
    """
    m = models_of(session)
    prototype = await session.get(m.MobPrototype, data.prototype_id)
    if prototype is None:
        raise api_error(422, "instances.mob_prototype_not_found", id=data.prototype_id)
    await service.ensure_room(session, data.room_id)
    service.check_non_negative("gold", data.gold)
    if data.hit_points is not None:
        service.check_hit_points(data.hit_points, data.hit_points)
    hit_points = data.hit_points or max(1, service.roll_dice(prototype.hp_dice_count, prototype.hp_die_size, prototype.hp_bonus))
    mob = await crud.create(
        session,
        m.MobInstance,
        {
            "prototype_id": prototype.id,
            "room_id": data.room_id,
            "hit_points_current": hit_points,
            "hit_points_max": hit_points,
            "gold": data.gold,
        },
    )
    return await _mob_detail(session, mob.id)


@router.put("/mobs/{mob_id}", response_model=MobDetail)
async def update_mob(mob_id: int, data: MobPatch, session: SessionDep) -> MobDetail:
    """Modifica PF, cassa (`gold`) e/o stanza di un mob vivo (solo i campi inviati; PF e stanza non azzerabili)."""
    MobInstance = service.queries(session).MobInstance  # noqa: N806
    mob = await crud.get_or_404(session, MobInstance, mob_id, code="instances.mob_not_found")
    values = data.model_dump(exclude_unset=True, by_alias=False)
    for name in ("hit_points_current", "hit_points_max", "room_id"):
        if name in values and values[name] is None:
            del values[name]
    service.check_hit_points(values.get("hit_points_current", mob.hit_points_current), values.get("hit_points_max", mob.hit_points_max))
    service.check_non_negative("gold", values.get("gold"))
    if "room_id" in values:
        await service.ensure_room(session, values["room_id"])
    await crud.update(session, MobInstance, mob_id, values, code="instances.mob_not_found")
    return await _mob_detail(session, mob_id)


@router.delete("/mobs/{mob_id}", status_code=204, response_model=None, skip_envelope=True)
async def despawn_mob(mob_id: int, session: SessionDep, contents: str = "destroy") -> None:
    """Elimina un mob vivo. `contents=destroy` (default) distrugge anche cio' che porta (e il contenuto dei
    suoi contenitori); `contents=drop` lo lascia cadere nella stanza del mob."""
    policy = _policy(contents)
    mob = await crud.get_or_404(session, service.queries(session).MobInstance, mob_id, code="instances.mob_not_found")
    await service.destroy_mob(session, mob, policy)
    await _commit_delete(session)


# --------------------------------------------------------------------------------- objects


@router.get("/objects", response_model=PaginatedResponse[ObjectOut])
async def list_objects(params: Annotated[ObjectInstanceParams, Query()], session: SessionDep) -> PaginatedResponse[ObjectOut]:
    """Oggetti vivi paginati; ordine di default per id decrescente."""
    q = service.queries(session)
    m = models_of(session)
    statement = q.object_statement()
    if params.room_id is not None:
        statement = statement.where(q.effective_room == params.room_id)
    if params.zone_id is not None:
        statement = statement.where(m.Room.zone_id == params.zone_id)
    if params.prototype_id is not None:
        statement = statement.where(q.ObjectInstance.prototype_id == params.prototype_id)
    if params.prototype_vnum is not None:
        statement = statement.where(m.ObjectPrototype.vnum == params.prototype_vnum)
    if params.object_type is not None:
        statement = statement.where(m.ObjectPrototype.object_type == params.object_type)
    if params.kind:
        column = q.kind_column(params.kind)
        statement = statement.where(column.is_not(None))
        if params.holder_id is not None:
            statement = statement.where(column == params.holder_id)
    if params.search:
        statement = statement.where(q.object_search_filter(params.search))
    rows, total, page = await service.paginate(session, statement, params, q.object_order_columns, [q.ObjectInstance.id.desc()])
    page.items = await service.build_objects(session, rows)
    return page


@router.get("/objects/{object_id}", response_model=ObjectDetail)
async def get_object(object_id: int, session: SessionDep) -> ObjectDetail:
    """Un oggetto vivo con il suo contenuto."""
    return await _object_detail(session, object_id)


@router.post("/objects", response_model=ObjectDetail, status_code=201)
async def spawn_object(data: ObjectCreate, session: SessionDep) -> ObjectDetail:
    """Genera un oggetto da un prototipo in una stanza, in un contenitore o nell'inventario (anche indossato)
    di un mob/personaggio. Posizione e stato verificati (422 se non validi)."""
    m = models_of(session)
    prototype = await session.get(m.ObjectPrototype, data.prototype_id)
    if prototype is None:
        raise api_error(422, "instances.object_prototype_not_found", id=data.prototype_id)
    service.check_object_state(prototype, charges=data.charges, liquid_amount=data.liquid_amount)
    placement = await service.resolve_location(session, prototype, data.location)
    row = await crud.create(
        session,
        m.ObjectInstance,
        {"prototype_id": prototype.id, "charges": data.charges, "liquid_amount": data.liquid_amount, **placement},
    )
    return await _object_detail(session, row.id)


@router.put("/objects/{object_id}", response_model=ObjectDetail)
async def update_object(object_id: int, data: ObjectPatch, session: SessionDep) -> ObjectDetail:
    """Modifica cariche, liquido e/o posizione (solo i campi inviati; `null` su un valore numerico lo riporta
    al prototipo, `location: null` e' rifiutato). Spostare un contenitore non sposta il suo contenuto."""
    m = models_of(session)
    instance = await crud.get_or_404(session, m.ObjectInstance, object_id, code="instances.object_not_found")
    prototype = await session.get(m.ObjectPrototype, instance.prototype_id)
    assert prototype is not None
    sent = data.model_dump(exclude_unset=True, by_alias=False)
    values = {name: sent[name] for name in ("charges", "liquid_amount", "liquid_type", "liquid_poisoned") if name in sent}
    service.check_object_state(prototype, **values)
    if data.location is not None:
        values.update(await service.resolve_location(session, prototype, data.location, instance=instance))
    elif "location" in sent:
        raise api_error(422, "instances.location_empty")
    await crud.update(session, m.ObjectInstance, object_id, values, code="instances.object_not_found")
    return await _object_detail(session, object_id)


@router.delete("/objects/{object_id}", status_code=204, response_model=None, skip_envelope=True)
async def despawn_object(object_id: int, session: SessionDep, contents: str = "destroy") -> None:
    """Elimina un oggetto vivo. Se e' un contenitore: `contents=destroy` (default) ne distrugge il contenuto,
    `contents=drop` lo lascia dove stava il contenitore (stanza o inventario)."""
    policy = _policy(contents)
    instance = await crud.get_or_404(session, service.queries(session).ObjectInstance, object_id, code="instances.object_not_found")
    await service.destroy_object(session, instance, policy)
    await _commit_delete(session)
