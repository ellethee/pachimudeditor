"""Scrittura: `write_document(doc, ...)` riemette il file.

- record **invariati** (`Record.dirty` falso): testo sorgente byte per byte, cosi' come intestazioni, terminatori
  di sezione, sezioni grezze e coda del file;
- record **nuovi o modificati**: forma canonica ricavata dalla stessa grammatica usata per leggere (un campo per riga,
  salvo i gruppi `line:`; `tagged` come dichiarato), con lo stile di a-capo del documento.
"""

from typing import Any

from pachimudeditor_adapter_mapping import hooks
from pachimudeditor_adapter_mapping.dsl import evaluate
from pachimudeditor_adapter_mapping.grammar import Document, Record, Section, default_value
from pachimudeditor_adapter_mapping.schema import (
    FieldStep,
    FileGrammar,
    LineStep,
    LiteralStep,
    MappingSpec,
    RecordGrammar,
    SwitchStep,
    TaggedStep,
    WhenStep,
)

MAX_BIT = 52


def fix_string(value: Any) -> str:
    """Toglie `\\r` e `~` (che chiuderebbe la stringa), come `fix_string` dei saver ROM."""
    return str(value).replace("\r", "").replace("~", "")


def format_flags(value: int) -> str:
    """`fwrite_flag`: `0`, lettere crescenti A-Z a-z, o decimale se negativo/non rappresentabile."""
    if value == 0:
        return "0"
    if value < 0 or value >> MAX_BIT:
        return str(value)
    return "".join(chr(65 + b) if b < 26 else chr(97 + b - 26) for b in range(MAX_BIT) if value >> b & 1)


def _token(step: FieldStep, value: Any) -> str:
    """Un valore scritto come token del tipo del passo."""
    kind = step.type
    if kind == "string_tilde":
        return fix_string(value) + "~"
    if kind == "word":
        text = str(value)
        return f"'{text}'" if step.quote == "always" or text == "" or any(c.isspace() for c in text) else text
    if kind == "flags":
        return format_flags(int(value)) if step.write == "letters" else str(int(value))
    if kind == "dice":
        return f"{value['n']}d{value['t']}+{value['b']}"
    if kind == "float":
        return format(float(value), "g")
    if kind == "line_text":
        return str(value) if step.raw else str(value).strip()
    text = str(value)
    return text.rjust(step.width) if step.width and kind in ("number", "enum") else text


def _field_names(steps: list[Any]) -> list[str]:
    """Nomi dei campi letti da un elenco di passi (anche dentro i gruppi `line`)."""
    out: list[str] = []
    for step in steps:
        if isinstance(step, FieldStep):
            out.append(step.field)
        elif isinstance(step, LineStep):
            out += _field_names(step.steps)
    return out


