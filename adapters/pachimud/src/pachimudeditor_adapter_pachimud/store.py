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
- **Riscrittura selettiva**: nei file di stanze, mob e oggetti `save` cambia nel testo SOLO le righe delle voci modificate, aggiunte
  o tolte: le altre voci, i commenti fra le voci e il resto del file restano byte per byte come erano (niente reflow dei testi
  a capo, niente diff rumorosi). Il risultato e' sempre riletto e confrontato con il documento: se non coincide (file con una
  forma insolita) si ripiega sulla scrittura completa, che e' quella di prima.
"""

import io
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
    text: str | None = None
    """Il testo del file come e' su disco (letto o scritto da noi); `None` = non noto (file nuovo): scrittura completa."""
    loaded: list[tuple[CommentedMap, Any]] = field(default_factory=list)
    """Le voci della lista come erano in `text`: (nodo, copia semplice), per riconoscere quelle cambiate."""
    rest: Any = None
    """Le altre chiavi del documento come erano in `text` (copia semplice): se cambiano si riscrive tutto."""

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
            _snapshot(file, text)
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
        """Scrive i file (atomici, solo le righe cambiate nei file di voci) e ne aggiorna l'impronta in cache; se una scrittura fallisce la cache e' invalidata."""
        try:
            for file in files:
                assert file.doc is not None
                text = render_text(file)
                write_text_atomic(file.path, text)
                _reanchor(file, text)
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


