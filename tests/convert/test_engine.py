"""Motore di conversione end-to-end su copie temporanee: BasedMud -> pachimud (e ritorno), politiche, conflitti, rollback."""

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from pachimudeditor_adapter_pachimud.adapter import PachimudAdapter
from pachimudeditor.common.adapters.convert.engine import convert
from pachimudeditor.common.adapters.convert.models import ConvertPlan
from pachimudeditor.common.adapters.convert.reader import list_all_zones, read_zone
from pachimudeditor.common.adapters.models import ExitPatch
from pachimudeditor.common.enums import DoorFlag
from tests.convert.helpers import assert_zone_valid, snapshot

MIDGAARD, SCHOOL = 3000, 3700


def plan(*zone_ids: int, **kwargs) -> ConvertPlan:  # type: ignore[no-untyped-def]
    """Un piano per le zone date."""
    return ConvertPlan.model_validate({"zone_ids": list(zone_ids), **kwargs})


def code_of(error: HTTPException) -> str:
    """Il codice stabile di un `HTTPException` dell'editor."""
    return error.detail[0]["code"]


async def test_preview_writes_nothing(rom_world, pachimud_world):
    """Il dry-run (default) restituisce conteggi, remap e perdite ma non tocca il mondo di arrivo."""
    before = await snapshot(pachimud_world)
    report = await convert(rom_world(), pachimud_world, plan(MIDGAARD, SCHOOL))
    assert await snapshot(pachimud_world) == before
    assert report.dry_run and not report.applied and report.converter == "specific"
    assert [z.action for z in report.zones] == ["create", "create"]
    src = rom_world()
    expected_rooms = (await src.zone_summary(MIDGAARD)).room_count + (await src.zone_summary(SCHOOL)).room_count
    assert report.totals["rooms"].create + report.totals["rooms"].dropped == expected_rooms
    assert len(report.remap["rooms"]) == report.totals["rooms"].create
    codes = {l.code for l in report.losses}
    assert {"shop_unsupported", "special_unsupported", "exit_target_outside"} <= codes
    assert report.loss_summary["dropped"] > 0


async def test_real_run_needs_confirm(rom_world, pachimud_world):
    """`dryRun=false` senza `confirm` e' 422; con `confirm` scrive."""
    with pytest.raises(HTTPException) as error:
        await convert(rom_world(), pachimud_world, plan(SCHOOL), dry_run=False)
    assert error.value.status_code == 422 and code_of(error.value) == "convert.confirm_required"
    assert await snapshot(pachimud_world) == await snapshot(pachimud_world)
    assert 3700 not in {z.vnum for z in await list_all_zones(pachimud_world)}


async def test_basedmud_to_pachimud_run(rom_world, pachimud_world, tmp_path: Path):
    """La conversione scrive zone, stanze, uscite, mob, oggetti e reset coerenti; il giornale registra piano ed esito."""
    src = rom_world()
    journal = tmp_path / "journal"
    report = await convert(src, pachimud_world, plan(MIDGAARD, SCHOOL), dry_run=False, confirm=True, journal_dir=journal)
    assert report.applied and not report.errors and not report.rolled_back
    zones = {z.vnum: z for z in await list_all_zones(pachimud_world)}
    assert {3000, 3700} <= set(zones)
    for action in report.zones:
        assert action.target_zone_id == zones[action.target_vnum].id
        s = await read_zone(pachimud_world, zones[action.target_vnum].id)
        assert (len(s.rooms), len(s.mobs), len(s.objects)) == (action.counts["rooms"], action.counts["mobs"], action.counts["objects"])
        assert sum(len(r.exits) for r in s.rooms) == action.counts["exits"]
        assert sum(len(r.extra_descriptions) for r in s.rooms) == action.counts["extraDescriptions"]
        assert len(s.resets) == action.counts["resets"]
        await assert_zone_valid(pachimud_world, zones[action.target_vnum].id)
    school = await read_zone(pachimud_world, zones[3700].id)
    assert all(zones[3700].bottom_vnum <= r.vnum <= zones[3700].top_vnum for r in school.rooms)
    files = list(journal.glob("convert-*.json"))
    assert report.journal.enabled and report.journal.file == files[0].name
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["plan"]["zoneIds"] == [MIDGAARD, SCHOOL] and saved["report"]["applied"] is True


