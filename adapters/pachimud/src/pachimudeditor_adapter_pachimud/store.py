"""Archivio dei file YAML di un mondo pachimud: cache, indici per vnum, scrittura atomica che conserva i commenti.

Layout del gioco (`<definitions>/zones/**`): una cartella per zona con `zone.yaml` e, nella stessa cartella (anche in
sottocartelle, come fa il loader del gioco), `room*.yaml`, `mob*.yaml`, `obj*.yaml`, `reset*.yaml`. Un suffisso
`_<area>` / `-<area>` nel nome del file e' l'«area» del file (etichetta, vedi `loaders.AreaName`).

- **Lettura tollerante**: ogni file e' un documento ruamel round-trip; un file YAML rotto o una voce non valida
  producono un `FileIssue` (file, riga, messaggio) ma non impediscono di leggere il resto del mondo.
- **Cache**: i file sono riletti solo se cambia `(mtime_ns, size)`; l'elenco dei file e' ricontrollato a ogni
  richiesta (solo `stat`), quindi le modifiche esterne (il gioco non scrive mai i YAML, ma l'utente si') sono viste subito.
- **Identita'**: zona = `vnum` di `zone.yaml`; stanza/mob/oggetto = `vnum` (globale). Con vnum duplicate vince la prima
  voce (in ordine di percorso) e le altre sono segnalate; il gioco invece le sovrascrive in silenzio.
- **Scrittura**: le funzioni dell'adapter modificano i mapping ruamel (solo le chiavi cambiate, commenti e formato
  salvi) e chiamano `save`, che scrive in modo atomico (file temporaneo + `os.replace`) e aggiorna la cache.
"""

import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pachifast.i18n import api_error
from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from pachimudeditor_adapter_pachimud.loaders import LoaderResetFile, LoaderZone, validate_entry

log = logging.getLogger(__name__)

Kind = Literal["room", "mob", "object"]
FileKind = Literal["zone", "rooms", "mobs", "objects", "resets"]
STEM: dict[str, str] = {"rooms": "rooms", "mobs": "mobs", "objects": "objects", "resets": "resets"}
STEMS: dict[str, tuple[str, ...]] = {
    "rooms": ("rooms", "room"),
    "mobs": ("mobs", "mob"),
    "objects": ("objects", "object", "obj"),
    "resets": ("resets", "reset"),
}
"""Radici di nome file da cui ricavare l'area (la prima che combacia)."""
"""Nome di base dei file creati dall'editor (`rooms.yaml`, `rooms_<area>.yaml`)."""
PREFIX: dict[str, str] = {"room": "rooms", "mob": "mobs", "object": "objects"}
"""Tipo di entita' -> tipo di file che la contiene."""
LIST_KEY: dict[str, str] = {"rooms": "rooms", "mobs": "mobs", "objects": "objects"}
FILE_PREFIXES: tuple[tuple[str, FileKind], ...] = (("room", "rooms"), ("mob", "mobs"), ("obj", "objects"), ("reset", "resets"))
"""Prefissi dei nomi file riconosciuti, come i glob del gioco (`room*.yaml`, `mob*.yaml`, `obj*.yaml`, `reset*.yaml`)."""
FOLDER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
"""Nome di cartella di zona ammesso: niente separatori ne' `..`."""
AREA_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def new_yaml(*, explicit_start: bool = False) -> YAML:
    """Istanza ruamel round-trip con lo stile dei file del gioco (sequenze sotto la chiave con trattino rientrato)."""
    yaml = YAML(typ="rt")
    yaml.explicit_start = explicit_start
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def plain(value: Any) -> Any:
    """Converte ricorsivamente mapping e sequenze ruamel in dict/list normali."""
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def area_of_filename(name: str, stem: str) -> str | None:
    """Area dal nome `<stem>_<area>.yaml` / `<stem>-<area>.yaml` (come `area_from_filename` del gioco)."""
    base = name[:-5] if name.endswith(".yaml") else name
    if not base.startswith(stem) or base[len(stem) : len(stem) + 1] not in ("_", "-"):
        return None
    suffix = base[len(stem) + 1 :]
    return suffix if suffix and AREA_RE.match(suffix) else None


