"""Metadati dell'adapter generico: `describe()`, `enums()`, razze/classi, capability, configurazione errata."""

from pathlib import Path

import pytest
from pachimudeditor_adapter_mapping.adapter import MappingAdapter
from pachimudeditor_adapter_mapping.schema import MappingConfigError

from pachimudeditor.common.adapters.registry import WorldConfig
from tests.support.mapping_worlds import DIKU_MAPPING, ROM_MAPPING


def make(mapping: Path, root: Path, **kwargs: object) -> MappingAdapter:
    """Adapter con la mappatura `mapping` sulla cartella `root`."""
    return MappingAdapter(WorldConfig(id="m", kind="mapping", mapping=str(mapping), path=str(root), **kwargs))  # type: ignore[arg-type]


async def test_rom_enums_and_describe(tmp_path: Path) -> None:
    """Le tabelle con `expose` diventano enum; i campi flag del DTO puntano alla tabella giusta."""
    (tmp_path / "area.lst").write_text("$\n")
    a = make(ROM_MAPPING, tmp_path)
    enums = await a.enums()
    assert {"sectorType", "direction", "doorFlag", "zoneResetMode", "sex", "objectType", "zoneCommandType"} <= set(enums)
    assert {"romRoomFlags", "romMobFlags", "romSectorType", "romItemType", "romWearLoc"} <= set(enums)
    assert any(o.label == "dark" and o.value == 1 for o in enums["romRoomFlags"])
    assert all(not o.label.startswith("unused") for o in enums["romMobFlags"])
    info = a.describe()
    by_type = {r.type: {f.name: f for f in r.fields} for r in info.resources}
    assert by_type["room"]["flags"].enum == "romRoomFlags" and by_type["mob"]["flags"].enum == "romMobFlags"
    assert by_type["object"]["extraFlags"].enum == "romExtraFlags" and by_type["object"]["wearFlags"].enum == "romWearFlags"
    assert by_type["mob"]["extra"].type == "dict" and by_type["zone"]["id"].read_only
    caps = info.capabilities
    assert caps.supports_reset_scripts and caps.supports_extra_descriptions and not caps.supports_players and not caps.read_only
    assert await a.races() == [] and await a.classes() == []


async def test_diku_races_come_from_a_table(tmp_path: Path) -> None:
    """`meta.races` puo' essere il nome di una tabella: gli id sono i nomi usati da `raceId` dei mob."""
    a = make(DIKU_MAPPING, tmp_path)
    races = await a.races()
    assert races[1].id == "human" and len(races) == 85 and await a.classes() == []


def test_configuration_errors(tmp_path: Path) -> None:
    """Mappatura o cartella mancanti: `ValueError` chiaro alla costruzione (non al primo uso)."""
    with pytest.raises(ValueError, match="mapping"):
        MappingAdapter(WorldConfig(id="m", kind="mapping", path=str(tmp_path)))
    with pytest.raises(ValueError, match="path"):
        MappingAdapter(WorldConfig(id="m", kind="mapping", mapping=str(ROM_MAPPING)))
    with pytest.raises(ValueError, match="non trovata"):
        make(ROM_MAPPING, tmp_path / "manca")
    with pytest.raises(MappingConfigError):
        make(tmp_path / "manca.yaml", tmp_path)


async def test_describe_extra_matches_emitted(rom_dir: Path, dikumod_dir: Path) -> None:
    """Mappatura ROM e Diku: le chiavi di `extra` dichiarate (campi non mappati) coincidono con quelle emesse."""
    from tests.support.describe_check import assert_describe_matches, emitted_extra_keys

    for mapping, root in ((ROM_MAPPING, rom_dir), (DIKU_MAPPING, dikumod_dir)):
        a = make(mapping, root)
        info = a.describe()
        assert_describe_matches(info, await emitted_extra_keys(a, rooms=200), optional=True)
        enums = await a.enums()
        for r in info.resources:
            for f in (*r.extra_fields, *r.fields):
                assert f.enum is None or f.enum in enums, (r.type, f.name, f.enum)
    by = {r.type: {f.name: f for f in r.fields} for r in make(ROM_MAPPING, rom_dir).describe().resources}
    assert by["zone"]["lifespanMinutes"].unsupported
