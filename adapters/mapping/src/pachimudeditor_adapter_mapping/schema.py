"""Schema Pydantic del file di mappatura (`kind: mapping`) e suo caricamento con errori leggibili.

Il YAML ha le sezioni `layout`, `grammar`, `tables`, `model`, `hooks`, `rules` (vedi `docs/adapters/index.md`, sezione
MappingAdapter, e `docs/adapters/mapping-guide.md`). Qui:

- i modelli di validazione (`MappingSpec` e figli): chiavi sconosciute rifiutate, tipi controllati;
- `normalize_step`: la sintassi compatta dei passi della grammatica (`- nome: string_tilde`) diventa il modello esteso;
- `load_mapping(path)`: legge il YAML con ruamel (per avere i numeri di riga), valida, controlla i riferimenti
  incrociati (record, tabelle, campi, espressioni, hook) e solleva `MappingConfigError` con `file:riga` per ogni problema;
- `json_schema()`: JSON Schema per l'autocompletamento nell'editor (file `mapping.schema.json` accanto a questo modulo).
"""

import json
from pathlib import Path
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, model_validator
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from pachimudeditor_adapter_mapping import hooks
from pachimudeditor_adapter_mapping.dsl import ExprError, names_in
from pachimudeditor_adapter_mapping.dto import DTO_OUT, annotation_of, enum_of

PRIMITIVES = ("number", "float", "word", "string_tilde", "line_text", "flags", "dice", "tag", "enum")
"""Primitive di campo della grammatica."""

SCHEMA_FILE = Path(__file__).with_name("mapping.schema.json")


class MappingConfigError(ValueError):
    """Mappatura non valida: il messaggio elenca ogni problema con `file:riga`."""


class _M(BaseModel):
    """Base: chiavi sconosciute rifiutate (un refuso nel YAML e' un errore, non un campo ignorato)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --------------------------------------------------------------------------- passi della grammatica


class FieldStep(_M):
    """Un campo tipizzato letto/scritto dal record."""

    kind: Literal["field"] = "field"
    field: str
    type: Literal["number", "float", "word", "string_tilde", "line_text", "flags", "dice", "tag", "enum"]
    table: str | None = None
    """Tabella dei nomi (flag `A|B`, enum): usata dal modello per mostrare nomi invece di numeri."""
    count: int | None = Field(default=None, ge=1)
    """Ripete il primitivo `count` volte e produce una lista."""
    optional: bool = False
    """Se il prossimo token non e' del tipo atteso il campo manca (`None`); scritto solo se presente."""
    same_line: bool = False
    """Con `optional`: considera solo i token della riga corrente (es. quarto argomento di un reset)."""
    default: Any = None
    """Valore dei record nuovi; con `optional` il campo, se assente, e' comunque scritto con questo valore."""
    width: int | None = None
    """Scrittura: allinea a destra il numero su `width` caratteri."""
    quote: Literal["auto", "always"] = "auto"
    """`word`: in scrittura apici attorno al valore se vuoto/con spazi (`auto`) o sempre."""
    lead: Literal["ws", "eol"] = "ws"
    """`string_tilde`: `ws` salta tutti gli spazi iniziali (ROM), `eol` solo fino al primo a-capo (Diku)."""
    write: Literal["letters", "number"] = "letters"
    """`flags`: scrittura a lettere (`ABV`, ROM) o come numero (Diku)."""
    as_: Literal["number", "word"] = Field(default="number", alias="as")
    """`enum`: il token e' un numero o una parola."""
    raw: bool = False
    """`line_text`: conserva il testo cosi' com'e' (senza `strip`)."""
    tolerant: bool = False
    """`dice`: accetta `NdT` senza bonus e `dT+B` senza numero di dadi (irregolarita' note)."""


class LiteralStep(_M):
    """Un token fisso (es. `#`, `S`, `H`)."""

    kind: Literal["literal"] = "literal"
    literal: str
    optional: bool = False
    glue: bool = False
    """Scrittura: nessuno spazio tra il token fisso e il successivo (`#3001`)."""


class LineStep(_M):
    """Gruppo di passi scritti sulla stessa riga (in lettura non cambia nulla: i token sono separati da spazi)."""

    kind: Literal["line"] = "line"
    steps: list["Step"]


class WhenStep(_M):
    """Blocco condizionale: `when` e' un'espressione sui campi gia' letti (anche in scrittura)."""

    kind: Literal["when"] = "when"
    when: str
    then: list["Step"]
    otherwise: list["Step"] = Field(default_factory=list, alias="else")


class SwitchStep(_M):
    """Sceglie i passi in base al valore di un campo gia' letto (es. lettera del comando)."""

    kind: Literal["switch"] = "switch"
    switch: str
    cases: dict[str, list["Step"]]
    default: list["Step"] = Field(default_factory=list)


