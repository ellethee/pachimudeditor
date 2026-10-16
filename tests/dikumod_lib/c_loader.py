"""Re-implementazione RIGOROSA, funzione per funzione, delle letture di `db.c` di Diku Modificato (solo per i test).

Non usa il parser della libreria (solo le primitive di I/O `CScan`, che imitano `fscanf`/`fread_*`): serve a verificare che
i file scritti restino leggibili dal gioco e che il parser e il loader concordino sul significato dei campi.
Riferimenti: `generate_indices`, `real_mobile/real_object`, `read_mobile`, `read_obj_from_file`, `load_one_room`,
`boot_zones`, `boot_the_shops`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pachimudeditor_adapter_dikumod.dikumod_lib.cscan import CScan


# --------------------------------------------------------------------------- generate_indices / real_*


@dataclass
class IndexEntry:
    """`struct index_data`: vnum, offset (`ftell` dopo la riga `#`, -1 = file per-vnum), nome."""

    vnum: int
    pos: int
    name: str


@dataclass
class Index:
    """Indice di mob o oggetti: `entries` (prima la parte "ordinata" = file principale, poi le directory), `sort_top`."""

    entries: list[IndexEntry] = field(default_factory=list)
    sort_top: int = 0


def _dir_name(body: str) -> str:
    """Nome letto da un file per-vnum: `fscanf(f, "#%*d\\n")` poi `fread_string`."""
    f = CScan(body)
    f.skip_ws()
    f.pos += 1  # '#'
    f.scan_int()
    f.skip_ws()
    return f.fread_string()


def generate_indices(text: str, dir_files: dict[int, str] | None = None) -> Index:
    """Scansione del file principale con `fgets(buf, 82)` come `generate_indices`; poi i file per-vnum non gia' presenti."""
    dir_files = dir_files or {}
    sc = CScan(text)
    index = Index()
    dvnums: set[int] = set()
    while True:
        if sc.eof:
            raise AssertionError("generate_indices: EOF senza %% (il gioco farebbe assert(0))")
        buf = sc.fgets(82)
        if buf.startswith("#"):
            m = re.match(r"#\s*([+-]?\d+)", buf)
            vnum = int(m.group(1)) if m else 0
            if vnum in dir_files:
                index.entries.append(IndexEntry(vnum, -1, _dir_name(dir_files[vnum])))
                dvnums.add(vnum)
            else:
                pos = sc.pos
                index.entries.append(IndexEntry(vnum, pos, sc.fread_string()))
        elif buf.startswith("%%"):
            break
    index.sort_top = len(index.entries)
    for vnum, body in sorted(dir_files.items()):
        if vnum in dvnums:
            continue
        index.entries.append(IndexEntry(vnum, -1, _dir_name(body)))
    return index


def real_lookup(index: Index, vnum: int) -> int:
    """`real_mobile`/`real_object`: ricerca binaria sulla parte ordinata, poi lineare sul resto; -1 se assente."""
    bot, top = 0, index.sort_top - 1
    while True:
        mid = (bot + top) // 2
        if 0 <= mid < len(index.entries) and index.entries[mid].vnum == vnum:
            return mid
        if bot >= top:
            for i in range(index.sort_top, len(index.entries)):
                if index.entries[i].vnum == vnum:
                    return i
            return -1
        if index.entries[mid].vnum > vnum:
            top = mid - 1
        else:
            bot = mid + 1


# --------------------------------------------------------------------------- read_mobile


