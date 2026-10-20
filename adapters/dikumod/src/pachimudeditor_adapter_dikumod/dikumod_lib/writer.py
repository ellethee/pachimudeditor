"""Scrittura dei file Diku Modificato.

- elementi **invariati** (stessa impronta) e record `Raw`: testo originale, byte per byte;
- elementi **nuovi o modificati**: forma canonica, quella che `db.c` rilegge senza ambiguita'
  (stringhe `testo~` + un carattere scartato, numeri semplici senza `|`, sempre 5 numeri per i comandi `O`);
- `canonical=True` riscrive tutto in forma canonica (idempotente).

Vincoli del gioco applicati in scrittura:

- `.mob`/`.obj`: nessuna riga (spezzata a 81 caratteri come `fgets(buf, 82)`) puo' iniziare per `#` o `%%`, altrimenti
  `generate_indices` vedrebbe un record fantasma o la fine del file (`DikumodWriteError`);
- niente `~` dentro le stringhe (non esiste escape);
- i record dei file indicizzati devono restare in ordine di vnum (`real_mobile`/`real_object` usano la ricerca
  binaria): `insert_sorted` lo garantisce;
- il file mob/obj deve finire con `%%` (senza, `generate_indices` va in `assert`); `ensure_terminator` lo aggiunge.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pachimudeditor.sdk import atomic_write_bytes

from .errors import DikumodUnencodableError, DikumodWriteError
from .model import (
    Dice,
    Mob,
    Obj,
    Raw,
    RecordFile,
    Room,
    ScriptEntry,
    Shop,
    Zone,
    ZoneCmd,
    ZoneOverride,
    ZoneText,
)
from .tables import ZONE_ARG_COUNT

Dice0 = Dice(1, 1, 0)
"""Dado di ripiego per un mob `S` privo di `hp_dice`."""
MOB_OBJ_TERMINATOR = "%%~\n"
ZONE_TERMINATOR = "#9999999\n$~\n"
SHOP_TERMINATOR = "$~\n"
COMMENT_LIMIT = 78
"""Resto di una riga di comando (dopo l'ultimo argomento) al massimo 78 caratteri: `fgets(buf, 80)` ne legge 79."""


def _s(value: str) -> str:
    """Stringa `fread_string`: `~` vietata (non c'e' escape); restituisce `testo~\\n`."""
    if "~" in value:
        raise DikumodWriteError("il carattere ~ non puo' comparire in un testo (non esiste escape)")
    return f"{value}~\n"


def index_hazard(text: str) -> str | None:
    """Motivo per cui `text` confonderebbe `generate_indices` (righe spezzate a 81 caratteri come `fgets(82)`), o None."""
    for n, raw in enumerate(text.split("\n")):
        piece_starts = range(0, max(len(raw), 1), 81)
        for j, p in enumerate(piece_starts):
            if n == 0 and j == 0:
                continue  # la riga `#vnum` di apertura
            head = raw[p : p + 2]
            if head[:1] == "#" or head == "%%":
                return f"una riga (o un suo frammento da 81 caratteri) inizia con {head[:2]!r}: {raw[p:p+30]!r}"
    return None


# --------------------------------------------------------------------------- formati canonici


def format_room(r: Room) -> str:
    """Stanza canonica (`load_one_room`): nome, descrizione, `zona flags settore`, blocchi opzionali, D/E/L, `S`."""
    out = [f"#{r.vnum}\n", _s(r.name), _s(r.description)]
    if r.tele is not None:
        t = r.tele
        count = f" {t.count or 0}" if t.mask & 2 else ""
        out.append(f"{r.zone_ignored} {r.flags} -1 {t.time} {t.target} {t.mask}{count} {r.sector}\n")
    else:
        out.append(f"{r.zone_ignored} {r.flags} {r.sector}\n")
    if r.sector in (7, 9):
        speed, direction = r.river or (0, 0)
        out.append(f"{speed} {direction}\n")
    if r.flags & 256:
        out.append(f"{r.moblim or 0}\n")
    for x in r.exits:
        if not 0 <= x.door <= 5:
            raise DikumodWriteError(f"direzione {x.door} non valida")
        cmd = f" {x.open_cmd}" if x.open_cmd is not None else ""
        out.append(f"D{x.door}\n{_s(x.description.lstrip())}{_s(x.keyword)}{x.info} {x.key} {x.to_room}{cmd}\n")
    for e in r.extra_descs:
        out.append(f"E\n{_s(e.keyword)}{_s(e.description)}")
    if r.light is not None:
        out.append(f"L\n{_s(r.light[0])}{_s(r.light[1])}")
    out.append("S\n")
    return "".join(out)


def format_mob(m: Mob) -> str:
    """Mob canonico `S/A/N/B/L` (vedi `read_mobile`)."""
    if m.kind not in ("S", "A", "N", "B", "L"):
        raise DikumodWriteError(f"tipo di mob {m.kind!r} non supportato")
    head = f"{m.act} {m.affected} {m.alignment} {m.kind}" + (f" {1 if m.multi is None else m.multi}" if m.kind in "ABL" else "")
    hp = str(m.hp_dice or Dice0) if m.kind == "S" else str(m.hp_bonus)
    money = f"-1 {m.gold} {m.exp} {m.race}" if m.race is not None else f"{m.gold} {m.exp}"
    code = m.sex_code
    masks = ""
    if m.immune or m.m_immune or m.susc:
        code = code + 3 if code < 3 else code
    if 3 <= code < 6:
        masks = f" {m.immune} {m.m_immune} {m.susc}"
    out = [
        f"#{m.vnum}\n", _s(m.name), _s(m.short), _s(m.long), _s(m.description), head, "\n",
        f"{m.level} {m.thac0} {m.ac} {hp} {m.damage}\n", money, "\n",
        f"{m.position} {m.default_pos} {code}{masks}",
    ]  # fmt: skip
    if m.kind == "L":
        # il gioco legge il suono subito dopo l'ultimo numero: il "\n" di fine riga fa parte del testo (vedi README)
        sound = m.sound or ""
        out += [_s(sound if sound.startswith("\n") else "\n" + sound), _s(m.distant_sound or "")]
    else:
        out.append("\n")
    if m.trailing:
        out.append(m.trailing + "\n")
    text = "".join(out)
    _guard(text, m.vnum)
    return text


def format_obj(o: Obj) -> str:
    """Oggetto canonico (`write_obj_to_file`): E prima di A, al massimo 5 A, P in fondo."""
    if len(o.affects) > 5:
        raise DikumodWriteError("un oggetto puo' avere al massimo 5 affect")
    v = (list(o.values) + [0, 0, 0, 0])[:4]
    out = [
        f"#{o.vnum}\n", _s(o.name), _s(o.short), _s(o.description), _s(o.action),
        f"{o.type} {o.extra_flags} {o.wear_flags}\n", f"{v[0]} {v[1]} {v[2]} {v[3]}\n",
        f"{o.weight} {o.cost} {o.rent}\n",
    ]  # fmt: skip
    for e in o.extra_descs:
        out.append(f"E\n{_s(e.keyword)}{_s(e.description)}")
    for a in o.affects:
        out.append(f"A\n{a.location} {a.modifier}\n")
    if o.forbidden is not None:
        out.append(f"P\n{_s(o.forbidden[0])}{_s(o.forbidden[1])}")
    text = "".join(out)
    _guard(text, o.vnum)
    return text


def _guard(text: str, vnum: int) -> None:
    """`DikumodWriteError` se il testo confonderebbe l'indicizzazione per righe."""
    hazard = index_hazard(text)
    if hazard:
        raise DikumodWriteError(f"record {vnum}: {hazard}")


def format_cmd(c: ZoneCmd) -> str:
    """Riga di comando canonica (`Zwrite`): `lettera if arg...` (`O` sempre con 5 numeri) + commento grezzo."""
    if c.letter not in ZONE_ARG_COUNT:
        raise DikumodWriteError(f"comando di reset {c.letter!r} sconosciuto")
    want = ZONE_ARG_COUNT[c.letter]
    args = (list(c.args) + [0] * want)[:want]
    comment = c.comment
    if len(comment) > COMMENT_LIMIT:
        comment = comment[:COMMENT_LIMIT]
    return f"{c.letter} {c.if_flag} {' '.join(str(a) for a in args)}{comment}\n"


def needs_fix(c: ZoneCmd) -> bool:
    """`O` con 3 argomenti: va riscritta con 5 numeri o il loader C salta la riga seguente."""
    return c.letter == "O" and len(c.args) < ZONE_ARG_COUNT["O"]


def _item_text(item: ZoneCmd | ZoneText, canonical: bool) -> str:
    """Testo di una riga di zona: originale se invariata (e non da correggere), altrimenti canonico."""
    if isinstance(item, ZoneText):
        if item._src is not None and not canonical:
            return item._src
        return item.text if item.text.endswith("\n") else item.text + "\n"
    if item._src is not None and item._fp == repr(item) and not canonical and not needs_fix(item):
        return item._src
    return format_cmd(item)


def format_zone(z: Zone, *, canonical: bool = False) -> str:
    """Zona canonica: intestazione, righe (comandi invariati con i loro byte), `S`."""
    body = "".join(_item_text(i, canonical) for i in z.items)
    return f"#{z.num}\n{_s(z.name)}{z.top} {z.lifespan} {z.reset_mode}\n{body}S\n"


def format_zone_override(z: ZoneOverride, *, canonical: bool = False) -> str:
    """`zones/<n>.zon` canonico: solo comandi e `S` (le `O` con 5 numeri: il quinto e' letto come commento)."""
    return "".join(_item_text(i, canonical) for i in z.items) + "S\n"


def format_shop(s: Shop) -> str:
    """Negozio canonico (`boot_the_shops`): un valore per riga."""
    out = [_s(s.tag if s.tag.startswith("#") else f"#{s.tag}")]
    out += [f"{v}\n" for v in s.producing[:5]]
    out += [f"{s.profit_buy}\n", f"{s.profit_sell}\n"]
    out += [f"{v}\n" for v in s.types[:5]]
    out += [_s(m) for m in s.messages[:7]]
    out += [f"{v}\n" for v in (s.temper1, s.temper2, s.keeper, s.with_who, s.room, s.open1, s.close1, s.open2, s.close2)]
    return "".join(out)


def format_script_entry(e: ScriptEntry) -> str:
    """Riga `Nome vnum` di `scripts.dat`."""
    return f"{e.name} {e.vnum}\n"


_FORMATTERS = {Room: format_room, Mob: format_mob, Obj: format_obj, Shop: format_shop, ScriptEntry: format_script_entry}


def is_unchanged(item: object) -> bool:
    """True se l'elemento ha ancora l'impronta del parsing (riemissione byte-esatta)."""
    src = getattr(item, "_src", None)
    return src is not None and getattr(item, "_fp", None) == repr(item)


def item_text(item: object, *, canonical: bool = False) -> str:
    """Testo di un elemento: sorgente se `Raw`/invariato, altrimenti forma canonica."""
    if isinstance(item, Raw):
        return item.src
    if not canonical and is_unchanged(item):
        return item._src  # type: ignore[attr-defined]
    if isinstance(item, Zone):
        return format_zone(item, canonical=canonical)
    return _FORMATTERS[type(item)](item)  # type: ignore[index]


# --------------------------------------------------------------------------- file


def insert_sorted(rf: RecordFile, item: object) -> None:
    """Inserisce `item` dopo l'ultimo elemento con vnum <= al suo (i file indicizzati devono restare ordinati)."""
    vnum = item.vnum  # type: ignore[attr-defined]
    at = 0
    for i, it in enumerate(rf.items):
        v = getattr(it, "vnum", None)
        if v is not None and v <= vnum:
            at = i + 1
    rf.items.insert(at, item)


def is_sorted(rf: RecordFile) -> bool:
    """True se i vnum del file sono in ordine non decrescente (requisito della ricerca binaria del gioco)."""
    vnums = [v for v in (getattr(i, "vnum", None) for i in rf.items) if v is not None]
    return all(a <= b for a, b in zip(vnums, vnums[1:]))


def write_text(rf: RecordFile, *, canonical: bool = False, ensure_terminator: bool = True) -> str:
    """Il testo del file. Con `ensure_terminator` aggiunge `%%~`/`$~`/zona `$~` se il file ne e' privo."""
    parts: list[str] = [rf.head]
    for item in rf.items:
        text = item_text(item, canonical=canonical)
        if parts and parts[-1] and not parts[-1].endswith("\n") and text and not isinstance(item, Raw):
            parts.append("\n")
        parts.append(text)
    tail = rf.tail
    if ensure_terminator:
        tail = _with_terminator(rf.kind, tail)
    if tail and parts[-1] and not parts[-1].endswith("\n"):
        parts.append("\n")
    parts.append(tail)
    return "".join(parts)


def _with_terminator(kind: str, tail: str) -> str:
    """`tail` con il terminatore del tipo di file se manca."""
    import re

    if kind in ("mob", "obj") and not re.search(r"(?m)^%%", tail):
        return tail + MOB_OBJ_TERMINATOR
    if kind == "zon" and not re.search(r"(?m)^\$~", tail):
        return tail + ZONE_TERMINATOR
    if kind == "shp" and not re.search(r"(?m)^\$", tail):
        return tail + SHOP_TERMINATOR
    return tail


def encode_latin1(text: str) -> bytes:
    """Codifica in `latin-1`; `DikumodUnencodableError` (non `UnicodeEncodeError`) se c'e' un carattere non rappresentabile."""
    try:
        return text.encode("latin-1")
    except UnicodeEncodeError as error:
        raise DikumodUnencodableError(f"carattere {text[error.start]!r} non rappresentabile in latin-1") from error


def write_file(path: str | os.PathLike[str], rf: RecordFile, *, canonical: bool = False, ensure_terminator: bool = True) -> None:
    """Scrive il file in modo atomico (temporaneo nella stessa cartella + `os.replace`), in `latin-1`."""
    atomic_write_bytes(path, encode_latin1(write_text(rf, canonical=canonical, ensure_terminator=ensure_terminator)))
