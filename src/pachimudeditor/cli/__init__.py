"""CLI `pachimudeditor`: init, serve, users, worlds, adapters, build-frontend, info."""

from typing import Annotated

import typer
from pachifast.cli.helpers import console

from pachimudeditor import __version__
from pachimudeditor.cli.commands import adapters, frontend, info, init, serve, users, worlds
from pachimudeditor.cli.helpers.workdir import WorkdirOption


def _version_callback(value: bool) -> None:
    """Stampa la versione ed esce con `--version`."""
    if value:
        console.print(f"pachimudeditor {__version__}", highlight=False)
        raise typer.Exit()


app = typer.Typer(
    name="pachimudeditor",
    help="Webeditor di pachimud: configura la cartella di lavoro, avvia il server, gestisce utenti e mondi.",
    no_args_is_help=True,
)
app.add_typer(adapters.app, name="adapters")
app.add_typer(users.app, name="users")
app.add_typer(worlds.app, name="worlds")
app.command("init")(init.init)
app.command("serve")(serve.serve)
app.command("info")(info.info)
app.command("build-frontend")(frontend.build_frontend)


@app.callback()
def _root(
    ctx: typer.Context,
    version: Annotated[
        bool | None, typer.Option("--version", callback=_version_callback, is_eager=True, help="Mostra la versione ed esce.")
    ] = None,
    workdir: WorkdirOption = None,
) -> None:
    """Opzioni globali: `--workdir` vale per tutti i comandi (che possono anche ripeterlo)."""
    ctx.obj = workdir


def main() -> None:
    """Entry point della console (`pachimudeditor`)."""
    app()
