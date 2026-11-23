"""Contenuti YAML «a strati» oltre razze e classi: skill, tabelle, social, cataloghi dei messaggi e testi lunghi.

Il gioco legge `src/pachimud/definitions` (strato di base, sola lettura per l'editor), poi `definition_path` (strato dell'utente): a parita'
di id (o di nome file) vince l'ultimo. L'editor **scrive solo nello strato dell'utente** (`params.definitions_path`): modificare un elemento
che esiste solo nella base ne crea la copia nello strato dell'utente, eliminarlo dallo strato dell'utente ripristina quello di base.
I file si modificano con `ruamel.yaml` in round-trip (commenti salvi) e si scrivono in modo atomico; i percorsi sono validati (niente `..`).
La validazione semantica completa e' del gioco (`content.validate` di livectl): qui si controlla solo che il YAML si legga.
"""

import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from pachifast.i18n import api_error
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import YAMLError

from pachimudeditor_adapter_pachimud.apps.content.yaml_store import ID_PATTERN, new_yaml, plain

MAX_BYTES = 512 * 1024
"""Dimensione massima di un file di contenuti salvabile dall'editor."""

# area -> (cartella, estensione). `tables` esclude i social (hanno una pagina propria).
AREAS: dict[str, tuple[str, str]] = {"tables": ("tables", ".yaml"), "locales": ("locales", ".yaml"), "texts": ("texts", ".txt")}
_PATH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*(/[A-Za-z0-9_][A-Za-z0-9_.\-]*)*$")

SOCIAL_KEYS: tuple[str, ...] = (
    "no_arg", "others_no_arg", "found", "others_found", "victim_found", "not_found", "auto", "others_auto",
)  # fmt: skip
"""Chiavi dei testi di un social (docs/contenuti.md del gioco)."""

SKILL_SCALARS: tuple[str, ...] = (
    "kind", "name", "description", "disabled", "mana", "beats", "fail", "min_position", "violent", "max_learn", "saving", "element", "targets", "item_types",
)  # fmt: skip
"""Campi semplici di una skill (form); gli altri (`levels`, `effects`, `messages`, ...) si modificano come YAML."""
ITEM_TYPES: tuple[str, ...] = ("potion", "scroll", "wand", "staff", "ointment")
"""Oggetti in cui puo' stare un incantesimo (valori di `item_types`)."""


@dataclass(frozen=True)
class Layers:
    """Gli strati di contenuti di un mondo: `roots[-1]` e' quello dell'utente (scrivibile), gli altri sono la base del gioco."""

    roots: tuple[Path, ...]

    @property
    def user(self) -> Path:
        """Lo strato dell'utente (`definitions_path`)."""
        return self.roots[-1]


# --- file YAML: lettura/scrittura --------------------------------------------------------------------------------------------


def load_yaml(text: str) -> Any:
    """Legge un YAML (round-trip); un errore diventa 422 `content.invalid` con riga e colonna."""
    try:
        return new_yaml().load(text)
    except YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        where = f"riga {mark.line + 1}, colonna {mark.column + 1}: " if mark is not None else ""
        problem = getattr(error, "problem", None) or "YAML non valido"
        raise api_error(422, "content.invalid", detail=f"{where}{problem}") from error


def dump_yaml(document: Any, *, explicit_start: bool = False) -> str:
    """Il testo YAML di un documento round-trip."""
    stream = StringIO()
    new_yaml(explicit_start=explicit_start).dump(document, stream)
    return stream.getvalue()


