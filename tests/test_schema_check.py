"""Compatibilita' con lo schema del gioco: revisioni note/ignote e degrado quando mancano colonne o tabelle.

I database di prova sono creati con i modelli copiati del gioco e poi "invecchiati" o alterati con SQL.
"""

import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException


from pachimudeditor_adapter_pachimud.adapter import PachimudAdapter  # noqa: E402
from pachimudeditor_adapter_pachimud.schema import HEAD, REVISIONS  # noqa: E402
from pachimudeditor.common.adapters.models import (  # noqa: E402
    ExtraDescriptionIn,
    MobIn,
    ResetCommandIn,
    ResetScriptIn,
    RoomIn,
    RoomPageParams,
    ZonePageParams,
)
from pachimudeditor.common.adapters.registry import WorldConfig, WorldRegistry, get_registry, set_registry  # noqa: E402
from tests.helpers import data, error_code  # noqa: E402
from tests.support import stack  # noqa: E402

OLD_COLUMNS = [
    "ALTER TABLE mob_prototype DROP COLUMN race_id",
    "ALTER TABLE mob_prototype DROP COLUMN class_id",
    "ALTER TABLE zone_reset_command DROP COLUMN arg_str",
    "ALTER TABLE room DROP COLUMN heal_rate",
    "ALTER TABLE room DROP COLUMN mana_rate",
    "ALTER TABLE room DROP COLUMN clan_id",
    "ALTER TABLE room DROP COLUMN owner",
    "ALTER TABLE zone DROP COLUMN min_level",
    "ALTER TABLE zone DROP COLUMN max_level",
]
"""Come uno schema alla revisione iniziale `64f2026e1334`."""


def world(tmp_path: Path, *sql: str, revision: str | None = HEAD) -> PachimudAdapter:
    """Adapter su un DB creato dal gioco e poi modificato con `sql`; `revision` e' scritta in `alembic_version`."""
    stack.seed_game_db(tmp_path)
    connection = sqlite3.connect(tmp_path / "game.db")
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute("DROP TABLE IF EXISTS alembic_version")
    if revision is not None:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        connection.execute("INSERT INTO alembic_version VALUES (?)", (revision,))
    for statement in sql:
        connection.execute(statement)
    connection.commit()
    connection.close()
    return PachimudAdapter(
        WorldConfig(
            id="w",
            kind="pachimud",
            params={"database_url": f"sqlite+aiosqlite:///{tmp_path / 'game.db'}", "definitions_path": str(tmp_path / "definitions")},
        )
    )


async def test_current_revision_is_ok(tmp_path: Path) -> None:
    """Revisione piu' recente nota e nessuna colonna assente: stato `ok`, nessun avviso, tutte le capability."""
    adapter = world(tmp_path)
    report = adapter.schema_report()
    assert report is not None and report.status == "ok" and report.revision == HEAD == REVISIONS[-1]
    assert report.warnings == [] and report.unsupported == {}
    caps = adapter.capabilities()
    assert caps.supports_players and caps.supports_instances and caps.supports_transfer and caps.supports_extra_descriptions
    await adapter.close()


