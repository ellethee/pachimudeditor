"""Parser dei file `.are`: `parse_area(text) -> Area`, fedele ai loader di `db.c` (basedmud)."""

from __future__ import annotations

import re
from collections.abc import Callable

from .errors import RomParseError
from .model import (
    Area,
    AreaHeader,
    CommentLine,
    Dice,
    Exit,
    ExtraDescription,
    FlagRemoval,
    Help,
    MobProg,
    MobProgTrigger,
    Mobile,
    Object,
    ObjectAffect,
    Reset,
    Room,
    Section,
    Shop,
    Social,
    Special,
)
from .reader import Reader

_SECTION_LINE = re.compile(r"^#[A-Za-z$]", re.MULTILINE)

#: Numero di argomenti numerici letti dal loader per ogni comando di reset.
RESET_ARG_COUNT = {"M": 5, "O": 4, "P": 5, "G": 3, "E": 4, "D": 4, "R": 3}

SectionParser = Callable[[Reader], tuple[list, str | None]]


def _seal(item, src: str):
    """Associa all'elemento il sorgente originale e l'impronta dei campi (per la scrittura fedele)."""
    item._src = src
    item._fp = repr(item)
    return item


def _list_section(r: Reader, parse_one: Callable[[Reader, int], object], what: str) -> tuple[list, str]:
    """Legge una sezione di elementi `#vnum ...` terminata da `#0`; restituisce (elementi, coda grezza)."""
    items: list = []
    while True:
        start = r.i
        r.context = what
        if r.peek_letter() != "#":
            raise r.error(f"'#' atteso in {what}, trovato {r.peek_letter()!r}" if r.peek_letter() else f"fine file in {what}: manca '#0'")
        r.letter()
        vnum = r.number()
        if vnum == 0:
            r.end_item()
            return items, r.text[start:r.i]
        r.context = f"{what} vnum {vnum}"
        item = parse_one(r, vnum)
        r.end_item()
        items.append(_seal(item, r.text[start:r.i]))


# -- AREA -------------------------------------------------------------------------------------
def _parse_area_old(r: Reader) -> tuple[list, None]:
    start = r.i
    h = AreaHeader(style="AREA")
    h.filename = r.string()
    h.name = r.string()
    h.credits = r.string()
    c = r.peek_letter()
    if c and (c.isdigit() or c in "+-"):
        h.min_vnum = r.number()
        h.max_vnum = r.number()
    else:
        a, b = r.word(), r.word()
        h.vnum_raw = f"{a} {b}"
    r.end_item()
    return [_seal(h, r.text[start:r.i])], None


def _parse_areadata(r: Reader) -> tuple[list, None]:
    start = r.i
    h = AreaHeader(style="AREADATA")
    while True:
        if r.eof():
            raise r.error("fine file in #AREADATA: manca 'End'")
        pos = r.i
        key = r.word()
        low = key.lower()
        if low == "end":
            break
        if low == "name":
            h.name = r.string()
        elif low == "builders":
            h.builders = r.string()
        elif low == "credits":
            h.credits = r.string()
        elif low == "security":
            h.security = r.number()
        elif low == "vnums":
            h.min_vnum = r.number()
            h.max_vnum = r.number()
        else:
            r.i = pos
            r.skip_ws()
            h.extra.append((key, r.rest_of_line().strip()[len(key):].strip()))
    r.end_item()
    return [_seal(h, r.text[start:r.i])], None


# -- MOBILES ----------------------------------------------------------------------------------
def _parse_dice(r: Reader) -> Dice:
    n, t, b = r.dice()
    return Dice(n, t, b)


def _parse_mobile(r: Reader, vnum: int) -> Mobile:
    m = Mobile(vnum=vnum)
    m.name = r.string()
    m.short_descr = r.string()
    m.long_descr = r.string()
    m.description = r.string()
    m.race = r.string()
    m.act = r.flag()
    m.affected_by = r.flag()
    m.alignment = r.number()
    m.group = r.number()
    m.level = r.number()
    m.hitroll = r.number()
    m.hit = _parse_dice(r)
    m.mana = _parse_dice(r)
    m.damage = _parse_dice(r)
    m.dam_type = r.word()
    m.ac = [r.number() for _ in range(4)]
    m.off_flags = r.flag()
    m.imm_flags = r.flag()
    m.res_flags = r.flag()
    m.vuln_flags = r.flag()
    m.start_pos = r.word()
    m.default_pos = r.word()
    m.sex = r.word()
    m.wealth = r.number()
    m.form = r.flag()
    m.parts = r.flag()
    m.size = r.word()
    m.material = r.word()
    r.end_item()
    while True:
        c = r.peek_letter()
        if c == "F":
            r.letter()
            word = r.word()
            m.flag_removals.append(FlagRemoval(word, r.flag()))
        elif c == "M":
            r.letter()
            trig = r.word()
            vn = r.number()
            m.mprogs.append(MobProgTrigger(trig, vn, r.string()))
        else:
            break
        r.end_item()
    return m


