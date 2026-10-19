"""Libreria Diku Modificato sul mondo sintetico (`tests/support/synthetic_worlds.py`): round trip, mutazioni, loader emulato.

Gira sempre, anche in CI. Gli equivalenti sui dati reali (conteggi, record corrotti, trappola `O` dei file originali) sono in
`test_roundtrip_real.py`, `test_mutation.py` e `test_loader_emulation.py` (marcati `real_dikumod`).
"""

from pathlib import Path

import pytest
from pachimudeditor_adapter_dikumod.dikumod_lib import (
    Dice,
    Exit,
    ExtraDesc,
    Mob,
    Obj,
    ObjAffect,
    Raw,
    ZoneCmd,
    insert_sorted,
    is_sorted,
    load_mob,
    load_obj,
    load_wld,
    load_world,
    load_zon,
    parse_mob,
    parse_obj,
    parse_shp,
    parse_wld,
    parse_zon,
    save,
    write_text,
)
from pachimudeditor_adapter_dikumod.dikumod_lib.files import read_text
from pachimudeditor_adapter_dikumod.dikumod_lib.writer import item_text

from tests.dikumod_lib import c_loader as c
from tests.support.synthetic_worlds import write_dikumod_world

PARSERS = {"wld": parse_wld, "mob": parse_mob, "obj": parse_obj, "zon": parse_zon, "shp": parse_shp}


@pytest.fixture
def lib(tmp_path: Path) -> Path:
    """Cartella `lib/` sintetica."""
    return write_dikumod_world(tmp_path / "lib")


def _texts(rf) -> list[str]:  # type: ignore[no-untyped-def]
    """Il testo di ciascun elemento del file."""
    return [item_text(i) for i in rf.items]


# --------------------------------------------------------------------------- round trip


def test_world_loads_without_errors(lib: Path) -> None:
    """Il mondo sintetico e' sano: nessun record corrotto ne' diagnostica; conteggi attesi."""
    world = load_world(lib)
    assert not any(rf.raws() for rf in (world.wld, world.mob, world.obj, world.zon, world.shp)) and not world.diagnostics
    assert (len(world.wld.entities()), len(world.mob.entities()), len(world.obj.entities())) == (5, 3, 5)
    assert (len(world.zon.entities()), len(world.shp.entities())) == (3, 1)


def test_untouched_files_are_byte_identical(lib: Path) -> None:
    """parse -> write senza modifiche = stessi byte, con e senza terminatore."""
    world = load_world(lib)
    for name in PARSERS:
        rf = getattr(world, name)
        assert write_text(rf, ensure_terminator=False) == read_text(rf.path), name
        assert write_text(rf) == read_text(rf.path), name


def test_canonical_rewrite_is_semantically_idempotent(lib: Path) -> None:
    """Riscrittura canonica: le entita' riparse sono uguali e una seconda riscrittura e' identica."""
    world = load_world(lib)
    for name, parse in PARSERS.items():
        rf = getattr(world, name)
        first = write_text(rf, canonical=True)
        again = parse(first, name)
        assert write_text(again, canonical=True) == first, name
        if name != "zon":  # le zone cambiano forma (`O` a 5 numeri): stesso numero di comandi
            assert [i.src if isinstance(i, Raw) else repr(i) for i in rf.items] == [
                i.src if isinstance(i, Raw) else repr(i) for i in again.items
            ]


