"""Equivalenza editor <-> gioco (il gioco e' una dipendenza di SOLO sviluppo: senza `pachimud` questi test si saltano).

- hash delle password: quelli dell'editor si verificano con `verify_password` del gioco e viceversa;
- trasferimento zone: file scritti dall'editor letti dall'importer del gioco, e file del gioco letti dall'editor,
  danno le stesse righe nel database;
- allineamento dei dati dell'editor (enum, schemi dei file, colonne attese, revisioni alembic) con il gioco.
"""

import re
import shutil
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("pachimud")

from pachimud.account import security as game_security  # noqa: E402
from pachimud.database.base import Base  # noqa: E402
from pachimud.database.database import create_engine, create_session_factory  # noqa: E402
from pachimud.zone.importer import import_zone_directory as game_import  # noqa: E402

from pachimudeditor_adapter_pachimud import security as editor_security  # noqa: E402
from pachimudeditor_adapter_pachimud.adapter import PachimudAdapter  # noqa: E402
from pachimudeditor_adapter_pachimud.transfer.files import ZONE_FILES  # noqa: E402
from pachimudeditor.common.adapters.models import ZonePageParams  # noqa: E402
from pachimudeditor.common.adapters.registry import WorldConfig  # noqa: E402
from tests.support import stack  # noqa: E402
from tests.support.stack import REPO_ROOT  # noqa: E402
from tests.support.zone_fixture import write_zone  # noqa: E402

TABLES = ("zone", "room", "exit", "room_extra_description", "mob_prototype", "object_prototype", "zone_reset_command")


# ------------------------------------------------------------------------------ hash


def test_hash_made_by_editor_verifies_in_game() -> None:
    """Un hash dell'editor passa `verify_password` del gioco (stesso formato Argon2id e parametri)."""
    hashed = editor_security.hash_password("una password-di-prova 123")
    assert hashed.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert game_security.verify_password(hashed, "una password-di-prova 123")
    assert not game_security.verify_password(hashed, "sbagliata")


def test_hash_made_by_game_verifies_in_editor() -> None:
    """E viceversa; un hash non valido non solleva."""
    hashed = game_security.hash_password("altra-password-9")
    assert editor_security.verify_password(hashed, "altra-password-9")
    assert not editor_security.verify_password(hashed, "no")
    assert editor_security.verify_password("non-un-hash", "x") is False
    assert game_security.hash_password("x").split("$")[:4] == editor_security.hash_password("x").split("$")[:4]


# ------------------------------------------------------------------------------ allineamento dati


def test_editor_data_tables_match_game() -> None:
    """Enum del gioco = tabelle dati dell'editor (nomi e valori); anche i flag di razze e mob."""
    from pachimud.character import enums as game_char
    from pachimud.character.race import enums as game_race
    from pachimud.object import enums as game_obj
    from pachimud.zone import enums as game_zone
    from pachimud.zone.room import enums as game_room

    from pachimudeditor_adapter_pachimud import race_enums
    from pachimudeditor.common import enums

    pairs = [
        (game_char, enums, ["Sex", "Position"]),
        (game_obj, enums, ["ObjectType"]),
        (game_zone, enums, ["ZoneCommandType", "ZoneResetMode"]),
        (game_room, enums, ["SectorType", "Direction", "DoorFlag"]),
        (
            game_race,
            race_enums,
            ["MobileFlags", "OffensiveFlags", "ResistanceFlags", "FormFlags", "PartFlags", "AffectedByFlags", "SizeType"],
        ),
    ]
    for original, mine, names in pairs:
        for name in names:
            assert {m.name: m.value for m in getattr(original, name)} == {m.name: m.value for m in getattr(mine, name)}, name


def _fields(model: type) -> dict[str, object]:
    """Campi Pydantic di un modello: nome -> (default, obbligatorio)."""
    return {n: (f.default if not f.is_required() else "<req>") for n, f in model.model_fields.items()}  # type: ignore[attr-defined]


