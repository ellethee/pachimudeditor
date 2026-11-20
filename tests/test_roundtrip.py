"""Coerenza editor <-> file YAML e <-> modelli copiati del gioco (`game_models`): girano sempre, senza checkout del MUD.

- colonne attese dall'adapter (`EXPECTED`) = colonne dei modelli copiati (`account`, `player_character`, `board_message`, `mail_message`);
- rilettura e riscrittura di una zona (la zona di prova «ricca» e `RavnFjord` di esempio) con i suoi stessi valori:
  i file restano semanticamente identici (stessi dati, commenti conservati);
- export -> import in un mondo vuoto: gli stessi file;
- hash delle password: round-trip del formato Argon2id.
Il confronto con il MUD vero e' opzionale: `tests/test_game_compat.py` (`PACHIMUD_GAME_ROOT`).
"""

import shutil
from pathlib import Path

import pytest
import yaml

from pachimudeditor.common.adapters.models import (
    ExitPatch,
    MobPatch,
    ObjectPatch,
    ResetCommandIn,
    ResetScriptIn,
    RoomPatch,
    ZonePatch,
)
from pachimudeditor.common.adapters.registry import WorldConfig
from pachimudeditor_adapter_pachimud import security as editor_security
from pachimudeditor_adapter_pachimud.adapter import PachimudAdapter
from pachimudeditor_adapter_pachimud.game_models import Base
from pachimudeditor_adapter_pachimud.schema import EXPECTED
from tests.support import stack
from tests.support.stack import DEFINITIONS_FIXTURE
from tests.support.zone_fixture import write_zone


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
    assert set(EXPECTED) == set(Base.metadata.tables) == {"account", "player_character", "board_message", "mail_message"}


def _world(tmp_path: Path, zone_dir: Path) -> PachimudAdapter:
    """Un adapter su `definitions/` temporanee (razze/classi di esempio) con `zone_dir` come unica zona."""
    definitions = tmp_path / "definitions"
    shutil.copytree(DEFINITIONS_FIXTURE, definitions, ignore=shutil.ignore_patterns("zones", "README.md"), dirs_exist_ok=True)
    shutil.copytree(zone_dir, definitions / "zones" / zone_dir.name)
    return PachimudAdapter(WorldConfig(id="rt", kind="pachimud", params={"definitions_path": str(definitions)}))


def _snapshot(adapter: PachimudAdapter) -> dict[str, object]:
    """Il contenuto di tutti i file YAML delle zone come dati (indipendente da formato e ordine dei commenti)."""
    root = adapter.params.definitions_path / "zones"
    return {str(p.relative_to(root)): yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(root.rglob("*.yaml"))}


async def _rewrite_everything(adapter: PachimudAdapter) -> None:
    """Rilegge ogni entita' e la riscrive con i suoi stessi valori (PATCH completa), come farebbe il form dell'editor."""
    from pachimudeditor.common.adapters.models import MobPageParams, ObjectPageParams, RoomPageParams, ZonePageParams

    for z in (await adapter.list_zones(ZonePageParams())).items:
        await adapter.update_zone(
            z.id, ZonePatch.model_validate(z.model_dump(by_alias=False, exclude={"id", "extra"}) | {"extra": z.extra})
        )
        for r in (await adapter.list_rooms(RoomPageParams(zone_id=z.id))).items:
            detail = await adapter.get_room(r.id)
            await adapter.update_room(r.id, RoomPatch.model_validate(r.model_dump(by_alias=False, exclude={"id", "zone_id"})))
            for e in detail.exits:
                body = e.model_dump(by_alias=False, include={"description", "keywords", "door_flag", "is_open", "is_locked", "key_vnum"})
                await adapter.update_exit(r.id, e.id, ExitPatch.model_validate(body | {"target_room_id": e.target_room_id}))
        for m in (await adapter.list_mobs(MobPageParams(zone_id=z.id))).items:
            await adapter.update_mob(m.id, MobPatch.model_validate(m.model_dump(by_alias=False, exclude={"id", "zone_id", "is_trainer"})))
        for o in (await adapter.list_objects(ObjectPageParams(zone_id=z.id))).items:
            await adapter.update_object(o.id, ObjectPatch.model_validate(o.model_dump(by_alias=False, exclude={"id", "zone_id"})))
        script = await adapter.list_reset_commands(z.id)
        await adapter.replace_reset_commands(
            z.id,
            ResetScriptIn(
                commands=[
                    ResetCommandIn.model_validate(
                        c.model_dump(by_alias=False, exclude={"id", "zone_id", "order_index", "extra", "if_value", "comment", "if_flag"})
                    )
                    for c in script
                ]
            ),
        )


@pytest.mark.parametrize("name", ["rich", "RavnFjord"])
async def test_rewrite_with_same_values_keeps_files(tmp_path: Path, name: str) -> None:
    """Riscrivere ogni voce con i suoi stessi valori non cambia i dati dei file (RavnFjord e la zona di prova ricca)."""
    zone_dir = write_zone(tmp_path / "src" / "Terra") if name == "rich" else DEFINITIONS_FIXTURE / "zones" / "RavnFjord"
    adapter = _world(tmp_path, zone_dir)
    before = _snapshot(adapter)
    assert adapter.schema_report().problems == []  # type: ignore[union-attr]
    await _rewrite_everything(adapter)
    assert _snapshot(adapter) == before
    assert adapter.schema_report().problems == []  # type: ignore[union-attr]


async def test_comments_survive_writes(tmp_path: Path) -> None:
    """Una modifica a una voce non perde i commenti del file."""
    adapter = _world(tmp_path, write_zone(tmp_path / "src" / "Terra"))
    await adapter.update_room(8801, RoomPatch(name="Salone"))
    text = (adapter.params.definitions_path / "zones" / "Terra" / "rooms.yaml").read_text(encoding="utf-8")
    assert "# l'atrio: il cuore della zona" in text and "name: Salone" in text


async def test_export_import_roundtrip(tmp_path: Path) -> None:
    """Esporta la zona ricca e la reimporta in un mondo vuoto: gli stessi file (testo identico)."""
    adapter = _world(tmp_path / "a", write_zone(tmp_path / "src" / "Terra"))
    bundle = await adapter.export_zone_bundle(88)
    assert sorted(bundle.files) == sorted(["zone.yaml", "rooms.yaml", "rooms_cantine.yaml", "mobs.yaml", "objects.yaml", "resets.yaml"])
    staged = tmp_path / "staged"
    staged.mkdir()
    for file_name, text in bundle.files.items():
        (staged / file_name).write_text(text, encoding="utf-8")
    empty = tmp_path / "empty"
    shutil.copytree(DEFINITIONS_FIXTURE, empty, ignore=shutil.ignore_patterns("zones", "README.md"))
    other = PachimudAdapter(WorldConfig(id="rt2", kind="pachimud", params={"definitions_path": str(empty)}))
    preview = await other.import_zone_dir(staged, dry_run=False, confirm=True)
    assert preview.applied and not preview.conflicts
    assert (await other.export_zone_bundle(88)).files == bundle.files
    again = await other.import_zone_dir(staged, dry_run=True, confirm=False)
    assert again.zone.action == "unchanged" and not again.resets.changed


def test_stack_world_params_point_to_tmp(tmp_path: Path) -> None:
    """`world_params` non usa mai un database di gioco reale."""
    params = stack.world_params(tmp_path)
    assert str(tmp_path) in params["database_url"] and str(tmp_path) in params["definitions_path"]
