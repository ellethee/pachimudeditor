"""L'esempio guidato di `docs/adapters/mapping-guide.md` (MiniMUD) funziona davvero: se questo test passa, la guida e' vera."""

import shutil
from pathlib import Path

import pytest
from pachimudeditor_adapter_mapping.adapter import MappingAdapter
from fastapi import HTTPException
from pachimudeditor.common.enums import ZoneCommandType
from pachimudeditor.common.enums import Direction, SectorType

from pachimudeditor.common.adapters.models import ExitIn, MobPatch, ResetCommandIn, ResetScriptIn, RoomIn, RoomPatch, ZoneIn
from pachimudeditor.common.adapters.registry import WorldConfig
from tests.support.mapping_worlds import EXAMPLES

MINIMUD = EXAMPLES / "minimud"


@pytest.fixture
def world(tmp_path: Path) -> Path:
    """Copia temporanea del mondo di esempio."""
    shutil.copytree(MINIMUD / "world", tmp_path / "world")
    return tmp_path / "world"


def adapter(root: Path) -> MappingAdapter:
    """Adapter con `minimud.yaml` su `root`."""
    return MappingAdapter(WorldConfig(id="mini", kind="mapping", mapping=str(MINIMUD / "minimud.yaml"), path=str(root)))


async def test_read(world: Path) -> None:
    """Lettura: zona con range e livelli, stanza con flag a nomi, uscita risolta, mob con dadi, reset."""
    a = adapter(world)
    zone = await a.get_zone(100)
    assert (zone.name, zone.bottom_vnum, zone.top_vnum, zone.min_level, zone.max_level) == ("Foresta Oscura", 100, 199, 5, 20)
    room = await a.get_room(100)
    assert room.flags == ["dark", "outdoor"] and room.sector_type is SectorType.FOREST
    assert (room.exits[0].direction, room.exits[0].target_room_name) == (Direction.NORTH, "Radura")
    mob = await a.get_mob(100)
    assert (mob.level, mob.hp_dice_count, mob.hp_die_size, mob.hp_bonus, mob.damage_dice_count) == (5, 1, 8, 2, 2)
    assert [(c.command_type, c.arg1, c.arg3) for c in await a.list_reset_commands(100)] == [
        (ZoneCommandType.LOAD_MOB, 100, 101), (ZoneCommandType.LOAD_OBJECT, 100, 100),
    ]  # fmt: skip
    caps = a.capabilities()
    assert caps.supports_reset_scripts and not caps.supports_extra_descriptions


async def test_write_keeps_untouched_bytes(world: Path) -> None:
    """Modifica di un mob e di una stanza: cambiano solo i loro blocchi, il resto del file e' identico."""
    a = adapter(world)
    before = (world / "foresta.mini").read_text()
    await a.update_mob(100, MobPatch(level=9, short_description="un orco ferito"))
    await a.update_room(101, RoomPatch(name="Radura lunare", flags=["safe", "outdoor"]))
    after = (world / "foresta.mini").read_text()
    assert "un orco ferito~" in after and "5 1d8+2 2d4+0 1" not in after and "9 1d8+2 2d4+0 1" in after
    assert "Radura lunare~" in after and "BD 2" in after  # flag riscritti a lettere
    assert (
        after.replace("un orco ferito", "un orco").replace("9 1d8+2", "5 1d8+2").replace("Radura lunare", "Radura").replace("BD 2", "B 2")
        == before
    )


async def test_create_content_and_zone(world: Path) -> None:
    """Nuova stanza con uscita, nuovo script, nuova zona (un nuovo file `.mini`)."""
    a = adapter(world)
    room = await a.create_room(RoomIn(vnum=102, zone_id=100, name="Grotta", flags=["dark"], sector_type=SectorType.INSIDE))
    await a.create_exit(102, ExitIn(direction=Direction.UP, target_room_id=101))
    assert (await a.get_room(102)).exits[0].target_room_id == 101 and room.flags == ["dark"]
    await a.replace_reset_commands(
        100, ResetScriptIn(commands=[ResetCommandIn(command_type=ZoneCommandType.LOAD_MOB, arg1=100, arg2=1, arg3=102)])
    )
    assert "@resets\nM 100 102\nS\n" in (world / "foresta.mini").read_text()
    free = await a.next_zone_vnum(99)
    zone = await a.create_zone(ZoneIn(vnum=free.vnum, name="Montagna", bottom_vnum=free.bottom_vnum, top_vnum=free.top_vnum))
    assert (world / "montagna.mini").read_text().startswith("@zone\nMontagna~\n200 299 1 1\n")
    assert zone.id == 200 and (await a.get_zone(200)).extra["file"] == "montagna.mini"


async def test_missing_features_are_reported(world: Path) -> None:
    """Le extra description non sono nel modello: capability spenta e 409 se qualcuno le chiede."""
    from pachimudeditor.common.adapters.models import ExtraDescriptionIn

    with pytest.raises(HTTPException) as error:
        await adapter(world).create_extra_description(100, ExtraDescriptionIn(keywords="k", text="t"))
    assert error.value.status_code == 409 and error.value.detail[0]["code"] == "world.capability_missing"
