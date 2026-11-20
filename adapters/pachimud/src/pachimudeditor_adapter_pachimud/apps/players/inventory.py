"""Inventario di un personaggio: la colonna JSON `player_character.inventory` (oggetti portati/equipaggiati e contenuti).

Formato (deciso dal gioco, che oggi non lo scrive ne' legge ancora): lista di `{vnum, overrides, equipped_slot, state,
contents}`. L'`id` di una voce e' la sua posizione nella visita in profondita' (`helpers.flatten_inventory`): cambia quando si
aggiunge o toglie qualcosa, quindi dopo ogni scrittura il client rilegge la lista. `liquid_amount`/`charges` si leggono da `state`.
"""

import copy
from typing import Any

from pachifast.i18n import api_error
from pachifast.router_factory import get_router

from pachimudeditor.common.enums import ObjectType
from pachimudeditor_adapter_pachimud import mapping
from pachimudeditor_adapter_pachimud.editor.db import PachimudDep, SessionDep
from pachimudeditor_adapter_pachimud.schema import models_of
from pachimudeditor.sdk import not_found

from .helpers import flatten_inventory, get_character_or_404, prototype_by
from .schemas import ItemIn, ItemOut, ItemPatch

router = get_router(prefix="")


def _out(adapter: PachimudDep, index: int, entry: dict[str, Any], parent: int | None) -> ItemOut:
    """`ItemOut` da una voce dell'inventario e dal suo prototipo (se esiste ancora nei file del mondo)."""
    vnum = entry.get("vnum")
    proto = adapter.sync().find("object", vnum) if isinstance(vnum, int) else None
    overrides = entry.get("overrides") or {}
    state = entry.get("state") or {}
    m = proto.model if proto is not None else None
    return ItemOut(
        id=index,
        prototype_id=vnum if isinstance(vnum, int) else 0,
        vnum=vnum if isinstance(vnum, int) else 0,
        keywords=overrides.get("keywords", m.keywords if m else ""),
        short_description=overrides.get("short_description", m.short_description if m else "?"),
        object_type=mapping.type_enum(m.object_type) if m else ObjectType.OTHER,
        equipped_slot=entry.get("equipped_slot"),
        container_instance_id=parent,
        wear_flags=list(overrides.get("wear_flags", m.wear_flags if m else [])),
        liquid_amount=state.get("liquid_amount"),
        charges=state.get("charges"),
    )


def _require_column(session: Any) -> None:
    """422 `world.field_unsupported` se il DB non ha la colonna `inventory` (schema vecchio)."""
    if not models_of(session).column("player_character", "inventory"):
        raise api_error(422, "world.field_unsupported", field="inventory")


@router.get("/characters/{character_id}/inventory", response_model=list[ItemOut])
async def list_inventory(character_id: int, session: SessionDep, adapter: PachimudDep) -> list[ItemOut]:
    """Oggetti del personaggio: portati, equipaggiati (`equippedSlot`) e dentro contenitori
    (`containerInstanceId`)."""
    character = await get_character_or_404(session, character_id)
    return [_out(adapter, i, entry, parent) for i, (entry, parent) in enumerate(flatten_inventory(character.inventory))]


@router.post("/characters/{character_id}/inventory", response_model=ItemOut, status_code=201)
async def add_item(character_id: int, data: ItemIn, session: SessionDep, adapter: PachimudDep) -> ItemOut:
    """Aggiunge all'inventario il prototipo (per `prototypeId` o `vnum`, che coincidono)."""
    _require_column(session)
    character = await get_character_or_404(session, character_id)
    proto = prototype_by(adapter, prototype_id=data.prototype_id, vnum=data.vnum)
    entry = {"vnum": proto.vnum, "overrides": {}, "equipped_slot": data.equipped_slot, "state": {}, "contents": []}
    before = len(flatten_inventory(character.inventory))  # il nuovo oggetto e' l'ultima voce di primo livello
    character.inventory = [*_copy(character.inventory), entry]  # riassegnazione: SQLAlchemy non vede le modifiche in place
    await session.commit()
    return _out(adapter, before, entry, None)


def _entry(character: Any, item_id: int) -> tuple[dict[str, Any], int | None]:
    """La voce `item_id` del personaggio o 404 `players.item_not_found`."""
    flat = flatten_inventory(character.inventory)
    if not 0 <= item_id < len(flat):
        raise not_found("players.item_not_found", id=item_id)
    return flat[item_id]


@router.put("/characters/{character_id}/inventory/{item_id}", response_model=ItemOut)
async def update_item(character_id: int, item_id: int, data: ItemPatch, session: SessionDep, adapter: PachimudDep) -> ItemOut:
    """Imposta/toglie lo slot di equipaggiamento (non per oggetti dentro un contenitore)."""
    _require_column(session)
    character = await get_character_or_404(session, character_id)
    entry, parent = _entry(character, item_id)
    if data.equipped_slot is not None and parent is not None:
        raise api_error(422, "players.item_in_container", loc=("body", "equippedSlot"))
    entry["equipped_slot"] = data.equipped_slot
    character.inventory = _copy(character.inventory)
    await session.commit()
    return _out(adapter, item_id, entry, parent)


def _copy(inventory: Any) -> list[Any]:
    """Copia profonda dell'inventario (per far rilevare la modifica a SQLAlchemy)."""
    return copy.deepcopy(list(inventory or []))


@router.delete("/characters/{character_id}/inventory/{item_id}", status_code=204, response_model=None, skip_envelope=True)
async def remove_item(character_id: int, item_id: int, session: SessionDep) -> None:
    """Elimina la voce (e il suo eventuale contenuto) dall'inventario."""
    _require_column(session)
    character = await get_character_or_404(session, character_id)
    _entry(character, item_id)
    inventory = _copy(character.inventory)
    target = flatten_inventory(inventory)[item_id][0]

    def drop(entries: list[Any]) -> bool:
        """Toglie `target` (per identita') dalla lista o da una sotto-lista."""
        for index, candidate in enumerate(entries):
            if candidate is target:
                del entries[index]
                return True
            if isinstance(candidate, dict) and isinstance(candidate.get("contents"), list) and drop(candidate["contents"]):
                return True
        return False

    drop(inventory)
    character.inventory = inventory
    await session.commit()
