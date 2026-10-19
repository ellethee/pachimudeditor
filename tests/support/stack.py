"""Ambiente di test isolato: database di gioco e di autenticazione temporanei, config e utente.

Usato sia dalla suite pytest sia dal setup e2e (`python -m tests.support.stack <cartella>`).
Non tocca MAI un `pachimud.db` reale: il mondo `pachimud` ha `database_url` assoluto verso un file nella cartella di
lavoro temporanea e `definitions_path` verso una copia delle definizioni di esempio (`tests/fixtures`). Schema e dati
si creano con i modelli copiati del gioco (`pachimudeditor_adapter_pachimud.game_models`): nessun checkout del MUD.
"""

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
"""Radice del repository dell'editor (template di configurazione `pachimudeditor.example.yaml`)."""

DEFINITIONS_FIXTURE = PACKAGE_ROOT / "tests" / "fixtures" / "pachimud_definitions"
"""Definizioni di esempio (razze, classi, zona `RavnFjord`): copia del MUD, vedi il README nella cartella."""

TEST_USER = "e2e-user"
TEST_PASSWORD = "Password-di-test-123"
TEST_SECRET = "x" * 48
"""Segreto di firma dei token: valido solo per i test (nessun segreto reale)."""


def world_params(workdir: Path) -> dict[str, str]:
    """I `params` del mondo pachimud di test: database di gioco e `definitions/` temporanei (mai quelli reali)."""
    return {
        "database_url": f"sqlite+aiosqlite:///{workdir / 'game.db'}",
        "definitions_path": str(workdir / "definitions"),
    }


def current_params() -> dict[str, str]:
    """I `params` del mondo di test gia' impostati da `apply_environment` (dall'ambiente)."""
    return {
        "database_url": os.environ["PACHIMUD_DATABASE_URL"],
        "definitions_path": os.environ["PACHIMUD_DEFINITIONS_PATH"],
    }


