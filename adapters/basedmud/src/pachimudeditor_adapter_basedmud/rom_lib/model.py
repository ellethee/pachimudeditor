"""Modello dati dei file `.are` ROM 2.4 / QuickMUD / basedmud (dataclass, nessuna dipendenza esterna).

Ogni entita' parsata (mob, oggetto, stanza, reset, ...) conserva il testo sorgente originale
(`_src`) e una "impronta" dei suoi campi al momento del parsing (`_fp`). In scrittura, se l'entita'
non e' stata modificata (impronta invariata) viene riemesso il testo originale byte per byte;
se e' stata modificata (o e' nuova) viene serializzata con le convenzioni di `olc_save.c`.
I campi `_src`/`_fp` non partecipano a `==` ne' a `repr`.

I flag sono interi (vedi `flags.py`); le stringhe usano sempre `\\n` come fine riga (la serializzazione
adatta lo stile newline dell'area).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from . import flags as fl
from .tables import FLAG_TABLES, TYPE_TABLES

DIRECTIONS = ("north", "east", "south", "west", "up", "down")


def _meta() -> str | None:
    """Campo di servizio (sorgente / impronta): escluso da repr, eq e init posizionale."""
    return field(default=None, repr=False, compare=False, kw_only=True)  # type: ignore[return-value]


@dataclass
class Dice:
    """Dado ROM `NdT+B` (hit/mana/damage dei mob)."""

    number: int = 0
    type: int = 0
    bonus: int = 0

    def __str__(self) -> str:
        return f"{self.number}d{self.type}+{self.bonus}"

    @classmethod
    def parse(cls, text: str) -> "Dice":
        """Interpreta `1d8+32` (accetta anche `1d8-2`).

        Raises:
            ValueError: formato non valido.
        """
        import re

        m = re.fullmatch(r"\s*(-?\d+)d(-?\d+)([+-])(-?\d+)\s*", text)
        if not m:
            raise ValueError(f"dado non valido: {text!r}")
        bonus = int(m.group(4))
        if m.group(3) == "-":
            bonus = -bonus
        return cls(int(m.group(1)), int(m.group(2)), bonus)


@dataclass
class CommentLine:
    """Riga di commento `* ...` dentro #RESETS / #SPECIALS, riemessa tale e quale."""

    text: str = "*"
    _src: str | None = _meta()
    _fp: str | None = _meta()


@dataclass
class ExtraDescription:
    """Descrizione extra `E` di stanza o oggetto (keyword~ testo~)."""

    keyword: str = ""
    description: str = ""


@dataclass
class Exit:
    """Uscita `D<n>` di una stanza.

    `locks` e' il codice di porta del formato file: 0 nessuna porta, 1 porta, 2 porta pickproof,
    3 porta nopass, 4 porta pickproof+nopass. `to_vnum` -1 = uscita senza destinazione.
    """

    door: int = 0
    description: str = ""
    keyword: str = ""
    locks: int = 0
    key: int = -1
    to_vnum: int = -1

    @property
    def is_door(self) -> bool:
        """True se l'uscita e' una porta (locks 1-4)."""
        return self.locks in (1, 2, 3, 4)

    @property
    def pickproof(self) -> bool:
        """True se la porta e' a prova di scasso (locks 2 o 4)."""
        return self.locks in (2, 4)

    @property
    def nopass(self) -> bool:
        """True se la porta e' nopass (locks 3 o 4)."""
        return self.locks in (3, 4)

    @property
    def direction(self) -> str:
        """Nome della direzione (north, east, ...)."""
        return DIRECTIONS[self.door] if 0 <= self.door < 6 else f"door{self.door}"

    @staticmethod
    def locks_from(is_door: bool, pickproof: bool = False, nopass: bool = False) -> int:
        """Calcola il codice `locks` dai flag (come in `save_room`)."""
        if not is_door:
            return 0
        return 1 + (1 if pickproof else 0) + (2 if nopass else 0)


