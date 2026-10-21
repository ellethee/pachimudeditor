"""Scrittura (solo byte in memoria, nessun I/O) dei file giocatore di Diku Modificato, simmetrica a `players.py`.

Principio: si parte dai byte **attuali** del file e si sovrascrivono solo i campi modificati, con gli stessi offset espliciti
(little-endian) del parser. Tutto il resto (compresi i campi che l'editor non conosce, il padding, i puntatori `next` degli
affect e soprattutto la **password**, offset 2974..2984) resta byte-per-byte com'e': nessuna modifica = file identico.
Ogni valore e' validato (tipo, intervallo del tipo C, lunghezza dei campi char fissi, enum); gli errori sono `PlayerValueError`
con un `reason` stabile, mai un'eccezione generica.

Rent (`obj_file_u`): `RentEditor` modifica una lista di record da 592 byte con le regole di `obj_store_to_char` (`reception.c`):
`depth` > 0 = dentro l'ultimo oggetto di profondita' inferiore, mai equipaggiato e contenuto insieme, al massimo 200 oggetti,
`owner` uguale al nome del personaggio (altrimenti il gioco scarta gli oggetti e al boot `update_obj_file` fa `assert(0)`).
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from . import tables as T
from .players import (
    _O_ABIL,
    _O_AFFECTED,
    _O_COND,
    _O_LEVEL,
    _O_PWD,
    _O_SAVES,
    _O_SKILLS,
    _PWD_LEN,
    CHAR_FILE_SIZE,
    CLASS_NAMES,
    CONDITION_NAMES,
    MAX_AFFECT,
    MAX_CLASS,
    MAX_DEPTH,
    MAX_OBJ_SAVE,
    MAX_SKILLS,
    MAX_WEAR,
    NAME_RE,
    RENT_ELEM_SIZE,
    RENT_HEADER_SIZE,
    PlayerFileError,
    _text,
    parse_rent,
)

MAX_LEVEL = 255
"""`level[]` e' un byte; il gioco usa 1..59 (`IMPLEMENTOR`), ma l'editor non impone il bilanciamento, solo il tipo."""
MAX_ITEM_VNUM = 32767
"""`item_number` e' un `sh_int`."""

_FMT_RANGE = {
    "b": (-(2**7), 2**7 - 1), "B": (0, 2**8 - 1), "h": (-(2**15), 2**15 - 1), "H": (0, 2**16 - 1),
    "i": (-(2**31), 2**31 - 1), "I": (0, 2**32 - 1),
}  # fmt: skip

# nome del campo -> (formato struct, offset, minimo, massimo); minimo/massimo None = quelli del tipo
_SCALARS: dict[str, tuple[str, int, int | None, int | None]] = {
    "classMask": ("i", 0, 0, (1 << MAX_CLASS) - 1), "sex": ("B", 4, 0, len(T.SEXES) - 1), "played": ("i", 32, 0, None),
    "race": ("i", 36, 0, len(T.RACES) - 1), "weight": ("I", 40, None, None), "height": ("I", 44, None, None),
    "hometown": ("h", 384, None, None), "extraFlags": ("i", 632, None, None), "loadRoom": ("h", 636, None, None),
    "str": ("b", _O_ABIL, None, None), "strAdd": ("b", _O_ABIL + 1, None, None), "int": ("b", _O_ABIL + 2, None, None),
    "wis": ("b", _O_ABIL + 3, None, None), "dex": ("b", _O_ABIL + 4, None, None), "con": ("b", _O_ABIL + 5, None, None),
    "chr": ("b", _O_ABIL + 6, None, None),
    "mana": ("h", 648, None, None), "maxMana": ("h", 650, None, None), "hit": ("h", 654, None, None), "maxHit": ("h", 656, None, None),
    "move": ("h", 660, None, None), "maxMove": ("h", 662, None, None), "armor": ("h", 672, None, None),
    "gold": ("i", 676, 0, None), "bankGold": ("i", 680, 0, None), "exp": ("i", 684, None, None), "trueExp": ("i", 688, None, None),
    "hitroll": ("b", 696, None, None), "damroll": ("b", 697, None, None),
    "spellsToLearn": ("B", 2900, None, None), "alignment": ("i", 2904, None, None), "affectedBy2": ("I", 2912, None, None),
    "actFlags": ("I", 2920, None, None), "startRoom": ("i", 3024, None, None), "userFlags": ("i", 3028, None, None),
    "speaks": ("i", 3032, None, None),
}  # fmt: skip
_AFFECT_BY = ("I", 2908)
_DATES = {"birth": 28, "lastLogon": 2916}
_STRINGS = {"title": (48, 80), "extraStr": (128, 255), "description": (386, 240), "alias": (2944, 30)}
READ_ONLY_FIELDS = frozenset({"name", "level", "autoRent", "password", "pwd"})
"""Mai scrivibili: il nome e' l'identita' del file, il livello e' derivato dai `levels`, `autoRent` da `loadRoom`, la password mai."""
WRITABLE_FIELDS = frozenset({*_SCALARS, *_DATES, *_STRINGS, "affectedBy", "levels", "conditions", "savingThrows"})
"""I nomi di `PlayerPatch.details` ammessi (gli altri: `read_only` o `unknown_field`)."""


