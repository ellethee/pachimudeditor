"""Lettura (solo lettura) dei file giocatore di Diku Modificato: `players/<nome>.dat` e `rent/<nome>`.

Formato: la struct C **cosi' com'e'** su disco (`structs.h`: `char_file_u` 3036 byte, `obj_file_u` = 40 byte di testata + `number`
elementi `obj_file_elem` da 592). Little-endian e padding naturale i386/x86-64 sono resi con **offset espliciti** (verificati
compilando le struct con g++: `offsetof`), mai con `struct` nativo. La password (`pwd[11]`, offset 2974) NON viene mai restituita:
l'unica informazione che ne esce e' se il campo e' vuoto (`has_password`). Nessuna scrittura.
"""

from __future__ import annotations

import os
import re
import stat
import struct
from dataclasses import dataclass, field
from pathlib import Path

CHAR_FILE_SIZE = 3036
"""`sizeof(struct char_file_u)` (static assert in `structs.h`)."""
RENT_HEADER_SIZE = 40
"""`owner[20]` + `gold_left` + `total_cost` + `last_update` + `minimum_stay` + `number`."""
RENT_ELEM_SIZE = 592
"""`sizeof(struct obj_file_elem)`."""
MAX_OBJ_SAVE = 200
"""`MAX_OBJ_SAVE` di `structs.h`: oltre, il gioco andrebbe in overflow."""
MAX_WEAR = 23
"""Slot equipaggiabili (`wearpos` 1..23; 0 = nell'inventario)."""
ABS_MAX_CLASS = 20
MAX_CLASS = 11
MAX_SKILLS = 350
MAX_AFFECT = 40
MAX_DEPTH = 60

NAME_RE = re.compile(r"[a-z][a-z0-9_-]{0,19}")
"""Nome di file giocatore ammesso (il gioco usa il nome in minuscolo): nessun separatore, nessun punto."""

CLASS_NAMES: tuple[str, ...] = (
    "magic_user", "cleric", "warrior", "thief", "druid", "monk", "barbarian", "sorcerer", "paladin", "ranger", "psi",
)  # fmt: skip
"""`CLASS_*` di `structs.h`: il bit `1 << i` di `iClass` e' `CLASS_NAMES[i]`."""
SEX_NAMES = ("neutral", "male", "female")
CONDITION_NAMES = ("drunk", "full", "thirst", "x3", "x4")
"""`conditions[5]`: `DRUNK`, `FULL`, `THIRST` (gli altri due non hanno nome)."""

# offset nel record char_file_u (little-endian)
_O_CLASS, _O_SEX, _O_LEVEL = 0, 4, 5
_O_BIRTH, _O_PLAYED, _O_RACE, _O_WEIGHT, _O_HEIGHT = 28, 32, 36, 40, 44
_O_TITLE, _O_HOMETOWN, _O_DESC = 48, 384, 386
_O_EXTRA_FLAGS, _O_LOAD_ROOM, _O_ABIL = 632, 636, 638
_O_POINTS, _O_SKILLS, _O_AFFECTED = 648, 700, 2100
_O_SPELLS_TO_LEARN, _O_ALIGN, _O_AFF_BY, _O_AFF_BY2 = 2900, 2904, 2908, 2912
_O_LAST_LOGON, _O_ACT, _O_NAME, _O_ALIAS = 2916, 2920, 2924, 2944
_O_PWD, _PWD_LEN = 2974, 11
_O_SAVES, _O_COND, _O_STARTROOM, _O_USER_FLAGS, _O_SPEAKS = 2986, 3004, 3024, 3028, 3032


class PlayerFileError(ValueError):
    """File giocatore non utilizzabile. `code` e' un codice stabile (`bad_size`, `not_regular`, `outside_dir`, `unreadable`)."""

    def __init__(self, code: str, message: str = "") -> None:
        """`code` stabile, `message` leggibile (mai contenuti di password)."""
        super().__init__(message or code)
        self.code = code


def _text(raw: bytes) -> str:
    """Stringa C (fino al primo NUL), latin-1, senza caratteri di controllo."""
    return "".join(c for c in raw.split(b"\0", 1)[0].decode("latin-1") if c >= " " or c == "\t")


@dataclass(frozen=True)
class SkillEntry:
    """Una abilita'/incantesimo del giocatore (`index` = numero di skill)."""

    index: int
    learned: int
    flags: int
    special: int
    nummem: int


@dataclass(frozen=True)
class AffectEntry:
    """Un effetto attivo (`affected_file`)."""

    type: int
    duration: int
    modifier: int
    location: int
    bitvector: int


