"""Allineamento editor <-> MUD vero: OPZIONALE, gira solo con `PACHIMUD_GAME_ROOT` che punta a un checkout del gioco.

Il gioco non e' una dipendenza (loader YAML in `loaders.py`, modelli del DB in `game_models`): senza checkout questi test si
saltano. Il checkout e' solo letto: avviare pytest con `PYTHONDONTWRITEBYTECODE=1` per non creare `__pycache__` nel suo albero.

- hash delle password: quelli dell'editor si verificano con `verify_password` del gioco e viceversa;
- allineamento dei dati dell'editor (enum, loader YAML, colonne attese, revisioni alembic) con il gioco;
- le `definitions/` reali del gioco si caricano senza errori e si riscrivono (su una COPIA) con gli stessi dati;
- i file scritti dall'editor sono validi per i loader del gioco.
"""

import re
import shutil
from pathlib import Path

import pytest
import yaml

from pachimudeditor.common.adapters.models import (
    ExitPatch,
    MobPageParams,
    MobPatch,
    ObjectPageParams,
    ObjectPatch,
    RoomPageParams,
    RoomPatch,
)
from pachimudeditor.common.adapters.registry import WorldConfig
from pachimudeditor_adapter_pachimud import security as editor_security  # noqa: E402
from pachimudeditor_adapter_pachimud.adapter import PachimudAdapter  # noqa: E402
from tests.support.game_checkout import game_root, load  # noqa: E402
from tests.support.zone_fixture import write_zone  # noqa: E402
from tests.test_roundtrip import _rewrite_everything, _snapshot  # noqa: E402

pytestmark = pytest.mark.skipif(game_root() is None, reason="PACHIMUD_GAME_ROOT non impostata: confronto col MUD saltato")


# ------------------------------------------------------------------------------ hash


def test_hash_made_by_editor_verifies_in_game() -> None:
    """Un hash dell'editor passa `verify_password` del gioco (stesso formato Argon2id e parametri)."""
    hashed = editor_security.hash_password("una password-di-prova 123")
    assert hashed.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert load("account.security").verify_password(hashed, "una password-di-prova 123")
    assert not load("account.security").verify_password(hashed, "sbagliata")


def test_hash_made_by_game_verifies_in_editor() -> None:
    """E viceversa; un hash non valido non solleva."""
    hashed = load("account.security").hash_password("altra-password-9")
    assert editor_security.verify_password(hashed, "altra-password-9")
    assert not editor_security.verify_password(hashed, "no")
    assert editor_security.verify_password("non-un-hash", "x") is False
    assert load("account.security").hash_password("x").split("$")[:4] == editor_security.hash_password("x").split("$")[:4]


# ------------------------------------------------------------------------------ allineamento dati


