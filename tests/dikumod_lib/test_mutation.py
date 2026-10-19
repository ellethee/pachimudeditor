"""Mutazioni sui dati reali: cambia solo cio' che si tocca, il file resta leggibile dal loader emulato."""

from pathlib import Path

import pytest

from pachimudeditor_adapter_dikumod.dikumod_lib import (
    Dice,
    DikumodWriteError,
    Mob,
    Obj,
    Raw,
    Room,
    ZoneCmd,
    format_mob,
    format_obj,
    format_room,
    index_hazard,
    insert_sorted,
    is_sorted,
    load_mob,
    load_obj,
    load_wld,
    load_zon,
    parse_mob,
    save,
    write_text,
)
from pachimudeditor_adapter_dikumod.dikumod_lib.files import read_text
from tests.dikumod_lib import c_loader as c


def _free(rf, start: int) -> int:  # type: ignore[no-untyped-def]
    """Il primo vnum >= `start` non usato nel file."""
    taken = {getattr(i, "vnum", None) for i in rf.items}
    while start in taken:
        start += 1
    return start


def _texts(rf) -> list[str]:  # type: ignore[no-untyped-def]
    """Il testo di ciascun elemento del file (sorgente o canonico)."""
    from pachimudeditor_adapter_dikumod.dikumod_lib.writer import item_text

    return [item_text(i) for i in rf.items]


@pytest.mark.real_dikumod
def test_editing_one_mob_changes_only_that_record(lib: Path) -> None:
    """Un mob modificato e' riscritto in forma canonica; tutti gli altri record (anche i corrotti) restano identici."""
    rf = load_mob(lib / "dikumoddata.mob")
    before = _texts(rf)
    mob = next(i for i in rf.items if getattr(i, "vnum", None) == 3000 and not isinstance(i, Raw))
    mob.level += 1
    mob.short = "Un mob rinominato"
    save(rf)
    again = load_mob(lib / "dikumoddata.mob")
    after = [i.src if isinstance(i, Raw) else i._src for i in again.items]
    changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert len(before) == len(after) and len(changed) == 1
    assert rf.items[changed[0]].vnum == 3000
    new = again.items[changed[0]]
    assert new.level == mob.level and new.short == "Un mob rinominato"
    assert len(again.raws()) == 33 and [r.src for r in again.raws()] == [r.src for r in rf.raws()]
    text = read_text(lib / "dikumoddata.mob")
    index = c.generate_indices(text)
    assert all(c.real_lookup(index, i.vnum) >= 0 for i in again.items)
    got = c.read_mobile(text, index.entries[changed[0]].pos)
    assert not got["errors"] and got["level"] == mob.level and got["short"] == "Un mob rinominato"


@pytest.mark.real_dikumod
def test_new_records_keep_the_file_sorted_and_loadable(lib: Path) -> None:
    """Un record nuovo va al suo posto (ricerca binaria del gioco) e il file termina con `%%`."""
    rf = load_mob(lib / "dikumoddata.mob")
    assert is_sorted(rf)
    mid = _free(rf, 3001)
    mob = Mob(
        vnum=mid,
        name="nuovo",
        short="Il nuovo",
        long="Un nuovo mob.\n",
        description="",
        kind="N",
        level=7,
        damage=Dice(1, 6, 2),
        hp_bonus=40,
    )
    insert_sorted(rf, mob)
    mob2 = Mob(
        vnum=99999,
        name="coda",
        short="coda",
        long="coda\n",
        kind="L",
        multi=2,
        race=4,
        gold=-0 + 10,
        exp=-50,
        sound="\nsuono",
        distant_sound="lontano",
        immune=4,
        sex_code=4,
    )
    insert_sorted(rf, mob2)
    assert is_sorted(rf)
    save(rf)
    text = read_text(lib / "dikumoddata.mob")
    assert text.rstrip().endswith("%%~")
    index = c.generate_indices(text)
    assert all(c.real_lookup(index, v) >= 0 for v in (mid, 99999, 3000))
    got = c.read_mobile(text, index.entries[c.real_lookup(index, 99999)].pos)
    assert not got["errors"] and (got["kind"], got["multi"], got["race"], got["exp"], got["immune"]) == ("L", 2, 4, -50, 4)
    assert got["sound"] == "\nsuono" and got["distant"] == "lontano"
    assert c.read_mobile(text, index.entries[c.real_lookup(index, mid)].pos)["damage"] == (1, 6, 2)


