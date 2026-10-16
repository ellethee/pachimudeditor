"""Helper della suite di contratto: costruzione dei DTO e asserzioni sugli errori HTTP."""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from pachimudeditor.common.adapters.base import WorldAdapter
from pachimudeditor.common.adapters.models import MobIn, ObjectIn, RoomIn, ZoneIn, ZoneOut


@contextmanager
def expect_error(status: int, code: str) -> Iterator[None]:
    """Il blocco deve alzare un `HTTPException` con lo `status` e il `code` stabile indicati."""
    try:
        yield
    except HTTPException as error:
        assert error.status_code == status, (error.status_code, error.detail)
        assert error.detail[0]["code"] == code, error.detail
    else:
        raise AssertionError(f"atteso {status} {code}, nessun errore")


async def new_zone(adapter: WorldAdapter, name: str = "Zona contratto") -> ZoneOut:
    """Crea una zona nel prossimo range libero e la restituisce."""
    free = await adapter.next_zone_vnum(99)
    return await adapter.create_zone(
        ZoneIn(vnum=free.vnum, name=name, builder="contratto", bottom_vnum=free.bottom_vnum, top_vnum=free.top_vnum)
    )


async def new_room(adapter: WorldAdapter, zone: ZoneOut, name: str = "Stanza"):  # type: ignore[no-untyped-def]
    """Crea una stanza nella zona al prossimo vnum libero."""
    vnum = await adapter.next_content_vnum(zone.id, "room")
    return await adapter.create_room(RoomIn(vnum=vnum, zone_id=zone.id, name=name))


async def new_mob(adapter: WorldAdapter, zone: ZoneOut, keywords: str = "orco"):  # type: ignore[no-untyped-def]
    """Crea un mob nella zona al prossimo vnum libero."""
    vnum = await adapter.next_content_vnum(zone.id, "mob")
    return await adapter.create_mob(MobIn(vnum=vnum, zone_id=zone.id, keywords=keywords, short_description=f"un {keywords}"))


async def new_object(adapter: WorldAdapter, zone: ZoneOut, keywords: str = "spada"):  # type: ignore[no-untyped-def]
    """Crea un oggetto nella zona al prossimo vnum libero."""
    vnum = await adapter.next_content_vnum(zone.id, "object")
    return await adapter.create_object(ObjectIn(vnum=vnum, zone_id=zone.id, keywords=keywords, short_description=f"una {keywords}"))
