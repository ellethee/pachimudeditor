"""Canale live verso il MUD acceso (SDK 1.5): prefisso `/api/world/live` (X-World come le altre rotte).

Solo **superuser** (401 senza sessione, 403 `access.superuser_required` altrimenti): sono operazioni con effetto immediato sul gioco.
Capability `supports_live` (409 `world.capability_missing`); le scritture anche mondo non `read_only` (409 `world.read_only`).
Gli errori del canale diventano `worldlive.*` (vedi `common.adapters.live.http_error`). Router sottile sopra il mixin `LiveAdapter`:
`status` non e' mai un errore (un canale spento e' `state: unreachable`).
"""

from typing import Annotated

from fastapi import Depends, Query
from pachifast.auth.dependencies import get_current_active_user
from pachifast.i18n import api_error
from pachifast.router_factory import get_router

from pachimudeditor.common.adapters.live import (
    LIVE_NAME_RE,
    LiveAdapter,
    LiveEchoIn,
    LiveEchoOut,
    LiveInstances,
    LiveInventory,
    LiveItem,
    LiveItemExpect,
    LiveItemRemoveOut,
    LiveItemSetIn,
    LiveItemSetOut,
    LiveLoadIn,
    LiveLoadOut,
    LivePlayerSetIn,
    LivePlayerSetOut,
    LivePlayerState,
    LiveServerInfo,
    LiveStatus,
    LiveWho,
    LiveContentReloadIn,
    LiveContentReloadOut,
    LiveContentValidateOut,
    LiveZoneReloadIn,
    LiveZoneReloadOut,
    LiveZoneResetIn,
    LiveZoneResetOut,
    LiveZones,
    live_errors,
)
from pachimudeditor.common.adapters.registry import AdapterDep, WriteAdapterDep, require_capability

router = get_router(name="world/live", require_superuser=True, deps=[Depends(require_capability("supports_live"))])


def live_of(adapter: AdapterDep) -> LiveAdapter:
    """L'adapter come `LiveAdapter` (409 `world.capability_missing` se non implementa il mixin)."""
    if not isinstance(adapter, LiveAdapter):
        raise api_error(409, "world.capability_missing", capability="supports_live")
    return adapter


def write_live_of(adapter: WriteAdapterDep) -> LiveAdapter:
    """Come `live_of` ma 409 `world.read_only` se il mondo e' in sola lettura."""
    return live_of(adapter)


LiveDep = Annotated[LiveAdapter, Depends(live_of)]
WriteLiveDep = Annotated[LiveAdapter, Depends(write_live_of)]


async def actor_of(user: Annotated[object, Depends(get_current_active_user)]) -> str:
    """Il nome dell'utente dell'editor: va nell'`hello` (audit del MUD) come informazione dichiarata."""
    return str(getattr(user, "username", "") or "editor")


ActorDep = Annotated[str, Depends(actor_of)]


def player_name(name: str) -> str:
    """404 `worldlive.not_found` se il nome non e' ammesso dal protocollo (`[A-Za-z][A-Za-z0-9_-]{0,19}`)."""
    if not LIVE_NAME_RE.fullmatch(name):
        raise api_error(404, "worldlive.not_found", what="player")
    return name


PlayerName = Annotated[str, Depends(player_name)]


@router.get("/status", response_model=LiveStatus)
async def status(adapter: LiveDep) -> LiveStatus:
    """Il canale e' raggiungibile? Versione, classi e comandi dichiarati, latenza. Non espone socket ne' token; non e' mai un errore."""
    return await adapter.live_status()


@router.get("/who", response_model=LiveWho)
async def who(adapter: LiveDep) -> LiveWho:
    """Giocatori connessi (anche con il collegamento caduto)."""
    with live_errors():
        return await adapter.live_who()


@router.get("/info", response_model=LiveServerInfo)
async def server_info(adapter: LiveDep) -> LiveServerInfo:
    """Uptime, giocatori e contatori del mondo."""
    with live_errors():
        return await adapter.live_server_info()


