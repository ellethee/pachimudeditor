"""Scrittura dell'adapter Diku Modificato sul mondo sintetico (`tests/support/synthetic_worlds.py`): gira sempre, anche in CI.

Gli equivalenti sui dati reali sono in `test_write.py` (marcati `real_dikumod`). Zone: 0 servizio, 1 "La valle di prova" (vnum 1-99),
2 "I monti di prova" (100-199).
"""

import hashlib
import re
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
    RoomPageParams,
    RoomPatch,
    ZoneIn,
    ZonePatch,
)
from pachimudeditor.common.adapters.registry import WorldConfig
from pachimudeditor.common.enums import DoorFlag, ObjectType
from tests.adapter_contract.helpers import expect_error
from tests.dikumod_lib import c_loader as c
from tests.support.synthetic_worlds import write_dikumod_world


@pytest.fixture
def lib(tmp_path: Path) -> Path:
    """Cartella `lib/` sintetica e scrivibile."""
    return write_dikumod_world(tmp_path / "lib")


@pytest.fixture
def rw(lib: Path) -> DikumodAdapter:
    """Adapter scrivibile (`read_only: false` esplicito)."""
    return DikumodAdapter(WorldConfig(id="syn", kind="dikumod", name="Sintetico", path=str(lib), read_only=False))