def write_text_atomic(path: Path, text: str) -> None:
    """Scrive il testo in modo atomico (temporaneo nella stessa cartella + `os.replace`), con i permessi del file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        os.chmod(temp_name, path.stat().st_mode & 0o777 if path.exists() else 0o644)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def dump_text(document: Any, *, explicit_start: bool = False) -> str:
    """Il documento ruamel come testo YAML (scrittura completa, nello stile dei file del gioco)."""
    buffer = io.StringIO()
    new_yaml(explicit_start=explicit_start).dump(document, buffer)
    return buffer.getvalue()


def write_atomic(path: Path, document: Any, *, explicit_start: bool = False) -> None:
    """Scrive il documento in modo atomico (scrittura completa, senza riscrittura selettiva)."""
    write_text_atomic(path, dump_text(document, explicit_start=explicit_start))


def _snapshot(file: YamlFile, text: str) -> None:
    """Ricorda testo e voci come sono ora (base della riscrittura selettiva del prossimo `save`)."""
    file.text = text
    file.loaded, file.rest = [], None
    if file.kind not in LIST_KEY or file.doc is None:
        return
    key = LIST_KEY[file.kind]
    seq = file.doc.get(key)
    if isinstance(seq, CommentedSeq):
        file.loaded = [(n, plain(n)) for n in seq if isinstance(n, CommentedMap)]
    file.rest = {k: plain(v) for k, v in file.doc.items() if k != key}


def _reanchor(file: YamlFile, text: str) -> None:
    """Dopo una scrittura: il testo scritto diventa la base e le righe dei nodi vivi si riallineano a quel testo (i nodi restano gli stessi)."""
    file.text = None  # se qualcosa va storto la prossima scrittura sara' completa
    try:
        parsed = new_yaml().load(text)
        if file.kind in LIST_KEY and isinstance(parsed, CommentedMap) and file.doc is not None:
            key = LIST_KEY[file.kind]
            mine, theirs = file.doc.get(key), parsed.get(key)
            if isinstance(mine, CommentedSeq) and isinstance(theirs, CommentedSeq) and len(mine) == len(theirs):
                for node, fresh in zip(mine, theirs, strict=True):
                    if isinstance(node, CommentedMap) and isinstance(fresh, CommentedMap):
                        node.lc.line, node.lc.col = fresh.lc.line, fresh.lc.col
                file.doc.lc.data = parsed.lc.data
                _snapshot(file, text)
            elif not isinstance(mine, CommentedSeq) and theirs is None:
                _snapshot(file, text)
        else:
            file.text = text
    except Exception:  # noqa: BLE001 - testo non rileggibile: resta la scrittura completa
        file.text = None


def _is_comment(line: str) -> bool:
    """Riga fatta solo di un commento."""
    return line.lstrip().startswith("#")


def _indent(line: str) -> int:
    """Spazi iniziali di una riga."""
    return len(line) - len(line.lstrip(" "))


def _header_start(lines: list[str], start: int, lower: int) -> int:
    """La prima riga del blocco di commenti attaccato (senza righe vuote) sopra la riga `start`, senza scendere sotto `lower`."""
    j = start
    while j - 1 >= lower and _is_comment(lines[j - 1]):
        j -= 1
    return j


def _selective(file: YamlFile) -> str | None:
    """Il testo con SOLO le voci cambiate, aggiunte o tolte riscritte; il resto identico a `file.text`. `None` se non e' possibile o non e' verificato."""
    if file.kind not in LIST_KEY or file.text is None or not file.loaded or file.doc is None:
        return None
    key = LIST_KEY[file.kind]
    seq = file.doc.get(key)
    if not isinstance(seq, CommentedSeq) or {k: plain(v) for k, v in file.doc.items() if k != key} != file.rest:
        return None
    lines = file.text.splitlines(keepends=True)
    starts = [getattr(node.lc, "line", None) for node, _ in file.loaded]
    key_line = (file.doc.lc.data.get(key) or [None])[0]
    if (
        key_line is None
        or any(s is None for s in starts)
        or starts != sorted(set(starts))
        or starts[0] <= key_line
        or starts[-1] >= len(lines)
    ):
        return None
    after = [k for k in file.doc if list(file.doc).index(k) > list(file.doc).index(key)]
    next_line = (file.doc.lc.data.get(after[0]) or [None])[0] if after else len(lines)
    if next_line is None or next_line <= starts[-1]:
        return None
    heads = [_header_start(lines, s, (starts[i - 1] if i else key_line) + 1) for i, s in enumerate(starts)]
    end = len(lines) if not after else _header_start(lines, next_line, starts[-1] + 1)
    bounds = [*heads[1:], end]
    parts: dict[int, tuple[str, str, str]] = {}  # id(nodo) -> (testata, corpo, coda)
    for i, (node, _snap) in enumerate(file.loaded):
        dash = _indent(lines[starts[i]])
        body_end = bounds[i]
        while body_end - 1 > starts[i] and (
            not lines[body_end - 1].strip() or (_is_comment(lines[body_end - 1]) and _indent(lines[body_end - 1]) <= dash)
        ):
            body_end -= 1
        parts[id(node)] = ("".join(lines[heads[i] : starts[i]]), "".join(lines[starts[i] : body_end]), "".join(lines[body_end : bounds[i]]))
    snaps = {id(node): snap for node, snap in file.loaded}
    out = ["".join(lines[: heads[0]])]
    for node in seq:
        before = parts.get(id(node))
        if before is not None and snaps[id(node)] == plain(node):
            head, body, tail = before
        else:
            head, tail = (before[0], before[2]) if before is not None else ("", "")
            body = dump_text(CommentedSeq([node]))
        out.append(head + body + ("\n" if body and not body.endswith("\n") else "") + tail)
    out.append("".join(lines[end:]))
    text = "".join(out)
    try:
        check = new_yaml().load(text)
    except Exception:  # noqa: BLE001 - la forma insolita del file: scrittura completa
        return None
    return text if plain(check) == plain(file.doc) else None


def render_text(file: YamlFile) -> str:
    """Il testo da scrivere per il file: riscrittura selettiva se possibile e verificata, altrimenti scrittura completa."""
    assert file.doc is not None
    selective = _selective(file)
    return selective if selective is not None else dump_text(file.doc, explicit_start=file.explicit_start)


def _first_error(error: ValidationError) -> str:
    """Il primo errore di validazione come `campo: messaggio`."""
    first = error.errors()[0]
    where = ".".join(str(p) for p in first["loc"])
    return f"{where}: {first['msg']}" if where else str(first["msg"])


def model_error(error: ValidationError) -> str:
    """Esportata per l'adapter: il primo errore come testo."""
    return _first_error(error)


__all__ = [
    "FileIssue",
    "Item",
    "Kind",
    "YamlFile",
    "YamlStore",
    "ZoneEntry",
    "dump_text",
    "model_error",
    "new_yaml",
    "plain",
    "render_text",
    "write_atomic",
    "write_text_atomic",
]
