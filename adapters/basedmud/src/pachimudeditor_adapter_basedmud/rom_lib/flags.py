"""Flag ROM: parsing e serializzazione delle "bit string" (`fread_flag` / `fwrite_flag`).

Convenzioni (db.c / olc_save.c di basedmud):

* le lettere `A`-`Z` valgono i bit 0-25, le lettere `a`-`z` i bit 26-51;
* un valore puo' essere numerico (`1234`), a lettere (`ABV`) o una somma con `|` (`A|C|8`);
* `fwrite_flag` scrive `0` per zero, altrimenti le lettere in ordine crescente di bit.
"""

from __future__ import annotations

from collections.abc import Iterable

from .tables import FLAG_TABLES

#: Bit massimo rappresentabile con lettere (a-z => bit 26..51).
MAX_BIT = 52


def letter_to_bit(letter: str) -> int:
    """Restituisce il valore (potenza di 2) di una lettera flag (`flag_convert`).

    Raises:
        ValueError: se `letter` non e' una lettera ASCII.
    """
    if len(letter) == 1 and "A" <= letter <= "Z":
        return 1 << (ord(letter) - ord("A"))
    if len(letter) == 1 and "a" <= letter <= "z":
        return 1 << (26 + ord(letter) - ord("a"))
    raise ValueError(f"lettera flag non valida: {letter!r}")


def bit_to_letter(bit: int) -> str:
    """Restituisce la lettera dell'indice di bit `bit` (0 -> `A`, 26 -> `a`).

    Raises:
        ValueError: se il bit e' fuori dall'intervallo 0..51.
    """
    if 0 <= bit <= 25:
        return chr(ord("A") + bit)
    if 26 <= bit < MAX_BIT:
        return chr(ord("a") + bit - 26)
    raise ValueError(f"bit flag fuori intervallo: {bit}")


def parse_flags(text: str) -> int:
    """Interpreta una bit string ROM (`ABV`, `1234`, `A|B|16`, `-1`) in intero, come `fread_flag`.

    Lettere seguite da cifre seguono il C (`A5` = 1*10+5); `|` somma altri termini.

    Raises:
        ValueError: se il testo non e' una bit string valida.
    """
    from .errors import RomParseError
    from .reader import Reader

    r = Reader(text.strip())
    try:
        value = r.flag()
    except RomParseError as exc:
        raise ValueError(f"bit string non valida: {text!r}") from exc
    if r.i < r.n:
        raise ValueError(f"bit string non valida: {text!r}")
    return value


def format_flags(value: int) -> str:
    """Serializza un intero come `fwrite_flag`: `0` se nullo, altrimenti lettere crescenti.

    I valori negativi (non rappresentabili a lettere) sono scritti come numero decimale.
    Bit oltre il 51 non sono rappresentabili e danno ValueError.
    """
    if value == 0:
        return "0"
    if value < 0:
        return str(value)
    if value >> MAX_BIT:
        raise ValueError(f"flag non rappresentabile a lettere: {value}")
    return "".join(bit_to_letter(b) for b in range(MAX_BIT) if value >> b & 1)


def flags_to_letters(value: int) -> frozenset[str]:
    """Restituisce l'insieme delle lettere impostate in `value`."""
    if value < 0 or value >> MAX_BIT:
        raise ValueError(f"flag non rappresentabile a lettere: {value}")
    return frozenset(bit_to_letter(b) for b in range(MAX_BIT) if value >> b & 1)


def letters_to_flags(letters: Iterable[str]) -> int:
    """Costruisce il valore intero da un insieme/stringa di lettere flag."""
    value = 0
    for letter in letters:
        value |= letter_to_bit(letter)
    return value


def has_flag(value: int, letter: str) -> bool:
    """True se la lettera `letter` e' impostata in `value`."""
    return bool(value & letter_to_bit(letter))


def set_flag(value: int, letter: str, on: bool = True) -> int:
    """Restituisce `value` con la lettera `letter` accesa (`on`) o spenta."""
    bit = letter_to_bit(letter)
    return value | bit if on else value & ~bit


def flag_names(table: str, value: int) -> list[str]:
    """Nomi simbolici (da `FLAG_TABLES[table]`) dei bit accesi, in ordine di bit.

    I bit non presenti in tabella sono riportati come lettera tra parentesi quadre, es. `[Z]`.
    """
    names = FLAG_TABLES[table]
    known = {bit: name for name, bit in names.items()}
    out: list[str] = []
    for b in range(MAX_BIT):
        bit = 1 << b
        if value & bit:
            out.append(known.get(bit, f"[{bit_to_letter(b)}]"))
    return out


def names_to_flags(table: str, names: Iterable[str]) -> int:
    """Converte nomi simbolici (o `[X]` per lettere ignote) nel valore intero.

    Raises:
        KeyError: se un nome non esiste nella tabella.
    """
    mapping = FLAG_TABLES[table]
    value = 0
    for name in names:
        if name.startswith("[") and name.endswith("]") and len(name) == 3:
            value |= letter_to_bit(name[1])
        else:
            value |= mapping[name]
    return value

