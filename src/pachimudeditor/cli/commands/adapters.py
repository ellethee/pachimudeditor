"""`pachimudeditor adapters list`: gli adapter (plugin) scoperti e quelli noti ma non installati."""

import typer
from pachifast.cli.helpers import console, handle_errors
from rich.markup import escape
from rich.table import Table

from pachimudeditor.common.adapters.plugins import ENTRY_POINT_GROUP, kind_statuses

app = typer.Typer(help="Adapter (pacchetti dei mondi) installati.", no_args_is_help=True)

_STATE_LABEL = {"installed": "[green]installato[/green]", "broken": "[red]ERRORE[/red]", "missing": "[yellow]non installato[/yellow]"}


@app.command("list")
@handle_errors
def list_adapters() -> None:
    """Elenca i plugin del gruppo `pachimudeditor.adapters`: kind, stato, pacchetto, versione e descrizione.

    Gli adapter ufficiali non installati compaiono con il comando per aggiungerli (es. `pip install 'pachimudeditor[dikumod]'`);
    un plugin che non si importa e' segnalato con l'errore.
    """
    table = Table("kind", "stato", "pacchetto", "versione", "descrizione / come installare")
    for row in kind_statuses():
        detail = row.hint if row.state != "installed" else row.description
        table.add_row(row.kind, _STATE_LABEL[row.state], row.package, row.version, escape(detail))
    console.print(table)
    console.print(f"Gruppo di entry point: {ENTRY_POINT_GROUP}", highlight=False)
