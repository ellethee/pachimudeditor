"""Prova 1: il motore dichiarativo con `rom.yaml` riproduce `adapters_rom_lib` (a mano) su TUTTE le aree reali di basedmud.

- parsing: stessi conteggi e stessi campi chiave per ogni record di ogni file (copie temporanee);
- scrittura: i file non toccati si riscrivono byte per byte; modificare un mob riscrive solo il suo blocco;
- adapter: `MappingAdapter` e `BasedMudAdapter` danno gli stessi DTO e, a parita' di operazioni, gli stessi file.
"""

import difflib
import shutil
from pathlib import Path
from typing import Any

import pytest
from pachimudeditor_adapter_basedmud.adapter import BasedMudAdapter
from pachimudeditor_adapter_mapping.adapter import MappingAdapter
from pachimudeditor_adapter_mapping.grammar import Document, parse_document
from pachimudeditor_adapter_mapping.schema import MappingSpec, load_mapping
from pachimudeditor_adapter_mapping.store import decode_bytes
from pachimudeditor_adapter_mapping.writer import write_document
from pachimudeditor_adapter_basedmud.rom_lib import load_area_file
from pachimudeditor.common.enums import ZoneCommandType
from pachimudeditor.common.enums import Direction, DoorFlag

from pachimudeditor.common.adapters.models import (
    ExitIn,
    ExtraDescriptionIn,
    MobPageParams,
    MobPatch,
    ObjectPageParams,
    ObjectPatch,
    ResetCommandIn,
    ResetScriptIn,
    RoomPageParams,
    RoomPatch,
    ZonePageParams,
    ZonePatch,
)
from pachimudeditor.common.adapters.registry import WorldConfig
from tests.support.mapping_worlds import ROM_AREA, ROM_MAPPING
from tests.support.real_data import HAVE_ROM
from tests.support.synthetic_worlds import write_rom_area

if HAVE_ROM:  # (file, mob, nome breve del mob, stanza, altra stanza, chiave, oggetto, zona) usati dagli scenari di scrittura
    FILE, MOB, MOB_SHORT, ROOM, ROOM2, KEY, OBJ, ZONE = "midgaard.are", 3000, "the wizard", 3001, 3002, 3005, 3000, 3000
else:
    FILE, MOB, MOB_SHORT, ROOM, ROOM2, KEY, OBJ, ZONE = "prato.are", 5000, "il maestro", 5000, 5001, 5004, 5001, 5000


@pytest.fixture(scope="module")
def spec() -> MappingSpec:
    """La mappatura ROM di esempio."""
    return load_mapping(ROM_MAPPING)


def parse(spec: MappingSpec, path: Path) -> tuple[Document, str]:
    """Documento del motore e testo decodificato di un `.are`."""
    text, _ = decode_bytes(path.read_bytes())
    return parse_document(spec, "area", text, path.name), text


def records(doc: Document, header: str) -> list[Any]:
    """I record della sezione `header`."""
    return [r for s in doc.sections if s.spec is not None and s.spec.header == header for r in s.records]


# ---- campi chiave per tipo, nell'ordine in cui li espone la libreria a mano
RESET_FIELDS = {
    "M": ("if_flag", "mob", "limit", "room", "room_limit"),
    "O": ("if_flag", "obj", "limit", "room"),
    "P": ("if_flag", "obj", "limit", "container", "count"),
    "G": ("if_flag", "obj", "limit"),
    "E": ("if_flag", "obj", "limit", "wear"),
    "D": ("if_flag", "room", "door", "state"),
    "R": ("if_flag", "room", "doors"),
}