class PlayerValueError(ValueError):
    """Valore non scrivibile. `reason` e' stabile: `type`, `range`, `too_long`, `charset`, `unknown_field`, `read_only`, `unknown_flag`,
    `unknown_class`, `duplicate`, `too_many`, `slot_taken`, ...; `params` porta i dettagli (mai contenuti della password)."""

    def __init__(self, field: str, reason: str, **params: Any) -> None:
        """`field` = nome del campo/operazione, `reason` stabile."""
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason
        self.params = params


# ------------------------------------------------------------------ revisioni


def char_revision(data: bytes) -> str:
    """Impronta del file giocatore **senza** i byte della password (non deve poter servire a indovinarla)."""
    masked = bytearray(data)
    masked[_O_PWD : _O_PWD + _PWD_LEN] = bytes(_PWD_LEN)
    return hashlib.sha256(bytes(masked)).hexdigest()[:16]


def rent_revision(data: bytes | None) -> str:
    """Impronta del file rent (assente e vuoto coincidono: entrambi «nessun oggetto»)."""
    return hashlib.sha256(data or b"").hexdigest()[:16]


# ------------------------------------------------------------------ validazione


def _int(field: str, value: Any, low: int, high: int) -> int:
    """Un intero (non bool, non float) nell'intervallo."""
    if type(value) is not int:
        raise PlayerValueError(field, "type", expected="integer")
    if not low <= value <= high:
        raise PlayerValueError(field, "range", min=low, max=high)
    return value


def _string(field: str, value: Any, size: int) -> bytes:
    """Stringa C: latin-1, nessun carattere di controllo, al massimo `size - 1` caratteri; NUL-riempita a `size`."""
    if not isinstance(value, str):
        raise PlayerValueError(field, "type", expected="string")
    if any((ord(c) < 32 and c != "\t") or ord(c) == 127 for c in value):  # la tab e' ammessa: il lettore (`_text`) la conserva
        raise PlayerValueError(field, "charset")
    try:
        raw = value.encode("latin-1")
    except UnicodeEncodeError as error:
        raise PlayerValueError(field, "charset") from error
    if len(raw) > size - 1:
        raise PlayerValueError(field, "too_long", max=size - 1)
    return raw.ljust(size, b"\0")


def _timestamp(field: str, value: Any) -> int:
    """ISO 8601 (o `null` = 0) come `time_t` a 32 bit."""
    if value is None:
        return 0
    if not isinstance(value, str):
        raise PlayerValueError(field, "type", expected="datetime")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as error:
        raise PlayerValueError(field, "type", expected="datetime") from error
    seconds = int((moment if moment.tzinfo else moment.replace(tzinfo=UTC)).timestamp())
    return _int(field, seconds, 0, 2**31 - 1)