def test_editor_data_tables_match_game() -> None:
    """Enum del gioco = tabelle dati dell'editor (nomi e valori); i tipi oggetto per nome (i numeri del gioco sono LeU)."""
    game_char, game_race, game_obj = load("character.enums"), load("character.race.enums"), load("object.enums")
    game_zone, game_room = load("zone.enums"), load("zone.room.enums")

    from pachimudeditor.common import enums
    from pachimudeditor_adapter_pachimud import race_enums

    pairs = [
        (game_char, enums, ["Sex", "Position"]),
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
    ours = {m.name for m in enums.ObjectType} | {"DRINKCON"}
    assert {m.name for m in game_obj.ObjectType} <= ours, {m.name for m in game_obj.ObjectType} - ours


def _fields(model: type) -> dict[str, object]:
    """Campi Pydantic di un modello: nome -> (default, obbligatorio)."""
    return {n: (f.default if not f.is_required() else "<req>") for n, f in model.model_fields.items()}  # type: ignore[attr-defined]


def _cls(module: object, *names: str) -> type:
    """La prima classe esistente tra `names` (il gioco rinomina i modelli dei loader: `LoaderRoom` -> `RoomProto`)."""
    return next(getattr(module, n) for n in names if hasattr(module, n))


def test_loader_schemas_match_game() -> None:
    """I loader YAML (contenuti e definizioni) hanno gli stessi campi e default di quelli del gioco."""
    g_class, g_race = load("character.classes.schema.loader_class"), load("character.race.schema.loader_race")
    g_mob, g_obj, g_room = load("mob.schema.loader_mob"), load("object.schema.loader_object"), load("zone.room.schema.loader_room")
    g_zone = load("zone.schema.loader_zone")

    from pachimudeditor_adapter_pachimud import definitions, loaders

    pairs = [
        (loaders.LoaderZone, g_zone.LoaderZone),
        (loaders.LoaderResetContent, g_zone.LoaderResetContent),
        (loaders.LoaderResetObject, g_zone.LoaderResetObject),
        (loaders.LoaderResetObjectInventory, g_zone.LoaderResetObjectInventory),
        (loaders.LoaderResetMob, g_zone.LoaderResetMob),
        (loaders.LoaderResetDoor, g_zone.LoaderResetDoor),
        (loaders.LoaderReset, g_zone.LoaderReset),
        (loaders.LoaderResetFile, g_zone.LoaderResetFile),
        (loaders.LoaderExit, _cls(g_room, "LoaderExit", "RoomExitProto")),
        (loaders.LoaderExtraDescription, _cls(g_room, "LoaderExtraDescription", "ExtraDescriptionProto")),
        (loaders.LoaderRoom, _cls(g_room, "LoaderRoom", "RoomProto")),
        (loaders.LoaderMob, _cls(g_mob, "LoaderMob", "MobProto")),
        (definitions.LoaderRace, g_race.LoaderRace),
        (definitions.BodyRange, g_race.BodyRange),
        (definitions.RaceBody, g_race.RaceBody),
        (definitions.LoaderClass, g_class.LoaderClass),
        (definitions.ClassTitle, g_class.ClassTitle),
        (definitions.HpGain, g_class.HpGain),
        (definitions.LevelLoss, g_class.LevelLoss),
        (definitions.ClassMana, g_class.ClassMana),
        (definitions.StartHp, g_class.StartHp),
    ]
    for name in (
        "ObjectBaseProto LightProto ScrollProto WandProto WeaponProto ArmorProto ContainerProto DrinkConProto FoodProto MoneyProto "
        "KeyProto AudioProto TrapProto GenericProto"
    ).split():
        pairs.append((getattr(loaders, name), getattr(g_obj, name)))
    for mine, theirs in pairs:
        assert _fields(mine) == _fields(theirs), mine.__name__
    assert set(loaders.TYPE_MODELS) == {t for proto in (g_obj.ObjectBaseProto.__subclasses__()) for t in _literals(proto)}, "tipi oggetto"


def _literals(model: type) -> set[str]:
    """I valori del campo `object_type` (un `Literal`) di un modello di oggetto."""
    from typing import get_args

    return set(get_args(model.model_fields["object_type"].annotation))  # type: ignore[attr-defined]


def test_expected_columns_match_game_models() -> None:
    """Le colonne attese dall'editor (`EXPECTED`) coincidono con quelle dei modelli del MUD vero (nome e nullabilita')."""
    load("account.models")
    load("character.models")
    Base = load("database.base").Base

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

    versions = next(
        (v for v in (game_root() / "src" / "pachimud" / "migrations" / "versions", game_root() / "alembic" / "versions") if v.is_dir()),
        None,
    )
    if versions is None:
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


# ------------------------------------------------------------------------------ definizioni reali


def _adapter(definitions: Path) -> PachimudAdapter:
    """Un adapter (senza DB) sulle `definitions/` indicate."""
    return PachimudAdapter(WorldConfig(id="game", kind="pachimud", params={"definitions_path": str(definitions)}))


def test_real_definitions_load_without_errors() -> None:
    """Le `definitions/` reali del gioco (sola lettura) si caricano: nessun file illeggibile ne' voce non valida."""
    definitions = game_root() / "definitions"
    adapter = _adapter(definitions)
    report = adapter.schema_report()
    assert report is not None and report.problems == [], [p.message for p in report.problems]
    assert report.zones >= 1 and report.rooms >= 1 and report.mobs >= 1 and report.objects >= 1


def test_packaged_classes_and_races_load() -> None:
    """Le classi e le razze di default del gioco (`src/pachimud/definitions`) sono tutte valide per i modelli dell'editor."""
    from pachimudeditor_adapter_pachimud.definitions import read_classes, read_races

    base = game_root() / "src" / "pachimud" / "definitions"
    if not base.is_dir():
        pytest.skip("definizioni di default del gioco non trovate")
    assert len(read_classes(base)) == len(list((base / "classes").glob("*.yaml"))) > 0
    assert len(read_races(base)) == len(list((base / "races").glob("*.yaml"))) > 0


async def test_real_zone_rewrite_is_semantically_identical(tmp_path: Path) -> None:
    """Ogni zona reale, copiata in /tmp e riscritta voce per voce con i suoi stessi valori, ha gli stessi dati (mai l'originale)."""
    source = game_root() / "definitions"
    copy = tmp_path / "definitions"
    shutil.copytree(source, copy, ignore=shutil.ignore_patterns("__pycache__", "*.example"))
    adapter = _adapter(copy)
    before = _snapshot(adapter)
    await _rewrite_everything(adapter)
    assert _snapshot(adapter) == before
    assert adapter.schema_report().problems == []  # type: ignore[union-attr]


async def test_editor_written_files_are_valid_for_the_game(tmp_path: Path) -> None:
    """Scritture dell'editor (creazioni, modifiche, spostamenti) su una copia: tutti i file passano i loader del gioco."""
    definitions = tmp_path / "definitions"
    shutil.copytree(game_root() / "definitions", definitions, ignore=shutil.ignore_patterns("__pycache__", "*.example"))
    shutil.copytree(write_zone(tmp_path / "src" / "Terra"), definitions / "zones" / "Terra")
    adapter = _adapter(definitions)
    await adapter.update_room(8801, RoomPatch(name="Salone", description="Nuova descrizione."))
    await adapter.update_mob(8801, MobPatch(level=9, hp_dice_count=2, hp_bonus=-3, flags=["SENTINEL"]))
    await adapter.update_object(8801, ObjectPatch(extra={"typeFields": {"dice_count": 3}}))
    await adapter.update_exit(8800, 8800 * 10, ExitPatch(description="Cambiata"))
    await _check_with_game_loaders(definitions)
    assert (await adapter.list_rooms(RoomPageParams(zone_id=88))).total == 4
    assert (await adapter.list_mobs(MobPageParams(zone_id=88))).total == 2
    assert (await adapter.list_objects(ObjectPageParams(zone_id=88))).total == 5


async def _check_with_game_loaders(definitions: Path) -> None:
    """Valida ogni file YAML di zona con i loader (Pydantic) del gioco."""
    load_yaml = load("config.loader").load_yaml
    g_zone, g_room = load("zone.schema.loader_zone"), load("zone.room.schema.loader_room")
    g_mob, g_obj = load("mob.schema.loader_mob"), load("object.schema.loader_object")
    models = {
        "zone": g_zone.LoaderZone,
        "room": g_room.LoaderRoomsFile,
        "mob": g_mob.LoaderMobsFile,
        "obj": g_obj.LoaderObjectsFile,
        "reset": g_zone.LoaderResetFile,
    }
    seen = 0
    for path in (definitions / "zones").rglob("*.yaml"):
        prefix = "zone" if path.name == "zone.yaml" else next((p for p in models if path.name.startswith(p)), None)
        if prefix is not None:
            load_yaml(path, models[prefix])
            seen += 1
    assert seen >= 10
    assert yaml.safe_load((definitions / "zones" / "Terra" / "rooms.yaml").read_text(encoding="utf-8"))["rooms"][1]["name"] == "Salone"
