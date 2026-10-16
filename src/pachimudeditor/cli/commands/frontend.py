"""`pachimudeditor build-frontend`: solo sviluppo, builda la SPA e la copia in `pachimudeditor/static`."""

import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from pachifast.cli.helpers import console, handle_errors

import pachimudeditor

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


def copy_spa(dist: Path, target: Path) -> None:
    """Sostituisce `target` con la SPA buildata in `dist` (che deve contenere `index.html`)."""
    if not (dist / "index.html").is_file():
        raise typer.BadParameter(f"Build mancante: {dist / 'index.html'} non esiste.")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(dist, target)


@handle_errors
def build_frontend(
    frontend_dir: Annotated[Path | None, typer.Option("--frontend-dir", help="Cartella dei sorgenti del frontend.")] = None,
    skip_install: Annotated[bool, typer.Option("--skip-install", help="Non eseguire `pnpm install`.")] = False,
) -> None:
    """Esegue `pnpm install` e `pnpm build` nel frontend e copia `dist/spa` in `src/pachimudeditor/static`."""
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        raise typer.BadParameter("pnpm non trovato nel PATH.")
    root = find_frontend_dir(frontend_dir)
    if not skip_install:
        subprocess.run([pnpm, "install", "--frozen-lockfile"], cwd=root, check=True)
    subprocess.run([pnpm, "build"], cwd=root, check=True)
    target = PACKAGE_DIR / "static"
    copy_spa(root / "dist" / "spa", target)
    console.print(f"SPA copiata in {target}", highlight=False)
