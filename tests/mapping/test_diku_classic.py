"""Prova 2: `diku_classic.yaml` (un file per tipo, zone a catena su `top`) su un mondo sintetico costruito con record
reali di Diku Modificato (`tests/support/mapping_worlds.py`).

I controlli sui valori leggono il testo grezzo con espressioni regolari indipendenti dal motore. In coda: cosa succede sui
file Diku Modificato **interi** (le irregolarita' note che la grammatica non puo' esprimere senza hook).
"""

import re
from pathlib import Path
from typing import Any

import pytest
from pachimudeditor_adapter_mapping.adapter import MappingAdapter
from pachimudeditor_adapter_mapping.grammar import MappingParseError, parse_document
from pachimudeditor_adapter_mapping.schema import MappingSpec, load_mapping
from pachimudeditor_adapter_mapping.writer import write_document
from fastapi import HTTPException
from pachimudeditor.common.enums import ZoneCommandType
from pachimudeditor.common.enums import DoorFlag, SectorType

from pachimudeditor.common.adapters.models import (
    ExitPatch,
    MobPageParams,
    MobPatch,
    ObjectPageParams,
    ObjectPatch,
    ResetCommandIn,
    ResetScriptIn,
    RoomIn,
    RoomPageParams,
    RoomPatch,
    ZoneIn,
    ZonePageParams,
    ZonePatch,
)
from pachimudeditor.common.adapters.registry import WorldConfig
from tests.support.mapping_worlds import DIKU_MAPPING, DIKUMOD_LIB, chunks, dikumod_text


@pytest.fixture(scope="module")
def spec() -> MappingSpec:
    """La mappatura Diku classico."""
    return load_mapping(DIKU_MAPPING)


def adapter_for(root: Path, *, read_only: bool = False) -> MappingAdapter:
    """Adapter con `diku_classic.yaml` sulla cartella `root`."""
    return MappingAdapter(WorldConfig(id="dikumod", kind="mapping", mapping=str(DIKU_MAPPING), path=str(root), read_only=read_only))


def text_of(root: Path, name: str) -> str:
    """Contenuto di un file del mondo (latin-1)."""
    return (root / name).read_text(encoding="latin-1")


def block(root: Path, name: str, vnum: int) -> str:
    """Il blocco di testo del record `vnum` di un file `#N`."""
    return next(c for c in chunks(text_of(root, name), r"#\d+\s*$") if re.match(rf"#{vnum}\n", c))


def bits(text: str) -> int:
    """Somma `a|b|c` come `fread_number`."""
    return sum(int(p) for p in text.split("|"))


async def page(fn: Any, params_cls: Any) -> list[Any]:
    """Un elenco intero (le prove hanno meno di 500 elementi per tipo)."""
    return (await fn(params_cls(page=1, pageSize=500))).items


def expect_code(error: pytest.ExceptionInfo[HTTPException], status: int, code: str) -> None:
    """Verifica status e codice stabile di un `HTTPException`."""
    assert error.value.status_code == status and error.value.detail[0]["code"] == code, error.value.detail


def changed_blocks(spec: MappingSpec, kind: str, old: str, new: str) -> list[tuple[str, str]]:
    """Coppie `(vecchio, nuovo)` dei record il cui testo differisce (stesso numero di record)."""
    a = [r.src for s in parse_document(spec, kind, old).sections for r in s.records]
    b = [r.src for s in parse_document(spec, kind, new).sections for r in s.records]
    assert len(a) == len(b)
    return [(x, y) for x, y in zip(a, b, strict=True) if x != y]


# --------------------------------------------------------------------------- parsing e scrittura


def test_world_parses_and_rewrites_identically(dikumod_dir: Path, spec: MappingSpec) -> None:
    """Ogni file ha tanti record quanti blocchi `#N` e si riscrive byte per byte."""
    expected = {
        "zon": ("dikumoddata.zon", 4),
        "wld": ("dikumoddata.wld", 159),
        "mob": ("dikumoddata.mob", 98),
        "obj": ("dikumoddata.obj", 95),
        "shp": ("dikumoddata.shp", 5),
    }
    for kind, (name, count) in expected.items():
        text = text_of(dikumod_dir, name)
        doc = parse_document(spec, kind, text, name)
        assert sum(len(s.records) for s in doc.sections) == count, name
        assert write_document(spec, kind, doc) == text, name