@dataclass(frozen=True, repr=False)
class CharRecord:
    """Un `char_file_u` interpretato. **Non contiene la password**, solo `has_password`."""

    name: str
    class_mask: int
    sex: int
    levels: tuple[int, ...]
    birth: int
    played: int
    race: int
    weight: int
    height: int
    title: str
    description: str
    hometown: int
    extra_flags: int
    load_room: int
    start_room: int
    abilities: dict[str, int]
    points: dict[str, int]
    alignment: int
    affected_by: int
    affected_by2: int
    last_logon: int
    act: int
    alias: str
    has_password: bool
    saving_throws: tuple[int, ...]
    conditions: tuple[int, ...]
    user_flags: int
    speaks: int
    spells_to_learn: int
    skills: tuple[SkillEntry, ...] = field(default_factory=tuple)
    affects: tuple[AffectEntry, ...] = field(default_factory=tuple)
    extra_str: str = ""

    def __repr__(self) -> str:
        """Breve e senza dati sensibili (nome e livello)."""
        return f"CharRecord(name={self.name!r}, level={self.level})"

    @property
    def classes(self) -> list[str]:
        """Nomi delle classi i cui bit sono accesi in `iClass`."""
        return [n for i, n in enumerate(CLASS_NAMES) if self.class_mask & (1 << i)]

    @property
    def level(self) -> int:
        """Livello massimo tra le classi del personaggio (se nessun bit di classe: tra le `MAX_CLASS` classi)."""
        picked = [self.levels[i] for i in range(MAX_CLASS) if self.class_mask & (1 << i)]
        return max(picked or self.levels[:MAX_CLASS] or [0])


def parse_char_record(data: bytes) -> CharRecord:
    """Interpreta un record da esattamente 3036 byte.

    Raises:
        PlayerFileError: `bad_size` se la lunghezza non e' 3036.
    """
    if len(data) != CHAR_FILE_SIZE:
        raise PlayerFileError("bad_size", f"il record deve essere di {CHAR_FILE_SIZE} byte, non {len(data)}")

    def i32(offset: int) -> int:
        return struct.unpack_from("<i", data, offset)[0]

    def u32(offset: int) -> int:
        return struct.unpack_from("<I", data, offset)[0]

    def i16(offset: int) -> int:
        return struct.unpack_from("<h", data, offset)[0]

    def i8(offset: int) -> int:
        return struct.unpack_from("<b", data, offset)[0]

    names = ("str", "strAdd", "int", "wis", "dex", "con", "chr", "extra", "extra2")
    abilities = {n: i8(_O_ABIL + k) for k, n in enumerate(names)}
    p = _O_POINTS
    points = {
        "mana": i16(p), "maxMana": i16(p + 2), "hit": i16(p + 6), "maxHit": i16(p + 8), "move": i16(p + 12), "maxMove": i16(p + 14),
        "armor": i16(p + 24), "gold": i32(p + 28), "bankGold": i32(p + 32), "exp": i32(p + 36), "trueExp": i32(p + 40),
        "hitroll": i8(p + 48), "damroll": i8(p + 49),
    }  # fmt: skip
    skills = []
    for n in range(MAX_SKILLS):
        learned, flags, special, nummem = struct.unpack_from("<4B", data, _O_SKILLS + n * 4)
        if learned or flags:
            skills.append(SkillEntry(n, learned, flags, special, nummem))
    affects = []
    for n in range(MAX_AFFECT):
        type_, duration, modifier, location, bitvector = struct.unpack_from("<hhiii", data, _O_AFFECTED + n * 20)
        if type_ or duration or modifier or location or bitvector:
            affects.append(AffectEntry(type_, duration, modifier, location, bitvector))
    # solo "e' vuota?": i byte della password non lasciano questa funzione
    has_password = any(data[_O_PWD : _O_PWD + _PWD_LEN - 1].split(b"\0", 1)[0])
    return CharRecord(
        name=_text(data[_O_NAME : _O_NAME + 20]),
        class_mask=i32(_O_CLASS),
        sex=data[_O_SEX],
        levels=tuple(data[_O_LEVEL : _O_LEVEL + ABS_MAX_CLASS]),
        birth=i32(_O_BIRTH),
        played=i32(_O_PLAYED),
        race=i32(_O_RACE),
        weight=u32(_O_WEIGHT),
        height=u32(_O_HEIGHT),
        title=_text(data[_O_TITLE : _O_TITLE + 80]),
        description=_text(data[_O_DESC : _O_DESC + 240]),
        hometown=i16(_O_HOMETOWN),
        extra_flags=i32(_O_EXTRA_FLAGS),
        load_room=i16(_O_LOAD_ROOM),
        start_room=i32(_O_STARTROOM),
        abilities=abilities,
        points=points,
        alignment=i32(_O_ALIGN),
        affected_by=u32(_O_AFF_BY),
        affected_by2=u32(_O_AFF_BY2),
        last_logon=i32(_O_LAST_LOGON),
        act=u32(_O_ACT),
        alias=_text(data[_O_ALIAS : _O_ALIAS + 30]),
        has_password=bool(has_password),
        saving_throws=struct.unpack_from("<8h", data, _O_SAVES),
        conditions=struct.unpack_from("<5i", data, _O_COND),
        user_flags=i32(_O_USER_FLAGS),
        speaks=i32(_O_SPEAKS),
        spells_to_learn=data[_O_SPELLS_TO_LEARN],
        skills=tuple(skills),
        affects=tuple(affects),
        extra_str=_text(data[128:383]),
    )