class TagSpec(_M):
    """Un elemento introdotto da una lettera dentro un blocco `tagged`."""

    into: str | None = None
    """Nome del campo-lista del record in cui accumulare gli elementi (dict di campi). Senza: campi scalari."""
    steps: list["Step"] = Field(default_factory=list)
    write_if: str | None = None
    """Scrittura di un tag scalare: espressione (default: scritto se un suo campo non e' `None`)."""
    inline: bool = False
    """Scrittura: lettera e prima riga dei passi sulla stessa riga."""
    glue: bool = False
    """Scrittura: lettera e primo token senza spazio (`D0`)."""


class TaggedStep(_M):
    """Elementi introdotti da una lettera (prima lettera del prossimo token), in qualunque ordine."""

    kind: Literal["tagged"] = "tagged"
    end: str = "other"
    """`other`: finisce al primo token che non e' un tag noto (non consumato); altro testo (`S`): token terminatore."""
    end_before: list[str] = Field(default_factory=list)
    """Tolleranza: finisce (senza consumare) anche se il prossimo token inizia con uno di questi testi (es. `#`:
    record successivo quando manca il terminatore `S`). In scrittura il terminatore e' sempre riscritto."""
    tag_field: str | None = None
    """Campo in cui memorizzare il tag dell'elemento (serve quando piu' tag finiscono nella stessa lista)."""
    ignore_case: bool = False
    """Il tag e' riconosciuto senza distinguere maiuscole/minuscole (`Name`, `NAME`)."""
    tags: dict[str, TagSpec]
    """Tag -> elemento. Un tag e' il prefisso (il piu' lungo) del prossimo token; il tag speciale `?` raccoglie
    qualunque altro token (memorizzato in `tag_field`)."""


def normalize_step(raw: Any) -> Any:
    """Dalla sintassi compatta (`- nome: tipo`, `- nome: {type: ..}`, `- line: [...]`) al modello esteso con `kind`."""
    if not isinstance(raw, dict) or raw.get("kind") in ("field", "literal", "line", "when", "switch", "tagged"):
        return raw
    if "field" in raw:
        return {"kind": "field", **raw}
    if "literal" in raw:
        return {"kind": "literal", **raw}
    if set(raw) == {"line"}:
        return {"kind": "line", "steps": raw["line"]}
    if "when" in raw:
        return {"kind": "when", **raw}
    if "switch" in raw:
        return {"kind": "switch", **raw}
    if set(raw) == {"tagged"}:
        return {"kind": "tagged", **raw["tagged"]}
    if len(raw) == 1:
        name, spec = next(iter(raw.items()))
        if isinstance(spec, str):
            return {"kind": "field", "field": name, "type": spec}
        if isinstance(spec, dict):
            return {"kind": "field", "field": name, **spec}
    return raw


Step = Annotated[
    Union[FieldStep, LiteralStep, LineStep, WhenStep, SwitchStep, TaggedStep],  # noqa: UP007
    Field(discriminator="kind"),
    BeforeValidator(normalize_step),
]
"""Un passo di grammatica (sintassi compatta o estesa)."""

for _cls in (LineStep, WhenStep, SwitchStep, TagSpec, TaggedStep):
    _cls.model_rebuild(_types_namespace={"Step": Step})


class RecordGrammar(_M):
    """Grammatica di un record: sequenza di passi, chiave (vnum) e hook di parsing/scrittura opzionale."""

    key: str | None = None
    """Campo che identifica il record (vnum): serve per gli indici e il controllo dei duplicati."""
    steps: list[Step] = Field(default_factory=list)
    parser: str | None = None
    """Nome di un hook registrato che sostituisce parsing e scrittura dei `steps` (casi che la grammatica non copre)."""
    blank_after: int = 0
    """Righe vuote dopo il record nella forma canonica."""


class Until(_M):
    """Come finisce una sezione di record."""

    field: str | None = None
    in_: list[Any] = Field(default_factory=list, alias="in")
    """Finisce quando il campo `field` appena letto vale uno di questi valori (terminatore `#0`, `S`, `$`)."""
    peek_not: str | None = None
    """Finisce quando il prossimo carattere non bianco non e' questo (es. `#` nei file `.mob` che chiudono con `%%`)."""
    tail_starts_with: str | None = None
    """Con `peek_not`: il testo che segue deve iniziare cosi' (`%%`), altrimenti e' un errore di sintassi: evita che un
    record malformato sia scambiato per la fine del file."""

    @model_validator(mode="after")
    def _one_rule(self) -> "Until":
        """Serve `field`+`in` oppure `peek_not`."""
        if bool(self.field) == (self.peek_not is not None):
            raise ValueError("indicare `field` con `in`, oppure `peek_not`")
        return self


class SectionSpec(_M):
    """Una sezione di un file: intestazione opzionale (`#MOBILES`), record di un'entita', terminatore."""

    header: str | None = None
    """Nome dell'intestazione (senza prefisso); assente = file/sezione unica senza intestazione."""
    record: str
    entity: str
    """Entita' del modello (zone, room, mob, object, reset, shop, ...) cui appartengono i record."""
    until: Until | None = None
    single: bool = False
    """Un solo record (intestazione di zona)."""
    tail: str = ""
    """Testo canonico del terminatore quando va riscritto (`#0\\n\\n`)."""