@pytest.mark.real_dikumod
def test_object_mutation_and_new_object(lib: Path) -> None:
    """Oggetto modificato/nuovo: E prima di A, al massimo 5 affect, `P` in fondo; il loader li rilegge uguali."""
    rf = load_obj(lib / "dikumoddata.obj")
    obj = next(i for i in rf.items if i.vnum == 3001)
    obj.cost += 5
    new = Obj(
        vnum=_free(rf, 3002),
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
    new.extra_descs = []
    from pachimudeditor_adapter_dikumod.dikumod_lib import ExtraDesc, ObjAffect

    new.extra_descs.append(ExtraDesc("spada", "Brilla.\n"))
    new.affects = [ObjAffect(1, 2), ObjAffect(13, 10)]
    new.forbidden = ("Non puoi.\n", "Non puo'.\n")
    insert_sorted(rf, new)
    save(rf)
    text = read_text(lib / "dikumoddata.obj")
    index = c.generate_indices(text)
    pos = index.entries[c.real_lookup(index, new.vnum)].pos
    got = c.read_object(text, pos)
    assert not got["errors"]
    assert (
        got["affects"] == [(1, 2), (13, 10)]
        and got["extras"] == [("spada", "Brilla.\n")]
        and got["forbidden"] == ("Non puoi.\n", "Non puo'.\n")
    )
    assert c.read_object(text, index.entries[c.real_lookup(index, 3001)].pos)["cost"] == obj.cost


@pytest.mark.real_dikumod
def test_room_mutation_only_touches_that_room(lib: Path) -> None:
    """Una stanza modificata (nome, nuova uscita, extra) cambia da sola; il loader la rilegge."""
    rf = load_wld(lib / "dikumoddata.wld")
    before = _texts(rf)
    room = next(i for i in rf.items if i.vnum == 3001)
    room.name = "Piazza rinominata"
    from pachimudeditor_adapter_dikumod.dikumod_lib import Exit, ExtraDesc

    room.exits = [x for x in room.exits if x.door != 5] + [Exit(door=5, to_room=3002, info=1, keyword="botola")]
    room.extra_descs.append(ExtraDesc("tabella", "Un testo.\n"))
    save(rf)
    again = load_wld(lib / "dikumoddata.wld")
    after = [i._src for i in again.items]
    assert [i for i, (a, b) in enumerate(zip(before, after)) if a != b] == [rf.items.index(room)]
    got = c.boot_world(read_text(lib / "dikumoddata.wld"))[3001]
    assert got["name"] == "Piazza rinominata" and got["exits"][5][4] == 3002 and ("tabella", "Un testo.\n") in got["extras"]


def test_special_room_blocks_roundtrip_canonically(tmp_path: Path) -> None:
    """Teleport (con e senza count), fiume, tunnel e luce si scrivono come li legge `load_one_room`."""
    from pachimudeditor_adapter_dikumod.dikumod_lib import Tele
    from pachimudeditor_adapter_dikumod.dikumod_lib.parser import parse_wld

    rooms = [
        Room(vnum=1, name="T", description="d\n", flags=1, sector=0, tele=Tele(10, 5071, 3, 10)),
        Room(vnum=2, name="T2", description="d\n", flags=0, sector=2, tele=Tele(1, 5, 1)),
        Room(vnum=3, name="F", description="d\n", sector=7, river=(3, 2)),
        Room(vnum=4, name="F9", description="d\n", sector=9, river=(1, 0)),
        Room(vnum=5, name="Tun", description="d\n", flags=256 | 8, sector=0, moblim=2, light=("notte\n", "giorno\n")),
    ]
    text = "".join(format_room(r) for r in rooms)
    got = c.boot_world(text)
    assert got[1]["tele"] == (10, 5071, 3, 10) and got[2]["tele"] == (1, 5, 1, 0) and got[1]["flags"] == 1
    assert got[3]["river"] == (3, 2) and got[4]["river"] == (1, 0) and got[5]["moblim"] == 2
    assert got[5]["light"] == ("notte\n", "giorno\n") and not any(r["unknown"] for r in got.values())
    back = parse_wld(text).items
    assert [repr(b) for b in back] == [repr(r) for r in rooms]


@pytest.mark.real_dikumod
def test_zone_edit_rewrites_only_that_zone_and_fixes_O(lib: Path) -> None:
    """Toccare un comando riscrive la sola zona; le sue `O` a 4 numeri diventano a 5 (e il loader non perde la zona)."""
    rf = load_zon(lib / "dikumoddata.zon")
    victim = next(z for z in rf.items if any(cmd.letter == "O" and len(cmd.args) == 3 for cmd in z.commands))
    before = [z._src for z in rf.items]
    victim.commands[0].comment = "\t; modificato"
    victim.items.append(ZoneCmd("M", 0, [3000, 1, 3001], "   ; nuovo"))
    victim.name = victim.name + " bis"
    save(rf)
    again = load_zon(lib / "dikumoddata.zon")
    after = [z._src for z in again.items]
    idx = rf.items.index(victim)
    assert [i for i, (a, b) in enumerate(zip(before, after)) if a != b] == [idx]
    z = again.items[idx]
    assert all(len(cmd.args) == {"O": 4}.get(cmd.letter, len(cmd.args)) for cmd in z.commands if cmd.letter == "O")
    loaded = c.boot_zones(read_text(lib / "dikumoddata.zon"))
    assert len(loaded) == 90  # le altre zone hanno ancora la trappola (byte intatti); la zona toccata e' sana
    mine = next(zz for zz in loaded if zz["name"] == victim.name)
    assert mine["cmds"][-1][:4] == ("M", 0, 3000, 1) and mine["cmds"][-1][4] == 3001


def test_zone_commands_canonical_text() -> None:
    """Righe canoniche: `O` sempre con 5 numeri, `G` con 2, commento dopo gli argomenti entro il limite del loader."""
    from pachimudeditor_adapter_dikumod.dikumod_lib import format_cmd

    assert format_cmd(ZoneCmd("O", 1, [10, 5, 3001])) == "O 1 10 5 3001 0\n"
    assert format_cmd(ZoneCmd("G", 0, [3023, 100])) == "G 0 3023 100\n"
    assert format_cmd(ZoneCmd("H", -5, [1, 2], "  ; odio")) == "H -5 1 2  ; odio\n"
    long = format_cmd(ZoneCmd("M", 0, [1, 1, 1], " ;" + "x" * 200))
    assert len(long.split("1 1 1", 1)[1]) <= 79
    with pytest.raises(DikumodWriteError):
        format_cmd(ZoneCmd("R", 0, [1, 2]))


def test_unsafe_texts_are_refused() -> None:
    """Testi che romperebbero l'indicizzazione o il parsing: `~`, riga che inizia per `#`/`%%`, frammento da 81 caratteri."""
    base = dict(vnum=5, name="a", short="b", kind="N")
    with pytest.raises(DikumodWriteError):
        format_mob(Mob(long="con ~ dentro\n", **base))
    with pytest.raises(DikumodWriteError):
        format_mob(Mob(description="riga\n#finta 7\n", **base))
    with pytest.raises(DikumodWriteError):
        format_obj(Obj(vnum=5, name="a", short="b", description="x\n%%\n"))
    assert index_hazard("#5\nok\n" + "y" * 81 + "#z\n") is not None  # il 82° carattere e' un `#`: fgets lo vede a inizio riga
    assert index_hazard("#5\nnormale\n  # con spazio\n") is None
    with pytest.raises(DikumodWriteError):
        format_obj(Obj(vnum=1, affects=[__import__("pachimudeditor_adapter_dikumod.dikumod_lib", fromlist=["x"]).ObjAffect(1, 1)] * 6))


def test_raw_records_survive_a_rewrite_and_terminator_is_added() -> None:
    """Un record corrotto non cambia; un file senza `%%` ne riceve uno in scrittura (il gioco altrimenti fa assert)."""
    text = "#1\na~\nb~\nc\n~\nd\n~\n0 0 0 Z\n1 2 3 4\n#2\nx~\ny~\nz\n~\nw\n~\n2 0 0 N\n1 20 0 5 1d4+0\n10 0\n8 8 1\n"
    rf = parse_mob(text, "x")
    assert len(rf.raws()) == 1 and rf.raws()[0].vnum == 1 and len(rf.entities()) == 1
    out = write_text(rf)
    assert out.startswith(text) and out.endswith("%%~\n")
    assert write_text(rf, ensure_terminator=False) == text


def test_zone_override_and_scripts_dat_roundtrip(lib: Path, tmp_path: Path) -> None:
    """`zones/<n>.zon` (solo comandi) e `scripts.dat`: invariati = stessi byte; modificati = righe canoniche con `S`."""
    from pachimudeditor_adapter_dikumod.dikumod_lib import ScriptEntry, parse_scripts_dat, parse_zone_override, save_zone_override
    from pachimudeditor_adapter_dikumod.dikumod_lib.writer import format_zone_override

    text = "M 0 1 1 2\t; primo\n* un commento\nO 0 5 10 20\n\nS\n"
    zo = parse_zone_override(text, 7)
    assert [c.letter for c in zo.commands] == ["M", "O"] and zo.has_end and zo.index == 7
    path = tmp_path / "7.zon"
    save_zone_override(path, zo)
    assert path.read_bytes().decode("latin-1") == text
    zo.commands[1].args.append(3)
    zo.items.append(ZoneCmd("G", 1, [4, 0], " ; dato"))
    assert format_zone_override(zo) == "M 0 1 1 2\t; primo\n* un commento\nO 0 5 10 20 3\n\nG 1 4 0 ; dato\nS\n"
    scripts = lib / "scripts.dat"
    if scripts.is_file():
        rf = parse_scripts_dat(read_text(scripts))
        assert write_text(rf) == read_text(scripts) and rf.entities()
        rf.items.append(ScriptEntry("Nuovo", 12345))
        assert write_text(rf).endswith("Nuovo 12345\n")
