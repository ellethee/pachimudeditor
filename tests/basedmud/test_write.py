"""Scritture dell'adapter BasedMud: fedelta' byte per byte, area.lst, sola lettura, sicurezza dei nomi, concorrenza."""

import asyncio
import re
from pathlib import Path

import pytest
from pachimudeditor_adapter_basedmud.rom_lib import read_area_list

from pachimudeditor_adapter_basedmud.adapter import BasedMudAdapter
from pachimudeditor.common.adapters.models import (
    ExitIn,
    ExitPatch,
    ExtraDescriptionIn,
    MobIn,
    MobPageParams,
    MobPatch,
    ObjectPatch,
    ResetCommandIn,
    ResetScriptIn,
    RoomIn,
    RoomPageParams,
    RoomPatch,
    ZoneIn,
    ZonePatch,
)
from pachimudeditor.common.enums import ZoneCommandType
from pachimudeditor.common.enums import Direction, DoorFlag
from tests.adapter_contract.helpers import expect_error


def _block(text: str, vnum: int) -> tuple[int, int]:
    """Intervallo `[inizio, fine)` del blocco `#vnum` (fino al prossimo `#<numero>` o `#0`)."""
    start = text.index(f"\n#{vnum}\n") + 1
    nxt = re.compile(r"\n#\d+\n").search(text, start + 1)
    end = nxt.start() + 1 if nxt else len(text)
    return start, end


@pytest.mark.real_rom
async def test_edit_mob_changes_only_its_bytes(adapter: BasedMudAdapter, area_dir: Path) -> None:
    """Modificare un mob riscrive solo il suo blocco: prefisso e suffisso del file restano identici."""
    path = area_dir / "midgaard.are"
    before = path.read_bytes().decode("latin-1")
    await adapter.update_mob(3000, MobPatch(level=30, short_description="the grand wizard"))
    after = path.read_bytes().decode("latin-1")
    start, end = _block(before, 3000)
    new_start, new_end = _block(after, 3000)
    assert before[:start] == after[:new_start] and before[end:] == after[new_end:]
    assert before[start:end] != after[new_start:new_end] and "the grand wizard" in after[new_start:new_end]
    mob = await adapter.get_mob(3000)
    assert mob.level == 30 and mob.extra["shop"]["profitBuy"] == 105  # il negozio e' intatto


@pytest.mark.real_rom
async def test_echoing_dtos_is_a_noop(adapter: BasedMudAdapter, area_dir: Path) -> None:
    """Rimandare come patch l'intero DTO letto (extra compreso) non cambia un solo byte del file."""
    path = area_dir / "midgaard.are"
    before = path.read_bytes()
    for mob in (await adapter.list_mobs(MobPageParams(zone_id=3000))).items:
        await adapter.update_mob(mob.id, MobPatch.model_validate(mob.model_dump(by_alias=True, exclude={"id"})))
    for room in (await adapter.list_rooms(RoomPageParams(zone_id=3000))).items:
        await adapter.update_room(room.id, RoomPatch.model_validate(room.model_dump(by_alias=True, exclude={"id"})))
    from pachimudeditor.common.adapters.models import ObjectPageParams

    for obj in (await adapter.list_objects(ObjectPageParams(zone_id=3000))).items:
        await adapter.update_object(obj.id, ObjectPatch.model_validate(obj.model_dump(by_alias=True, exclude={"id"})))
    zone = await adapter.get_zone(3000)
    await adapter.update_zone(3000, ZonePatch.model_validate(zone.model_dump(by_alias=True, exclude={"id"})))
    script = await adapter.list_reset_commands(3000)
    await adapter.replace_reset_commands(
        3000, ResetScriptIn(commands=[ResetCommandIn.model_validate(c.model_dump(by_alias=True)) for c in script])
    )
    assert path.read_bytes() == before


@pytest.mark.real_rom
async def test_object_room_and_exit_edits(adapter: BasedMudAdapter, area_dir: Path) -> None:
    """Oggetto, stanza, uscita ed extra description: round trip dei valori ROM (flag, settore, porte, extra)."""
    obj = await adapter.update_object(3000, ObjectPatch(cost=99, extra={"values": ["300", "300", "wine", "0", "0"]}))
    assert obj.cost == 99 and obj.extra["values"][2] == "wine"
    room = await adapter.update_room(3001, RoomPatch(flags=["dark", "indoors"], extra={"sector": 10}))
    assert room.flags == ["dark", "indoors"] and room.extra["sector"] == 10
    with expect_error(422, "basedmud.unknown_flag"):
        await adapter.update_room(3001, RoomPatch(flags=["nonesiste"]))
    with expect_error(422, "basedmud.extra_unknown"):
        await adapter.update_room(3001, RoomPatch(extra={"boh": 1}))
    exit_ = next(e for e in room.exits if e.direction is Direction.SOUTH)
    door = await adapter.update_exit(3001, exit_.id, ExitPatch(door_flag=DoorFlag.PICKPROOF, is_open=False, key_vnum=3000))
    assert (door.door_flag, door.is_open, door.is_locked, door.key_vnum) == (DoorFlag.PICKPROOF, False, False, 3000)
    assert any(
        c.command_type is ZoneCommandType.SET_DOOR_STATE and c.arg1 == 3001 and c.arg_str == "CLOSED"
        for c in await adapter.list_reset_commands(3000)
    )
    text = (area_dir / "midgaard.are").read_text(encoding="latin-1")
    assert re.search(r"D2\n.*\n~\n2 3000 3005\n", text) or "2 3000 3005" in text
    await adapter.delete_exit(3001, door.id)
    assert not any(c.arg1 == 3001 and c.command_type is ZoneCommandType.SET_DOOR_STATE for c in await adapter.list_reset_commands(3000))
    extra = await adapter.create_extra_description(3001, ExtraDescriptionIn(keywords="ratto", text="Squit."))
    assert extra.id == 3001 * 1000 + 1 and len((await adapter.get_room(3001)).extra_descriptions) == 2
    new_exit = await adapter.create_exit(3001, ExitIn(direction=Direction.WEST, target_room_id=3005))
    assert new_exit.id == 30013 and new_exit.target_room_name == "The Temple Square"