def test_loader_schemas_match_game() -> None:
    """Gli schemi dei file YAML e delle definizioni (razze/classi) hanno gli stessi campi e default di quelli del gioco."""
    from pachimud.character.classes.schema import loader_class as g_class
    from pachimud.character.race.schema import loader_race as g_race
    from pachimud.mob.schema import loader_mob as g_mob
    from pachimud.object.schema import loader_object as g_obj
    from pachimud.zone.room.schema import loader_room as g_room
    from pachimud.zone.schema import loader_reset as g_reset
    from pachimud.zone.schema import loader_zone as g_zone

    from pachimudeditor_adapter_pachimud import definitions
    from pachimudeditor_adapter_pachimud.transfer import schemas

    for mine, theirs in [
        (schemas.LoaderZone, g_zone.LoaderZone),
        (schemas.LoaderExit, g_room.LoaderExit),
        (schemas.LoaderExtraDescription, g_room.LoaderExtraDescription),
        (schemas.LoaderRoom, g_room.LoaderRoom),
        (schemas.LoaderRoomsFile, g_room.LoaderRoomsFile),
        (schemas.LoaderMob, g_mob.LoaderMob),
        (schemas.LoaderMobsFile, g_mob.LoaderMobsFile),
        (schemas.LoaderObject, g_obj.LoaderObject),
        (schemas.LoaderObjectsFile, g_obj.LoaderObjectsFile),
        (schemas.LoaderLoadMob, g_reset.LoaderLoadMob),
        (schemas.LoaderLoadObject, g_reset.LoaderLoadObject),
        (schemas.LoaderGiveObject, g_reset.LoaderGiveObject),
        (schemas.LoaderEquipObject, g_reset.LoaderEquipObject),
        (schemas.LoaderPutObject, g_reset.LoaderPutObject),
        (schemas.LoaderSetDoorState, g_reset.LoaderSetDoorState),
        (schemas.LoaderRandomizeExits, g_reset.LoaderRandomizeExits),
        (definitions.LoaderRace, g_race.LoaderRace),
        (definitions.LoaderClass, g_class.LoaderClass),
    ]:
        assert _fields(mine) == _fields(theirs), mine.__name__


def test_expected_columns_match_game_models() -> None:
    """Le colonne attese dall'editor (`EXPECTED`) coincidono con quelle dei modelli del gioco (nome e nullabilita')."""
    import pachimud.database  # noqa: F401  registra i modelli

    from pachimudeditor_adapter_pachimud.schema import EXPECTED

    for table_name, columns in EXPECTED.items():
        table = Base.metadata.tables[table_name]
        assert set(columns) == {c.name for c in table.c}, table_name
        for name, spec in columns.items():
            if name != "id":
                assert spec.null == table.c[name].nullable, f"{table_name}.{name}"
    assert set(EXPECTED) == {t for t in Base.metadata.tables}


def test_known_revisions_match_alembic_chain() -> None:
    """`REVISIONS` e' la catena delle migration alembic del gioco, nell'ordine di applicazione."""
    from pachimudeditor_adapter_pachimud.schema import REVISIONS

    versions = REPO_ROOT / "alembic" / "versions"
    if not versions.is_dir():
        pytest.skip("alembic/versions del gioco non trovato")
    down: dict[str, str | None] = {}
    for path in versions.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        revision = re.search(r"^revision(?::[^=]+)?\s*=\s*['\"](\w+)['\"]", text, re.M)
        parent = re.search(r"^down_revision(?::[^=]+)?\s*=\s*(?:['\"](\w+)['\"]|None)", text, re.M)
        assert revision and parent
        down[revision.group(1)] = parent.group(1)
    chain: list[str] = []
    head = next(r for r in down if r not in down.values())
    while head is not None:
        chain.insert(0, head)
        head = down[head]
    assert tuple(chain) == REVISIONS


# ------------------------------------------------------------------------------ trasferimento zone


def _dump(path: Path) -> dict[str, list[tuple]]:
    """Tutte le righe delle tabelle di contenuto, ordinate per id."""
    connection = sqlite3.connect(path)
    try:
        return {t: connection.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in TABLES}  # noqa: S608
    finally:
        connection.close()


def _empty_game_db(path: Path) -> str:
    """Un DB di gioco vuoto creato dal GIOCO (schema `Base.metadata.create_all`); restituisce l'URL async."""
    import pachimud.database  # noqa: F401
    from sqlalchemy import create_engine as sync_engine

    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
    engine = sync_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    engine.dispose()
    return f"sqlite+aiosqlite:///{path}"


async def _game_import(path: Path, zone_dir: Path) -> None:
    """Importa `zone_dir` con l'importer del GIOCO nel DB `path`."""
    engine = create_engine(_empty_game_db(path) if not path.exists() else f"sqlite+aiosqlite:///{path}")
    try:
        async with create_session_factory(engine)() as session:
            await game_import(session, zone_dir)
            await session.commit()
    finally:
        await engine.dispose()