async def test_old_schema_degrades_gracefully(tmp_path: Path) -> None:
    """Schema iniziale: stato `behind`, campi mancanti `unsupported`, lettura con neutri, scrittura solo di neutri."""
    adapter = world(tmp_path, *OLD_COLUMNS, revision=REVISIONS[0])
    report = adapter.schema_report()
    assert report is not None and report.status == "behind" and report.revision == REVISIONS[0]
    assert report.unsupported["mob_prototype"] == ["class_id", "race_id"] and report.warnings == []
    info = adapter.describe()
    mob = {f.name: f for f in next(r for r in info.resources if r.type == "mob").fields}
    assert mob["raceId"].unsupported and mob["classId"].unsupported and not mob["keywords"].unsupported
    zone = {f.name: f for f in next(r for r in info.resources if r.type == "zone").fields}
    assert zone["minLevel"].unsupported and zone["maxLevel"].read_only
    # lettura: valori neutri
    zones = await adapter.list_zones(ZonePageParams())
    assert zones.total == 2 and zones.items[0].min_level == 1
    room = await adapter.get_room((await adapter.list_rooms(RoomPageParams())).items[0].id)
    assert room.heal_rate == 100 and room.clan_id is None
    # scrittura: il neutro passa, il resto e' 422
    created = await adapter.create_mob(MobIn(vnum=1500, zone_id=zones.items[0].id, keywords="k", short_description="s"))
    assert created.race_id is None
    with pytest.raises(HTTPException) as error:
        await adapter.create_mob(MobIn(vnum=1501, zone_id=zones.items[0].id, keywords="k", short_description="s", race_id="human"))
    assert error.value.status_code == 422 and error.value.detail[0]["code"] == "world.field_unsupported"
    with pytest.raises(HTTPException):
        await adapter.create_room(RoomIn(vnum=1600, zone_id=zones.items[0].id, name="x", heal_rate=200))
    await adapter.create_room(RoomIn(vnum=1600, zone_id=zones.items[0].id, name="x"))
    scripts = await adapter.replace_reset_commands(
        zones.items[0].id, ResetScriptIn(commands=[ResetCommandIn(command_type=1, arg1=1000, arg2=1, arg3=1000)])
    )
    assert scripts[0].arg_str is None
    with pytest.raises(HTTPException):
        await adapter.replace_reset_commands(
            zones.items[0].id, ResetScriptIn(commands=[ResetCommandIn(command_type=3, arg1=1000, arg2=1, arg_str="wield")])
        )
    # export/import YAML continuano a funzionare
    bundle = await adapter.export_zone_bundle(zones.items[0].id)
    assert "race_id" not in bundle.files["mobs.yaml"] and bundle.warnings == []
    await adapter.close()


async def test_unknown_revision_warns_but_works(tmp_path: Path) -> None:
    """Revisione ignota (gioco piu' recente): avviso, stato `unknown`, il mondo funziona."""
    adapter = world(tmp_path, revision="ffffffffffff")
    report = adapter.schema_report()
    assert report is not None and report.status == "unknown"
    assert [i.code for i in report.warnings] == ["unknown_revision"]
    assert (await adapter.list_zones(ZonePageParams())).total == 2
    await adapter.close()


async def test_unversioned_database(tmp_path: Path) -> None:
    """Senza `alembic_version`: stato `unversioned` con avviso."""
    adapter = world(tmp_path, revision=None)
    report = adapter.schema_report()
    assert report is not None and report.status == "unversioned" and report.revision is None
    assert [i.code for i in report.warnings] == ["unversioned"]
    await adapter.close()


async def test_unknown_required_column_is_a_warning(tmp_path: Path) -> None:
    """Una colonna NOT NULL nuova e senza default: avviso (gli inserimenti potrebbero fallire), nient'altro."""
    adapter = world(
        tmp_path, "ALTER TABLE zone ADD COLUMN futuro INTEGER NOT NULL DEFAULT 0", "ALTER TABLE room ADD COLUMN extra_nuova VARCHAR"
    )
    report = adapter.schema_report()
    assert report is not None and report.status == "ok"
    assert report.warnings == []  # ha un default: nessun avviso
    assert any(i.code == "unknown_column" for i in report.issues)
    await adapter.close()


async def test_optional_tables_switch_off_capabilities(tmp_path: Path) -> None:
    """Senza giocatori/istanze/extra description le capability collegate sono false e il resto funziona."""
    adapter = world(
        tmp_path,
        "DROP TABLE object_instance",
        "DROP TABLE mob_instance",
        "DROP TABLE player_character",
        "DROP TABLE account",
        "DROP TABLE room_extra_description",
    )
    caps = adapter.capabilities()
    assert not caps.supports_players and not caps.supports_instances and not caps.supports_extra_descriptions
    assert caps.supports_transfer
    report = adapter.schema_report()
    assert report is not None and report.status == "ok" and len(report.missing_tables) == 5
    zones = await adapter.list_zones(ZonePageParams())
    room_id = (await adapter.create_room(RoomIn(vnum=1700, zone_id=zones.items[0].id, name="solo"))).id
    await adapter.delete_room(room_id)
    bundle = await adapter.export_zone_bundle(zones.items[0].id)
    assert "extra_descriptions" not in bundle.files["rooms.yaml"]
    with pytest.raises(HTTPException) as error:
        await adapter.create_extra_description(room_id, ExtraDescriptionIn(keywords="a", text="b"))
    assert error.value.status_code in (404, 409)
    await adapter.close()