def test_tolerated_irregularities_roundtrip(spec: MappingSpec) -> None:
    """Le irregolarita' Diku Modificato che la grammatica tollera (flag `optional`/`tolerant`/`end_before`) si leggono e si riscrivono uguali."""
    zon = (
        "\n#7\nProva~\n99 5 2\n"
        "M 0 10 1 20   ; ok\n"
        "O 0 64 5 167\t\t;rock\n"  # `O` con 4 numeri invece di 5
        "O -5 1 99 99 10\n"
        "E 1 16026 999       ; A lute\n"  # `E` senza posizione
        "$\n"  # riga `$` vagante
        "* commento\n"
        "S\n"
        "#8\nSenza S~\n199 5 2\nG 1 3 4\n"  # zona senza `S` finale
        "#9999999\n$~\n"
    )
    doc = parse_document(spec, "zon", zon)
    first, second = (r.fields for r in doc.sections[0].records)
    by_cmd = [(x["cmd"], x.get("room_limit"), x.get("wear")) for x in first["resets"]]
    assert by_cmd == [("M", None, None), ("O", None, None), ("O", 10, None), ("E", None, None), ("$", None, None), ("*", None, None)]
    assert [x["cmd"] for x in second["resets"]] == ["G"]
    assert write_document(spec, "zon", doc) == zon  # invariato: byte per byte
    first["resets"].append({"cmd": "O", "if_flag": 0, "obj": 70, "limit": 5, "room": 167})
    first["top"] = 98
    second["top"] = 198
    out = write_document(spec, "zon", doc)
    assert "O 0 64 5 167 0 ;rock\n" in out  # canonico: un `O` letto con 4 numeri si riscrive con 5 (il quinto vale 0)
    assert out.count("\nS\n") == 2 and out.endswith("#9999999\n$~\n")  # `S` riscritta anche per la zona senza terminatore

    mob = "\n#1\nPuff~\nPuff~\nPuff e' qui.~\n~\n2097153 0 1000 S\n26 1 -10 5d10+550 4d6+3\n-1 5000 155 9\n8 8 1 0 0 0\n%%~\n"
    doc = parse_document(spec, "mob", mob)
    f = doc.sections[0].records[0].fields
    assert (f["mtype"], f["hp"], f["gold_real"], f["exp"], f["race"], f["junk"]) == (
        "S",
        {"n": 5, "t": 10, "b": 550},
        5000,
        155,
        9,
        "0 0 0",
    )
    assert write_document(spec, "mob", doc) == mob
    tolerant = mob.replace("5d10+550", "1d4")  # dado senza `+K` (irregolarita' reale di 17 mob)
    assert parse_document(spec, "mob", tolerant).sections[0].records[0].fields["hp"] == {"n": 1, "t": 4, "b": 0}


# --------------------------------------------------------------------------- lettura confrontata con il testo grezzo


async def test_zones_chain_on_top(dikumod_dir: Path) -> None:
    """Le zone sono i record del `.zon`: id = `top`, bottom = top precedente + 1, un solo file, sempre abilitate."""
    a = adapter_for(dikumod_dir)
    zones = await page(a.list_zones, ZonePageParams)
    assert [(z.id, z.bottom_vnum, z.top_vnum) for z in zones] == [(0, 0, 0), (49, 1, 49), (199, 50, 199), (249, 200, 249)]
    assert [z.name for z in zones][1:3] == ["LIMBO", "Temple Extensions"]
    assert [z.extra["znum"] for z in zones] == [1, 2, 3, 4]
    assert all(z.enabled and "file" not in z.extra and "resets" not in z.extra for z in zones)
    assert (zones[2].lifespan_minutes, zones[2].reset_mode.name) == (20, "ALWAYS") and zones[1].reset_mode.name == "NEVER"
    summary = await a.zone_summary(249)
    assert (summary.room_count, summary.mob_count, summary.object_count) == (50, 45, 14)


