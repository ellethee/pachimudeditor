"""Parametri di un mondo `kind: pachimud`: database di gioco, cartella delle definizioni, config del game server.

Il mondo si configura in `pachimudeditor.yaml` (o `WEBEDITOR_WORLDS`) cosi':

    - id: pachimud
      kind: pachimud
      params:
        database_url: sqlite+aiosqlite:///pachimud.db   # URL SQLAlchemy async (path SQLite relativi: vedi sotto)
        definitions_path: ./definitions                 # races/ classes/ (e zones/ per l'import)
        config_path: /percorso/pachimud.yaml            # facoltativo: ne legge database_url/definition_path

Regole:

- i parametri espliciti (`database_url`, `definitions_path`) vincono sempre su quelli letti da `config_path`;
- `config_path` (anche come chiave diretta del mondo, per compatibilita') e' il `pachimud.yaml` del game server,
  letto con un semplice parser YAML (nessun import di `pachimud`): si usano solo `database_url` e `definition_path`;
  i path relativi li' dentro si risolvono rispetto alla cartella di quel file (e' la cwd del game server);
- i path relativi dei parametri espliciti si risolvono rispetto alla cartella di lavoro (la cartella del
  `pachimudeditor.yaml`, in mancanza la cwd);
- ripiego (documentato, 3 righe): se non c'e' ne' `database_url` ne' `config_path`, si usa la variabile d'ambiente
  `PACHIMUD_CONFIG_PATH` come `config_path`. Senza nulla di tutto cio' il mondo non e' configurato (errore chiaro).
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.engine import make_url

from pachimudeditor.sdk import WorldConfig

CONFIG_ENV_VAR = "PACHIMUD_CONFIG_PATH"
"""Ripiego per `config_path` (vedi docstring del modulo)."""

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///pachimud.db"
DEFAULT_DEFINITIONS = "./definitions"
"""Default di `PachimudConfig` del gioco, usati quando il `pachimud.yaml` non li indica."""

ASYNC_DRIVERS = {"sqlite": "sqlite+aiosqlite", "postgresql": "postgresql+asyncpg", "mysql": "mysql+aiomysql"}
"""Un URL senza driver async viene portato al driver async di default (il mondo usa solo SQLAlchemy async)."""


class PachimudConfigError(ValueError):
    """Parametri del mondo pachimud mancanti o non validi (messaggio pensato per l'utente)."""


@dataclass(frozen=True)
class PachimudParams:
    """Parametri risolti di un mondo pachimud."""

    database_url: str
    """URL SQLAlchemy async, con il path SQLite gia' assoluto."""
    definitions_path: Path | None
    """Cartella `definitions/` (assoluta) o `None` se non configurata (razze/classi/contenuti non disponibili)."""
    config_path: Path | None = None
    """Il `pachimud.yaml` da cui sono stati letti i valori mancanti, se c'e'."""

    @property
    def sqlite_file(self) -> Path | None:
        """Il file del DB se l'URL e' SQLite su file, altrimenti `None`."""
        url = make_url(self.database_url)
        if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
            return None
        return Path(url.database)

    def redacted_url(self) -> str:
        """L'URL senza la password (per log e `worlds check`)."""
        return make_url(self.database_url).render_as_string(hide_password=True)


def base_dir() -> Path:
    """Cartella da cui risolvere i path relativi dei parametri espliciti: quella del `pachimudeditor.yaml`, o la cwd."""
    config = os.environ.get("PACHIFAST_CONFIG_FILE")
    if config and Path(config).expanduser().is_file():
        return Path(config).expanduser().resolve().parent
    return Path.cwd()


def normalize_url(url: str, root: Path) -> str:
    """Porta `url` al driver async e rende assoluto un path SQLite relativo (rispetto a `root`)."""
    try:
        parsed = make_url(url)
    except Exception as exc:  # noqa: BLE001 - qualunque URL malformato
        raise PachimudConfigError(f"database_url non valido: {exc}") from exc
    if parsed.drivername in ASYNC_DRIVERS:
        parsed = parsed.set(drivername=ASYNC_DRIVERS[parsed.drivername])
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:"):
        database = Path(str(parsed.database)).expanduser()
        if not database.is_absolute():
            database = root / database
        parsed = parsed.set(database=str(database))
    return parsed.render_as_string(hide_password=False)


def read_game_config(path: Path) -> dict[str, Any]:
    """Il `pachimud.yaml` del game server come dict (solo lettura, nessuna validazione del gioco).

    Raises:
        PachimudConfigError: se il file manca o non e' una mappa YAML.
    """
    if not path.is_file():
        raise PachimudConfigError(f"config_path non trovato: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 - YAML malformato
        raise PachimudConfigError(f"config_path non leggibile ({path}): {exc}") from exc
    if not isinstance(data, dict):
        raise PachimudConfigError(f"config_path non contiene una mappa YAML: {path}")
    return data


def resolve_params(config: WorldConfig, root: Path | None = None) -> PachimudParams:
    """Risolve i parametri del mondo pachimud (vedi docstring del modulo).

    Raises:
        PachimudConfigError: nessuna sorgente per il database, URL non valido o `config_path` illeggibile.
    """
    root = root or base_dir()
    params = config.params or {}
    explicit_url = params.get("database_url")
    explicit_defs = params.get("definitions_path")
    config_path = params.get("config_path") or config.config_path
    if not explicit_url and not config_path and os.environ.get(CONFIG_ENV_VAR):
        config_path = os.environ[CONFIG_ENV_VAR]

    game_path: Path | None = None
    game: dict[str, Any] = {}
    if config_path:
        game_path = Path(str(config_path)).expanduser()
        if not game_path.is_absolute():
            game_path = root / game_path
        game_path = game_path.resolve()
        game = read_game_config(game_path)

    if explicit_url:
        database_url = normalize_url(str(explicit_url), root)
    elif game_path is not None:
        database_url = normalize_url(str(game.get("database_url") or DEFAULT_DATABASE_URL), game_path.parent)
    else:
        raise PachimudConfigError(
            f"Mondo pachimud {config.id!r} senza database: impostare params.database_url "
            f"(o params.config_path verso il pachimud.yaml del game server)."
        )

    definitions: Path | None = None
    if explicit_defs:
        definitions = Path(str(explicit_defs)).expanduser()
        definitions = definitions if definitions.is_absolute() else root / definitions
    elif game_path is not None:
        definitions = Path(str(game.get("definition_path") or DEFAULT_DEFINITIONS)).expanduser()
        definitions = definitions if definitions.is_absolute() else game_path.parent / definitions
    return PachimudParams(
        database_url=database_url,
        definitions_path=definitions.resolve() if definitions is not None else None,
        config_path=game_path,
    )


def validate_world(config: WorldConfig) -> None:
    """Hook `AdapterPlugin.validate`: alza `PachimudConfigError` (un `ValueError`) se i parametri non bastano ad aprire il database."""
    resolve_params(config)
