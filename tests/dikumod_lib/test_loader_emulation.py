"""Parser e writer contro l'emulazione rigorosa del loader del gioco (`c_loader.py`) sui dati reali."""

from pathlib import Path


from pachimudeditor_adapter_dikumod.dikumod_lib import Raw, load_world, write_text
from pachimudeditor_adapter_dikumod.dikumod_lib.files import read_text
from tests.dikumod_lib import c_loader as c


def _dir_files(rf_group: dict[int, object]) -> dict[int, str]:
    """Testo dei file per-vnum (`objects/<vnum>`)."""
    return {v: read_text(rf.path) for v, rf in rf_group.items()}  # type: ignore[attr-defined]


def test_every_vnum_is_reachable_with_the_games_binary_search(lib: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """`generate_indices` + `real_mobile/real_object` trovano ogni vnum del file (richiede i record in ordine)."""
    world = load_world(lib)
    mob_index = c.generate_indices(read_text(world.mob.path))
    obj_index = c.generate_indices(read_text(world.obj.path), _dir_files(world.object_overrides))
    mobs = [i.vnum for i in world.mob.items]
    objs = [i.vnum for i in world.obj.items]
    assert [e.vnum for e in mob_index.entries[: mob_index.sort_top]] == mobs
    assert [e.vnum for e in obj_index.entries[: obj_index.sort_top]] == objs
    assert all(c.real_lookup(mob_index, v) >= 0 for v in mobs)
    assert all(c.real_lookup(obj_index, v) >= 0 for v in objs)
    with capsys.disabled():
        print(
            f"\n[{lib.parent.name}] indice mob {len(mobs)} / oggetti {len(objs)} voci ({len(obj_index.entries) - obj_index.sort_top} solo-directory)"
        )


def test_parser_agrees_with_the_loader_on_every_mob_and_object(lib: Path) -> None:
    """Per ogni mob/oggetto interpretato, `read_mobile`/`read_obj_from_file` vedono gli stessi valori, senza errori."""
    world = load_world(lib)
    text = read_text(world.mob.path)
    index = c.generate_indices(text)
    offsets = {}
    for e in index.entries:
        offsets.setdefault(e.vnum, []).append(e.pos)
    seen: dict[int, int] = {}
    for m in world.mob.items:
        n = seen.get(m.vnum, 0)
        seen[m.vnum] = n + 1
        if isinstance(m, Raw):
            continue
        got = c.read_mobile(text, offsets[m.vnum][n])
        assert not got["errors"], (m.vnum, got["errors"])
        assert (got["act"], got["affected"], got["alignment"], got["kind"], got["level"], got["thac0"], got["ac"]) == (
            m.act,
            m.affected,
            m.alignment,
            m.kind,
            m.level,
            m.thac0,
            m.ac,
        ), m.vnum
        assert (got["gold"], got["exp"], got["race"], got["position"], got["default_pos"], got["sex_code"]) == (
            m.gold,
            m.exp,
            m.race,
            m.position,
            m.default_pos,
            m.sex_code,
        ), m.vnum
        assert got["damage"] == (m.damage.n, m.damage.m, m.damage.k)
        assert got["hp"] == ((m.hp_dice.n, m.hp_dice.m, m.hp_dice.k) if m.hp_dice else None)
        if m.kind != "S":
            assert got["hp_bonus"] == m.hp_bonus
        assert (got["name"], got["short"], got["long"], got["desc"]) == (m.name, m.short, m.long, m.description)
        if 3 <= m.sex_code < 6:
            assert (got["immune"], got["m_immune"], got["susc"]) == (m.immune, m.m_immune, m.susc)
        if m.kind == "L":
            assert (got["sound"], got["distant"]) == (m.sound, m.distant_sound)
    otext = read_text(world.obj.path)
    oindex = c.generate_indices(otext)
    pos: dict[int, list[int]] = {}
    for e in oindex.entries:
        pos.setdefault(e.vnum, []).append(e.pos)
    seen = {}
    for o in world.obj.items:
        n = seen.get(o.vnum, 0)
        seen[o.vnum] = n + 1
        got = c.read_object(otext, pos[o.vnum][n])
        assert not got["errors"], (o.vnum, got["errors"])
        assert (got["type"], got["extra"], got["wear"], got["values"], got["weight"], got["cost"], got["rent"]) == (
            o.type,
            o.extra_flags,
            o.wear_flags,
            o.values,
            o.weight,
            o.cost,
            o.rent,
        ), o.vnum
        assert got["affects"] == [(a.location, a.modifier) for a in o.affects]
        assert got["extras"] == [(e.keyword, e.description) for e in o.extra_descs]
        assert got["forbidden"] == o.forbidden
        assert (got["name"], got["short"], got["desc"], got["action"]) == (o.name, o.short, o.description, o.action)


def test_parser_agrees_with_the_loader_on_every_room(lib: Path) -> None:
    """`boot_world` emulato e parser: stessi campi, uscite, extra, teleport, fiume, tunnel, luce; nessun token ignoto."""
    world = load_world(lib)
    rooms = c.boot_world(read_text(world.wld.path))
    last = {r.vnum: r for r in world.wld.items}  # vnum doppi: nel gioco l'ultimo sovrascrive
    assert len(rooms) == len(last)
    for r in last.values():
        got = rooms[r.vnum]
        assert not got["unknown"] and not got["errors"], r.vnum
        assert (got["name"], got["desc"], got["flags"], got["sector"]) == (r.name, r.description, r.flags, r.sector), r.vnum
        assert got["tele"] == ((r.tele.time, r.tele.target, r.tele.mask, r.tele.count or 0) if r.tele else None)
        assert got["river"] == r.river and got["moblim"] == r.moblim
        assert got["exits"] == {
            x.door: (x.description, x.keyword, x.info, x.key, x.to_room, -1 if x.open_cmd is None else x.open_cmd) for x in r.exits
        }
        assert got["extras"] == [(e.keyword, e.description) for e in r.extra_descs]
        assert got["light"] == r.light


def test_original_zone_file_hits_the_O_trap_and_canonical_rewrite_fixes_it(lib: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Il loader C legge 90 zone dal file originale (trappola dei `O` a 4 numeri); riscritto in forma canonica ne legge 93."""
    world = load_world(lib)
    original = c.boot_zones(read_text(world.zon.path))
    assert len(original) == 90
    fixed = c.boot_zones(write_text(world.zon, canonical=True))
    assert len(fixed) == 93
    for z, loaded in zip(world.zon.items, fixed, strict=True):
        assert (loaded["num"], loaded["name"], loaded["top"], loaded["life"], loaded["mode"]) == (
            z.num,
            z.name,
            z.top,
            z.lifespan,
            z.reset_mode,
        )
    with capsys.disabled():
        print(f"\n[{lib.parent.name}] zone viste dal loader: originale {len(original)}, riscrittura canonica {len(fixed)}")


def test_canonical_zone_commands_match_the_parser_exactly(lib: Path) -> None:
    """Dopo la riscrittura canonica ogni comando riletto dal loader ha lettera, if e argomenti del parser."""
    world = load_world(lib)
    fixed = c.boot_zones(write_text(world.zon, canonical=True))
    count = {"M": 3, "O": 4, "G": 2, "E": 3, "P": 3, "D": 3, "C": 3, "H": 2, "F": 2, "Z": 2}
    for z, loaded in zip(world.zon.items, fixed, strict=True):
        cmds = z.commands
        assert len(loaded["cmds"]) == len(cmds), z.name
        for cmd, got in zip(cmds, loaded["cmds"]):
            args = (list(cmd.args) + [0] * 4)[: count[cmd.letter]]
            letter, if_flag, a1, a2, a3, a4 = got
            assert (letter, if_flag) == (cmd.letter, cmd.if_flag)
            assert (a1, a2) == (args[0], args[1])
            if count[cmd.letter] >= 3:
                assert a3 == args[2], (z.name, cmd)
            if cmd.letter == "O":
                assert a4 == args[3]


def test_shop_file_loader(lib: Path) -> None:
    """Il loader dei negozi legge i negozi sani del parser (il troncato fa perdere il sincronismo, come nel gioco)."""
    world = load_world(lib)
    shops = c.boot_shops(read_text(world.shp.path))
    by_tag = {sh["tag"]: sh for sh in shops}
    for mine in world.shp.entities():
        theirs = by_tag[mine.tag]
        assert theirs["producing"] == mine.producing and theirs["types"] == mine.types
        assert theirs["messages"] == mine.messages and theirs["rest"][2] == mine.keeper
    assert any(r.vnum == 18201 for r in world.shp.raws())
