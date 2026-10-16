"""Cartella di lavoro dell'editor: `.env`, `pachimudeditor.yaml`, DB di autenticazione e migration.

Risoluzione della cartella: opzione `--workdir`, poi variabile `PACHIMUDEDITOR_WORKDIR`, poi la cartella corrente.
Configurazione (priorita' decrescente): variabili d'ambiente (`PACHIFAST_*`, `WEBEDITOR_*`/`PACHIMUDEDITOR_*`),
`.env` della cartella, `pachimudeditor.yaml`, default. Il file YAML e' quello letto da pachifast tramite
`PACHIFAST_CONFIG_FILE`, che `use_workdir` imposta se non e' gia' definita.
"""

import os
from pathlib import Path
from typing import Annotated

import typer

WORKDIR_ENV = "PACHIMUDEDITOR_WORKDIR"
CONFIG_ENV = "PACHIFAST_CONFIG_FILE"
CONFIG_NAMES = ("pachimudeditor.yaml", "pachimudeditor.yml", "pachifast.yaml", "pachifast.yml")
"""Nomi cercati nella cartella di lavoro; gli ultimi due per compatibilita' con il vecchio `backend/`."""
PROJECT_MODULES = "project_modules.py"
"""File che i comandi di pachifast (`users`, `migrations`) cercano nella cartella di progetto."""

WorkdirOption = Annotated[
    Path | None,
    typer.Option(
        "--workdir",
        "-w",
        help="Cartella di lavoro (.env, pachimudeditor.yaml, DB auth). Default: $PACHIMUDEDITOR_WORKDIR o la cartella corrente.",
    ),
]


def resolve_workdir(workdir: Path | None = None) -> Path:
    """Path assoluto della cartella di lavoro (non verifica che esista)."""
    chosen = workdir or (Path(os.environ[WORKDIR_ENV]) if os.environ.get(WORKDIR_ENV) else Path.cwd())
    return chosen.expanduser().resolve()


def find_config_file(workdir: Path) -> Path | None:
    """Il file di configurazione YAML della cartella (`PACHIFAST_CONFIG_FILE` ha la precedenza), se esiste."""
    explicit = os.environ.get(CONFIG_ENV)
    if explicit:
        return Path(explicit).expanduser()
    return next((workdir / name for name in CONFIG_NAMES if (workdir / name).is_file()), None)


def use_workdir(workdir: Path | None = None, *, must_exist: bool = True) -> Path:
    """Entra nella cartella di lavoro e punta pachifast al suo YAML.

    pachifast legge `.env` e i path relativi dalla cartella corrente, quindi il processo ci si sposta.

    Raises:
        typer.BadParameter: se la cartella non esiste e `must_exist` e' vero.
    """
    root = resolve_workdir(workdir)
    if not root.is_dir():
        if must_exist:
            raise typer.BadParameter(f"La cartella di lavoro non esiste: {root} (crearla con `pachimudeditor init`).")
        root.mkdir(parents=True)
    os.chdir(root)
    config = find_config_file(root)
    if config is not None and CONFIG_ENV not in os.environ:
        os.environ[CONFIG_ENV] = str(config)
    return root


def require_initialized(root: Path) -> None:
    """Verifica che `init` sia stato eseguito (shim dei moduli presente).

    Raises:
        typer.BadParameter: con il suggerimento di eseguire `pachimudeditor init`.
    """
    if not (root / PROJECT_MODULES).is_file():
        raise typer.BadParameter(
            f"{root} non e' una cartella di lavoro inizializzata ({PROJECT_MODULES} mancante): "
            f"eseguire `pachimudeditor init --workdir {root}`."
        )
