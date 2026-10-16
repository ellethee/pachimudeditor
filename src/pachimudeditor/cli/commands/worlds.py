"""`pachimudeditor worlds list|check`: i mondi configurati, senza avviare il server."""

import asyncio
from pathlib import Path
from typing import Any

import typer
from pachifast.cli.helpers import console, handle_errors
from rich.markup import escape
from rich.table import Table

from pachimudeditor.cli.helpers.workdir import WorkdirOption, use_workdir

app = typer.Typer(help="Mondi (MUD) configurati nell'editor.", no_args_is_help=True)


def _load_registry():  # type: ignore[no-untyped-def]
    """Il registro dei mondi dalla configurazione (i `kind` arrivano dai plugin installati)."""
    from pachimudeditor.common.adapters.bootstrap import WorldSetupError, prepare_worlds
    from pachimudeditor.common.adapters.registry import WorldRegistry

    try:
        configs, default = prepare_worlds()
    except WorldSetupError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]", highlight=False)
        raise typer.Exit(1) from exc
    return WorldRegistry(configs, default)


def _kinds_summary() -> None:
    """Una riga con i kind utilizzabili e quelli ufficiali non installati (con l'extra da installare)."""
    from pachimudeditor.common.adapters.plugins import kind_statuses

    rows = kind_statuses()
    console.print(escape("Kind disponibili: " + (", ".join(r.kind for r in rows if r.state == "installed") or "nessuno")), highlight=False)
    missing = [f"{r.kind} ({r.hint})" for r in rows if r.state == "missing"]
    if missing:
        console.print(escape("Kind non installati: " + "; ".join(missing)), highlight=False)
    for r in rows:
        if r.state == "broken":
            console.print(f"[red]{escape(f'Kind {r.kind} non utilizzabile: {r.hint}')}[/red]", highlight=False)


def _where(adapter: Any, config: Any) -> str:
    """Dove vivono i dati del mondo: `path`, oppure (pachimud) l'URL del database senza password."""
    params = getattr(adapter, "params", None)
    return params.redacted_url() if params is not None else (config.path or "-")


def _caps(info: Any) -> str:
    """Le capability attive dell'adapter in forma compatta."""
    names = [n.removeprefix("supports_") for n, v in info.capabilities.model_dump().items() if v is True and n != "read_only"]
    return ",".join(names) or "-"


@app.callback()
def _enter_workdir(ctx: typer.Context, workdir: WorkdirOption = None) -> None:
    """Entra nella cartella di lavoro (config e `.env`)."""
    use_workdir(workdir or ctx.obj)


@app.command("list")
@handle_errors
def list_worlds() -> None:
    """Elenca i mondi: id, kind, capability, sola lettura (nessun accesso ai dati)."""
    registry = _load_registry()
    if not registry.world_ids:
        console.print("Nessun mondo configurato: aggiungere webeditor_worlds in pachimudeditor.yaml.", highlight=False)
        _kinds_summary()
        return
    table = Table("id", "kind", "nome", "sola lettura", "capability", "default")
    for info in registry.describe_all():
        table.add_row(
            info.id, info.kind, info.name, "si" if info.capabilities.read_only else "no", _caps(info), "*" if info.default else ""
        )
    console.print(table)
    _kinds_summary()


async def _probe(registry: Any, world_id: str) -> tuple[bool, str]:
    """Conta le zone del mondo (apre davvero il dato): `(ok, dettaglio)`. Per i mondi con un controllo di schema
    (pachimud) il dettaglio riporta anche revisione e stato dello schema."""
    from pachimudeditor.common.adapters.models import ZonePageParams

    adapter = registry.get(world_id)
    try:
        page = await adapter.list_zones(ZonePageParams(page=1, page_size=1))
    except Exception as exc:  # noqa: BLE001 - il check riporta qualunque errore di caricamento
        reason = getattr(adapter, "unavailable_reason", lambda: None)()
        detail = getattr(exc, "detail", None)
        text = reason or (detail[0].get("message") if isinstance(detail, list) and detail else None) or f"{type(exc).__name__}: {exc}"
        return False, str(text)
    report = getattr(adapter, "schema_report", lambda: None)()
    return True, f"{page.total} zone" + (f"; {report.summary()}" if report is not None else "")


def _schema_warnings(registry: Any, world_ids: list[str]) -> list[str]:
    """Gli avvisi del controllo di schema dei mondi che lo prevedono: righe `mondo: [codice] messaggio`."""
    lines: list[str] = []
    for world_id in world_ids:
        report = getattr(registry.get(world_id), "schema_report", lambda: None)()
        if report is not None:
            lines += [f"{world_id}: [{i.code}] {i.message}" for i in report.warnings]
    return lines


@app.command("check")
@handle_errors
def check_worlds() -> None:
    """Carica ogni mondo e ne verifica la salute: path esistente e numero di zone/aree. Esce con 1 se qualcuno fallisce."""
    from pachimudeditor.common.adapters.registry import WorldConfig  # noqa: F401

    registry = _load_registry()
    if not registry.world_ids:
        console.print("Nessun mondo configurato: aggiungere webeditor_worlds in pachimudeditor.yaml.", highlight=False)
        _kinds_summary()
        raise typer.Exit(1)
    configs = registry._configs  # noqa: SLF001 - sola lettura dei path configurati
    infos = registry.describe_all()
    missing = {i.id: [p for p in (configs[i.id].path, configs[i.id].mapping) if p and not Path(p).expanduser().exists()] for i in infos}

    async def probe_all() -> dict[str, tuple[bool, str]]:
        """Un solo event loop per tutti i mondi (gli engine async non migrano tra loop)."""
        return {i.id: await _probe(registry, i.id) for i in infos if not missing[i.id]}

    results = asyncio.run(probe_all())
    table = Table("id", "kind", "path", "esito", "dettaglio")
    failed = False
    for info in infos:
        ok, detail = results.get(info.id, (False, f"path inesistente: {', '.join(missing[info.id])}"))
        failed |= not ok
        table.add_row(
            info.id, info.kind, _where(registry.get(info.id), configs[info.id]), "[green]ok[/green]" if ok else "[red]ERRORE[/red]", detail
        )
    console.print(table)
    _kinds_summary()
    for line in _schema_warnings(registry, [i.id for i in infos]):
        console.print(f"[yellow]avviso[/yellow] {line}", highlight=False)
    if failed:
        raise typer.Exit(1)
