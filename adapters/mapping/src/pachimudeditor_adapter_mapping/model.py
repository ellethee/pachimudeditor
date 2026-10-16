"""Mappatura record <-> DTO neutri: tabelle, campi (`FieldMap`), `extra` e comandi di reset.

Il YAML dichiara per ogni campo del DTO da dove si legge e come si riscrive; qui sta il motore:

- lettura: `hook` | `const` | `pairs` | `expr` | `from` -> conversioni (flag -> nomi, `map`, `null_if`) -> enum del DTO;
- scrittura: inversa. Un patch applica **solo i campi diversi** dal valore corrente (rimandare un DTO letto non
  cambia un byte); i campi senza equivalente accettano solo il valore neutro (422 `mapping.field_unsupported`);
- `extra`: tutti i campi del record non consumati dal DTO, in camelCase, riscrivibili (round trip completo).
"""

import copy
import re
from enum import Enum
from pathlib import Path
from typing import Any

from pachifast.i18n import api_error
from pydantic import BaseModel
from ruamel.yaml import YAML

from pachimudeditor_adapter_mapping import hooks
from pachimudeditor_adapter_mapping.dto import annotation_of, enum_of, neutral_default
from pachimudeditor_adapter_mapping.dsl import evaluate
from pachimudeditor_adapter_mapping.schema import (
    EntityModel,
    FieldMap,
    FieldStep,
    LineStep,
    MappingSpec,
    RecordGrammar,
    ResetCommandModel,
    SwitchStep,
    TaggedStep,
    WhenStep,
)
from pachimudeditor.sdk import ExtraFieldDescriptor
from pachimudeditor.common.adapters.models import Option, ResetCommandDraft, ResetCommandOut

MAX_BIT = 52


def to_camel(name: str) -> str:
    """`room_flags` -> `roomFlags`."""
    head, *rest = name.split("_")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)


def get_path(obj: Any, path: str) -> Any:
    """Valore a `path` (`hit.n`, `ac.0`) dentro dict/liste annidati (`None` se manca)."""
    for part in path.split("."):
        try:
            obj = obj[int(part)] if isinstance(obj, list) else obj.get(part)
        except IndexError, ValueError, AttributeError:
            return None
        if obj is None:
            return None
    return obj


def set_path(obj: dict[str, Any], path: str, value: Any) -> None:
    """Imposta il valore a `path` (come `get_path`); 422 se il percorso non esiste."""
    parts = path.split(".")
    for part in parts[:-1]:
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    last = parts[-1]
    if isinstance(obj, list):
        obj[int(last)] = value
    else:
        obj[last] = value


# --------------------------------------------------------------------------- tabelle


class Table:
    """Una tabella di nomi: flag (nome -> bit), enum (nome -> valore) o lista (indice = valore)."""

    def __init__(self, name: str, values: dict[str, int] | list[str], expose: str | None) -> None:
        """`values` dict o lista di nomi."""
        self.name, self.values, self.expose = name, values, expose
        self.by_value: dict[int, str] = (
            {v: k for k, v in reversed(list(values.items()))} if isinstance(values, dict) else dict(enumerate(values))
        )
        self.by_name: dict[str, int] = values if isinstance(values, dict) else {}
        if isinstance(values, list):
            for i, n in enumerate(values):
                self.by_name.setdefault(n, i)  # nomi doppi: vale il primo

    def flag_names(self, value: int) -> list[str]:
        """Nomi dei bit accesi in ordine di bit; i bit senza nome sono `[A]`, `[b]`, ..."""
        out = []
        for b in range(MAX_BIT):
            if value & (1 << b):
                out.append(self.by_value.get(1 << b) or f"[{chr(65 + b) if b < 26 else chr(97 + b - 26)}]")
        return out

    def flag_value(self, names: list[str]) -> int:
        """Valore dei nomi (o `[X]` per lettere senza nome); 422 `mapping.unknown_flag` se un nome non esiste."""
        value = 0
        for name in names:
            if re.fullmatch(r"\[[A-Za-z]\]", name):
                c = name[1]
                value |= 1 << (ord(c) - 65 if c < "a" else 26 + ord(c) - 97)
            elif name in self.by_name:
                value |= self.by_name[name]
            else:
                raise api_error(422, "mapping.unknown_flag", table=self.name, name=name)
        return value

    def name_of(self, raw: Any) -> str:
        """Nome per un valore grezzo (sconosciuto: il valore come testo)."""
        return self.by_value.get(raw, str(raw)) if isinstance(raw, int) else str(raw)

    def value_of(self, name: str) -> int:
        """Valore di un nome (o di un intero scritto come testo); 422 `mapping.unknown_name` altrimenti."""
        if name in self.by_name:
            return self.by_name[name]
        if re.fullmatch(r"-?\d+", str(name)):
            return int(name)
        raise api_error(422, "mapping.unknown_name", table=self.name, name=name)

    def options(self) -> list[Option]:
        """Opzioni per `enums()` (le voci `unused*` sono escluse)."""
        if isinstance(self.values, dict):
            return [Option(value=bit, label=n) for n, bit in self.values.items() if not n.startswith("unused")]
        return [Option(value=i, label=n) for i, n in enumerate(self.values) if not n.startswith("unused")]


