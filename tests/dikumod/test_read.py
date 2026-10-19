"""Lettura dell'adapter Diku Modificato sui dati reali di dikumod e dikumod2 (copie temporanee)."""

from pathlib import Path

import pytest

from pachimudeditor_adapter_dikumod.adapter import DikumodAdapter
from pachimudeditor.common.adapters.models import (
    MobPageParams,
    ObjectPageParams,
    ResetCommandIn,
    RoomPageParams,
    ZonePageParams,
)
from tests.adapter_contract.helpers import expect_error
from tests.dikumod.conftest import DUPLICATES, MOB_SPEC, SPEC


@pytest.mark.real_dikumod
async def test_counts_match_the_spec(ro: DikumodAdapter, variant: str, capsys) -> None:  # type: ignore[no-untyped-def]
    """Zone, stanze, mob (sani + corrotti), oggetti come da documento, tolti i vnum doppi (l'API ne mostra uno)."""
    want, dup = SPEC[variant], DUPLICATES[variant]
    zones = await ro.list_zones(ZonePageParams(page=1, pageSize=500))
    rooms = await ro.list_rooms(RoomPageParams(page=1, pageSize=1))
    mobs = await ro.list_mobs(MobPageParams(page=1, pageSize=1))
    objects = await ro.list_objects(ObjectPageParams(page=1, pageSize=1))
    assert zones.total == want["zones"] == len(zones.items)
    assert rooms.total == want["rooms"] - dup["rooms"]
    assert mobs.total == want["mobs"] - dup["mobs"]
    assert objects.total == want["objects"] - dup["objects"]
    everyone = await ro.list_mobs(MobPageParams(page=1, pageSize=5000))
    bad = [m for m in everyone.items if m.extra.get("corrupted")]
    ok, nbad = MOB_SPEC[variant]
    assert len(bad) == nbad and len(everyone.items) - len(bad) == ok - dup["mobs"]
    with capsys.disabled():
        print(
            f"\n[{variant}] API: zone {zones.total}, stanze {rooms.total}, mob {mobs.total} ({len(bad)} corrotti), oggetti {objects.total}"
        )


@pytest.mark.real_dikumod
async def test_zone_ids_are_positions_and_ranges_derive_from_top(ro: DikumodAdapter) -> None:
    """`id == vnum ==` indice; `#N` doppi (138, 151) restano zone distinte; il bottom e' `top` precedente + 1."""
    zones = (await ro.list_zones(ZonePageParams(page=1, pageSize=500))).items
    assert [z.id for z in zones] == list(range(len(zones))) and all(z.vnum == z.id for z in zones)
    nums = [z.extra["numRaw"] for z in zones]
    assert 138 in nums and nums.count(138) > 1 and nums.count(151) > 1
    for prev, z in zip(zones, zones[1:]):
        assert z.bottom_vnum == prev.top_vnum + 1 or (z.bottom_vnum, z.top_vnum) == (0, 0), z
    assert zones[0].name.startswith("Scratch") and zones[1].name == "LIMBO" and (zones[1].bottom_vnum, zones[1].top_vnum) == (1, 49)
    assert all(z.enabled and z.min_level == z.max_level == 1 and z.builder == "" for z in zones)
    assert zones[2].reset_mode.name == "ALWAYS" and zones[2].extra["resetModeRaw"] == 2


async def test_content_belongs_to_the_zone_of_its_vnum(ro: DikumodAdapter) -> None:
    """`zoneId` di stanze/mob/oggetti e' la prima zona con `top >= vnum`; il filtro per zona e' coerente."""
    zone = await ro.get_zone(1)
    rooms = await ro.list_rooms(RoomPageParams(page=1, pageSize=500, zone_id=1))
    assert rooms.total and all(zone.bottom_vnum <= r.vnum <= zone.top_vnum and r.zone_id == 1 for r in rooms.items)
    summary = await ro.zone_summary(1)
    assert summary.room_count == rooms.total
    assert (await ro.get_room(rooms.items[0].id)).zone_id == 1