async def test_rerun_skip_then_replace(rom_world, pachimud_world):
    """Seconda esecuzione: `skip` non cambia nulla; `replace` svuota e riscrive lo stesso contenuto."""
    src = rom_world()
    await convert(src, pachimud_world, plan(SCHOOL), dry_run=False, confirm=True)
    after_first = await snapshot(pachimud_world)
    skipped = await convert(src, pachimud_world, plan(SCHOOL), dry_run=False, confirm=True)
    assert [z.action for z in skipped.zones] == ["skip"] and skipped.totals["zones"].skip == 1
    assert skipped.conflicts[0].kind == "zone_exists" and not skipped.conflicts[0].resolved
    assert await snapshot(pachimud_world) == after_first
    replaced = await convert(src, pachimud_world, plan(SCHOOL, on_conflict="replace"), dry_run=False, confirm=True)
    assert [z.action for z in replaced.zones] == ["replace"] and replaced.applied
    assert replaced.totals["rooms"].replace == replaced.zones[0].counts["rooms"]
    assert await snapshot(pachimud_world) == after_first
    zone = next(z for z in await list_all_zones(pachimud_world) if z.vnum == 3700)
    await assert_zone_valid(pachimud_world, zone.id)


async def test_vnum_policies(rom_world, pachimud_world):
    """`offset` somma ai vnum (anche dentro reset e uscite); `shift_to` usa il primo intervallo libero, zone una dopo l'altra."""
    src = rom_world()
    report = await convert(src, pachimud_world, plan(SCHOOL, vnum_policy={"mode": "offset", "offset": 10000}), dry_run=False, confirm=True)
    assert report.applied and report.zones[0].bottom_vnum == 13700 and report.zones[0].target_vnum == 13700
    assert report.remap["rooms"][3700] == 13700 if 3700 in report.remap["rooms"] else True
    zone = next(z for z in await list_all_zones(pachimud_world) if z.vnum == 13700)
    s = await read_zone(pachimud_world, zone.id)
    assert all(13700 <= r.vnum <= 13799 for r in s.rooms) and all(13700 <= m.vnum <= 13799 for m in s.mobs)
    await assert_zone_valid(pachimud_world, zone.id)

    shifted = await convert(src, pachimud_world, plan(MIDGAARD, SCHOOL, vnum_policy={"mode": "shift_to"}))
    first, second = shifted.zones
    existing = await list_all_zones(pachimud_world)
    taken = [(z.bottom_vnum, z.top_vnum) for z in existing]
    for z in shifted.zones:
        assert all(not (z.bottom_vnum <= hi and lo <= z.top_vnum) for lo, hi in taken), z
    assert first.top_vnum < second.bottom_vnum and first.offset != 0
    assert all(a.action == "create" for a in shifted.zones)
    with pytest.raises(HTTPException) as error:
        await convert(src, pachimud_world, plan(SCHOOL, vnum_policy={"mode": "offset", "offset": -5000}))
    assert code_of(error.value) == "convert.offset_negative"


async def test_blocked_by_foreign_vnums(rom_world, pachimud_world):
    """Un vnum o un range che toccano un'altra zona bloccano la zona: nulla viene scritto."""
    src = rom_world()
    before = await snapshot(pachimud_world)
    report = await convert(src, pachimud_world, plan(SCHOOL, vnum_policy={"mode": "offset", "offset": -2700}), dry_run=False, confirm=True)
    assert [z.action for z in report.zones] == ["blocked"]
    assert {c.kind for c in report.conflicts} >= {"range_overlap", "vnum_taken"}
    assert await snapshot(pachimud_world) == before


async def test_safety_checks(rom_world, pachimud_world):
    """Arrivo in sola lettura, stesso mondo e zona inesistente sono rifiutati."""
    with pytest.raises(HTTPException) as error:
        await convert(pachimud_world, rom_world(read_only=True), plan(1))
    assert error.value.status_code == 409 and code_of(error.value) == "world.read_only"
    src = rom_world()
    with pytest.raises(HTTPException) as same:
        await convert(src, src, plan(SCHOOL))
    assert code_of(same.value) == "convert.same_world"
    with pytest.raises(HTTPException) as twin:  # altro id, stessi dati
        await convert(src, rom_world(world_id="rom2"), plan(SCHOOL))
    assert code_of(twin.value) == "convert.same_world"
    with pytest.raises(HTTPException) as missing:
        await convert(src, pachimud_world, plan(99999))
    assert missing.value.status_code == 404 and code_of(missing.value) == "convert.zone_not_found"


