"""Zone: CRUD di base, script di reset, vnum liberi e clonazione. Prefisso `/api/zones`.

Router sottile: la logica sta nell'adapter del mondo attivo (`common.adapters`). I DTO sono in
`common.adapters.models`.
"""

from typing import Annotated, Literal

from fastapi import Query
from pachifast.router_factory import get_router
from pachifast.schemas.responses import PaginatedResponse

from pachimudeditor.common.adapters.models import (
    NextZoneVnum,
    ResetCommandOut,
    ResetDraftScriptIn,
    ResetScriptIn,
    ResetValidation,
    ZoneCloneIn,
    ZoneIn,
    ZoneOut,
    ZonePageParams,
    ZonePatch,
    ZoneSummary,
)
from pachimudeditor.common.adapters.registry import AdapterDep, WriteAdapterDep

router = get_router()


@router.get("", response_model=PaginatedResponse[ZoneOut])
async def list_zones(params: Annotated[ZonePageParams, Query()], adapter: AdapterDep) -> PaginatedResponse[ZoneOut]:
    """Zone paginate, cercabili per nome/builder/vnum; ordine di default per vnum."""
    return await adapter.list_zones(params)


@router.post("", response_model=ZoneOut, status_code=201)
async def create_zone(data: ZoneIn, adapter: WriteAdapterDep) -> ZoneOut:
    """Crea una zona (il vnum deve essere libero)."""
    return await adapter.create_zone(data)


@router.get("/next-vnum", response_model=NextZoneVnum)
async def next_zone_vnum(adapter: AdapterDep, span: Annotated[int, Query(ge=0, le=100000)] = 99) -> NextZoneVnum:
    """Un vnum di zona libero e un range `span` ampio che non tocca nessun'altra zona."""
    return await adapter.next_zone_vnum(span)


@router.get("/{zone_id}", response_model=ZoneOut)
async def get_zone(zone_id: int, adapter: AdapterDep) -> ZoneOut:
    """Una zona."""
    return await adapter.get_zone(zone_id)


@router.put("/{zone_id}", response_model=ZoneOut)
async def update_zone(zone_id: int, data: ZonePatch, adapter: WriteAdapterDep) -> ZoneOut:
    """Aggiornamento parziale di una zona; i range finali (vnum e livelli) devono restare coerenti
    (422 `zones.invalid_vnum_range` / `zones.invalid_level_range`) anche se il patch ne cambia solo un estremo."""
    return await adapter.update_zone(zone_id, data)


@router.delete("/{zone_id}", status_code=204, response_model=None, skip_envelope=True)
async def delete_zone(zone_id: int, adapter: WriteAdapterDep) -> None:
    """Elimina una zona: 409 `zones.not_empty` finche' contiene ancora stanze, mob o oggetti."""
    await adapter.delete_zone(zone_id)


@router.get("/{zone_id}/summary", response_model=ZoneSummary)
async def zone_summary(zone_id: int, adapter: AdapterDep) -> ZoneSummary:
    """Conteggi del contenuto di una zona."""
    return await adapter.zone_summary(zone_id)


@router.get("/{zone_id}/next-vnum", response_model=int)
async def next_content_vnum(zone_id: int, adapter: AdapterDep, kind: Annotated[Literal["room", "mob", "object"], Query()]) -> int:
    """Un vnum libero per una nuova stanza/mob/oggetto della zona."""
    return await adapter.next_content_vnum(zone_id, kind)


@router.post("/{zone_id}/clone", response_model=ZoneOut, status_code=201)
async def clone_zone(zone_id: int, data: ZoneCloneIn, adapter: WriteAdapterDep) -> ZoneOut:
    """Duplica una zona (non il suo contenuto) con un nuovo vnum/nome; opzionalmente copia anche lo script di
    reset (i vnum restano quelli originali). Range della copia: quello nel body (409 `zones.range_overlap`
    se si sovrappone) oppure 0-0."""
    return await adapter.clone_zone(zone_id, data)


@router.get("/{zone_id}/reset-commands", response_model=list[ResetCommandOut])
async def list_reset_commands(zone_id: int, adapter: AdapterDep) -> list[ResetCommandOut]:
    """Lo script di reset della zona, in ordine."""
    return await adapter.list_reset_commands(zone_id)


@router.put("/{zone_id}/reset-commands", response_model=list[ResetCommandOut])
async def replace_reset_commands(zone_id: int, data: ResetScriptIn, adapter: WriteAdapterDep) -> list[ResetCommandOut]:
    """Sostituisce l'intero script di reset, rinumerando `orderIndex` 0..n-1 per posizione nella lista.

    Oltre alla validazione per tipo di `ResetCommandIn`, ogni vnum di mob/oggetto/stanza referenziato deve
    esistere: altrimenti 422 `zones.reset_unknown_mob|object|room` (params `index`, `vnum`) e nulla viene salvato."""
    return await adapter.replace_reset_commands(zone_id, data)


@router.post("/{zone_id}/reset-commands/validate", response_model=ResetValidation)
async def validate_reset_commands(zone_id: int, data: ResetDraftScriptIn, adapter: AdapterDep) -> ResetValidation:
    """Controlla uno script di reset senza salvarlo: `issues` per passo (`index` 0-based, `severity`
    error|warning, `code`, `params`, `message`). Il body e' `{commands: [...]}` come il PUT, ma i
    problemi dei singoli comandi sono riportati qui invece di dare 422."""
    return await adapter.validate_reset_commands(zone_id, data)