@pytest.mark.real_rom
async def test_vnum_change_follows_references(adapter: BasedMudAdapter) -> None:
    """Un vnum usato da un reset non cambia; altrimenti uscite entranti, negozio e special seguono il nuovo vnum."""
    with expect_error(409, "rooms.vnum_in_use"):
        await adapter.update_room(3001, RoomPatch(vnum=3390))
    with expect_error(409, "mobs.vnum_in_use"):
        await adapter.update_mob(3011, MobPatch(vnum=3390))
    with expect_error(409, "rooms.vnum_taken"):
        await adapter.update_room(3001, RoomPatch(vnum=3005))
    a = await adapter.create_room(RoomIn(vnum=3390, zone_id=3000, name="A"))
    b = await adapter.create_room(RoomIn(vnum=3391, zone_id=3000, name="B"))
    await adapter.create_exit(a.id, ExitIn(direction=Direction.EAST, target_room_id=b.id))
    moved = await adapter.update_room(b.id, RoomPatch(vnum=3392))
    assert moved.id == 3392 and (await adapter.get_room(3390)).exits[0].target_room_id == 3392
    await adapter.delete_room(3392)
    dangling = (await adapter.get_room(3390)).exits[0]
    assert dangling.target_room_id is None and dangling.target_room_vnum is None
    mob = await adapter.create_mob(
        MobIn(
            vnum=3393,
            zone_id=3000,
            keywords="oste",
            short_description="un oste",
            extra={"shop": {"buyTypes": ["food"]}, "special": "spec_fido"},
        )
    )
    moved_mob = await adapter.update_mob(mob.id, MobPatch(vnum=3394))
    assert moved_mob.extra["shop"]["buyTypes"][0] == "food" and moved_mob.extra["special"] == "spec_fido"
    zone = await adapter.create_zone(ZoneIn(vnum=1, name="Altro", bottom_vnum=40000, top_vnum=40099))
    shifted = await adapter.update_mob(3394, MobPatch(vnum=40001, zone_id=zone.id))
    assert shifted.zone_id == zone.id and shifted.extra["special"] == "spec_fido" and shifted.extra["shop"]
    assert (await adapter.list_mobs(MobPageParams(zone_id=3000))).total == 65


@pytest.mark.real_rom
async def test_delete_mob_removes_shop_and_special(adapter: BasedMudAdapter, area_dir: Path) -> None:
    """Eliminare un mob toglie anche il suo negozio e la sua spec_fun (se nessun reset lo usa)."""
    mob = await adapter.create_mob(
        MobIn(
            vnum=3390,
            zone_id=3000,
            keywords="tester",
            short_description="un tester",
            extra={"shop": {"buyTypes": ["weapon"], "profitBuy": 120}, "special": "spec_fido"},
        )
    )
    assert mob.extra["shop"]["buyTypes"][0] == "weapon" and mob.extra["special"] == "spec_fido" and "npc" in mob.flags
    text = (area_dir / "midgaard.are").read_text(encoding="latin-1")
    assert re.search(r"^M\s+3390\s+spec_fido", text, re.M) and re.search(r"^\s*3390\s", text, re.M)
    await adapter.delete_mob(3390)
    text = (area_dir / "midgaard.are").read_text(encoding="latin-1")
    assert "3390" not in text


