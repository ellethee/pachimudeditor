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


def _expected(everything: list, field: str, desc: bool) -> list[int]:
    """Ids ordinati per `field` (nulli in fondo in entrambe le direzioni, a parita' il vnum: `everything` e' gia' per vnum)."""
    have = sorted((o for o in everything if getattr(o, field) is not None), key=lambda o: getattr(o, field), reverse=desc)
    return [o.id for o in have] + [o.id for o in everything if getattr(o, field) is None]


async def _assert_orderings(list_fn, params_cls, everything: list, fields: tuple[str, ...]) -> None:  # type: ignore[no-untyped-def]
    """Ogni ordinamento (camelCase e snake_case, asc e desc) coincide con quello di riferimento."""
    from pachifast.utils.helpers import to_camel

    for field in fields:
        for desc in (False, True):
            want = _expected(everything, field, desc)
            for name in {to_camel(field), field}:
                key = ("-" if desc else "") + name
                assert [o.id for o in (await list_fn(params_cls(orderBy=key))).items] == want, key


async def assert_mob_queries_match_oracle(adapter: WorldAdapter) -> None:
    """Confronta `list_mobs` con un'implementazione di riferimento sui dati reali dell'adapter: filtri, ordinamenti
    (nulli in fondo) e le loro combinazioni danno gli stessi risultati di un filtro/ordinamento in Python sulla lista completa."""
    from pachimudeditor.common.adapters import mob_query
    from pachimudeditor.common.adapters.models import MobPageParams

    everything = (await adapter.list_mobs(MobPageParams())).items
    assert everything, "serve un mondo con mob"
    ids = lambda page: [m.id for m in page.items]  # noqa: E731
    for field in mob_query.RANGE_FIELDS:
        samples = sorted({getattr(m, field) for m in everything})
        low, high = samples[len(samples) // 3], samples[2 * len(samples) // 3]
        want = [m.id for m in everything if low <= getattr(m, field) <= high]
        assert ids(await adapter.list_mobs(MobPageParams(**{f"min_{field}": low, f"max_{field}": high}))) == want, field
        assert ids(await adapter.list_mobs(MobPageParams(**{f"min_{field}": high}))) == [
            m.id for m in everything if getattr(m, field) >= high
        ]
        assert ids(await adapter.list_mobs(MobPageParams(**{f"max_{field}": low}))) == [
            m.id for m in everything if getattr(m, field) <= low
        ]
    await _assert_orderings(
        adapter.list_mobs,
        MobPageParams,
        everything,
        ("id", "vnum", "zone_id", "short_description", "sex", "race_id", "class_id", *mob_query.RANGE_FIELDS),
    )
    sexes = sorted({int(m.sex) for m in everything})
    assert ids(await adapter.list_mobs(MobPageParams(sex=sexes[:1]))) == [m.id for m in everything if int(m.sex) in sexes[:1]]
    assert ids(await adapter.list_mobs(MobPageParams(sex=sexes))) == [m.id for m in everything]
    for flag in sorted({f for m in everything for f in m.flags}):
        want = [m.id for m in everything if flag in m.flags]
        assert ids(await adapter.list_mobs(MobPageParams(flag=[flag]))) == want, flag
        assert ids(await adapter.list_mobs(MobPageParams(flag=[flag.upper()]))) == want, flag
    for wanted in (True, False):  # nei mondi che non lo sanno `is_trainer` e' nullo e il filtro non esclude nulla
        assert ids(await adapter.list_mobs(MobPageParams(trainer=wanted))) == [m.id for m in everything if m.is_trainer in (None, wanted)]
    for attr in ("race_id", "class_id"):
        values = sorted({getattr(m, attr) for m in everything if getattr(m, attr)})
        for value in values:
            assert ids(await adapter.list_mobs(MobPageParams(**{attr: [value]}))) == [m.id for m in everything if getattr(m, attr) == value]
        if values:  # senza valori il filtro e' vuoto, quindi assente
            assert ids(await adapter.list_mobs(MobPageParams(**{attr: values}))) == [m.id for m in everything if getattr(m, attr) in values]
    zone_ids = sorted({m.zone_id for m in everything})
    first = (await adapter.list_mobs(MobPageParams(zone_id=zone_ids[0], min_level=0, orderBy="-level"))).items
    assert [m.id for m in first] == [i for i in _expected([m for m in everything if m.zone_id == zone_ids[0]], "level", True)]


async def assert_room_queries_match_oracle(adapter: WorldAdapter) -> None:
    """Come `assert_mob_queries_match_oracle`, per `list_rooms`."""
    from pachimudeditor.common.adapters import room_query
    from pachimudeditor.common.adapters.models import RoomPageParams

    everything = (await adapter.list_rooms(RoomPageParams())).items
    assert everything, "serve un mondo con stanze"
    ids = lambda page: [r.id for r in page.items]  # noqa: E731
    for field in room_query.RANGE_FIELDS:
        samples = sorted({getattr(r, field) for r in everything})
        low, high = samples[len(samples) // 3], samples[2 * len(samples) // 3]
        want = [r.id for r in everything if low <= getattr(r, field) <= high]
        assert ids(await adapter.list_rooms(RoomPageParams(**{f"min_{field}": low, f"max_{field}": high}))) == want, field
    await _assert_orderings(
        adapter.list_rooms,
        RoomPageParams,
        everything,
        ("id", "vnum", "name", "sector_type", "zone_id", "heal_rate", "mana_rate", "clan_id", "owner"),
    )
    sectors = sorted({int(r.sector_type) for r in everything})
    assert ids(await adapter.list_rooms(RoomPageParams(sector_type=sectors[:1]))) == [
        r.id for r in everything if int(r.sector_type) in sectors[:1]
    ]
    for flag in sorted({f for r in everything for f in r.flags}):
        want = [r.id for r in everything if flag in r.flags]
        assert ids(await adapter.list_rooms(RoomPageParams(flag=[flag]))) == want, flag
    for clan in sorted({r.clan_id for r in everything if r.clan_id}):
        assert ids(await adapter.list_rooms(RoomPageParams(clan_id=[clan]))) == [r.id for r in everything if r.clan_id == clan]
    for owner in sorted({r.owner for r in everything if r.owner}):
        want = [r.id for r in everything if r.owner and owner[:3].lower() in r.owner.lower()]
        assert ids(await adapter.list_rooms(RoomPageParams(owner=owner[:3].upper()))) == want