def apply_environment(workdir: Path) -> dict[str, str]:
    """Scrive le cartelle temporanee e imposta le variabili d'ambiente verso i DB temporanei.

    Copia `definitions/` (senza `zones/`) nella cartella di lavoro e configura il mondo `pachimud` con parametri
    espliciti (`database_url`, `definitions_path`). Restituisce le variabili impostate (utili per lanciare un
    processo figlio); `PACHIMUD_DATABASE_URL`/`PACHIMUD_DEFINITIONS_PATH` servono allo stack e2e.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    params = world_params(workdir)
    definitions = Path(params["definitions_path"])
    if not definitions.exists():
        shutil.copytree(DEFINITIONS_FIXTURE, definitions, ignore=shutil.ignore_patterns("zones", "README.md"))
    world = {"id": "pachimud", "kind": "pachimud", "name": "Pachimud", "params": params}
    env = {
        "PACHIFAST_CONFIG_FILE": str(PACKAGE_ROOT / "pachimudeditor.example.yaml"),  # locale it, limiti auth: come il vecchio backend/
        "WEBEDITOR_WORLDS": json.dumps([world]),
        "WEBEDITOR_DEFAULT_WORLD": "pachimud",
        "PACHIFAST_AUTH_DATABASE_URL": f"sqlite+aiosqlite:///{workdir / 'auth.db'}",
        "PACHIFAST_SECRET_KEY": TEST_SECRET,
        "PACHIFAST_AUTO_CREATE_AUTH_SCHEMA": "true",
        "PACHIMUD_DATABASE_URL": params["database_url"],
        "PACHIMUD_DEFINITIONS_PATH": params["definitions_path"],
    }
    os.environ.update(env)
    os.environ.pop("PACHIMUD_CONFIG_PATH", None)
    return env


def seed_game_db(workdir: Path) -> None:
    """Ricrea da zero il database di gioco temporaneo con dati minimi.

    Contenuto: zona 10 (range 1000-1099) con stanze 1000/1001 collegate da uscite a doppio senso,
    stanza 1002 isolata con extra description, mob 1000 (usato da un reset) e 1001, oggetto 1000
    (usato da un reset) e 1001; zona 20 vuota (range 2000-2099).
    """
    import pachimudeditor_adapter_pachimud.game_models  # noqa: F401  registra i modelli
    from pachimudeditor_adapter_pachimud.game_models.enums import Sex
    from pachimudeditor_adapter_pachimud.game_models.base import Base
    from pachimudeditor_adapter_pachimud.game_models.mob import MobPrototype
    from pachimudeditor_adapter_pachimud.game_models.enums import ObjectType
    from pachimudeditor_adapter_pachimud.game_models.object import ObjectPrototype
    from pachimudeditor_adapter_pachimud.game_models.enums import ZoneCommandType, ZoneResetMode
    from pachimudeditor_adapter_pachimud.game_models.zone import Zone, ZoneResetCommand
    from pachimudeditor_adapter_pachimud.game_models.enums import Direction, SectorType
    from pachimudeditor_adapter_pachimud.game_models.room import Exit, Room, RoomExtraDescription
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    path = workdir / "game.db"
    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        zone = Zone(
            vnum=10,
            name="Zona Alfa",
            builder="tester",
            bottom_vnum=1000,
            top_vnum=1099,
            min_level=1,
            max_level=10,
            lifespan_minutes=30,
            reset_mode=ZoneResetMode.EMPTY,
            enabled=True,
        )
        empty = Zone(
            vnum=20,
            name="Zona Vuota",
            builder="tester",
            bottom_vnum=2000,
            top_vnum=2099,
            min_level=1,
            max_level=5,
            lifespan_minutes=15,
            reset_mode=ZoneResetMode.NEVER,
            enabled=True,
        )
        s.add_all([zone, empty])
        s.flush()
        r0 = Room(vnum=1000, zone_id=zone.id, name="Piazza", description="Una piazza.", sector_type=SectorType.CITY, flags=[])
        r1 = Room(vnum=1001, zone_id=zone.id, name="Vicolo", description="Un vicolo.", sector_type=SectorType.CITY, flags=["dark"])
        r2 = Room(vnum=1002, zone_id=zone.id, name="Cantina", description="Una cantina.", sector_type=SectorType.INSIDE, flags=[])
        s.add_all([r0, r1, r2])
        s.flush()
        s.add_all(
            [
                Exit(room_id=r0.id, direction=Direction.NORTH, target_room_id=r1.id),
                Exit(room_id=r1.id, direction=Direction.SOUTH, target_room_id=r0.id),
                RoomExtraDescription(room_id=r2.id, keywords="botte", text="Una grossa botte."),
            ]
        )
        common_mob = dict(
            zone_id=zone.id,
            long_description="",
            detailed_description="",
            level=1,
            thac0=20,
            armor_class=0,
            hp_dice_count=1,
            hp_die_size=8,
            hp_bonus=0,
            damage_dice_count=1,
            damage_die_size=4,
            damage_bonus=0,
            gold=0,
            experience=0,
            sex=Sex.NEUTRAL,
            flags=[],
            alignment=0,
            quest_ids=[],
            is_banker=False,
        )
        s.add_all(
            [
                MobPrototype(vnum=1000, keywords="guardia", short_description="una guardia", **common_mob),
                MobPrototype(vnum=1001, keywords="ratto", short_description="un ratto", **common_mob),
            ]
        )
        common_obj = dict(
            zone_id=zone.id,
            long_description="",
            weight=1,
            cost=1,
            rent=0,
            extra_flags=[],
            wear_flags=[],
            affects={},
            object_type=ObjectType.OTHER,
        )
        s.add_all(
            [
                ObjectPrototype(vnum=1000, keywords="spada", short_description="una spada", **common_obj),
                ObjectPrototype(vnum=1001, keywords="sasso", short_description="un sasso", **common_obj),
            ]
        )
        s.add_all(
            [
                ZoneResetCommand(
                    zone_id=zone.id,
                    order_index=0,
                    command_type=ZoneCommandType.LOAD_MOB,
                    if_flag=False,
                    arg1=1000,
                    arg2=1,
                    arg3=1000,
                    arg4=1,
                ),
                ZoneResetCommand(
                    zone_id=zone.id, order_index=1, command_type=ZoneCommandType.LOAD_OBJECT, if_flag=False, arg1=1000, arg2=1, arg3=1000
                ),
            ]
        )
        s.commit()
    engine.dispose()


async def _create_user() -> None:
    """Crea le tabelle del database di autenticazione e l'utente di test."""
    from pachifast.auth.cruds import create_user
    from pachifast.auth.schemas import UserCreate
    from pachifast.config import get_settings
    from pachifast.database.engine import get_core_sessionmaker
    from pachifast.startup import init_db

    get_settings.cache_clear()
    await init_db()
    async with get_core_sessionmaker()() as session:
        await create_user(session, UserCreate(username=TEST_USER, password=TEST_PASSWORD, is_superuser=True))


def create_test_user() -> None:
    """Crea l'utente di test nel database di autenticazione temporaneo (che deve essere nuovo)."""
    asyncio.run(_create_user())


def prepare(workdir: Path) -> dict[str, str]:
    """Prepara tutto: config, DB di gioco seminato, DB auth con utente. Restituisce l'ambiente."""
    env = apply_environment(workdir)
    for suffix in ("", "-wal", "-shm"):
        (workdir / f"auth.db{suffix}").unlink(missing_ok=True)
    seed_game_db(workdir)
    create_test_user()
    return env


if __name__ == "__main__":
    # Uso: python -m tests.support.stack <cartella>  -> stampa le variabili d'ambiente come KEY=VALUE
    for key, value in prepare(Path(sys.argv[1]).resolve()).items():
        print(f"{key}={value}")