def test_parses_all_real_areas_like_rom_lib(rom_dir: Path, spec: MappingSpec) -> None:
    """Per ogni `.are`: stessi conteggi per sezione e stessi campi chiave di ogni record (zona, mob, oggetti, stanze, reset, negozi, spec)."""
    files = sorted(rom_dir.glob("*.are"))
    assert len(files) >= (40 if HAVE_ROM else 2)
    totals = {"MOBILES": 0, "OBJECTS": 0, "ROOMS": 0, "RESETS": 0, "SHOPS": 0, "SPECIALS": 0}
    for path in files:
        doc, _ = parse(spec, path)
        lib = load_area_file(path)
        for name in totals:
            mine = records(doc, name)
            theirs = lib.section(name, create=False).items if lib.section(name, create=False) else []
            assert len(mine) == len(theirs), f"{path.name} {name}"
            totals[name] += len(mine)
        zones = records(doc, "AREA") + records(doc, "AREADATA")
        if lib.header is not None:
            assert len(zones) == 1
            z = zones[0].fields
            expected = (lib.header.min_vnum, lib.header.max_vnum) if lib.header.vnum_raw is None else (None, None)
            assert (z["name"], z.get("min_vnum"), z.get("max_vnum")) == (lib.header.name, *expected)
        for mine, theirs in zip(records(doc, "MOBILES"), lib.mobiles, strict=True):
            f = mine.fields
            assert (f["vnum"], f["name"], f["short_descr"], f["level"], f["race"], f["act"], f["wealth"], f["ac"]) == (
                theirs.vnum, theirs.name, theirs.short_descr, theirs.level, theirs.race, theirs.act, theirs.wealth, theirs.ac,
            )  # fmt: skip
            assert (f["hit"], f["damage"], f["mana"]) == tuple(
                {"n": d.number, "t": d.type, "b": d.bonus} for d in (theirs.hit, theirs.damage, theirs.mana)
            )
            assert [(x["word"], x["value"]) for x in f["flag_removals"]] == [(x.word, x.value) for x in theirs.flag_removals]
            assert [(x["trigger"], x["vnum"], x["phrase"]) for x in f["mprogs"]] == [(x.trigger, x.vnum, x.phrase) for x in theirs.mprogs]
        for mine, theirs in zip(records(doc, "OBJECTS"), lib.objects, strict=True):
            f = mine.fields
            assert (f["vnum"], f["name"], f["item_type"], f["cost"], f["weight"], f["values"], f["extra_flags"], f["wear_flags"]) == (
                theirs.vnum, theirs.name, theirs.item_type, theirs.cost, theirs.weight, theirs.values, theirs.extra_flags, theirs.wear_flags,
            )  # fmt: skip
            assert len(f["affects"]) + len(f["flag_affects"]) == len(theirs.affects) and len(f["extra_descs"]) == len(theirs.extra_descs)
        for mine, theirs in zip(records(doc, "ROOMS"), lib.rooms, strict=True):
            f = mine.fields
            assert (f["vnum"], f["name"], f["room_flags"], f["sector"], f["heal_rate"], f["mana_rate"], f["owner"], f["clan"]) == (
                theirs.vnum, theirs.name, theirs.room_flags, theirs.sector, theirs.heal_rate, theirs.mana_rate, theirs.owner, theirs.clan,
            )  # fmt: skip
            assert [(x["door"], x["to_vnum"], x["locks"], x["key"]) for x in f["exits"]] == [
                (x.door, x.to_vnum, x.locks, x.key) for x in theirs.exits
            ]
            assert [x["keyword"] for x in f["extra_descs"]] == [x.keyword for x in theirs.extra_descs]
        lib_resets = lib.section("RESETS", create=False).items if lib.section("RESETS", create=False) else []
        for mine, theirs in zip(records(doc, "RESETS"), lib_resets, strict=True):
            f = mine.fields
            if f["cmd"] == "*":
                assert theirs.text.startswith("*")
                continue
            assert f["cmd"] == theirs.command
            assert [f[n] for n in RESET_FIELDS[f["cmd"]]] == theirs.args
        for mine, theirs in zip(records(doc, "SHOPS"), lib.shops, strict=True):
            assert (mine.fields["keeper"], mine.fields["buy_types"]) == (theirs.keeper, theirs.buy_types)
        for mine, theirs in zip(records(doc, "SPECIALS"), lib.specials, strict=False):
            if mine.fields["cmd"] == "M":
                assert (mine.fields["mob_vnum"], mine.fields["function"]) == (theirs.mob_vnum, theirs.function)
    assert (
        totals["ROOMS"] > (3000 if HAVE_ROM else 5)
        and totals["MOBILES"] > (900 if HAVE_ROM else 3)
        and totals["RESETS"] > (5000 if HAVE_ROM else 10)
    )