def _flags(field: str, value: Any, table: Mapping[str, int]) -> int:
    """Nomi di flag -> maschera (ogni nome deve stare nella tabella)."""
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise PlayerValueError(field, "type", expected="list")
    mask = 0
    for name in value:
        if not isinstance(name, str) or name not in table:
            raise PlayerValueError(field, "unknown_flag")
        mask |= table[name]
    return mask


def _set_levels(buf: bytearray, value: Any) -> None:
    """`{classe: livello}` sostituisce i livelli delle `MAX_CLASS` classi (assenti = 0); gli slot oltre restano."""
    if not isinstance(value, Mapping):
        raise PlayerValueError("levels", "type", expected="object")
    new = [0] * MAX_CLASS
    for key, level in value.items():
        code = str(key).strip().lower().replace(" ", "_")
        if code not in CLASS_NAMES:
            raise PlayerValueError("levels", "unknown_class")
        new[CLASS_NAMES.index(code)] = _int("levels", level, 0, MAX_LEVEL)
    buf[_O_LEVEL : _O_LEVEL + MAX_CLASS] = bytes(new)


def _set_conditions(buf: bytearray, value: Any) -> None:
    """`{drunk, full, thirst, x3, x4}`: solo le chiavi presenti cambiano."""
    if not isinstance(value, Mapping):
        raise PlayerValueError("conditions", "type", expected="object")
    for key, number in value.items():
        if key not in CONDITION_NAMES:
            raise PlayerValueError("conditions", "unknown_field")
        struct.pack_into("<i", buf, _O_COND + CONDITION_NAMES.index(key) * 4, _int("conditions", number, *_FMT_RANGE["i"]))


def _set_saves(buf: bytearray, value: Any) -> None:
    """Otto tiri salvezza (int16)."""
    if not isinstance(value, Sequence) or isinstance(value, str) or len(value) != 8:
        raise PlayerValueError("savingThrows", "type", expected="list of 8")
    struct.pack_into("<8h", buf, _O_SAVES, *(_int("savingThrows", v, *_FMT_RANGE["h"]) for v in value))


def _set_skills(buf: bytearray, rows: Any) -> None:
    """Sostituisce le abilita' elencate: quelle gia' elencate e assenti dal nuovo elenco sono azzerate; le voci non elencate dal
    parser (`learned == 0 e flags == 0`, ma con `special`/`nummem`) restano com'erano."""
    if not isinstance(rows, Sequence) or isinstance(rows, str):
        raise PlayerValueError("skills", "type", expected="list")
    new: dict[int, bytes] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not set(row) <= {"index", "learned", "flags", "special", "nummem"} or "index" not in row:
            raise PlayerValueError("skills", "type", expected="rows with index")
        index = _int("skills.index", row["index"], 0, MAX_SKILLS - 1)
        if index in new:
            raise PlayerValueError("skills", "duplicate", index=index)
        new[index] = bytes(_int(f"skills.{k}", row.get(k, 0), 0, 255) for k in ("learned", "flags", "special", "nummem"))
    for n in range(MAX_SKILLS):
        at = _O_SKILLS + n * 4
        if n in new:
            buf[at : at + 4] = new[n]
        elif buf[at] or buf[at + 1]:
            buf[at : at + 4] = bytes(4)


