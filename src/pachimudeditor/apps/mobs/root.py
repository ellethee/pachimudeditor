"""Mob prototype: CRUD, uso nei reset. Prefisso `/api/mobs`. Router sottile sopra l'adapter del mondo attivo."""

from typing import Annotated

from fastapi import Query
from pachifast.router_factory import get_router
from pachifast.schemas.responses import PaginatedResponse

from pachimudeditor.common.adapters.models import MobIn, MobOut, MobPageParams, MobPatch, ResetUsage
from pachimudeditor.common.adapters.registry import AdapterDep, WriteAdapterDep

router = get_router()


@router.get("", response_model=PaginatedResponse[MobOut])
async def list_mobs(params: Annotated[MobPageParams, Query()], adapter: AdapterDep) -> PaginatedResponse[MobOut]:
    """Mob paginati, filtrabili per zona (`zoneId`), cercabili per nome/vnum; ordine di default per vnum."""
    return await adapter.list_mobs(params)


@router.post("", response_model=MobOut, status_code=201)
async def create_mob(data: MobIn, adapter: WriteAdapterDep) -> MobOut:
    """Crea un mob prototype (il vnum deve essere libero)."""
    return await adapter.create_mob(data)


@router.get("/{mob_id}", response_model=MobOut)
async def get_mob(mob_id: int, adapter: AdapterDep) -> MobOut:
    """Un mob prototype."""
    return await adapter.get_mob(mob_id)


@router.put("/{mob_id}", response_model=MobOut)
async def update_mob(mob_id: int, data: MobPatch, adapter: WriteAdapterDep) -> MobOut:
    """Aggiornamento parziale di un mob prototype. Cambiare il vnum e' rifiutato (409 `mobs.vnum_in_use`)
    finche' un comando di reset lo referenzia."""
    return await adapter.update_mob(mob_id, data)


@router.get("/{mob_id}/usage", response_model=list[ResetUsage])
async def mob_usage(mob_id: int, adapter: AdapterDep) -> list[ResetUsage]:
    """I comandi di reset (di qualsiasi zona) che referenziano questo mob per vnum."""
    return await adapter.mob_usage(mob_id)


@router.delete("/{mob_id}", status_code=204, response_model=None, skip_envelope=True)
async def delete_mob(mob_id: int, adapter: WriteAdapterDep) -> None:
    """Elimina un mob prototype: 409 `mobs.in_reset_usage` se e' referenziato da un reset,
    `mobs.has_instances` se esistono istanze vive."""
    await adapter.delete_mob(mob_id)