async def _editor_import(path: Path, zone_dir: Path, *, create: bool = True) -> PachimudAdapter:
    """Importa `zone_dir` con l'importer dell'EDITOR in un DB di gioco (creato dal gioco se manca)."""
    url = _empty_game_db(path) if create else f"sqlite+aiosqlite:///{path}"
    adapter = PachimudAdapter(
        WorldConfig(id="eq", kind="pachimud", params={"database_url": url, "definitions_path": str(REPO_ROOT / "definitions")})
    )
    preview = await adapter.import_zone_dir(zone_dir, dry_run=False, confirm=True)
    assert preview.applied and not preview.conflicts
    return adapter


async def _editor_export(adapter: PachimudAdapter, vnum: int, target: Path) -> Path:
    """Esporta la zona `vnum` con l'editor in `target`."""
    page = await adapter.list_zones(ZonePageParams())
    zone = next(z for z in page.items if z.vnum == vnum)
    bundle = await adapter.export_zone_bundle(zone.id)
    target.mkdir(parents=True, exist_ok=True)
    assert sorted(bundle.files) == sorted(ZONE_FILES)
    for name, text in bundle.files.items():
        (target / name).write_text(text, encoding="utf-8")
    return target


async def test_game_files_editor_import_same_rows_as_game_import(tmp_path: Path) -> None:
    """File del gioco -> importer dell'editor = stesse righe (ids compresi) dell'importer del gioco."""
    zone_dir = write_zone(tmp_path / "zona")
    await _game_import(tmp_path / "game.db", zone_dir)
    adapter = await _editor_import(tmp_path / "editor.db", zone_dir)
    await adapter.close()
    game_rows, editor_rows = _dump(tmp_path / "game.db"), _dump(tmp_path / "editor.db")
    assert editor_rows == game_rows
    assert len(game_rows["room"]) == 3 and len(game_rows["exit"]) == 6 and len(game_rows["zone_reset_command"]) == 7


async def test_editor_export_game_import_same_rows(tmp_path: Path) -> None:
    """Zona esportata dall'editor -> importer del gioco = le stesse righe da cui e' stata esportata."""
    zone_dir = write_zone(tmp_path / "zona")
    adapter = await _editor_import(tmp_path / "origine.db", zone_dir)
    exported = await _editor_export(adapter, 88, tmp_path / "esportata")
    await adapter.close()
    await _game_import(tmp_path / "game.db", exported)
    assert _dump(tmp_path / "game.db") == _dump(tmp_path / "origine.db")


async def test_real_zone_definitions_equivalent(tmp_path: Path) -> None:
    """La zona reale `RavnFjord` (copia): gioco -> DB, esportata dall'editor, riletta dal gioco = stesse righe."""
    source = REPO_ROOT / "definitions" / "zones" / "RavnFjord"
    if not source.is_dir():
        pytest.skip("zona RavnFjord non trovata")
    copy = tmp_path / "RavnFjord"
    shutil.copytree(source, copy)
    await _game_import(tmp_path / "a.db", copy)
    adapter_b = await _editor_import(tmp_path / "b.db", copy)
    await adapter_b.close()
    assert _dump(tmp_path / "b.db") == _dump(tmp_path / "a.db")
    adapter_a = PachimudAdapter(WorldConfig(id="a", kind="pachimud", params={"database_url": f"sqlite+aiosqlite:///{tmp_path / 'a.db'}"}))
    exported = await _editor_export(adapter_a, _dump(tmp_path / "a.db")["zone"][0][1], tmp_path / "exp")
    await adapter_a.close()
    await _game_import(tmp_path / "c.db", exported)
    assert _dump(tmp_path / "c.db") == _dump(tmp_path / "a.db")


async def test_second_import_is_idempotent_like_game(tmp_path: Path) -> None:
    """Reimportare la stessa zona (editor e gioco) lascia i dati come sono, tranne gli id dei reset (sostituiti)."""
    zone_dir = write_zone(tmp_path / "zona")
    await _game_import(tmp_path / "game.db", zone_dir)
    await _game_import(tmp_path / "game.db", zone_dir)
    adapter = await _editor_import(tmp_path / "editor.db", zone_dir)
    again = await adapter.import_zone_dir(zone_dir, dry_run=False, confirm=True)
    await adapter.close()
    assert again.zone.action == "unchanged" and again.resets.changed is False
    assert _dump(tmp_path / "editor.db") == _dump(tmp_path / "game.db")


def test_stack_world_params_point_to_tmp(tmp_path: Path) -> None:
    """`world_params` non usa mai il database reale del gioco."""
    params = stack.world_params(tmp_path)
    assert str(tmp_path) in params["database_url"] and str(REPO_ROOT / "pachimud.db") not in params["database_url"]