class FileGrammar(_M):
    """Struttura di un tipo di file: sezioni in ordine canonico, terminatore di file, sezioni sconosciute."""

    header_prefix: str = "#"
    sections: list[SectionSpec]
    end: str | None = None
    """Nome dell'intestazione che chiude il file (`$` per `#$`); il testo successivo e' conservato."""
    unknown_sections: Literal["raw", "error"] = "raw"
    """Sezioni non descritte: conservate come testo grezzo (`raw`) oppure errore."""


class Grammar(_M):
    """`files` (tipi di file) e `records` (grammatiche dei record)."""

    files: dict[str, FileGrammar]
    records: dict[str, RecordGrammar]


# --------------------------------------------------------------------------- tabelle


class TableSpec(_M):
    """Tabella di nomi: flag (nome -> bit), enum (nome -> valore) o lista di tipi (indice = valore)."""

    values: dict[str, int] | list[str] | None = None
    file: str | None = None
    """File con la tabella (JSON/YAML, percorso relativo al YAML di mappatura): formato `meta/*.json` di basedmud
    (`[{table: {name, values: [{name, bit}]}}]`, scelta con `name`) oppure un dict/lista semplice."""
    name: str | None = None
    expose: str | None = None
    """Chiave con cui la tabella compare in `GET /api/meta/enums` (e `enum` nei descrittori dei campi)."""

    @model_validator(mode="before")
    @classmethod
    def _shorthand(cls, raw: Any) -> Any:
        """`nome: {A: 1, B: 2}` o `nome: [a, b]` senza opzioni."""
        if isinstance(raw, list) or (isinstance(raw, dict) and not set(raw) <= {"values", "file", "name", "expose"}):
            return {"values": raw}
        return raw

    @model_validator(mode="after")
    def _source(self) -> "TableSpec":
        """Valori inline oppure file."""
        if (self.values is None) == (self.file is None):
            raise ValueError("indicare `values` oppure `file`")
        return self


# --------------------------------------------------------------------------- modello neutro


class PairsSpec(_M):
    """Lista di elementi `{chiave, valore}` del record vista come dict (`affects: {nome_apply: somma}`)."""

    list: str
    key: str
    value: str
    table: str | None = None
    """Tabella con cui il campo `key` (numero) diventa un nome."""


class FieldMap(_M):
    """Come un campo del DTO neutro si ricava dal record (lettura) e vi si riscrive (scrittura)."""

    from_: str | None = Field(default=None, alias="from")
    """Campo del record (percorso con punti: `hit.n`, `ac.0`)."""
    expr: str | None = None
    """Espressione di sola lettura sui campi del record (vedi DSL)."""
    to: dict[str, str] | None = None
    """Scrittura con `expr`: `{campo_record: espressione}` con `value` = valore del DTO."""
    map: dict[str, str] | str | None = None
    """Valore grezzo -> nome del membro dell'enum del DTO (inline), oppure nome di una tabella."""
    unmapped: str | None = None
    """Membro dell'enum usato per i valori grezzi non in `map`."""
    null_if: Any = None
    """Valore grezzo che il DTO vede come `None` (e viceversa in scrittura)."""
    const: Any = None
    """Valore costante (il MUD non ha il campo)."""
    soft: bool = False
    """Con `const`/campo di sola lettura: i valori diversi sono ignorati invece di dare 422."""
    hook: str | None = None
    """Hook registrato (`FieldHook`) che legge/scrive il campo."""
    pairs: PairsSpec | None = None
    in_extra: bool = False
    """Il campo del record compare anche in `extra` (oltre che nel campo del DTO)."""

    @model_validator(mode="after")
    def _one_source(self) -> "FieldMap":
        """Al massimo una fra `from`, `expr`, `const`, `hook`."""
        given = [n for n in ("from_", "expr", "hook", "pairs") if getattr(self, n) is not None]
        if "const" in self.model_fields_set:
            given.append("const")
        if len(given) > 1:
            raise ValueError(f"fonti in conflitto: {', '.join(given)}")
        return self


class ExtraSpec(_M):
    """Quali campi del record non mappati finiscono in `extra` (default: tutti, cosi' il round trip e' completo)."""

    include: Literal["all", "none"] | list[str] = "all"
    exclude: list[str] = Field(default_factory=list)


class EntityModel(_M):
    """Mappatura di un'entita' (zona, stanza, mob, oggetto) sui campi del DTO."""

    entity: str
    fields: dict[str, FieldMap] = Field(default_factory=dict)
    defaults: dict[str, Any] = Field(default_factory=dict)
    """Valori dei campi del record per le entita' nuove (oltre ai default dei primitivi)."""
    extra: ExtraSpec = Field(default_factory=ExtraSpec)


class ResetsSource(_M):
    """Dove vive lo script di reset di una zona: una sezione del file o una lista dentro il record di zona."""

    section: str | None = None
    field: str | None = None

    @model_validator(mode="after")
    def _one(self) -> "ResetsSource":
        """Esattamente uno dei due."""
        if bool(self.section) == bool(self.field):
            raise ValueError("indicare `section` oppure `field`")
        return self


