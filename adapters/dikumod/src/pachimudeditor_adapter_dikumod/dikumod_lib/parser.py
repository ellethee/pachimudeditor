"""Parser tollerante dei file Diku Modificato.

Ogni record e' letto con le stesse primitive del gioco (`cscan.CScan`) ma **isolato**: un record corrotto diventa un
`Raw` (testo originale + motivo + riga) e il parsing riprende dal record successivo, senza perdere dati.

Confini dei record, come li vede il gioco:

- `.mob`/`.obj`: una riga che inizia con `#` apre un record (indicizzazione per righe di `generate_indices`); `%%` a
  inizio riga chiude il file;
- `.wld`: guidato dai token (`load_one_room`), il record finisce alla `S`;
- `.zon`: parser **per righe** (il loader C ha la trappola dell'argomento 4 di `O`, vedi README);
- `.shp`: guidato dai token (`boot_the_shops`), termina con `$~`.
"""

from __future__ import annotations

import re

from .cscan import CScan
from .errors import Diagnostic
from .model import (
    MAX_OBJ_AFFECT,
    Dice,
    Exit,
    ExtraDesc,
    Mob,
    Obj,
    ObjAffect,
    Raw,
    RecordFile,
    Room,
    ScriptEntry,
    Shop,
    Tele,
    Zone,
    ZoneCmd,
    ZoneOverride,
    ZoneText,
)
from .tables import ZONE_ARG_COUNT, ZONE_COMMANDS

_HASH_LINE = re.compile(r"(?m)^#")
_HASH_VNUM = re.compile(r"(?m)^#\s*\d")
_TERMINATOR = re.compile(r"(?m)^%%")


class _Bad(Exception):
    """Record non interpretabile (messaggio per `Raw.error`)."""


def _stamp(item: object, src: str) -> None:
    """Memorizza sorgente e impronta (la `repr` esclude questi campi)."""
    item._src = src  # type: ignore[attr-defined]
    item._fp = repr(item)  # type: ignore[attr-defined]


def _check(sc: CScan, what: str) -> None:
    """Alza `_Bad` se il C avrebbe segnalato un errore di lettura."""
    if sc.errors:
        raise _Bad(f"{what}: {sc.errors[0]}")


def _atoi(text: str) -> int:
    """`atoi`: prefisso numerico (0 se assente)."""
    m = re.match(r"\s*[+-]?\d+", text)
    return int(m.group()) if m else 0


# --------------------------------------------------------------------------- stanze


def _load_room(sc: CScan, vnum: int) -> Room:
    """Emula `load_one_room`; `_Bad` alla prima anomalia (token ignoto, dato mancante, EOF)."""
    sc.errors.clear()
    room = Room(vnum=vnum)
    room.name = sc.fread_string()
    room.description = sc.fread_string()
    _check(sc, "stringhe")
    zone = sc.scan_int()
    if zone is None:
        raise _Bad("numero di zona mancante")
    room.zone_ignored = zone
    room.flags = sc.fread_number()
    sector = sc.fread_number()
    if sector == -1:
        tele = Tele(time=sc.fread_number(), target=sc.fread_number(), mask=sc.fread_number())
        if tele.mask & 2:
            tele.count = sc.fread_number()
        room.tele = tele
        sector = sc.fread_number()
    room.sector = sector
    if sector in (7, 9):
        room.river = (sc.fread_number(), sc.fread_number())
    if room.flags & 256:
        room.moblim = sc.fread_number()
    _check(sc, "campi numerici")
    while True:
        tok = sc.scan_word()
        if tok is None:
            raise _Bad("EOF prima della S finale")
        c = tok[0]
        if c == "D":
            door = _atoi(tok[1:])
            if not 0 <= door <= 5:
                raise _Bad(f"direzione {door} non valida")
            ex = Exit(door=door)
            ex.description = sc.fread_string()
            ex.keyword = sc.fread_string()
            ex.info = sc.fread_number()
            ex.key = sc.fread_number()
            ex.to_room = sc.fread_number()
            ex.open_cmd = sc.scan_int()
            sc.skip_ws()
            _check(sc, f"uscita D{door}")
            room.exits.append(ex)
        elif c == "E":
            kw, desc = sc.fread_string(), sc.fread_string()
            _check(sc, "extra description")
            room.extra_descs.append(ExtraDesc(kw, desc))
        elif c == "L":
            night, day = sc.fread_string(), sc.fread_string()
            _check(sc, "blocco L")
            room.light = (night, day)
        elif c == "S":
            return room
        else:
            raise _Bad(f"codice ausiliario sconosciuto {tok!r}")


