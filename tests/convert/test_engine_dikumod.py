"""Conversioni da/verso Diku Modificato: mondo sintetico minuscolo (veloce) e una zona dei dati reali di dikumod2 (sola lettura)."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from pachimudeditor_adapter_dikumod.adapter import DikumodAdapter
from pachimudeditor.common.adapters.convert.engine import convert
from pachimudeditor.common.adapters.convert.models import ConvertPlan
from pachimudeditor.common.adapters.convert.reader import list_all_zones, read_zone
from pachimudeditor.common.adapters.models import RoomPatch
from pachimudeditor.common.adapters.registry import WorldConfig
from tests.convert.helpers import SCHOOL, SCHOOL_NAME, assert_zone_valid, snapshot
from tests.dikumod.synthetic import write_world
from tests.dikumod_lib.conftest import PREFIX, lib_of


@pytest.fixture
def dikumod_small(tmp_path: Path) -> DikumodAdapter:
    """Mondo Diku Modificato sintetico (zona LIMBO: stanze 1-2 (la 0 e' della zona 0), mob 1, oggetto 1, reset M/E/O), scrivibile."""
    lib = write_world(tmp_path / "small" / "lib")
    return DikumodAdapter(WorldConfig(id="dikumod-small", kind="dikumod", name="Small", path=str(lib), read_only=False))


def plan(*ids: int, **kw) -> ConvertPlan:  # type: ignore[no-untyped-def]
    """Un piano per le zone date."""
    return ConvertPlan.model_validate({"zone_ids": list(ids), **kw})


async def test_dikumod_to_pachimud(dikumod_small, pachimud_world):
    """Diku Modificato -> pachimud: reset tradotti (`max` 0 -> 99, slot `finger`/`wield`), uscite e script validi."""
    zone = next(z for z in await list_all_zones(dikumod_small) if z.name == "LIMBO")
    report = await convert(dikumod_small, pachimud_world, plan(zone.id), dry_run=False, confirm=True)
    assert report.applied and not report.errors, report.errors
    target = next(z for z in await list_all_zones(pachimud_world) if z.name == "LIMBO")
    s = await read_zone(pachimud_world, target.id)
    assert sorted(r.vnum for r in s.rooms) == [1, 2]  # la stanza 0 e' della zona 0
    by_type = {c.command_type.name: c for c in s.resets}
    assert by_type["EQUIP_OBJECT"].arg_str == "wield" and by_type["EQUIP_OBJECT"].if_flag is True
    assert by_type["LOAD_OBJECT"].arg3 == 2
    await assert_zone_valid(pachimud_world, target.id)


async def test_dikumod_to_basedmud_and_back(dikumod_small, empty_rom, tmp_path):
    """Diku Modificato -> BasedMud (via pivot) e ritorno verso un secondo mondo Diku Modificato: i riferimenti restano validi."""
    zone = next(z for z in await list_all_zones(dikumod_small) if z.name == "LIMBO")
    report = await convert(dikumod_small, empty_rom, plan(zone.id), dry_run=False, confirm=True)
    assert report.applied and not report.errors, report.errors
    rom_zone = (await list_all_zones(empty_rom))[0]
    await assert_zone_valid(empty_rom, rom_zone.id)
    lib = write_world(tmp_path / "other" / "lib")
    other = DikumodAdapter(WorldConfig(id="dikumod-other", kind="dikumod", name="Other", path=str(lib), read_only=False))
    back = await convert(empty_rom, other, plan(rom_zone.id, vnum_policy={"mode": "shift_to"}), dry_run=False, confirm=True)
    assert back.applied and not back.errors, back.errors
    assert len(await list_all_zones(other)) == 3


async def test_basedmud_and_pachimud_to_dikumod(rom_world, pachimud_world, dikumod_small):
    """BasedMud -> Diku Modificato e pachimud -> Diku Modificato in coda al mondo Diku Modificato; un guasto non lascia nulla."""
    before = await snapshot(dikumod_small)
    report = await convert(rom_world(), dikumod_small, plan(SCHOOL, vnum_policy={"mode": "shift_to"}), dry_run=False, confirm=True)
    assert report.applied and not report.errors, report.errors
    created = next(z for z in await list_all_zones(dikumod_small) if z.name == SCHOOL_NAME)
    await assert_zone_valid(dikumod_small, created.id)
    after_first = await snapshot(dikumod_small)
    assert len(after_first) == len(before) + 1
    again = await convert(pachimud_world, dikumod_small, plan(1, vnum_policy={"mode": "shift_to"}), dry_run=False, confirm=True)
    assert again.applied and not again.errors, again.errors
    alfa = next(z for z in await list_all_zones(dikumod_small) if z.name == "Zona Alfa")
    await assert_zone_valid(dikumod_small, alfa.id)


async def test_real_dikumod_zone_to_pachimud(pachimud_world):
    """Una zona dei dati reali di dikumod2 (aperti in sola lettura) finisce in pachimud con perdite riportate."""
    lib = lib_of("dikumod2")
    if not (lib / f"{PREFIX}.wld").is_file():
        pytest.skip("dati dikumod2 non trovati")
    source = DikumodAdapter(
        WorldConfig(
            id="dikumod2-real", kind="dikumod", name="DIKUMOD2", path=str(lib), params={"variant": "dikumod2", "data_prefix": PREFIX}
        )
    )
    zone = next(z for z in await list_all_zones(source) if z.name == "The colossal tree")
    report = await convert(source, pachimud_world, plan(zone.id), dry_run=False, confirm=True)
    assert report.applied and not report.errors, report.errors
    assert {"mob_flagset_dropped", "flags_dropped"} & {l.code for l in report.losses}
    target = next(z for z in await list_all_zones(pachimud_world) if z.name == "The colossal tree")
    await assert_zone_valid(pachimud_world, target.id)


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize(("target", "code"), [("dikumod_small", "dikumod.unencodable_text"), ("empty_rom", "basedmud.unencodable_text")])
async def test_emoji_not_encodable_is_422_in_preview_and_run(request, pachimud_world, target, code, dry_run):
    """Testo non codificabile nell'arrivo: 422 gia' in anteprima (e nel run), senza scrivere nulla.

    Verso BasedMud una zona nuova e' utf-8 (emoji ammesse): qui si sostituisce una zona latin-1 esistente.
    """
    room = (await read_zone(pachimud_world, 1)).rooms[0]
    await pachimud_world.update_room(room.id, RoomPatch(name="Piazza \U0001f600"))
    world = request.getfixturevalue(target)
    if target == "empty_rom":  # arrivo: area latin-1 gia' presente con lo stesso vnum di zona
        src = await convert(pachimud_world, world, plan(1), dry_run=False, confirm=True)
        assert src.applied
        entry = world.store.zone_by_id((await list_all_zones(world))[0].id)
        entry.area.encoding = "latin-1"
        kw = {"on_conflict": "replace"}
    else:
        kw = {"vnum_policy": {"mode": "shift_to"}}
    before = await snapshot(world)
    with pytest.raises(HTTPException) as err:
        await convert(pachimud_world, world, plan(1, **kw), dry_run=dry_run, confirm=True)
    assert err.value.status_code == 422 and err.value.detail[0]["code"] == code
    assert await snapshot(world) == before
