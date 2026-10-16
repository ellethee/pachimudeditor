"""Modello dei dati Diku Modificato: dataclass per entita' e i contenitori di file.

Ogni entita' letta ricorda il testo sorgente (`_src`) e un'impronta dei campi (`_fp`, la `repr` al momento del parsing).
In scrittura un'entita' con impronta invariata viene riemessa **byte per byte**; una modificata o nuova viene scritta in
forma canonica (come la rilegge `db.c`). I record non interpretabili sono `Raw`: mantengono il testo e l'errore e
vengono sempre riemessi identici.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import Diagnostic


def _meta() -> Any:
    """Campo di servizio (sorgente / impronta): escluso da repr, eq e init posizionale."""
    return field(default=None, repr=False, compare=False, kw_only=True)


@dataclass
class Dice:
    """Dado `NdM+K` (hp dei mob `S`, danno)."""

    n: int = 1
    m: int = 4
    k: int = 0

    def __str__(self) -> str:
        """Forma letta da `fscanf(" %ldd%ld+%ld ")`: un bonus negativo e' `+-K`."""
        return f"{self.n}d{self.m}+{self.k}"

    @classmethod
    def parse(cls, text: str) -> "Dice":
        """`2d6+3`, `2d6-3` o `2d6+-3`; `ValueError` se non e' un dado."""
        import re

        m = re.fullmatch(r"\s*(-?\d+)d(-?\d+)(?:\+(-?\d+)|(-\d+))\s*", text)
        if not m:
            raise ValueError(f"dado non valido: {text!r}")
        return cls(int(m.group(1)), int(m.group(2)), int(m.group(3) or m.group(4)))


# --------------------------------------------------------------------------- stanze


@dataclass
class Exit:
    """Uscita `D<n>`. `open_cmd` e' il numero opzionale dopo `to_room` (None = assente)."""

    door: int = 0
    description: str = ""
    keyword: str = ""
    info: int = 0
    key: int = -1
    to_room: int = -1
    open_cmd: int | None = None


@dataclass
class ExtraDesc:
    """Extra description `E` di stanza/oggetto."""

    keyword: str = ""
    description: str = ""


@dataclass
class Tele:
    """Blocco teleport (settore -1): `count` esiste solo se `mask & 2` (TELE_COUNT)."""

    time: int = 0
    target: int = 0
    mask: int = 0
    count: int | None = None


@dataclass
class Room:
    """Stanza. `sector` e' il settore vero (con `tele` presente il file scrive prima -1)."""

    vnum: int = 0
    name: str = ""
    description: str = ""
    zone_ignored: int = 0
    flags: int = 0
    sector: int = 0
    tele: Tele | None = None
    river: tuple[int, int] | None = None
    moblim: int | None = None
    exits: list[Exit] = field(default_factory=list)
    extra_descs: list[ExtraDesc] = field(default_factory=list)
    light: tuple[str, str] | None = None
    _src: str | None = _meta()
    _fp: str | None = _meta()

    def exit_for(self, door: int) -> Exit | None:
        """L'uscita nella direzione (l'ultima vince, come nel loader)."""
        found = [x for x in self.exits if x.door == door]
        return found[-1] if found else None


# --------------------------------------------------------------------------- mob


@dataclass
class Mob:
    """Mob prototipo. `kind` S/A/N/B/L. `hp_dice` solo per `S`, `hp_bonus` per gli altri (hp = level d8 + bonus)."""

    vnum: int = 0
    name: str = ""
    short: str = ""
    long: str = ""
    description: str = ""
    act: int = 0
    affected: int = 0
    alignment: int = 0
    kind: str = "N"
    multi: int | None = None
    level: int = 1
    thac0: int = 20
    ac: int = 0
    hp_dice: Dice | None = None
    hp_bonus: int = 0
    damage: Dice = field(default_factory=Dice)
    gold: int = 0
    exp: int = 0
    race: int | None = None
    position: int = 8
    default_pos: int = 8
    sex_code: int = 0
    immune: int = 0
    m_immune: int = 0
    susc: int = 0
    sound: str | None = None
    distant_sound: str | None = None
    trailing: str = ""
    """Testo dopo l'ultimo campo letto dal gioco (ignorato da `read_mobile`: es. `0 0 0` o stringhe di suono su un `N`)."""
    _src: str | None = _meta()
    _fp: str | None = _meta()

    @property
    def sex(self) -> int:
        """Sesso 0 neutro, 1 maschio, 2 femmina (codici 3..5 = sesso + 3 con maschere; >= 6 neutro)."""
        c = self.sex_code
        return c if c < 3 else (c - 3 if c < 6 else 0)


# --------------------------------------------------------------------------- oggetti


@dataclass
class ObjAffect:
    """Riga `A` di un oggetto (`location` = apply, `modifier`)."""

    location: int = 0
    modifier: int = 0


@dataclass
class Obj:
    """Oggetto prototipo (massimo 5 affect, E prima di A, P in fondo)."""

    vnum: int = 0
    name: str = ""
    short: str = ""
    description: str = ""
    action: str = ""
    type: int = 12
    extra_flags: int = 0
    wear_flags: int = 0
    values: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    weight: int = 0
    cost: int = 0
    rent: int = 0
    extra_descs: list[ExtraDesc] = field(default_factory=list)
    affects: list[ObjAffect] = field(default_factory=list)
    forbidden: tuple[str, str] | None = None
    _src: str | None = _meta()
    _fp: str | None = _meta()