def parse_wld(text: str, filename: str = "", *, force_vnum: int | None = None) -> RecordFile:
    """Legge `dikumoddata.wld` o un file `rooms/<vnum>` (con `force_vnum` l'intestazione `#N` e' ignorata e facoltativa)."""
    rf = RecordFile("wld")
    sc = CScan(text)
    first = True
    while True:
        mark = sc.pos
        sc.skip_ws()
        if sc.pos >= len(text) or text[sc.pos] != "#":
            if force_vnum is not None and first and sc.pos < len(text):
                header_vnum = force_vnum  # file per-vnum senza intestazione
                start = sc.pos
            else:
                rf.tail = text[mark:]
                rf.mark_clean()
                return rf
        else:
            start = sc.pos
            sc.pos += 1
            header_vnum = sc.scan_int()
            if header_vnum is None:
                rf.tail = text[mark:]
                rf.mark_clean()
                return rf
            sc.skip_ws()
        if first:
            rf.head, first = text[:start], False
        vnum = force_vnum if force_vnum is not None else header_vnum
        line = sc.line_of(start)
        try:
            room = _load_room(sc, vnum)
        except _Bad as bad:
            nxt = _HASH_VNUM.search(text, start + 1)
            end = nxt.start() if nxt else len(text)
            rf.items.append(Raw(vnum, text[start:end], str(bad), line))
            rf.diagnostics.append(Diagnostic(filename, line, vnum, str(bad)))
            sc.pos = end
            continue
        if not (-1 <= room.sector <= 12):
            rf.diagnostics.append(Diagnostic(filename, line, vnum, f"settore fuori tabella ({room.sector})", "warning"))
        _stamp(room, text[start : sc.pos])
        rf.items.append(room)


# --------------------------------------------------------------------------- mob e oggetti


def _split_indexed(text: str) -> tuple[str, list[tuple[int, str]], str]:
    """`(head, [(offset, chunk)], tail)` per `.mob`/`.obj`: record = da `#` a inizio riga fino al prossimo `#`/`%%`."""
    term = _TERMINATOR.search(text)
    body_end = term.start() if term else len(text)
    starts = [m.start() for m in _HASH_LINE.finditer(text, 0, body_end)]
    tail = text[body_end:]
    if not starts:
        return text[:body_end], [], tail
    chunks = [(s, text[s : (starts[i + 1] if i + 1 < len(starts) else body_end)]) for i, s in enumerate(starts)]
    return text[: starts[0]], chunks, tail


def _chunk_header(sc: CScan) -> int:
    """Legge la riga `#vnum` come `sscanf(buf, "#%d")`; `_Bad` se non c'e' un numero."""
    first = sc.fgets(82)
    m = re.match(r"#\s*([+-]?\d+)", first)
    if not m:
        raise _Bad("intestazione #vnum non valida")
    return int(m.group(1))


def _read_dice(sc: CScan, what: str) -> Dice:
    """`fscanf(" %ldd%ld+%ld ")` rigoroso."""
    d = sc.scan_dice()
    if d is None:
        raise _Bad(f"dado {what} malformato")
    return Dice(*d)


def _load_mob(chunk: str) -> Mob:
    """Emula `read_mobile` sul blocco del record; `_Bad` se non e' leggibile."""
    sc = CScan(chunk)
    mob = Mob(vnum=_chunk_header(sc))
    mob.name, mob.short, mob.long, mob.description = (sc.fread_string() for _ in range(4))
    _check(sc, "stringhe")
    mob.act, mob.affected, mob.alignment = sc.fread_number(), sc.fread_number(), sc.fread_number()
    letter = sc.scan_char()
    if letter not in ("S", "A", "N", "B", "L"):
        raise _Bad(f"lettera tipo mancante o non supportata ({letter!r})")
    mob.kind = letter
    if letter in ("A", "B", "L"):
        mob.multi = sc.fread_number()
    sc.skip_ws()
    mob.level, mob.thac0, mob.ac = sc.fread_number(), sc.fread_number(), sc.fread_number()
    if letter == "S":
        mob.hp_dice = _read_dice(sc, "hp")
    else:
        mob.hp_bonus = sc.fread_number()
    mob.damage = _read_dice(sc, "danno")
    first = sc.fread_number()
    if first == -1:
        mob.gold, mob.exp, mob.race = sc.fread_number(), sc.fread_number(), sc.fread_number()
    else:
        mob.gold, mob.exp = first, sc.fread_number()
    mob.position, mob.default_pos, mob.sex_code = sc.fread_number(), sc.fread_number(), sc.fread_number()
    if 3 <= mob.sex_code < 6:
        mob.immune, mob.m_immune, mob.susc = sc.fread_number(), sc.fread_number(), sc.fread_number()
    if letter == "L":
        mob.sound, mob.distant_sound = sc.fread_string(), sc.fread_string()
    _check(sc, "campi numerici")
    mob.trailing = sc.rest().strip()  # il gioco ignora cio' che segue l'ultimo campo (`read_mobile` non lo legge)
    return mob


