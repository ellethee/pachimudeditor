"""Object prototype: CRUD, uso nei reset. Prefisso `/api/objects`. Router sottile sopra l'adapter del mondo attivo."""

from typing import Annotated

from fastapi import Query
from pachifast.router_factory import get_router
from pachifast.schemas.responses import PaginatedResponse

from pachimudeditor.common.adapters.models import ObjectIn, ObjectOut, ObjectPageParams, ObjectPatch, ResetUsage
from pachimudeditor.common.adapters.registry import AdapterDep, WriteAdapterDep

router = get_router()


@router.get("", response_model=PaginatedResponse[ObjectOut])
async def list_objects(params: Annotated[ObjectPageParams, Query()], adapter: AdapterDep) -> PaginatedResponse[ObjectOut]:
    """Oggetti paginati, filtrabili per zona (`zoneId`), cercabili per nome/vnum; ordine di default per vnum."""
    return await adapter.list_objects(params)


@router.post("", response_model=ObjectOut, status_code=201)
async def create_object(data: ObjectIn, adapter: WriteAdapterDep) -> ObjectOut:
    """Crea un object prototype (il vnum deve essere libero)."""
    return await adapter.create_object(data)


@router.get("/{object_id}", response_model=ObjectOut)
async def get_object(object_id: int, adapter: AdapterDep) -> ObjectOut:
    """Un object prototype."""
    return await adapter.get_object(object_id)


@router.put("/{object_id}", response_model=ObjectOut)
async def update_object(object_id: int, data: ObjectPatch, adapter: WriteAdapterDep) -> ObjectOut:
    """Aggiornamento parziale di un object prototype. Cambiare il vnum e' rifiutato (409
    `objects.vnum_in_use`) finche' un reset o la chiave di un'uscita lo referenzia."""
    return await adapter.update_object(object_id, data)


@router.get("/{object_id}/usage", response_model=list[ResetUsage])
async def object_usage(object_id: int, adapter: AdapterDep) -> list[ResetUsage]:
    """I comandi di reset (di qualsiasi zona) che referenziano questo oggetto per vnum."""
    return await adapter.object_usage(object_id)


@router.delete("/{object_id}", status_code=204, response_model=None, skip_envelope=True)
async def delete_object(object_id: int, adapter: WriteAdapterDep) -> None:
    """Elimina un object prototype: 409 `objects.in_reset_usage` se e' referenziato da un reset,
    `objects.in_exit_key_usage` se e' la chiave di un'uscita, `objects.has_instances` se esistono istanze."""
    await adapter.delete_object(object_id)
