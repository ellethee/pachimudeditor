"""Coerenza editor <-> modelli copiati del gioco (`game_models`): girano sempre, senza checkout del MUD.

- colonne attese dall'adapter (`EXPECTED`) = colonne dei modelli copiati;
- zone importate dall'editor, esportate e reimportate = stesse righe (zona di prova e `RavnFjord` di esempio);
- hash delle password: round-trip del formato Argon2id.
Il confronto con il MUD vero e' opzionale: `tests/test_game_compat.py` (`PACHIMUD_GAME_ROOT`).
"""

import shutil
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine as sync_engine

from pachimudeditor_adapter_pachimud import security as editor_security
from pachimudeditor_adapter_pachimud.adapter import PachimudAdapter
from pachimudeditor_adapter_pachimud.game_models import Base
from pachimudeditor_adapter_pachimud.schema import EXPECTED
from pachimudeditor_adapter_pachimud.transfer.files import ZONE_FILES
from pachimudeditor.common.adapters.models import ZonePageParams
from pachimudeditor.common.adapters.registry import WorldConfig
from tests.support import stack
from tests.support.stack import DEFINITIONS_FIXTURE
from tests.support.zone_fixture import write_zone

TABLES = ("zone", "room", "exit", "room_extra_description", "mob_prototype", "object_prototype", "zone_reset_command")


def test_hash_format_and_roundtrip() -> None:
    """Hash Argon2id con i parametri del gioco; verifica corretta, errata e hash non valido (mai eccezioni)."""
    hashed = editor_security.hash_password("una password-di-prova 123")
    assert hashed.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert editor_security.verify_password(hashed, "una password-di-prova 123")
    assert not editor_security.verify_password(hashed, "sbagliata")
    assert editor_security.verify_password("non-un-hash", "x") is False


def test_expected_columns_match_copied_models() -> None:
    """Le colonne attese dall'editor (`EXPECTED`) coincidono con i modelli copiati (nome e nullabilita')."""
    for table_name, columns in EXPECTED.items():
        table = Base.metadata.tables[table_name]
        assert set(columns) == {c.name for c in table.c}, table_name
        for name, spec in columns.items():
            if name != "id":
                assert spec.null == table.c[name].nullable, f"{table_name}.{name}"
    assert set(EXPECTED) == set(Base.metadata.tables)


def _dump(path: Path) -> dict[str, list[tuple]]:
    """Tutte le righe delle tabelle di contenuto, ordinate per id."""
    connection = sqlite3.connect(path)
    try:
        return {t: connection.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in TABLES}  # noqa: S608
    finally:
        connection.close()


def _empty_db_url(path: Path) -> str:
    """Un DB di gioco vuoto con lo schema dei modelli copiati; restituisce l'URL async."""
    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
    engine = sync_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    engine.dispose()
    return f"sqlite+aiosqlite:///{path}"


def _adapter(path: Path, *, create: bool = True) -> PachimudAdapter:
    """Adapter su un DB (nuovo con `create`) con le definizioni di esempio."""
    url = _empty_db_url(path) if create else f"sqlite+aiosqlite:///{path}"
    return PachimudAdapter(
        WorldConfig(id="rt", kind="pachimud", params={"database_url": url, "definitions_path": str(DEFINITIONS_FIXTURE)})
    )


async def _export(adapter: PachimudAdapter, vnum: int, target: Path) -> Path:
    """Esporta la zona `vnum` in `target`."""
    page = await adapter.list_zones(ZonePageParams())
    zone = next(z for z in page.items if z.vnum == vnum)
    bundle = await adapter.export_zone_bundle(zone.id)
    target.mkdir(parents=True, exist_ok=True)
    assert sorted(bundle.files) == sorted(ZONE_FILES)
    for name, text in bundle.files.items():
        (target / name).write_text(text, encoding="utf-8")
    return target


async def _roundtrip(tmp_path: Path, zone_dir: Path, vnum: int | None) -> dict[str, list[tuple]]:
    """Importa `zone_dir`, esporta, reimporta in un altro DB: restituisce le righe dei due (devono coincidere)."""
    first = _adapter(tmp_path / "a.db")
    preview = await first.import_zone_dir(zone_dir, dry_run=False, confirm=True)
    assert preview.applied and not preview.conflicts
    rows_a = _dump(tmp_path / "a.db")
    exported = await _export(first, vnum if vnum is not None else rows_a["zone"][0][1], tmp_path / "exp")
    await first.close()
    second = _adapter(tmp_path / "b.db")
    assert (await second.import_zone_dir(exported, dry_run=False, confirm=True)).applied
    await second.close()
    assert _dump(tmp_path / "b.db") == rows_a
    return rows_a


async def test_zone_export_import_roundtrip(tmp_path: Path) -> None:
    """Zona di prova: import -> export -> import = stesse righe (ids compresi)."""
    rows = await _roundtrip(tmp_path, write_zone(tmp_path / "zona"), 88)
    assert len(rows["room"]) == 3 and len(rows["exit"]) == 6 and len(rows["zone_reset_command"]) == 7


async def test_sample_zone_roundtrip(tmp_path: Path) -> None:
    """La zona di esempio `RavnFjord` (fixture) fa lo stesso giro."""
    copy = tmp_path / "RavnFjord"
    shutil.copytree(DEFINITIONS_FIXTURE / "zones" / "RavnFjord", copy)
    rows = await _roundtrip(tmp_path, copy, None)
    assert rows["room"]


async def test_second_import_is_idempotent(tmp_path: Path) -> None:
    """Reimportare la stessa zona la lascia com'e' (zona `unchanged`, stesse righe)."""
    zone_dir = write_zone(tmp_path / "zona")
    adapter = _adapter(tmp_path / "editor.db")
    await adapter.import_zone_dir(zone_dir, dry_run=False, confirm=True)
    before = _dump(tmp_path / "editor.db")
    again = await adapter.import_zone_dir(zone_dir, dry_run=False, confirm=True)
    await adapter.close()
    assert again.zone.action == "unchanged" and again.resets.changed is False
    after = _dump(tmp_path / "editor.db")  # gli id dei figli (extra description, reset) possono essere rigenerati
    assert {k: len(v) for k, v in after.items()} == {k: len(v) for k, v in before.items()}
    assert after["room"] == before["room"] and after["zone"] == before["zone"]


def test_stack_world_params_point_to_tmp(tmp_path: Path) -> None:
    """`world_params` non usa mai un database di gioco reale."""
    params = stack.world_params(tmp_path)
    assert str(tmp_path) in params["database_url"] and str(tmp_path) in params["definitions_path"]