def atomic_write(path: Path, text: str) -> None:
    """Scrive `text` (UTF-8) in modo atomico, creando le cartelle; permessi del file esistente, altrimenti 0644."""
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise api_error(422, "content.too_large", max=MAX_BYTES // 1024)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.chmod(temp, path.stat().st_mode & 0o777 if path.exists() else 0o644)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def read_text(path: Path) -> str:
    """Legge un file UTF-8; non decodificabile -> 422 `content.invalid`."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise api_error(422, "content.invalid", detail="il file non e' UTF-8") from error


# --- file generici (tables, locales, texts) --------------------------------------------------------------------------------


def _safe(layers_root: Path, area: str, rel: str) -> Path:
    """Il percorso `<root>/<area>/<rel>` se `rel` e' ammesso (forma, estensione, dentro la cartella dell'area), altrimenti 422."""
    directory, suffix = AREAS[area]
    base = (layers_root / directory).resolve()
    target = (base / rel).resolve()
    if not _PATH.fullmatch(rel) or ".." in rel.split("/") or not rel.endswith(suffix) or not target.is_relative_to(base):
        raise api_error(422, "content.invalid_path", path=rel)
    if area == "tables" and rel.startswith("socials"):
        raise api_error(422, "content.invalid_path", path=rel)  # i social hanno la loro pagina
    return target


def list_files(layers: Layers, area: str) -> list[dict[str, Any]]:
    """I file di un'area: `{path, layer, size}`; `layer` = `user` se sta nello strato dell'utente, altrimenti `base`."""
    directory, suffix = AREAS[area]
    found: dict[str, dict[str, Any]] = {}
    for root in layers.roots:
        layer = "user" if root == layers.user else "base"
        for file in sorted((root / directory).rglob(f"*{suffix}")):
            rel = file.relative_to(root / directory).as_posix()
            if file.is_file() and _PATH.fullmatch(rel) and not (area == "tables" and rel.startswith("socials")):
                found[rel] = {"path": rel, "layer": layer, "size": file.stat().st_size}
    return sorted(found.values(), key=lambda e: e["path"])


def read_file(layers: Layers, area: str, rel: str) -> dict[str, Any]:
    """`{path, layer, text}` del file (strato dell'utente, altrimenti base). 404 `content.not_found`."""
    for root in reversed(layers.roots):
        target = _safe(root, area, rel)
        if target.is_file():
            return {"path": rel, "layer": "user" if root == layers.user else "base", "text": read_text(target)}
    raise api_error(404, "content.not_found", id=rel)


def write_file(layers: Layers, area: str, rel: str, text: str) -> dict[str, Any]:
    """Scrive `text` nello strato dell'utente (crea o sostituisce). I `.yaml` devono leggersi e avere una mappa o una lista."""
    target = _safe(layers.user, area, rel)
    if AREAS[area][1] == ".yaml":
        document = load_yaml(text)
        if document is not None and not isinstance(document, Mapping | list):
            raise api_error(422, "content.invalid", detail="il file deve contenere una mappa o una lista YAML")
    atomic_write(target, text)
    return {"path": rel, "layer": "user", "text": text}


def delete_file(layers: Layers, area: str, rel: str) -> None:
    """Elimina il file dello strato dell'utente (se esiste anche in quello di base, torna a valere quello). 404 se non e' dell'utente."""
    target = _safe(layers.user, area, rel)
    if not target.is_file():
        raise api_error(404, "content.not_found", id=rel)
    target.unlink()


# --- skill -----------------------------------------------------------------------------------------------------------------


def _skill_files(layers: Layers) -> dict[str, tuple[Path, str]]:
    """`skill_id -> (file, layer)`; le traduzioni `<id>.<lingua>.yaml` non sono skill. L'id e' il nome del file (come `pachimud new skill`)."""
    found: dict[str, tuple[Path, str]] = {}
    for root in layers.roots:
        for file in sorted((root / "skills").glob("*.yaml")):
            if ID_PATTERN.fullmatch(file.stem):
                found[file.stem] = (file, "user" if root == layers.user else "base")
    return found


def _skill_view(skill_id: str, file: Path, layer: str, *, detail: bool) -> dict[str, Any]:
    """Una skill come `dict`: campi semplici (e `advanced` col resto in YAML se `detail`). Un file illeggibile ha `error`."""
    try:
        data = plain(load_yaml(read_text(file)) or {})
        if not isinstance(data, dict):
            raise ValueError("non e' una mappa")
    except Exception as error:
        message = getattr(error, "detail", None)
        return {"skill_id": skill_id, "layer": layer, "error": str(message[0].get("params", {}).get("detail")) if message else str(error)}
    view: dict[str, Any] = {"skill_id": skill_id, "layer": layer, "levels": data.get("levels") or {}}
    view |= {key: data[key] for key in SKILL_SCALARS if key in data}
    names = (data.get("messages") or {}).get("name") if isinstance(data.get("messages"), dict) else None
    view["names"] = {str(lang): str(text) for lang, text in names.items()} if isinstance(names, dict) else {}
    if detail:
        rest = {k: v for k, v in data.items() if k not in SKILL_SCALARS and k != "skill_id"}
        view["advanced"] = dump_yaml(rest) if rest else ""
    return view


def list_skills(layers: Layers) -> list[dict[str, Any]]:
    """Le skill (strati fusi), per id."""
    return [_skill_view(i, f, layer, detail=False) for i, (f, layer) in sorted(_skill_files(layers).items())]


def get_skill(layers: Layers, skill_id: str) -> dict[str, Any]:
    """Una skill con il resto dei campi come YAML (`advanced`). 404 `content.not_found`."""
    entry = _skill_files(layers).get(skill_id)
    if entry is None:
        raise api_error(404, "content.not_found", id=skill_id)
    return _skill_view(skill_id, *entry, detail=True)


def save_skill(layers: Layers, skill_id: str, fields: Mapping[str, Any], advanced: str | None, *, create: bool) -> dict[str, Any]:
    """Crea o aggiorna `skills/<id>.yaml` nello strato dell'utente.

    `fields` = solo i campi semplici inviati (`None` = toglie la chiave); `advanced` = YAML degli altri campi (`None` = invariati; testo
    vuoto = nessuno: le chiavi non piu' presenti vengono tolte). Un elemento solo di base viene copiato nello strato dell'utente.
    """
    if not ID_PATTERN.fullmatch(skill_id):
        raise api_error(422, "content.invalid_id", loc=("path", "id"), id=skill_id)
    existing = _skill_files(layers).get(skill_id)
    if create and existing is not None:
        raise api_error(409, "content.id_taken", id=skill_id)
    if not create and existing is None:
        raise api_error(404, "content.not_found", id=skill_id)
    target = layers.user / "skills" / f"{skill_id}.yaml"
    document = load_yaml(read_text(existing[0])) if existing else None
    if document is None:
        document = CommentedMap({"skill_id": skill_id})
    if not isinstance(document, Mapping):
        raise api_error(422, "content.invalid", detail="il file non contiene una mappa YAML")
    for key, value in fields.items():
        if key not in SKILL_SCALARS:
            continue
        if value is None or value == "":
            document.pop(key, None)
        else:
            document[key] = value
    unknown = [str(v) for v in (document.get("item_types") or []) if v not in ITEM_TYPES]
    if unknown:
        raise api_error(422, "content.invalid", detail=f"item_types: valori non ammessi {unknown} (ammessi: {', '.join(ITEM_TYPES)})")
    if advanced is not None:
        extra = load_yaml(advanced) if advanced.strip() else {}
        if not isinstance(extra, Mapping):
            raise api_error(422, "content.invalid", detail="i campi avanzati devono essere una mappa YAML")
        if set(extra) & (set(SKILL_SCALARS) | {"skill_id"}):
            raise api_error(422, "content.invalid", detail="i campi avanzati non possono ripetere quelli del form")
        for key in [k for k in document if k not in SKILL_SCALARS and k != "skill_id" and k not in extra]:
            del document[key]
        for key, value in extra.items():
            document[key] = value
    atomic_write(target, dump_yaml(document, explicit_start=False))
    return get_skill(layers, skill_id)


def delete_skill(layers: Layers, skill_id: str) -> None:
    """Elimina `skills/<id>.yaml` dello strato dell'utente (sulla base non si puo': 404)."""
    target = layers.user / "skills" / f"{skill_id}.yaml"
    if not ID_PATTERN.fullmatch(skill_id) or not target.is_file():
        raise api_error(404, "content.not_found", id=skill_id)
    target.unlink()


# --- social ----------------------------------------------------------------------------------------------------------------


def _read_map(file: Path) -> dict[str, Any]:
    """Il contenuto di un file YAML come mappa (assente o vuoto -> `{}`)."""
    if not file.is_file():
        return {}
    data = plain(load_yaml(read_text(file)) or {})
    if not isinstance(data, dict):
        raise api_error(422, "content.invalid", detail=f"{file.name}: non e' una mappa YAML")
    return data


def _socials(layers: Layers) -> dict[str, dict[str, Any]]:
    """I social con strati e lingue fuse: `nome -> {aliases, position, victim_min_position, hide, messages, layer}`."""
    merged: dict[str, dict[str, Any]] = {}
    for root in layers.roots:
        layer = "user" if root == layers.user else "base"
        tables = root / "tables"
        for name, entry in _read_map(tables / "socials.yaml").items():
            merged[str(name)] = {**(entry if isinstance(entry, dict) else {}), "layer": layer}
        for file in sorted(tables.glob("socials.*.yaml")):
            lang = file.name.removeprefix("socials.").removesuffix(".yaml")
            for name, texts in _read_map(file).items():
                if str(name) in merged and isinstance(texts, dict):
                    merged[str(name)].setdefault("messages", {}).setdefault(lang, {}).update(texts)
    return merged


def _social_view(name: str, entry: Mapping[str, Any]) -> dict[str, Any]:
    """Un social con i valori di default per i campi assenti."""
    return {
        "name": name,
        "aliases": [str(a) for a in entry.get("aliases") or []],
        "position": str(entry.get("position", "resting")),
        "victim_min_position": int(entry.get("victim_min_position", 0)),
        "hide": bool(entry.get("hide", False)),
        "messages": {
            str(lang): {str(k): str(v) for k, v in (texts or {}).items()} for lang, texts in (entry.get("messages") or {}).items()
        },
        "layer": entry.get("layer", "base"),
    }


def list_socials(layers: Layers) -> list[dict[str, Any]]:
    """I social ordinati per nome."""
    return [_social_view(name, entry) for name, entry in sorted(_socials(layers).items())]


def get_social(layers: Layers, name: str) -> dict[str, Any]:
    """Un social. 404 `content.not_found`."""
    entry = _socials(layers).get(name)
    if entry is None:
        raise api_error(404, "content.not_found", id=name)
    return _social_view(name, entry)


def save_social(layers: Layers, name: str, body: Mapping[str, Any], *, create: bool) -> dict[str, Any]:
    """Scrive il social (tutti i campi, testi per lingua compresi) in `tables/socials.yaml` dello strato dell'utente, commenti salvi."""
    if not ID_PATTERN.fullmatch(name):
        raise api_error(422, "content.invalid_id", loc=("path", "id"), id=name)
    exists = name in _socials(layers)
    if create and exists:
        raise api_error(409, "content.id_taken", id=name)
    if not create and not exists:
        raise api_error(404, "content.not_found", id=name)
    messages = {
        lang: {k: v for k, v in texts.items() if k in SOCIAL_KEYS and v.strip()}
        for lang, texts in (body.get("messages") or {}).items()
        if re.fullmatch(r"[a-z]{2,8}", lang)
    }
    entry = {
        "aliases": list(body.get("aliases") or []),
        "position": body.get("position") or "resting",
        "victim_min_position": int(body.get("victim_min_position") or 0),
        "hide": bool(body.get("hide")),
        "messages": {lang: texts for lang, texts in messages.items() if texts},
    }
    target = layers.user / "tables" / "socials.yaml"
    document = load_yaml(read_text(target)) if target.is_file() else None
    if document is None:
        document = CommentedMap()
    document[name] = entry
    atomic_write(target, dump_yaml(document))
    return get_social(layers, name)


def delete_social(layers: Layers, name: str) -> None:
    """Toglie il social dallo strato dell'utente (404 se non e' li')."""
    target = layers.user / "tables" / "socials.yaml"
    document = load_yaml(read_text(target)) if target.is_file() else None
    if not isinstance(document, Mapping) or name not in document:
        raise api_error(404, "content.not_found", id=name)
    del document[name]
    atomic_write(target, dump_yaml(document))