def test_untouched_files_rewrite_byte_identical(rom_dir: Path, spec: MappingSpec) -> None:
    """Letto e riscritto senza modifiche, ogni file (anche quelli con sezioni non modellate) e' identico all'originale."""
    for path in sorted(rom_dir.iterdir()):
        if path.suffix != ".are":
            continue
        raw = path.read_bytes()
        text, encoding = decode_bytes(raw)
        doc = parse_document(spec, "area", text, path.name)
        assert write_document(spec, "area", doc).encode(encoding) == raw, path.name
        assert all(not r.dirty for s in doc.sections for r in s.records)


async def test_editing_a_mob_rewrites_only_its_block(rom_dir: Path, spec: MappingSpec) -> None:
    """`update_mob` cambia solo i byte del blocco del mob; gli altri record e gli altri file restano identici."""
    path = rom_dir / FILE
    before = {p.name: p.read_bytes() for p in rom_dir.iterdir() if p.is_file()}
    old_doc, old_text = parse(spec, path)
    adapter = MappingAdapter(WorldConfig(id="rom", kind="mapping", mapping=str(ROM_MAPPING), path=str(rom_dir)))
    await adapter.update_mob(MOB, MobPatch(level=24, short_description="il mago"))

    new_doc, new_text = parse(spec, path)
    old_blocks = [r.src for s in old_doc.sections for r in s.records]
    new_blocks = [r.src for s in new_doc.sections for r in s.records]
    changed = [i for i, (a, b) in enumerate(zip(old_blocks, new_blocks, strict=True)) if a != b]
    assert len(old_blocks) == len(new_blocks) and len(changed) == 1
    old_block, new_block = old_blocks[changed[0]], new_blocks[changed[0]]
    assert old_block.lstrip().startswith(f"#{MOB}") and MOB_SHORT in old_block and "il mago" in new_block
    assert new_text == old_text.replace(old_block, new_block, 1)  # tutto il resto del file e' identico
    assert {p.name: p.read_bytes() for p in rom_dir.iterdir() if p.is_file() and p.name != FILE} == {
        k: v for k, v in before.items() if k != FILE
    }


async def all_pages(fn: Any, params_cls: Any) -> list[Any]:
    """Tutte le pagine di un elenco."""
    out, page = [], 1
    while True:
        result = await fn(params_cls(page=page, pageSize=500))
        out += result.items
        if len(out) >= result.total:
            return out
        page += 1


def pair(rom_dir: Path) -> tuple[MappingAdapter, BasedMudAdapter]:
    """I due adapter sulla stessa cartella."""
    return (
        MappingAdapter(WorldConfig(id="m", kind="mapping", mapping=str(ROM_MAPPING), path=str(rom_dir), read_only=True)),
        BasedMudAdapter(WorldConfig(id="b", kind="basedmud", path=str(rom_dir), read_only=True)),
    )


async def test_adapter_dtos_equal_basedmud(rom_dir: Path) -> None:
    """Zone, stanze (con uscite ed extra), mob, oggetti e script di reset: stessi DTO del `BasedMudAdapter`.

    Unica differenza ammessa: i `valueN` degli oggetti i cui slot contengono nomi/lettere (il mapping dichiarativo
    legge solo i decimali: `None`), e i campi `extra` che solo uno dei due espone.
    """
    mine, theirs = pair(rom_dir)
    for fn_m, fn_b, params in (
        (mine.list_zones, theirs.list_zones, ZonePageParams),
        (mine.list_rooms, theirs.list_rooms, RoomPageParams),
        (mine.list_mobs, theirs.list_mobs, MobPageParams),
        (mine.list_objects, theirs.list_objects, ObjectPageParams),
    ):
        xs, ys = await all_pages(fn_m, params), await all_pages(fn_b, params)
        assert [x.id for x in xs] == [y.id for y in ys]
        for x, y in zip(xs, ys, strict=True):
            dx, dy = x.model_dump(by_alias=False), y.model_dump(by_alias=False)
            for key in dx:
                if key == "extra":
                    assert all(dx[key][k] == dy[key][k] for k in set(dx[key]) & set(dy[key])), (x.id, key)
                elif key.startswith("value_") and dx[key] is None:
                    continue
                else:
                    assert dx[key] == dy[key], (type(x).__name__, x.id, key)
    for zone in await all_pages(mine.list_zones, ZonePageParams):
        assert await mine.list_reset_commands(zone.id) == await theirs.list_reset_commands(zone.id)
    for room in (await all_pages(mine.list_rooms, RoomPageParams))[::9]:  # un campione (ogni lettura rilegge lo stato dei file)
        a, b = await mine.get_room(room.id), await theirs.get_room(room.id)
        assert a.exits == b.exits and a.extra_descriptions == b.extra_descriptions