async def test_missing_core_table_is_incompatible_503(tmp_path: Path) -> None:
    """Manca una tabella obbligatoria: 503 `world.unavailable` per quel mondo (gli altri funzionano), mai un 500."""
    adapter = world(tmp_path, "DROP TABLE exit")
    assert adapter.schema_report() is not None and adapter.schema_report().status == "incompatible"  # type: ignore[union-attr]
    assert adapter.unavailable_reason() and "exit" in adapter.unavailable_reason()  # type: ignore[operator]
    with pytest.raises(HTTPException) as error:
        await adapter.list_zones(ZonePageParams())
    assert error.value.status_code == 503 and error.value.detail[0]["code"] == "world.unavailable"
    assert adapter.describe().kind == "pachimud" and adapter.capabilities().supports_players is False
    await adapter.close()


async def test_missing_database_file_is_not_created(tmp_path: Path) -> None:
    """File SQLite inesistente: 503 e NESSUN DB vuoto creato (come faceva aiosqlite)."""
    missing = tmp_path / "non-esiste.db"
    adapter = PachimudAdapter(WorldConfig(id="w", kind="pachimud", params={"database_url": f"sqlite+aiosqlite:///{missing}"}))
    with pytest.raises(HTTPException) as error:
        await adapter.list_zones(ZonePageParams())
    assert error.value.status_code == 503
    assert not missing.exists() and adapter.schema_report() is None
    await adapter.close()


async def test_http_503_on_broken_world_keeps_others_working(client: httpx.AsyncClient, tmp_path: Path) -> None:
    """Due mondi pachimud: quello rotto risponde 503 con codice stabile, il default continua a funzionare."""
    broken = world(tmp_path, "DROP TABLE zone_reset_command")
    await broken.close()
    previous = get_registry()
    registry = WorldRegistry(
        [
            WorldConfig(id="pachimud", kind="pachimud", params=stack.current_params()),
            WorldConfig(id="rotto", kind="pachimud", params=broken.config.params),
        ],
        "pachimud",
    )
    set_registry(registry)
    try:
        assert error_code(await client.get("/api/zones", headers={"X-World": "rotto"}), 503) == "world.unavailable"
        assert error_code(await client.get("/api/world/overview", headers={"X-World": "rotto"}), 409) == "world.capability_missing"
        assert data(await client.get("/api/zones"))["total"] == 2
        worlds = {w["id"]: w for w in data(await client.get("/api/worlds"))}
        assert set(worlds) == {"pachimud", "rotto"} and worlds["rotto"]["capabilities"]["supportsWorldOverview"] is False
    finally:
        await registry.aclose_all()
        set_registry(previous)


async def test_schema_is_read_once_and_refreshable(tmp_path: Path) -> None:
    """Lo schema si legge una volta; `refresh=True` lo rilegge (dopo una migration del gioco)."""
    adapter = world(tmp_path, *OLD_COLUMNS, revision=REVISIONS[0])
    first = adapter.connection.schema()
    assert adapter.connection.schema() is first
    connection = sqlite3.connect(tmp_path / "game.db")
    connection.execute("ALTER TABLE mob_prototype ADD COLUMN race_id VARCHAR")
    connection.commit()
    connection.close()
    assert "race_id" in adapter.connection.schema().report.unsupported.get("mob_prototype", [])
    refreshed = adapter.connection.schema(refresh=True)
    assert "race_id" not in refreshed.report.unsupported.get("mob_prototype", [])
    await adapter.close()