@pytest.mark.real_dikumod
async def test_corrupted_mobs_are_visible_with_warning_and_not_editable(ro: DikumodAdapter, rw: DikumodAdapter, variant: str) -> None:
    """I 33 mob corrotti compaiono in list/get con `extra.corrupted` e il motivo; update/delete danno 409."""
    mob = await ro.get_mob(2111)
    assert mob.extra["corrupted"] is True and mob.extra["warning"] and mob.extra["line"] > 0 and mob.extra["raw"].startswith("#2111")
    listed = await ro.list_mobs(MobPageParams(page=1, pageSize=50, search="2111"))
    assert any(m.vnum == 2111 and m.extra.get("corrupted") for m in listed.items)
    from pachimudeditor.common.adapters.models import MobPatch

    with expect_error(409, "dikumod.record_corrupted"):
        await rw.update_mob(2111, MobPatch(level=3))
    with expect_error(409, "dikumod.record_corrupted"):
        await rw.delete_mob(2111)
    assert (await ro.get_mob(3000)).extra.get("corrupted") is None


@pytest.mark.real_dikumod
async def test_room_fields_and_special_blocks(ro: DikumodAdapter, variant: str) -> None:
    """Teleport, fiume, tunnel e settore vero stanno in `extra`; le uscite hanno id `vnum*10+dir` e info grezza."""
    tele = next(r for r in (await ro.list_rooms(RoomPageParams(page=1, pageSize=5000))).items if r.extra["tele"])
    assert set(tele.extra["tele"]) == {"time", "target", "mask", "count"} and tele.extra["sector"] >= 0
    river = next(r for r in (await ro.list_rooms(RoomPageParams(page=1, pageSize=5000))).items if r.extra["river"])
    assert river.extra["sector"] in (7, 9) and set(river.extra["river"]) == {"speed", "dir"}
    tunnel = next(r for r in (await ro.list_rooms(RoomPageParams(page=1, pageSize=5000))).items if r.extra["moblim"] is not None)
    assert "tunnel" in tunnel.flags
    room = await ro.get_room(3001)
    assert room.exits and all(x.id == 3001 * 10 + int(x.direction) for x in room.exits)
    assert all(set(x.extra) >= {"exitInfo", "openCmd"} for x in room.exits)
    assert any(e.id // 1000 == 3001 for e in room.extra_descriptions) or not room.extra_descriptions


@pytest.mark.real_dikumod
async def test_override_files_take_precedence(ro: DikumodAdapter, lib: Path, variant: str) -> None:
    """Con `rooms/<vnum>` e `objects/<vnum>` (dikumod2) il contenuto effettivo e' quello del file per-vnum."""
    if variant != "dikumod2":
        pytest.skip("gli override per-vnum popolati esistono solo in dikumod2")
    room = await ro.get_room(3008)
    assert room.extra["source"] == "override" and room.name == "Il Bordello"
    assert (await ro.get_room(3001)).extra["source"] == "main"
    obj = await ro.get_object(40022)
    assert obj.extra["source"] == "override" and obj.object_type.name == "OTHER" and obj.extra["typeRaw"] == 24
    assert obj.extra["extraDescs"][0]["keyword"].startswith("board")
    assert (lib / "rooms" / "3008").is_file() and (await ro.get_zone(0)).extra["override"] is None


@pytest.mark.real_dikumod
async def test_mob_mapping(ro: DikumodAdapter) -> None:
    """Mob `S` (dado hp del file) e `A/N/B/L` (hp = level d8 + bonus), razza, sesso, maschere, negozio, script."""
    puff = await ro.get_mob(1)
    assert (puff.extra["kind"], puff.hp_dice_count, puff.hp_die_size, puff.hp_bonus) == ("S", 5, 10, 550)
    assert (puff.damage_dice_count, puff.damage_die_size, puff.damage_bonus, puff.thac0, puff.armor_class) == (4, 6, 3, 1, -10)
    assert puff.race_id == "dragon" and puff.gold == 5000 and puff.extra["expRaw"] == 155  # `-1 gold exp race`
    wraith = await ro.get_mob(2)
    assert wraith.extra["kind"] == "A" and wraith.extra["multiAttack"] == 2
    assert (wraith.hp_dice_count, wraith.hp_die_size, wraith.hp_bonus) == (wraith.level, 8, 100)
    assert wraith.extra["expRaw"] == 4 and wraith.experience == 4
    assert wraith.extra["immune"] is not None and wraith.extra["affectedBy"]
    keeper = next(m for m in (await ro.list_mobs(MobPageParams(page=1, pageSize=5000))).items if m.extra.get("shop"))
    shop = keeper.extra["shop"]
    assert len(shop["producing"]) == 5 and len(shop["types"]) == 5 and "noSuchItem1" in shop["messages"] and shop["tag"].startswith("#")


@pytest.mark.real_dikumod
async def test_script_extra_on_dikumod(ro: DikumodAdapter, variant: str) -> None:
    """In dikumod gli script di `scripts.dat` compaiono in `extra.script` con il testo del file."""
    if variant != "dikumod":
        pytest.skip("scripts.dat esiste solo in dikumod")
    mob = await ro.get_mob(3064)
    assert mob.extra["script"]["name"] == "Drunk" and mob.extra["script"]["text"]


@pytest.mark.real_dikumod
async def test_object_mapping(ro: DikumodAdapter) -> None:
    """Tipo, flag, affect (somma + elenco ordinato in extra), extra description."""
    objs = (await ro.list_objects(ObjectPageParams(page=1, pageSize=5000))).items
    armor = next(o for o in objs if o.affects and o.object_type.name == "ARMOR")
    assert (
        armor.extra["affects"]
        and sum(armor.affects.values()) == sum(a["modifier"] for a in armor.extra["affects"])
        or len(armor.affects) < len(armor.extra["affects"])
    )
    assert armor.extra_flags and armor.wear_flags and "take" in armor.wear_flags
    with_extra = next(o for o in objs if o.extra["extraDescs"])
    assert with_extra.extra["extraDescs"][0]["keyword"]


@pytest.mark.real_dikumod
async def test_reset_commands_mapping(ro: DikumodAdapter, variant: str) -> None:
    """Comandi M O G E P D C H F: argomenti per tipo, if_value intero (anche -5), commento, `O` senza arg4 segnalata."""
    zones = (await ro.list_zones(ZonePageParams(page=1, pageSize=500))).items
    by_type: dict[int, object] = {}
    negative = None
    missing = None
    for z in zones:
        for c in await ro.list_reset_commands(z.id):
            by_type.setdefault(int(c.command_type), c)
            if (c.if_value or 0) < 0 and negative is None:
                negative = c
            if c.extra.get("missingArg4") and missing is None:
                missing = c
    assert set(by_type) >= {0, 1, 2, 3, 4, 5, 8, 9}  # M O G E P D H F
    assert negative is not None and negative.if_flag is False and negative.if_value in (-5, -39)
    assert missing is not None and missing.extra["letter"] == "O" and missing.arg4 == 0
    equip = by_type[3]
    assert equip.arg_str in __import__("pachimudeditor_adapter_dikumod.dikumod_lib", fromlist=["x"]).tables.WEAR_POSITIONS
    door = by_type[5]
    assert door.arg_str in ("OPEN", "CLOSED", "LOCKED")
    commented = [c for z in zones[:20] for c in await ro.list_reset_commands(z.id) if c.comment]
    assert commented and not commented[0].comment.startswith(";")
    assert all(c.id == c.order_index == i for i, c in enumerate(await ro.list_reset_commands(3)))


async def test_meta_and_describe(ro: DikumodAdapter) -> None:
    """Le tabelle `dikumod*` sono in `enums()`, i campi flag di `describe()` le richiamano, razze e classi sono liste."""
    enums = await ro.enums()
    for key in (
        "dikumodRoomFlags",
        "dikumodActFlags",
        "dikumodExtraFlags",
        "dikumodWearFlags",
        "dikumodAffectFlags",
        "dikumodImmuneFlags",
        "dikumodSector",
        "dikumodItemType",
        "dikumodApplyType",
        "dikumodWearPos",
        "dikumodRace",
        "dikumodPosition",
        "zoneCommandType",
    ):
        assert enums[key], key
    assert {o.value for o in enums["zoneCommandType"]} == {0, 1, 2, 3, 4, 5, 7, 8, 9, 10}
    assert next(o for o in enums["dikumodRoomFlags"] if o.label == "tunnel").value == 256
    info = ro.describe()
    assert info.kind == "dikumod" and info.capabilities.read_only is True
    room = next(r for r in info.resources if r.type == "room")
    assert next(f for f in room.fields if f.name == "flags").enum == "dikumodRoomFlags"
    reset = next(r for r in info.resources if r.type == "reset_command")
    assert next(f for f in reset.fields if f.name == "commandType").enum == "zoneCommandType"
    assert any(f.name == "ifValue" for f in reset.fields)
    races = await ro.races()
    assert len(races) == 85 and races[1].id == "human" and await ro.classes() == []


@pytest.mark.real_dikumod
async def test_read_only_is_the_default(make_adapter, lib: Path) -> None:  # type: ignore[no-untyped-def]
    """Senza `read_only` esplicito il mondo e' in sola lettura; `read_only: false` abilita le scritture."""
    from pachimudeditor.common.adapters.models import MobPatch, ZoneIn

    default = make_adapter()
    assert default.capabilities().read_only is True
    with expect_error(409, "world.read_only"):
        await default.update_mob(3000, MobPatch(level=3))
    with expect_error(409, "world.read_only"):
        await default.create_zone(ZoneIn(vnum=500, name="x"))
    explicit_ro = make_adapter(read_only=True)
    with expect_error(409, "world.read_only"):
        await explicit_ro.update_mob(3000, MobPatch(level=3))
    assert make_adapter(read_only=False).capabilities().read_only is False
    assert (await default.get_mob(3000)).level == (await make_adapter(read_only=False).get_mob(3000)).level


@pytest.mark.real_dikumod
async def test_reading_never_writes(ro: DikumodAdapter, lib: Path) -> None:
    """Nessuna lettura modifica un file (hash prima/dopo)."""
    import hashlib

    def digest() -> dict[str, str]:
        """Hash di ogni file della copia."""
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(lib.rglob("*")) if p.is_file()}

    before = digest()
    await ro.list_zones(ZonePageParams(page=1, pageSize=500))
    await ro.list_rooms(RoomPageParams(page=1, pageSize=500))
    await ro.get_mob(3000)
    await ro.room_graph(3)
    assert digest() == before