@router.get("/zones", response_model=LiveZones)
async def zones(adapter: LiveDep) -> LiveZones:
    """Le zone come le vede il gioco (`index` da usare in `zones/reset`)."""
    with live_errors():
        return await adapter.live_zones()


@router.get("/players/{name}", response_model=LivePlayerState)
async def get_player(name: PlayerName, adapter: LiveDep) -> LivePlayerState:
    """Valori correnti in memoria di un giocatore connesso (404 `worldlive.not_found`, 409 `worldlive.player_not_playing`)."""
    with live_errors():
        return await adapter.live_player_get(name)


@router.patch("/players/{name}", response_model=LivePlayerSetOut)
async def set_player(name: PlayerName, change: LivePlayerSetIn, adapter: WriteLiveDep, actor: ActorDep) -> LivePlayerSetOut:
    """Modifica un giocatore connesso (`save` vero di default); promuovere a >= 51 richiede `confirmImmortal` (409 senza)."""
    with live_errors():
        return await adapter.live_player_set(name, change, actor=actor)


# inventario live: il `ref` e' un percorso opaco (contiene `:` e `/`), quindi query param; capability `supports_live_inventory`
inventory_dep = Depends(require_capability("supports_live_inventory"))
RefQuery = Annotated[str, Query(min_length=1, max_length=128, description="`ref` di un oggetto, preso dall'ultima lettura dell'inventario")]


@router.get("/players/{name}/inventory", response_model=LiveInventory, dependencies=[inventory_dep])
async def get_inventory(name: PlayerName, adapter: LiveDep) -> LiveInventory:
    """Inventario ed equipaggiamento LIVE di un giocatore connesso (elenco piatto con `depth`, `ref`, `fp`). 409 `worldlive.command_disabled`
    se il MUD non ha la feature `inventory`."""
    with live_errors():
        return await adapter.live_player_inventory(name)


@router.get("/players/{name}/inventory/item", response_model=LiveItem, dependencies=[inventory_dep])
async def get_inventory_item(name: PlayerName, ref: RefQuery, adapter: LiveDep) -> LiveItem:
    """Un oggetto del giocatore, con i campi di sola lettura (404 `worldlive.not_found` se il `ref` non risolve)."""
    with live_errors():
        return await adapter.live_item_get(name, ref)


@router.patch("/players/{name}/inventory/item", response_model=LiveItemSetOut, dependencies=[inventory_dep])
async def set_inventory_item(
    name: PlayerName, ref: RefQuery, change: LiveItemSetIn, adapter: WriteLiveDep, actor: ActorDep
) -> LiveItemSetOut:
    """Modifica un oggetto. `expect {vnum, fp}` e' obbligatorio (422 senza); se non coincide 409 `worldlive.stale_ref` e nulla cambia."""
    with live_errors():
        return await adapter.live_item_set(name, ref, change, actor=actor)


@router.delete("/players/{name}/inventory/item", response_model=LiveItemRemoveOut, dependencies=[inventory_dep])
async def remove_inventory_item(
    name: PlayerName,
    ref: RefQuery,
    fp: Annotated[str, Query(pattern=r"^[0-9a-f]{8}$", description="`expect.fp` dell'ultima lettura (obbligatorio)")],
    adapter: WriteLiveDep,
    actor: ActorDep,
    vnum: Annotated[int | None, Query(description="`expect.vnum` (assente = `null`, oggetto senza prototipo)")] = None,
    save: bool = True,
) -> LiveItemRemoveOut:
    """Toglie e DISTRUGGE l'oggetto (e il contenuto se e' un contenitore). Senza `fp` 422; se non coincide 409 `worldlive.stale_ref`."""
    with live_errors():
        return await adapter.live_item_remove(name, ref, LiveItemExpect(vnum=vnum, fp=fp), save=save, actor=actor)


@router.post("/zones/reset", response_model=LiveZoneResetOut)
async def reset_zone(reset: LiveZoneResetIn, adapter: WriteLiveDep, actor: ActorDep) -> LiveZoneResetOut:
    """Forza il reset di una zona (`zone` = indice di `GET /zones`, oppure `room`). Mai ritentato: dopo un timeout l'esito e' sconosciuto."""
    with live_errors():
        return await adapter.live_zone_reset(reset, actor=actor)


