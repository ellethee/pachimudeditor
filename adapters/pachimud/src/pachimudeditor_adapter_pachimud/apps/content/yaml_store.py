"""CRUD su una cartella di file YAML di definizioni (`definitions/races`, `definitions/classes`).

I file sono scritti a mano e contengono commenti: le modifiche passano da `ruamel.yaml` in modalita'
round-trip, che tocca solo le chiavi cambiate e lascia intatti commenti e formattazione. La scrittura
e' atomica (file temporaneo + `os.replace`). Gli id sono validati con una regex, quindi non possono
contenere separatori di path (niente path traversal).

Il game server carica gli YAML una sola volta all'avvio: le modifiche hanno effetto al riavvio.
"""

import os
import re
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pachifast.i18n import api_error
from pydantic import BaseModel, ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import LiteralScalarString

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
"""Forma ammessa per un id (e quindi per il nome del file): minuscole, cifre, underscore."""
DISABLED_SUFFIX = ".yaml.disabled"
"""Suffisso dei file disattivati per rinomina (non e' piu' catturato da `glob("*.yaml")` del game server)."""

Validator = Callable[[Mapping[str, Any]], list[str]]


def new_yaml(*, explicit_start: bool = False) -> YAML:
    """Istanza round-trip: conserva commenti e apici, non riformatta le righe lunghe.

    `explicit_start` scrive il marcatore `---` iniziale (usato dai file del gioco)."""
    yaml = YAML(typ="rt")
    yaml.explicit_start = explicit_start
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def plain(value: Any) -> Any:
    """Converte ricorsivamente i contenitori ruamel in dict/list normali."""
    if isinstance(value, Mapping):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [plain(item) for item in value]
    return value


def _as_scalar(value: Any) -> Any:
    """Le stringhe multilinea diventano blocchi letterali `|`, come nei file scritti a mano."""
    if isinstance(value, str) and "\n" in value:
        return LiteralScalarString(value if value.endswith("\n") else value + "\n")
    return value


def _same(old: Any, new: Any) -> bool:
    """Confronto tra il valore del file e quello nuovo (i blocchi letterali ignorano l'a-capo finale)."""
    old, new = plain(old), plain(new)
    if isinstance(old, str) and isinstance(new, str):
        return old.rstrip("\n") == new.rstrip("\n")
    return bool(old == new)


def merge_into(target: Any, new: Mapping[str, Any], defaults: Mapping[str, Any], *, drop_missing: bool = False) -> None:
    """Applica `new` a `target` (mapping ruamel) toccando solo cio' che cambia.

    - chiave presente e uguale: invariata (commenti e formato salvi);
    - chiave assente e valore pari al default: non viene aggiunta (nessun rumore nel file);
    - valore `None`: la chiave viene rimossa;
    - mapping annidati: unione ricorsiva (le sotto-chiavi non inviate restano).
    `drop_missing` rimuove anche le chiavi non presenti in `new` (non usato per l'update parziale).
    """
    for key, value in new.items():
        if value is None:
            if key in target:
                del target[key]
            continue
        if key in target:
            current = target[key]
            if isinstance(value, Mapping) and isinstance(current, Mapping):
                merge_into(current, value, {})
            elif not _same(current, value):
                target[key] = _as_scalar(value) if not isinstance(value, list) else list(value)
            continue
        if key in defaults and _same(defaults[key], value):
            continue
        target[key] = _as_scalar(value) if not isinstance(value, list) else list(value)
    if drop_missing:
        for key in [k for k in target if k not in new]:
            del target[key]


@dataclass
class StoredFile:
    """Un file YAML trovato: percorso, dati grezzi (plain) ed eventuale stato 'disattivato per rinomina'."""

    path: Path
    raw: dict[str, Any]
    renamed_disabled: bool = False