@dataclass
class Room:
    """Stanza (#ROOMS). `heal_rate`/`mana_rate` default 100; `clan`/`owner` stringhe vuote se assenti."""

    vnum: int = 0
    name: str = ""
    description: str = ""
    area_number: int = 0
    room_flags: int = 0
    sector: int = 0
    exits: list[Exit] = field(default_factory=list)
    extra_descs: list[ExtraDescription] = field(default_factory=list)
    heal_rate: int = 100
    mana_rate: int = 100
    clan: str = ""
    owner: str = ""
    _src: str | None = _meta()
    _fp: str | None = _meta()

    @property
    def flag_names(self) -> list[str]:
        """Nomi simbolici dei room flag accesi."""
        return fl.flag_names("room_flags", self.room_flags)

    @property
    def sector_name(self) -> str:
        """Nome del tipo di terreno (o il numero se sconosciuto)."""
        table = TYPE_TABLES["sector_types"]
        return table[self.sector] if 0 <= self.sector < len(table) else str(self.sector)

    def exit_for(self, door: int) -> Exit | None:
        """Restituisce l'uscita per la direzione `door` (0-5) o None."""
        return next((e for e in self.exits if e.door == door), None)


@dataclass
class FlagRemoval:
    """Riga `F <word> <flags>` di un mob: bit rimossi dai default della razza."""

    word: str = "act"
    value: int = 0


@dataclass
class MobProgTrigger:
    """Riga `M <trigger> <vnum> <frase>~` di un mob (aggancio a mobprog)."""

    trigger: str = ""
    vnum: int = 0
    phrase: str = ""


@dataclass
class Mobile:
    """Mob (#MOBILES, formato nuovo ROM). I flag `*_orig` del file sono quelli senza i default di razza.

    `ac` sono i 4 valori del file (pierce, bash, slash, exotic), cioe' gia' divisi per 10.
    """

    vnum: int = 0
    name: str = ""
    short_descr: str = ""
    long_descr: str = ""
    description: str = ""
    race: str = "human"
    act: int = 0
    affected_by: int = 0
    alignment: int = 0
    group: int = 0
    level: int = 1
    hitroll: int = 0
    hit: Dice = field(default_factory=Dice)
    mana: Dice = field(default_factory=Dice)
    damage: Dice = field(default_factory=Dice)
    dam_type: str = "none"
    ac: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    off_flags: int = 0
    imm_flags: int = 0
    res_flags: int = 0
    vuln_flags: int = 0
    start_pos: str = "stand"
    default_pos: str = "stand"
    sex: str = "neutral"
    wealth: int = 0
    form: int = 0
    parts: int = 0
    size: str = "medium"
    material: str = "0"
    flag_removals: list[FlagRemoval] = field(default_factory=list)
    mprogs: list[MobProgTrigger] = field(default_factory=list)
    _src: str | None = _meta()
    _fp: str | None = _meta()

    @property
    def act_names(self) -> list[str]:
        """Nomi simbolici dei flag `act`."""
        return fl.flag_names("mob_flags", self.act)

    @property
    def affect_names(self) -> list[str]:
        """Nomi simbolici dei flag `affected_by`."""
        return fl.flag_names("affect_flags", self.affected_by)

    @property
    def off_names(self) -> list[str]:
        """Nomi simbolici dei flag offensivi."""
        return fl.flag_names("off_flags", self.off_flags)


@dataclass
class ObjectAffect:
    """Affect di oggetto: `A` (apply semplice) oppure `F` (flag affect con bit_type A/I/R/V).

    Per `A` `where` e' "" e `bits` 0; per `F` `where` e' una tra "A", "I", "R", "V".
    """

    location: int = 0
    modifier: int = 0
    where: str = ""
    bits: int = 0

    @property
    def is_flag_affect(self) -> bool:
        """True se e' una riga `F` (con bit_type)."""
        return self.where != ""


# Posizioni dei 5 valori che il formato file scrive tra apici (nomi: liquidi, skill).
_QUOTED_SLOTS: dict[str, tuple[int, ...]] = {
    "drink": (2,),
    "fountain": (2,),
    "potion": (1, 2, 3, 4),
    "pill": (1, 2, 3, 4),
    "scroll": (1, 2, 3, 4),
    "staff": (3,),
    "wand": (3,),
}

_VALUE_NAMES: dict[str, tuple[str, ...]] = {
    "weapon": ("weapon_type", "dice_number", "dice_size", "attack_type", "flags"),
    "container": ("capacity", "flags", "key", "max_weight", "weight_mult"),
    "drink": ("capacity", "filled", "liquid", "poisoned", "unused"),
    "fountain": ("capacity", "filled", "liquid", "poisoned", "unused"),
    "wand": ("level", "recharge", "charges", "skill", "unused"),
    "staff": ("level", "recharge", "charges", "skill", "unused"),
    "potion": ("level", "skill1", "skill2", "skill3", "skill4"),
    "pill": ("level", "skill1", "skill2", "skill3", "skill4"),
    "scroll": ("level", "skill1", "skill2", "skill3", "skill4"),
}


