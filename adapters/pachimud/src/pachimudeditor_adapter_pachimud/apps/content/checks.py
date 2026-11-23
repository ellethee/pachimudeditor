"""Controllo dei contenuti: da `file:riga` (come li riporta `content.validate`) alla voce che li contiene, e soglie del lint di stile.
Prefisso `/api/content`.

`content.validate` indica un file del gioco e una riga; l'editor vuole aprire la stanza, il mob o l'oggetto giusti. Qui si risolve
sull'archivio YAML (le righe sono quelle dei file letti dall'editor): la voce e' quella che comincia alla riga piu' vicina prima di `line`.
"""

from pathlib import Path
from typing import Literal

from fastapi import Depends
from pachifast.database import AliasedBaseModel
from pachifast.router_factory import get_router
from pydantic import Field

from pachimudeditor.sdk import require_capability
from pachimudeditor_adapter_pachimud.editor.db import PachimudDep
from pachimudeditor_adapter_pachimud.params import read_game_config
from pachimudeditor_adapter_pachimud.store import YamlStore

router = get_router(name="content", deps=[Depends(require_capability("supports_content_races"))])

DEFAULT_TIME_WORDS = ("giorno", "notte", "pioggia", "neve")
"""Parole che legano una stanza a un'ora o al meteo, se `validate.style.time_words` non le sostituisce (default documentato dal gioco)."""


class LocateQuery(AliasedBaseModel):
    """Un punto di un file: percorso (come lo riporta il gioco) e riga 1-based."""

    file: str | None = None
    """Assente per i problemi che non stanno in un file: la risposta e' `none`."""
    line: int | None = None


class LocateIn(AliasedBaseModel):
    """Richiesta di `POST /checks/locate`."""

    items: list[LocateQuery] = Field(max_length=2000)


class Located(AliasedBaseModel):
    """La voce che contiene un punto di un file."""

    kind: Literal["zone", "room", "mob", "object", "resets", "file", "none"] = "none"
    """`zone` = `zone.yaml`; `resets` = `resets*.yaml`; `file` = file di contenuto senza una voce precisa (riga assente); `none` = file sconosciuto."""
    vnum: int | None = None
    """Vnum della stanza, mob o oggetto (assente per zona, reset, file)."""
    zone_id: int | None = None
    """Vnum della zona che possiede il file."""


class StyleLimits(AliasedBaseModel):
    """Soglie del lint di stile (`validate.style` del `pachimud.yaml` del gioco, altrimenti i default del manuale)."""

    enabled: bool = True
    room_name_max: int = 80
    description_min_lines: int = 3
    description_max_lines: int = 8
    description_width: int = 80
    short_max: int = 40
    long_max: int = 80
    time_words: list[str] = Field(default_factory=lambda: list(DEFAULT_TIME_WORDS))


def locate(store: YamlStore, file: str | None, line: int | None) -> Located:
    """La voce di `file` che contiene `line` (vedi docstring del modulo). Il percorso si cerca prima uguale, poi dal ramo `zones/...`."""
    if not file:
        return Located()
    wanted = Path(file)
    tail = wanted.parts[-3:]
    best: Located | None = None
    for zone in store.zones:
        for yaml_file in (zone.file, *zone.files):
            path = yaml_file.path
            same = path == wanted or path.resolve() == wanted.resolve() or (len(tail) == 3 and path.parts[-3:] == tail and best is None)
            if not same:
                continue
            if yaml_file.kind == "zone":
                return Located(kind="zone", zone_id=zone.vnum)
            if yaml_file.kind == "resets":
                return Located(kind="resets", zone_id=zone.vnum)
            if line is not None:
                inside = [
                    i
                    for items in zone.items.values()
                    for i in items
                    if i.file is yaml_file and (getattr(getattr(i.raw, "lc", None), "line", None) or 0) + 1 <= line
                ]
                if inside:
                    item = max(inside, key=lambda i: i.raw.lc.line)
                    return Located(kind=item.kind, vnum=item.vnum, zone_id=zone.vnum)
            best = Located(kind="file", zone_id=zone.vnum)
    return best or Located()


@router.post("/checks/locate", response_model=list[Located])
async def locate_issues(body: LocateIn, adapter: PachimudDep) -> list[Located]:
    """Per ogni `file:riga` la voce che lo contiene (stanza, mob, oggetto), la zona o `none` se il file non e' dell'editor."""
    store = adapter.sync()
    return [locate(store, q.file, q.line) for q in body.items]


@router.get("/checks/style", response_model=StyleLimits)
async def style_limits(adapter: PachimudDep) -> StyleLimits:
    """Le soglie del lint di stile: `validate.style` del `pachimud.yaml` del mondo (`config_path`) sui default del manuale di Clessidra."""
    path = adapter.params.config_path
    section: dict = {}
    if path is not None:
        try:
            validate = read_game_config(path).get("validate")
            style = validate.get("style") if isinstance(validate, dict) else None
            section = style if isinstance(style, dict) else {}
        except Exception:  # noqa: BLE001 - config illeggibile: valgono i default
            section = {}
    known = {k: v for k, v in section.items() if k in StyleLimits.model_fields}
    try:
        return StyleLimits.model_validate(known)
    except ValueError:  # soglie scritte male nel pachimud.yaml: il gioco le rifiuterebbe, qui valgono i default
        return StyleLimits()
