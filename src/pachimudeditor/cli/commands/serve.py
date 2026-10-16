"""`pachimudeditor serve`: avvia uvicorn sulla factory dell'app, con la SPA impacchettata."""

import os
import threading
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
from pachifast.cli.helpers import console, handle_errors
from rich.markup import escape

from pachimudeditor.cli.helpers.workdir import WorkdirOption, require_initialized, use_workdir

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8123
APP_FACTORY = "pachimudeditor.app:create_editor_app"


def resolve_address(host: str | None, port: int | None) -> tuple[str, int]:
    """`(host, porta)`: opzioni, poi `PACHIFAST_HOST`/`PACHIFAST_PORT`, poi sezione `server` del YAML, poi 127.0.0.1:8123."""
    from pachifast.config.yaml_source import load_config_data

    data = load_config_data()
    chosen_host = host or os.environ.get("PACHIFAST_HOST") or data.get("host") or DEFAULT_HOST
    chosen_port = port or int(os.environ.get("PACHIFAST_PORT") or data.get("port") or DEFAULT_PORT)
    return str(chosen_host), chosen_port


@handle_errors
def serve(
    ctx: typer.Context,
    workdir: WorkdirOption = None,
    host: Annotated[str | None, typer.Option("--host", help="Indirizzo (default: config, poi 127.0.0.1).")] = None,
    port: Annotated[int | None, typer.Option("--port", help="Porta (default: config, poi 8123).")] = None,
    reload: Annotated[bool, typer.Option("--reload/--no-reload", help="Riavvio automatico (sviluppo).")] = False,
    open_browser: Annotated[bool, typer.Option("--open", help="Apre il browser sull'editor all'avvio.")] = False,
    log_level: Annotated[str, typer.Option("--log-level", help="Livello di log di uvicorn.")] = "info",
) -> None:
    """Avvia API e frontend sullo stesso processo/porta (default 127.0.0.1:8123)."""
    import uvicorn

    from pachimudeditor.spa import static_dir

    root = use_workdir(workdir or ctx.obj)
    require_initialized(root)
    if static_dir() is None:
        raise typer.BadParameter(
            "Frontend non trovato (pachimudeditor/static/index.html). In un checkout di sviluppo eseguire "
            "`pachimudeditor build-frontend`; un wheel normale lo contiene gia'."
        )
    from pachimudeditor.common.adapters.bootstrap import WorldSetupError, prepare_worlds

    try:
        prepare_worlds()  # errore chiaro prima di avviare uvicorn (poi lo rifa' la factory, idempotente)
    except WorldSetupError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]", highlight=False)
        raise typer.Exit(1) from exc
    bind_host, bind_port = resolve_address(host, port)
    if open_browser:
        url = f"http://{'127.0.0.1' if bind_host in ('0.0.0.0', '::') else bind_host}:{bind_port}/"
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    package_dir = Path(__file__).resolve().parents[2]
    env_file = root / ".env"
    uvicorn.run(
        APP_FACTORY,
        factory=True,
        host=bind_host,
        port=bind_port,
        reload=reload,
        reload_dirs=[str(package_dir)] if reload else None,
        log_level=log_level.lower(),
        proxy_headers=True,
        env_file=str(env_file) if env_file.exists() else None,
    )