@dataclass
class Object:
    """Oggetto (#OBJECTS).

    `values` sono i 5 valori v0-v4 come stringhe logiche (senza apici), interpretati secondo
    `item_type` (vedi `value_names`/`named_values`); i valori testuali (liquido, skill) sono
    scritti tra apici dal serializzatore. `condition` e' la lettera P/G/A/W/D/B/R.
    """

    vnum: int = 0
    name: str = ""
    short_descr: str = ""
    description: str = ""
    material: str = "unknown"
    item_type: str = "trash"
    extra_flags: int = 0
    wear_flags: int = 0
    values: list[str] = field(default_factory=lambda: ["0"] * 5)
    level: int = 0
    weight: int = 0
    cost: int = 0
    condition: str = "P"
    affects: list[ObjectAffect] = field(default_factory=list)
    extra_descs: list[ExtraDescription] = field(default_factory=list)
    _src: str | None = _meta()
    _fp: str | None = _meta()

    QUOTED_SLOTS: ClassVar[dict[str, tuple[int, ...]]] = _QUOTED_SLOTS

    @property
    def value_names(self) -> tuple[str, ...]:
        """Nomi dei 5 valori per il tipo corrente (`v0`..`v4` per i tipi senza interpretazione)."""
        return _VALUE_NAMES.get(self.item_type, ("v0", "v1", "v2", "v3", "v4"))

    def named_values(self) -> dict[str, str]:
        """Dizionario nome->valore grezzo secondo il tipo dell'oggetto."""
        return dict(zip(self.value_names, self.values, strict=True))

    def value_int(self, index: int) -> int:
        """Valore `index` come intero (accetta anche bit string a lettere)."""
        return fl.parse_flags(self.values[index])

    def set_value(self, index: int, value: int | str) -> None:
        """Imposta il valore `index` (interi in decimale, stringhe tali e quali)."""
        self.values[index] = str(value)

    def set_named(self, name: str, value: int | str) -> None:
        """Imposta un valore per nome (es. `set_named("dice_size", 8)` su un'arma).

        Raises:
            KeyError: se il nome non esiste per il tipo corrente.
        """
        self.values[self.value_names.index(name)] = str(value)

    @property
    def extra_names(self) -> list[str]:
        """Nomi simbolici degli extra flag."""
        return fl.flag_names("extra_flags", self.extra_flags)

    @property
    def wear_names(self) -> list[str]:
        """Nomi simbolici dei wear flag."""
        return fl.flag_names("wear_flags", self.wear_flags)

    @property
    def known_type(self) -> bool:
        """True se `item_type` e' un tipo noto della tabella di basedmud."""
        return self.item_type in TYPE_TABLES["item_types"]


@dataclass
class Reset:
    """Reset (#RESETS): `command` M O P G E D R e `args` numerici nell'ordine del file.

    Layout argomenti (come in `load_resets`; il primo e' sempre il vecchio `if_flag`, ignorato dal loader):
    M: if, mob_vnum, global_limit, room_vnum, room_limit | O: if, obj_vnum, global_limit, room_vnum |
    P: if, obj_vnum, global_limit, into_obj_vnum, count | G: if, obj_vnum, global_limit |
    E: if, obj_vnum, global_limit, wear_loc | D: if, room_vnum, dir, locks(0 aperta,1 chiusa,2 chiusa+bloccata) |
    R: if, room_vnum, dir_count. `comment` e' il testo dopo gli argomenti (di solito `* ...`).
    """

    command: str = "M"
    args: list[int] = field(default_factory=list)
    comment: str = ""
    _src: str | None = _meta()
    _fp: str | None = _meta()

    ARG_NAMES: ClassVar[dict[str, tuple[str, ...]]] = {
        "M": ("if_flag", "mob_vnum", "global_limit", "room_vnum", "room_limit"),
        "O": ("if_flag", "obj_vnum", "global_limit", "room_vnum"),
        "P": ("if_flag", "obj_vnum", "global_limit", "into_vnum", "count"),
        "G": ("if_flag", "obj_vnum", "global_limit"),
        "E": ("if_flag", "obj_vnum", "global_limit", "wear_loc"),
        "D": ("if_flag", "room_vnum", "direction", "locks"),
        "R": ("if_flag", "room_vnum", "dir_count"),
    }

    def named(self) -> dict[str, int]:
        """Argomenti come dizionario nome->valore."""
        return dict(zip(self.ARG_NAMES[self.command], self.args, strict=True))

    def get(self, name: str) -> int:
        """Valore dell'argomento `name`. Raises KeyError/ValueError se non valido per il comando."""
        return self.args[self.ARG_NAMES[self.command].index(name)]

    def set(self, name: str, value: int) -> None:
        """Imposta l'argomento `name`."""
        self.args[self.ARG_NAMES[self.command].index(name)] = value

    @classmethod
    def make(cls, command: str, comment: str = "", **named: int) -> "Reset":
        """Costruisce un reset da argomenti con nome (mancanti = 0, `global_limit`/`room_limit` = 1)."""
        names = cls.ARG_NAMES[command]
        args = [named.pop(n, 1 if n in ("global_limit", "room_limit") else 0) for n in names]
        if named:
            raise KeyError(f"argomenti sconosciuti per {command}: {sorted(named)}")
        return cls(command, args, comment)


