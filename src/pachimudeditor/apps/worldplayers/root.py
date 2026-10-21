"""Giocatori dei mondi su file, in sola lettura. Prefisso `/api/world/players` (X-World come le altre rotte).

Non tocca `/api/players` (account/personaggi del DB pachimud). Router sottile sopra il mixin `PlayersAdapter`.
"""

from typing import Annotated

from fastapi import Depends, Query
from pachifast.i18n import api_error
from pachifast.router_factory import get_router
from pachifast.schemas.responses import PaginatedResponse

from pachimudeditor.common.adapters.players import (
    PlayerDetail,
    PlayerInventory,
    PlayerPageParams,
    PlayersAdapter,
    PlayersInfo,
    PlayersStatus,
    PlayerSummary,
)
from pachimudeditor.common.adapters.registry import AdapterDep, require_capability

router = get_router(name="world/players", deps=[Depends(require_capability("supports_player_records"))])

PlayerId = str
"""Id opaco: gli adapter lo validano; qui si escludono solo i caratteri di percorso (404, mai 422)."""


def players_of(adapter: AdapterDep) -> PlayersAdapter:
    """L'adapter come `PlayersAdapter` (409 `world.capability_missing` se non implementa il mixin)."""
    if not isinstance(adapter, PlayersAdapter):
        raise api_error(409, "world.capability_missing", capability="supports_player_records")
    return adapter


PlayersDep = Annotated[PlayersAdapter, Depends(players_of)]


def checked_id(player_id: PlayerId) -> str:
    """404 `worldplayers.not_found` se l'id contiene separatori di percorso, `..` o caratteri di controllo."""
    if "/" in player_id or "\\" in player_id or ".." in player_id or any(ord(c) < 32 for c in player_id):
        raise api_error(404, "worldplayers.not_found")
    return player_id


CheckedId = Annotated[str, Depends(checked_id)]


@router.get("/info", response_model=PlayersInfo)
async def info(adapter: PlayersDep) -> PlayersInfo:
    """Colonne dell'elenco e campi/tabelle del dettaglio dichiarati dall'adapter."""
    return adapter.players_info()


@router.get("/status", response_model=PlayersStatus)
async def status(adapter: PlayersDep) -> PlayersStatus:
    """Stato del server di gioco se rilevabile (`serverRunning` nullo = sconosciuto). Mai bloccante."""
    return await adapter.players_status()


@router.get("", response_model=PaginatedResponse[PlayerSummary])
async def list_players(params: Annotated[PlayerPageParams, Query()], adapter: PlayersDep) -> PaginatedResponse[PlayerSummary]:
    """Giocatori paginati, cercabili per nome."""
    return await adapter.list_players(params)


@router.get("/{player_id}", response_model=PlayerDetail)
async def get_player(player_id: CheckedId, adapter: PlayersDep) -> PlayerDetail:
    """Il dettaglio di un giocatore (404 `worldplayers.not_found`)."""
    return await adapter.get_player(player_id)


@router.get(
    "/{player_id}/inventory", response_model=PlayerInventory, dependencies=[Depends(require_capability("supports_player_inventory"))]
)
async def player_inventory(player_id: CheckedId, adapter: PlayersDep) -> PlayerInventory:
    """Inventario ed equipaggiamento (capability `supports_player_inventory`)."""
    return await adapter.player_inventory(player_id)
