"""Motore di parsing: legge un file di testo secondo la grammatica del YAML e produce un albero di record.

Il cursore (`Cursor`) replica i primitivi di lettura dei server Diku/ROM (`fread_number`, `fread_flag`,
`fread_word`, `fread_string`, ...): token separati da spazi bianchi, stringhe terminate da `~`.

Ogni `Record` ricorda il testo sorgente (`src`, comprese le righe vuote che lo precedono) e un'impronta dei campi
(`fp`): finche' non cambia, `writer.write_document` lo riemette byte per byte. Intestazioni e terminatori di sezione
sono conservati come testo (`Section.head`/`tail`), il resto del file dopo il marcatore finale in `Document.trailer`.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from pachimudeditor_adapter_mapping import hooks
from pachimudeditor_adapter_mapping.dsl import evaluate
from pachimudeditor_adapter_mapping.schema import (
    FieldStep,
    FileGrammar,
    LineStep,
    LiteralStep,
    MappingSpec,
    RecordGrammar,
    SectionSpec,
    SwitchStep,
    TaggedStep,
    WhenStep,
)

_WS = " \t\n\r\f\v"
_DICE = re.compile(r"(-?\d+)[dD](-?\d+)([+-])(-?\d+)")
_DICE_TOLERANT = re.compile(r"(-?\d+)?[dD](-?\d+)(?:([+-])(-?\d+))?")
_FLOAT = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")
_RAW_END = re.compile(r"^#[A-Za-z$]", re.MULTILINE)
_LETTERS = {c: 1 << (ord(c) - 65) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"} | {
    c: 1 << (26 + ord(c) - 97) for c in "abcdefghijklmnopqrstuvwxyz"
}


class MappingParseError(ValueError):
    """Errore di sintassi in un file di dati, con riga, colonna e contesto (record)."""

    def __init__(self, message: str, line: int, column: int, context: str = "", filename: str | None = None) -> None:
        """Compone `file: riga N, colonna M [contesto]: messaggio`."""
        self.line, self.column, self.context, self.filename = line, column, context, filename
        where = f"{filename}: " if filename else ""
        ctx = f" [{context}]" if context else ""
        super().__init__(f"{where}riga {line}, colonna {column}{ctx}: {message}")


class _EndSection(Exception):
    """Segnale interno: il record appena letto e' il terminatore della sezione."""


@dataclass(eq=False)
class Record:
    """Un record parsato: campi (dict, liste annidate di dict), sorgente e impronta per la scrittura fedele."""

    entity: str
    fields: dict[str, Any]
    rname: str = ""
    """Nome della grammatica del record (`grammar.records`)."""
    style: str = ""
    """Marcatore della sezione (distingue `AREA` da `AREADATA`)."""
    src: str | None = None
    fp: str | None = None

    def seal(self, src: str) -> "Record":
        """Associa il sorgente e l'impronta dei campi attuali."""
        self.src, self.fp = src, repr(self.fields)
        return self

    @property
    def dirty(self) -> bool:
        """Nuovo o modificato dopo il parsing (va riscritto in forma canonica)."""
        return self.src is None or self.fp != repr(self.fields)


@dataclass(eq=False)
class Section:
    """Una sezione: intestazione, record, terminatore (testi originali se letti da file)."""

    spec: SectionSpec | None
    name: str
    records: list[Record] = field(default_factory=list)
    head: str | None = None
    tail: str | None = None
    raw: str = ""
    """Corpo di una sezione sconosciuta (`spec is None`), riemesso identico."""


@dataclass(eq=False)
class Document:
    """Un file parsato."""

    sections: list[Section] = field(default_factory=list)
    end_head: str | None = None
    has_end: bool = False
    trailer: str = ""
    newline: str = "\n"
    encoding: str = "utf-8"
    filename: str | None = None