class ZoneModel(EntityModel):
    """Zona: `id` e script di reset."""

    id: Literal["bottom", "top", "position"] = "bottom"
    """Da cosa deriva l'`id`; senza valore univoco/valido: `-(posizione)`."""
    resets: ResetsSource | None = None


class RoomModel(EntityModel):
    """Stanza: dove sono uscite ed extra description."""

    exits: str
    """Campo-lista del record con le uscite."""
    extra_descriptions: str | None = None
    """Campo-lista con le extra description (assente: il MUD non le ha, capability `supportsExtraDescriptions` falsa)."""


class ExitModel(_M):
    """Uscita (dict dentro la lista `exits` della stanza)."""

    fields: dict[str, FieldMap] = Field(default_factory=dict)
    defaults: dict[str, Any] = Field(default_factory=dict)
    direction_field: str
    target_field: str
    """Campo con il vnum di destinazione."""
    no_target: Any = -1
    """Valore di `target_field` per "nessuna destinazione"."""
    key_field: str | None = None
    door_state: Literal["fields", "resets"] = "fields"
    """`fields`: `is_open`/`is_locked` sono campi come gli altri; `resets`: stato porta nello script di reset (`D`)."""
    sort_by_direction: bool = True


class ExtraDescModel(_M):
    """Extra description di stanza."""

    fields: dict[str, FieldMap]
    defaults: dict[str, Any] = Field(default_factory=dict)


class ResetCommandModel(_M):
    """Un comando di reset del MUD (una lettera) e come i suoi campi diventano `arg1..arg4`/`argStr` neutri."""

    type: str
    """Membro di `ZoneCommandType` (LOAD_MOB, GIVE_OBJECT, ...)."""
    if_flag: FieldMap | None = None
    arg1: FieldMap | None = None
    arg2: FieldMap | None = None
    arg3: FieldMap | None = None
    arg4: FieldMap | None = None
    arg_str: FieldMap | None = None
    defaults: dict[str, Any] = Field(default_factory=dict)


class ResetModel(_M):
    """Script di reset: campo con la lettera, commenti ignorati, comandi mappati."""

    command_field: str
    comments: list[str] = Field(default_factory=list)
    """Lettere che sono righe di commento (conservate, invisibili al DTO)."""
    commands: dict[str, ResetCommandModel]
    new_defaults: dict[str, Any] = Field(default_factory=dict)


class Model(_M):
    """Sezione `model`."""

    zone: ZoneModel
    room: RoomModel
    mob: EntityModel
    object: EntityModel
    exit: ExitModel
    extra_description: ExtraDescModel
    reset: ResetModel


class ZoneRange(_M):
    """Come si ricava il range di vnum di una zona."""

    mode: Literal["fields", "top", "hook"]
    bottom: FieldMap | None = None
    top: FieldMap | None = None
    hook: str | None = None
    """Per `hook`: hook registrato `(zone_fields) -> [(bottom, top)]`."""


class IndexSpec(_M):
    """File indice con l'elenco dei file di zona abilitati (`area.lst`)."""

    file: str
    comment: str = "#"
    end: str | None = "$"


class NewZone(_M):
    """Valori per le zone create dall'editor."""

    style: str | None = None
    """Intestazione (`header` della sezione `single` di zona) da usare."""
    file: str = "{slug}.dat"
    """Nome del file (layout `zone_files`); `{slug}` = nome di zona minuscolo senza simboli."""


class Layout(_M):
    """Dove vivono i file di dati e come si delimitano le zone."""

    mode: Literal["zone_files", "type_files"]
    encoding: str = "auto"
    """`auto` = UTF-8 se valido, altrimenti latin-1 (round trip esatto)."""
    newline: Literal["auto", "lf", "crlf"] = "auto"
    zone_file: str | None = None
    """`zone_files`: tipo di file (`grammar.files`) di ogni file di zona."""
    glob: str | None = None
    index: IndexSpec | None = None
    files: dict[str, str] = Field(default_factory=dict)
    """`type_files`: tipo di file -> glob relativo alla radice dati."""
    zone_range: ZoneRange
    new_zone: NewZone = Field(default_factory=NewZone)
    insert: Literal["append", "by_vnum"] = "append"
    """Posizione dei nuovi record: in coda alla sezione o ordinati per vnum."""


class Rules(_M):
    """Convenzioni di id e opzioni di integrita'."""

    vnum_range_check: bool = True
    """Un vnum nuovo deve cadere nel range della zona (se ha un range)."""
    zone_alignment: int = Field(default=100, ge=1)
    """`next_zone_vnum`: il range suggerito parte da un multiplo di questo valore."""
    exit_id_stride: int = 10
    """`id` uscita = `vnum_stanza * stride + direzione`."""
    extra_id_stride: int = 1000
    """`id` extra description = `vnum_stanza * stride + posizione`."""