def test_parser_agrees_with_the_loader(lib: Path) -> None:
    """`boot_world` emulato e parser: stessi campi, uscite ed extra per ogni stanza; negozi e zone coincidono."""
    world = load_world(lib)
    rooms = c.boot_world(read_text(world.wld.path))
    assert len(rooms) == len(world.wld.items)
    for r in world.wld.items:
        got = rooms[r.vnum]
        assert not got["unknown"] and not got["errors"], r.vnum
        assert (got["name"], got["desc"], got["flags"], got["sector"]) == (r.name, r.description, r.flags, r.sector)
        assert got["exits"] == {
            x.door: (x.description, x.keyword, x.info, x.key, x.to_room, -1 if x.open_cmd is None else x.open_cmd) for x in r.exits
        }
        assert got["extras"] == [(e.keyword, e.description) for e in r.extra_descs]
    shops = c.boot_shops(read_text(world.shp.path))
    for mine in world.shp.entities():
        theirs = next(s for s in shops if s["tag"] == mine.tag)
        assert theirs["producing"] == mine.producing and theirs["types"] == mine.types and theirs["rest"][2] == mine.keeper
    zones = c.boot_zones(read_text(world.zon.path))
    assert [(z["name"], z["top"]) for z in zones] == [(z.name, z.top) for z in world.zon.items]


def test_the_O_trap_and_the_canonical_rewrite(lib: Path) -> None:
    """Un `O` a 4 numeri desincronizza il loader C (la riga dopo viene divorata); la riscrittura canonica (5 numeri) le restituisce tutte."""
    zon = (lib / "dikumoddata.zon").read_text(encoding="latin-1").replace("O -5 100 1 101 0\n", "O -5 100 1 101\n")
    (lib / "dikumoddata.zon").write_text(zon, encoding="latin-1")
    world = load_world(lib)
    trapped = c.boot_zones(read_text(world.zon.path))
    total = sum(len(z.commands) for z in world.zon.items)
    assert len(trapped) != len(world.zon.items) or sum(len(z["cmds"]) for z in trapped) != total  # il loader C si desincronizza
    fixed = c.boot_zones(write_text(world.zon, canonical=True))
    assert [(z["name"], z["top"]) for z in fixed] == [(z.name, z.top) for z in world.zon.items]


# --------------------------------------------------------------------------- mutazioni


def test_editing_one_mob_changes_only_that_record(lib: Path) -> None:
    """Un mob modificato e' riscritto in forma canonica; tutti gli altri record restano identici."""
    rf = load_mob(lib / "dikumoddata.mob")
    before = _texts(rf)
    mob = next(i for i in rf.items if getattr(i, "vnum", None) == 1 and not isinstance(i, Raw))
    mob.level += 1
    mob.short = "Un mob rinominato"
    save(rf)
    again = load_mob(lib / "dikumoddata.mob")
    after = [i.src if isinstance(i, Raw) else i._src for i in again.items]
    changed = [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b]
    assert len(before) == len(after) and len(changed) == 1 and rf.items[changed[0]].vnum == 1
    text = read_text(lib / "dikumoddata.mob")
    index = c.generate_indices(text)
    assert all(c.real_lookup(index, i.vnum) >= 0 for i in again.items)
    got = c.read_mobile(text, index.entries[changed[0]].pos)
    assert not got["errors"] and got["level"] == mob.level and got["short"] == "Un mob rinominato"


def test_new_records_keep_the_file_sorted_and_loadable(lib: Path) -> None:
    """Un record nuovo va al suo posto (ricerca binaria del gioco) e il file termina con `%%`."""
    rf = load_mob(lib / "dikumoddata.mob")
    assert is_sorted(rf)
    insert_sorted(
        rf,
        Mob(
            vnum=50,
            name="nuovo",
            short="Il nuovo",
            long="Un nuovo mob.\n",
            description="",
            kind="N",
            level=7,
            damage=Dice(1, 6, 2),
            hp_bonus=40,
        ),
    )
    insert_sorted(
        rf,
        Mob(vnum=99999, name="coda", short="coda", long="coda\n", kind="L", multi=2, race=4, gold=10, exp=-50, sound="\nsuono", distant_sound="lontano", immune=4, sex_code=4),
    )  # fmt: skip
    assert is_sorted(rf)
    save(rf)
    text = read_text(lib / "dikumoddata.mob")
    assert text.rstrip().endswith("%%~")
    index = c.generate_indices(text)
    assert all(c.real_lookup(index, v) >= 0 for v in (1, 50, 99999))
    got = c.read_mobile(text, index.entries[c.real_lookup(index, 99999)].pos)
    assert not got["errors"] and (got["kind"], got["multi"], got["race"], got["exp"], got["immune"]) == ("L", 2, 4, -50, 4)
    assert c.read_mobile(text, index.entries[c.real_lookup(index, 50)].pos)["damage"] == (1, 6, 2)


