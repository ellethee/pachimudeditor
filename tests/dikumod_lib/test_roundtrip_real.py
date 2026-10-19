"""Round-trip sui dati REALI di dikumod e dikumod2 (copiati in una cartella temporanea): conteggi, byte-identita', idempotenza."""

import pytest
import collections
from pathlib import Path

from pachimudeditor_adapter_dikumod.dikumod_lib import (
    Raw,
    load_world,
    parse_mob,
    parse_obj,
    parse_shp,
    parse_wld,
    parse_zon,
    write_text,
)
from pachimudeditor_adapter_dikumod.dikumod_lib.files import read_text

EXPECTED = {
    "dikumod": {"rooms": 3841, "mobs": 2093, "bad_mobs": 33, "objects": 2025, "zones": 93, "commands": 7832},
    "dikumod2": {"rooms": 3856, "mobs": 2097, "bad_mobs": 33, "objects": 2041, "zones": 93, "commands": 7861},
}
PARSERS = {"wld": parse_wld, "mob": parse_mob, "obj": parse_obj, "zon": parse_zon, "shp": parse_shp}


@pytest.mark.real_dikumod
def test_counts_match_the_spec(variant: str, lib: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Stanze, mob, oggetti, zone e comandi come nel documento del formato; stampa le statistiche (-s)."""
    world = load_world(lib)
    want = EXPECTED[variant]
    got = {
        "rooms": len(world.wld.entities()),
        "mobs": len(world.mob.entities()),
        "bad_mobs": len(world.mob.raws()),
        "objects": len(world.obj.entities()),
        "zones": len(world.zon.entities()),
        "commands": sum(len(z.commands) for z in world.zon.entities()),
    }
    assert got == want
    assert not world.wld.raws() and not world.obj.raws() and not world.zon.raws()
    errors = collections.Counter(r.error.split(":")[0] for r in world.mob.raws())
    shops = (len(world.shp.entities()), len(world.shp.raws())) if world.shp else (0, 0)
    with capsys.disabled():
        print(
            f"\n[{variant}] {got} | negozi {shops[0]} + {shops[1]} corrotto | override stanze {len(world.room_overrides)}, "
            f"oggetti {len(world.object_overrides)} | mob corrotti per categoria {dict(errors)} | "
            f"diagnostiche {len(world.diagnostics)}"
        )


def test_untouched_files_are_byte_identical(lib: Path) -> None:
    """parse -> write senza modifiche = stessi byte, per i file principali e per tutti i file per-vnum."""
    world = load_world(lib)
    for name in ("wld", "mob", "obj", "zon", "shp"):
        rf = getattr(world, name)
        assert write_text(rf, ensure_terminator=False) == read_text(rf.path), name
        assert write_text(rf) == read_text(rf.path), name  # il terminatore c'e' gia': nessuna aggiunta
    if world.scripts is not None:
        assert write_text(world.scripts) == read_text(world.scripts.path)
    for group in (world.room_overrides, world.object_overrides):
        for rf in group.values():
            assert write_text(rf, ensure_terminator=False) == read_text(rf.path), rf.path


def test_canonical_rewrite_is_semantically_idempotent(lib: Path) -> None:
    """Riscrittura canonica di tutto il file: le entita' riparse sono uguali e una seconda riscrittura e' identica."""
    world = load_world(lib)
    for name, parse in PARSERS.items():
        rf = getattr(world, name)
        first = write_text(rf, canonical=True)
        again = parse(first, name)
        second = write_text(again, canonical=True)
        assert second == first, name
        a = [i.src if isinstance(i, Raw) else repr(i) for i in rf.items]
        b = [i.src if isinstance(i, Raw) else repr(i) for i in again.items]
        if name == "zon":  # la forma canonica porta a 5 i numeri delle `O` (vedi test_loader_emulation): stesse zone e comandi
            assert [(z.num, z.name, z.top, len(z.commands)) for z in rf.entities()] == [
                (z.num, z.name, z.top, len(z.commands)) for z in again.entities()
            ]
            continue
        assert a == b, name


@pytest.mark.real_dikumod
def test_bad_mobs_are_kept_as_raw_with_error(lib: Path) -> None:
    """I 33 mob corrotti restano visibili con errore e riga, e nessun byte va perso nella riscrittura."""
    world = load_world(lib)
    raws = world.mob.raws()
    assert len(raws) == 33
    assert all(r.error and r.line > 0 and r.src.startswith("#") for r in raws)
    assert {2111, 3649, 3671, 3729, 3743, 6618, 6810} <= {r.vnum for r in raws}
    text = write_text(world.mob, canonical=True)
    assert all(r.src in text for r in raws)
