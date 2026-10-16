"""Archivio dei file di dati di un mondo `kind: mapping`: scoperta dei file, cache, indici per vnum e scrittura atomica.

Due layout (`layout.mode`):

- `zone_files`: ogni zona e' un file (ROM `.are`); un eventuale file indice (`area.lst`) elenca i file abilitati, gli altri
  file che corrispondono al `glob` sono zone `enabled: false`; stanze/mob/oggetti appartengono alla zona del file;
- `type_files`: un file per tipo (`.wld .mob .obj .zon`, Diku classico); le zone sono i record del file di zona e le
  entita' appartengono alla zona il cui range di vnum le contiene (`zone_range`).

Cache: ogni file e' riletto solo se cambia `(mtime_ns, size)`; indice e cartelle sono controllati a ogni `refresh`
(solo `stat`), quindi le modifiche esterne si vedono alla richiesta dopo.
"""

import bisect
import fnmatch
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pachifast.i18n import api_error

from pachimudeditor_adapter_mapping import hooks
from pachimudeditor_adapter_mapping.dsl import evaluate
from pachimudeditor_adapter_mapping.grammar import Document, MappingParseError, Record, Section, parse_document
from pachimudeditor_adapter_mapping.schema import FieldMap, MappingSpec, SectionSpec
from pachimudeditor_adapter_mapping.writer import write_document

log = logging.getLogger(__name__)

KINDS = ("room", "mob", "object")
FILE_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,60}$")
"""Nome di file di zona ammesso: niente separatori ne' `..`."""


def decode_bytes(data: bytes, encoding: str = "auto") -> tuple[str, str]:
    """Decodifica un file: `auto` = UTF-8 se valido, altrimenti latin-1 (lossless). Restituisce (testo, encoding)."""
    if encoding != "auto":
        return data.decode(encoding), encoding
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Scrive `data` su `path` in modo atomico (file temporaneo nella stessa cartella + `os.replace`)."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp, path.stat().st_mode & 0o7777)
        except FileNotFoundError:
            os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@dataclass
class IndexFile:
    """File indice dei file di zona: righe (nomi, commenti, vuote) e terminatore (`$`)."""

    lines: list[str] = field(default_factory=list)
    comment: str = "#"
    end: str | None = "$"
    newline: str = "\n"
    after: str = ""
    final_newline: bool = True

    @classmethod
    def parse(cls, text: str, comment: str, end: str | None) -> "IndexFile":
        """Interpreta il testo (si ferma al terminatore, il resto e' conservato)."""
        newline = "\r\n" if "\r\n" in text else "\n"
        lines: list[str] = []
        pos = 0
        while pos < len(text):
            eol = text.find("\n", pos)
            stop = len(text) if eol < 0 else eol
            line = text[pos:stop].rstrip("\r")
            nxt = len(text) if eol < 0 else eol + 1
            if end and line.strip().startswith(end):
                return cls(lines, comment, end, newline, text[nxt:], eol >= 0)
            lines.append(line)
            pos = nxt
        return cls(lines, comment, end, newline)

    @property
    def names(self) -> list[str]:
        """Nomi elencati (senza commenti ne' righe vuote)."""
        return [ln.strip() for ln in self.lines if ln.strip() and not ln.strip().startswith(self.comment)]

    def add(self, name: str) -> bool:
        """Aggiunge `name` prima del terminatore (`False` se gia' presente)."""
        if name in self.names:
            return False
        self.lines.append(name)
        return True

    def remove(self, name: str) -> bool:
        """Toglie `name` (`False` se assente)."""
        keep = [ln for ln in self.lines if ln.strip() != name]
        changed = len(keep) != len(self.lines)
        self.lines = keep
        return changed

    def to_text(self) -> str:
        """Testo con il terminatore sempre presente."""
        body = "".join(ln + self.newline for ln in self.lines)
        end = (self.end or "") + (self.newline if self.final_newline or self.after else "")
        return body + end + self.after


@dataclass(eq=False)
class FileEntry:
    """Un file di dati caricato."""

    name: str
    path: Path
    kind: str
    """Nome della grammatica di file (`grammar.files`)."""
    doc: Document
    stamp: tuple[int, int] | None
    listed: bool = True


@dataclass(eq=False)
class ZoneUnit:
    """Una zona: record di intestazione, file, range di vnum, id e contenuto."""

    header: Record
    file: FileEntry
    position: int = 0
    zone_id: int = 0
    bottom: int = 0
    top: int = 0
    items: dict[str, list[Record]] = field(default_factory=lambda: {k: [] for k in KINDS})

    @property
    def listed(self) -> bool:
        """Zona abilitata (file elencato nell'indice)."""
        return self.file.listed