class Meta(_M):
    """Razze/classi esposte da `races()`/`classes()`: liste di nomi o nome di una tabella."""

    races: list[str] | str = Field(default_factory=list)
    classes: list[str] | str = Field(default_factory=list)


class MappingSpec(_M):
    """Radice del file di mappatura."""

    schema_: str | None = Field(default=None, alias="$schema")
    name: str
    version: Literal[1] = 1
    description: str = ""
    layout: Layout
    grammar: Grammar
    tables: dict[str, TableSpec] = Field(default_factory=dict)
    model: Model
    hooks: list[str] = Field(default_factory=list)
    """Hook registrati in codice che questa mappatura usa (dichiarazione esplicita: il YAML non importa mai codice)."""
    rules: Rules = Field(default_factory=Rules)
    meta: Meta = Field(default_factory=Meta)


# --------------------------------------------------------------------------- caricamento e controlli


def _plain(node: Any) -> Any:
    """Converte i tipi ruamel in dict/list/scalari Python."""
    if isinstance(node, dict):
        return {str(k): _plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_plain(v) for v in node]
    if isinstance(node, bool) or node is None:
        return node
    if isinstance(node, int):
        return int(node)
    if isinstance(node, float):
        return float(node)
    return str(node) if isinstance(node, str) else node


def line_of(root: Any, path: tuple[Any, ...]) -> int:
    """Numero di riga (1-based) del nodo piu' profondo raggiungibile lungo `path` nell'albero ruamel (segmenti
    inesistenti, es. i tag delle unioni di Pydantic, sono saltati)."""
    node, line = root, 1
    if isinstance(root, CommentedMap | CommentedSeq):
        line = root.lc.line + 1
    for seg in path:
        if isinstance(node, CommentedMap) and seg in node:
            line = node.lc.key(seg)[0] + 1
            node = node[seg]
        elif isinstance(node, CommentedSeq) and isinstance(seg, int) and seg < len(node):
            line = node.lc.item(seg)[0] + 1
            node = node[seg]
        elif isinstance(node, CommentedMap) and len(node) == 1:
            # sintassi compatta di un passo: il tag `field` non esiste nel YAML, il nodo e' la mappa a un solo elemento
            continue
    return line


def _problem(problems: list[tuple[tuple[Any, ...], str]], path: tuple[Any, ...], message: str) -> None:
    """Registra un problema trovato dai controlli incrociati."""
    problems.append((path, message))


def _walk_steps(steps: list[Any], path: tuple[Any, ...]) -> Any:
    """Genera `(passo, percorso)` per ogni passo annidato (percorso nel YAML originale)."""
    for i, step in enumerate(steps):
        here = (*path, i)
        yield step, here
        if isinstance(step, LineStep):
            yield from _walk_steps(step.steps, (*here, "line"))
        elif isinstance(step, WhenStep):
            yield from _walk_steps(step.then, (*here, "then"))
            yield from _walk_steps(step.otherwise, (*here, "else"))
        elif isinstance(step, SwitchStep):
            for case, sub in step.cases.items():
                yield from _walk_steps(sub, (*here, "cases", case))
            yield from _walk_steps(step.default, (*here, "default"))
        elif isinstance(step, TaggedStep):
            for tag, spec in step.tags.items():
                yield from _walk_steps(spec.steps, (*here, "tagged", "tags", tag, "steps"))


def record_fields(grammar: RecordGrammar, records: dict[str, RecordGrammar] | None = None) -> set[str]:
    """Nomi dei campi di un record (inclusi liste di `tagged` e campi dei loro elementi)."""
    names: set[str] = set()
    for step, _ in _walk_steps(grammar.steps, ()):
        if isinstance(step, FieldStep):
            names.add(step.field)
        elif isinstance(step, TaggedStep):
            names |= {s.into for s in step.tags.values() if s.into}
            if step.tag_field:
                names.add(step.tag_field)
    return names


def _check_exprs(problems: list, path: tuple, source: str | None, allowed: set[str], extra: frozenset[str] = frozenset()) -> None:
    """Valida un'espressione e i nomi che usa."""
    if source is None:
        return
    try:
        unknown = names_in(source) - allowed - extra
    except ExprError as error:
        _problem(problems, path, str(error))
        return
    if unknown:
        _problem(problems, path, f"campi sconosciuti nell'espressione {source!r}: {', '.join(sorted(unknown))}")


def _check_field_map(problems: list, path: tuple, fm: FieldMap, fields: set[str], spec: "MappingSpec") -> None:
    """Riferimenti di un `FieldMap`: campi, espressioni, tabella, hook."""
    if fm.from_ is not None and fm.from_.split(".")[0] not in fields:
        _problem(problems, (*path, "from"), f"campo del record sconosciuto: {fm.from_!r}")
    _check_exprs(problems, (*path, "expr"), fm.expr, fields)
    for target, source in (fm.to or {}).items():
        if target.split(".")[0] not in fields:
            _problem(problems, (*path, "to", target), f"campo del record sconosciuto: {target!r}")
        _check_exprs(problems, (*path, "to", target), source, fields, frozenset({"value"}))
    if isinstance(fm.map, str) and fm.map not in spec.tables:
        _problem(problems, (*path, "map"), f"tabella sconosciuta: {fm.map!r}")
    if fm.hook is not None:
        _check_hook(problems, (*path, "hook"), fm.hook, "field", spec)
    if fm.pairs is not None and fm.pairs.list not in fields:
        _problem(problems, (*path, "pairs", "list"), f"lista sconosciuta: {fm.pairs.list!r}")