def file_name_for(kind: FileKind, area: str | None) -> str:
    """`rooms.yaml` senza area, `rooms_<area>.yaml` con."""
    return f"{STEM[kind]}.yaml" if area is None else f"{STEM[kind]}_{area}.yaml"


@dataclass(eq=False)
class FileIssue:
    """Un problema di lettura: file, riga (1-based) se nota, gravita' e messaggio."""

    path: str
    message: str
    line: int | None = None
    severity: Literal["error", "warning"] = "error"
    code: str = "file_invalid"

    def text(self) -> str:
        """`percorso:riga: messaggio`."""
        return f"{self.path}{f':{self.line}' if self.line else ''}: {self.message}"


@dataclass(eq=False)
class YamlFile:
    """Un file YAML della zona."""

    path: Path
    kind: FileKind
    area: str | None = None
    stamp: tuple[int, int] | None = None
    doc: CommentedMap | None = None
    error: str | None = None
    explicit_start: bool = False
    resets: LoaderResetFile | None = None

    def list_of(self, create: bool = False) -> CommentedSeq | None:
        """La sequenza `rooms`/`mobs`/`objects` del documento (creata se manca e `create`)."""
        assert self.doc is not None
        key = LIST_KEY[self.kind]
        seq = self.doc.get(key)
        if seq is None and create:
            seq = CommentedSeq()
            self.doc[key] = seq
        return seq if isinstance(seq, list) else None


@dataclass(eq=False)
class Item:
    """Una stanza, un mob o un oggetto caricato."""

    kind: Kind
    vnum: int
    raw: CommentedMap
    file: YamlFile
    zone: "ZoneEntry"
    model: Any
    """Vista tipizzata (`LoaderRoom`/`LoaderMob`/`Proto`) della voce, ricalcolata dopo ogni modifica."""

    @property
    def area(self) -> str | None:
        """Area della voce: quella propria, altrimenti quella del file (suffisso del nome o chiave `area`)."""
        return self.model.area or (self.file.doc or {}).get("area") or self.file.area

    def revalidate(self) -> None:
        """Ricalcola la vista tipizzata dopo una modifica di `raw`.

        Raises:
            ValidationError: se la voce non e' piu' valida (l'adapter la traduce in 422).
        """
        self.model = validate_entry(PREFIX[self.kind], plain(self.raw))
        self.vnum = self.model.vnum


@dataclass(eq=False)
class ZoneEntry:
    """Una zona: cartella, `zone.yaml` e file di contenuto."""

    dir: Path
    file: YamlFile
    model: LoaderZone
    files: list[YamlFile] = field(default_factory=list)
    items: dict[Kind, list[Item]] = field(default_factory=lambda: {"room": [], "mob": [], "object": []})

    @property
    def vnum(self) -> int:
        """`id` = `vnum` della zona."""
        return int(self.model.vnum)

    def of_kind(self, kind: FileKind) -> list[YamlFile]:
        """I file della zona di quel tipo, in ordine di percorso."""
        return [f for f in self.files if f.kind == kind]

    def revalidate(self) -> None:
        """Ricalcola la vista tipizzata di `zone.yaml`.

        Raises:
            ValidationError: se `zone.yaml` non e' piu' valido.
        """
        self.model = LoaderZone.model_validate(plain(self.file.doc))