class Tables:
    """Le tabelle della mappatura (inline o lette da file relativo al YAML)."""

    def __init__(self, spec: MappingSpec, base_dir: Path) -> None:
        """Carica ogni tabella."""
        self.tables: dict[str, Table] = {}
        cache: dict[Path, Any] = {}
        for name, ts in spec.tables.items():
            values = ts.values
            if ts.file is not None:
                path = (base_dir / ts.file).resolve()
                if path not in cache:
                    cache[path] = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
                values = self._select(cache[path], ts.name or name, path)
            self.tables[name] = Table(name, values, ts.expose)  # type: ignore[arg-type]

    @staticmethod
    def _select(data: Any, name: str, path: Path) -> dict[str, int] | list[str]:
        """La tabella `name` da un file: dict di tabelle oppure formato `meta/*.json` di basedmud."""
        if isinstance(data, list):
            for item in data:
                table = item.get("table", item)
                if table.get("name") == name:
                    vals = table["values"]
                    if table.get("type") == "flags":
                        return {v["name"]: int(v["bit"]) for v in vals}
                    return [v["name"] for v in sorted(vals, key=lambda v: v["bit"])]
        elif isinstance(data, dict) and name in data:
            raw = data[name]
            return {str(k): int(v) for k, v in raw.items()} if isinstance(raw, dict) else [str(v) for v in raw]
        raise ValueError(f"tabella {name!r} non trovata in {path}")

    def __getitem__(self, name: str) -> Table:
        """La tabella `name`."""
        return self.tables[name]


# --------------------------------------------------------------------------- campi


def step_index(grammar: RecordGrammar) -> dict[str, FieldStep]:
    """Campo -> passo che lo legge (per conoscere tipo e tabella)."""
    index: dict[str, FieldStep] = {}

    def walk(steps: list[Any]) -> None:
        """Visita i passi annidati."""
        for step in steps:
            if isinstance(step, FieldStep):
                index.setdefault(step.field, step)
            elif isinstance(step, LineStep):
                walk(step.steps)
            elif isinstance(step, WhenStep):
                walk(step.then)
                walk(step.otherwise)
            elif isinstance(step, SwitchStep):
                for sub in step.cases.values():
                    walk(sub)
                walk(step.default)
            elif isinstance(step, TaggedStep):
                for ts in step.tags.values():
                    if not ts.into:
                        walk(ts.steps)

    walk(grammar.steps)
    return index


def tagged_lists(steps: list[Any]) -> list[str]:
    """Nomi dei campi-lista in cui i blocchi `tagged` accumulano elementi (`into`), anche annidati."""
    out: list[str] = []
    for step in steps:
        if isinstance(step, LineStep):
            out += tagged_lists(step.steps)
        elif isinstance(step, WhenStep):
            out += tagged_lists(step.then) + tagged_lists(step.otherwise)
        elif isinstance(step, SwitchStep):
            out += [n for sub in (*step.cases.values(), step.default) for n in tagged_lists(sub)]
        elif isinstance(step, TaggedStep):
            for ts in step.tags.values():
                if ts.into:
                    out.append(ts.into)
                out += tagged_lists(ts.steps)
    return out