# -- OBJECTS ----------------------------------------------------------------------------------
def _parse_object(r: Reader, vnum: int) -> Object:
    o = Object(vnum=vnum)
    o.name = r.string()
    o.short_descr = r.string()
    o.description = r.string()
    o.material = r.string()
    o.item_type = r.word()
    o.extra_flags = r.flag()
    o.wear_flags = r.flag()
    o.values = [r.word() for _ in range(5)]
    o.level = r.number()
    o.weight = r.number()
    o.cost = r.number()
    o.condition = r.letter()
    r.end_item()
    while True:
        c = r.peek_letter()
        if c == "A":
            r.letter()
            loc = r.number()
            o.affects.append(ObjectAffect(loc, r.number()))
        elif c == "F":
            r.letter()
            where = r.letter()
            if where not in "AIRV":
                raise r.error(f"bit_type di affect non valido: {where!r} (atteso A/I/R/V)")
            loc = r.number()
            mod = r.number()
            o.affects.append(ObjectAffect(loc, mod, where, r.flag()))
        elif c == "E":
            r.letter()
            kw = r.string()
            o.extra_descs.append(ExtraDescription(kw, r.string()))
        else:
            break
        r.end_item()
    return o


# -- ROOMS ------------------------------------------------------------------------------------
def _parse_room(r: Reader, vnum: int) -> Room:
    room = Room(vnum=vnum)
    room.name = r.string()
    room.description = r.string()
    room.area_number = r.number()
    room.room_flags = r.flag()
    room.sector = r.number()
    r.end_item()
    while True:
        c = r.letter()
        if c == "S":
            break
        if c == "H":
            room.heal_rate = r.number()
        elif c == "M":
            room.mana_rate = r.number()
        elif c == "C":
            room.clan = r.string()
        elif c == "O":
            room.owner = r.string()
        elif c == "D":
            door = r.number()
            if not 0 <= door <= 5:
                raise r.error(f"numero di uscita non valido: {door} (atteso 0-5)")
            desc = r.string()
            kw = r.string()
            locks = r.number()
            if not 0 <= locks <= 4:
                raise r.error(f"codice porta (locks) non valido: {locks} (atteso 0-4)")
            key = r.number()
            to = r.number()
            room.exits.append(Exit(door, desc, kw, locks, key, to))
        elif c == "E":
            kw = r.string()
            room.extra_descs.append(ExtraDescription(kw, r.string()))
        else:
            raise r.error(f"lettera {c!r} non valida in una stanza (attese D/E/H/M/C/O/S)", r.i - 1)
        r.end_item()
    return room


# -- RESETS / SHOPS / SPECIALS / MOBPROGS -----------------------------------------------------
def _parse_resets(r: Reader) -> tuple[list, str]:
    items: list = []
    r.context = "RESETS"
    while True:
        start = r.i
        if r.eof():
            raise r.error("fine file in #RESETS: manca 'S'")
        c = r.letter()
        if c == "S":
            r.end_item()
            return items, r.text[start:r.i]
        if c == "*":
            text = "*" + r.rest_of_line()
            items.append(_seal(CommentLine(text.rstrip()), r.text[start:r.i]))
            continue
        if c not in RESET_ARG_COUNT:
            raise r.error(f"comando di reset {c!r} sconosciuto (attesi M O P G E D R S)", r.i - 1)
        args = [r.number() for _ in range(RESET_ARG_COUNT[c])]
        comment = r.rest_of_line().strip()
        items.append(_seal(Reset(c, args, comment), r.text[start:r.i]))


def _parse_shops(r: Reader) -> tuple[list, str]:
    items: list = []
    r.context = "SHOPS"
    while True:
        start = r.i
        keeper = r.number()
        if keeper == 0:
            r.end_item()
            return items, r.text[start:r.i]
        r.context = f"SHOPS keeper {keeper}"
        buy = [r.number() for _ in range(5)]
        pb, ps, oh, ch = r.number(), r.number(), r.number(), r.number()
        comment = r.rest_of_line().strip()
        items.append(_seal(Shop(keeper, buy, pb, ps, oh, ch, comment), r.text[start:r.i]))


def _parse_specials(r: Reader) -> tuple[list, str]:
    items: list = []
    r.context = "SPECIALS"
    while True:
        start = r.i
        if r.eof():
            raise r.error("fine file in #SPECIALS: manca 'S'")
        c = r.letter()
        if c == "S":
            r.end_item()
            return items, r.text[start:r.i]
        if c == "*":
            text = "*" + r.rest_of_line()
            items.append(_seal(CommentLine(text.rstrip()), r.text[start:r.i]))
        elif c == "M":
            vnum = r.number()
            func = r.word()
            items.append(_seal(Special(vnum, func, r.rest_of_line().strip()), r.text[start:r.i]))
        else:
            raise r.error(f"lettera {c!r} non valida in #SPECIALS (attese M, * o S)", r.i - 1)


