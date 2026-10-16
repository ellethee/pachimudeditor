"""Stanze: CRUD, uscite, extra description e il grafo delle stanze per la mappa. Prefisso `/api/rooms`.

Router sottile: la logica sta nell'adapter del mondo attivo (`common.adapters`).
"""

from typing import Annotated

from fastapi import Query
from pachifast.router_factory import get_router
from pachifast.schemas.responses import PaginatedResponse

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
from pachimudeditor.common.adapters.registry import AdapterDep, WriteAdapterDep

router = get_router()


@router.get("", response_model=PaginatedResponse[RoomOut])
async def list_rooms(params: Annotated[RoomPageParams, Query()], adapter: AdapterDep) -> PaginatedResponse[RoomOut]:
    """Stanze paginate, filtrabili per zona (`zoneId`), cercabili per nome/vnum; ordine di default per vnum."""
    return await adapter.list_rooms(params)


@router.post("", response_model=RoomDetail, status_code=201)
async def create_room(data: RoomIn, adapter: WriteAdapterDep) -> RoomDetail:
    """Crea una stanza (il vnum deve essere libero)."""
    return await adapter.create_room(data)


@router.get("/graph", response_model=RoomGraph)
async def room_graph(adapter: AdapterDep, zone_id: Annotated[int, Query(alias="zoneId")]) -> RoomGraph:
    """Le stanze di una zona e le uscite tra loro, con un layout a bussola calcolato dal server."""
    return await adapter.room_graph(zone_id)


@router.get("/{room_id}", response_model=RoomDetail)
async def get_room(room_id: int, adapter: AdapterDep) -> RoomDetail:
    """Una stanza, con uscite ed extra description."""
    return await adapter.get_room(room_id)


@router.put("/{room_id}", response_model=RoomDetail)
async def update_room(room_id: int, data: RoomPatch, adapter: WriteAdapterDep) -> RoomDetail:
    """Aggiornamento parziale di una stanza. Cambiare il vnum e' rifiutato (409 `rooms.vnum_in_use`)
    finche' un comando di reset lo referenzia."""
    return await adapter.update_room(room_id, data)


@router.get("/{room_id}/usage", response_model=list[ResetUsage])
async def room_usage(room_id: int, adapter: AdapterDep) -> list[ResetUsage]:
    """I comandi di reset (di qualsiasi zona) che referenziano questa stanza per vnum."""
    return await adapter.room_usage(room_id)


@router.post("/{room_id}/clone", response_model=RoomDetail, status_code=201)
async def clone_room(room_id: int, data: RoomCloneIn, adapter: WriteAdapterDep) -> RoomDetail:
    """Duplica una stanza (non le uscite) con un nuovo vnum; copia le extra description."""
    return await adapter.clone_room(room_id, data)


@router.delete("/{room_id}", status_code=204, response_model=None, skip_envelope=True)
async def delete_room(room_id: int, adapter: WriteAdapterDep) -> None:
    """Elimina una stanza insieme alle sue uscite e alle sue extra description (le uscite di altre stanze che
    puntavano a questa restano senza destinazione). Rifiutato (409) finche' e' referenziata da un reset
    (`rooms.in_reset_usage`) o contiene istanze vive / e' l'ultima stanza di un personaggio (`rooms.has_instances`)."""
    await adapter.delete_room(room_id)


@router.post("/{room_id}/exits", response_model=ExitOut, status_code=201)
async def create_exit(room_id: int, data: ExitIn, adapter: WriteAdapterDep) -> ExitOut:
    """Crea un'uscita dalla stanza (una per direzione)."""
    return await adapter.create_exit(room_id, data)


@router.put("/{room_id}/exits/{exit_id}", response_model=ExitOut)
async def update_exit(room_id: int, exit_id: int, data: ExitPatch, adapter: WriteAdapterDep) -> ExitOut:
    """Aggiornamento parziale di un'uscita."""
    return await adapter.update_exit(room_id, exit_id, data)


@router.delete("/{room_id}/exits/{exit_id}", status_code=204, response_model=None, skip_envelope=True)
async def delete_exit(room_id: int, exit_id: int, adapter: WriteAdapterDep) -> None:
    """Elimina un'uscita."""
    await adapter.delete_exit(room_id, exit_id)


@router.post("/{room_id}/extra-descriptions", response_model=ExtraDescriptionOut, status_code=201)
async def create_extra_description(room_id: int, data: ExtraDescriptionIn, adapter: WriteAdapterDep) -> ExtraDescriptionOut:
    """Crea un'extra description."""
    return await adapter.create_extra_description(room_id, data)


@router.put("/{room_id}/extra-descriptions/{extra_id}", response_model=ExtraDescriptionOut)
async def update_extra_description(
    room_id: int, extra_id: int, data: ExtraDescriptionPatch, adapter: WriteAdapterDep
) -> ExtraDescriptionOut:
    """Aggiornamento parziale di un'extra description."""
    return await adapter.update_extra_description(room_id, extra_id, data)


@router.delete("/{room_id}/extra-descriptions/{extra_id}", status_code=204, response_model=None, skip_envelope=True)
async def delete_extra_description(room_id: int, extra_id: int, adapter: WriteAdapterDep) -> None:
    """Elimina un'extra description."""
    await adapter.delete_extra_description(room_id, extra_id)