MAX_OBJ_AFFECT = 5
"""`MAX_OBJ_AFFECT` di `structs.h`."""


# --------------------------------------------------------------------------- zone


@dataclass
class ZoneCmd:
    """Comando di reset di una zona. `args` esclude `if_flag`; `comment` e' il resto grezzo della riga dopo l'ultimo
    argomento (`\\t; testo`). Un `O` con 3 argomenti (manca `max_in_room`) e' la forma che il loader C legge male."""

    letter: str = "M"
    if_flag: int = 0
    args: list[int] = field(default_factory=list)
    comment: str = ""
    _src: str | None = _meta()
    _fp: str | None = _meta()

    @property
    def comment_text(self) -> str:
        """Il commento senza separatori (`;`, `*!`) ne' spazi ai bordi."""
        text = self.comment.strip()
        while text[:1] in (";", "*", "!"):
            text = text[1:].lstrip()
        return text.strip()


@dataclass
class ZoneText:
    """Riga non-comando di una zona (commento `* ...`, riga vuota): conservata dov'e'."""

    text: str = ""
    _src: str | None = _meta()
    _fp: str | None = _meta()


@dataclass
class Zone:
    """Zona di `dikumoddata.zon`: `num` (`#N`, non univoco), `top`, `lifespan`, `reset_mode`. `has_end`: c'e' la `S` finale."""

    num: int = 0
    name: str = ""
    top: int = 0
    lifespan: int = 0
    reset_mode: int = 0
    items: list[ZoneCmd | ZoneText] = field(default_factory=list)
    has_end: bool = True
    _src: str | None = _meta()
    _fp: str | None = _meta()

    @property
    def commands(self) -> list[ZoneCmd]:
        """I soli comandi (senza commenti/righe vuote)."""
        return [i for i in self.items if isinstance(i, ZoneCmd)]


@dataclass
class ZoneOverride:
    """`zones/<n>.zon`: solo comandi fino a `S`, senza intestazione."""

    index: int = 0
    items: list[ZoneCmd | ZoneText] = field(default_factory=list)
    has_end: bool = True
    _src: str | None = _meta()
    _fp: str | None = _meta()

    @property
    def commands(self) -> list[ZoneCmd]:
        """I soli comandi."""
        return [i for i in self.items if isinstance(i, ZoneCmd)]


# --------------------------------------------------------------------------- negozi, script


@dataclass
class Shop:
    """Negozio di `dikumoddata.shp` (ordine dei campi di `boot_the_shops`). I moltiplicatori restano testo (`1.1`, `.001`)."""

    tag: str = "#0"
    producing: list[int] = field(default_factory=lambda: [-1, -1, -1, -1, -1])
    profit_buy: str = "1.0"
    profit_sell: str = "1.0"
    types: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0])
    messages: list[str] = field(default_factory=lambda: [""] * 7)
    temper1: int = 0
    temper2: int = 0
    keeper: int = 0
    with_who: int = 0
    room: int = 0
    open1: int = 0
    close1: int = 28
    open2: int = 0
    close2: int = 0
    _src: str | None = _meta()
    _fp: str | None = _meta()


MESSAGE_NAMES = (
    "no_such_item1", "no_such_item2", "do_not_buy", "missing_cash1", "missing_cash2", "message_buy", "message_sell",
)  # fmt: skip
"""Nomi dei sette messaggi del negozio, nell'ordine del file."""


@dataclass
class ScriptEntry:
    """Riga di `scripts.dat`: `Nome vnum_mob`."""

    name: str = ""
    vnum: int = 0
    _src: str | None = _meta()
    _fp: str | None = _meta()


# --------------------------------------------------------------------------- contenitori


@dataclass
class Raw:
    """Record non interpretabile: testo e motivo. Mai modificato, sempre riemesso identico."""

    vnum: int | None
    src: str
    error: str
    line: int = 0


Item = Any
"""Un elemento di `RecordFile.items`: entita' o `Raw`."""


@dataclass(eq=False)
class RecordFile:
    """File di record: `head` (prima del primo record), `items`, `tail` (terminatore e resto: `%%~`, `#9999999 $~`...)."""

    kind: str
    path: Path | None = None
    head: str = ""
    items: list[Item] = field(default_factory=list)
    tail: str = ""
    diagnostics: list[Diagnostic] = field(default_factory=list)
    _snapshot: list[int] | None = field(default=None, repr=False)

    def mark_clean(self) -> None:
        """Memorizza l'elenco degli elementi come "appena letto" (vedi `is_clean`)."""
        self._snapshot = [id(i) for i in self.items]

    def is_clean(self) -> bool:
        """True se nessun elemento e' stato aggiunto/tolto/riordinato/modificato dopo la lettura (nulla da riscrivere)."""
        if self._snapshot is None or self._snapshot != [id(i) for i in self.items]:
            return False
        return all(isinstance(i, Raw) or (i._src is not None and i._fp == repr(i)) for i in self.items)

    def entities(self) -> list[Item]:
        """Gli elementi interpretati (senza `Raw`)."""
        return [i for i in self.items if not isinstance(i, Raw)]

    def raws(self) -> list[Raw]:
        """I record corrotti."""
        return [i for i in self.items if isinstance(i, Raw)]

    def find(self, vnum: int) -> Item | None:
        """Il primo elemento con quel vnum (entita' o `Raw`)."""
        return next((i for i in self.items if getattr(i, "vnum", None) == vnum), None)
