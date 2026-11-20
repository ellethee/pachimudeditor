"""Compatibilita' del DB dei giocatori con lo schema del gioco: revisioni note/ignote e degrado quando mancano colonne o tabelle.

Nel DB del gioco restano solo `account` e `player_character`: i contenuti (YAML) non dipendono dallo schema. I database di prova sono
creati con i modelli copiati del gioco e poi "invecchiati" o alterati con SQL.
"""

import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from pachimudeditor.common.adapters.models import RoomIn, ZonePageParams
from pachimudeditor.common.adapters.registry import WorldConfig, WorldRegistry, get_registry, set_registry
from pachimudeditor_adapter_pachimud.adapter import PachimudAdapter
from pachimudeditor_adapter_pachimud.schema import HEAD, REVISIONS
from tests.helpers import data, error_code
from tests.support import stack

OLD_COLUMNS = [
    "ALTER TABLE account DROP COLUMN language",
    "ALTER TABLE player_character DROP COLUMN inventory",
]
"""Come uno schema alla revisione `1d51263b0036` (prima dell'inventario JSON e della lingua)."""
OLD_REVISION = REVISIONS[5]


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
    assert report is not None and report.db is not None
    assert report.db.status == "ok" and report.db.revision == HEAD == REVISIONS[-1]
    assert report.warnings == [] and report.db.unsupported == {}
    assert report.summary().startswith("3 stanze, 2 mob, 2 oggetti; giocatori: schema ok")
    caps = adapter.capabilities()
    assert caps.supports_players and caps.supports_transfer and caps.supports_extra_descriptions and not caps.supports_instances
    await adapter.close()


async def test_old_schema_degrades_gracefully(tmp_path: Path) -> None:
    """Schema senza `inventory` e `language`: stato `behind`, colonne `unsupported`, il resto del mondo funziona."""
    adapter = world(tmp_path, *OLD_COLUMNS, revision=OLD_REVISION)
    report = adapter.schema_report()
    assert report is not None and report.db is not None
    assert report.db.status == "behind" and report.db.revision == OLD_REVISION
    assert report.db.unsupported == {"account": ["language"], "player_character": ["inventory"]} and report.warnings == []
    models = adapter.connection.schema().models  # type: ignore[union-attr]
    assert not models.column("player_character", "inventory") and models.column("player_character", "name")
    assert adapter.capabilities().supports_players
    assert (await adapter.list_zones(ZonePageParams())).total == 2  # i contenuti sono su file
    await adapter.close()


async def test_unknown_revision_warns_but_works(tmp_path: Path) -> None:
    """Revisione ignota (gioco piu' recente): avviso, stato `unknown`, il mondo funziona."""
    adapter = world(tmp_path, revision="ffffffffffff")
    report = adapter.schema_report()
    assert report is not None and report.db is not None and report.db.status == "unknown"
    assert [i.code for i in report.warnings] == ["unknown_revision"]
    assert (await adapter.list_zones(ZonePageParams())).total == 2
    await adapter.close()


async def test_unversioned_database(tmp_path: Path) -> None:
    """Senza `alembic_version`: stato `unversioned` con avviso."""
    adapter = world(tmp_path, revision=None)
    report = adapter.schema_report()
    assert report is not None and report.db is not None and report.db.status == "unversioned" and report.db.revision is None
    assert [i.code for i in report.warnings] == ["unversioned"]
    await adapter.close()


async def test_unknown_required_column_is_a_warning(tmp_path: Path) -> None:
    """Una colonna nuova: con default solo informazione; NOT NULL senza default: avviso (gli inserimenti potrebbero fallire)."""
    adapter = world(
        tmp_path,
        "ALTER TABLE account ADD COLUMN futuro INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE player_character ADD COLUMN nuova VARCHAR",
    )
    report = adapter.schema_report()
    assert report is not None and report.db is not None and report.db.status == "ok"
    assert report.warnings == []
    assert any(i.code == "unknown_column" for i in report.db.issues)
    await adapter.close()


async def test_missing_players_tables_switch_off_capability(tmp_path: Path) -> None:
    """Senza `account`/`player_character` niente giocatori; i contenuti (YAML) funzionano e si possono scrivere."""
    adapter = world(tmp_path, "DROP TABLE player_character", "DROP TABLE account")
    caps = adapter.capabilities()
    assert not caps.supports_players and not caps.supports_instances and caps.supports_transfer and caps.supports_extra_descriptions
    report = adapter.schema_report()
    assert report is not None and report.db is not None and report.db.status == "ok" and len(report.db.missing_tables) == 2
    zones = await adapter.list_zones(ZonePageParams())
    room = await adapter.create_room(RoomIn(vnum=1700, zone_id=zones.items[0].id, name="solo"))
    await adapter.delete_room(room.id)
    await adapter.close()