class Store:
    """File di un mondo con cache e indici (vedi docstring del modulo)."""

    def __init__(self, spec: MappingSpec, root: Path) -> None:
        """`root` e' la cartella dei dati (`path` del mondo)."""
        self.spec, self.root, self.layout = spec, root, spec.layout
        self.entries: dict[str, FileEntry] = {}
        self.zones: list[ZoneUnit] = []
        self._index: dict[str, dict[int, tuple[ZoneUnit, Record, FileEntry]]] = {k: {} for k in KINDS}
        self._owner: dict[int, FileEntry] = {}
        self._signature: tuple[Any, ...] | None = None
        self.key_of = {n: rg.key for n, rg in spec.grammar.records.items()}
        self.zone_entity = spec.model.zone.entity

    # ------------------------------------------------------------------ file indice

    @property
    def index_path(self) -> Path | None:
        """Percorso del file indice, se configurato."""
        return self.root / self.layout.index.file if self.layout.index else None

    def read_index(self) -> IndexFile:
        """Il file indice (vuoto se non esiste)."""
        idx = self.layout.index
        assert idx is not None
        try:
            text, _ = decode_bytes(self.index_path.read_bytes())  # type: ignore[union-attr]
        except FileNotFoundError:
            return IndexFile(comment=idx.comment, end=idx.end)
        return IndexFile.parse(text, idx.comment, idx.end)

    def set_listed(self, name: str, listed: bool) -> None:
        """Aggiunge/toglie `name` dall'indice."""
        index = self.read_index()
        if index.add(name) if listed else index.remove(name):
            atomic_write_bytes(self.index_path, index.to_text().encode("utf-8"))  # type: ignore[arg-type]
        self._signature = None

    def safe_path(self, name: str) -> Path:
        """Percorso di un file di zona nella radice; 422 `mapping.invalid_file_name` se il nome non e' ammesso."""
        glob = self.layout.glob or "*"
        if not FILE_NAME.fullmatch(name or "") or not fnmatch.fnmatch(name, glob):
            raise api_error(422, "mapping.invalid_file_name", name=str(name), pattern=glob)
        path = (self.root / name).resolve()
        if path.parent != self.root.resolve():
            raise api_error(422, "mapping.invalid_file_name", name=name, pattern=glob)
        return path

    # ------------------------------------------------------------------ caricamento

    @staticmethod
    def _stamp(path: Path) -> tuple[int, int] | None:
        """`(mtime_ns, size)` o `None`."""
        try:
            st = path.stat()
        except FileNotFoundError:
            return None
        return st.st_mtime_ns, st.st_size

    def _discover(self) -> tuple[list[tuple[str, str, bool]], set[str]]:
        """`[(nome relativo, grammatica di file, elencato)]` nell'ordine di lettura e nomi dell'indice."""
        lay, out = self.layout, []
        if lay.mode == "zone_files":
            glob = lay.glob or "*"
            names = [n for n in (self.read_index().names if lay.index else []) if fnmatch.fnmatch(n, glob) and FILE_NAME.fullmatch(n)]
            listed = set(names)
            if lay.index is None:
                names = []
            extra = sorted(p.name for p in self.root.glob(glob) if p.is_file() and p.name not in listed and FILE_NAME.fullmatch(p.name))
            out = [(n, lay.zone_file or "", True) for n in names] + [(n, lay.zone_file or "", lay.index is None) for n in extra]
            return out, listed
        for kind, pattern in lay.files.items():
            out += [(str(p.relative_to(self.root)), kind, True) for p in sorted(self.root.glob(pattern)) if p.is_file()]
        return out, set()

    def refresh(self) -> None:
        """Riallinea cache e indici al disco (solo `stat`; rilegge i file cambiati)."""
        discovered, _ = self._discover()
        stamps = {name: self._stamp(self.root / name) for name, _, _ in discovered}
        signature = (tuple((n, k, ls, stamps[n]) for n, k, ls in discovered), self._stamp(self.index_path) if self.index_path else None)
        if signature == self._signature:
            return
        entries: dict[str, FileEntry] = {}
        for name, kind, listed in discovered:
            stamp, old = stamps[name], self.entries.get(name)
            if stamp is None:
                continue
            if old is not None and old.stamp == stamp and old.kind == kind:
                old.listed = listed
                entries[name] = old
                continue
            try:
                entries[name] = self._load(name, kind, stamp, listed)
            except (MappingParseError, OSError, ValueError, UnicodeDecodeError) as error:
                log.warning("file %s non leggibile: %s", name, error)
        self.entries, self._signature = entries, signature
        self._rebuild()

    def _load(self, name: str, kind: str, stamp: tuple[int, int], listed: bool) -> FileEntry:
        """Legge e interpreta un file."""
        path = self.root / name
        text, encoding = decode_bytes(path.read_bytes(), self.layout.encoding)
        doc = parse_document(self.spec, kind, text, name)
        doc.encoding = encoding
        if self.layout.newline != "auto":
            doc.newline = "\r\n" if self.layout.newline == "crlf" else "\n"
        return FileEntry(name, path, kind, doc, stamp, listed)

    # ------------------------------------------------------------------ indici

    def sections(self, entry: FileEntry, entity: str) -> list[Section]:
        """Le sezioni del documento che contengono record di `entity`."""
        return [s for s in entry.doc.sections if s.spec is not None and s.spec.entity == entity]

    def range_of(self, fm: FieldMap, fields: dict[str, Any]) -> int:
        """Valore intero di un estremo del range dall'intestazione di zona."""
        value = evaluate(fm.expr, fields) if fm.expr is not None else (fields.get(fm.from_ or "") if fm.from_ else None)
        return int(value or 0)

    def _ranges(self, units: list[ZoneUnit]) -> list[tuple[int, int]]:
        """`(bottom, top)` per zona secondo `layout.zone_range`."""
        zr = self.layout.zone_range
        fields = [u.header.fields for u in units]
        if zr.mode == "hook":
            return hooks.zone_range_hook(zr.hook or "")(fields)
        tops = [self.range_of(zr.top, f) for f in fields]  # type: ignore[arg-type]
        if zr.mode == "top":
            return hooks.zone_from_top([{"top": t} for t in tops])
        return [(self.range_of(zr.bottom, f), t) for f, t in zip(fields, tops, strict=True)]  # type: ignore[arg-type]

    def _rebuild(self) -> None:
        """Ricostruisce zone, id e indici per vnum."""
        self.zones, self._owner = [], {}
        self._index = {k: {} for k in KINDS}
        lay = self.layout
        for entry in self.entries.values():
            for sec in self.sections(entry, self.zone_entity):
                for rec in sec.records[: 1 if lay.mode == "zone_files" else None]:
                    self.zones.append(ZoneUnit(rec, entry, len(self.zones) + 1))
        for unit, (bottom, top) in zip(self.zones, self._ranges(self.zones), strict=True):
            unit.bottom, unit.top = bottom, top
        used: set[int] = set()
        rule = self.spec.model.zone.id
        for unit in self.zones:
            ranged = (unit.bottom, unit.top) != (0, 0) or lay.zone_range.mode != "fields"
            candidate = {"bottom": unit.bottom, "top": unit.top, "position": unit.position}[rule]
            if ranged and candidate not in used and (candidate != 0 or rule != "position"):
                unit.zone_id = candidate
                used.add(candidate)
            else:
                unit.zone_id = -unit.position
        by_file = {u.file.name: u for u in self.zones} if lay.mode == "zone_files" else {}
        ranged_units = sorted(
            (u for u in self.zones if (u.bottom, u.top) != (0, 0) or lay.zone_range.mode != "fields"), key=lambda u: u.bottom
        )
        bottoms = [u.bottom for u in ranged_units]
        for entry in self.entries.values():
            for sec in entry.doc.sections:
                if sec.spec is None:
                    continue
                for rec in sec.records:
                    self._owner[id(rec)] = entry
                    if sec.spec.entity not in KINDS:
                        continue
                    key = self.key_of.get(rec.rname)
                    vnum = rec.fields.get(key) if key else None
                    if vnum is None:
                        continue
                    unit = by_file.get(entry.name)
                    if lay.mode == "type_files":
                        i = bisect.bisect_right(bottoms, vnum) - 1
                        unit = ranged_units[i] if i >= 0 and vnum <= ranged_units[i].top else None
                    if unit is None:
                        continue
                    unit.items[sec.spec.entity].append(rec)
                    if self._index[sec.spec.entity].setdefault(vnum, (unit, rec, entry))[1] is not rec:
                        log.warning("%s vnum %s duplicato in %s", sec.spec.entity, vnum, entry.name)

    # ------------------------------------------------------------------ ricerca

    def zone_by_id(self, zone_id: int) -> ZoneUnit | None:
        """La zona con quell'id."""
        return next((z for z in self.zones if z.zone_id == zone_id), None)

    def find(self, kind: str, vnum: int) -> tuple[ZoneUnit, Record] | None:
        """`(zona, record)` per vnum."""
        hit = self._index[kind].get(vnum)
        return (hit[0], hit[1]) if hit else None

    def all_items(self, kind: str) -> list[tuple[ZoneUnit, Record]]:
        """Tutti i record `kind` in ordine di vnum."""
        return [(u, r) for _, (u, r, _) in sorted(self._index[kind].items())]

    def vnums(self, kind: str) -> set[int]:
        """I vnum esistenti di `kind`."""
        return set(self._index[kind])

    def file_of(self, rec: Record) -> FileEntry:
        """Il file che contiene il record."""
        return self._owner[id(rec)]

    def key_value(self, rec: Record) -> int:
        """Vnum (campo chiave) del record."""
        return int(rec.fields[self.key_of[rec.rname]])

    # ------------------------------------------------------------------ modifica

    def ensure_section(self, entry: FileEntry, spec: SectionSpec) -> Section:
        """La sezione `spec` del documento (creata, nell'ordine canonico, se manca)."""
        for sec in entry.doc.sections:
            if sec.spec is spec:
                return sec
        order = self.spec.grammar.files[entry.kind].sections
        rank = order.index(spec)
        new = Section(spec, spec.header or spec.entity)
        at = len(entry.doc.sections)
        for i, sec in enumerate(entry.doc.sections):
            if sec.spec is not None and order.index(sec.spec) > rank:
                at = i
                break
        entry.doc.sections.insert(at, new)
        return new

    def spec_for(self, kind_file: str, entity: str, header: str | None = None) -> SectionSpec | None:
        """La sezione della grammatica di file `kind_file` per `entity` (con `header` se dato)."""
        for sec in self.spec.grammar.files[kind_file].sections:
            if sec.entity == entity and (header is None or sec.header == header):
                return sec
        return None

    def target_file(self, zone: ZoneUnit | None, entity: str) -> tuple[FileEntry, SectionSpec]:
        """File e sezione in cui aggiungere un record `entity` della zona."""
        if self.layout.mode == "zone_files" and zone is not None:
            spec = self.spec_for(zone.file.kind, entity)
            return zone.file, spec  # type: ignore[return-value]
        for entry in self.entries.values():
            spec = self.spec_for(entry.kind, entity)
            if spec is not None:
                return entry, spec
        raise api_error(422, "mapping.no_file_for", entity=entity)

    def make_record(self, zone: ZoneUnit, entity: str, fields: dict[str, Any]) -> Record:
        """Un `Record` nuovo di `entity` (grammatica e stile della sezione in cui andra' nella zona)."""
        _, spec = self.target_file(zone, entity)
        return Record(entity, fields, spec.record, spec.header or "")

    def insert_record(self, zone: ZoneUnit | None, rec: Record, *, sort_key: Any = None) -> FileEntry:
        """Inserisce `rec` nella zona (in coda o ordinato per chiave, secondo `layout.insert`); restituisce il file."""
        entry, spec = self.target_file(zone, rec.entity)
        section = self.ensure_section(entry, spec)
        keyfn = sort_key or (lambda r: r.fields.get(self.key_of.get(r.rname) or "", 0))
        if sort_key is not None or (self.layout.insert == "by_vnum" and self.key_of.get(rec.rname)):
            at = next((i for i, other in enumerate(section.records) if keyfn(other) > keyfn(rec)), len(section.records))
            section.records.insert(at, rec)
        else:
            section.records.append(rec)
        return entry

    def add_record(self, zone: ZoneUnit, entity: str, fields: dict[str, Any]) -> tuple[Record, FileEntry]:
        """Crea e inserisce un record nuovo nella zona."""
        rec = self.make_record(zone, entity, fields)
        return rec, self.insert_record(zone, rec)

    def remove_record(self, rec: Record) -> FileEntry:
        """Toglie `rec` (per identita') dalla sezione che lo contiene; restituisce il file."""
        entry = self.file_of(rec)
        for sec in entry.doc.sections:
            sec.records[:] = [r for r in sec.records if r is not rec]
        return entry

    # ------------------------------------------------------------------ salvataggio

    def render(self, entry: FileEntry) -> bytes:
        """Il file riscritto (record invariati byte per byte)."""
        return write_document(self.spec, entry.kind, entry.doc).encode(entry.doc.encoding)

    def save(self, *entries: FileEntry) -> None:
        """Scrive i file (atomici) e ricarica dal disco quelli scritti; se una scrittura fallisce invalida la cache."""
        try:
            for entry in dict.fromkeys(entries):
                atomic_write_bytes(entry.path, self.render(entry))
        finally:
            for entry in dict.fromkeys(entries):
                self.entries.pop(entry.name, None)
            self._signature = None
            self.refresh()

    def new_file(self, name: str, kind: str, doc: Document, *, listed: bool) -> FileEntry:
        """Scrive un file nuovo (zone_files), lo elenca nell'indice se `listed` e lo restituisce caricato."""
        path = self.safe_path(name)
        doc.encoding = "utf-8"
        atomic_write_bytes(path, write_document(self.spec, kind, doc).encode("utf-8"))
        if self.layout.index:
            self.set_listed(name, listed)
        self._signature = None
        self.refresh()
        return self.entries[name]

    def delete_file(self, entry: FileEntry) -> None:
        """Elimina un file di zona (e la sua riga nell'indice)."""
        if self.layout.index:
            self.set_listed(entry.name, False)
        entry.path.unlink(missing_ok=True)
        self._signature = None
        self.refresh()
