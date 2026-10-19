"""`MappingAdapter` (rom.yaml) sul mondo ROM sintetico: una scrittura fallita non lascia la cache sporca."""

from pathlib import Path

from pachimudeditor_adapter_mapping.adapter import MappingAdapter

from pachimudeditor.common.adapters.models import MobPatch, RoomPatch
from pachimudeditor.common.adapters.registry import WorldConfig
from tests.adapter_contract.helpers import expect_error
from tests.support.mapping_worlds import ROM_MAPPING
from tests.support.synthetic_worlds import write_rom_area


def _adapter(root: Path) -> MappingAdapter:
    """Adapter scrivibile con `rom.yaml` sulla cartella `root`."""
    return MappingAdapter(WorldConfig(id="syn", kind="mapping", mapping=str(ROM_MAPPING), path=str(root)))


async def test_failed_update_leaves_cache_and_disk_clean(tmp_path: Path) -> None:
    """422 su `extra` sconosciuto: DTO invariato, nessun byte scritto e un adapter nuovo non vede il valore scartato."""
    root = write_rom_area(tmp_path / "area")
    adapter = _adapter(root)
    room, mob = await adapter.get_room(5000), await adapter.get_mob(5000)
    raw = (root / "prato.are").read_bytes()
    with expect_error(422, "mapping.extra_unknown"):
        await adapter.update_room(5000, RoomPatch(name="Mutata", heal_rate=77, extra={"boh": 1}))
    with expect_error(422, "mapping.extra_unknown"):
        await adapter.update_mob(5000, MobPatch(level=3, short_description="x", extra={"boh": 1}))
    assert (await adapter.get_room(5000), await adapter.get_mob(5000)) == (room, mob)
    assert (root / "prato.are").read_bytes() == raw
    await adapter.update_mob(5001, MobPatch(level=9))
    assert "Mutata" not in (root / "prato.are").read_text(encoding="latin-1")
    assert (await _adapter(root).get_room(5000)).name == room.name