@pytest.mark.real_rom
async def test_area_list_edits(adapter: BasedMudAdapter, area_dir: Path) -> None:
    """Creare/disabilitare/riabilitare/eliminare una zona modifica `area.lst` mantenendo il `$` finale."""
    zone = await adapter.create_zone(ZoneIn(vnum=1, name="Nuova Terra", builder="Luca", bottom_vnum=20000, top_vnum=20099))
    assert zone.id == 20000 and zone.extra["file"] == "nuovaterra.are" and zone.enabled
    lst = (area_dir / "area.lst").read_text()
    assert lst.rstrip().endswith("nuovaterra.are\n$") and lst.count("nuovaterra.are") == 1
    assert (area_dir / "nuovaterra.are").read_text().startswith("#AREADATA\nName Nuova Terra~\nBuilders Luca~\nVNUMs 20000 20099")
    off = await adapter.update_zone(zone.id, ZonePatch(enabled=False))
    assert off.enabled is False and "nuovaterra.are" not in read_area_list(area_dir / "area.lst").names
    assert (area_dir / "nuovaterra.are").exists() and (await adapter.get_zone(20000)).enabled is False
    await adapter.update_zone(zone.id, ZonePatch(enabled=True, name="Terra Nuova", min_level=5, max_level=20, builder="Anna"))
    again = await adapter.get_zone(20000)
    assert (again.enabled, again.name, again.min_level, again.max_level, again.builder) == (True, "Terra Nuova", 5, 20, "Anna")
    assert read_area_list(area_dir / "area.lst").names[-1] == "nuovaterra.are"
    await adapter.delete_zone(20000)
    assert not (area_dir / "nuovaterra.are").exists() and "nuovaterra.are" not in (area_dir / "area.lst").read_text()
    assert (area_dir / "area.lst").read_text().rstrip().endswith("$")
    with expect_error(409, "zones.not_empty"):
        await adapter.delete_zone(3000)
    with expect_error(409, "zones.range_overlap"):
        await adapter.create_zone(ZoneIn(vnum=2, name="Sovrapposta", bottom_vnum=3100, top_vnum=3200))
    with expect_error(422, "basedmud.vnum_out_of_range"):
        await adapter.create_mob(MobIn(vnum=2950, zone_id=3000, keywords="x", short_description="x"))


@pytest.mark.real_rom
async def test_read_only(make_adapter, area_dir: Path) -> None:  # type: ignore[no-untyped-def]
    """Un mondo `read_only` legge ma rifiuta ogni scrittura (409 `world.read_only`) senza toccare i file."""
    adapter = make_adapter(read_only=True)
    before = {p.name: p.read_bytes() for p in area_dir.iterdir()}
    assert adapter.capabilities().read_only and (await adapter.get_mob(3000)).level == 23
    with expect_error(409, "world.read_only"):
        await adapter.update_mob(3000, MobPatch(level=1))
    with expect_error(409, "world.read_only"):
        await adapter.create_zone(ZoneIn(vnum=1, name="X"))
    with expect_error(409, "world.read_only"):
        await adapter.delete_room(3001)
    assert {p.name: p.read_bytes() for p in area_dir.iterdir()} == before


@pytest.mark.parametrize("bad", ["../evil.are", "a/b.are", "x.txt", "/etc/passwd", "..", ".hidden.are", "a b.are", "x" * 80 + ".are"])
async def test_path_traversal_is_rejected(adapter: BasedMudAdapter, area_dir: Path, bad: str) -> None:
    """Il nome del file di una nuova zona non puo' uscire dalla cartella ne' avere suffissi diversi da `.are`."""
    with expect_error(422, "basedmud.invalid_file_name"):
        await adapter.create_zone(ZoneIn(vnum=1, name="Zona", extra={"file": bad}))
    assert not (area_dir.parent / "evil.are").exists() and sorted(p.name for p in area_dir.parent.iterdir()) == ["area"]


async def test_zone_name_cannot_escape(adapter: BasedMudAdapter, area_dir: Path) -> None:
    """Il nome file derivato dal nome della zona e' sempre un nome semplice dentro la cartella."""
    zone = await adapter.create_zone(ZoneIn(vnum=1, name="../../etc/passwd", bottom_vnum=30000, top_vnum=30009))
    assert zone.extra["file"] == "etcpasswd.are" and (area_dir / "etcpasswd.are").exists()
    with expect_error(409, "basedmud.file_exists"):
        await adapter.create_zone(ZoneIn(vnum=1, name="x", bottom_vnum=30100, top_vnum=30109, extra={"file": "etcpasswd.are"}))


@pytest.mark.real_rom
async def test_concurrent_writes_are_serialized(adapter: BasedMudAdapter, area_dir: Path) -> None:
    """Molte scritture concorrenti sullo stesso file non si perdono: tutte presenti e file ancora valido."""
    before = (await adapter.list_mobs(MobPageParams(zone_id=3000))).total
    creates = [
        adapter.create_mob(MobIn(vnum=3300 + i, zone_id=3000, keywords=f"clone{i}", short_description=f"clone {i}")) for i in range(20)
    ]
    edits = [adapter.update_mob(3011, MobPatch(level=i)) for i in range(1, 11)]
    results = await asyncio.gather(*creates, *edits)
    assert len(results) == 30
    fresh = BasedMudAdapter(adapter.config)  # cache nuova: legge davvero da disco
    page = await fresh.list_mobs(MobPageParams(zone_id=3000))
    assert page.total == before + 20
    assert (await fresh.get_mob(3011)).level == 10
    assert sorted(m.vnum for m in page.items if m.keywords.startswith("clone")) == list(range(3300, 3320))
