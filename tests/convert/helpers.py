"""Utility dei test di conversione: istantanea di un mondo e verifiche di integrita'."""

from typing import Any

from pachimudeditor.common.adapters.base import WorldAdapter
from pachimudeditor.common.adapters.convert.reader import list_all_zones, read_zone
from pachimudeditor.common.adapters.models import ResetCommandDraft, ResetDraftScriptIn


async def snapshot(adapter: WorldAdapter) -> dict[int, tuple[Any, ...]]:
    """`{vnum zona: (nome, range, conteggi, vnum di stanze/mob/oggetti, script)}` per ogni zona del mondo."""
    out: dict[int, tuple[Any, ...]] = {}
    for zone in await list_all_zones(adapter):
        s = await read_zone(adapter, zone.id)
        out[zone.vnum] = (
            zone.name,
            zone.bottom_vnum,
            zone.top_vnum,
            tuple(sorted(r.vnum for r in s.rooms)),
            tuple(sorted(m.vnum for m in s.mobs)),
            tuple(sorted(o.vnum for o in s.objects)),
            tuple((c.command_type, c.arg1, c.arg2, c.arg3, c.arg4, c.arg_str) for c in s.resets),
        )
    return out


async def assert_zone_valid(adapter: WorldAdapter, zone_id: int) -> None:
    """Le uscite puntano a stanze esistenti e lo script di reset non ha errori di riferimento."""
    s = await read_zone(adapter, zone_id)
    for room in s.rooms:
        for ex in room.exits:
            if ex.target_room_vnum is not None:
                assert ex.target_room_id is not None, (room.vnum, ex.direction)
    drafts = [ResetCommandDraft.model_validate(c.model_dump(by_alias=False, exclude={"id", "zone_id", "order_index"})) for c in s.resets]
    result = await adapter.validate_reset_commands(zone_id, ResetDraftScriptIn(commands=drafts))
    assert result.ok, [i.message for i in result.issues if i.severity == "error"][:5]