class YamlStore:
    """Tutte le zone sotto `<definitions>/zones` (vedi docstring del modulo)."""

    def __init__(self, definitions: Path) -> None:
        """`definitions` e' la cartella `definitions/` del gioco (nessuna lettura finche' non serve)."""
        self.definitions = definitions
        self.root = definitions / "zones"
        self.zones: list[ZoneEntry] = []
        self.issues: list[FileIssue] = []
        self._parse_issues: list[FileIssue] = []
        self.duplicates: list[tuple[Kind, int, ZoneEntry]] = []
        """Voci con vnum gia' usato da un'altra voce (la prima vince)."""
        self.duplicate_zones: list[tuple[int, Path]] = []
        self._files: dict[Path, YamlFile] = {}
        self._stamps: dict[Path, tuple[int, int]] | None = None
        self._index: dict[Kind, dict[int, Item]] = {"room": {}, "mob": {}, "object": {}}
        self._zone_index: dict[int, ZoneEntry] = {}

    # ------------------------------------------------------------------ lettura

    @staticmethod
    def _stat(path: Path) -> tuple[int, int] | None:
        """`(mtime_ns, size)` o `None` se il file non esiste."""
        try:
            st = path.stat()
        except OSError:
            return None
        return st.st_mtime_ns, st.st_size

    def _candidates(self) -> dict[Path, tuple[int, int]]:
        """Tutti i file YAML che il gioco leggerebbe, con la loro impronta."""
        found: dict[Path, tuple[int, int]] = {}
        if not self.root.is_dir():
            return found
        for current, _dirs, names in os.walk(self.root):
            for name in names:
                if not name.endswith(".yaml") or not (name == "zone.yaml" or any(name.startswith(p) for p, _ in FILE_PREFIXES)):
                    continue
                path = Path(current, name)
                stamp = self._stat(path)
                if stamp is not None:
                    found[path] = stamp
        return found

    @staticmethod
    def _kind_of(name: str) -> FileKind | None:
        """Il tipo di file dal nome (`zone.yaml` o prefisso del gioco)."""
        if name == "zone.yaml":
            return "zone"
        return next((kind for prefix, kind in FILE_PREFIXES if name.startswith(prefix)), None)

    def _load_file(self, path: Path, kind: FileKind, stamp: tuple[int, int]) -> YamlFile:
        """Legge un file in un documento ruamel; gli errori finiscono in `YamlFile.error`."""
        area = next((a for stem in STEMS.get(kind, ()) if (a := area_of_filename(path.name, stem))), None)
        file = YamlFile(path=path, kind=kind, area=area, stamp=stamp)
        try:
            text = path.read_text(encoding="utf-8")
            file.explicit_start = text.lstrip().startswith("---")
            doc = new_yaml().load(text)
            if doc is None:
                doc = CommentedMap()
            if not isinstance(doc, CommentedMap):
                raise ValueError("il file non contiene una mappa YAML")
            file.doc = doc
        except Exception as error:  # noqa: BLE001 - YAML malformato / non leggibile: il file e' segnalato, non fatale
            file.error = str(error).splitlines()[0][:300] if str(error) else type(error).__name__
            mark = getattr(error, "problem_mark", None)
            self._parse_issues.append(FileIssue(self._rel(path), file.error, getattr(mark, "line", -1) + 1 or None))
        return file

    def _rel(self, path: Path) -> str:
        """Il percorso relativo a `definitions/` (per i messaggi)."""
        try:
            return str(path.relative_to(self.definitions))
        except ValueError:
            return str(path)

    def refresh(self) -> None:
        """Riallinea cache e indici al disco (solo `stat` se nulla e' cambiato)."""
        stamps = self._candidates()
        if self._stamps is not None and stamps == self._stamps:
            return
        self._parse_issues = []
        files: dict[Path, YamlFile] = {}
        for path, stamp in sorted(stamps.items()):
            kind = self._kind_of(path.name)
            if kind is None:
                continue
            old = self._files.get(path)
            if old is not None and old.stamp == stamp and old.error is None:
                files[path] = old
            else:
                files[path] = self._load_file(path, kind, stamp)
        self._files = files
        self._stamps = stamps
        self._rebuild()

    def invalidate(self) -> None:
        """Scarta la cache: la prossima `refresh` rilegge tutto dal disco."""
        self._files, self._stamps = {}, None

    def _rebuild(self) -> None:
        """Ricostruisce zone, voci tipizzate e indici dai file caricati."""
        self.issues = list(self._parse_issues)
        self.zones, self.duplicates, self.duplicate_zones = [], [], []
        self._index = {"room": {}, "mob": {}, "object": {}}
        self._zone_index = {}
        zone_dirs = sorted({p.parent for p, f in self._files.items() if f.kind == "zone"}, key=lambda d: (-len(d.parts), str(d)))
        owned: dict[Path, list[YamlFile]] = {d: [] for d in zone_dirs}
        for path, file in self._files.items():
            if file.kind == "zone":
                continue
            owner = next((d for d in zone_dirs if d in path.parents), None)  # la cartella di zona piu' vicina
            if owner is not None:
                owned[owner].append(file)
        for zone_dir in sorted(zone_dirs, key=str):
            zone_file = self._files[zone_dir / "zone.yaml"]
            if zone_file.doc is None:
                continue
            try:
                model = LoaderZone.model_validate(plain(zone_file.doc))
            except ValidationError as error:
                self.issues.append(FileIssue(self._rel(zone_file.path), _first_error(error)))
                continue
            if model.vnum in self._zone_index:
                self.duplicate_zones.append((model.vnum, zone_dir))
                self.issues.append(
                    FileIssue(self._rel(zone_file.path), f"vnum di zona {model.vnum} gia' usato da un'altra zona", code="duplicate")
                )
                continue
            entry = ZoneEntry(dir=zone_dir, file=zone_file, model=model, files=sorted(owned[zone_dir], key=lambda f: str(f.path)))
            self._zone_index[model.vnum] = entry
            self.zones.append(entry)
            self._load_items(entry)
        self.zones.sort(key=lambda z: z.vnum)

    def _load_items(self, zone: ZoneEntry) -> None:
        """Valida le voci dei file di contenuto e dei reset di una zona e le inserisce negli indici."""
        for file in zone.files:
            if file.doc is None:
                continue
            if file.kind == "resets":
                try:
                    file.resets = LoaderResetFile.model_validate(plain(file.doc))
                except ValidationError as error:
                    file.resets = None
                    file.error = _first_error(error)
                    self.issues.append(FileIssue(self._rel(file.path), file.error))
                continue
            kind: Kind = {"rooms": "room", "mobs": "mob", "objects": "object"}[file.kind]  # type: ignore[assignment]
            entries = file.doc.get(LIST_KEY[file.kind])
            if entries is None:
                continue
            if not isinstance(entries, list):
                self.issues.append(FileIssue(self._rel(file.path), f"«{LIST_KEY[file.kind]}» deve essere una lista"))
                continue
            for raw in entries:
                line = getattr(getattr(raw, "lc", None), "line", None)
                try:
                    if not isinstance(raw, CommentedMap):
                        raise ValueError("la voce non e' una mappa")
                    model = validate_entry(PREFIX[kind], plain(raw))
                except (ValidationError, ValueError) as error:
                    message = _first_error(error) if isinstance(error, ValidationError) else str(error)
                    self.issues.append(FileIssue(self._rel(file.path), message, None if line is None else line + 1))
                    continue
                item = Item(kind=kind, vnum=model.vnum, raw=raw, file=file, zone=zone, model=model)
                zone.items[kind].append(item)
                if item.vnum in self._index[kind]:
                    self.duplicates.append((kind, item.vnum, zone))
                    self.issues.append(
                        FileIssue(
                            self._rel(file.path),
                            f"{kind} vnum {item.vnum} duplicato",
                            None if line is None else line + 1,
                            "warning",
                            "duplicate",
                        )
                    )
                else:
                    self._index[kind][item.vnum] = item

    # ------------------------------------------------------------------ ricerca

    def zone(self, vnum: int) -> ZoneEntry | None:
        """La zona con quel vnum."""
        return self._zone_index.get(vnum)

    def find(self, kind: Kind, vnum: int) -> Item | None:
        """La voce per vnum (indice globale)."""
        return self._index[kind].get(vnum)

    def all_items(self, kind: Kind) -> list[Item]:
        """Tutte le voci `kind`, in ordine di vnum."""
        return sorted(self._index[kind].values(), key=lambda i: i.vnum)

    def vnums(self, kind: Kind) -> set[int]:
        """I vnum esistenti."""
        return set(self._index[kind])

    def room_names(self) -> dict[int, str]:
        """vnum -> nome di ogni stanza (per risolvere le destinazioni)."""
        return {v: i.model.name for v, i in self._index["room"].items()}

    # ------------------------------------------------------------------ scrittura

    def safe_folder(self, name: str) -> Path:
        """La cartella di una nuova zona sotto `zones/`; 422 `pachimud.invalid_folder` se il nome non e' ammesso."""
        if not FOLDER_NAME.fullmatch(name or ""):
            raise api_error(422, "pachimud.invalid_folder", name=str(name))
        return self.root / name

    def free_folder(self, base: str) -> str:
        """Un nome di cartella di zona non ancora esistente: `base`, poi `base2`, `base3`..."""
        n = 1
        while (self.root / f"{base}{'' if n == 1 else n}").exists():
            n += 1
        return f"{base}{'' if n == 1 else n}"

    def save(self, *files: YamlFile) -> None:
        """Scrive i file (atomici) e ne aggiorna l'impronta in cache; se una scrittura fallisce la cache e' invalidata."""
        try:
            for file in files:
                assert file.doc is not None
                write_atomic(file.path, file.doc, explicit_start=file.explicit_start)
        except BaseException:
            self.invalidate()
            raise
        for file in files:
            file.stamp = self._stat(file.path)
            if self._stamps is not None and file.stamp is not None:
                self._stamps[file.path] = file.stamp
            self._files[file.path] = file
        self._rebuild()

    def new_file(self, zone: ZoneEntry, kind: FileKind, area: str | None) -> YamlFile:
        """Un nuovo file di contenuto della zona (non ancora scritto) per `kind`/`area`."""
        path = zone.dir / file_name_for(kind, area)
        doc = CommentedMap()
        if kind in LIST_KEY:
            doc[LIST_KEY[kind]] = CommentedSeq()
        file = YamlFile(path=path, kind=kind, area=area, doc=doc, explicit_start=True)
        zone.files.append(file)
        zone.files.sort(key=lambda f: str(f.path))
        self._files[path] = file
        return file

    def file_for(self, zone: ZoneEntry, kind: Kind, area: str | None) -> YamlFile:
        """Il file dove aggiungere una nuova voce: quello dell'area indicata, altrimenti il file base (creato se manca)."""
        file_kind: FileKind = PREFIX[kind]  # type: ignore[assignment]
        if area is not None and not AREA_RE.fullmatch(str(area)):
            raise api_error(422, "pachimud.invalid_area", area=str(area))
        same = [f for f in zone.of_kind(file_kind) if f.doc is not None and f.error is None and f.area == area]
        if same:
            exact = file_name_for(file_kind, area)
            return next((f for f in same if f.path.name == exact), same[0])
        return self.new_file(zone, file_kind, area)


def write_atomic(path: Path, document: Any, *, explicit_start: bool = False) -> None:
    """Scrive il documento in modo atomico (temporaneo nella stessa cartella + `os.replace`), con i permessi del file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            new_yaml(explicit_start=explicit_start).dump(document, stream)
        os.chmod(temp_name, path.stat().st_mode & 0o777 if path.exists() else 0o644)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _first_error(error: ValidationError) -> str:
    """Il primo errore di validazione come `campo: messaggio`."""
    first = error.errors()[0]
    where = ".".join(str(p) for p in first["loc"])
    return f"{where}: {first['msg']}" if where else str(first["msg"])


def model_error(error: ValidationError) -> str:
    """Esportata per l'adapter: il primo errore come testo."""
    return _first_error(error)


__all__ = ["FileIssue", "Item", "Kind", "YamlFile", "YamlStore", "ZoneEntry", "model_error", "new_yaml", "plain", "write_atomic"]
