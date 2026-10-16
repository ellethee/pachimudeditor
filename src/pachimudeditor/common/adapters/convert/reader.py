"""Lettura dai mondi (solo tramite l'interfaccia `WorldAdapter`): contenuto delle zone sorgente e indice dell'arrivo."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from pachifast.i18n import api_error

from pachimudeditor.common.adapters.base import WorldAdapter
from pachimudeditor.common.adapters.models import (
    MobOut,
    MobPageParams,
    ObjectOut,
    ObjectPageParams,
    ResetCommandOut,
    RoomDetail,
    RoomPageParams,
    ZoneOut,
    ZonePageParams,
)

PAGE_SIZE = 200


async def collect(fetch: Callable[[int], Awaitable[Any]]) -> list[Any]:
    """Tutti gli elementi di una lista paginata: `fetch(pagina)` restituisce una `PaginatedResponse`."""
    items: list[Any] = []
    page = 1
    while True:
        result = await fetch(page)
        items.extend(result.items)
        if not result.items or len(items) >= result.total:
            return items
        page += 1


@dataclass
class SourceZone:
    """Una zona con tutto il suo contenuto, come l'adapter la restituisce."""

    zone: ZoneOut
    rooms: list[RoomDetail] = field(default_factory=list)
    mobs: list[MobOut] = field(default_factory=list)
    objects: list[ObjectOut] = field(default_factory=list)
    resets: list[ResetCommandOut] = field(default_factory=list)

    @property
    def vnums(self) -> list[int]:
        """Tutti i vnum di contenuto della zona."""
        return [*(r.vnum for r in self.rooms), *(m.vnum for m in self.mobs), *(o.vnum for o in self.objects)]


async def list_all_zones(adapter: WorldAdapter) -> list[ZoneOut]:
    """Tutte le zone del mondo."""
    return await collect(lambda p: adapter.list_zones(ZonePageParams(page=p, pageSize=PAGE_SIZE)))


async def read_zone(adapter: WorldAdapter, zone_id: int, *, with_resets: bool = True) -> SourceZone:
    """Zona, stanze (con uscite ed extra description), mob, oggetti e script di reset; 404 `convert.zone_not_found`."""
    try:
        zone = await adapter.get_zone(zone_id)
    except HTTPException as error:
        if error.status_code == 404:
            raise api_error(404, "convert.zone_not_found", zone=zone_id) from error
        raise
    rooms_out = await collect(lambda p: adapter.list_rooms(RoomPageParams(page=p, pageSize=PAGE_SIZE, zone_id=zone.id)))
    rooms = [await adapter.get_room(r.id) for r in rooms_out]
    mobs = await collect(lambda p: adapter.list_mobs(MobPageParams(page=p, pageSize=PAGE_SIZE, zone_id=zone.id)))
    objects = await collect(lambda p: adapter.list_objects(ObjectPageParams(page=p, pageSize=PAGE_SIZE, zone_id=zone.id)))
    resets = await adapter.list_reset_commands(zone.id) if with_resets else []
    return SourceZone(zone, rooms, mobs, objects, resets)


@dataclass
class TargetIndex:
    """Cosa esiste gia' nel mondo di arrivo (per conflitti e riferimenti fuori dalla conversione)."""

    zones: list[ZoneOut]
    rooms: dict[int, tuple[int, int]]
    """vnum -> (id, zone_id)."""
    mobs: dict[int, int]
    """vnum -> zone_id."""
    objects: dict[int, int]


async def read_target_index(adapter: WorldAdapter) -> TargetIndex:
    """Zone, stanze, mob e oggetti del mondo di arrivo (solo vnum/id/zona)."""
    zones = await list_all_zones(adapter)
    rooms = await collect(lambda p: adapter.list_rooms(RoomPageParams(page=p, pageSize=PAGE_SIZE)))
    mobs = await collect(lambda p: adapter.list_mobs(MobPageParams(page=p, pageSize=PAGE_SIZE)))
    objects = await collect(lambda p: adapter.list_objects(ObjectPageParams(page=p, pageSize=PAGE_SIZE)))
    return TargetIndex(
        zones=zones,
        rooms={r.vnum: (r.id, r.zone_id) for r in rooms},
        mobs={m.vnum: m.zone_id for m in mobs},
        objects={o.vnum: o.zone_id for o in objects},
    )