def _load_obj(chunk: str) -> Obj:
    """Emula `read_obj_from_file`: stringhe, numeri, `E`*, `A`* (max 5), `P` opzionale, nient'altro."""
    sc = CScan(chunk)
    obj = Obj(vnum=_chunk_header(sc))
    obj.name, obj.short, obj.description, obj.action = (sc.fread_string() for _ in range(4))
    _check(sc, "stringhe")
    obj.type, obj.extra_flags, obj.wear_flags = sc.fread_number(), sc.fread_number(), sc.fread_number()
    obj.values = [sc.fread_number() for _ in range(4)]
    obj.weight, obj.cost, obj.rent = sc.fread_number(), sc.fread_number(), sc.fread_number()
    _check(sc, "campi numerici")
    tok = sc.scan_word()
    while tok is not None and tok[0] == "E":
        kw, desc = sc.fread_string(), sc.fread_string()
        _check(sc, "extra description")
        obj.extra_descs.append(ExtraDesc(kw, desc))
        tok = sc.scan_word()
    while tok is not None and tok[0] == "A" and len(obj.affects) < MAX_OBJ_AFFECT:
        loc = sc.scan_int()
        if loc is None:
            raise _Bad("location di affect mancante")
        obj.affects.append(ObjAffect(loc, sc.fread_number()))
        _check(sc, "affect")
        tok = sc.scan_word()
    if tok is not None and tok[0] == "P":
        obj.forbidden = (sc.fread_string(), sc.fread_string())
        _check(sc, "blocco P")
        tok = sc.scan_word()
    if tok is not None:
        raise _Bad(f"token inatteso {tok!r} (E dopo A, piu' di {MAX_OBJ_AFFECT} affect o dati extra)")
    _check(sc, "record")
    return obj


def _parse_indexed(kind: str, loader, text: str, filename: str, force_vnum: int | None = None) -> RecordFile:  # type: ignore[no-untyped-def]
    """Parser comune di `.mob` e `.obj` (con `force_vnum` l'identita' e' quella del nome del file per-vnum)."""
    rf = RecordFile(kind)
    rf.head, chunks, rf.tail = _split_indexed(text)
    for offset, chunk in chunks:
        line = text.count("\n", 0, offset) + 1
        m = re.match(r"#\s*([+-]?\d+)", chunk)
        vnum = force_vnum if force_vnum is not None else (int(m.group(1)) if m else None)
        try:
            item = loader(chunk)
            if force_vnum is not None:
                item.vnum = force_vnum
        except _Bad as bad:
            rf.items.append(Raw(vnum, chunk, str(bad), line))
            rf.diagnostics.append(Diagnostic(filename, line, vnum, str(bad)))
            continue
        _stamp(item, chunk)
        rf.items.append(item)
    if not _TERMINATOR.search(text):
        rf.diagnostics.append(Diagnostic(filename, 0, None, "terminatore %% mancante (il gioco andrebbe in assert)", "warning"))
    rf.mark_clean()
    return rf


def parse_mob(text: str, filename: str = "") -> RecordFile:
    """Legge `dikumoddata.mob` (o un file di mob): record `S/A/N/B/L`; gli altri diventano `Raw`."""
    return _parse_indexed("mob", _load_mob, text, filename)


def parse_obj(text: str, filename: str = "", *, force_vnum: int | None = None) -> RecordFile:
    """Legge `dikumoddata.obj` o un file `objects/<vnum>` (stessa grammatica; con `force_vnum` l'header `#N`, inaffidabile nei
    file per-vnum, e' ignorato come fa il gioco: il nome del file e' l'identita')."""
    return _parse_indexed("obj", _load_obj, text, filename, force_vnum)


