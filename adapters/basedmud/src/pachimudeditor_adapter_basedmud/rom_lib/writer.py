"""Serializzatore `.are`: `write_area(area) -> str` (formato di `olc_save.c`, sorgente originale se invariato)."""

from __future__ import annotations

from collections.abc import Callable

from . import flags as fl
from .errors import RomWriteError
from .model import (
    Area,
    AreaHeader,
    CommentLine,
    Help,
    MobProg,
    Mobile,
    Object,
    Reset,
    Room,
    Section,
    Shop,
    Social,
    Special,
)


def fix_string(s: str) -> str:
    """Come `fix_string` di olc_save.c: toglie `\\r` e `~` (che chiuderebbe la stringa)."""
    return s.replace("\r", "").replace("~", "")


def _ffl(value: int) -> str:
    """`fwrite_flag` (valori negativi in decimale)."""
    return fl.format_flags(value)


def _tok(value: str, quote: bool) -> str:
    """Serializza un valore-token di oggetto, tra apici se richiesto o necessario."""
    if quote or value == "" or any(c.isspace() for c in value):
        return f"'{value}'"
    return value


# -- singoli elementi (testo con `\n`) ----------------------------------------------------------
def format_mobile(m: Mobile) -> str:
    """Mob nel formato di `save_mobile`."""
    out = [
        f"#{m.vnum}",
        f"{fix_string(m.name)}~",
        f"{fix_string(m.short_descr)}~",
        f"{fix_string(m.long_descr)}~",
        f"{fix_string(m.description)}~",
        f"{fix_string(m.race)}~",
        f"{_ffl(m.act)} {_ffl(m.affected_by)} {m.alignment} {m.group}",
        f"{m.level} {m.hitroll} {m.hit} {m.mana} {m.damage} {m.dam_type}",
        " ".join(str(v) for v in m.ac),
        f"{_ffl(m.off_flags)} {_ffl(m.imm_flags)} {_ffl(m.res_flags)} {_ffl(m.vuln_flags)}",
        f"{m.start_pos} {m.default_pos} {m.sex} {m.wealth}",
        f"{_ffl(m.form)} {_ffl(m.parts)} {m.size} {m.material}",
    ]
    if len(m.ac) != 4:
        raise RomWriteError(f"mob {m.vnum}: 'ac' deve avere 4 valori")
    out += [f"F {fr.word} {_ffl(fr.value)}" for fr in m.flag_removals]
    out += [f"M {mp.trigger} {mp.vnum} {fix_string(mp.phrase)}~" for mp in m.mprogs]
    return "\n".join(out) + "\n"


def format_object(o: Object) -> str:
    """Oggetto nel formato di `save_object` (valori tra apici dove li usa il C)."""
    if len(o.values) != 5:
        raise RomWriteError(f"oggetto {o.vnum}: 'values' deve avere 5 valori")
    quoted = Object.QUOTED_SLOTS.get(o.item_type, ())
    vals = " ".join(_tok(v, i in quoted) for i, v in enumerate(o.values))
    out = [
        f"#{o.vnum}",
        f"{fix_string(o.name)}~",
        f"{fix_string(o.short_descr)}~",
        f"{fix_string(o.description)}~",
        f"{fix_string(o.material)}~",
        f"{o.item_type} {_ffl(o.extra_flags)} {_ffl(o.wear_flags)}",
        vals,
        f"{o.level} {o.weight} {o.cost} {o.condition}",
    ]
    for a in o.affects:
        if a.where == "" and a.bits == 0:
            out += ["A", f"{a.location} {a.modifier}"]
        else:
            if a.where not in ("A", "I", "R", "V"):
                raise RomWriteError(f"oggetto {o.vnum}: bit_type di affect non valido {a.where!r}")
            out += ["F", f"{a.where} {a.location} {a.modifier} {_ffl(a.bits)}"]
    for e in o.extra_descs:
        out += ["E", f"{fix_string(e.keyword)}~", f"{fix_string(e.description)}~"]
    return "\n".join(out) + "\n"