@dataclass(frozen=True)
class RentAffect:
    """Un effetto di un oggetto salvato."""

    location: int
    modifier: int


@dataclass(frozen=True)
class RentItem:
    """Un `obj_file_elem`. `wearpos` 0 = inventario, `n` = slot `n - 1`; `depth` = annidamento nei contenitori."""

    index: int
    item_number: int
    values: tuple[int, int, int, int]
    extra_flags: int
    weight: int
    timer: int
    bitvector: int
    name: str
    short: str
    description: str
    wearpos: int
    depth: int
    affects: tuple[RentAffect, ...]


@dataclass(frozen=True)
class RentFile:
    """Un `obj_file_u` (anche troncato o corrotto: `problem` dice cosa non va, gli oggetti leggibili ci sono comunque)."""

    owner: str = ""
    gold_left: int = 0
    total_cost: int = 0
    last_update: int = 0
    minimum_stay: int = 0
    number: int = 0
    items: tuple[RentItem, ...] = ()
    problem: str | None = None
    """`truncated_header`, `too_many_items` (numero fuori 0..200: nessun oggetto letto), `truncated` (meno elementi del dichiarato),
    `trailing_data` (byte in piu'); `None` = file coerente (o vuoto: rent azzerato)."""


def parse_rent(data: bytes) -> RentFile:
    """Interpreta un file rent senza mai fidarsi di `number`: nessuna eccezione per file vuoti, troncati o corrotti."""
    if not data:
        return RentFile()
    if len(data) < RENT_HEADER_SIZE:
        return RentFile(problem="truncated_header")
    owner = _text(data[:20])
    gold_left, total_cost, last_update, minimum_stay, number = struct.unpack_from("<iiiii", data, 20)
    if not 0 <= number <= MAX_OBJ_SAVE:
        return RentFile(owner, gold_left, total_cost, last_update, minimum_stay, number, (), "too_many_items")
    available = (len(data) - RENT_HEADER_SIZE) // RENT_ELEM_SIZE
    count = min(number, available)
    items = tuple(_rent_item(data, RENT_HEADER_SIZE + k * RENT_ELEM_SIZE, k) for k in range(count))
    problem = "truncated" if available < number else "trailing_data" if len(data) != RENT_HEADER_SIZE + number * RENT_ELEM_SIZE else None
    return RentFile(owner, gold_left, total_cost, last_update, minimum_stay, number, items, problem)


def _rent_item(data: bytes, base: int, index: int) -> RentItem:
    """Un `obj_file_elem` da 592 byte che inizia a `base`."""
    (item_number,) = struct.unpack_from("<h", data, base)
    values = struct.unpack_from("<4i", data, base + 4)
    extra_flags, weight, timer, bitvector = struct.unpack_from("<4i", data, base + 20)
    wearpos, depth = data[base + 548], data[base + 549]
    affects = []
    for n in range(5):
        location, modifier = struct.unpack_from("<hxxi", data, base + 552 + n * 8)
        if location or modifier:
            affects.append(RentAffect(location, modifier))
    return RentItem(
        index=index,
        item_number=item_number,
        values=values,  # type: ignore[arg-type]
        extra_flags=extra_flags,
        weight=weight,
        timer=timer,
        bitvector=bitvector,
        name=_text(data[base + 36 : base + 164]),
        short=_text(data[base + 164 : base + 292]),
        description=_text(data[base + 292 : base + 548]),
        wearpos=wearpos,
        depth=depth,
        affects=tuple(affects),
    )


# ------------------------------------------------------------------ file system