def _set_affects(buf: bytearray, rows: Any) -> None:
    """Sostituisce l'elenco degli effetti (al massimo 40, compattati dall'inizio); se e' uguale all'attuale non tocca nulla."""
    if not isinstance(rows, Sequence) or isinstance(rows, str):
        raise PlayerValueError("affects", "type", expected="list")
    if len(rows) > MAX_AFFECT:
        raise PlayerValueError("affects", "too_many", max=MAX_AFFECT)
    keys = (("type", "h"), ("duration", "h"), ("modifier", "i"), ("location", "i"), ("bitvector", "i"))
    new = []
    for row in rows:
        if not isinstance(row, Mapping) or not set(row) <= {k for k, _ in keys}:
            raise PlayerValueError("affects", "type", expected="rows")
        new.append(tuple(_int(f"affects.{k}", row.get(k, 0), *_FMT_RANGE[f]) for k, f in keys))
    current = []
    for n in range(MAX_AFFECT):
        values = struct.unpack_from("<hhiii", buf, _O_AFFECTED + n * 20)
        if any(values):
            current.append(values)
    if new == current:
        return
    for n in range(MAX_AFFECT):
        at = _O_AFFECTED + n * 20
        buf[at : at + 20] = struct.pack("<hhiiii", *new[n], 0) if n < len(new) else bytes(20)


def apply_char_patch(data: bytes, details: Mapping[str, Any], lists: Mapping[str, Any] | None = None) -> bytes:
    """Il file giocatore `data` (3036 byte) con i campi `details` e le tabelle `lists` (`skills`, `affects`) modificati.

    Raises:
        PlayerFileError: `bad_size`.
        PlayerValueError: campo sconosciuto/di sola lettura o valore non valido (nulla e' stato scritto).
    """
    if len(data) != CHAR_FILE_SIZE:
        raise PlayerFileError("bad_size", f"il record deve essere di {CHAR_FILE_SIZE} byte, non {len(data)}")
    buf = bytearray(data)
    for name, value in details.items():
        if name in READ_ONLY_FIELDS:
            raise PlayerValueError(name, "read_only")
        if name not in WRITABLE_FIELDS:
            raise PlayerValueError(name, "unknown_field")
        _apply_field(buf, name, value)
    for name, rows in (lists or {}).items():
        if name == "skills":
            _set_skills(buf, rows)
        elif name == "affects":
            _set_affects(buf, rows)
        else:
            raise PlayerValueError(name, "unknown_field")
    if buf[_O_PWD : _O_PWD + _PWD_LEN] != data[_O_PWD : _O_PWD + _PWD_LEN]:  # difesa in profondita': non puo' succedere
        raise PlayerValueError("password", "read_only")
    return bytes(buf)


def _apply_field(buf: bytearray, name: str, value: Any) -> None:
    """Scrive un campo di `details` (gia' noto come scrivibile)."""
    if name in _SCALARS:
        fmt, offset, low, high = _SCALARS[name]
        lo, hi = _FMT_RANGE[fmt]
        if value == struct.unpack_from("<" + fmt, buf, offset)[0] and type(value) is int:
            return  # invariato: accettato anche se fuori dall'intervallo di gioco (un file reale puo' averlo)
        struct.pack_into("<" + fmt, buf, offset, _int(name, value, lo if low is None else low, hi if high is None else high))
    elif name in _STRINGS:
        offset, size = _STRINGS[name]
        value = "" if value is None else value  # null = vuoto (campi nullable)
        if value != _text(bytes(buf[offset : offset + size])):  # invariato: non si valida ne' si toccano i byte (esistono file con 80 byte pieni)
            buf[offset : offset + size] = _string(name, value, size)
    elif name in _DATES:
        struct.pack_into("<i", buf, _DATES[name], _timestamp(name, value))
    elif name == "affectedBy":
        mask = _flags(name, value, T.FLAG_TABLES["affect_flags"])
        known = 0
        for bit in T.FLAG_TABLES["affect_flags"].values():
            known |= bit
        (old,) = struct.unpack_from("<I", buf, _AFFECT_BY[1])
        struct.pack_into("<I", buf, _AFFECT_BY[1], (old & ~known & 0xFFFFFFFF) | mask)  # i bit senza nome restano
    elif name == "levels":
        _set_levels(buf, value)
    elif name == "conditions":
        _set_conditions(buf, value)
    else:
        _set_saves(buf, value)