@dataclass
class Shop:
    """Negozio (#SHOPS): keeper, 5 tipi merce, margini %, orari apertura/chiusura."""

    keeper: int = 0
    buy_types: list[int] = field(default_factory=lambda: [0] * 5)
    profit_buy: int = 100
    profit_sell: int = 100
    open_hour: int = 0
    close_hour: int = 23
    comment: str = ""
    _src: str | None = _meta()
    _fp: str | None = _meta()


@dataclass
class Special:
    """Voce #SPECIALS: `M <mob_vnum> <spec_fun>` (+ commento)."""

    mob_vnum: int = 0
    function: str = ""
    comment: str = ""
    _src: str | None = _meta()
    _fp: str | None = _meta()


@dataclass
class MobProg:
    """Codice di mobprog (#MOBPROGS): `#vnum` + codice terminato da `~`."""

    vnum: int = 0
    code: str = ""
    _src: str | None = _meta()
    _fp: str | None = _meta()


@dataclass
class Help:
    """Voce di help (#HELPS): livello, keyword (stringa) e testo."""

    level: int = 0
    keyword: str = ""
    text: str = ""
    _src: str | None = _meta()
    _fp: str | None = _meta()


@dataclass
class Social:
    """Social (#SOCIALS). `lines` ha fino a 8 voci (None = `$`); `truncated` se terminato da `#`.

    `params` e' il resto della riga del nome (es. `0 0`), ignorato dal server ma conservato.
    """

    name: str = ""
    params: str = ""
    lines: list[str | None] = field(default_factory=list)
    truncated: bool = False
    _src: str | None = _meta()
    _fp: str | None = _meta()


@dataclass
class AreaHeader:
    """Intestazione area: formato vecchio `#AREA` (filename/name/credits/vnum) o `#AREADATA`.

    `style` e' "AREA" o "AREADATA". Nel formato vecchio `credits` contiene tipicamente
    `{ min max } Autore  Titolo`. `vnum_raw` conserva il testo del range se non numerico
    (es. `XX00 XX99` in proto.are). `extra` raccoglie le chiavi sconosciute di #AREADATA.
    """

    style: str = "AREADATA"
    filename: str = ""
    name: str = ""
    builders: str = ""
    credits: str = ""
    min_vnum: int = 0
    max_vnum: int = 0
    security: int = 9
    vnum_raw: str | None = None
    extra: list[tuple[str, str]] = field(default_factory=list)
    _src: str | None = _meta()
    _fp: str | None = _meta()


#: Nome sezione -> chiave convenzionale usata nei metodi di Area.
SECTION_ORDER = ("AREA", "AREADATA", "MOBILES", "OBJECTS", "ROOMS", "RESETS", "SHOPS", "SPECIALS", "MOBPROGS", "HELPS", "SOCIALS")


@dataclass
class Section:
    """Sezione di un file `.are`.

    `kind` e' il nome in maiuscolo (`MOBILES`, ...) oppure `RAW` per sezioni sconosciute (in tal
    caso `name` e `text` conservano nome e corpo originali). `head`/`tail` sono il testo grezzo
    che precede gli elementi (compresa la riga `#NOME`) e il terminatore (`#0`, `S`, `0`, ...);
    None = sezione nuova (serializzata in forma canonica).
    """

    kind: str
    items: list = field(default_factory=list)
    head: str | None = field(default=None, repr=False, compare=False)
    tail: str | None = field(default=None, repr=False, compare=False)
    name: str = ""
    text: str = ""