# --------------------------------------------------------------------------- zone

_CMD = re.compile(r"[ \t]*([A-Za-z])")
_NUM = re.compile(r"[ \t]*([+-]?\d+)")
_ZONE_HEAD = re.compile(r"(?m)^#[ \t]*[+-]?\d+[ \t]*\r?$")


def _parse_cmd_line(line: str) -> ZoneCmd | ZoneText:
    """Una riga di comando di zona, per righe: lettera, `if_flag`, argomenti presenti; il resto e' il commento."""
    body = line.rstrip("\n")
    m = _CMD.match(body)
    if not m:
        return ZoneText(line)
    letter = m.group(1)
    if letter not in ZONE_COMMANDS:
        return ZoneText(line)
    pos = m.end()
    nums: list[int] = []
    for _ in range(ZONE_ARG_COUNT[letter] + 1):
        n = _NUM.match(body, pos)
        if not n:
            break
        nums.append(int(n.group(1)))
        pos = n.end()
    cmd = ZoneCmd(letter, nums[0] if nums else 0, nums[1:], body[pos:])
    return cmd


def _parse_items(lines: list[str], diag: list[Diagnostic], filename: str, first_line: int) -> tuple[list, bool, int]:
    """Righe di comandi fino alla `S`: `(items, has_end, righe consumate inclusa la S)`."""
    items: list[ZoneCmd | ZoneText] = []
    for n, line in enumerate(lines):
        stripped = line.strip()
        if stripped[:1] == "S":
            return items, True, n + 1
        item: ZoneCmd | ZoneText
        if not stripped or stripped[0] in "*;":
            item = ZoneText(line)
        else:
            item = _parse_cmd_line(line)
            if isinstance(item, ZoneText):
                diag.append(Diagnostic(filename, first_line + n, None, f"riga di zona non riconosciuta: {stripped[:30]!r}", "warning"))
        if isinstance(item, ZoneCmd):
            expected = ZONE_ARG_COUNT[item.letter]
            if len(item.args) < expected and not (item.letter == "O" and len(item.args) == 3):
                diag.append(Diagnostic(filename, first_line + n, None, f"comando {item.letter} con argomenti mancanti", "warning"))
        if len(line.rstrip("\n")) > 78 and (isinstance(item, ZoneCmd) and item.comment or stripped[:1] in "*;" and stripped):
            diag.append(Diagnostic(filename, first_line + n, None, "commento oltre 79 caratteri: il loader C lo rilegge come comando", "warning"))
        _stamp(item, line)
        items.append(item)
    return items, False, len(lines)


def parse_zon(text: str, filename: str = "") -> RecordFile:
    """Legge `dikumoddata.zon`: zone con `#N`, nome `~`, `top lifespan mode`, comandi, `S`. Termina con la zona `$~`."""
    rf = RecordFile("zon")
    heads = [m.start() for m in _ZONE_HEAD.finditer(text)]
    if not heads:
        rf.tail = text
        rf.mark_clean()
        return rf
    rf.head = text[: heads[0]]
    for i, start in enumerate(heads):
        end = heads[i + 1] if i + 1 < len(heads) else len(text)
        chunk = text[start:end]
        line = text.count("\n", 0, start) + 1
        sc = CScan(chunk)
        sc.pos = chunk.index("\n") + 1 if "\n" in chunk else len(chunk)
        num = int(re.match(r"#\s*([+-]?\d+)", chunk).group(1))  # type: ignore[union-attr]
        name = sc.fread_string()
        if sc.errors:
            rf.items.append(Raw(num, chunk, "nome di zona senza ~", line))
            rf.diagnostics.append(Diagnostic(filename, line, num, "nome di zona senza ~"))
            continue
        if name.startswith("$"):
            rf.tail = text[start:]
            rf.mark_clean()
            return rf
        nums = [sc.scan_int() for _ in range(3)]
        if None in nums:
            rf.items.append(Raw(num, chunk, "intestazione `top lifespan mode` incompleta", line))
            rf.diagnostics.append(Diagnostic(filename, line, num, "intestazione `top lifespan mode` incompleta"))
            continue
        first = chunk.count("\n", 0, sc.pos) + 1
        rest = chunk[sc.pos :]
        nl = rest.find("\n")
        body = rest[nl + 1 :] if nl >= 0 else ""
        lines = body.splitlines(keepends=True)
        items, has_end, used = _parse_items(lines, rf.diagnostics, filename, line + first)
        zone = Zone(num, name, nums[0], nums[1], nums[2], items, has_end)  # type: ignore[arg-type]
        _stamp(zone, chunk)
        rf.items.append(zone)
    rf.mark_clean()
    return rf