def format_room(r: Room) -> str:
    """Stanza nel formato di `save_room`."""
    out = [
        f"#{r.vnum}",
        f"{fix_string(r.name)}~",
        f"{fix_string(r.description)}~",
        f"{r.area_number} {_ffl(r.room_flags)} {r.sector}",
    ]
    for x in r.exits:
        out += [
            f"D{x.door}",
            f"{fix_string(x.description)}~",
            f"{fix_string(x.keyword)}~",
            f"{x.locks} {x.key} {x.to_vnum}",
        ]
    for e in r.extra_descs:
        out += ["E", f"{fix_string(e.keyword)}~", f"{fix_string(e.description)}~"]
    if r.owner:
        out.append(f"O {fix_string(r.owner)}~")
    if r.mana_rate != 100 or r.heal_rate != 100:
        out.append(f"M {r.mana_rate} H {r.heal_rate}")
    if r.clan:
        out.append(f"C {fix_string(r.clan)}~")
    out.append("S")
    return "\n".join(out) + "\n"


_RESET_FORMATS: dict[str, str] = {
    "M": "M {0} {1:5d} {2:3d} {3:5d} {4:2d}",
    "O": "O {0} {1:5d} {2:3d} {3:5d}",
    "P": "P {0} {1:5d} {2:3d} {3:5d} {4:2d}",
    "G": "G {0} {1:5d} {2:3d}",
    "E": "E {0} {1:5d} {2:3d} {3:5d}",
    "D": "D {0} {1:5d} {2:3d} {3:5d}",
    "R": "R {0} {1:5d} {2:3d}",
}


def format_reset(r: Reset) -> str:
    """Riga di reset nel formato di `save_resets` (commento in coda, se presente)."""
    fmt = _RESET_FORMATS.get(r.command)
    names = Reset.ARG_NAMES.get(r.command)
    if fmt is None or names is None:
        raise RomWriteError(f"comando di reset sconosciuto: {r.command!r}")
    if len(r.args) != len(names):
        raise RomWriteError(f"reset {r.command}: servono {len(names)} argomenti, trovati {len(r.args)}")
    line = fmt.format(*r.args)
    return line + (f" {r.comment}" if r.comment else "") + "\n"


def format_shop(s: Shop) -> str:
    """Riga di negozio nel formato di `save_shops`."""
    if len(s.buy_types) != 5:
        raise RomWriteError(f"negozio {s.keeper}: 'buy_types' deve avere 5 valori")
    buys = "".join(f"{b:2d} " for b in s.buy_types)
    line = f"{s.keeper:5d} {buys}{s.profit_buy:3d} {s.profit_sell:3d} {s.open_hour:2d} {s.close_hour:2d}"
    return line + (f" {s.comment}" if s.comment else "") + "\n"


def format_special(s: Special) -> str:
    """Riga #SPECIALS nel formato di `save_specials`."""
    line = f"M {s.mob_vnum:5d} {s.function:<20s}"
    return (line + f" {s.comment}" if s.comment else line) + "\n"


def format_comment(c: CommentLine) -> str:
    """Riga di commento."""
    return c.text + "\n"


def format_mobprog(p: MobProg) -> str:
    """Mobprog nel formato di `save_mobprogs`."""
    return f"#{p.vnum}\n{fix_string(p.code)}~\n"


def format_help(h: Help) -> str:
    """Help nel formato di `save_helps`."""
    return f"{h.level} {fix_string(h.keyword)}~\n{fix_string(h.text)}~\n\n"


def format_social(s: Social) -> str:
    """Social: nome (+parametri), 8 righe (`$` = vuota, `#` = terminazione anticipata), riga vuota."""
    head = s.name + (f" {s.params}" if s.params else "")
    body = ["$" if line is None else line for line in s.lines]
    if s.truncated:
        body.append("#")
    return "\n".join([head, *body]) + "\n\n"


def format_header(h: AreaHeader) -> str:
    """Intestazione nel formato `#AREA` (vecchio) o `#AREADATA` (`save_area`)."""
    if h.style == "AREA":
        vn = h.vnum_raw if h.vnum_raw is not None else f"{h.min_vnum} {h.max_vnum}"
        return f"{fix_string(h.filename)}~\n{fix_string(h.name)}~\n{fix_string(h.credits)}~\n{vn}\n\n"
    out = [
        f"Name {fix_string(h.name)}~",
        f"Builders {fix_string(h.builders)}~",
        f"VNUMs {h.min_vnum} {h.max_vnum}",
        f"Credits {fix_string(h.credits)}~",
        f"Security {h.security}",
    ]
    out += [f"{k} {v}".rstrip() for k, v in h.extra]
    out.append("End")
    return "\n".join(out) + "\n\n"