async def scenario(adapter: Any) -> None:
    """Una sequenza di scritture di ogni tipo (zona, stanza, uscita, extra, mob, oggetto, reset)."""
    await adapter.update_mob(MOB, MobPatch(level=24, short_description="il mago", flags=["npc", "sentinel"], race_id="elf", hp_bonus=5))
    await adapter.update_room(ROOM, RoomPatch(name="Altare", flags=["indoors", "no_recall"], heal_rate=120, clan_id="xx", owner="luca"))
    await adapter.update_object(
        OBJ, ObjectPatch(cost=99, extra_flags=["glow"], wear_flags=["take", "hold"], affects={"strength": 2, "hit roll": 1}, value_2=None)
    )
    await adapter.create_exit(
        ROOM,
        ExitIn(
            direction=Direction.WEST,
            target_room_id=ROOM2,
            door_flag=DoorFlag.CLOSABLE,
            is_open=False,
            key_vnum=KEY,
            keywords="porta",
            description="Una porta.",
        ),
    )
    await adapter.create_extra_description(ROOM, ExtraDescriptionIn(keywords="statua", text="Una statua."))
    await adapter.update_zone(ZONE, ZonePatch(name="Midgaard2", builder="luca", min_level=2, max_level=40))
    commands = [
        ResetCommandIn(command_type=ZoneCommandType.LOAD_MOB, arg1=MOB, arg2=2, arg3=ROOM, arg4=3),
        ResetCommandIn(command_type=ZoneCommandType.EQUIP_OBJECT, arg1=OBJ, arg_str="hold"),
        ResetCommandIn(command_type=ZoneCommandType.GIVE_OBJECT, arg1=OBJ),
        ResetCommandIn(command_type=ZoneCommandType.PUT_OBJECT, arg1=OBJ, arg3=OBJ, arg4=2),
        ResetCommandIn(command_type=ZoneCommandType.SET_DOOR_STATE, arg1=ROOM, arg2=0, arg_str="CLOSED"),
    ]
    await adapter.replace_reset_commands(ZONE, ResetScriptIn(commands=commands))


async def test_same_operations_produce_the_same_files(rom_dir: Path, tmp_path: Path) -> None:
    """Stesse scritture sui due adapter -> stessi file `.are`, salvo due formattazioni equivalenti del testo canonico
    (slot oggetto `'beer'` tra apici nell'oggetto riscritto e `M 100 H 120` su una riga)."""
    other = tmp_path / "other"
    shutil.copytree(rom_dir, other)
    mine = MappingAdapter(WorldConfig(id="m", kind="mapping", mapping=str(ROM_MAPPING), path=str(rom_dir)))
    theirs = BasedMudAdapter(WorldConfig(id="b", kind="basedmud", path=str(other)))
    await scenario(mine)
    await scenario(theirs)
    for path in sorted(rom_dir.glob("*.are")):
        a = path.read_text(encoding="latin-1")
        b = (
            (other / path.name)
            .read_text(encoding="latin-1")
            .replace("300 300 'beer' 0 0", "300 300 beer 0 0")
            .replace("M 100 H 120\n", "H 120\n")
        )
        assert a == b, "".join(list(difflib.unified_diff(b.splitlines(True), a.splitlines(True)))[:40])
    original = ROM_AREA if HAVE_ROM else write_rom_area(tmp_path / "orig")
    assert (rom_dir / FILE).read_bytes() != (original / FILE).read_bytes()  # riscritto davvero