class Binding:
    """Un campo del DTO legato a un `FieldMap` (o, senza mappatura, al suo valore neutro)."""

    def __init__(self, dto: str, fm: FieldMap | None, annotation: Any, nullable: bool, steps: dict[str, FieldStep], tables: Tables) -> None:
        """`steps` sono i passi del record (per riconoscere flag/enum con tabella)."""
        self.dto, self.fm, self.tables = dto, fm, tables
        self.enum = enum_of(annotation)
        self.is_list = getattr(annotation, "__origin__", None) is list
        self.neutral = neutral_default(annotation, nullable)
        self.nullable = nullable
        self.const = fm is None or "const" in fm.model_fields_set
        self.step = steps.get(fm.from_.split(".")[0]) if fm and fm.from_ else None
        self.table = tables[self.step.table] if self.step and self.step.table else None
        self.map_table = tables[fm.map] if fm and isinstance(fm.map, str) else None
        self.map = {str(k): v for k, v in fm.map.items()} if fm and isinstance(fm.map, dict) else None

    # -- lettura
    def read(self, fields: dict[str, Any]) -> Any:
        """Valore del DTO dal record."""
        fm = self.fm
        if fm is None:
            return self.neutral
        if fm.hook:
            value = hooks.field_hook(fm.hook).read(fields)
        elif self.const:
            value = fm.const
        elif fm.pairs:
            value = self._pairs_read(fields)
        elif fm.expr is not None:
            value = evaluate(fm.expr, fields)
        else:
            value = get_path(fields, fm.from_ or "")
        if self.table is not None and self.is_list and self.step and self.step.type == "flags":
            value = self.table.flag_names(int(value or 0))
        if self.map is not None:
            value = self.map.get(str(value), fm.unmapped if fm.unmapped is not None else value)
        elif self.map_table is not None and value is not None:
            value = self.map_table.name_of(value)
        if fm.null_if is not None and value == fm.null_if:
            value = None
        return self._coerce(value)

    def _coerce(self, value: Any) -> Any:
        """Enum del DTO da nome o valore."""
        if self.enum is None or value is None:
            return value
        if isinstance(value, self.enum):
            return value
        if isinstance(value, str) and value in self.enum.__members__:
            return self.enum[value]
        try:
            return self.enum(value)
        except ValueError:
            return next(iter(self.enum)) if self.fm and self.fm.unmapped is None else self.enum[self.fm.unmapped]

    def _pairs_read(self, fields: dict[str, Any]) -> dict[str, int]:
        """Lista di `{chiave, valore}` come dict `{nome: somma}`."""
        p = self.fm.pairs  # type: ignore[union-attr]
        table = self.tables[p.table] if p.table else None
        out: dict[str, int] = {}
        for item in fields.get(p.list, []):
            key = table.name_of(item.get(p.key)) if table else str(item.get(p.key))
            out[key] = out.get(key, 0) + int(item.get(p.value) or 0)
        return out

    # -- scrittura
    def write(self, fields: dict[str, Any], value: Any, current: Any) -> None:
        """Riscrive il campo del record dal valore del DTO (`current` = valore letto prima, per i campi di sola lettura)."""
        fm = self.fm
        if fm is None or self.const:
            if fm is not None and fm.soft:
                return
            if value != self.read(fields) and not (not value and not self.read(fields)):
                raise api_error(422, "mapping.field_unsupported", field=self.dto)
            return
        raw = (
            value.name if isinstance(value, Enum) and (fm.map is not None or fm.to) else (int(value) if isinstance(value, Enum) else value)
        )
        if fm.null_if is not None and raw is None:
            raw = fm.null_if
        if self.map is not None:
            inverse = next((k for k, v in self.map.items() if v == raw), None)
            if inverse is None:
                raise api_error(422, "mapping.unsupported_value", field=self.dto, value=str(raw))
            raw = int(inverse) if re.fullmatch(r"-?\d+", inverse) else inverse
        elif self.map_table is not None and isinstance(raw, str):
            raw = self.map_table.value_of(raw)
        if fm.hook:
            hooks.field_hook(fm.hook).write(fields, value)
        elif fm.pairs:
            self._pairs_write(fields, raw)
        elif fm.to:
            env = dict(fields) | {"value": raw}
            for target, source in fm.to.items():
                set_path(fields, target, evaluate(source, env))
        elif fm.from_:
            if self.table is not None and self.is_list and self.step and self.step.type == "flags":
                raw = self.table.flag_value(list(raw or []))
            set_path(fields, fm.from_, raw)
        elif not fm.soft and raw != self._plain(current):
            raise api_error(422, "mapping.field_readonly", field=self.dto)

    @staticmethod
    def _plain(value: Any) -> Any:
        """Valore senza enum (per confronti con il grezzo)."""
        return value.name if isinstance(value, Enum) else value

    def _pairs_write(self, fields: dict[str, Any], value: dict[str, int]) -> None:
        """Sostituisce la lista con un elemento per chiave del dict."""
        p = self.fm.pairs  # type: ignore[union-attr]
        table = self.tables[p.table] if p.table else None
        fields[p.list] = [{p.key: table.value_of(k) if table else int(k), p.value: int(v)} for k, v in value.items()]