async def test_incompatible_players_db_is_503_only_for_players(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Manca una colonna essenziale: i giocatori rispondono 503 `world.unavailable` (dettaglio solo nel log), i contenuti funzionano."""
    adapter = world(tmp_path, "ALTER TABLE player_character RENAME COLUMN account_id TO account_ref")
    report = adapter.schema_report()
    assert report is not None and report.db is not None and report.db.status == "incompatible"
    assert not adapter.capabilities().supports_players
    with pytest.raises(HTTPException) as error:
        async with adapter.session():
            pass
    assert error.value.status_code == 503 and error.value.detail[0]["code"] == "world.unavailable"
    # niente percorso/driver nella risposta, dettaglio solo nel log
    assert str(tmp_path) not in str(error.value.detail) and "account_id" not in str(error.value.detail)
    assert any("account_id" in r.getMessage() for r in caplog.records)
    assert (await adapter.list_zones(ZonePageParams())).total == 2
    await adapter.close()


async def test_missing_database_file_is_not_created(tmp_path: Path) -> None:
    """File SQLite inesistente: giocatori non disponibili e NESSUN DB vuoto creato; i contenuti funzionano."""
    stack.seed_game_db(tmp_path)
    missing = tmp_path / "non-esiste.db"
    adapter = PachimudAdapter(
        WorldConfig(
            id="w",
            kind="pachimud",
            params={"database_url": f"sqlite+aiosqlite:///{missing}", "definitions_path": str(tmp_path / "definitions")},
        )
    )
    with pytest.raises(HTTPException) as error:
        async with adapter.session():
            pass
    assert error.value.status_code == 503
    report = adapter.schema_report()
    assert not missing.exists() and report is not None and report.db is None and not adapter.capabilities().supports_players
    assert (await adapter.list_zones(ZonePageParams())).total == 2
    await adapter.close()


async def test_world_without_database_url(tmp_path: Path) -> None:
    """Senza `database_url` il mondo ha solo i contenuti (nessuna capability dei giocatori)."""
    stack.seed_game_db(tmp_path)
    adapter = PachimudAdapter(WorldConfig(id="w", kind="pachimud", params={"definitions_path": str(tmp_path / "definitions")}))
    assert not adapter.capabilities().supports_players and adapter.capabilities().supports_transfer
    assert (await adapter.list_zones(ZonePageParams())).total == 2
    await adapter.close()


async def test_missing_definitions_is_503_keeps_others_working(
    client: httpx.AsyncClient, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Due mondi pachimud: quello senza cartella delle definizioni risponde 503 con codice stabile, il default continua a funzionare."""
    registry = WorldRegistry(
        [
            WorldConfig(id="pachimud", kind="pachimud", params=stack.current_params()),
            WorldConfig(id="rotto", kind="pachimud", params={"definitions_path": str(tmp_path / "non-esiste")}),
        ],
        "pachimud",
    )
    previous = get_registry()
    set_registry(registry)
    try:
        response = await client.get("/api/zones", headers={"X-World": "rotto"})
        assert error_code(response, 503) == "world.unavailable" and str(tmp_path) not in response.text
        assert any("non-esiste" in r.getMessage() for r in caplog.records)
        assert data(await client.get("/api/zones"))["total"] == 2
        worlds = {w["id"]: w for w in data(await client.get("/api/worlds"))}
        assert set(worlds) == {"pachimud", "rotto"} and worlds["rotto"]["capabilities"]["supportsPlayers"] is False
        assert registry.get("rotto").unavailable_reason()  # type: ignore[attr-defined]
    finally:
        await registry.aclose_all()
        set_registry(previous)


async def test_schema_is_read_once_and_refreshable(tmp_path: Path) -> None:
    """Lo schema si legge una volta; `refresh=True` lo rilegge (dopo una migration del gioco)."""
    adapter = world(tmp_path, *OLD_COLUMNS, revision=OLD_REVISION)
    first = adapter.connection.schema()  # type: ignore[union-attr]
    assert adapter.connection.schema() is first  # type: ignore[union-attr]
    connection = sqlite3.connect(tmp_path / "game.db")
    connection.execute("ALTER TABLE account ADD COLUMN language VARCHAR")
    connection.commit()
    connection.close()
    assert "language" in adapter.connection.schema().report.unsupported.get("account", [])  # type: ignore[union-attr]
    refreshed = adapter.connection.schema(refresh=True)  # type: ignore[union-attr]
    assert "language" not in refreshed.report.unsupported.get("account", [])
    await adapter.close()