class Cursor:
    """Cursore sul testo con i primitivi di lettura dei server Diku/ROM."""

    def __init__(self, text: str, filename: str | None = None) -> None:
        """Parte dall'inizio del testo."""
        self.text, self.n, self.i, self.filename, self.context = text, len(text), 0, filename, ""

    # -- errori e posizione
    def error(self, message: str, pos: int | None = None) -> MappingParseError:
        """Errore alla posizione `pos` (default: corrente) con riga/colonna."""
        p = min(self.i if pos is None else pos, self.n)
        line = self.text.count("\n", 0, p) + 1
        return MappingParseError(message, line, p - (self.text.rfind("\n", 0, p) + 1) + 1, self.context, self.filename)

    # -- spazi e sbirciate
    def skip_ws(self) -> None:
        """Salta gli spazi bianchi (a-capo compresi)."""
        while self.i < self.n and self.text[self.i] in _WS:
            self.i += 1

    def peek_pos(self, same_line: bool = False) -> int | None:
        """Posizione del prossimo carattere non bianco (`None` a fine file o, con `same_line`, a fine riga)."""
        j = self.i
        while j < self.n and self.text[j] in _WS:
            if same_line and self.text[j] == "\n":
                return None
            j += 1
        return j if j < self.n else None

    def peek(self) -> str:
        """Prossimo carattere non bianco senza consumarlo ('' a fine file)."""
        j = self.peek_pos()
        return self.text[j] if j is not None else ""

    def eof(self) -> bool:
        """Solo spazi bianchi fino alla fine."""
        return self.peek_pos() is None

    def end_item(self) -> None:
        """Consuma il resto della riga se bianco (compreso l'a-capo): chiude un record."""
        j = self.i
        while j < self.n and self.text[j] in " \t\f\v":
            j += 1
        if j >= self.n:
            self.i = j
        elif self.text[j] == "\r" and self.text[j + 1 : j + 2] == "\n":
            self.i = j + 2
        elif self.text[j] in "\r\n":
            self.i = j + 1

    # -- primitivi
    def letter(self) -> str:
        """`fread_letter`: salta gli spazi e consuma un carattere."""
        self.skip_ws()
        if self.i >= self.n:
            raise self.error("fine file inattesa")
        self.i += 1
        return self.text[self.i - 1]

    def number(self) -> int:
        """`fread_number`: intero con segno e somme `a|b` (un eventuale spazio finale e' consumato)."""
        self.skip_ws()
        start, sign = self.i, False
        if self.i < self.n and self.text[self.i] == "+":
            self.i += 1
        elif self.i < self.n and self.text[self.i] == "-":
            sign = True
            self.i += 1
        j = self.i
        while j < self.n and "0" <= self.text[j] <= "9":
            j += 1
        if j == self.i:
            raise self.error("numero atteso", start)
        value = int(self.text[self.i : j])
        self.i = j
        value = -value if sign else value
        if self.i < self.n and self.text[self.i] == "|":
            self.i += 1
            value += self.number()
        elif self.i < self.n and self.text[self.i] == " ":
            self.i += 1
        return value

    def flags(self) -> int:
        """`fread_flag`: lettere (`A`=1 ... `a`=2^26), numeri e somme `a|b`."""
        self.skip_ws()
        start, negative, value, consumed = self.i, False, 0, False
        if self.i < self.n and self.text[self.i] == "-":
            negative = True
            self.i += 1
        if not (self.i < self.n and "0" <= self.text[self.i] <= "9"):
            while self.i < self.n and self.text[self.i] in _LETTERS:
                value += _LETTERS[self.text[self.i]]
                self.i += 1
                consumed = True
        while self.i < self.n and "0" <= self.text[self.i] <= "9":
            value = value * 10 + int(self.text[self.i])
            self.i += 1
            consumed = True
        if not consumed:
            raise self.error("flag atteso", start)
        value = -value if negative else value
        if self.i < self.n and self.text[self.i] == "|":
            self.i += 1
            value += self.flags()
        elif self.i < self.n and self.text[self.i] == " ":
            self.i += 1
        return value

    def word(self) -> str:
        """`fread_word`: parola separata da spazi, oppure tra apici (`'..'`/`".."`, apici esclusi)."""
        self.skip_ws()
        if self.i >= self.n:
            raise self.error("parola attesa, fine file")
        c = self.text[self.i]
        if c in "'\"":
            end = self.text.find(c, self.i + 1)
            if end < 0:
                raise self.error("apice non chiuso")
            word, self.i = self.text[self.i + 1 : end], end + 1
            return word
        j = self.i
        while j < self.n and self.text[j] not in _WS:
            j += 1
        word, self.i = self.text[self.i : j], j
        return word

    def string(self, lead: str = "ws") -> str:
        """`fread_string`: testo fino a `~` (esclusa). `ws` salta gli spazi iniziali; `eol` solo il resto bianco
        della riga corrente (i rientri delle descrizioni restano)."""
        if lead == "ws":
            self.skip_ws()
        else:
            j = self.i
            while j < self.n and self.text[j] in " \t\f\v\r":
                j += 1
            if j < self.n and self.text[j] == "\n":
                self.i = j + 1
            elif j >= self.n:
                self.i = j
        start = self.i
        end = self.text.find("~", start)
        if end < 0:
            raise self.error("stringa senza '~' finale", start)
        self.i = end + 1
        return self.text[start:end].replace("\r", "")

    def rest_of_line(self, raw: bool = False) -> str:
        """Testo fino a fine riga (a-capo consumato, escluso dal risultato)."""
        j = self.i
        while j < self.n and self.text[j] not in "\r\n":
            j += 1
        s = self.text[self.i : j]
        if j < self.n:
            j += 2 if self.text[j] == "\r" and self.text[j + 1 : j + 2] == "\n" else 1
        self.i = j
        return s if raw else s.strip()

    def float_(self) -> float:
        """Numero decimale."""
        self.skip_ws()
        m = _FLOAT.match(self.text, self.i)
        if not m:
            raise self.error("numero decimale atteso")
        self.i = m.end()
        return float(m.group())

    def dice(self, tolerant: bool) -> dict[str, int]:
        """`NdT+B` come `{n, t, b}`. Con `tolerant` accetta `NdT` e `dT+B`."""
        self.skip_ws()
        m = (_DICE_TOLERANT if tolerant else _DICE).match(self.text, self.i)
        if not m:
            raise self.error("dado atteso (NdT+B)")
        self.i = m.end()
        n, t, sign, bonus = m.groups()
        b = int(bonus) if bonus is not None else 0
        return {"n": int(n) if n is not None else 1, "t": int(t), "b": -b if sign == "-" else b}

    def literal(self, text: str, optional: bool = False) -> bool:
        """Consuma il token fisso `text` (se `optional` e assente non fa nulla e restituisce `False`)."""
        pos = self.peek_pos()
        if pos is not None and self.text.startswith(text, pos):
            self.i = pos + len(text)
            return True
        if optional:
            return False
        raise self.error(f"atteso {text!r}")