class Formatter:
    """Forma canonica di un record secondo la sua grammatica."""

    def __init__(self, spec: MappingSpec) -> None:
        """Usa le grammatiche dei record di `spec`."""
        self.spec = spec

    def tokens(self, steps: list[Any], fields: dict[str, Any]) -> list[str]:
        """Token (senza a-capo tra loro) dei passi: per i gruppi `line` e i campi."""
        out: list[str] = []
        for step in steps:
            if isinstance(step, FieldStep):
                value = fields.get(step.field)
                if value is None:
                    if step.optional and step.default is None:
                        continue  # opzionale senza default: assente resta assente
                    value = default_value(step)  # opzionale con default: sempre scritto (es. quinto numero di `O`)
                for item in value if step.count else [value]:
                    out.append(_token(step, item))
            elif isinstance(step, LiteralStep):
                if not step.optional:
                    out.append(step.literal + ("\x00" if step.glue else ""))
            elif isinstance(step, LineStep):
                out += self.tokens(step.steps, fields)
            elif isinstance(step, WhenStep):
                out += self.tokens(step.then if evaluate(step.when, fields) else step.otherwise, fields)
            elif isinstance(step, SwitchStep):
                out += self.tokens(step.cases.get(str(fields.get(step.switch)), step.default), fields)
        return out

    def lines(self, steps: list[Any], fields: dict[str, Any]) -> list[str]:
        """Righe di testo: un passo semplice = una riga, un gruppo `line` = una riga, i blocchi si espandono."""
        out: list[str] = []
        for step in steps:
            if isinstance(step, FieldStep | LiteralStep | LineStep):
                text = " ".join(self.tokens([step], fields)).replace("\x00 ", "").rstrip("\x00 ")
                if text:
                    out.append(text)
            elif isinstance(step, WhenStep):
                out += self.lines(step.then if evaluate(step.when, fields) else step.otherwise, fields)
            elif isinstance(step, SwitchStep):
                out += self.lines(step.cases.get(str(fields.get(step.switch)), step.default), fields)
            elif isinstance(step, TaggedStep):
                out += self.tagged(step, fields)
        return out

    def tag_item(self, tag: str, spec: Any, item: dict[str, Any]) -> list[str]:
        """Le righe di un elemento: lettera piu' i suoi passi (stessa riga con `inline`/`glue`)."""
        body = self.lines(spec.steps, item)
        if not body:
            return [tag]
        if spec.glue or spec.inline:
            return [tag + ("" if spec.glue else " ") + body[0], *body[1:]]
        return [tag, *body]

    def tagged(self, step: TaggedStep, fields: dict[str, Any]) -> list[str]:
        """Elementi di un blocco `tagged`: liste nell'ordine dei dati, tag scalari se `write_if`."""
        out: list[str] = []
        done: set[str] = set()
        for tag, spec in step.tags.items():
            if spec.into:
                if spec.into in done:
                    continue
                done.add(spec.into)
                for item in fields.get(spec.into, []):
                    letter = item.get(step.tag_field) if step.tag_field else tag
                    out += self.tag_item(letter, step.tags.get(letter, spec), item)
            else:
                names = _field_names(spec.steps)
                present = evaluate(spec.write_if, fields) if spec.write_if else any(fields.get(n) is not None for n in names)
                if present:
                    out += self.tag_item(tag, spec, fields)
        if step.end != "other":
            out.append(step.end)
        return out

    def record(self, rec: Record) -> str:
        """Testo canonico del record (a-capo `\\n`)."""
        rg: RecordGrammar = self.spec.grammar.records[rec.rname]
        if rg.parser:
            return hooks.record_hook(rg.parser).write(rec.fields)
        return "\n".join(self.lines(rg.steps, rec.fields)) + "\n" + "\n" * rg.blank_after


def _nl(text: str, newline: str) -> str:
    """Applica lo stile di a-capo del documento al testo canonico."""
    return text if newline == "\n" else text.replace("\n", newline)


def section_text(spec: MappingSpec, fmt: Formatter, fg: FileGrammar, sec: Section, doc: Document, preserve: bool) -> str:
    """Testo di una sezione."""
    nl = doc.newline
    prefix = fg.header_prefix
    if sec.spec is None:
        return (sec.head if preserve and sec.head is not None else f"{prefix}{sec.name}\n") + sec.raw
    keep = preserve and sec.head is not None
    if sec.head is None and not sec.records and not sec.spec.single:
        return ""  # sezione creata dall'accesso e rimasta vuota
    if not sec.records and sec.spec.single:
        return ""
    head = sec.head if keep else (_nl(f"{prefix}{sec.spec.header}\n", nl) if sec.spec.header else "")
    parts = [head]
    for rec in sec.records:
        parts.append(rec.src if preserve and not rec.dirty and rec.src is not None else _nl(fmt.record(rec), nl))
    parts.append(sec.tail if preserve and sec.tail is not None and (keep or not sec.spec.header) else _nl(sec.spec.tail, nl))
    return "".join(parts)


def write_document(spec: MappingSpec, file_grammar: str, doc: Document, *, preserve: bool = True) -> str:
    """Serializza il documento (vedi docstring del modulo)."""
    fg = spec.grammar.files[file_grammar]
    fmt, nl = Formatter(spec), doc.newline
    out: list[str] = []
    for sec in doc.sections:
        text = section_text(spec, fmt, fg, sec, doc, preserve)
        if text and preserve and sec.head is None and out and fg.sections[0].header is not None:
            if not "".join(out[-2:]).endswith(nl + nl):
                text = nl + text  # sezione nuova: separata dalla precedente da una riga vuota
        out.append(text)
    if doc.has_end and fg.end:
        end = doc.end_head if preserve and doc.end_head is not None else _nl(f"{fg.header_prefix}{fg.end}\n", nl)
        if preserve and doc.end_head is not None and "".join(out[-2:]).endswith(nl + nl):
            end = end.lstrip("\r\n")
        out.append(end)
    out.append(doc.trailer if preserve else "")
    return "".join(out)