def read_mobile(text: str, pos: int) -> dict[str, Any]:
    """`read_mobile`: legge un mob a partire da `pos` (offset dell'indice). Anomalie in `errors`."""
    sc = CScan(text, pos)
    m: dict[str, Any] = {}
    m["name"], m["short"], m["long"], m["desc"] = (sc.fread_string() for _ in range(4))
    m["act"] = sc.fread_number()
    m["affected"] = sc.fread_number()
    m["alignment"] = sc.fread_number()
    letter = sc.scan_char()
    m["kind"] = letter
    m["multi"] = None
    if letter == "S":
        sc.skip_ws()
        m["level"] = sc.fread_number()
        m["thac0"] = sc.fread_number()
        m["ac"] = sc.fread_number()
        hp = sc.scan_dice()
        m["hp"] = hp
        m["damage"] = sc.scan_dice()
        m["hp_bonus"] = None
    elif letter in ("A", "N", "B", "L"):
        if letter != "N":
            m["multi"] = sc.fread_number()
        sc.skip_ws()
        m["level"] = sc.fread_number()
        m["thac0"] = sc.fread_number()
        m["ac"] = sc.fread_number()
        m["hp"] = None
        m["hp_bonus"] = sc.fread_number()
        m["damage"] = sc.scan_dice()
    else:
        sc.errors.append(f"tipo vecchio/ignoto {letter!r}")
        m["errors"] = sc.errors
        return m
    first = sc.fread_number()
    if first == -1:
        m["gold"], m["exp"], m["race"] = sc.fread_number(), sc.fread_number(), sc.fread_number()
    else:
        m["gold"], m["exp"], m["race"] = first, sc.fread_number(), None
    m["position"], m["default_pos"] = sc.fread_number(), sc.fread_number()
    code = sc.fread_number()
    m["sex_code"] = code
    m["immune"] = m["m_immune"] = m["susc"] = 0
    if 3 <= code < 6:
        m["immune"], m["m_immune"], m["susc"] = sc.fread_number(), sc.fread_number(), sc.fread_number()
    m["sound"] = m["distant"] = None
    if letter == "L":
        m["sound"], m["distant"] = sc.fread_string(), sc.fread_string()
    m["errors"] = sc.errors
    return m


# --------------------------------------------------------------------------- read_obj_from_file


def read_object(text: str, pos: int) -> dict[str, Any]:
    """`read_obj_from_file`: stringhe, numeri, `E`*, `A`* (max 5), `P`."""
    sc = CScan(text, pos)
    o: dict[str, Any] = {}
    o["name"], o["short"], o["desc"], o["action"] = (sc.fread_string() for _ in range(4))
    o["type"], o["extra"], o["wear"] = sc.fread_number(), sc.fread_number(), sc.fread_number()
    o["values"] = [sc.fread_number() for _ in range(4)]
    o["weight"], o["cost"], o["rent"] = sc.fread_number(), sc.fread_number(), sc.fread_number()
    o["extras"], o["affects"], o["forbidden"] = [], [], None
    chk = sc.scan_word()
    while chk is not None and chk[0] == "E":
        o["extras"].append((sc.fread_string(), sc.fread_string()))
        chk = sc.scan_word()
    i = 0
    while i < 5 and chk is not None and chk[0] == "A":
        loc = sc.scan_int()
        mod = sc.fread_number()
        o["affects"].append((loc, mod))
        i += 1
        chk = sc.scan_word()
        if chk is None:
            break
    if chk is not None and chk[0] == "P":
        o["forbidden"] = (sc.fread_string(), sc.fread_string())
    o["errors"] = sc.errors
    return o


# --------------------------------------------------------------------------- boot_world / load_one_room


def boot_world(text: str) -> dict[int, dict[str, Any]]:
    """`boot_world` + `load_one_room`: `{vnum: stanza}`; token ignoti finiscono in `unknown`."""
    sc = CScan(text)
    rooms: dict[int, dict[str, Any]] = {}
    while True:
        sc.skip_ws()
        if sc.text[sc.pos : sc.pos + 1] != "#":
            break
        sc.pos += 1
        vnum = sc.scan_int()
        if vnum is None:
            break
        sc.skip_ws()
        rooms[vnum] = load_one_room(sc, vnum)
    return rooms