_FORMATTERS: dict[type, Callable] = {
    Mobile: format_mobile,
    Object: format_object,
    Room: format_room,
    Reset: format_reset,
    Shop: format_shop,
    Special: format_special,
    CommentLine: format_comment,
    MobProg: format_mobprog,
    Help: format_help,
    Social: format_social,
    AreaHeader: format_header,
}

#: Terminatori canonici delle sezioni (da olc_save.c).
CANONICAL_TAIL: dict[str, str] = {
    "MOBILES": "#0\n\n",
    "OBJECTS": "#0\n\n",
    "ROOMS": "#0\n\n",
    "MOBPROGS": "#0\n\n",
    "RESETS": "S\n\n",
    "SHOPS": "0\n\n",
    "SPECIALS": "S\n\n",
    "HELPS": "-1 $~\n\n",
    "SOCIALS": "#0\n\n",
    "AREA": "",
    "AREADATA": "",
}


def format_item(item: object) -> str:
    """Serializza un singolo elemento in forma canonica (newline `\\n`)."""
    fmt = _FORMATTERS.get(type(item))
    if fmt is None:
        raise RomWriteError(f"tipo non serializzabile: {type(item).__name__}")
    return fmt(item)


def is_unchanged(item: object) -> bool:
    """True se l'elemento conserva il sorgente originale e non e' stato modificato dopo il parsing."""
    src = getattr(item, "_src", None)
    return src is not None and getattr(item, "_fp", None) == repr(item)


def _nl(text: str, newline: str) -> str:
    return text if newline == "\n" else text.replace("\n", newline)


def _write_section(sec: Section, newline: str, preserve: bool) -> str:
    """Testo di una sezione."""
    if sec.kind == "RAW":
        head = sec.head if (preserve and sec.head is not None) else f"#{sec.name}\n"
        return head + sec.text
    if sec.head is None and not sec.items and sec.kind not in ("AREA", "AREADATA"):
        return ""  # sezione creata dall'accesso alle proprieta' e rimasta vuota
    use_src = preserve and sec.head is not None
    kind = sec.kind
    if kind in ("AREA", "AREADATA") and sec.items and sec.items[0].style != kind:
        kind = sec.items[0].style  # cambio di stile dell'intestazione: la testata va rigenerata
        use_src = False
    parts = [sec.head if use_src else _nl(f"#{kind}\n", newline)]
    for item in sec.items:
        if use_src and is_unchanged(item):
            parts.append(item._src)  # type: ignore[attr-defined]
        else:
            text = format_item(item)
            if use_src and kind in ("AREA", "AREADATA"):
                text = text.rstrip("\n") + "\n"  # la riga vuota dopo l'intestazione sta nella testata della sezione successiva
            parts.append(_nl(text, newline))
    if sec.tail is not None and use_src:
        parts.append(sec.tail)
    else:
        parts.append(_nl(CANONICAL_TAIL.get(sec.kind, ""), newline))
    return "".join(parts)


def write_area(area: Area, *, preserve: bool = True) -> str:
    """Serializza l'`Area` in testo `.are`.

    Con `preserve=True` (default) testata/terminatori di sezione e gli elementi non modificati
    sono riemessi byte per byte dal sorgente; gli elementi nuovi o modificati usano il formato
    canonico di `olc_save.c`. Con `preserve=False` l'intero file e' rigenerato in forma canonica
    (nell'ordine delle sezioni dell'area e con lo stile newline di `area.newline`).

    Raises:
        RomWriteError: dati non serializzabili (es. argomenti di reset mancanti).
    """
    nl = area.newline
    out: list[str] = []
    for sec in area.sections:
        text = _write_section(sec, nl, preserve)
        if text and preserve and sec.head is None and out:
            # sezione nuova: separala dalla precedente con una riga vuota, come fa il saver C
            joined = "".join(out[-2:])
            if not joined.endswith(nl + nl):
                text = nl + text
        out.append(text)
    if area.has_terminator:
        end = area.end_head if preserve and area.end_head is not None else _nl("#$\n", nl)
        if preserve and area.end_head is not None and "".join(out[-2:]).endswith(nl + nl):
            end = end.lstrip("\r\n")  # il blocco precedente chiude gia' con una riga vuota
        out.append(end)
    out.append(area.trailer if preserve else "")
    return "".join(out)


__all__ = ["CANONICAL_TAIL", "fix_string", "format_item", "format_mobile", "format_object", "format_room", "is_unchanged", "write_area"]
