"""Parametri di un mondo `kind: pachimud`: cartella delle definizioni (contenuti YAML), database dei giocatori, config del game server.

Il mondo si configura in `pachimudeditor.yaml` (o `WEBEDITOR_WORLDS`) cosi':

    - id: pachimud
      kind: pachimud
      params:
        definitions_path: ./definitions                 # zones/ classes/ races/ (OBBLIGATORIO, o config_path)
        base_definitions_path: ./src/pachimud/definitions  # facoltativo: classi e razze di default del gioco (con config_path: ricavata)
        database_url: sqlite+aiosqlite:///pachimud.db   # facoltativo: account e personaggi (senza, niente giocatori)
        config_path: /percorso/pachimud.yaml            # facoltativo: ne legge database_url/definition_path

Regole:

- i contenuti del gioco (zone, stanze, mob, oggetti, reset, classi, razze) sono file YAML sotto `definitions_path`; nel
  database SQLite restano solo `account` e `player_character`;
- `definition_path` (come nel `pachimud.yaml` del gioco) e' accettato come sinonimo di `definitions_path`;
- i parametri espliciti vincono sempre su quelli letti da `config_path`;
- `config_path` (anche come chiave diretta del mondo, per compatibilita') e' il `pachimud.yaml` del game server,
  letto con un semplice parser YAML (nessun import di `pachimud`): si usano solo `database_url` e `definition_path`;
  i path relativi li' dentro si risolvono rispetto alla cartella di quel file (e' la cwd del game server);
- i path relativi dei parametri espliciti si risolvono rispetto alla cartella di lavoro (la cartella del
  `pachimudeditor.yaml`, in mancanza la cwd);
- ripiego (documentato, 3 righe): se non c'e' ne' `definitions_path` ne' `config_path`, si usa la variabile d'ambiente
  `PACHIMUD_CONFIG_PATH` come `config_path`. Senza nulla di tutto cio' il mondo non e' configurato (errore chiaro).
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.engine import make_url

from pachimudeditor.sdk import WorldConfig
from pachimudeditor_adapter_pachimud.live_config import parse_live_settings

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

    definitions_path: Path
    """Cartella `definitions/` (assoluta): zone, classi e razze."""
    database_url: str | None = None
    """URL SQLAlchemy async dei giocatori, con il path SQLite gia' assoluto; `None` = giocatori non disponibili."""
    config_path: Path | None = None
    """Il `pachimud.yaml` da cui sono stati letti i valori mancanti, se c'e'."""
    ignored_extra_paths: tuple[str, ...] = ()
    """`extra_definition_paths` del `pachimud.yaml` del gioco: l'editor non li legge (solo avviso in `worlds check` e nel log)."""
    base_definitions_path: Path | None = None
    """Contenuti di default del gioco (classi e razze nel pacchetto, `src/pachimud/definitions`): primo strato, sola lettura."""

    @property
    def layers(self) -> tuple[Path, ...]:
        """Le cartelle di classi e razze in ordine di applicazione (la base del gioco, poi `definitions_path`)."""
        return (*([self.base_definitions_path] if self.base_definitions_path else []), self.definitions_path)

    @property
    def sqlite_file(self) -> Path | None:
        """Il file del DB se l'URL e' SQLite su file, altrimenti `None`."""
        if self.database_url is None:
            return None
        url = make_url(self.database_url)
        if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
            return None
        return Path(url.database)

    def redacted_url(self) -> str:
        """Dove vivono i dati del mondo, per log e `worlds check`: le definizioni e, se c'e', il DB dei giocatori senza password."""
        if self.database_url is None:
            return str(self.definitions_path)
        return f"{self.definitions_path} + {make_url(self.database_url).render_as_string(hide_password=True)}"


def base_dir() -> Path:
    """Cartella da cui risolvere i path relativi dei parametri espliciti: quella del `pachimudeditor.yaml`, o la cwd."""
    config = os.environ.get("PACHIFAST_CONFIG_FILE")
    if config and Path(config).expanduser().is_file():
        return Path(config).expanduser().resolve().parent
    return Path.cwd()


def expand_env(url: str) -> str:
    """Espande `${VARIABILE}` dall'ambiente come il gioco (la password non sta nel file) e porta `sslmode=` di libpq a `ssl=` di asyncpg.

    Raises:
        PachimudConfigError: se una variabile non e' impostata (meglio di una password vuota).
    """
    missing = [v for v in re.findall(r"\$\{(\w+)\}", url) if v not in os.environ]
    if missing:
        raise PachimudConfigError(f"variabili d'ambiente mancanti in database_url: {', '.join(missing)}")
    url = re.sub(r"\$\{(\w+)\}", lambda m: os.environ[m.group(1)], url)
    return re.sub(r"([?&])sslmode=", r"\1ssl=", url) if "+asyncpg" in url else url


def normalize_url(url: str, root: Path) -> str:
    """Porta `url` al driver async e rende assoluto un path SQLite relativo (rispetto a `root`)."""
    url = expand_env(url)
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
        PachimudConfigError: nessuna sorgente per le definizioni, URL non valido o `config_path` illeggibile.
    """
    root = root or base_dir()
    params = config.params or {}
    explicit_url = params.get("database_url")
    explicit_defs = params.get("definitions_path") or params.get("definition_path")
    config_path = params.get("config_path") or config.config_path
    if not explicit_defs and not config_path and os.environ.get(CONFIG_ENV_VAR):
        config_path = os.environ[CONFIG_ENV_VAR]

    game_path: Path | None = None
    game: dict[str, Any] = {}
    if config_path:
        game_path = Path(str(config_path)).expanduser()
        if not game_path.is_absolute():
            game_path = root / game_path
        game_path = game_path.resolve()
        game = read_game_config(game_path)

    database_url: str | None = None
    if explicit_url:
        database_url = normalize_url(str(explicit_url), root)
    elif game_path is not None:
        database_url = normalize_url(str(game.get("database_url") or DEFAULT_DATABASE_URL), game_path.parent)

    if explicit_defs:
        definitions = Path(str(explicit_defs)).expanduser()
        definitions = definitions if definitions.is_absolute() else root / definitions
    elif game_path is not None:
        definitions = Path(str(game.get("definition_path") or DEFAULT_DEFINITIONS)).expanduser()
        definitions = definitions if definitions.is_absolute() else game_path.parent / definitions
    else:
        raise PachimudConfigError(
            f"Mondo pachimud {config.id!r} senza definizioni: impostare params.definitions_path "
            f"(o params.config_path verso il pachimud.yaml del game server)."
        )
    base = params.get("base_definitions_path")
    base_path = Path(str(base)).expanduser() if base else (game_path.parent / "src" / "pachimud" / "definitions" if game_path else None)
    if base_path is not None and not base_path.is_absolute():
        base_path = root / base_path
    if base_path is not None and not base_path.is_dir():
        base_path = None
    return PachimudParams(
        definitions_path=definitions.resolve(),
        database_url=database_url,
        config_path=game_path,
        base_definitions_path=base_path.resolve() if base_path else None,
        ignored_extra_paths=tuple(str(p) for p in game.get("extra_definition_paths") or () if p),
    )


def validate_world(config: WorldConfig) -> None:
    """Hook `AdapterPlugin.validate`: alza `PachimudConfigError` (un `ValueError`) se i parametri non bastano a trovare le definizioni."""
    resolve_params(config)
    parse_live_settings(config.params)
