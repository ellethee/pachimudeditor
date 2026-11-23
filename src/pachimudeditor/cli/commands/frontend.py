"""`pachimudeditor build-frontend`: solo sviluppo, builda la SPA e la copia in `pachimudeditor/static`."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from pachifast.cli.helpers import console, handle_errors

import pachimudeditor
from pachimudeditor.cli.helpers.workdir import WorkdirOption, find_config_file, use_workdir

BUILD_ENV_PREFIXES = ("QCLI_", "VITE_")
BUILD_ENV_SECTION = "frontend_env"
PACKAGE_DIR = Path(pachimudeditor.__file__).resolve().parent


def find_frontend_dir(explicit: Path | None) -> Path:
    """La cartella `frontend/`: `--frontend-dir`, poi `./frontend`, poi quella accanto a `src/` del checkout.

    Raises:
        typer.BadParameter: se non c'e' (un'installazione da wheel non contiene i sorgenti del frontend).
    """
    candidates = [explicit] if explicit else [Path.cwd() / "frontend", PACKAGE_DIR.parents[1] / "frontend"]
    for candidate in candidates:
        if candidate and (candidate / "package.json").is_file():
            return candidate.resolve()
    raise typer.BadParameter("Cartella frontend non trovata: eseguire dal checkout o passare --frontend-dir.")


def read_build_env(workdir: Path) -> dict[str, str]:
    """Variabili `QCLI_*`/`VITE_*` di build: sezione `frontend_env` di `pachimudeditor.yaml`, poi `.env` della workdir.

    Il frontend le legge SOLO alla build (es. `QCLI_APP_NAVIGATION=sidebar`, `QCLI_APP_THEMES=true`). Le variabili
    gia' nella shell hanno la precedenza su entrambe; il `.env` sulla sezione YAML.
    """
    found: dict[str, str] = {}
    config = find_config_file(workdir)
    if config is not None:
        import yaml  # già dipendenza di pachifast

        section = (yaml.safe_load(config.read_text(encoding="utf-8")) or {}).get(BUILD_ENV_SECTION) or {}
        found.update({str(k): str(v).lower() if isinstance(v, bool) else str(v) for k, v in section.items()})
    env_file = workdir / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key.startswith(BUILD_ENV_PREFIXES):
                found[key.strip()] = value.strip().strip("\"'")
    return {k: v for k, v in found.items() if k.startswith(BUILD_ENV_PREFIXES) and k not in os.environ}


def copy_spa(dist: Path, target: Path) -> None:
    """Sostituisce `target` con la SPA buildata in `dist` (che deve contenere `index.html`)."""
    if not (dist / "index.html").is_file():
        raise typer.BadParameter(f"Build mancante: {dist / 'index.html'} non esiste.")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(dist, target)


@handle_errors
def build_frontend(
    ctx: typer.Context,
    workdir: WorkdirOption = None,
    frontend_dir: Annotated[Path | None, typer.Option("--frontend-dir", help="Cartella dei sorgenti del frontend.")] = None,
    skip_install: Annotated[bool, typer.Option("--skip-install", help="Non eseguire `pnpm install`.")] = False,
) -> None:
    """Esegue `pnpm install` e `pnpm build` nel frontend e copia `dist/spa` in `src/pachimudeditor/static`.

    Le variabili `QCLI_*`/`VITE_*` si leggono dalla shell, dal `.env` e dalla sezione `frontend_env` del YAML della workdir.
    """
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        raise typer.BadParameter("pnpm non trovato nel PATH.")
    root = find_frontend_dir(frontend_dir)
    build_env = read_build_env(use_workdir(workdir or ctx.obj))
    if not skip_install:
        subprocess.run([pnpm, "install", "--frozen-lockfile"], cwd=root, check=True)
    if build_env:
        console.print(f"Variabili di build: {', '.join(sorted(build_env))}", highlight=False)
    subprocess.run([pnpm, "build"], cwd=root, check=True, env={**os.environ, **build_env})
    target = PACKAGE_DIR / "static"
    copy_spa(root / "dist" / "spa", target)
    console.print(f"SPA copiata in {target}", highlight=False)
