"""Scrittura dell'adapter Diku Modificato sui dati reali (copie): cambiano solo i record toccati e i file restano caricabili."""

import hashlib
from pathlib import Path

import pytest

from pachimudeditor_adapter_dikumod.adapter import DikumodAdapter
from pachimudeditor_adapter_dikumod.dikumod_lib import Raw, load_world
from pachimudeditor_adapter_dikumod.dikumod_lib.files import read_text
from pachimudeditor.common.adapters.models import (
    ExitIn,
    ExitPatch,
    MobIn,
    MobPatch,
    ObjectIn,
    ObjectPatch,
    ResetCommandIn,
    ResetScriptIn,
    RoomIn,
    RoomPatch,
    ZoneCloneIn,
    ZoneIn,
    ZonePatch,
)
from pachimudeditor.common.enums import ObjectType
from pachimudeditor.common.enums import DoorFlag
from tests.adapter_contract.helpers import expect_error
from tests.dikumod_lib import c_loader as c


def digest(lib: Path) -> dict[str, str]:
    """Hash di ogni file (anche delle sottocartelle) della copia."""
    return {str(p.relative_to(lib)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(lib.rglob("*")) if p.is_file()}


def changed(before: dict[str, str], after: dict[str, str]) -> set[str]:
    """I file diversi, aggiunti o spariti."""
    return {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}


def records(path: Path, kind: str) -> dict[tuple[int, int], str]:
    """`{(vnum, occorrenza): testo sorgente}` dei record di un file (per confrontare solo quelli che cambiano)."""
    world = load_world(path.parent)
    rf = {"wld": world.wld, "mob": world.mob, "obj": world.obj}[kind]
    seen: dict[int, int] = {}
    out: dict[tuple[int, int], str] = {}
    for item in rf.items:
        n = seen.get(item.vnum, 0)
        seen[item.vnum] = n + 1
        out[(item.vnum, n)] = item.src if isinstance(item, Raw) else item._src
    return out


async def test_editing_one_mob_and_one_room_changes_only_those_records(rw: DikumodAdapter, lib: Path) -> None:
    """Un mob e una stanza modificati: cambiano solo dikumoddata.mob e dikumoddata.wld e, dentro, solo quei due record."""
    before_files = digest(lib)
    before_mob, before_wld = records(lib / "dikumoddata.mob", "mob"), records(lib / "dikumoddata.wld", "wld")
    mob = await rw.update_mob(3000, MobPatch(level=31, short_description="Un mago rinominato", extra={"position": 5}))
    room = await rw.update_room(3001, RoomPatch(name="Piazza rinominata", description="Nuova descrizione."))
    assert mob.level == 31 and mob.extra["position"] == 5 and room.name == "Piazza rinominata" and room.description == "Nuova descrizione."
    assert changed(before_files, digest(lib)) == {"dikumoddata.mob", "dikumoddata.wld"}
    after_mob, after_wld = records(lib / "dikumoddata.mob", "mob"), records(lib / "dikumoddata.wld", "wld")
    assert [k for k in before_mob if before_mob[k] != after_mob.get(k)] == [(3000, 0)] and before_mob.keys() == after_mob.keys()
    assert [k for k in before_wld if before_wld[k] != after_wld.get(k)] == [(3001, 0)] and before_wld.keys() == after_wld.keys()
    text = read_text(lib / "dikumoddata.mob")
    index = c.generate_indices(text)
    got = c.read_mobile(text, index.entries[c.real_lookup(index, 3000)].pos)
    assert not got["errors"] and got["level"] == 31 and got["position"] == 5 and got["short"] == "Un mago rinominato"
    wld = c.boot_world(read_text(lib / "dikumoddata.wld"))[3001]
    assert wld["name"] == "Piazza rinominata" and wld["desc"] == "Nuova descrizione.\n"


async def test_overrides_are_edited_in_place(rw: DikumodAdapter, lib: Path, variant: str) -> None:
    """Una stanza con `rooms/<vnum>` e un oggetto con `objects/<vnum>` si scrivono nel loro file; il principale non cambia."""
    if variant != "dikumod2":
        pytest.skip("override popolati solo in dikumod2")
    before = digest(lib)
    room = await rw.update_room(3008, RoomPatch(name="Bordello nuovo"))
    assert room.name == "Bordello nuovo" and room.extra["source"] == "override"
    assert changed(before, digest(lib)) == {"rooms/3008"}
    obj = await rw.update_object(40022, ObjectPatch(cost=77))
    assert obj.cost == 77 and obj.extra["source"] == "override"
    assert changed(before, digest(lib)) == {"rooms/3008", "objects/40022"}
    assert load_world(lib).room_overrides[3008].items[0].name == "Bordello nuovo"
    with expect_error(422, "dikumod.override_vnum_locked"):
        await rw.update_room(3008, RoomPatch(vnum=3999))
    with expect_error(409, "rooms.in_reset_usage"):
        await rw.delete_room(3008)  # usata da un reset
    free = next(v for v in (100, 3165, 3171) if not rw.find_usage("room", v, include_exit_keys=False))
    await rw.delete_room(free)
    assert not (lib / "rooms" / str(free)).exists()
    with expect_error(404, "rooms.not_found"):
        await rw.get_room(free)


async def test_unchanged_dto_roundtrip_writes_no_byte(rw: DikumodAdapter, lib: Path) -> None:
    """Rimandare il DTO letto (extra compreso) come patch non cambia nessun file, nemmeno con record speciali."""
    before = digest(lib)
    for vnum in (1, 2, 3000, 3001):
        mob = await rw.get_mob(vnum)
        patch = MobPatch.model_validate({**mob.model_dump(by_alias=False, exclude={"id", "vnum", "zone_id"}), "extra": mob.extra})
        await rw.update_mob(vnum, patch)
    rooms = [
        r
        for r in (
            await rw.list_rooms(
                __import__("pachimudeditor.common.adapters.models", fromlist=["RoomPageParams"]).RoomPageParams(page=1, pageSize=3000)
            )
        ).items
    ][:400:3]
    for room in rooms:
        patch = RoomPatch.model_validate({**room.model_dump(by_alias=False, exclude={"id", "vnum", "zone_id"}), "extra": room.extra})
        await rw.update_room(room.vnum, patch)
    for vnum in (1, 3001, 3010):
        if vnum in rw.store.objs:
            obj = await rw.get_object(vnum)
            await rw.update_object(
                vnum, ObjectPatch.model_validate({**obj.model_dump(by_alias=False, exclude={"id", "vnum", "zone_id"}), "extra": obj.extra})
            )
    assert digest(lib) == before


async def test_create_update_delete_mob_keeps_order_and_loader_compat(rw: DikumodAdapter, lib: Path) -> None:
    """Un mob nuovo finisce al posto giusto (ricerca binaria del gioco), con negozio e script; poi cambia vnum e si elimina."""
    zone = await rw.get_zone(10)
    vnum = await rw.next_content_vnum(zone.id, "mob")
    new = await rw.create_mob(
        MobIn(
            vnum=vnum,
            zone_id=zone.id,
            keywords="mercante nuovo",
            short_description="Un mercante",
            long_description="Un mercante e' qui.",
            level=12,
            gold=100,
            race_id="human",
            flags=["sentinel"],
            extra={"affectedBy": ["sanctuary"], "immune": ["fire"]},
        )
    )
    assert (
        new.extra["kind"] == "N" and new.race_id == "human" and new.extra["affectedBy"] == ["sanctuary"] and new.extra["immune"] == ["fire"]
    )
    assert new.extra["sexCode"] == 3  # le maschere si leggono solo con il codice sesso 3..5
    text = read_text(lib / "dikumoddata.mob")
    index = c.generate_indices(text)
    vnums = [e.vnum for e in index.entries]
    assert vnums == sorted(vnums) and c.real_lookup(index, vnum) >= 0
    got = c.read_mobile(text, index.entries[c.real_lookup(index, vnum)].pos)
    assert not got["errors"] and (got["level"], got["race"], got["immune"], got["act"] & 2) == (12, 1, 1, 2)
    shop = {
        "producing": [3000, -1, -1, -1, -1],
        "profitBuy": 1.5,
        "profitSell": 0.5,
        "types": [9, 0, 0, 0, 0],
        "messages": {"noSuchItem1": "%s Non l'ho.", "messageBuy": "%s Costa %d."},
        "room": 3001,
        "open1": 0,
        "close1": 28,
    }
    updated = await rw.update_mob(vnum, MobPatch(extra={"shop": shop}))
    assert updated.extra["shop"]["tag"].startswith("#") and updated.extra["shop"]["messages"]["noSuchItem1"] == "%s Non l'ho."
    from tests.dikumod_lib.test_loader_emulation import c as loader

    shops = loader.boot_shops(read_text(lib / "dikumoddata.shp"))
    assert any(s["rest"][2] == vnum for s in shops)
    moved = await rw.update_mob(vnum, MobPatch(vnum=vnum + 1))
    assert moved.vnum == vnum + 1 and moved.extra["shop"] is not None
    assert (await rw.get_mob(vnum + 1)).extra["shop"]["profitBuy"] == 1.5
    with expect_error(404, "mobs.not_found"):
        await rw.get_mob(vnum)
    await rw.delete_mob(vnum + 1)
    assert (vnum + 1) not in rw.store.mobs and (vnum + 1) not in rw.store.shops
    index = c.generate_indices(read_text(lib / "dikumoddata.mob"))
    assert [e.vnum for e in index.entries] == sorted(e.vnum for e in index.entries)


async def test_object_create_and_affects(rw: DikumodAdapter, lib: Path) -> None:
    """Oggetto nuovo con affect (dict) e `extra.affects` ordinato; il loader legge E, A e P come previsto."""
    zone = await rw.get_zone(10)
    vnum = await rw.next_content_vnum(zone.id, "object")
    obj = await rw.create_object(
        ObjectIn(
            vnum=vnum,
            zone_id=zone.id,
            keywords="gile",
            short_description="un gile",
            object_type=ObjectType.ARMOR,
            wear_flags=["take", "body"],
            extra_flags=["magic"],
            affects={"str": 2, "hit": 10},
            value_0=5,
            extra={"extraDescs": [{"keyword": "gile", "description": "Bello."}], "forbiddenWear": {"toChar": "No.", "toRoom": "Non puo'."}},
        )
    )
    assert obj.object_type.name == "ARMOR" and obj.affects == {"str": 2, "hit": 10} and obj.value_0 == 5
    text = read_text(lib / "dikumoddata.obj")
    index = c.generate_indices(text)
    got = c.read_object(text, index.entries[c.real_lookup(index, vnum)].pos)
    assert (
        not got["errors"]
        and got["affects"] == [(1, 2), (13, 10)]
        and got["extras"] == [("gile", "Bello.\n")]
        and got["forbidden"] == ("No.\n", "Non puo'.\n")
    )
    assert got["type"] == 9 and got["wear"] == 9 and got["extra"] == 64
    patched = await rw.update_object(
        vnum, ObjectPatch(extra={"affects": [{"location": 2, "modifier": -1}, {"location": 2, "modifier": 4}]})
    )
    assert patched.affects == {"dex": 3} and len(patched.extra["affects"]) == 2
    with expect_error(422, "dikumod.too_many_affects"):
        await rw.update_object(vnum, ObjectPatch(affects={str(i): 1 for i in range(1, 7)}))
    await rw.delete_object(vnum)


async def test_zone_edit_rewrites_only_that_zone(rw: DikumodAdapter, lib: Path) -> None:
    """Sostituire lo script di una zona con una `O` a 4 numeri la riscrive (a 5 numeri); le altre zone restano identiche."""
    world = load_world(lib)
    idx = next(i for i, z in enumerate(world.zon.items) if any(cmd.letter == "O" and len(cmd.args) == 3 for cmd in z.commands))
    before = [z._src for z in world.zon.items]
    script = await rw.list_reset_commands(idx)
    same = ResetScriptIn(
        commands=[
            ResetCommandIn.model_validate(c_.model_dump(by_alias=False, exclude={"id", "zone_id", "order_index", "extra"}) | {"extra": {}})
            for c_ in script
        ]
    )
    digest_before = digest(lib)
    await rw.replace_reset_commands(idx, same)
    assert digest(lib) == digest_before  # script identico: nessuna scrittura
    edited = same.model_copy(deep=True)
    edited.commands[0].comment = "commento nuovo"
    await rw.replace_reset_commands(idx, edited)
    after_world = load_world(lib)
    after = [z._src for z in after_world.zon.items]
    assert [i for i, (a, b) in enumerate(zip(before, after)) if a != b] == [idx]
    zone = after_world.zon.items[idx]
    assert zone.commands[0].comment_text == "commento nuovo"
    assert all(len(cmd.args) == 4 for cmd in zone.commands if cmd.letter == "O")
    loaded = c.boot_zones(read_text(lib / "dikumoddata.zon"))
    mine = next(z for z in loaded if z["name"] == zone.name and z["top"] == zone.top)
    assert len(mine["cmds"]) == len(zone.commands) and mine["cmds"][0][0] == zone.commands[0].letter


async def test_exit_door_state_updates_bits_and_d_commands(rw: DikumodAdapter, lib: Path) -> None:
    """`isOpen/isLocked` aggiornano i bit di `exit_info` e i comandi `D` esistenti della stanza."""
    world = load_world(lib)
    zone_idx, cmd = next(
        (i, c_)
        for i, z in enumerate(world.zon.items)
        for c_ in z.commands
        if c_.letter == "D"
        and c_.args[0] in {r.vnum for r in world.wld.items}
        and next(r for r in world.wld.items if r.vnum == c_.args[0]).exit_for(c_.args[1]) is not None
    )
    room_vnum, door = cmd.args[0], cmd.args[1]
    detail = await rw.get_room(room_vnum)
    exit_ = next(x for x in detail.exits if int(x.direction) == door)
    updated = await rw.update_exit(
        room_vnum, exit_.id, ExitPatch(door_flag=DoorFlag.CLOSABLE, is_open=False, is_locked=True, key_vnum=3001)
    )
    assert updated.is_open is False and updated.is_locked is True and updated.door_flag == DoorFlag.CLOSABLE
    assert updated.extra["exitInfo"] & 7 == 7 and updated.extra["dState"] == 2
    reloaded = load_world(lib)
    d = [c_ for c_ in reloaded.zon.items[zone_idx].commands if c_.letter == "D" and c_.args[:2] == [room_vnum, door]]
    assert d and all(c_.args[2] == 2 for c_ in d)
    reopened = await rw.update_exit(room_vnum, exit_.id, ExitPatch(is_open=True, is_locked=False))
    assert reopened.is_open and not reopened.is_locked and reopened.extra["exitInfo"] & 6 == 0 and reopened.extra["dState"] == 0


async def test_room_vnum_change_follows_exits_and_doors(rw: DikumodAdapter, lib: Path) -> None:
    """Cambiando il vnum di una stanza, le uscite delle altre che portano li' e i suoi `D` seguono; resta ordinato."""
    zone = await rw.get_zone(10)
    free = await rw.next_content_vnum(zone.id, "room")
    a = await rw.create_room(RoomIn(vnum=free, zone_id=zone.id, name="A"))
    b = await rw.create_room(RoomIn(vnum=free + 1, zone_id=zone.id, name="B", flags=["tunnel"], extra={"moblim": 3}))
    await rw.create_exit(a.id, ExitIn(direction=1, target_room_id=b.id))
    moved = await rw.update_room(b.id, RoomPatch(vnum=free + 2))
    assert moved.vnum == free + 2 and (await rw.get_room(a.id)).exits[0].target_room_vnum == free + 2
    assert moved.extra["moblim"] == 3
    text = read_text(lib / "dikumoddata.wld")
    rooms = c.boot_world(text)
    assert rooms[free]["exits"][1][4] == free + 2 and rooms[free + 2]["moblim"] == 3 and free + 1 not in rooms
    vnums = [int(x) for x in __import__("re").findall(r"(?m)^#(\d+)$", text)]
    assert vnums == sorted(vnums)
    await rw.delete_room(a.id)
    await rw.delete_room(moved.id)


async def test_zone_lifecycle_on_real_world(rw: DikumodAdapter, lib: Path) -> None:
    """Crea (in coda), aggiorna, clona ed elimina una zona: rispetta l'ordine dei `top` e il formato del file."""
    free = await rw.next_zone_vnum(99)
    assert free.vnum == 93 and free.bottom_vnum == 1000000
    zone = await rw.create_zone(
        ZoneIn(vnum=free.vnum, name="Zona di prova", bottom_vnum=free.bottom_vnum, top_vnum=free.top_vnum, lifespan_minutes=15)
    )
    assert zone.id == 93 and (zone.bottom_vnum, zone.top_vnum) == (1000000, 1000099) and zone.reset_mode.name == "EMPTY"
    with expect_error(422, "dikumod.zone_bottom_derived"):
        await rw.create_zone(ZoneIn(vnum=94, name="Con buco", bottom_vnum=1000500, top_vnum=1000600))
    with expect_error(409, "zones.range_overlap"):
        await rw.create_zone(ZoneIn(vnum=94, name="Sovrapposta", bottom_vnum=1000050, top_vnum=1000600))
    room = await rw.create_room(RoomIn(vnum=1000000, zone_id=93, name="Prima stanza"))
    assert room.zone_id == 93
    with expect_error(422, "dikumod.vnum_out_of_range"):
        await rw.create_room(RoomIn(vnum=1000100, zone_id=93, name="Fuori"))
    with expect_error(409, "zones.not_empty"):
        await rw.delete_zone(93)
    with expect_error(422, "zones.invalid_vnum_range"):
        await rw.update_zone(93, ZonePatch(top_vnum=5))
    with expect_error(422, "dikumod.zone_top_order"):
        await rw.update_zone(2, ZonePatch(top_vnum=300))  # oltre il top della zona successiva (249)
    assert (await rw.update_zone(93, ZonePatch(top_vnum=1000200))).top_vnum == 1000200  # nessun contenuto cambia zona
    await rw.create_room(RoomIn(vnum=1000150, zone_id=93, name="Lontana"))
    with expect_error(409, "dikumod.zone_range_has_content"):
        await rw.update_zone(93, ZonePatch(top_vnum=1000099))
    await rw.delete_room(1000150)
    await rw.update_zone(93, ZonePatch(top_vnum=1000099))
    await rw.update_zone(93, ZonePatch(name="Rinominata", lifespan_minutes=5, extra={"resetModeRaw": 6}))
    got = await rw.get_zone(93)
    assert (got.name, got.lifespan_minutes, got.reset_mode.name, got.extra["resetModeRaw"]) == ("Rinominata", 5, "ALWAYS", 6)
    loaded = c.boot_zones(read_text(lib / "dikumoddata.zon"))
    assert loaded[-1]["name"] == "Rinominata" and loaded[-1]["top"] == 1000099 and len(loaded) == 91  # 90 viste dal gioco + la nuova
    await rw.delete_room(1000000)
    empty = await rw.clone_zone(93, ZoneCloneIn(vnum=94, name="Vuota"))
    assert empty.id == 94 and (empty.bottom_vnum, empty.top_vnum) == (0, 0)
    await rw.delete_zone(94)
    await rw.delete_zone(93)
    assert (await rw.next_zone_vnum(9)).vnum == 93


async def test_invalid_input_is_rejected_with_stable_codes(rw: DikumodAdapter, lib: Path) -> None:
    """`extra` sconosciuto, flag inesistente, tilde e righe pericolose: 422 con codice stabile e nessun byte scritto."""
    before = digest(lib)
    with expect_error(422, "dikumod.extra_unknown"):
        await rw.update_mob(3000, MobPatch(extra={"nope": 1}))
    with expect_error(422, "dikumod.unknown_flag"):
        await rw.update_mob(3000, MobPatch(flags=["inesistente"]))
    with expect_error(422, "dikumod.unsafe_text"):
        await rw.update_room(3001, RoomPatch(description="con ~ dentro"))
    with expect_error(422, "dikumod.unsafe_text"):
        await rw.update_mob(3000, MobPatch(detailed_description="riga\n#finta 7\n"))
    with expect_error(422, "dikumod.unsafe_text"):
        await rw.update_object(3001, ObjectPatch(long_description="x\n%%\n"))
    with expect_error(422, "dikumod.hp_not_dice"):
        await rw.update_mob(2, MobPatch(hp_dice_count=99, hp_die_size=3))
    with expect_error(422, "dikumod.unknown_race"):
        await rw.update_mob(3000, MobPatch(race_id="elfonano"))
    with expect_error(422, "dikumod.field_unsupported"):
        await rw.update_mob(3000, MobPatch(is_banker=True))
    with expect_error(422, "dikumod.zone_derived"):
        await rw.update_mob(3000, MobPatch(zone_id=3))
    with expect_error(409, "mobs.vnum_taken"):
        await rw.update_mob(3000, MobPatch(vnum=3001))
    assert digest(lib) == before
    assert (await rw.get_mob(3000)).level != 99  # la cache non conserva modifiche fallite
    # dopo gli errori il mondo e' ancora scrivibile
    assert (await rw.update_mob(3000, MobPatch(level=5))).level == 5


async def test_originals_stay_readable_after_all_writes(rw: DikumodAdapter, lib: Path) -> None:
    """Dopo una raffica di scritture ogni vnum dei file mob/oggetti si trova ancora con la ricerca binaria del gioco."""
    for vnum in (3000, 3001, 3002):
        if vnum in rw.store.mobs:
            await rw.update_mob(vnum, MobPatch(alignment=10))
    for pair in ((await rw.next_content_vnum(10, "mob"),),):
        await rw.create_mob(MobIn(vnum=pair[0], zone_id=10, keywords="x", short_description="x"))
    world = load_world(lib)
    mob_index = c.generate_indices(read_text(world.mob.path))
    assert all(c.real_lookup(mob_index, item.vnum) >= 0 for item in world.mob.items)
    assert len(world.mob.raws()) == 33 and read_text(world.mob.path).rstrip().endswith("%%~")
