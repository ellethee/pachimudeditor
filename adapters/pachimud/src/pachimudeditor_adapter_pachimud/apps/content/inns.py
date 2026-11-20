"""Locande del gioco: i mob con `receptionist: true` e le stanze dove un reset li carica. Prefisso `/api/content`.

Una locanda non e' un file: e' il flag `receptionist` del mob (si modifica nella scheda del mob); con il mob nella stanza
funzionano `offer` e `rent`. Qui c'e' solo la vista d'insieme, con le stanze risolte per nome (da tutte le zone: un mob puo'
essere caricato da un reset di un'altra zona).
"""

from pachifast.database import AliasedBaseModel
from pachifast.router_factory import get_router

from fastapi import Depends
from pachimudeditor.common.enums import ZoneCommandType
from pachimudeditor.sdk import require_capability
from pachimudeditor_adapter_pachimud import resets
from pachimudeditor_adapter_pachimud.editor.db import PachimudDep

router = get_router(name="content", deps=[Depends(require_capability("supports_content_races"))])


class InnRoom(AliasedBaseModel):
    """Una stanza dove un reset carica il locandiere."""

    vnum: int
    name: str | None
    """Nome della stanza; `None` se non esiste (il reset punta a una stanza inesistente)."""


class InnItem(AliasedBaseModel):
    """Un locandiere: il mob e le stanze dove compare."""

    vnum: int
    name: str
    zone_id: int
    zone_name: str
    rooms: list[InnRoom] = []
    """Vuoto = nessun reset lo carica: `offer` e `rent` non si possono usare."""


@router.get("/inns", response_model=list[InnItem])
async def list_inns(adapter: PachimudDep) -> list[InnItem]:
    """I mob `receptionist`, in ordine di vnum, con le stanze dove un reset li carica."""
    store = adapter.sync()
    names = store.room_names()
    spawns: dict[int, list[int]] = {}
    for zone in store.zones:
        for kind, mob, _max, room, *_ in resets.flatten(zone):
            if kind == ZoneCommandType.LOAD_MOB and mob is not None and room is not None and room not in spawns.setdefault(mob, []):
                spawns[mob].append(room)
    return [
        InnItem(
            vnum=mob.vnum,
            name=mob.model.short_description,
            zone_id=mob.zone.vnum,
            zone_name=mob.zone.model.name,
            rooms=[InnRoom(vnum=room, name=names.get(room)) for room in spawns.get(mob.vnum, [])],
        )
        for mob in sorted(store.all_items("mob"), key=lambda m: m.vnum)
        if mob.model.receptionist
    ]