def _check_hook(problems: list, path: tuple, name: str, family: str, spec: "MappingSpec") -> None:
    """L'hook deve essere registrato (famiglia giusta) e dichiarato in `hooks:`."""
    if name not in hooks.registered(family):
        _problem(problems, path, f"hook {family} sconosciuto: {name!r} (registrati: {', '.join(hooks.registered(family)) or 'nessuno'})")
    elif name not in spec.hooks:
        _problem(problems, path, f"hook {name!r} non dichiarato nella lista `hooks:`")


def cross_check(spec: MappingSpec) -> list[tuple[tuple[Any, ...], str]]:
    """Controlli incrociati (riferimenti fra sezioni); restituisce `[(percorso, messaggio)]`."""
    problems: list[tuple[tuple[Any, ...], str]] = []
    records = spec.grammar.records
    fields_of = {name: record_fields(rg) for name, rg in records.items()}
    entity_record: dict[str, str] = {}
    for fname, fg in spec.grammar.files.items():
        for i, sec in enumerate(fg.sections):
            path = ("grammar", "files", fname, "sections", i)
            if sec.record not in records:
                _problem(problems, (*path, "record"), f"record sconosciuto: {sec.record!r}")
                continue
            entity_record.setdefault(sec.entity, sec.record)
            if sec.until and sec.until.field and sec.until.field not in fields_of[sec.record]:
                _problem(problems, (*path, "until", "field"), f"campo {sec.until.field!r} non presente in {sec.record!r}")
    for rname, rg in records.items():
        base = ("grammar", "records", rname)
        if rg.key and rg.key not in fields_of[rname]:
            _problem(problems, (*base, "key"), f"campo chiave sconosciuto: {rg.key!r}")
        if rg.parser:
            _check_hook(problems, (*base, "parser"), rg.parser, "record", spec)
        for step, p in _walk_steps(rg.steps, (*base, "steps")):
            if isinstance(step, FieldStep) and step.table and step.table not in spec.tables:
                _problem(problems, p, f"tabella sconosciuta: {step.table!r}")
            if isinstance(step, WhenStep):
                _check_exprs(problems, (*p, "when"), step.when, fields_of[rname])
            if isinstance(step, SwitchStep) and step.switch not in fields_of[rname]:
                _problem(problems, (*p, "switch"), f"campo sconosciuto: {step.switch!r}")
            if isinstance(step, TaggedStep):
                for tag, ts in step.tags.items():
                    _check_exprs(problems, (*p, "tagged", "tags", tag, "write_if"), ts.write_if, fields_of[rname])
    layout = spec.layout
    if layout.mode == "zone_files" and layout.zone_file not in spec.grammar.files:
        _problem(problems, ("layout", "zone_file"), "serve `zone_file` (tipo di file in grammar.files)")
    for kind in layout.files:
        if kind not in spec.grammar.files:
            _problem(problems, ("layout", "files", kind), f"tipo di file sconosciuto: {kind!r}")
    if layout.mode == "type_files" and not layout.files:
        _problem(problems, ("layout", "files"), "`type_files` richiede `files`")
    zone_record = entity_record.get(spec.model.zone.entity)
    zone_fields = fields_of.get(zone_record or "", set())
    zr = layout.zone_range
    if zr.mode == "hook":
        _check_hook(problems, ("layout", "zone_range", "hook"), zr.hook or "", "zone_range", spec)
    else:
        for which in ("bottom", "top"):
            fm = getattr(zr, which)
            if fm is not None:
                _check_field_map(problems, ("layout", "zone_range", which), fm, zone_fields, spec)
        if zr.top is None:
            _problem(problems, ("layout", "zone_range", "top"), "serve `top`")
        if zr.mode == "fields" and zr.bottom is None:
            _problem(problems, ("layout", "zone_range", "bottom"), "`fields` richiede `bottom`")
    for entity, em in (("zone", spec.model.zone), ("room", spec.model.room), ("mob", spec.model.mob), ("object", spec.model.object)):
        rec = entity_record.get(em.entity)
        if rec is None:
            _problem(problems, ("model", entity, "entity"), f"nessuna sezione di grammatica contiene l'entita' {em.entity!r}")
            continue
        for fname, fm in em.fields.items():
            _check_field_map(problems, ("model", entity, "fields", fname), fm, fields_of[rec], spec)
        for fname in em.defaults:
            if fname not in fields_of[rec]:
                _problem(problems, ("model", entity, "defaults", fname), f"campo del record sconosciuto: {fname!r}")
    room_rec = fields_of.get(entity_record.get(spec.model.room.entity, ""), set())
    for attr in ("exits", "extra_descriptions"):
        name = getattr(spec.model.room, attr)
        if name is not None and name not in room_rec:
            _problem(problems, ("model", "room", attr), f"lista sconosciuta: {name!r}")
    zone_rec_fields = zone_fields
    resets = spec.model.zone.resets
    if resets and resets.field and resets.field not in zone_rec_fields:
        _problem(problems, ("model", "zone", "resets", "field"), f"lista sconosciuta: {resets.field!r}")
    if (
        resets
        and resets.section
        and not any(s.header == resets.section or s.entity == resets.section for fg in spec.grammar.files.values() for s in fg.sections)
    ):
        _problem(problems, ("model", "zone", "resets", "section"), f"sezione sconosciuta: {resets.section!r}")
    sub_exit = spec.model.exit
    exit_fields = _tagged_fields(records, spec.model.room.exits, entity_record.get(spec.model.room.entity, ""))
    for fname, fm in sub_exit.fields.items():
        _check_field_map(problems, ("model", "exit", "fields", fname), fm, exit_fields, spec)
    for attr in ("direction_field", "target_field", "key_field"):
        name = getattr(sub_exit, attr)
        if name is not None and exit_fields and name not in exit_fields:
            _problem(problems, ("model", "exit", attr), f"campo sconosciuto nell'uscita: {name!r}")
    extra_fields = _tagged_fields(records, spec.model.room.extra_descriptions, entity_record.get(spec.model.room.entity, ""))
    for fname, fm in spec.model.extra_description.fields.items():
        _check_field_map(problems, ("model", "extra_description", "fields", fname), fm, extra_fields, spec)
    reset_rec = _reset_record_fields(spec, fields_of, entity_record)
    for letter, cmd in spec.model.reset.commands.items():
        for slot in ("if_flag", "arg1", "arg2", "arg3", "arg4", "arg_str"):
            fm = getattr(cmd, slot)
            if fm is not None:
                _check_field_map(problems, ("model", "reset", "commands", letter, slot), fm, reset_rec, spec)
    for table in (spec.meta.races, spec.meta.classes):
        if isinstance(table, str) and table not in spec.tables:
            _problem(problems, ("meta",), f"tabella sconosciuta: {table!r}")
    _check_dto(problems, spec)
    return problems