@pytest.mark.real_dikumod
async def test_validate_script_on_dikumod_commands(ro: DikumodAdapter) -> None:
    """La validazione riconosce i comandi Diku Modificato (C/H/F/Z) e i vnum inesistenti."""
    from pachimudeditor.common.adapters.models import ResetCommandDraft, ResetDraftScriptIn

    draft = ResetDraftScriptIn(
        commands=[
            ResetCommandDraft(command_type=0, arg1=3000, arg2=1, arg3=3001),
            ResetCommandDraft(command_type=7, arg1=3000, arg2=1, arg3=0),
            ResetCommandDraft(command_type=8, arg1=7, arg2=999999),
            ResetCommandDraft(command_type=9, arg1=1, arg2=2),
            ResetCommandDraft(command_type=10, arg1=1, arg2=1),
            ResetCommandDraft(command_type=7, arg1=999999, arg2=1, arg3=0),
        ]
    )
    result = await ro.validate_reset_commands(3, draft)
    codes = {(i.index, i.code) for i in result.issues}
    assert (2, "zones.reset_unknown_mob") in codes and (5, "zones.reset_unknown_mob") in codes
    assert not any(i.index in (1, 3, 4) and i.severity == "error" for i in result.issues)
    assert ResetCommandIn(command_type=8, arg1=1, arg2=2).command_type == 8