async def test_rooms_match_raw_text(dikumod_dir: Path) -> None:
    """Nome, flag, settore, uscite ed extra di ogni stanza coincidono con il testo del `.wld`."""
    a = adapter_for(dikumod_dir)
    rooms = {r.vnum: r for r in await page(a.list_rooms, RoomPageParams)}
    raw = chunks(text_of(dikumod_dir, "dikumoddata.wld"), r"#\d+\s*$")
    assert len(rooms) == len(raw) == 159
    table = a.tables["room_flags"]
    teleports = 0
    for chunk in raw:
        vnum = int(re.match(r"#(\d+)", chunk).group(1))  # type: ignore[union-attr]
        m = re.match(r"(?s)#\d+\n(.*?)~\n.*?~\n\s*(-?\d+) ([0-9|]+) (-?\d+)(.*)", chunk)
        assert m is not None
        room = rooms[vnum]
        assert room.name == m.group(1).strip("\n")
        assert room.flags == table.flag_names(bits(m.group(3)))
        detail = await a.get_room(vnum)
        assert len(detail.exits) == len(re.findall(r"(?m)^D[0-5]\s*$", chunk)), vnum
        assert len(detail.extra_descriptions) == len(re.findall(r"(?m)^E\s*$", chunk)), vnum
        if m.group(4) == "-1":
            teleports += 1
            assert {"teleTime", "teleTarget", "teleMask"} <= set(room.extra)  # blocco condizionale `sector == -1`
    assert teleports >= 1


async def test_mobs_and_objects_match_raw_text(dikumod_dir: Path) -> None:
    """Livello, thac0, AC, tipo e allineamento dei mob; tipo, peso, costo e valori degli oggetti coincidono con il grezzo."""
    a = adapter_for(dikumod_dir)
    mobs = {m.vnum: m for m in await page(a.list_mobs, MobPageParams)}
    kinds = set()
    for chunk in chunks(text_of(dikumod_dir, "dikumoddata.mob"), r"#\d+\s*$"):
        vnum = int(re.match(r"#(\d+)", chunk).group(1))  # type: ignore[union-attr]
        head = re.search(r"(?m)^([0-9|]+) ([0-9|]+) (-?\d+) ([A-Z])( \d+)?\n(\d+) (-?\d+) (-?\d+) ", chunk)
        assert head is not None, vnum
        mob = mobs[vnum]
        kinds.add(head.group(4))
        assert (mob.alignment, mob.extra["mtype"], mob.level, mob.thac0, mob.armor_class) == (
            int(head.group(3)), head.group(4), int(head.group(6)), int(head.group(7)), int(head.group(8))
        )  # fmt: skip
        assert mob.flags == a.tables["act_flags"].flag_names(bits(head.group(1)))
        if head.group(4) != "S":
            assert (mob.hp_dice_count, mob.hp_die_size) == (mob.level, 8)  # `level`d8 + bonus
    assert {"S", "N"} <= kinds
    objects = {o.vnum: o for o in await page(a.list_objects, ObjectPageParams)}
    for chunk in chunks(text_of(dikumod_dir, "dikumoddata.obj"), r"#\d+\s*$"):
        vnum = int(re.match(r"#(\d+)", chunk).group(1))  # type: ignore[union-attr]
        m = re.search(
            r"(?s)^#\d+\n(?:.*?~\n){4}\s*(\d+) ([0-9|]+) ([0-9|]+)\n\s*(-?\d+) (-?\d+) (-?\d+) (-?\d+)\s*\n\s*(\d+) (-?\d+) (-?\d+)", chunk
        )
        assert m is not None, vnum
        obj = objects[vnum]
        assert (obj.extra["itemType"], obj.weight, obj.cost, obj.rent) == (
            int(m.group(1)),
            int(m.group(8)),
            int(m.group(9)),
            int(m.group(10)),
        )
        assert [obj.value_0, obj.value_1, obj.value_2, obj.value_3] == [int(m.group(i)) for i in range(4, 8)]
        assert len(obj.affects) <= len(re.findall(r"(?m)^A\s*$", chunk))


async def test_reset_scripts_match_raw_text(dikumod_dir: Path) -> None:
    """Una zona ha tanti comandi quante righe di comando (M O P G E D) nel `.zon`; commenti e `if_flag <= 0` sono letti bene."""
    a = adapter_for(dikumod_dir)
    for zone_chunk in chunks(text_of(dikumod_dir, "dikumoddata.zon"), r"#\d+\s*$"):
        found = re.search(r"(?m)^(\d+) \d+ \d+$", zone_chunk)
        if found is None:
            continue  # record terminatore `#9999999`
        top = int(found.group(1))
        commands = await a.list_reset_commands(top)
        assert len(commands) == len(re.findall(r"(?m)^[MOPGED] ", zone_chunk)), top
    temple = await a.list_reset_commands(199)
    assert temple[0].command_type is ZoneCommandType.LOAD_OBJECT and temple[0].if_flag is False  # `O -5 ...`: sempre
    assert (temple[0].arg1, temple[0].arg2, temple[0].arg3, temple[0].arg4) == (1, 99, 99, 10)
    limbo = await a.list_reset_commands(49)
    assert [(c.command_type, c.arg1, c.arg3) for c in limbo] == [(ZoneCommandType.LOAD_MOB, 3, 2)]
    doom = await a.list_reset_commands(249)
    held = next(c for c in doom if c.command_type is ZoneCommandType.EQUIP_OBJECT and c.arg1 == 201)
    assert held.arg_str == "hold" and held.if_flag is True  # slot 17 della tabella `wear_pos`; `E 1 ...`: se il mob e' stato caricato
    assert any(c.command_type is ZoneCommandType.SET_DOOR_STATE and c.arg_str == "CLOSED" for c in doom)