def _parse_mobprog(r: Reader, vnum: int) -> MobProg:
    return MobProg(vnum, r.string())


# -- HELPS / SOCIALS --------------------------------------------------------------------------
def _parse_helps(r: Reader) -> tuple[list, str]:
    items: list = []
    r.context = "HELPS"
    while True:
        start = r.i
        level = r.number()
        keyword = r.string()
        if keyword.startswith("$"):
            r.end_item()
            return items, r.text[start:r.i]
        r.context = f"HELPS {keyword!r}"
        text = r.string()
        r.end_item()
        items.append(_seal(Help(level, keyword, text), r.text[start:r.i]))


def _parse_socials(r: Reader) -> tuple[list, str]:
    items: list = []
    r.context = "SOCIALS"
    while True:
        start = r.i
        if r.eof():
            raise r.error("fine file in #SOCIALS: manca '#0'")
        w = r.word()
        if w == "#0":
            r.end_item()
            return items, r.text[start:r.i]
        r.context = f"SOCIALS {w!r}"
        soc = Social(name=w, params=r.rest_of_line().strip())
        for _ in range(8):
            if r.eof():
                raise r.error("fine file dentro un social")
            line = r.string_eol()
            if line == "$":
                soc.lines.append(None)
            elif line == "#":
                soc.truncated = True
                break
            else:
                soc.lines.append(line)
        r.end_item()
        items.append(_seal(soc, r.text[start:r.i]))


def _raw_section(r: Reader, name: str) -> str:
    """Corpo di una sezione sconosciuta: fino alla prossima riga `#NOME` (o fine file)."""
    m = _SECTION_LINE.search(r.text, r.i)
    end = m.start() if m else r.n
    body = r.text[r.i:end]
    r.i = end
    return body


_PARSERS: dict[str, SectionParser] = {
    "AREA": _parse_area_old,
    "AREADATA": _parse_areadata,
    "MOBILES": lambda r: _list_section(r, _parse_mobile, "MOBILES"),
    "OBJECTS": lambda r: _list_section(r, _parse_object, "OBJECTS"),
    "ROOMS": lambda r: _list_section(r, _parse_room, "ROOMS"),
    "MOBPROGS": lambda r: _list_section(r, _parse_mobprog, "MOBPROGS"),
    "RESETS": _parse_resets,
    "SHOPS": _parse_shops,
    "SPECIALS": _parse_specials,
    "HELPS": _parse_helps,
    "SOCIALS": _parse_socials,
}


def parse_area(text: str, *, filename: str | None = None) -> Area:
    """Interpreta il testo di un file `.are` e restituisce l'`Area`.

    Sezioni supportate: #AREA, #AREADATA, #MOBILES, #OBJECTS, #ROOMS, #RESETS, #SHOPS,
    #SPECIALS, #MOBPROGS, #HELPS, #SOCIALS; le altre (es. #MOBOLD, #OBJOLD) sono conservate come
    testo grezzo. Ogni elemento ricorda il proprio sorgente, cosi' che `write_area` riproduca
    byte per byte quanto non e' stato modificato.

    Args:
        text: contenuto del file (gia' decodificato, newline originali conservati).
        filename: nome del file, usato solo nei messaggi d'errore.

    Raises:
        RomParseError: sintassi non valida (con numero di riga/colonna e contesto).
    """
    r = Reader(text, filename)
    area = Area(newline="\r\n" if "\r\n" in text else "\n", filename=filename)
    while True:
        head_start = r.i
        r.context = ""
        if r.eof():
            area.has_terminator = False
            area.trailer = text[head_start:]
            break
        if r.letter() != "#":
            raise r.error("'#' atteso all'inizio di una sezione", r.i - 1)
        pos_name = r.i
        name = r.word()
        if not name:
            raise r.error("nome sezione mancante dopo '#'", pos_name)
        if name.startswith("$"):
            r.end_item()
            area.end_head = text[head_start:r.i]
            area.trailer = text[r.i:]
            break
        r.end_item()
        head = text[head_start:r.i]
        kind = name.upper()
        parser = _PARSERS.get(kind)
        if parser is None:
            body = _raw_section(r, name)
            area.sections.append(Section("RAW", head=head, name=name, text=body))
            continue
        r.context = kind
        items, tail = parser(r)
        area.sections.append(Section(kind, items, head, tail))
    return area


__all__ = ["RESET_ARG_COUNT", "RomParseError", "parse_area"]