def parse_zone_override(text: str, index: int, filename: str = "") -> ZoneOverride:
    """Legge `zones/<n>.zon`: solo comandi (anche `;`) fino alla `S`, senza intestazione (`LoadZoneFile`)."""
    items, has_end, _ = _parse_items(text.splitlines(keepends=True), [], filename, 1)
    zo = ZoneOverride(index, items, has_end)
    _stamp(zo, text)
    return zo


# --------------------------------------------------------------------------- negozi

_SHOP_START = re.compile(r"(?m)^#[^\n]*~[ \t]*$")


def _load_shop(sc: CScan, tag: str) -> Shop:
    """Emula `boot_the_shops` dopo la stringa `#...`."""
    sc.errors.clear()

    def num() -> int:
        """`fscanf("%d \\n")`."""
        v = sc.scan_int()
        if v is None:
            raise _Bad("intero atteso")
        sc.skip_ws()
        return v

    def flt() -> str:
        """`fscanf("%f \\n")`."""
        v = sc.scan_float_token()
        if v is None:
            raise _Bad("numero decimale atteso")
        return v

    shop = Shop(tag=tag)
    shop.producing = [num() for _ in range(5)]
    shop.profit_buy, shop.profit_sell = flt(), flt()
    shop.types = [num() for _ in range(5)]
    shop.messages = [sc.fread_string() for _ in range(7)]
    _check(sc, "messaggi")
    shop.temper1, shop.temper2, shop.keeper, shop.with_who, shop.room = num(), num(), num(), num(), num()
    shop.open1, shop.close1, shop.open2, shop.close2 = num(), num(), num(), num()
    return shop


def parse_shp(text: str, filename: str = "") -> RecordFile:
    """Legge `dikumoddata.shp`: negozi `#id~ ...` e terminatore `$~`; un negozio troncato diventa `Raw`."""
    rf = RecordFile("shp")
    sc = CScan(text)
    sc.skip_ws()
    rf.head = text[: sc.pos]
    while True:
        start = sc.pos
        if start >= len(text):
            rf.mark_clean()
            return rf
        tag = sc.fread_string()
        if tag.startswith("$"):
            rf.tail = text[start:]
            rf.mark_clean()
            return rf
        if not tag.startswith("#"):
            rf.tail = text[start:]
            rf.diagnostics.append(Diagnostic(filename, sc.line_of(start), None, "testo inatteso nel file negozi", "warning"))
            rf.mark_clean()
            return rf
        line = sc.line_of(start)
        try:
            shop = _load_shop(sc, tag)
        except _Bad as bad:
            nxt = _SHOP_START.search(text, start + 1)
            end = nxt.start() if nxt else len(text)
            tail = re.search(r"(?m)^\$~", text[start:end])
            if tail:  # il troncato e' l'ultimo: il terminatore resta fuori dal Raw
                end = start + tail.start()
            rf.items.append(Raw(_atoi(tag[1:]), text[start:end], str(bad), line))
            rf.diagnostics.append(Diagnostic(filename, line, _atoi(tag[1:]), str(bad)))
            sc.pos = end
            continue
        _stamp(shop, text[start : sc.pos])
        rf.items.append(shop)


# --------------------------------------------------------------------------- script


def parse_scripts_dat(text: str, filename: str = "") -> RecordFile:
    """Legge `scripts.dat`: una riga `Nome vnum_mob` per script; le altre righe restano `Raw` (verbatim)."""
    rf = RecordFile("scripts")
    for n, line in enumerate(text.splitlines(keepends=True), 1):
        m = re.fullmatch(r"\s*(\S+)\s+(-?\d+)\s*", line)
        if m:
            entry = ScriptEntry(m.group(1), int(m.group(2)))
            _stamp(entry, line)
            rf.items.append(entry)
        else:
            error = "" if not line.strip() else "riga di scripts.dat non riconosciuta"
            rf.items.append(Raw(None, line, error, n))
            if error:
                rf.diagnostics.append(Diagnostic(filename, n, None, error, "warning"))
    rf.mark_clean()
    return rf
