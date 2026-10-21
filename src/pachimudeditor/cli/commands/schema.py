"""`pachimudeditor schema`: il JSON Schema di `pachimudeditor.yaml`, per completamento e validazione nell'editor."""

from pathlib import Path
from typing import Annotated

import typer
from pachifast.cli.helpers import console, handle_errors

from pachimudeditor.cli.helpers.schema import SCHEMA_NAME, render_schema
from pachimudeditor.cli.helpers.workdir import WorkdirOption, use_workdir


@handle_errors
def schema(
    ctx: typer.Context,
    workdir: WorkdirOption = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Scrive lo schema in questo file ('-' = stdout, default)."),
    ] = None,
    write: Annotated[bool, typer.Option("--write", help=f"Scrive {SCHEMA_NAME} nella cartella di lavoro (come fa `init`).")] = False,
) -> None:
    """Stampa (o scrive) il JSON Schema di `pachimudeditor.yaml`, comprese le chiavi `webeditor_*` e i `params` per kind."""
    text = render_schema()
    if write:
        output = use_workdir(workdir or ctx.obj, must_exist=False) / SCHEMA_NAME
    if output is None or str(output) == "-":
        typer.echo(text, nl=False)
        return
    output.write_text(text, encoding="utf-8")
    console.print(f"Schema scritto in {output}", highlight=False)
