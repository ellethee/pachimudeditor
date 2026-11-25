"""File YAML grezzi delle zone pachimud (`zones/<zona>/zone.yaml`, `rooms*.yaml`, ...): elenco, lettura e scrittura come testo. Prefisso `/api/content/zonefiles`.

Si modificano solo file **esistenti** (niente creazione ne' cancellazione: i file nuovi li crea l'editor delle voci). Il percorso e' valido solo se
coincide con un file YAML che il gioco leggerebbe (e' cercato nell'elenco su disco: nessun `..` o percorso esterno passa). Prima di scrivere il testo
si legge come YAML (422 `pachimud.yaml_invalid`, riga e colonna) e si valida con gli stessi modelli del gioco (422 `pachimud.zonefile_invalid`, campo e
riga): se non e' valido non si scrive nulla. Un testo identico a quello su disco non riscrive il file. Dopo la scrittura la cache dell'archivio e'
invalidata: la lettura successiva (zone, stanze, mob...) rilegge i file dal disco.
"""

import hashlib
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, Path as PathParam
from pachifast.database import AliasedBaseModel
from pachifast.i18n import api_error
from pachifast.router_factory import get_router
from pydantic import ValidationError
from ruamel.yaml.error import YAMLError

from pachimudeditor.sdk import require_capability
from pachimudeditor_adapter_pachimud.apps.content.files_store import MAX_BYTES
from pachimudeditor_adapter_pachimud.editor.db import PachimudDep, ReadOnlyGuard
from pachimudeditor_adapter_pachimud.loaders import LoaderResetFile, LoaderZone, validate_entry
from pachimudeditor_adapter_pachimud.store import LIST_KEY, PREFIX, FileKind, YamlStore, new_yaml, plain, write_text_atomic

router = get_router(name="content", deps=[Depends(require_capability("supports_content_races")), ReadOnlyGuard])

SCHEMA_OF: dict[str, str] = {"zone": "zone", "rooms": "rooms", "mobs": "mobs", "objects": "objects", "resets": "resets"}
"""Tipo di file -> nome dello schema di `GET /content/schemas/{name}`."""
MAX_ISSUES = 20
"""Violazioni riportate al massimo in una risposta 422."""


class ZoneFileEntry(AliasedBaseModel):
    """Un file YAML di zona: percorso relativo a `zones/` (`<cartella>/<file>`), cartella, tipo, schema, dimensione e impronta."""

    path: str
    zone: str
    name: str
    kind: str
    schema_name: str
    size: int
    etag: str


class ZoneFileContent(ZoneFileEntry):
    """Un file con il suo testo."""

    text: str


class ZoneFileBody(AliasedBaseModel):
    """Il testo da scrivere; `etag` (facoltativo) e' quello letto: se il file e' cambiato nel frattempo 409 `pachimud.zonefile_changed`."""

    text: str
    etag: str | None = None


ZonePath = Annotated[str, PathParam(description="percorso relativo a `zones/`, es. `ZonaAlfa/mobs.yaml`")]


def _etag(data: bytes) -> str:
    """Impronta del contenuto (sha1 abbreviata)."""
    return hashlib.sha1(data).hexdigest()[:16]  # noqa: S324 - solo impronta di cambiamento, non sicurezza


def _entry(store: YamlStore, path: Path, kind: FileKind, data: bytes) -> dict[str, Any]:
    rel = path.relative_to(store.root)
    return {
        "path": rel.as_posix(),
        "zone": rel.parts[0],
        "name": path.name,
        "kind": kind,
        "schema_name": SCHEMA_OF[kind],
        "size": len(data),
        "etag": _etag(data),
    }


def _resolve(store: YamlStore, rel: str) -> tuple[Path, FileKind]:
    """Il file `rel` se e' fra quelli che il gioco legge (404 `pachimud.zonefile_not_found` altrimenti)."""
    for path, kind in store.files_on_disk().items():
        if path.relative_to(store.root).as_posix() == rel:
            return path, kind
    raise api_error(404, "pachimud.zonefile_not_found", path=rel)


def _line_of(doc: Any, loc: tuple[Any, ...]) -> int | None:
    """La riga (1-based) del valore a `loc` nel documento ruamel; se il percorso non esiste piu', quella dell'ultimo nodo trovato."""
    node, line = doc, getattr(getattr(doc, "lc", None), "line", None)
    for part in loc:
        try:
            line = node.lc.item(part)[0]
            node = node[part]
        except KeyError, IndexError, TypeError, AttributeError:
            break
    return None if line is None else line + 1