def digest(lib: Path) -> dict[str, str]:
    """Hash di ogni file della cartella."""
    return {str(p.relative_to(lib)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(lib.rglob("*")) if p.is_file()}


def records(lib: Path, kind: str) -> dict[tuple[int, int], str]:
    """`{(vnum, occorrenza): testo sorgente}` dei record di un file."""
    world = load_world(lib)
    rf = {"wld": world.wld, "mob": world.mob, "obj": world.obj}[kind]
    seen: dict[int, int] = {}
    out: dict[tuple[int, int], str] = {}
    for item in rf.items:
        n = seen.get(item.vnum, 0)
        seen[item.vnum] = n + 1
        out[(item.vnum, n)] = item.src if isinstance(item, Raw) else item._src
    return out


async def test_read_only_is_the_default(lib: Path) -> None:
    """Senza `read_only` esplicito il mondo e' in sola lettura: nessuna scrittura."""
    adapter = DikumodAdapter(WorldConfig(id="syn", kind="dikumod", path=str(lib)))
    before = digest(lib)
    with expect_error(409, "world.read_only"):
        await adapter.update_mob(1, MobPatch(level=2))
    assert digest(lib) == before


async def test_editing_one_mob_and_one_room_changes_only_those_records(rw: DikumodAdapter, lib: Path) -> None:
    """Un mob e una stanza modificati: cambiano solo `.mob` e `.wld` e, dentro, solo quei due record; il loader emulato li rilegge."""
    before_files, before_mob, before_wld = digest(lib), records(lib, "mob"), records(lib, "wld")
    mob = await rw.update_mob(1, MobPatch(level=31, short_description="Una guardia rinominata", extra={"position": 5}))
    room = await rw.update_room(1, RoomPatch(name="Piazza rinominata", description="Nuova descrizione."))
    assert mob.level == 31 and mob.extra["position"] == 5 and room.name == "Piazza rinominata"
    after_files = digest(lib)
    assert {k for k in after_files if after_files[k] != before_files.get(k)} == {"dikumoddata.mob", "dikumoddata.wld"}
    after_mob, after_wld = records(lib, "mob"), records(lib, "wld")
    assert [k for k in before_mob if before_mob[k] != after_mob.get(k)] == [(1, 0)] and before_mob.keys() == after_mob.keys()
    assert [k for k in before_wld if before_wld[k] != after_wld.get(k)] == [(1, 0)] and before_wld.keys() == after_wld.keys()
    text = read_text(lib / "dikumoddata.mob")
    index = c.generate_indices(text)
    got = c.read_mobile(text, index.entries[c.real_lookup(index, 1)].pos)
    assert not got["errors"] and got["level"] == 31 and got["position"] == 5 and got["short"] == "Una guardia rinominata"
    assert c.boot_world(read_text(lib / "dikumoddata.wld"))[1]["desc"] == "Nuova descrizione.\n"


async def test_unchanged_dto_roundtrip_writes_no_byte(rw: DikumodAdapter, lib: Path) -> None:
    """Rimandare il DTO letto (extra compreso) come patch non cambia nessun file."""
    before = digest(lib)
    for vnum in (1, 2, 100):
        mob = await rw.get_mob(vnum)
        await rw.update_mob(
            vnum, MobPatch.model_validate({**mob.model_dump(by_alias=False, exclude={"id", "vnum", "zone_id"}), "extra": mob.extra})
        )
    for vnum in (1, 2, 3, 100, 101):
        room = await rw.get_room(vnum)
        await rw.update_room(
            vnum, RoomPatch.model_validate({**room.model_dump(by_alias=False, exclude={"id", "vnum", "zone_id"}), "extra": room.extra})
        )
    for vnum in (1, 2, 3, 4, 100):
        obj = await rw.get_object(vnum)
        await rw.update_object(
            vnum, ObjectPatch.model_validate({**obj.model_dump(by_alias=False, exclude={"id", "vnum", "zone_id"}), "extra": obj.extra})
        )
    assert digest(lib) == before


async def test_create_update_delete_mob_keeps_order_and_loader_compat(rw: DikumodAdapter, lib: Path) -> None:
    """Un mob nuovo finisce al posto giusto (ricerca binaria del gioco), con negozio; poi cambia vnum e si elimina."""
    vnum = await rw.next_content_vnum(1, "mob")
    new = await rw.create_mob(
        MobIn(
            vnum=vnum,
            zone_id=1,
            keywords="oste nuovo",
            short_description="Un oste",
            long_description="Un oste e' qui.",
            level=12,
            gold=100,
            race_id="human",
            flags=["sentinel"],
            extra={"affectedBy": ["sanctuary"], "immune": ["fire"]},
        )
    )
    assert new.extra["kind"] == "N" and new.race_id == "human" and new.extra["affectedBy"] == ["sanctuary"]
    text = read_text(lib / "dikumoddata.mob")
    index = c.generate_indices(text)
    assert [e.vnum for e in index.entries] == sorted(e.vnum for e in index.entries) and c.real_lookup(index, vnum) >= 0
    got = c.read_mobile(text, index.entries[c.real_lookup(index, vnum)].pos)
    assert not got["errors"] and (got["level"], got["race"], got["immune"], got["act"] & 2) == (12, 1, 1, 2)
    shop = {
        "producing": [3, -1, -1, -1, -1],
        "profitBuy": 1.5,
        "profitSell": 0.5,
        "types": [19, 0, 0, 0, 0],
        "messages": {"noSuchItem1": "%s Non l'ho.", "messageBuy": "%s Costa %d."},
        "room": 3,
        "open1": 0,
        "close1": 28,
    }
    updated = await rw.update_mob(vnum, MobPatch(extra={"shop": shop}))
    assert updated.extra["shop"]["messages"]["noSuchItem1"] == "%s Non l'ho."
    assert any(s["rest"][2] == vnum for s in c.boot_shops(read_text(lib / "dikumoddata.shp")))
    moved = await rw.update_mob(vnum, MobPatch(vnum=vnum + 1))
    assert moved.vnum == vnum + 1 and (await rw.get_mob(vnum + 1)).extra["shop"]["profitBuy"] == 1.5
    with expect_error(404, "mobs.not_found"):
        await rw.get_mob(vnum)
    await rw.delete_mob(vnum + 1)
    assert (vnum + 1) not in rw.store.mobs and (vnum + 1) not in rw.store.shops
    index = c.generate_indices(read_text(lib / "dikumoddata.mob"))
    assert [e.vnum for e in index.entries] == sorted(e.vnum for e in index.entries)


async def test_object_create_and_affects(rw: DikumodAdapter, lib: Path) -> None:
    """Oggetto nuovo con affect e extra description; il loader emulato legge E, A e P come previsto."""
    vnum = await rw.next_content_vnum(1, "object")
    obj = await rw.create_object(
        ObjectIn(
            vnum=vnum,
            zone_id=1,
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
    assert not got["errors"] and got["affects"] == [(1, 2), (13, 10)] and got["extras"] == [("gile", "Bello.\n")]
    assert got["forbidden"] == ("No.\n", "Non puo'.\n") and (got["type"], got["wear"], got["extra"]) == (9, 9, 64)
    with expect_error(422, "dikumod.too_many_affects"):
        await rw.update_object(vnum, ObjectPatch(affects={str(i): 1 for i in range(1, 7)}))
    await rw.delete_object(vnum)


async def test_zone_script_edit_rewrites_only_that_zone(rw: DikumodAdapter, lib: Path) -> None:
    """Un script identico non scrive nulla; con un commento nuovo cambia solo la zona toccata e le `O` hanno 5 numeri."""
    before = [z._src for z in load_world(lib).zon.items]
    script = await rw.list_reset_commands(1)
    same = ResetScriptIn(
        commands=[
            ResetCommandIn.model_validate(c_.model_dump(by_alias=False, exclude={"id", "zone_id", "order_index", "extra"}) | {"extra": {}})
            for c_ in script
        ]
    )
    digest_before = digest(lib)
    await rw.replace_reset_commands(1, same)
    assert digest(lib) == digest_before
    edited = same.model_copy(deep=True)
    edited.commands[0].comment = "commento nuovo"
    await rw.replace_reset_commands(1, edited)
    world = load_world(lib)
    after = [z._src for z in world.zon.items]
    assert [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b] == [1]
    assert world.zon.items[1].commands[0].comment_text == "commento nuovo"
    loaded = c.boot_zones(read_text(lib / "dikumoddata.zon"))
    assert len(loaded) == 3 and len(loaded[1]["cmds"]) == len(world.zon.items[1].commands)


async def test_exit_door_state_updates_bits_and_d_commands(rw: DikumodAdapter, lib: Path) -> None:
    """`isOpen/isLocked` aggiornano i bit di `exit_info` e i comandi `D` esistenti della stanza."""
    detail = await rw.get_room(1)
    exit_ = next(x for x in detail.exits if int(x.direction) == 1)
    updated = await rw.update_exit(1, exit_.id, ExitPatch(door_flag=DoorFlag.CLOSABLE, is_open=False, is_locked=True, key_vnum=4))
    assert updated.is_open is False and updated.is_locked is True and updated.door_flag == DoorFlag.CLOSABLE
    assert updated.extra["exitInfo"] & 7 == 7 and updated.extra["dState"] == 2
    d = [cmd for cmd in load_world(lib).zon.items[1].commands if cmd.letter == "D" and cmd.args[:2] == [1, 1]]
    assert d and all(cmd.args[2] == 2 for cmd in d)
    reopened = await rw.update_exit(1, exit_.id, ExitPatch(is_open=True, is_locked=False))
    assert reopened.is_open and not reopened.is_locked and reopened.extra["exitInfo"] & 6 == 0 and reopened.extra["dState"] == 0


async def test_room_vnum_change_follows_exits_and_doors(rw: DikumodAdapter, lib: Path) -> None:
    """Cambiando il vnum di una stanza, le uscite delle altre che portano li' seguono; il file resta ordinato."""
    free = await rw.next_content_vnum(1, "room")
    a = await rw.create_room(RoomIn(vnum=free, zone_id=1, name="A"))
    b = await rw.create_room(RoomIn(vnum=free + 1, zone_id=1, name="B", flags=["tunnel"], extra={"moblim": 3}))
    await rw.create_exit(a.id, ExitIn(direction=1, target_room_id=b.id))
    moved = await rw.update_room(b.id, RoomPatch(vnum=free + 2))
    assert moved.vnum == free + 2 and (await rw.get_room(a.id)).exits[0].target_room_vnum == free + 2 and moved.extra["moblim"] == 3
    text = read_text(lib / "dikumoddata.wld")
    rooms = c.boot_world(text)
    assert rooms[free]["exits"][1][4] == free + 2 and rooms[free + 2]["moblim"] == 3 and free + 1 not in rooms
    vnums = [int(x) for x in re.findall(r"(?m)^#(\d+)$", text)]
    assert vnums == sorted(vnums)
    await rw.delete_room(a.id)
    await rw.delete_room(moved.id)


async def test_zone_lifecycle(rw: DikumodAdapter, lib: Path) -> None:
    """Crea (in coda), aggiorna ed elimina una zona: rispetta l'ordine dei `top` e il formato del file."""
    free = await rw.next_zone_vnum(99)
    assert free.bottom_vnum == 200
    zone = await rw.create_zone(
        ZoneIn(vnum=free.vnum, name="Zona di prova", bottom_vnum=free.bottom_vnum, top_vnum=free.top_vnum, lifespan_minutes=15)
    )
    assert zone.id == 3 and (zone.bottom_vnum, zone.top_vnum) == (200, 299)
    with expect_error(422, "dikumod.zone_bottom_derived"):
        await rw.create_zone(ZoneIn(vnum=94, name="Con buco", bottom_vnum=500, top_vnum=600))
    with expect_error(409, "zones.range_overlap"):
        await rw.create_zone(ZoneIn(vnum=94, name="Sovrapposta", bottom_vnum=250, top_vnum=600))
    await rw.create_room(RoomIn(vnum=200, zone_id=3, name="Prima stanza"))
    with expect_error(422, "dikumod.vnum_out_of_range"):
        await rw.create_room(RoomIn(vnum=300, zone_id=3, name="Fuori"))
    with expect_error(409, "zones.not_empty"):
        await rw.delete_zone(3)
    await rw.update_zone(3, ZonePatch(name="Rinominata", lifespan_minutes=5, extra={"resetModeRaw": 6}))
    got = await rw.get_zone(3)
    assert (got.name, got.lifespan_minutes, got.reset_mode.name) == ("Rinominata", 5, "ALWAYS")
    loaded = c.boot_zones(read_text(lib / "dikumoddata.zon"))
    assert loaded[-1]["name"] == "Rinominata" and loaded[-1]["top"] == 299 and len(loaded) == 4
    await rw.delete_room(200)
    await rw.delete_zone(3)
    assert len(c.boot_zones(read_text(lib / "dikumoddata.zon"))) == 3


async def test_invalid_input_is_rejected_with_stable_codes(rw: DikumodAdapter, lib: Path) -> None:
    """`extra` sconosciuto, flag inesistente, tilde e righe pericolose: 422 con codice stabile e nessun byte scritto."""
    before = digest(lib)
    with expect_error(422, "dikumod.extra_unknown"):
        await rw.update_mob(1, MobPatch(extra={"nope": 1}))
    with expect_error(422, "dikumod.unknown_flag"):
        await rw.update_mob(1, MobPatch(flags=["inesistente"]))
    with expect_error(422, "dikumod.unsafe_text"):
        await rw.update_room(1, RoomPatch(description="con ~ dentro"))
    with expect_error(422, "dikumod.unsafe_text"):
        await rw.update_mob(1, MobPatch(detailed_description="riga\n#finta 7\n"))
    with expect_error(422, "dikumod.unsafe_text"):
        await rw.update_object(1, ObjectPatch(long_description="x\n%%\n"))
    with expect_error(422, "dikumod.unknown_race"):
        await rw.update_mob(1, MobPatch(race_id="elfonano"))
    with expect_error(409, "mobs.vnum_taken"):
        await rw.update_mob(1, MobPatch(vnum=2))
    assert digest(lib) == before
    assert (await rw.update_mob(1, MobPatch(level=5))).level == 5  # dopo gli errori il mondo e' ancora scrivibile


async def test_failed_update_leaves_cache_clean(rw: DikumodAdapter, lib: Path) -> None:
    """Una scrittura fallita dopo la mutazione in memoria non lascia traccia nella cache ne' sul disco al salvataggio seguente."""
    before = await rw.get_room(1)
    with expect_error(422, "dikumod.unsafe_text"):
        await rw.update_room(1, RoomPatch(name="Mutata", description="con ~ dentro"))
    assert await rw.get_room(1) == before
    await rw.update_mob(1, MobPatch(level=9))
    assert "Mutata" not in read_text(lib / "dikumoddata.wld")


async def test_unencodable_text_is_422_and_writes_nothing(rw: DikumodAdapter, lib: Path) -> None:
    """Un'emoji non sta in latin-1: 422 `dikumod.unencodable_text` (non 500) per stanza, mob e zona, nessun byte scritto."""
    before = digest(lib)
    with expect_error(422, "dikumod.unencodable_text"):
        await rw.update_room(1, RoomPatch(name="Valle \U0001f600"))
    with expect_error(422, "dikumod.unencodable_text"):
        await rw.update_mob(1, MobPatch(level=3, short_description="mob €"))
    with expect_error(422, "dikumod.unencodable_text"):
        await rw.update_zone(1, ZonePatch(name="Zona \U0001f600"))
    assert digest(lib) == before
    assert (await rw.update_mob(1, MobPatch(level=5))).level == 5


async def test_hash_lines_in_room_text_are_safe_and_roundtrip(rw: DikumodAdapter, lib: Path) -> None:
    """`.wld` e `.zon` non sono indicizzati per riga (`boot_world`/`boot_zones` leggono in sequenza): `#N` in un testo di stanza
    e' ammesso (a differenza di `.mob`/`.obj`) e il mondo si rilegge con le stesse stanze."""
    rooms = [r.id for r in (await rw.list_rooms(RoomPageParams(page_size=100))).items]
    await rw.update_room(1, RoomPatch(description="riga\n#2\nfine"))
    fresh = DikumodAdapter(WorldConfig(id="syn", kind="dikumod", name="S", path=str(lib), read_only=False))
    assert (await fresh.get_room(1)).description == "riga\n#2\nfine"
    assert [r.id for r in (await fresh.list_rooms(RoomPageParams(page_size=100))).items] == rooms
