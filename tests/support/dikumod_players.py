"""Giocatori e rent Diku Modificato SINTETICI (nessun dato reale, nessun hash vero), costruiti con `struct.pack`.

Il formato e' scritto qui con una stringa di formato **contigua** (padding `x` esplicito, little-endian), indipendente dagli
offset del parser: se parser e fixture sono d'accordo, il layout C e' quello giusto (verificato anche con g++ `offsetof`).
"""

import struct
from pathlib import Path

PWD_MARKER = b"SYNTH-PW9"
"""Contenuto (finto) del campo `pwd` delle fixture: i test verificano che non esca MAI da nessuna risposta o log."""

CHAR_FMT = (
    "<i B 20B 3x i i i I I 80s 255s x h 240s 3B 3x i h 9b x "
    "h h b x h h b x h h b x h h B x h 2x i i i i i b b b x "
    "1400s 800s B 3x i I I i I 20s 30s 11s x 8h 2x 5i i i i"
).replace(" ", "")
CHAR_SIZE = 3036
assert struct.calcsize(CHAR_FMT) == CHAR_SIZE

RENT_HEAD = "<20s i i i i i"


def _elem_fmt() -> str:
    """Formato di un `obj_file_elem` (5 effetti espansi: `struct` non ha le ripetizioni di gruppo)."""
    return "<h2x4iiiii128s128s256sBB2x" + "h2xi" * 5


assert struct.calcsize(_elem_fmt()) == 592


def make_char(
    name: str = "Tizio",
    *,
    class_mask: int = 4,
    levels: tuple[int, ...] | None = None,
    sex: int = 1,
    race: int = 1,
    gold: int = 1234,
    bank: int = 99,
    exp: int = 5000,
    load_room: int = 3001,
    last_logon: int = 1_700_000_000,
    played: int = 7200,
    title: str = "il Prode",
    password: bytes = PWD_MARKER,
    skills: dict[int, tuple[int, int]] | None = None,
    affects: list[tuple[int, int, int, int, int]] | None = None,
) -> bytes:
    """Un `char_file_u` da 3036 byte. `levels` di default: livello 12 sulla prima classe accesa in `class_mask`."""
    lv = list(levels or [0] * 20)
    if levels is None:
        lv[(class_mask & -class_mask).bit_length() - 1] = 12
    lv += [0] * (20 - len(lv))
    skill_bytes = bytearray(1400)
    for index, (learned, flags) in (skills or {}).items():
        skill_bytes[index * 4 : index * 4 + 4] = bytes((learned, flags, 0, 0))
    aff = bytearray(800)
    for n, (t, dur, mod, loc, bv) in enumerate(affects or []):
        aff[n * 20 : n * 20 + 20] = struct.pack("<hhiiii", t, dur, mod, loc, bv, 0)
    return _pack(
        name, class_mask, sex, lv, race, gold, bank, exp, load_room, last_logon, played, title, password, bytes(skill_bytes), bytes(aff)
    )


def _pack(
    name: str, class_mask: int, sex: int, lv: list[int], race: int, gold: int, bank: int, exp: int, load_room: int,
    last_logon: int, played: int, title: str, password: bytes, skills: bytes, affects: bytes,
) -> bytes:  # fmt: skip
    """Impacchetta tutti i campi nell'ordine di `char_file_u`."""
    return struct.pack(
        CHAR_FMT,
        class_mask, sex, *lv, 1_000_000_000, played, race, 170, 180, title.encode("latin-1"), b"", 1, b"Un tipo.",
        0, 0, 0,  # talks[3]
        0, load_room,  # extra_flags, load_room
        16, 5, 12, 13, 14, 15, 9, 0, 0,  # abilities: str str_add int wis dex con chr extra extra2 (9 sbyte)
        20, 30, 0, 100, 120, 0, 90, 110, 0, 0, 0, 0, -50,  # mana max_mana gain hit max_hit gain move max_move gain e1 e2 e3 armor
        gold, bank, exp, exp, 0, 3, 4, 0,  # gold bank exp true_exp extra_dual hitroll damroll extra_h
        skills, affects, 7, 250, 0x10, 0, last_logon, 0x20, name.encode("latin-1"), b"", password, *([1] * 8), 0, 0, 0, 0, 0, 3001, 0, 0,
    )  # fmt: skip


def make_item(
    number: int = 1, *, name: str = "gile pelle", short: str = "Un gile in pelle", wearpos: int = 0, depth: int = 0, affects: int = 0
) -> bytes:
    """Un `obj_file_elem` da 592 byte."""
    aff: list[int] = []
    for n in range(5):
        aff += [40, 5] if n < affects else [0, 0]
    return struct.pack(
        _elem_fmt(), number, 9, 9, 0, 0, 0, 50, 0, 0, name.encode("latin-1"), short.encode("latin-1"), b"descrizione", wearpos, depth, *aff
    )


def make_rent(
    owner: str, items: list[bytes], *, number: int | None = None, gold_left: int = 500, last_update: int = 1_700_000_000
) -> bytes:
    """Un `obj_file_u`: testata da 40 byte + gli elementi (`number` dichiarato modificabile per simulare file corrotti)."""
    n = len(items) if number is None else number
    return struct.pack(RENT_HEAD.replace(" ", ""), owner.encode("latin-1"), gold_left, 10, last_update, 0, n) + b"".join(items)


def write_players(lib: Path, players: dict[str, bytes], rents: dict[str, bytes] | None = None) -> None:
    """Scrive `lib/players/<nome>.dat` e `lib/rent/<nome>` (cartelle create)."""
    (lib / "players").mkdir(parents=True, exist_ok=True)
    (lib / "rent").mkdir(parents=True, exist_ok=True)
    for name, data in players.items():
        (lib / "players" / f"{name}.dat").write_bytes(data)
    for name, data in (rents or {}).items():
        (lib / "rent" / name).write_bytes(data)


def standard_players(lib: Path) -> None:
    """Quattro giocatori: Tizio (guerriero, rent con equipaggiamento e contenitore), Caio (multiclasse, rent vuoto 0 byte),
    Sempronio (senza rent, senza password) e Mevio (rent con owner diverso)."""
    write_players(
        lib,
        {
            "tizio": make_char("Tizio", skills={5: (80, 1), 9: (0, 1)}, affects=[(3, 10, 2, 1, 0)]),
            "caio": make_char("Caio", class_mask=4 | 8, levels=(0, 0, 20, 31) + (0,) * 16, race=2, sex=2, load_room=-2, gold=0),
            "sempronio": make_char("Sempronio", class_mask=1, password=b"", last_logon=0, played=0, load_room=-1),
            "mevio": make_char("Mevio"),
        },
        {
            "tizio": make_rent(
                "Tizio",
                [
                    make_item(1, wearpos=6, affects=2),
                    make_item(1, name="sacco", short="Un sacco"),
                    make_item(9999, short="Roba strana", depth=1),
                ],
            ),
            "caio": b"",
            "mevio": make_rent("Altro", [make_item(1)]),
        },
    )


def reseed(*libs: str) -> None:
    """Sostituisce `players/` e `rent/` di ogni `lib` con i giocatori sintetici standard (per lo stack E2E: nessun dato reale)."""
    import shutil

    for name in libs:
        lib = Path(name)
        for d in ("players", "rent"):
            shutil.rmtree(lib / d, ignore_errors=True)
        standard_players(lib)


if __name__ == "__main__":
    import sys

    reseed(*sys.argv[1:])