def test_object_mutation_and_new_object(lib: Path) -> None:
    """Oggetto modificato/nuovo: E prima di A, al massimo 5 affect, `P` in fondo; il loader li rilegge uguali."""
    rf = load_obj(lib / "dikumoddata.obj")
    obj = next(i for i in rf.items if i.vnum == 1)
    obj.cost += 5
    new = Obj(
        vnum=20,
        name="spada nuova",
        short="una spada",
        description="Una spada.\n",
        type=5,
        wear_flags=8193,
        values=[0, 2, 4, 3],
        weight=5,
        cost=100,
        rent=10,
    )
    new.extra_descs.append(ExtraDesc("spada", "Brilla.\n"))
    new.affects = [ObjAffect(1, 2), ObjAffect(13, 10)]
    new.forbidden = ("Non puoi.\n", "Non puo'.\n")
    insert_sorted(rf, new)
    save(rf)
    text = read_text(lib / "dikumoddata.obj")
    index = c.generate_indices(text)
    got = c.read_object(text, index.entries[c.real_lookup(index, 20)].pos)
    assert not got["errors"] and got["affects"] == [(1, 2), (13, 10)] and got["extras"] == [("spada", "Brilla.\n")]
    assert got["forbidden"] == ("Non puoi.\n", "Non puo'.\n")
    assert c.read_object(text, index.entries[c.real_lookup(index, 1)].pos)["cost"] == obj.cost


def test_room_mutation_only_touches_that_room(lib: Path) -> None:
    """Una stanza modificata (nome, nuova uscita, extra) cambia da sola; il loader la rilegge."""
    rf = load_wld(lib / "dikumoddata.wld")
    before = _texts(rf)
    room = next(i for i in rf.items if i.vnum == 1)
    room.name = "Piazza rinominata"
    room.exits = [x for x in room.exits if x.door != 5] + [Exit(door=5, to_room=2, info=1, keyword="botola")]
    room.extra_descs.append(ExtraDesc("tabella", "Un testo.\n"))
    save(rf)
    again = load_wld(lib / "dikumoddata.wld")
    after = [i._src for i in again.items]
    assert [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b] == [rf.items.index(room)]
    got = c.boot_world(read_text(lib / "dikumoddata.wld"))[1]
    assert got["name"] == "Piazza rinominata" and got["exits"][5][4] == 2 and ("tabella", "Un testo.\n") in got["extras"]


def test_zone_edit_rewrites_only_that_zone(lib: Path) -> None:
    """Toccare un comando riscrive la sola zona; il loader legge la zona modificata con i comandi nuovi."""
    rf = load_zon(lib / "dikumoddata.zon")
    victim = rf.items[1]
    before = [z._src for z in rf.items]
    victim.commands[0].comment = "\t; modificato"
    victim.items.append(ZoneCmd("M", 0, [2, 1, 3], "   ; nuovo"))
    victim.name += " bis"
    save(rf)
    again = load_zon(lib / "dikumoddata.zon")
    after = [z._src for z in again.items]
    assert [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b] == [1]
    loaded = c.boot_zones(read_text(lib / "dikumoddata.zon"))
    assert len(loaded) == 3
    mine = next(zz for zz in loaded if zz["name"] == victim.name)
    assert mine["cmds"][-1][:4] == ("M", 0, 2, 1) and mine["cmds"][-1][4] == 3


def test_parse_wld_roundtrip_of_a_new_world_text(lib: Path) -> None:
    """Il testo `.wld` riscritto in forma canonica si riparsifica in stanze uguali (sanity del parser sulle uscite)."""
    rf = load_wld(lib / "dikumoddata.wld")
    again = parse_wld(write_text(rf, canonical=True), "wld")
    assert [repr(r) for r in again.items] == [repr(r) for r in rf.items]
