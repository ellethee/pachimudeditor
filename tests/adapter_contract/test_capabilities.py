"""Contratto sulle funzioni opzionali: se la capability e' dichiarata devono funzionare, altrimenti 409."""

from pathlib import Path

from pachimudeditor.common.adapters.base import WorldAdapter
from tests.adapter_contract.helpers import expect_error, new_zone


async def test_transfer_matches_capability(adapter: WorldAdapter, tmp_path: Path) -> None:
    """`export_zone_bundle`/`import_zone_dir` funzionano con `supports_transfer`, altrimenti 409 `world.capability_missing`."""
    zone = await new_zone(adapter)
    if not adapter.capabilities().supports_transfer:
        with expect_error(409, "world.capability_missing"):
            await adapter.export_zone_bundle(zone.id)
        with expect_error(409, "world.capability_missing"):
            await adapter.import_zone_dir(tmp_path, dry_run=True, confirm=False)
        return
    bundle = await adapter.export_zone_bundle(zone.id)
    assert bundle.zone_vnum == zone.vnum and bundle.files
    for name, text in bundle.files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    preview = await adapter.import_zone_dir(tmp_path, dry_run=True, confirm=False)
    assert preview.applied is False and preview.zone.action == "unchanged"
    with expect_error(422, "transfer.confirm_required"):
        await adapter.import_zone_dir(tmp_path, dry_run=False, confirm=False)