def _check_dto(problems: list, spec: MappingSpec) -> None:
    """I campi mappati esistono nel DTO e i nomi delle enum (`map`, `unmapped`, `const`, `type` dei reset) sono membri veri."""
    from pachimudeditor.common.enums import ZoneCommandType

    model = spec.model
    sections = {
        "zone": model.zone.fields, "room": model.room.fields, "mob": model.mob.fields, "object": model.object.fields,
        "exit": model.exit.fields, "extra_description": model.extra_description.fields,
    }  # fmt: skip
    for section, fields in sections.items():
        out = DTO_OUT[section]
        for name, fm in fields.items():
            path = ("model", section, "fields", name)
            info = out.model_fields.get(name)
            if info is None:
                _problem(problems, path, f"{name!r} non e' un campo di {out.__name__}")
                continue
            enum = enum_of(annotation_of(info.annotation)[0])
            if enum is None:
                continue
            members = set(enum.__members__)
            candidates = (
                ("map", set(fm.map.values()) if isinstance(fm.map, dict) else set()),
                ("unmapped", {fm.unmapped} if fm.unmapped else set()),
                ("const", {fm.const} if "const" in fm.model_fields_set and isinstance(fm.const, str) else set()),
            )
            for key, names in candidates:
                if names - members:
                    _problem(
                        problems,
                        (*path, key),
                        f"membri non validi per {enum.__name__}: {', '.join(sorted(names - members))} (validi: {', '.join(sorted(members))})",
                    )
    for letter, cmd in model.reset.commands.items():
        if cmd.type not in ZoneCommandType.__members__:
            _problem(
                problems,
                ("model", "reset", "commands", letter, "type"),
                f"tipo di comando sconosciuto: {cmd.type!r} (validi: {', '.join(ZoneCommandType.__members__)})",
            )


def _tagged_fields(records: dict[str, RecordGrammar], list_name: str | None, record: str) -> set[str]:
    """Campi degli elementi della lista `list_name` (passi dei tag con `into: list_name`)."""
    names: set[str] = set()
    rg = records.get(record)
    if rg is None or list_name is None:
        return names
    for step, _ in _walk_steps(rg.steps, ()):
        if isinstance(step, TaggedStep):
            for ts in step.tags.values():
                if ts.into == list_name:
                    names |= {s.field for s, _ in _walk_steps(ts.steps, ()) if isinstance(s, FieldStep)}
                    if step.tag_field:
                        names.add(step.tag_field)
    return names


