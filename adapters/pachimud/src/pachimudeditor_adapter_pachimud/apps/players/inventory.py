"""Inventario di un personaggio tramite `ObjectInstance.character_id` (oggetti portati/equipaggiati e contenuti)."""

from typing import Any

from pachifast.i18n import api_error
from pachifast.router_factory import get_router
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.schema import models_of
from pachimudeditor_adapter_pachimud.editor.db import SessionDep
from pachimudeditor.sdk import not_found

from .helpers import collect_item_ids, delete_items, get_character_or_404, prototype_by
from .schemas import ItemIn, ItemOut, ItemPatch

router = get_router(prefix="")


def _out(instance: Any, proto: Any) -> ItemOut:
    """`ItemOut` dall'istanza e dal suo prototipo."""
    return ItemOut(
        id=instance.id,
        prototype_id=proto.id,
        vnum=proto.vnum,
        keywords=proto.keywords,
        short_description=proto.short_description,
        object_type=proto.object_type,
        equipped_slot=instance.equipped_slot,
        container_instance_id=instance.container_instance_id,
        wear_flags=proto.wear_flags,
        liquid_amount=instance.liquid_amount,
        charges=instance.charges,
    )


async def _load(session: AsyncSession, ids: list[int]) -> list[ItemOut]:
    """Le istanze `ids` con prototipo, ordinate per id."""
    if not ids:
        return []
    m = models_of(session)
    ObjectInstance, ObjectPrototype = m.ObjectInstance, m.ObjectPrototype  # noqa: N806
    res = await session.execute(
        select(ObjectInstance, ObjectPrototype)
        .join(ObjectPrototype, ObjectPrototype.id == ObjectInstance.prototype_id)
        .where(ObjectInstance.id.in_(ids))
        .order_by(ObjectInstance.id)
    )
    return [_out(i, p) for i, p in res.all()]


@router.get("/characters/{character_id}/inventory", response_model=list[ItemOut])
async def list_inventory(character_id: int, session: SessionDep) -> list[ItemOut]:
    """Oggetti del personaggio: portati, equipaggiati (`equippedSlot`) e dentro contenitori
    (`containerInstanceId`)."""
    await get_character_or_404(session, character_id)
    return await _load(session, await collect_item_ids(session, character_id))


@router.post("/characters/{character_id}/inventory", response_model=ItemOut, status_code=201)
async def add_item(character_id: int, data: ItemIn, session: SessionDep) -> ItemOut:
    """Crea un'istanza del prototipo (per `prototypeId` o `vnum`) nell'inventario del personaggio."""
    await get_character_or_404(session, character_id)
    proto = await prototype_by(session, prototype_id=data.prototype_id, vnum=data.vnum)
    instance = models_of(session).ObjectInstance(prototype_id=proto.id, character_id=character_id, equipped_slot=data.equipped_slot)
    session.add(instance)
    await session.commit()
    await session.refresh(instance)
    return _out(instance, proto)


async def _owned_direct(session: AsyncSession, character_id: int, item_id: int) -> Any:
    """L'istanza se appartiene al personaggio; 404 `players.item_not_found` altrimenti."""
    if item_id not in await collect_item_ids(session, character_id):
        raise not_found("players.item_not_found", id=item_id)
    instance = await session.get(models_of(session).ObjectInstance, item_id)
    assert instance is not None
    return instance


@router.put("/characters/{character_id}/inventory/{item_id}", response_model=ItemOut)
async def update_item(character_id: int, item_id: int, data: ItemPatch, session: SessionDep) -> ItemOut:
    """Imposta/toglie lo slot di equipaggiamento (non per oggetti dentro un contenitore)."""
    await get_character_or_404(session, character_id)
    instance = await _owned_direct(session, character_id, item_id)
    if data.equipped_slot is not None and instance.character_id != character_id:
        raise api_error(422, "players.item_in_container", loc=("body", "equippedSlot"))
    instance.equipped_slot = data.equipped_slot
    await session.commit()
    proto = await session.get(models_of(session).ObjectPrototype, instance.prototype_id)
    assert proto is not None
    return _out(instance, proto)


@router.delete("/characters/{character_id}/inventory/{item_id}", status_code=204, response_model=None, skip_envelope=True)
async def remove_item(character_id: int, item_id: int, session: SessionDep) -> None:
    """Elimina l'istanza (e il suo eventuale contenuto) dall'inventario."""
    await get_character_or_404(session, character_id)
    await _owned_direct(session, character_id, item_id)
    to_delete = [item_id]
    frontier = [item_id]
    while frontier:
        ObjectInstance = models_of(session).ObjectInstance  # noqa: N806
        res = await session.execute(select(ObjectInstance.id).where(ObjectInstance.container_instance_id.in_(frontier)))
        frontier = [i for (i,) in res.all() if i not in to_delete]
        to_delete.extend(frontier)
    await delete_items(session, to_delete)
    await session.commit()