def _issue(doc: Any, error: ValidationError, prefix: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Le violazioni di un `ValidationError` come `{field, line, message}`; `prefix` e' il percorso della voce nel documento."""
    out = []
    for e in error.errors():
        loc = prefix + tuple(e["loc"])
        field = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in loc).lstrip(".")
        out.append({"field": field, "line": _line_of(doc, loc), "message": str(e["msg"]).removeprefix("Value error, ")})
    return out


def _check(kind: FileKind, text: str) -> None:
    """Legge il testo come YAML e lo valida come file di tipo `kind` (stessi modelli del gioco); 422 se non va."""
    try:
        doc = new_yaml().load(text)
    except YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        where = f"riga {mark.line + 1}, colonna {mark.column + 1}: " if mark is not None else ""
        raise api_error(
            422, "pachimud.yaml_invalid", detail=f"{where}{getattr(error, 'problem', None) or 'YAML non valido'}",
            line=None if mark is None else mark.line + 1, column=None if mark is None else mark.column + 1,
        ) from error  # fmt: skip
    if doc is None:
        doc = {}
    issues: list[dict[str, Any]] = []
    if not isinstance(doc, dict):
        issues.append({"field": "", "line": 1, "message": "il file deve contenere una mappa YAML"})
    elif kind in ("zone", "resets"):
        try:
            (LoaderZone if kind == "zone" else LoaderResetFile).model_validate(plain(doc))
        except ValidationError as error:
            issues += _issue(doc, error)
    else:
        key = LIST_KEY[kind]
        entries = doc.get(key)
        if entries is None:
            pass
        elif not isinstance(entries, list):
            issues.append({"field": key, "line": _line_of(doc, (key,)), "message": f"«{key}» deve essere una lista"})
        else:
            for index, raw in enumerate(entries):
                if not isinstance(raw, dict):
                    issues.append({"field": f"{key}[{index}]", "line": _line_of(doc, (key, index)), "message": "la voce non e' una mappa"})
                    continue
                try:
                    validate_entry(PREFIX[{"rooms": "room", "mobs": "mob", "objects": "object"}[kind]], plain(raw))
                except ValidationError as error:
                    issues += _issue(doc, error, (key, index))
    if issues:
        first = issues[0]
        where = f"riga {first['line']}, " if first["line"] else ""
        what = f"{first['field']}: " if first["field"] else ""
        extra = f" (e altri {len(issues) - 1})" if len(issues) > 1 else ""
        raise api_error(
            422, "pachimud.zonefile_invalid", detail=f"{where}{what}{first['message']}{extra}", line=first["line"], field=first["field"], issues=issues[:MAX_ISSUES]
        )  # fmt: skip


@router.get("/zonefiles", response_model=list[ZoneFileEntry])
async def list_zone_files(adapter: PachimudDep) -> list[dict[str, Any]]:
    """I file YAML delle zone (anche quelli rotti), per percorso."""
    store = adapter.sync()
    return [_entry(store, p, k, p.read_bytes()) for p, k in store.files_on_disk().items()]


@router.get("/zonefiles/{rel:path}", response_model=ZoneFileContent)
async def get_zone_file(rel: ZonePath, adapter: PachimudDep) -> dict[str, Any]:
    """Il testo di un file di zona. 404 `pachimud.zonefile_not_found`."""
    store = adapter.sync()
    path, kind = _resolve(store, rel)
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise api_error(422, "content.invalid", detail="il file non e' UTF-8") from error
    return {**_entry(store, path, kind, data), "text": text}


@router.put("/zonefiles/{rel:path}", response_model=ZoneFileContent)
async def put_zone_file(rel: ZonePath, body: ZoneFileBody, adapter: PachimudDep) -> dict[str, Any]:
    """Valida e scrive il testo di un file di zona esistente (atomico; un testo identico non riscrive nulla)."""
    if len(body.text.encode("utf-8")) > MAX_BYTES:
        raise api_error(422, "content.too_large", max=MAX_BYTES // 1024)
    async with adapter.writing() as store:
        path, kind = _resolve(store, rel)
        old = path.read_bytes()
        if body.etag is not None and body.etag != _etag(old):
            raise api_error(409, "pachimud.zonefile_changed", path=rel)
        _check(kind, body.text)
        if body.text.encode("utf-8") != old:
            write_text_atomic(path, body.text)
            store.invalidate()
        new = path.read_bytes()
    return {**_entry(store, path, kind, new), "text": body.text}