def load_one_room(sc: CScan, vnum: int) -> dict[str, Any]:
    """`load_one_room` (senza effetti collaterali sul mondo)."""
    r: dict[str, Any] = {"vnum": vnum, "exits": {}, "extras": [], "unknown": [], "light": None}
    r["name"], r["desc"] = sc.fread_string(), sc.fread_string()
    r["zone_ignored"] = sc.scan_int()
    r["flags"] = sc.fread_number()
    sector = sc.fread_number()
    r["tele"] = None
    if sector == -1:
        t, tg, mask = sc.fread_number(), sc.fread_number(), sc.fread_number()
        cnt = sc.fread_number() if mask & 2 else 0
        r["tele"] = (t, tg, mask, cnt)
        sector = sc.fread_number()
    r["sector"] = sector
    r["river"] = None
    if sector in (7, 9):
        r["river"] = (sc.fread_number(), sc.fread_number())
    r["moblim"] = sc.fread_number() if r["flags"] & 256 else None
    while True:
        chk = sc.scan_word()
        if chk is None:
            r["unknown"].append("EOF")
            break
        c = chk[0]
        if c == "D":
            d = int(re.match(r"\d*", chk[1:]).group() or 0)  # type: ignore[union-attr]
            desc, kw = sc.fread_string(), sc.fread_string()
            info, key, to = sc.fread_number(), sc.fread_number(), sc.fread_number()
            open_cmd = sc.scan_int()
            sc.skip_ws()
            r["exits"][d] = (desc, kw, info, key, to, -1 if open_cmd is None else open_cmd)
        elif c == "E":
            r["extras"].append((sc.fread_string(), sc.fread_string()))
        elif c == "L":
            r["light"] = (sc.fread_string(), sc.fread_string())
        elif c == "S":
            break
        elif c == "C":
            pass
        else:
            r["unknown"].append(chk)
    r["errors"] = list(sc.errors)
    return r


# --------------------------------------------------------------------------- boot_zones


def boot_zones(text: str) -> list[dict[str, Any]]:
    """`boot_zones` ESATTO, compresa la trappola dell'argomento 4 di `O` (`fscanf(" %d")` che salta il newline e fallisce)."""
    sc = CScan(text)
    zones: list[dict[str, Any]] = []
    while True:
        sc.skip_ws()
        if sc.text[sc.pos : sc.pos + 1] == "#":
            sc.pos += 1
            znum = sc.scan_int()
            sc.skip_ws()
        else:
            znum = None
        if sc.eof:
            break
        check = sc.fread_string()
        if check[:1] == "$":
            break
        top, life, mode = sc.scan_int(), sc.scan_int(), sc.scan_int()
        sc.skip_ws()
        cmds: list[tuple[Any, ...]] = []
        while True:
            sc.skip_ws()
            c = sc.getc()
            if c == "" or c == "S":
                break
            if c == "*":
                sc.fgets(80)
                continue
            vals: list[int | None] = []
            for _ in range(3):  # fscanf(" %d %d %d"): si ferma al primo fallimento
                v = sc.scan_int()
                vals.append(v)
                if v is None:
                    break
            vals += [None] * (3 - len(vals))
            arg3 = arg4 = None
            if c in "MOCEPD" and None not in vals:
                arg3 = sc.scan_int()
            if c == "O" and None not in vals:
                arg4 = sc.scan_int()
            sc.fgets(80)
            cmds.append((c, *vals, arg3, arg4))
        zones.append({"num": znum, "name": check, "top": top, "life": life, "mode": mode, "cmds": cmds})
        if sc.eof:
            break
    return zones


# --------------------------------------------------------------------------- boot_the_shops


def boot_shops(text: str) -> list[dict[str, Any]]:
    """`boot_the_shops`: una stringa `#...` apre un negozio, `$` chiude."""
    sc = CScan(text)
    shops: list[dict[str, Any]] = []
    while not sc.eof:
        buf = sc.fread_string()
        if buf.startswith("#"):
            s: dict[str, Any] = {"tag": buf}

            def num() -> int | None:
                """`fscanf("%d \\n")`."""
                v = sc.scan_int()
                sc.skip_ws()
                return v

            s["producing"] = [num() for _ in range(5)]
            sc_f = [sc.scan_float_token() for _ in range(2)]
            s["profit"] = sc_f
            s["types"] = [num() for _ in range(5)]
            s["messages"] = [sc.fread_string() for _ in range(7)]
            s["rest"] = [num() for _ in range(9)]
            shops.append(s)
        elif buf.startswith("$"):
            break
    return shops