def default_value(step: FieldStep) -> Any:
    """Valore di un campo in un record nuovo: `default` del passo o lo zero del tipo."""
    if step.default is not None:
        base = step.default
    else:
        base = {
            "number": 0, "float": 0.0, "word": "", "string_tilde": "", "line_text": "", "flags": 0,
            "tag": "", "enum": 0 if step.as_ == "number" else "",
        }.get(step.type)  # fmt: skip
        if step.type == "dice":
            base = {"n": 0, "t": 0, "b": 0}
    return [base if not isinstance(base, dict) else dict(base) for _ in range(step.count)] if step.count else base


def _word_end(text: str, pos: int) -> int:
    """Fine del token che inizia a `pos`."""
    while pos < len(text) and text[pos] not in _WS:
        pos += 1
    return pos


class Parser:
    """Interpreta un testo secondo una `MappingSpec`."""

    def __init__(self, spec: MappingSpec, cur: Cursor) -> None:
        """`cur` e' il cursore sul testo del file."""
        self.spec, self.cur = spec, cur
        self.records = spec.grammar.records
        self._top: dict[str, Any] | None = None
        self._until: Any = None
        self._key: tuple[str, str] | None = None
        """`(campo chiave, nome del record)` del record in lettura: dopo il vnum il contesto degli errori lo include."""

    # -- passi
    def field(self, step: FieldStep, fields: dict[str, Any]) -> None:
        """Legge un campo (o `count` valori) e lo mette in `fields`."""
        cur = self.cur
        if step.optional:
            pos = cur.peek_pos(step.same_line)
            if pos is None or not self._looks_like(step, pos):
                return
        if step.count:
            fields[step.field] = [self.primitive(step) for _ in range(step.count)]
        else:
            fields[step.field] = value = self.primitive(step)
            if fields is self._top and self._key and step.field == self._key[0]:
                cur.context = f"{self._key[1]} {value}"
            if fields is self._top and self._until is not None and step.field == self._until.field and value in self._until.in_:
                raise _EndSection

    def _looks_like(self, step: FieldStep, pos: int) -> bool:
        """Il token a `pos` e' del tipo del passo? (campi `optional`)"""
        ch = self.cur.text[pos]
        if step.type in ("number", "enum") and (step.type == "number" or step.as_ == "number"):
            return ch.isdigit() or (ch in "+-" and self.cur.text[pos + 1 : pos + 2].isdigit())
        if step.type == "flags":
            return ch.isalnum() or ch == "-"
        if step.type == "dice":
            return bool((_DICE_TOLERANT if step.tolerant else _DICE).match(self.cur.text, pos))
        if step.type == "float":
            return bool(_FLOAT.match(self.cur.text, pos))
        return True

    def primitive(self, step: FieldStep) -> Any:
        """Un valore del tipo del passo."""
        cur, kind = self.cur, step.type
        if kind == "number":
            return cur.number()
        if kind == "string_tilde":
            return cur.string(step.lead)
        if kind == "flags":
            return cur.flags()
        if kind == "word":
            return cur.word()
        if kind == "line_text":
            return cur.rest_of_line(step.raw)
        if kind == "dice":
            return cur.dice(step.tolerant)
        if kind == "tag":
            return cur.letter()
        if kind == "float":
            return cur.float_()
        return cur.number() if step.as_ == "number" else cur.word()  # enum

    def run(self, steps: list[Any], fields: dict[str, Any]) -> None:
        """Esegue i passi riempiendo `fields`."""
        for step in steps:
            if isinstance(step, FieldStep):
                self.field(step, fields)
            elif isinstance(step, LiteralStep):
                self.cur.literal(step.literal, step.optional)
            elif isinstance(step, LineStep):
                self.run(step.steps, fields)
            elif isinstance(step, WhenStep):
                self.run(step.then if evaluate(step.when, fields) else step.otherwise, fields)
            elif isinstance(step, SwitchStep):
                self.run(step.cases.get(str(fields.get(step.switch)), step.default), fields)
            elif isinstance(step, TaggedStep):
                self.tagged(step, fields)

    def tagged(self, step: TaggedStep, fields: dict[str, Any]) -> None:
        """Elementi introdotti da un tag, fino al terminatore (`end`) o al primo token estraneo."""
        cur = self.cur
        keys = sorted((k for k in step.tags if k != "?"), key=len, reverse=True)
        fold = (lambda t: t.lower()) if step.ignore_case else (lambda t: t)
        for spec in step.tags.values():
            if spec.into:
                fields.setdefault(spec.into, [])
            else:
                for s in spec.steps:
                    for f in [s] if isinstance(s, FieldStep) else s.steps if isinstance(s, LineStep) else []:
                        if isinstance(f, FieldStep) and f.default is not None:
                            fields.setdefault(f.field, default_value(f))
        while True:
            pos = cur.peek_pos()
            if pos is None:
                if step.end != "other":
                    raise cur.error(f"fine file: manca {step.end!r}")
                return
            rest = fold(cur.text[pos : pos + 64])
            if any(rest.startswith(fold(t)) for t in step.end_before):
                return
            if step.end != "other" and rest.startswith(fold(step.end)):
                cur.i = pos + len(step.end)
                cur.end_item()
                return
            tag = next((k for k in keys if rest.startswith(fold(k))), None)
            spec = step.tags.get(tag) if tag is not None else None
            if spec is None and "?" in step.tags:
                tag, spec = (cur.text[pos : _word_end(cur.text, pos)]), step.tags["?"]
            if spec is None or tag is None:
                if step.end == "other":
                    return
                raise cur.error(f"tag non valido (attesi {', '.join(step.tags)} o {step.end!r})", pos)
            cur.i = pos + len(tag)
            target: dict[str, Any] = {} if spec.into else fields
            if step.tag_field and spec.into:
                target[step.tag_field] = tag
            self.run(spec.steps, target)
            if spec.into:
                fields[spec.into].append(target)
            if step.end != "other":
                cur.end_item()

    # -- record e sezioni
    def record(self, section: SectionSpec) -> Record | None:
        """Un record della sezione; `None` se e' il terminatore (consumato)."""
        rg: RecordGrammar = self.records[section.record]
        fields: dict[str, Any] = {}
        self._top, self._until = fields, section.until if section.until and section.until.field else None
        self._key = (rg.key, section.record) if rg.key else None
        self.cur.context = section.record
        try:
            if rg.parser:
                hook = hooks.record_hook(rg.parser)
                result = hook.parse(self.cur)
                if result is None:
                    return None
                fields = result
            else:
                self.run(rg.steps, fields)
        except _EndSection:
            return None
        finally:
            self._top = None
        return Record(section.entity, fields, section.record, section.header or "")

    def section_records(self, section: SectionSpec) -> tuple[list[Record], str]:
        """`(record, testo del terminatore)` della sezione."""
        cur, records = self.cur, []
        if section.single:
            start = cur.i
            rec = self.record(section)
            cur.end_item()
            if rec is not None:
                records.append(rec.seal(cur.text[start : cur.i]))
            return records, ""
        while True:
            start = cur.i
            if section.until and section.until.peek_not is not None:
                ch = cur.peek()
                if ch != section.until.peek_not:
                    marker = section.until.tail_starts_with
                    if marker is not None and not cur.text.startswith(marker, cur.peek_pos() or cur.n):
                        raise cur.error(f"atteso {section.until.peek_not!r} (nuovo record) oppure {marker!r} (fine file)", cur.peek_pos())
                    cur.i = cur.n
                    return records, cur.text[start:]
            elif cur.eof() and section.until is None:
                cur.i = cur.n
                return records, cur.text[start:]
            elif cur.eof():
                raise cur.error(f"fine file nella sezione {section.header or section.entity}: terminatore mancante")
            rec = self.record(section)
            cur.end_item()
            if rec is None:
                return records, cur.text[start : cur.i]
            records.append(rec.seal(cur.text[start : cur.i]))

    def document(self, fg: FileGrammar) -> Document:
        """Interpreta l'intero file."""
        cur, text = self.cur, self.cur.text
        doc = Document(newline="\r\n" if "\r\n" in text else "\n", filename=cur.filename)
        prefix = fg.header_prefix
        if len(fg.sections) == 1 and fg.sections[0].header is None:  # file di un solo tipo di record, senza intestazioni
            section = fg.sections[0]
            records, tail = self.section_records(section)
            doc.sections.append(Section(section, section.entity, records, "", tail))
            return doc
        by_header = {s.header.upper(): s for s in fg.sections if s.header}
        while True:
            start = cur.i
            cur.context = ""
            if cur.eof():
                doc.trailer = text[start:]
                cur.i = cur.n
                return doc
            if cur.letter() != prefix:
                raise cur.error(f"{prefix!r} atteso all'inizio di una sezione", cur.i - 1)
            name = cur.word()
            if not name:
                raise cur.error("nome sezione mancante")
            if fg.end and name.upper() == fg.end.upper():
                cur.end_item()
                doc.has_end, doc.end_head, doc.trailer = True, text[start : cur.i], text[cur.i :]
                cur.i = cur.n
                return doc
            cur.end_item()
            head = text[start : cur.i]
            spec = by_header.get(name.upper())
            if spec is None:
                if fg.unknown_sections == "error":
                    raise cur.error(f"sezione sconosciuta: {name}")
                m = _RAW_END.search(text, cur.i)
                end = m.start() if m else cur.n
                doc.sections.append(Section(None, name, head=head, raw=text[cur.i : end]))
                cur.i = end
                continue
            cur.context = spec.header or ""
            records, tail = self.section_records(spec)
            doc.sections.append(Section(spec, spec.header or "", records, head, tail))


def parse_document(spec: MappingSpec, file_grammar: str, text: str, filename: str | None = None) -> Document:
    """Interpreta `text` con la grammatica di file `file_grammar`.

    Raises:
        MappingParseError: sintassi non valida (riga, colonna e record).
    """
    return Parser(spec, Cursor(text, filename)).document(spec.grammar.files[file_grammar])


def new_record_fields(spec: MappingSpec, record: str) -> dict[str, Any]:
    """Campi di un record nuovo: zero dei tipi per i passi incondizionati e liste vuote per i tag."""
    fields: dict[str, Any] = {}

    def walk(steps: list[Any]) -> None:
        """Passi incondizionati (le diramazioni `when`/`switch` non sono inizializzate)."""
        for step in steps:
            if isinstance(step, FieldStep) and not step.optional:
                fields[step.field] = default_value(step)
            elif isinstance(step, LineStep):
                walk(step.steps)
            elif isinstance(step, TaggedStep):
                for ts in step.tags.values():
                    if ts.into:
                        fields.setdefault(ts.into, [])

    walk(spec.grammar.records[record].steps)
    return fields
