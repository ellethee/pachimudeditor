"""Lettura dell'adapter Diku Modificato sul mondo sintetico (`tests/support/synthetic_worlds.py`): gira sempre, anche in CI."""

from pathlib import Path

import pytest
from pachimudeditor_adapter_dikumod.adapter import DikumodAdapter

from pachimudeditor.common.adapters.models import MobPageParams, ObjectPageParams, RoomPageParams, ZonePageParams
from pachimudeditor.common.adapters.registry import WorldConfig
from tests.adapter_contract.helpers import expect_error
from tests.support.synthetic_worlds import write_dikumod_world


@pytest.fixture
def ro(tmp_path: Path) -> DikumodAdapter:
    """Adapter con la configurazione di default (sola lettura) sul mondo sintetico."""
    return DikumodAdapter(WorldConfig(id="syn", kind="dikumod", name="Sintetico", path=str(write_dikumod_world(tmp_path / "lib"))))


async def test_counts_and_zone_ranges(ro: DikumodAdapter) -> None:
    """Conteggi, id di zona = posizione, range derivato dal `top` della zona precedente."""
    assert (await ro.list_rooms(RoomPageParams())).total == 5
    assert (await ro.list_mobs(MobPageParams())).total == 3
    assert (await ro.list_objects(ObjectPageParams())).total == 5
    zones = (await ro.list_zones(ZonePageParams())).items
    assert [(z.id, z.bottom_vnum, z.top_vnum) for z in zones] == [(0, 0, 0), (1, 1, 99), (2, 100, 199)]
    assert ro.capabilities().read_only
    assert [r.vnum for r in (await ro.list_rooms(RoomPageParams(zone_id=1))).items] == [1, 2, 3]


async def test_room_mob_object_and_reset_mapping(ro: DikumodAdapter) -> None:
    """Uscite con porta ed extra, mob con negozio, oggetto con affect, comandi di reset tradotti."""
    room = await ro.get_room(1)
    door = next(e for e in room.exits if int(e.direction) == 1)
    assert door.target_room_id == 3 and door.key_vnum == 4 and room.extra_descriptions[0].keywords == "fontana"
    mob = await ro.get_mob(2)
    assert mob.extra["shop"]["profitBuy"] == 1.5 and mob.extra["shop"]["producing"][0] == 3
    assert (await ro.get_mob(100)).extra["kind"] == "A" and (await ro.get_object(1)).affects == {"hitroll": 2}
    commands = await ro.list_reset_commands(1)
    assert [c.command_type.name for c in commands][:3] == ["LOAD_MOB", "EQUIP_OBJECT", "LOAD_MOB"]
    assert len(await ro.mob_usage(1)) >= 1
    with expect_error(404, "rooms.not_found"):
        await ro.get_room(424242)


async def test_search_and_paging(ro: DikumodAdapter) -> None:
    """Ricerca su nome/keywords/vnum e paginazione."""
    found = await ro.list_mobs(MobPageParams(search="MERCANTE"))
    assert [m.vnum for m in found.items] == [2]
    page = await ro.list_rooms(RoomPageParams(page=2, pageSize=2))
    assert page.total == 5 and page.page == 2 and len(page.items) == 2