# --------------------------------------------------------------------------- scritture


async def test_edit_room_rewrites_only_its_block(dikumod_dir: Path, spec: MappingSpec) -> None:
    """`update_room` cambia solo il blocco della stanza nel `.wld`; gli altri file restano identici."""
    a = adapter_for(dikumod_dir)
    before = {n: text_of(dikumod_dir, n) for n in ("dikumoddata.zon", "dikumoddata.mob", "dikumoddata.obj", "dikumoddata.shp")}
    old = text_of(dikumod_dir, "dikumoddata.wld")
    await a.update_room(5, RoomPatch(name="Una carrozza", flags=["indoors", "dark"]))
    new = text_of(dikumod_dir, "dikumoddata.wld")
    ((old_block, new_block),) = changed_blocks(spec, "wld", old, new)
    assert old_block.lstrip().startswith("#5\n") and "Una carrozza~" in new_block
    assert new == old.replace(old_block, new_block, 1)
    assert "\n1 9 -1 30 6 1 0" in new_block  # flag riscritti come numero (8|1), blocco teletrasporto invariato
    assert {n: text_of(dikumod_dir, n) for n in before} == before


async def test_exit_door_bits(dikumod_dir: Path) -> None:
    """`doorFlag`, `isOpen` e `isLocked` sono espressioni sui bit di `exit_info` (1 ISDOOR, 2 CLOSED, 4 LOCKED, 32 PICKPROOF)."""
    a = adapter_for(dikumod_dir)
    room = await a.get_room(5)
    exit_ = room.exits[0]
    assert (exit_.door_flag, exit_.is_open, exit_.is_locked) == (DoorFlag.NONE, True, False)
    patched = await a.update_exit(5, exit_.id, ExitPatch(door_flag=DoorFlag.CLOSABLE, is_open=False))
    assert (patched.door_flag, patched.is_open, patched.is_locked) == (DoorFlag.CLOSABLE, False, False)
    assert re.search(r"(?m)^3 -1 98 -1$", block(dikumod_dir, "dikumoddata.wld", 5))  # exit_info 1|2; `open_cmd -1` conservato
    locked = await a.update_exit(5, exit_.id, ExitPatch(is_locked=True, key_vnum=7))
    assert (locked.is_locked, locked.key_vnum) == (True, 7)
    assert re.search(r"(?m)^7 7 98 -1$", block(dikumod_dir, "dikumoddata.wld", 5))  # 1|2|4
    proof = await a.update_exit(5, exit_.id, ExitPatch(door_flag=DoorFlag.PICKPROOF))
    assert proof.door_flag is DoorFlag.PICKPROOF and proof.is_locked and not proof.is_open


