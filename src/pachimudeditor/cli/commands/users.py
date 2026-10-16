"""`pachimudeditor users create|ls|update|delete`: i comandi utenti di pachifast sulla cartella di lavoro."""

import typer
from pachifast.cli.commands import users as pachifast_users

from pachimudeditor.cli.helpers.workdir import WorkdirOption, require_initialized, use_workdir

app = typer.Typer(help="Gestione utenti dell'editor (DB di autenticazione della cartella di lavoro).", no_args_is_help=True)


@app.callback()
def _enter_workdir(ctx: typer.Context, workdir: WorkdirOption = None) -> None:
    """Entra nella cartella di lavoro prima di eseguire il comando di pachifast (che usa `--base-dir .`)."""
    root = use_workdir(workdir or ctx.obj)
    require_initialized(root)


# Delega: gli stessi comandi (e opzioni) di `pachifast users`, eseguiti dalla cartella di lavoro.
app.registered_commands.extend(pachifast_users.app.registered_commands)