class YamlDirStore:
    """I file `<definitions>/<directory>/<id>.yaml`, ciascuno validato con `model` (schema `Loader*`).

    `root` e' una callable che restituisce la cartella `definitions` (letta a ogni chiamata, cosi' i test
    possono puntarla su una copia temporanea). `validate` ritorna i messaggi di errore semantici extra
    (nomi di flag inesistenti, ...) oltre a quelli di Pydantic. `disabled_by_flag` e' il nome della chiave
    booleana che il game server rispetta (`disabled`); se `None` la disattivazione avviene rinominando il file.
    """

    def __init__(
        self,
        root: Callable[[], Path],
        directory: str,
        model: type[BaseModel],
        id_field: str,
        *,
        validate: Validator | None = None,
        disabled_by_flag: str | None = None,
    ) -> None:
        """Vedi la classe per il significato dei parametri."""
        self._root = root
        self.directory = directory
        self.model = model
        self.id_field = id_field
        self._validate = validate
        self.disabled_by_flag = disabled_by_flag

    @property
    def path(self) -> Path:
        """Cartella dei file di questo tipo."""
        return self._root() / self.directory

    # --- lettura -----------------------------------------------------------------------------

    def _read(self, file: Path) -> dict[str, Any]:
        """Legge un file in dict normale (YAML vuoto -> `{}`)."""
        with file.open("r", encoding="utf-8") as handle:
            data = plain(new_yaml().load(handle) or {})
        if not isinstance(data, dict):
            raise ValueError("il file non contiene una mappa YAML")
        return data

    def _files(self) -> list[Path]:
        """Tutti i file del tipo, attivi e disattivati per rinomina, ordinati per nome."""
        if not self.path.is_dir():
            return []
        found = [p for p in self.path.iterdir() if p.is_file() and (p.name.endswith(".yaml") or p.name.endswith(DISABLED_SUFFIX))]
        return sorted(found, key=lambda p: p.name)

    def stored(self) -> list[StoredFile]:
        """I file leggibili (quelli con YAML rotto sono restituiti con `raw` vuoto e id = nome file)."""
        out: list[StoredFile] = []
        for file in self._files():
            try:
                raw = self._read(file)
            except Exception:
                raw = {}
            out.append(StoredFile(file, raw, file.name.endswith(DISABLED_SUFFIX)))
        return out

    @staticmethod
    def stem(file: Path) -> str:
        """Id implicito dal nome file (`dragon.yaml` / `dragon.yaml.disabled` -> `dragon`)."""
        name = file.name
        for suffix in (DISABLED_SUFFIX, ".yaml"):
            if name.endswith(suffix):
                return name[: -len(suffix)]
        return name

    def locate(self, item_id: str) -> StoredFile | None:
        """Il file che contiene `item_id`: prima per nome, poi cercando la chiave id nel contenuto."""
        for suffix in (".yaml", DISABLED_SUFFIX):
            direct = self.path / f"{item_id}{suffix}"
            if direct.is_file():
                try:
                    return StoredFile(direct, self._read(direct), suffix == DISABLED_SUFFIX)
                except Exception:
                    return StoredFile(direct, {}, suffix == DISABLED_SUFFIX)
        for stored in self.stored():
            if stored.raw.get(self.id_field) == item_id:
                return stored
        return None

    def check_id(self, item_id: str) -> str:
        """`item_id` se ammesso dalla regex, altrimenti 422 `content.invalid_id`."""
        if not ID_PATTERN.fullmatch(item_id):
            raise api_error(422, "content.invalid_id", loc=("path", "id"), id=item_id)
        return item_id

    def parse(self, raw: Mapping[str, Any]) -> BaseModel:
        """Valida `raw` con lo schema del gioco e le regole extra; errore -> 422 `content.invalid`."""
        try:
            item = self.model.model_validate(dict(raw))
        except ValidationError as error:
            first = error.errors()[0]
            raise api_error(
                422, "content.invalid", detail=f"{'.'.join(str(p) for p in first['loc']) or 'valore'}: {first['msg']}"
            ) from error
        problems = self._validate(raw) if self._validate else []
        if problems:
            raise api_error(422, "content.invalid", detail="; ".join(problems))
        return item

    # --- scrittura ---------------------------------------------------------------------------

    def create(self, payload: Mapping[str, Any]) -> StoredFile:
        """Crea `<id>.yaml` da `payload` (chiavi snake_case inviate dal client). 409 se l'id esiste."""
        item_id = self.check_id(str(payload.get(self.id_field, "")))
        self.parse(payload)
        if self.locate(item_id) is not None:
            raise api_error(409, "content.id_taken", id=item_id)
        self.path.mkdir(parents=True, exist_ok=True)
        document = CommentedMap()
        defaults = {name: f.get_default(call_default_factory=True) for name, f in self.model.model_fields.items() if not f.is_required()}
        ordered = {name: payload[name] for name in self.model.model_fields if name in payload}
        ordered |= {k: v for k, v in payload.items() if k not in ordered}
        merge_into(document, ordered, defaults)
        # i campi obbligatori vanno sempre scritti, anche se uguali al default
        for name, field in self.model.model_fields.items():
            if field.is_required() and name in payload and name not in document:
                document[name] = _as_scalar(payload[name])
        target = self.path / f"{item_id}.yaml"
        self._write(target, document, explicit_start=True)
        return StoredFile(target, plain(document))

    def update(self, item_id: str, payload: Mapping[str, Any]) -> StoredFile:
        """Applica `payload` (solo le chiavi inviate) al file di `item_id`. 404 se manca."""
        stored = self.locate(item_id)
        if stored is None:
            raise api_error(404, "content.not_found", id=item_id)
        merged = {**stored.raw}
        merge_dicts(merged, payload)
        self.parse(merged)
        with stored.path.open("r", encoding="utf-8") as handle:
            text = handle.read()
        document = new_yaml().load(text)
        if document is None:
            document = CommentedMap()
        defaults = {name: f.get_default(call_default_factory=True) for name, f in self.model.model_fields.items() if not f.is_required()}
        merge_into(document, {k: v for k, v in payload.items() if k != self.id_field}, defaults)
        self._write(stored.path, document, explicit_start=text.lstrip().startswith("---"))
        return StoredFile(stored.path, plain(document), stored.renamed_disabled)

    def set_disabled(self, item_id: str, disabled: bool) -> StoredFile:
        """Disattiva/riattiva: flag `disabled` nel file (se previsto dal gioco), altrimenti rinomina."""
        stored = self.locate(item_id)
        if stored is None:
            raise api_error(404, "content.not_found", id=item_id)
        if self.disabled_by_flag:
            return self.update(item_id, {self.disabled_by_flag: True if disabled else None})
        target_name = f"{self.stem(stored.path)}{DISABLED_SUFFIX if disabled else '.yaml'}"
        target = stored.path.with_name(target_name)
        if target != stored.path:
            if target.exists():
                raise api_error(409, "content.id_taken", id=item_id)
            os.replace(stored.path, target)
        return StoredFile(target, stored.raw, disabled)

    def delete(self, item_id: str) -> None:
        """Elimina il file di `item_id` (i riferimenti vanno controllati prima dal chiamante)."""
        stored = self.locate(item_id)
        if stored is None:
            raise api_error(404, "content.not_found", id=item_id)
        stored.path.unlink()

    def _write(self, file: Path, document: Any, *, explicit_start: bool = False) -> None:
        """Scrive il documento in modo atomico, mantenendo i permessi del file esistente (0644 se nuovo)."""
        handle, temp_name = tempfile.mkstemp(dir=file.parent, prefix=f".{file.name}.", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                new_yaml(explicit_start=explicit_start).dump(document, stream)
            os.chmod(temp_name, file.stat().st_mode & 0o777 if file.exists() else 0o644)
            os.replace(temp_name, file)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise


def merge_dicts(target: dict[str, Any], new: Mapping[str, Any]) -> None:
    """Unione ricorsiva su dict normali (per validare lo stato finale prima di scrivere)."""
    for key, value in new.items():
        if value is None:
            target.pop(key, None)
        elif isinstance(value, Mapping) and isinstance(target.get(key), dict):
            merge_dicts(target[key], value)
        else:
            target[key] = value
