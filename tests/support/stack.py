"""Ambiente di test isolato: database di gioco e di autenticazione temporanei, config e utente.

Usato sia dalla suite pytest sia dal setup e2e (`python -m tests.support.stack <cartella>`).
Non tocca MAI un `pachimud.db` reale: il mondo `pachimud` ha `database_url` assoluto verso un file nella cartella di
lavoro temporanea e `definitions_path` verso una copia delle definizioni di esempio (`tests/fixtures`). I contenuti sono file
YAML scritti qui (`write_world`); il DB dei giocatori si crea con i modelli copiati del gioco
(`pachimudeditor_adapter_pachimud.game_models`): nessun checkout del MUD.
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
    if not (definitions / "races").exists():  # `seed_game_db` puo' aver gia' creato `zones/`
        shutil.copytree(DEFINITIONS_FIXTURE, definitions, ignore=shutil.ignore_patterns("zones", "README.md"), dirs_exist_ok=True)
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


ZONE_ALFA = {
    "zone.yaml": """\
zone_id: zona_alfa
vnum: 10
name: Zona Alfa
builder: tester
bottom_vnum: 1000
top_vnum: 1099
min_level: 1
max_level: 10
lifespan_minutes: 30
reset_mode: EMPTY
enabled: true
""",
    "rooms.yaml": """\
rooms:
  # la piazza e il vicolo sono collegati a doppio senso
  - vnum: 1000
    name: Piazza
    description: Una piazza.
    sector_type: CITY
    exits:
      north:
        target_vnum: 1001
  - vnum: 1001
    name: Vicolo
    description: Un vicolo.
    sector_type: CITY
    flags:
      - dark
    exits:
      south:
        target_vnum: 1000
  - vnum: 1002
    name: Cantina
    description: Una cantina.
    sector_type: INSIDE
    extra_descriptions:
      - keywords: botte
        text: Una grossa botte.
""",
    "mobs.yaml": """\
mobs:
  - vnum: 1000
    keywords: guardia
    short_description: una guardia
    long_description: ""
    detailed_description: ""
    level: 1
    thac0: 20
    armor_class: 0
    hp_dice: 1d8+0
    damage_dice: 1d4+0
  - vnum: 1001
    keywords: ratto
    short_description: un ratto
    long_description: ""
    detailed_description: ""
    level: 1
    thac0: 20
    armor_class: 0
    hp_dice: 1d8+0
    damage_dice: 1d4+0
""",
    "objects.yaml": """\
objects:
  - vnum: 1000
    keywords: spada
    short_description: una spada
    long_description: ""
    object_type: OTHER
    weight: 1
    cost: 1
  - vnum: 1001
    keywords: sasso
    short_description: un sasso
    long_description: ""
    object_type: OTHER
    weight: 1
    cost: 1
""",
    "resets.yaml": """\
resets:
  objects:
    - obj_vnum: 1000
      max_existing: 1
      room_vnum: 1000
      room_limit: 1
  mobs:
    - mob_vnum: 1000
      max_existing: 1
      room_vnum: 1000
      room_limit: 1
""",
}
"""La zona 10 «Zona Alfa» (range 1000-1099): stanze 1000/1001 collegate a doppio senso, 1002 isolata con extra description,
mob 1000 (usato da un reset) e 1001, oggetto 1000 (usato da un reset) e 1001. Script di reset: `O 1000 -> 1000`, `M 1000 -> 1000`."""

ZONE_VUOTA = {
    "zone.yaml": """\
zone_id: zona_vuota
vnum: 20
name: Zona Vuota
builder: tester
bottom_vnum: 2000
top_vnum: 2099
min_level: 1
max_level: 5
lifespan_minutes: 15
reset_mode: NEVER
enabled: true
"""
}
"""La zona 20 «Zona Vuota» (range 2000-2099), senza contenuto."""


def write_world(definitions: Path) -> None:
    """Scrive (sostituendola) la cartella `zones/` del mondo di test: `ZonaAlfa` e `ZonaVuota`."""
    zones = definitions / "zones"
    shutil.rmtree(zones, ignore_errors=True)
    for folder, files in (("ZonaAlfa", ZONE_ALFA), ("ZonaVuota", ZONE_VUOTA)):
        (zones / folder).mkdir(parents=True)
        for name, text in files.items():
            (zones / folder / name).write_text(text, encoding="utf-8")


def zones_dir() -> Path:
    """La cartella `zones/` del mondo di test in uso (da `PACHIMUD_DEFINITIONS_PATH`)."""
    return Path(os.environ["PACHIMUD_DEFINITIONS_PATH"]) / "zones"


def edit_world_file(relative: str, old: str, new: str) -> None:
    """Sostituisce `old` con `new` nel file YAML `zones/<relative>` del mondo di test (ne verifica la presenza)."""
    path = zones_dir() / relative
    text = path.read_text(encoding="utf-8")
    assert old in text, (relative, old)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def write_world_file(relative: str, text: str) -> None:
    """Scrive (creando le cartelle) il file `zones/<relative>` del mondo di test."""
    path = zones_dir() / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def seed_game_db(workdir: Path) -> None:
    """Ricrea da zero il mondo di prova: contenuti YAML (`write_world`) e database dei giocatori (solo `account` e
    `player_character`, vuote: i test che servono dei giocatori li inseriscono)."""
    import pachimudeditor_adapter_pachimud.game_models  # noqa: F401  registra i modelli
    from pachimudeditor_adapter_pachimud.game_models.base import Base
    from sqlalchemy import create_engine

    write_world(Path(world_params(workdir)["definitions_path"]))
    path = workdir / "game.db"
    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
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
