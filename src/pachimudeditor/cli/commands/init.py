"""`pachimudeditor init`: prepara la cartella di lavoro (config, `.env`, DB auth con migration, primo superuser)."""

from pathlib import Path
from typing import Annotated

import typer
from pachifast.cli.helpers import console, handle_errors

from pachimudeditor.cli.helpers.templates import PROJECT_MODULES_SOURCE, render_config
from pachimudeditor.cli.helpers.workdir import (
    CONFIG_NAMES,
    PROJECT_MODULES,
    WorkdirOption,
    find_config_file,
    use_workdir,
)


def _write_if_missing(path: Path, content: str) -> bool:
    """Scrive `content` in `path` solo se non esiste (mai sovrascrive); `True` se l'ha creato."""
    if path.exists():
        return False
    path.write_text(content, encoding="utf-8")
    return True


@handle_errors
def init(
    ctx: typer.Context,
    workdir: WorkdirOption = None,
    username: Annotated[str, typer.Option("--username", "-u", help="Username del primo superuser.")] = "admin",
    password: Annotated[str | None, typer.Option("--password", help="Password del superuser (se omessa viene chiesta).")] = None,
    email: Annotated[str | None, typer.Option("--email", help="Email del superuser.")] = None,
    database_url: Annotated[
        str | None,
        typer.Option("--database-url", help="URL del DB di autenticazione (default: SQLite db.sqlite3 nella cartella)."),
    ] = None,
    no_user: Annotated[bool, typer.Option("--no-user", help="Non creare il superuser (utile rieseguendo init).")] = False,
) -> None:
    """Prepara la cartella di lavoro: `pachimudeditor.yaml`, `.env`, DB di autenticazione e primo superuser.

    Idempotente: file, valori di `.env`, migration e utenti esistenti non vengono toccati. Le migration dell'auth
    vengono generate NELLA cartella di lavoro (`migrations/auth/`), quindi funziona anche da un wheel installato.
    """
    from pachifast.cli.services.init import init_project

    root = use_workdir(workdir or ctx.obj, must_exist=False)
    if not no_user and password is None:
        password = typer.prompt(f"Password per {username}", hide_input=True, confirmation_prompt=True)

    created = []
    if _write_if_missing(root / PROJECT_MODULES, PROJECT_MODULES_SOURCE):
        created.append(PROJECT_MODULES)
    if find_config_file(root) is None and _write_if_missing(
        root / CONFIG_NAMES[0],
        render_config(),
    ):
        created.append(CONFIG_NAMES[0])
        use_workdir(root)  # ora il file c'e': pachifast lo legge
    report = init_project(
        base_dir=str(root),
        username=username,
        password=password,
        email=email,
        database_url=database_url,
        create_user=not no_user,
    )

    console.print(f"Cartella di lavoro: {root}", highlight=False)
    for name in created:
        console.print(f"Creato {name}", highlight=False)
    console.print(f"{'Creato' if report.env_created else 'Mantenuto'} {report.env_file}", highlight=False)
    console.print("Migration dell'auth applicate (target 'auth').", highlight=False)
    if report.username:
        console.print(
            f"{'Creato superuser' if report.user_created else 'Superuser gia' + chr(39) + ' presente:'} {report.username}",
            highlight=False,
        )
    console.print(f"Avvio: pachimudeditor serve --workdir {root}", highlight=False)