async def test_create_edit_delete_content(dikumod_dir: Path, spec: MappingSpec) -> None:
    """Stanza, mob, oggetto: creazione ordinata per vnum, patch (gold `-1`, affects), eliminazione; solo un blocco cambia."""
    a = adapter_for(dikumod_dir)
    vnum = await a.next_content_vnum(49, "room")
    old_wld = text_of(dikumod_dir, "dikumoddata.wld")
    room = await a.create_room(RoomIn(vnum=vnum, zone_id=49, name="Nuova stanza", description="Descrizione.", sector_type=SectorType.CITY))
    new_wld = text_of(dikumod_dir, "dikumoddata.wld")
    assert room.sector_type is SectorType.CITY and f"#{vnum}\nNuova stanza~" in new_wld
    order = [int(n) for n in re.findall(r"(?m)^#(\d+)$", new_wld)]
    assert order == sorted(order) and len(order) == 160  # inserita al suo posto per vnum
    assert new_wld.replace(f"#{vnum}\n", "", 1) != old_wld
    with pytest.raises(HTTPException) as error:
        await a.create_room(RoomIn(vnum=500, zone_id=49, name="Fuori range"))
    expect_code(error, 422, "mapping.vnum_out_of_range")
    # mob con `gold == -1`: la riga `-1 <gold> <exp> <race>` si riscrive coerente
    mob = next(
        m
        for m in await page(a.list_mobs, MobPageParams)
        if re.search(rf"(?ms)^#{m.vnum}\n.*?^-1 ", text_of(dikumod_dir, "dikumoddata.mob"))
    )
    patched = await a.update_mob(mob.vnum, MobPatch(gold=1234, level=mob.level + 1, flags=["isnpc", "sentinel"], race_id="orc"))
    assert (patched.gold, patched.level, patched.flags, patched.race_id, patched.experience) == (
        1234,
        mob.level + 1,
        ["sentinel", "isnpc"],
        "orc",
        mob.experience,
    )
    block = re.search(rf"(?ms)^#{mob.vnum}\n.*?(?=^#\d+$|^%%)", text_of(dikumod_dir, "dikumoddata.mob")).group(0)  # type: ignore[union-attr]
    assert re.search(rf"(?m)^-1 1234 {mob.experience} {a.tables['races'].value_of('orc')}$", block)
    obj = (await page(a.list_objects, ObjectPageParams))[0]
    updated = await a.update_object(obj.vnum, ObjectPatch(cost=77, affects={"hit": 3}, wear_flags=["take", "hold"]))
    assert (updated.cost, updated.affects, updated.wear_flags) == (77, {"hit": 3}, ["take", "hold"])
    assert re.search(rf"(?s)#{obj.vnum}\n.*?\nA\n13 3\n", text_of(dikumod_dir, "dikumoddata.obj"))
    await a.delete_room(vnum)
    assert text_of(dikumod_dir, "dikumoddata.wld") == old_wld


async def test_zones_are_appended_in_order(dikumod_dir: Path) -> None:
    """Una zona nuova va in coda (top oltre l'ultima, bottom derivato); `top` non puo' scavalcare le vicine."""
    a = adapter_for(dikumod_dir)
    free = await a.next_zone_vnum(99)
    assert (free.bottom_vnum, free.top_vnum, free.vnum) == (250, 349, 349)
    zon_before = text_of(dikumod_dir, "dikumoddata.zon")
    zone = await a.create_zone(ZoneIn(vnum=349, name="Zona nuova", bottom_vnum=250, top_vnum=349, lifespan_minutes=30))
    assert (zone.id, zone.bottom_vnum, zone.top_vnum, zone.lifespan_minutes) == (349, 250, 349, 30)
    zon = text_of(dikumod_dir, "dikumoddata.zon")
    assert "Zona nuova~\n349 30 " in zon and zon.endswith("#9999999\n$~\n") and zon.startswith(zon_before.split("#9999999")[0].rstrip("\n"))
    room = await a.create_room(RoomIn(vnum=await a.next_content_vnum(349, "room"), zone_id=349, name="Prima"))
    assert room.vnum == 250 and room.zone_id == 349
    for bad, code in (
        (ZoneIn(vnum=100, name="Tra le altre", bottom_vnum=60, top_vnum=100), "zones.range_overlap"),
        (ZoneIn(vnum=449, name="Salto", bottom_vnum=400, top_vnum=449), "mapping.zone_bottom_derived"),
    ):
        with pytest.raises(HTTPException) as error:
            await a.create_zone(bad)
        expect_code(error, 409 if code.startswith("zones") else 422, code)
    with pytest.raises(HTTPException) as error:
        await a.update_zone(199, ZonePatch(top_vnum=205))  # sposterebbe le stanze 200-205 nella zona 249... che e' un'altra zona
    expect_code(error, 422, "mapping.zone_range_has_items")
    with pytest.raises(HTTPException) as error:
        await a.update_zone(199, ZonePatch(bottom_vnum=40))
    expect_code(error, 422, "mapping.zone_bottom_derived")
    renamed = await a.update_zone(349, ZonePatch(name="Zona rinominata", lifespan_minutes=45))
    assert (renamed.name, renamed.lifespan_minutes) == ("Zona rinominata", 45)
    with pytest.raises(HTTPException) as error:
        await a.delete_zone(349)
    expect_code(error, 409, "zones.not_empty")
    await a.delete_room(250)
    await a.delete_zone(349)
    assert text_of(dikumod_dir, "dikumoddata.zon") == zon_before