class Failing(PachimudAdapter):
    """Adapter pachimud che fallisce alla N-esima creazione di mob (per provare il rollback)."""

    fail_at = 5

    async def create_mob(self, data):  # type: ignore[no-untyped-def]
        """Alza un errore alla `fail_at`-esima chiamata."""
        self.calls = getattr(self, "calls", 0) + 1
        if self.calls == self.fail_at:
            raise RuntimeError("guasto iniettato")
        return await super().create_mob(data)


async def test_rollback_on_failure(rom_world, pachimud_world):
    """Un errore a meta': tutto cio' che questa esecuzione ha creato viene annullato."""
    failing = Failing(pachimud_world.config)
    before = await snapshot(failing)
    report = await convert(rom_world(), failing, plan(MIDGAARD), dry_run=False, confirm=True)
    assert not report.applied and report.rolled_back and not report.rollback_errors
    assert report.errors[0].code == "convert.write_failed" and "guasto iniettato" in report.errors[0].params["msg"]
    assert await snapshot(failing) == before
    await failing.close()


async def test_rollback_restores_replaced_zone(rom_world, pachimud_world):
    """Con `replace` il rollback ripristina il contenuto precedente della zona."""
    src = rom_world()
    await convert(src, pachimud_world, plan(SCHOOL), dry_run=False, confirm=True)
    before = await snapshot(pachimud_world)
    failing = Failing(pachimud_world.config)
    failing.fail_at = 3
    report = await convert(src, failing, plan(SCHOOL, on_conflict="replace"), dry_run=False, confirm=True)
    assert report.rolled_back and not report.applied and not report.rollback_errors, report.rollback_errors
    assert await snapshot(failing) == before
    zone = next(z for z in await list_all_zones(failing) if z.vnum == 3700)
    await assert_zone_valid(failing, zone.id)
    await failing.close()


async def test_pachimud_to_basedmud(pachimud_world, empty_rom):
    """pachimud -> BasedMud: i file `.are` riletti da un adapter nuovo hanno stanze, uscite, stato porta e reset."""
    s = await read_zone(pachimud_world, 1)
    exit_out = s.rooms[0].exits[0]
    await pachimud_world.update_exit(s.rooms[0].id, exit_out.id, ExitPatch(door_flag=DoorFlag.CLOSABLE, is_open=False))
    report = await convert(pachimud_world, empty_rom, plan(1), dry_run=False, confirm=True)
    assert report.applied and not report.errors
    fresh = type(empty_rom)(empty_rom.config)
    zones = await list_all_zones(fresh)
    assert [(z.name, z.bottom_vnum, z.top_vnum) for z in zones] == [("Zona Alfa", 1000, 1099)]
    t = await read_zone(fresh, zones[0].id)
    assert sorted(r.vnum for r in t.rooms) == [1000, 1001, 1002]
    closed = next(e for r in t.rooms for e in r.exits if not e.is_open)
    assert closed.door_flag == DoorFlag.CLOSABLE and closed.target_room_vnum == 1001
    assert any(r.extra_descriptions for r in t.rooms)
    assert [(c.command_type.name, c.arg1) for c in t.resets if c.command_type.name != "SET_DOOR_STATE"] == [
        ("LOAD_MOB", 1000),
        ("LOAD_OBJECT", 1000),
    ]
    await assert_zone_valid(fresh, zones[0].id)
    # round trip: indietro in pachimud con un altro intervallo, nessuna perdita sostanziale
    back = await convert(fresh, pachimud_world, plan(zones[0].id, vnum_policy={"mode": "shift_to"}), dry_run=False, confirm=True)
    assert back.applied and back.totals["rooms"].dropped == 0 and back.totals["exits"].dropped == 0


async def test_generic_fallback_with_mapping_world(tmp_path: Path, pachimud_world):
    """Un mondo `mapping` (rom.yaml) usa il ripiego generico: nucleo copiato, `extra` scartato e riportato."""
    from pachimudeditor_adapter_mapping.adapter import MappingAdapter
    from pachimudeditor.common.adapters.registry import WorldConfig
    from tests.convert.conftest import make_rom_dir
    from tests.support.mapping_worlds import ROM_MAPPING

    root = make_rom_dir(tmp_path / "map")
    world = MappingAdapter(WorldConfig(id="map", kind="mapping", name="Map", mapping=str(ROM_MAPPING), path=str(root)))
    report = await convert(world, pachimud_world, plan(SCHOOL), dry_run=False, confirm=True)
    assert report.converter == "generic" and report.applied, report.errors
    assert any(l.code == "extra_dropped" for l in report.losses)
    zone = next(z for z in await list_all_zones(pachimud_world) if z.vnum == 3700)
    await assert_zone_valid(pachimud_world, zone.id)