@router.post("/zones/reload", response_model=LiveZoneReloadOut)
async def reload_zone(reload: LiveZoneReloadIn, adapter: WriteLiveDep, actor: ActorDep) -> LiveZoneReloadOut:
    """Il gioco rilegge dai file la zona `vnum` e rifa' il reset (estensione pachimud: 409 `worldlive.command_disabled` se il MUD non
    ha `zone.reload`). Mai ritentato: dopo un timeout l'esito e' sconosciuto."""
    with live_errors():
        return await adapter.live_zone_reload(reload, actor=actor)


@router.get("/content/validate", response_model=LiveContentValidateOut)
async def validate_content(adapter: LiveDep, strict: bool = False) -> LiveContentValidateOut:
    """Il gioco controlla i file dei contenuti come li carica (estensione pachimud, comando `content.validate`: altrove 409
    `worldlive.command_disabled`). `issues[]`: `severity`, `code`, `message`, `file`, `line`; con `strict` anche gli avvisi fanno `ok=false`."""
    with live_errors():
        return await adapter.live_content_validate(strict=strict)


@router.post("/content/reload", response_model=LiveContentReloadOut)
async def reload_content(reload: LiveContentReloadIn, adapter: WriteLiveDep, actor: ActorDep) -> LiveContentReloadOut:
    """Il gioco rilegge dai file razze, classi, skill, tabelle, social o cataloghi (`kind`: `races|classes|skills|tables|socials|locales|all`;
    estensione pachimud, comando `content.reload`). Tutto o niente: se un file non e' valido 409 `worldlive.content_reload_failed` con
    i problemi (`issues`) e il gioco resta com'era. Non tocca giocatori connessi, zone ne' hook Python. Mai ritentato."""
    with live_errors():
        return await adapter.live_content_reload(reload, actor=actor)


@router.get("/instances", response_model=LiveInstances)
async def instances(
    adapter: LiveDep,
    room_vnum: Annotated[int | None, Query(alias="roomVnum", ge=0)] = None,
    mob_vnum: Annotated[int | None, Query(alias="mobVnum", ge=0)] = None,
    obj_vnum: Annotated[int | None, Query(alias="objVnum", ge=0)] = None,
    zone_vnum: Annotated[int | None, Query(alias="zoneVnum", ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> LiveInstances:
    """Istanze in memoria nel gioco (estensione pachimud): **una sola** tra `roomVnum`, `mobVnum`, `objVnum`, `zoneVnum` (422 altrimenti)."""
    if sum(v is not None for v in (room_vnum, mob_vnum, obj_vnum, zone_vnum)) != 1:
        raise api_error(422, "worldlive.bad_params", field="roomVnum|mobVnum|objVnum|zoneVnum")
    with live_errors():
        return await adapter.live_instances(room_vnum=room_vnum, mob_vnum=mob_vnum, obj_vnum=obj_vnum, zone_vnum=zone_vnum, limit=limit)


@router.post("/load/mob", response_model=LiveLoadOut)
async def load_mob(load: LiveLoadIn, adapter: WriteLiveDep, actor: ActorDep) -> LiveLoadOut:
    """Crea mob in una stanza o nella stanza di un giocatore."""
    with live_errors():
        return await adapter.live_load("mob", load, actor=actor)


@router.post("/load/obj", response_model=LiveLoadOut)
async def load_obj(load: LiveLoadIn, adapter: WriteLiveDep, actor: ActorDep) -> LiveLoadOut:
    """Crea oggetti in una stanza o nell'inventario di un giocatore (deny-list del MUD: 409 `worldlive.object_denied`)."""
    with live_errors():
        return await adapter.live_load("obj", load, actor=actor)


@router.post("/echo", response_model=LiveEchoOut)
async def echo(message: LiveEchoIn, adapter: WriteLiveDep, actor: ActorDep) -> LiveEchoOut:
    """Manda un messaggio a tutti i giocatori, a uno o a una stanza."""
    with live_errors():
        return await adapter.live_echo(message, actor=actor)