async def test_reset_scripts_roundtrip_and_canonical_O(dikumod_dir: Path) -> None:
    """Rimandare lo script letto non cambia byte (commenti e `O` con 4 numeri compresi); uno script diverso riscrive i soli
    comandi nuovi in forma canonica (`O` sempre con 5 numeri) e perde i commenti."""
    a = adapter_for(dikumod_dir)
    original = text_of(dikumod_dir, "dikumoddata.zon")
    commands = await a.list_reset_commands(199)
    same = ResetScriptIn(
        commands=[
            ResetCommandIn(**c.model_dump(by_alias=False, include={"command_type", "if_flag", "arg1", "arg2", "arg3", "arg4", "arg_str"}))
            for c in commands
        ]
    )
    await a.replace_reset_commands(199, same)
    assert text_of(dikumod_dir, "dikumoddata.zon") == original
    changed = ResetScriptIn(
        commands=[*same.commands[:2], ResetCommandIn(command_type=ZoneCommandType.LOAD_OBJECT, arg1=70, arg2=5, arg3=167, arg4=None)]
    )
    await a.replace_reset_commands(199, changed)
    zon = text_of(dikumod_dir, "dikumoddata.zon")
    assert "O -5 1 99 99 10\n" in zon and "O -5 2 99 99 10\n" in zon  # riusati (if_flag -5 conservato)
    assert re.search(r"(?m)^O 0 70 5 167 0$", zon)  # il quinto numero e' sempre scritto
    assert "donation room" not in zon  # i commenti vanno persi quando lo script cambia
    assert [(c.arg1, c.arg4) for c in await a.list_reset_commands(199)] == [(1, 10), (2, 10), (70, 0)]


async def test_unmapped_reset_commands_block_replace(dikumod_dir: Path) -> None:
    """I comandi `H/F/C/Z` non hanno un tipo neutro: restano nel file ma sostituire lo script li cancellerebbe (422)."""
    zon = text_of(dikumod_dir, "dikumoddata.zon")
    (dikumod_dir / "dikumoddata.zon").write_bytes(zon.replace("* donation room.", "H 0 5 3\n* donation room.", 1).encode("latin-1"))
    a = adapter_for(dikumod_dir)
    commands = await a.list_reset_commands(199)
    assert commands[0].arg1 == 1  # `H` non e' elencato
    script = ResetScriptIn(commands=[ResetCommandIn(command_type=ZoneCommandType.LOAD_MOB, arg1=3, arg2=1, arg3=2, arg4=1)])
    with pytest.raises(HTTPException) as error:
        await a.replace_reset_commands(199, script)
    expect_code(error, 422, "mapping.reset_unmapped_commands")
    assert "H 0 5 3" in text_of(dikumod_dir, "dikumoddata.zon")


async def test_read_only_world_rejects_writes(dikumod_dir: Path) -> None:
    """Con `read_only` ogni scrittura e' 409 `world.read_only` e i file non cambiano."""
    a = adapter_for(dikumod_dir, read_only=True)
    before = text_of(dikumod_dir, "dikumoddata.wld")
    with pytest.raises(HTTPException) as error:
        await a.update_room(5, RoomPatch(name="x"))
    expect_code(error, 409, "world.read_only")
    assert text_of(dikumod_dir, "dikumoddata.wld") == before


# --------------------------------------------------------------------------- limiti sui file Diku Modificato interi


@pytest.mark.skipif(not DIKUMOD_LIB.is_dir(), reason="dati Diku Modificato non trovati")
def test_real_dikumod_files_known_irregularities(spec: MappingSpec) -> None:
    """Sui file Diku Modificato interi: `.zon` (93 zone), `.wld` (3856) e `.obj` (2041) si leggono e si riscrivono identici;
    `.mob` e `.shp` contengono record corrotti/troncati (vedi docs/formats/dikumod.md) che una grammatica rigorosa rifiuta
    con riga e colonna: cosi' si evita di scambiarli per la fine del file. Servirebbe un hook di resincronizzazione."""
    for kind, name, count in (("zon", "dikumoddata.zon", 93), ("wld", "dikumoddata.wld", 3856), ("obj", "dikumoddata.obj", 2041)):
        text = dikumod_text(name)
        doc = parse_document(spec, kind, text, name)
        assert sum(len(s.records) for s in doc.sections) == count, name
        assert write_document(spec, kind, doc) == text, name
    for kind, name in (("mob", "dikumoddata.mob"), ("shp", "dikumoddata.shp")):
        with pytest.raises(MappingParseError) as error:
            parse_document(spec, kind, dikumod_text(name), name)
        assert error.value.line > 1 and name in str(error.value)