@dataclass
class Area:
    """Contenuto di un file `.are` (un'area, un file di help o di social).

    Le proprieta' `mobiles`, `objects`, ... restituiscono la lista di elementi della prima sezione
    del tipo (creandola se manca). Le sezioni sono in `sections` nell'ordine del file.
    """

    sections: list[Section] = field(default_factory=list)
    newline: str = "\n"
    encoding: str = "utf-8"
    has_terminator: bool = True
    end_head: str | None = field(default=None, repr=False, compare=False)
    trailer: str = field(default="", repr=False, compare=False)
    filename: str | None = field(default=None, compare=False)

    def section(self, kind: str, create: bool = True) -> Section | None:
        """Prima sezione di tipo `kind`; se manca viene creata (in ordine canonico) se `create`."""
        for s in self.sections:
            if s.kind == kind:
                return s
        if not create:
            return None
        new = Section(kind)
        rank = SECTION_ORDER.index(kind) if kind in SECTION_ORDER else len(SECTION_ORDER)
        pos = len(self.sections)
        for i, s in enumerate(self.sections):
            r = SECTION_ORDER.index(s.kind) if s.kind in SECTION_ORDER else len(SECTION_ORDER)
            if r > rank:
                pos = i
                break
        self.sections.insert(pos, new)
        return new

    def sections_of(self, kind: str) -> list[Section]:
        """Tutte le sezioni di tipo `kind` (di norma una)."""
        return [s for s in self.sections if s.kind == kind]

    def _items(self, kind: str) -> list:
        sec = self.section(kind)
        assert sec is not None
        return sec.items

    @property
    def header(self) -> AreaHeader | None:
        """Intestazione dell'area (None per i file di soli help/social)."""
        for kind in ("AREA", "AREADATA"):
            sec = self.section(kind, create=False)
            if sec is not None and sec.items:
                return sec.items[0]
        return None

    @header.setter
    def header(self, value: AreaHeader) -> None:
        kind = "AREA" if value.style == "AREA" else "AREADATA"
        other = "AREADATA" if kind == "AREA" else "AREA"
        gone = self.section(other, create=False)
        if gone is not None:
            self.sections.remove(gone)
        self._items_replace(kind, [value])

    def _items_replace(self, kind: str, items: list) -> None:
        sec = self.section(kind)
        assert sec is not None
        sec.items = items

    @property
    def mobiles(self) -> list[Mobile]:
        """Mob (#MOBILES)."""
        return self._items("MOBILES")

    @property
    def objects(self) -> list[Object]:
        """Oggetti (#OBJECTS)."""
        return self._items("OBJECTS")

    @property
    def rooms(self) -> list[Room]:
        """Stanze (#ROOMS)."""
        return self._items("ROOMS")

    @property
    def resets(self) -> list[Reset | CommentLine]:
        """Reset (#RESETS), con eventuali righe di commento."""
        return self._items("RESETS")

    @property
    def shops(self) -> list[Shop]:
        """Negozi (#SHOPS)."""
        return self._items("SHOPS")

    @property
    def specials(self) -> list[Special | CommentLine]:
        """Special procedure (#SPECIALS)."""
        return self._items("SPECIALS")

    @property
    def mobprogs(self) -> list[MobProg]:
        """Mobprog (#MOBPROGS)."""
        return self._items("MOBPROGS")

    @property
    def helps(self) -> list[Help]:
        """Help (#HELPS)."""
        return self._items("HELPS")

    @property
    def socials(self) -> list[Social]:
        """Social (#SOCIALS)."""
        return self._items("SOCIALS")

    @property
    def raw_sections(self) -> list[Section]:
        """Sezioni sconosciute conservate come testo grezzo."""
        return [s for s in self.sections if s.kind == "RAW"]

    def find_mobile(self, vnum: int) -> Mobile | None:
        """Mob per vnum o None."""
        return next((m for m in self.mobiles if m.vnum == vnum), None)

    def find_object(self, vnum: int) -> Object | None:
        """Oggetto per vnum o None."""
        return next((o for o in self.objects if o.vnum == vnum), None)

    def find_room(self, vnum: int) -> Room | None:
        """Stanza per vnum o None."""
        return next((r for r in self.rooms if r.vnum == vnum), None)


__all__ = [
    "Area", "AreaHeader", "CommentLine", "DIRECTIONS", "Dice", "Exit", "ExtraDescription", "FLAG_TABLES",
    "FlagRemoval", "Help", "MobProg", "MobProgTrigger", "Mobile", "Object", "ObjectAffect", "Reset",
    "Room", "Section", "Shop", "Social", "Special",
]