class EntityMapper:
    """Record di un'entita' <-> campi del DTO piu' `extra`."""

    def __init__(
        self,
        out_cls: type[BaseModel],
        em: EntityModel | Any,
        grammar: RecordGrammar,
        tables: Tables,
        *,
        structural: frozenset[str] = frozenset(),
        children: frozenset[str] = frozenset(),
        consumed: frozenset[str] = frozenset(),
        key_field: str | None = None,
    ) -> None:
        """`structural`: campi del DTO gestiti dall'adapter; `children`: liste del record gestite a parte;
        `consumed`: campi del record usati da altri meccanismi (es. range di zona)."""
        self.tables, self.grammar, self.em = tables, grammar, em
        self.steps = step_index(grammar)
        self.lists = tagged_lists(grammar.steps)
        self.bindings: dict[str, Binding] = {}
        fields = getattr(em, "fields", {})
        for name, info in out_cls.model_fields.items():
            if name in structural or name == "extra":
                continue
            annotation, nullable = annotation_of(info.annotation)
            self.bindings[name] = Binding(name, fields.get(name), annotation, nullable, self.steps, tables)
        used: set[str] = set(consumed)
        for fm in fields.values():
            if fm.from_ and not fm.in_extra:
                used.add(fm.from_.split(".")[0])
            used |= {t.split(".")[0] for t in (fm.to or {}) if not fm.in_extra}
            if fm.pairs:
                used.add(fm.pairs.list)
        extra = getattr(em, "extra", None)
        self.include = extra.include if extra is not None else "all"
        self.hidden = used | set(children) | ({key_field} if key_field else set()) | set(extra.exclude if extra else ())

    # -- extra
    def _extra_names(self, fields: dict[str, Any]) -> list[str]:
        """Campi del record che vanno in `extra`."""
        if self.include == "none":
            return []
        names = [n for n in fields if n not in self.hidden and fields[n] is not None]
        return names if self.include == "all" else [n for n in names if n in self.include]

    def extra_descriptors(self, more: tuple[RecordGrammar, ...] = ()) -> list[ExtraFieldDescriptor]:
        """Le chiavi di `extra` possibili, ricavate dalla grammatica: i campi del record non mappati sul DTO.

        `more`: altre grammatiche della stessa entita' (le zone possono avere stili diversi per file)."""
        if self.include == "none":
            return []
        steps = dict(self.steps)
        lists = list(self.lists)
        for g in more:
            steps = {**step_index(g), **steps}
            lists += tagged_lists(g.steps)
        names = [n for n in (*steps, *lists) if n not in self.hidden]
        if self.include != "all":
            names = [n for n in names if n in self.include]
        out: list[ExtraFieldDescriptor] = []
        for name in dict.fromkeys(names):
            step = steps.get(name)
            table = self.tables[step.table] if step is not None and step.table else None
            kind, enum = "json", None
            if step is not None and step.count is None:
                kind = {"number": "number", "float": "number", "flags": "number" if table is None else "flags"}.get(step.type, "text")
                if step.type == "enum" and table is not None and table.expose:
                    kind = "enum"
                if table is not None and table.expose and kind in ("flags", "enum"):
                    enum = table.expose
            camel = to_camel(name)
            out.append(ExtraFieldDescriptor(name=camel, label_key=f"extra.labels.{camel}", type=kind, enum=enum))  # type: ignore[arg-type]
        return out

    def unsupported_names(self) -> set[str]:
        """Campi del DTO (camelCase) che il MUD non ha: costanti o senza mappatura (valore neutro)."""
        return {to_camel(n) for n, b in self.bindings.items() if b.const}

    def derived_names(self) -> set[str]:
        """Campi del DTO (camelCase) calcolati e non riscrivibili (espressione senza `to`/hook/pairs)."""
        return {
            to_camel(n)
            for n, b in self.bindings.items()
            if not b.const and b.fm is not None and not (b.fm.hook or b.fm.pairs or b.fm.to or b.fm.from_ or b.fm.soft)
        }

    def _extra_value(self, name: str, value: Any) -> Any:
        """Valore di un campo in `extra`: nomi per flag/enum con tabella, `NdT+B` per i dadi."""
        step = self.steps.get(name)
        if step is not None and step.table:
            table = self.tables[step.table]
            if step.type == "flags":
                return table.flag_names(int(value))
            if step.type == "enum":
                return table.name_of(value)
        if step is not None and step.type == "dice" and isinstance(value, dict):
            return f"{value['n']}d{value['t']}+{value['b']}"
        return copy.deepcopy(value)

    def _extra_from(self, name: str, value: Any) -> Any:
        """Inverso di `_extra_value`; 422 `mapping.extra_invalid` se il tipo non torna."""
        step = self.steps.get(name)
        try:
            if step is not None and step.table and step.type == "flags":
                if not isinstance(value, list):
                    raise ValueError
                return self.tables[step.table].flag_value(value)
            if step is not None and step.table and step.type == "enum":
                return self.tables[step.table].value_of(str(value))
            if step is not None and step.type == "dice":
                m = re.fullmatch(r"\s*(-?\d+)d(-?\d+)([+-])(-?\d+)\s*", str(value))
                if not m:
                    raise ValueError
                return {"n": int(m[1]), "t": int(m[2]), "b": int(m[4]) * (-1 if m[3] == "-" else 1)}
            if step is not None and step.type in ("number", "flags") and not isinstance(value, int):
                raise ValueError
            return copy.deepcopy(value)
        except ValueError as error:
            raise api_error(422, "mapping.extra_invalid", key=to_camel(name)) from error

    def extra_of(self, fields: dict[str, Any]) -> dict[str, Any]:
        """`extra` del record."""
        return {to_camel(n): self._extra_value(n, fields[n]) for n in self._extra_names(fields)}

    # -- lettura/scrittura
    def read(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Valori del DTO (nomi Python) piu' `extra`."""
        out = {name: b.read(fields) for name, b in self.bindings.items()}
        out["extra"] = self.extra_of(fields)
        return out

    def apply(self, fields: dict[str, Any], values: dict[str, Any], extra: dict[str, Any] | None = None) -> None:
        """Applica ai campi del record i soli valori diversi dall'attuale (`extra` compreso)."""
        current = self.read(fields)
        for name, value in values.items():
            binding = self.bindings.get(name)
            if binding is None or name == "extra" or value == current[name]:
                continue
            binding.write(fields, value, current[name])
        if extra:
            known = {to_camel(n): n for n in set(fields) | set(self.steps) if n not in self.hidden}
            for key, value in extra.items():
                name = known.get(key)
                if name is None:
                    raise api_error(422, "mapping.extra_unknown", key=key, known=", ".join(sorted(known)))
                if key in current["extra"] and value == current["extra"][key]:
                    continue
                fields[name] = self._extra_from(name, value)

    def new_fields(self, mapping_spec: MappingSpec, record: str) -> dict[str, Any]:
        """Campi di un record nuovo: zeri dei tipi, poi i `defaults` del modello."""
        from pachimudeditor_adapter_mapping.grammar import new_record_fields

        fields = new_record_fields(mapping_spec, record)
        fields.update(copy.deepcopy(getattr(self.em, "defaults", {})))
        return fields


# --------------------------------------------------------------------------- reset


class ResetMapper:
    """Comandi di reset del MUD <-> `ResetCommandOut`/`ResetCommandDraft` neutri."""

    def __init__(self, spec: MappingSpec, tables: Tables) -> None:
        """Un binding per ogni slot dichiarato di ogni comando."""
        from pachimudeditor.common.enums import ZoneCommandType

        self.model = spec.model.reset
        self.letter_of: dict[Any, str] = {}
        self.bindings: dict[str, dict[str, Binding]] = {}
        for letter, cmd in self.model.commands.items():
            self.letter_of[ZoneCommandType[cmd.type]] = letter
            self.bindings[letter] = {
                slot: Binding(slot, getattr(cmd, slot), int, True, {}, tables)
                for slot in ("if_flag", "arg1", "arg2", "arg3", "arg4", "arg_str")
                if getattr(cmd, slot) is not None
            }
        self.type_of = {letter: ZoneCommandType[cmd.type] for letter, cmd in self.model.commands.items()}

    def is_command(self, fields: dict[str, Any]) -> bool:
        """Il record e' un comando mappato (non un commento ne' un comando sconosciuto)."""
        return fields.get(self.model.command_field) in self.model.commands

    def is_comment(self, fields: dict[str, Any]) -> bool:
        """Il record e' una riga di commento."""
        return fields.get(self.model.command_field) in self.model.comments

    def out(self, zone_id: int, index: int, fields: dict[str, Any]) -> ResetCommandOut:
        """DTO di un comando (`id` e `orderIndex` = posizione tra i soli comandi)."""
        letter = fields[self.model.command_field]
        b = self.bindings[letter]
        get = lambda slot: b[slot].read(fields) if slot in b else None  # noqa: E731
        return ResetCommandOut(
            id=index, zone_id=zone_id, order_index=index, command_type=self.type_of[letter],
            if_flag=bool(get("if_flag")), arg1=get("arg1"), arg2=get("arg2"), arg3=get("arg3"), arg4=get("arg4"),
            arg_str=get("arg_str"),
        )  # fmt: skip

    def build(self, command: ResetCommandDraft | Any, new_fields: dict[str, Any]) -> dict[str, Any]:
        """Campi di un record di reset dal comando neutro (422 se il MUD non ha quel tipo di comando)."""
        letter = self.letter_of.get(command.command_type)
        if letter is None:
            raise api_error(422, "mapping.reset_type_unsupported", type=getattr(command.command_type, "name", command.command_type))
        cmd: ResetCommandModel = self.model.commands[letter]
        fields = {**new_fields, **self.model.new_defaults, **copy.deepcopy(cmd.defaults), self.model.command_field: letter}
        for slot, binding in self.bindings[letter].items():
            value = bool(command.if_flag) if slot == "if_flag" else getattr(command, slot)
            binding.write(fields, value, None)
        return fields

    def key(self, zone_id: int, fields: dict[str, Any]) -> tuple[Any, ...]:
        """Identita' del comando come lo vede il DTO (per riconoscere i reset invariati)."""
        o = self.out(zone_id, 0, fields)
        return o.command_type, o.if_flag, o.arg1, o.arg2, o.arg3, o.arg4, o.arg_str
