"""`pachimudeditor info`: versioni, cartella di lavoro, file di configurazione e stato del frontend."""

import sys
from importlib.metadata import PackageNotFoundError, version

import typer
from pachifast.cli.helpers import console, handle_errors
from rich.markup import escape

from pachimudeditor.cli.helpers.workdir import PROJECT_MODULES, WorkdirOption, find_config_file, resolve_workdir, use_workdir


def _version(name: str) -> str:
    """Versione installata di un pacchetto, o `non installato`."""
    try:
        return version(name)
    except PackageNotFoundError:
        return "non installato"


@handle_errors
def info(ctx: typer.Context, workdir: WorkdirOption = None) -> None:
    """Mostra versioni, cartella di lavoro, path di configurazione e presenza del frontend (nessun segreto)."""
    from pachimudeditor.common.adapters.plugins import kind_statuses
    from pachimudeditor.common.adapters.registry import load_world_configs
    from pachimudeditor.spa import static_dir

    root = resolve_workdir(workdir or ctx.obj)
    if root.is_dir():
        use_workdir(root)
    try:
        worlds = ", ".join(f"{c.id}({c.kind})" for c in load_world_configs()[0]) or "nessuno (vedi pachimudeditor.yaml)"
    except Exception as exc:  # noqa: BLE001 - info non deve fallire per una config errata
        worlds = f"errore di configurazione: {exc}"
    static = static_dir()
    statuses = kind_statuses()
    installed = ", ".join(f"{r.kind} {r.version}" for r in statuses if r.state == "installed") or "nessuno"
    broken = ", ".join(f"{r.kind} ({r.hint})" for r in statuses if r.state == "broken")
    missing = ", ".join(f"{r.kind} -> pip install 'pachimudeditor[{r.kind}]'" for r in statuses if r.state == "missing")
    rows = {
        "pachimudeditor": _version("pachimudeditor"),
        "pachifast": _version("pachifast"),
        "python": sys.version.split()[0],
        "cartella di lavoro": str(root),
        "inizializzata": "si" if (root / PROJECT_MODULES).is_file() else "no (eseguire `pachimudeditor init`)",
        "pachimudeditor.yaml": str(find_config_file(root) or "assente"),
        ".env": "presente" if (root / ".env").is_file() else "assente",
        "migrations/auth": "presente" if (root / "migrations" / "auth").is_dir() else "assente",
        "adapter installati": installed,
        **({"adapter rotti": broken} if broken else {}),
        **({"adapter non installati": missing} if missing else {}),
        "mondi configurati": worlds,
        "frontend (static)": str(static) if static else "assente (sviluppo: `pachimudeditor build-frontend`)",
    }
    for key, value in rows.items():
        console.print(f"{key:22} {escape(str(value))}", highlight=False)