def rent_with_gold(data: bytes, owner: str, gold: int) -> bytes | None:
    """Il rent con `gold_left` (offset 20) = `gold`, o `None` se non c'e' nulla da allineare (vuoto, header troncato o di un altro
    proprietario). Il gioco confronta `total_cost * giorni` con `gold_left` al boot (`update_obj_file`)."""
    if len(data) < RENT_HEADER_SIZE or _text(data[:20]).lower() != owner.lower():
        return None
    out = bytearray(data)
    struct.pack_into("<i", out, 20, gold)
    return bytes(out)


# ------------------------------------------------------------------ rent


def pack_item(
    vnum: int,
    *,
    values: Sequence[int],
    extra_flags: int,
    weight: int,
    name: str,
    short: str,
    description: str,
    affects: Sequence[tuple[int, int]],
) -> bytes:
    """Un `obj_file_elem` (592 byte) per un oggetto **nuovo** dal prototipo, come lo salverebbe il gioco subito dopo `read_object`:
    `timer` 0 e `bitvector` 0 (il prototipo non li ha), `wearpos`/`depth` 0 (li imposta `RentEditor.add`), effetti non usati a 0.
    Le stringhe lunghe sono troncate a `size - 1` (il gioco farebbe `strcpy` oltre il campo)."""
    if not 0 <= vnum <= MAX_ITEM_VNUM:
        raise PlayerValueError("vnum", "range", min=0, max=MAX_ITEM_VNUM)
    if len(values) != 4 or len(affects) > 5:
        raise PlayerValueError("item", "type", expected="4 values, up to 5 affects")
    buf = bytearray(RENT_ELEM_SIZE)
    try:
        struct.pack_into("<h", buf, 0, vnum)
        struct.pack_into("<4i", buf, 4, *values)
        struct.pack_into("<4i", buf, 20, extra_flags, weight, 0, 0)
        for offset, size, text in ((36, 128, name), (164, 128, short), (292, 256, description)):
            raw = text.encode("latin-1", "replace")[: size - 1]
            buf[offset : offset + len(raw)] = raw
        for n, (location, modifier) in enumerate(affects):
            struct.pack_into("<hxxi", buf, 552 + n * 8, location, modifier)
    except struct.error as error:
        raise PlayerValueError("item", "range") from error
    return bytes(buf)


def wearpos_of(record: bytes) -> int:
    """`wearpos` di un record (0 = non equipaggiato)."""
    return record[548]


def depth_of(record: bytes) -> int:
    """`depth` di un record."""
    return record[549]


