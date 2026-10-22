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


async def assert_object_queries_match_oracle(adapter: WorldAdapter) -> None:
    """Confronta `list_objects` con un'implementazione di riferimento sui dati reali dell'adapter: nuovi filtri, ordinamenti
    (nulli in fondo) e la loro combinazione danno gli stessi risultati di un filtro/ordinamento in Python sulla lista completa."""
    from pachimudeditor.common.adapters.models import ObjectPageParams

    everything = (await adapter.list_objects(ObjectPageParams())).items
    assert everything, "serve un mondo con oggetti"
    ints = ("weight", "cost", "rent", "value_0", "value_1", "value_2", "value_3")
    samples = sorted({v for o in everything for f in ints if (v := getattr(o, f)) is not None})
    low, high = samples[len(samples) // 3], samples[2 * len(samples) // 3]
    types = sorted({int(o.object_type) for o in everything})[:2]
    flags = sorted({f for o in everything for f in o.extra_flags} | {f for o in everything for f in o.wear_flags})
    for field in ints:
        want = [o.id for o in everything if getattr(o, field) is not None and low <= getattr(o, field) <= high]
        got = (await adapter.list_objects(ObjectPageParams(**{f"min_{field}": low, f"max_{field}": high}))).items
        assert [o.id for o in got] == want, field
        for desc in (False, True):
            key = ("-" if desc else "") + field.replace("_", "")
            have = sorted((o for o in everything if getattr(o, field) is not None), key=lambda o: getattr(o, field), reverse=desc)
            want_order = [o.id for o in have] + [o.id for o in everything if getattr(o, field) is None]
            assert [o.id for o in (await adapter.list_objects(ObjectPageParams(orderBy=key))).items] == want_order, key
    assert [o.id for o in (await adapter.list_objects(ObjectPageParams(object_type=types))).items] == [
        o.id for o in everything if int(o.object_type) in types
    ]
    for flag in flags:
        want = [o.id for o in everything if flag in o.extra_flags]
        assert [o.id for o in (await adapter.list_objects(ObjectPageParams(extra_flag=[flag]))).items] == want, flag
        want = [o.id for o in everything if flag in o.wear_flags]
        assert [o.id for o in (await adapter.list_objects(ObjectPageParams(wear_flag=[flag]))).items] == want, flag
    for apply in sorted({a for o in everything for a in o.affects}):
        want = [o.id for o in everything if apply in o.affects]
        assert [o.id for o in (await adapter.list_objects(ObjectPageParams(affect=apply))).items] == want, apply
