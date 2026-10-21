"""Giocatori dei mondi su file: lettura (SDK 1.3) e scrittura (SDK 1.4). Prefisso `/api/world/players` (X-World come le altre rotte).

Non tocca `/api/players` (account/personaggi del DB pachimud). Router sottile sopra il mixin `PlayersAdapter`. Ogni scrittura:
mondo non `read_only` (409 `world.read_only`), capability dedicata, e se il server di gioco e' acceso (`/status`) richiede
`confirmServerRunning: true` (409 `worldplayers.server_running`).
"""

from typing import Annotated

from fastapi import Depends, Query
from pachifast.i18n import api_error
from pachifast.router_factory import get_router
from pachifast.schemas.responses import PaginatedResponse

from pachimudeditor.common.adapters.players import (
    PlayerDetail,
    PlayerInventory,
    PlayerItemAdd,
    PlayerItemUpdate,
    PlayerPageParams,
    PlayerPatch,
    PlayersAdapter,
    PlayersInfo,
    PlayersStatus,
    PlayerSummary,
    PlayerWriteOptions,
)
from pachimudeditor.common.adapters.registry import AdapterDep, WriteAdapterDep, require_capability

router = get_router(name="world/players", deps=[Depends(require_capability("supports_player_records"))])

PlayerId = str
"""Id opaco: gli adapter lo validano; qui si escludono solo i caratteri di percorso (404, mai 422)."""


def players_of(adapter: AdapterDep) -> PlayersAdapter:
    """L'adapter come `PlayersAdapter` (409 `world.capability_missing` se non implementa il mixin)."""
    if not isinstance(adapter, PlayersAdapter):
        raise api_error(409, "world.capability_missing", capability="supports_player_records")
    return adapter


PlayersDep = Annotated[PlayersAdapter, Depends(players_of)]


def write_players_of(adapter: WriteAdapterDep) -> PlayersAdapter:
    """Come `players_of` ma 409 `world.read_only` se il mondo e' in sola lettura."""
    return players_of(adapter)


WritePlayersDep = Annotated[PlayersAdapter, Depends(write_players_of)]


async def confirm_server(adapter: PlayersAdapter, options: PlayerWriteOptions, player_id: str | None = None) -> None:
    """409 `worldplayers.server_running` se il server e' acceso (rilevato) o il giocatore risulta connesso (SDK 1.5, certo) e la
    richiesta non lo conferma; non rilevabile = si scrive."""
    if options.confirm_server_running:
        return
    if (player_id is not None and await adapter.player_connected(player_id)) or (await adapter.players_status()).server_running:
        raise api_error(409, "worldplayers.server_running")


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


_WRITE = [Depends(require_capability("supports_player_write"))]
_INVENTORY_WRITE = [
    Depends(require_capability("supports_player_inventory")),
    Depends(require_capability("supports_player_inventory_write")),
]


@router.patch("/{player_id}", response_model=PlayerDetail, dependencies=_WRITE)
async def update_player(player_id: CheckedId, patch: PlayerPatch, adapter: WritePlayersDep) -> PlayerDetail:
    """Modifica parziale dei campi (`details`) e delle tabelle (`lists`); la password non e' modificabile.

    409 `worldplayers.server_running` (server acceso senza conferma), `worldplayers.conflict` (file cambiato), 422 `worldplayers.invalid_value`.
    """
    await confirm_server(adapter, patch, player_id)
    return await adapter.update_player(player_id, patch)


@router.post("/{player_id}/inventory/items", response_model=PlayerInventory, status_code=201, dependencies=_INVENTORY_WRITE)
async def add_player_item(player_id: CheckedId, item: PlayerItemAdd, adapter: WritePlayersDep) -> PlayerInventory:
    """Aggiunge un oggetto dal prototipo del mondo (per `vnum`), portato, equipaggiato o in un contenitore."""
    await confirm_server(adapter, item, player_id)
    return await adapter.add_player_item(player_id, item)


@router.patch("/{player_id}/inventory/items/{item_id}", response_model=PlayerInventory, dependencies=_INVENTORY_WRITE)
async def update_player_item(player_id: CheckedId, item_id: int, change: PlayerItemUpdate, adapter: WritePlayersDep) -> PlayerInventory:
    """Cambia lo slot di un oggetto di primo livello (`item_id` = `PlayerItem.id`)."""
    await confirm_server(adapter, change, player_id)
    return await adapter.update_player_item(player_id, item_id, change)


@router.delete("/{player_id}/inventory/items/{item_id}", response_model=PlayerInventory, dependencies=_INVENTORY_WRITE)
async def remove_player_item(
    player_id: CheckedId, item_id: int, options: Annotated[PlayerWriteOptions, Query()], adapter: WritePlayersDep
) -> PlayerInventory:
    """Toglie l'oggetto con il suo contenuto (`revision` e `confirmServerRunning` come query)."""
    await confirm_server(adapter, options, player_id)
    return await adapter.remove_player_item(player_id, item_id, options)