class RentEditor:
    """Un file rent in memoria come testata + lista di record da 592 byte; modifica e riserializza (`to_bytes`).

    Un file vuoto (o `None`) e' un rent nuovo: `owner` del personaggio, `total_cost` 100 (il minimo di `recep_offer`),
    `last_update` adesso, `gold_left` = oro del personaggio. Un file esistente deve essere coerente (40 + n x 592 byte, n <= 200)
    e del proprietario giusto; la testata (`gold_left`, `last_update`, `minimum_stay`) resta com'e' salvo `total_cost`.
    """

    def __init__(self, data: bytes | None, owner: str, *, gold: int, now: int) -> None:
        """Raises: PlayerFileError con `truncated_header`, `too_many_items`, `truncated`, `trailing_data` o `owner_mismatch`."""
        if len(owner.encode("latin-1")) > 19 or not NAME_RE.fullmatch(owner.lower()):
            raise PlayerValueError("owner", "type", expected="player name")
        self.owner = owner.encode("latin-1")
        if not data:
            self.gold_left, self.total_cost, self.last_update, self.minimum_stay = gold, 100, now, 0
            self.records: list[bytes] = []
            self.created = True
            return
        parsed = parse_rent(data)
        if parsed.problem:
            raise PlayerFileError(parsed.problem)
        if parsed.owner.lower() != owner.lower():
            raise PlayerFileError("owner_mismatch")
        self.owner = data[:20]  # i 20 byte originali (maiuscole diverse dal nome e residui dopo il NUL compresi)
        self.gold_left, self.total_cost, self.last_update, self.minimum_stay = (
            parsed.gold_left, parsed.total_cost, parsed.last_update, parsed.minimum_stay,
        )  # fmt: skip
        self.records = [data[RENT_HEADER_SIZE + k * RENT_ELEM_SIZE : RENT_HEADER_SIZE + (k + 1) * RENT_ELEM_SIZE] for k in range(parsed.number)]
        self.created = False

    def _subtree_end(self, index: int) -> int:
        """Posizione dopo l'ultimo discendente di `index` (record contigui con `depth` maggiore)."""
        depth = depth_of(self.records[index])
        end = index + 1
        while end < len(self.records) and depth_of(self.records[end]) > depth:
            end += 1
        return end

    def _check_index(self, index: int) -> None:
        """`PlayerValueError('item', 'not_found')` se la posizione non esiste."""
        if not 0 <= index < len(self.records):
            raise PlayerValueError("item", "not_found")

    def _check_slot(self, wearpos: int, *, ignore: int | None = None) -> None:
        """`wearpos` 0..`MAX_WEAR` e slot libero (un solo oggetto per slot: `equip_char` lo richiede)."""
        _int("wearSlot", wearpos, 0, MAX_WEAR)
        if wearpos and any(wearpos_of(r) == wearpos for k, r in enumerate(self.records) if k != ignore):
            raise PlayerValueError("wearSlot", "slot_taken")

    def add(self, element: bytes, wearpos: int = 0, container: int | None = None) -> int:
        """Aggiunge `element` (da `pack_item`) e ne restituisce la posizione. Con `container` (posizione di un oggetto) l'oggetto va
        subito dopo il suo ultimo contenuto con `depth` + 1 e senza slot; altrimenti in fondo con `depth` 0 e lo slot dato."""
        if len(self.records) >= MAX_OBJ_SAVE:
            raise PlayerValueError("item", "inventory_full", max=MAX_OBJ_SAVE)
        self._check_slot(wearpos)
        buf = bytearray(element)
        if container is None:
            buf[548], buf[549] = wearpos, 0
            self.records.append(bytes(buf))
            return len(self.records) - 1
        self._check_index(container)
        if wearpos:
            raise PlayerValueError("wearSlot", "slot_in_container")
        depth = depth_of(self.records[container]) + 1
        if depth > MAX_DEPTH:
            raise PlayerValueError("item", "too_deep", max=MAX_DEPTH)
        buf[548], buf[549] = 0, depth
        at = self._subtree_end(container)
        self.records.insert(at, bytes(buf))
        return at

    def delete(self, index: int) -> list[bytes]:
        """Toglie l'oggetto e tutto il suo contenuto (un contenuto senza contenitore sarebbe un record «weird» per il gioco);
        restituisce i record tolti."""
        self._check_index(index)
        end = self._subtree_end(index)
        removed = self.records[index:end]
        del self.records[index:end]
        return removed

    def set_wearpos(self, index: int, wearpos: int) -> None:
        """Cambia lo slot di un oggetto di primo livello (0 = portato). Un oggetto dentro un contenitore non si equipaggia."""
        self._check_index(index)
        record = self.records[index]
        if depth_of(record) and wearpos:
            raise PlayerValueError("wearSlot", "slot_in_container")
        self._check_slot(wearpos, ignore=index)
        buf = bytearray(record)
        buf[548] = wearpos
        self.records[index] = bytes(buf)

    def to_bytes(self) -> bytes:
        """Testata (40 byte, `number` = oggetti) + record."""
        head = struct.pack("<20siiiii", self.owner, self.gold_left, self.total_cost, self.last_update, self.minimum_stay, len(self.records))
        return head + b"".join(self.records)


__all__ = [
    "READ_ONLY_FIELDS",
    "WRITABLE_FIELDS",
    "PlayerValueError",
    "RentEditor",
    "apply_char_patch",
    "char_revision",
    "pack_item",
    "rent_revision",
    "rent_with_gold",
]