def _reset_record_fields(spec: MappingSpec, fields_of: dict[str, set[str]], entity_record: dict[str, str]) -> set[str]:
    """Campi dei record di reset: del record `reset` (sezione) o degli elementi della lista nel record di zona."""
    rec = entity_record.get("reset")
    if rec:
        return fields_of[rec]
    res = spec.model.zone.resets
    zone_rec = entity_record.get(spec.model.zone.entity, "")
    return _tagged_fields(spec.grammar.records, res.field if res else None, zone_rec)


def _format_errors(path: Path, root: Any, problems: list[tuple[tuple[Any, ...], str]]) -> str:
    """Messaggio unico con una riga per problema."""
    lines = [f"mappatura non valida ({path.name}):"]
    for loc, message in problems:
        where = ".".join(str(p) for p in loc)
        lines.append(f"  {path}:{line_of(root, tuple(loc))}: {where}: {message}")
    return "\n".join(lines)


def _describe(error: Any) -> str:
    """Messaggio di un errore di Pydantic con il valore trovato (quando e' un semplice scalare)."""
    found = error.get("input")
    if isinstance(found, dict) and error["loc"] and error["loc"][-1] in found:
        found = found[error["loc"][-1]]
    return error["msg"] + (f" (trovato: {found!r})" if isinstance(found, str | int | float) and not isinstance(found, bool) else "")


def load_mapping(path: str | Path) -> MappingSpec:
    """Legge e valida un file di mappatura.

    Raises:
        MappingConfigError: file illeggibile, YAML non valido o campi/riferimenti errati (con `file:riga`).
    """
    p = Path(path).expanduser()
    try:
        root = YAML(typ="rt").load(p.read_text(encoding="utf-8"))
    except OSError as error:
        raise MappingConfigError(f"mappatura non leggibile: {p} ({error})") from error
    except Exception as error:  # ruamel solleva tipi diversi per errori di sintassi
        raise MappingConfigError(f"YAML non valido in {p}: {error}") from error
    if not isinstance(root, CommentedMap):
        raise MappingConfigError(f"{p}: la radice deve essere una mappa")
    try:
        spec = MappingSpec.model_validate(_plain(root))
    except ValidationError as error:
        problems = [(tuple(e["loc"]), _describe(e)) for e in error.errors()]
        raise MappingConfigError(_format_errors(p, root, problems)) from error
    problems = cross_check(spec)
    if problems:
        raise MappingConfigError(_format_errors(p, root, problems))
    return spec


def json_schema() -> dict[str, Any]:
    """JSON Schema del file di mappatura: la sintassi compatta dei passi e' ammessa (`AnyStep`)."""
    schema = MappingSpec.model_json_schema(by_alias=True)
    defs = schema["$defs"]

    def replace(node: Any) -> Any:
        """Sostituisce le unioni di passi con `AnyStep`."""
        if isinstance(node, dict):
            if node.get("discriminator", {}).get("propertyName") == "kind":
                return {"$ref": "#/$defs/AnyStep"}
            return {k: replace(v) for k, v in node.items()}
        if isinstance(node, list):
            return [replace(v) for v in node]
        return node

    schema = replace(schema)
    defs = schema["$defs"]
    options = {k: v for k, v in defs["FieldStep"]["properties"].items() if k not in ("kind", "field", "type")}
    defs["AnyStep"] = {
        "description": "Un passo della grammatica: forma estesa o compatta (`- nome: tipo`, `- nome: {type: .., ..}`).",
        "anyOf": [
            {"$ref": "#/$defs/FieldStep"},
            {"$ref": "#/$defs/LiteralStep"},
            {
                "type": "object",
                "required": ["line"],
                "properties": {"line": {"type": "array", "items": {"$ref": "#/$defs/AnyStep"}}},
                "additionalProperties": False,
            },
            {"$ref": "#/$defs/WhenStep"},
            {"$ref": "#/$defs/SwitchStep"},
            {
                "type": "object",
                "required": ["tagged"],
                "properties": {"tagged": {"$ref": "#/$defs/TaggedStep"}},
                "additionalProperties": False,
            },
            {
                "description": "Campo in sintassi compatta: `nome: tipo` oppure `nome: {type: tipo, ...opzioni}`.",
                "type": "object",
                "minProperties": 1,
                "maxProperties": 1,
                "additionalProperties": {
                    "anyOf": [
                        {"enum": list(PRIMITIVES)},
                        {
                            "type": "object",
                            "required": ["type"],
                            "properties": {"type": {"enum": list(PRIMITIVES)}, **options},
                            "additionalProperties": False,
                        },
                    ]
                },
            },
        ],
    }
    schema["title"] = "Mappatura MappingAdapter (pachimudeditor)"
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return schema


def write_json_schema() -> None:
    """Rigenera `mapping.schema.json` (da lanciare dopo ogni modifica dello schema)."""
    SCHEMA_FILE.write_text(json.dumps(json_schema(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


__all__ = [
    "FieldMap",
    "FieldStep",
    "MappingConfigError",
    "MappingSpec",
    "load_mapping",
    "json_schema",
    "write_json_schema",
]
