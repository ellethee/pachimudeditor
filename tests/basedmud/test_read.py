"""Lettura dell'adapter BasedMud sulle aree reali (copia): caricamento, conteggi, ricerca, paginazione, filtri."""

from pathlib import Path

from pachimudeditor_adapter_basedmud.rom_lib import load_area_file, read_area_list

from pachimudeditor_adapter_basedmud.adapter import BasedMudAdapter
from pachimudeditor.common.adapters.models import MobPageParams, ObjectPageParams, RoomPageParams, ZonePageParams
from tests.adapter_contract.helpers import expect_error


async def test_all_areas_load_and_counts_match_library(adapter: BasedMudAdapter, area_dir: Path) -> None:
    """Tutti i 53 file di `area.lst` si caricano; zone, stanze, mob e oggetti coincidono con i conteggi della libreria."""
    names = read_area_list(area_dir / "area.lst").names
    assert len(names) == 53
    adapter.sync()
    assert {n for n in names if n.endswith(".are")} <= set(adapter.store.entries)  # olc.hlp e' un file di help
    for n in names:
        load_area_file(area_dir / n)
    loaded = [load_area_file(area_dir / n) for n in sorted(adapter.store.entries)]
    zones = [a for a in loaded if a.header is not None]
    assert (await adapter.list_zones(ZonePageParams())).total == len(zones) == 49  # 48 elencate + proto.are
    for kind, page, attr in (
        ("rooms", await adapter.list_rooms(RoomPageParams()), "rooms"),
        ("mobs", await adapter.list_mobs(MobPageParams()), "mobiles"),
        ("objects", await adapter.list_objects(ObjectPageParams()), "objects"),
    ):
        expected = sum(len(getattr(a, attr)) for a in zones)
        assert page.total == expected, kind
    zone_page = await adapter.list_zones(ZonePageParams())
    assert [z.enabled for z in zone_page.items].count(False) == 1  # proto.are non e' in area.lst
    for zone in zone_page.items:
        summary = await adapter.zone_summary(zone.id)
        entry = adapter.store.zone_by_id(zone.id)
        assert summary.room_count == len(entry.items("room"))


async def test_zone_mapping(adapter: BasedMudAdapter) -> None:
    """Id = vnum minimo, livelli/builder dai credits, extra con file e credits."""
    zone = await adapter.get_zone(3000)
    assert (zone.id, zone.vnum, zone.name, zone.bottom_vnum, zone.top_vnum) == (3000, 3000, "Midgaard", 3000, 3399)
    assert zone.builder == "Diku" and (zone.min_level, zone.max_level) == (1, 60) and zone.enabled
    assert zone.extra["file"] == "midgaard.are" and zone.extra["style"] == "AREA"
    assert (await adapter.get_zone(0)).name == "Limbo"
    unlisted = [z for z in (await adapter.list_zones(ZonePageParams())).items if not z.enabled]
    assert unlisted[0].id < 0 and unlisted[0].extra["file"] == "proto.are"
    with expect_error(404, "zones.not_found"):
        await adapter.get_zone(424242)


async def test_search_paging_and_ordering(adapter: BasedMudAdapter) -> None:
    """Ricerca case-insensitive su nome/keywords/vnum, paginazione, ordinamento e filtro per zona."""
    found = await adapter.list_mobs(MobPageParams(search="WIZARD"))
    assert found.total >= 1 and all("wizard" in (m.keywords + m.short_description).lower() for m in found.items)
    assert [m.vnum for m in (await adapter.list_mobs(MobPageParams(search="3000"))).items][0] == 3000
    page = await adapter.list_rooms(RoomPageParams(page=2, pageSize=10, zone_id=3000))
    assert len(page.items) == 10 and page.page == 2 and page.pages == -(-page.total // 10)
    assert all(r.zone_id == 3000 for r in page.items)
    vnums = [r.vnum for r in (await adapter.list_rooms(RoomPageParams(zone_id=3000))).items]
    assert vnums == sorted(vnums)
    desc = await adapter.list_mobs(MobPageParams(order_by=None, orderBy="-level", pageSize=5, page=1))
    levels = [m.level for m in desc.items]
    assert levels == sorted(levels, reverse=True)
    zones = await adapter.list_zones(ZonePageParams(search="midgaard"))
    assert [z.id for z in zones.items] == [3000]
    assert (await adapter.list_zones(ZonePageParams(search="3000"))).total >= 1


async def test_details_and_usage(adapter: BasedMudAdapter) -> None:
    """Stanza con uscite ed extra, mob con negozio/special, oggetto, reset e uso dei vnum."""
    room = await adapter.get_room(3001)
    assert {e.direction.name for e in room.exits} == {"NORTH", "SOUTH", "UP"} and room.extra_descriptions[0].keywords == "plaque"
    assert room.extra["sector"] == 0 and "no_mob" in room.flags
    mob = await adapter.get_mob(3000)
    assert mob.extra["shop"]["profitBuy"] == 105 and mob.extra["special"] == "spec_cast_mage" and mob.race_id == "human"
    obj = await adapter.get_object(3000)
    assert obj.extra["itemType"] == "drink" and obj.extra["values"][2] == "beer" and obj.value_2 is None
    resets = await adapter.list_reset_commands(3000)
    assert resets[0].command_type.name == "LOAD_MOB" and resets[1].arg_str == "wielded"
    assert len(await adapter.mob_usage(3011)) >= 1
    graph = await adapter.room_graph(3000)
    assert len(graph.nodes) == 143 and graph.edges


async def test_meta_from_tables(adapter: BasedMudAdapter, area_dir: Path) -> None:
    """Razze e classi vengono da `src/tables.c` (vuote se manca); le enum includono le tabelle ROM."""
    assert await adapter.races() == [] and await adapter.classes() == []
    (area_dir.parent / "src").mkdir()
    (area_dir.parent / "src" / "tables.c").write_text(
        'const RACE_TYPE race_table[RACE_MAX + 1] = {\n    {"unique", FALSE, 0},\n    {"human", TRUE, 0},\n};\n'
        'const CLASS_TYPE class_table[CLASS_MAX + 1] = {\n    {CLASS_MAGE, "mage", "Mag"},\n    {0}\n};\n'
    )
    assert [r.id for r in await adapter.races()] == ["unique", "human"]
    assert [c.id for c in await adapter.classes()] == ["mage"]
    enums = await adapter.enums()
    assert {"sectorType", "romRoomFlags", "romMobFlags", "romItemType", "romSectorType"} <= set(enums)
    assert any(o.label == "no_mob" for o in enums["romRoomFlags"])
    info = adapter.describe()
    room = next(r for r in info.resources if r.type == "room")
    assert next(f for f in room.fields if f.name == "flags").enum == "romRoomFlags"
    assert info.capabilities.supports_reset_scripts and not info.capabilities.supports_players


async def test_cache_follows_external_changes(adapter: BasedMudAdapter, area_dir: Path) -> None:
    """Una modifica esterna del file (mtime/size) e' vista alla richiesta successiva."""
    assert (await adapter.get_mob(3000)).level == 23
    path = area_dir / "midgaard.are"
    text = path.read_text(encoding="latin-1")
    path.write_text(text.replace("23 0 1d1+999", "24 0 1d1+999", 1), encoding="latin-1")
    assert (await adapter.get_mob(3000)).level == 24