def player_names(players_dir: Path) -> list[str]:
    """I nomi (stem) dei file `<nome>.dat` ammessi in `players_dir`, ordinati; i `.dat~`, i backup e i nomi strani sono ignorati."""
    try:
        entries = os.listdir(players_dir)
    except OSError:
        return []
    names = []
    for entry in entries:
        stem, dot, ext = entry.rpartition(".")
        if dot and ext == "dat" and NAME_RE.fullmatch(stem):
            names.append(stem)
    return sorted(names)


def read_confined(directory: Path, filename: str, max_bytes: int) -> tuple[bytes, os.stat_result]:
    """Legge `directory/filename` (al massimo `max_bytes + 1` byte) solo se e' un file regolare che, risolti i symlink,
    sta dentro `directory`.

    Raises:
        FileNotFoundError: il file non esiste.
        PlayerFileError: `outside_dir` (symlink verso l'esterno), `not_regular` (cartella, fifo, ...), `unreadable`.
    """
    path = directory / filename
    if filename != os.path.basename(filename) or filename in ("", ".", ".."):
        raise PlayerFileError("outside_dir", "nome di file non valido")
    try:
        real_dir = directory.resolve(strict=True)
        real = path.resolve(strict=True)
    except FileNotFoundError:
        raise
    except OSError as error:  # anello di symlink e simili
        raise PlayerFileError("unreadable", error.__class__.__name__) from error
    if real.parent != real_dir:
        raise PlayerFileError("outside_dir", "il file risolve fuori dalla cartella")
    try:
        st = real.stat()
        if not stat.S_ISREG(st.st_mode):
            raise PlayerFileError("not_regular", "non e' un file regolare")
        with real.open("rb") as handle:
            return handle.read(max_bytes + 1), st
    except FileNotFoundError:
        raise
    except OSError as error:
        raise PlayerFileError("unreadable", error.__class__.__name__) from error


def read_char_bytes(players_dir: Path, name: str) -> tuple[bytes, float]:
    """`(byte, mtime)` di `players/<name>.dat`, solo se sono esattamente 3036 byte.

    Raises:
        FileNotFoundError: manca. PlayerFileError: dimensione diversa da 3036, symlink fuori cartella, non regolare, illeggibile.
    """
    if not NAME_RE.fullmatch(name):
        raise FileNotFoundError(name)
    data, st = read_confined(players_dir, f"{name}.dat", CHAR_FILE_SIZE)
    if len(data) != CHAR_FILE_SIZE:
        raise PlayerFileError("bad_size", f"il record deve essere di {CHAR_FILE_SIZE} byte")
    return data, st.st_mtime


def read_char_file(players_dir: Path, name: str) -> tuple[CharRecord, float]:
    """`(record, mtime)` di `players/<name>.dat` (stesse eccezioni di `read_char_bytes`)."""
    data, mtime = read_char_bytes(players_dir, name)
    return parse_char_record(data), mtime


def read_rent_bytes(rent_dir: Path, name: str) -> bytes | None:
    """I byte di `rent/<name>`, `None` se il file non esiste o il nome non e' ammesso.

    Raises:
        PlayerFileError: symlink fuori cartella, non regolare, illeggibile.
    """
    if not NAME_RE.fullmatch(name):
        return None
    try:
        data, _ = read_confined(rent_dir, name, RENT_HEADER_SIZE + MAX_OBJ_SAVE * RENT_ELEM_SIZE + RENT_ELEM_SIZE)
    except FileNotFoundError:
        return None
    return data


def read_rent_file(rent_dir: Path, name: str) -> RentFile | None:
    """Il rent di `name` (`rent/<name>`), `None` se il file non esiste (stesse eccezioni di `read_rent_bytes`)."""
    data = read_rent_bytes(rent_dir, name)
    return None if data is None else parse_rent(data)


def write_target(directory: Path, filename: str) -> Path:
    """Il percorso reale su cui scrivere `directory/filename` (un symlink e' risolto), solo se resta dentro `directory` e non e'
    una cartella o un file speciale. Un file che non esiste ancora e' ammesso (verra' creato).

    Raises:
        PlayerFileError: `outside_dir`, `not_regular`, `unreadable`.
    """
    if filename != os.path.basename(filename) or filename in ("", ".", ".."):
        raise PlayerFileError("outside_dir", "nome di file non valido")
    try:
        real_dir = directory.resolve(strict=True)
        path = directory / filename
        real = path.resolve(strict=True) if os.path.lexists(path) else real_dir / filename
    except OSError as error:
        raise PlayerFileError("unreadable", error.__class__.__name__) from error
    if real.parent != real_dir:
        raise PlayerFileError("outside_dir", "il file risolve fuori dalla cartella")
    if real.exists() and not stat.S_ISREG(real.stat().st_mode):
        raise PlayerFileError("not_regular", "non e' un file regolare")
    return real
