"""Lettore a cursore che replica i primitivi di lettura di `db.c` (fread_letter/number/flag/string/word)."""

from __future__ import annotations

from .errors import RomParseError

_WS = " \t\n\r\f\v"


class Reader:
    """Cursore sul testo di un `.are` con le stesse semantiche dei `fread_*` del server.

    Attributes:
        text: testo completo.
        i: posizione corrente.
        filename: nome file per i messaggi d'errore.
        context: contesto logico (sezione/vnum) per i messaggi d'errore.
    """

    def __init__(self, text: str, filename: str | None = None) -> None:
        self.text = text
        self.n = len(text)
        self.i = 0
        self.filename = filename
        self.context = ""

    # -- errori -----------------------------------------------------------------------------
    def error(self, message: str, pos: int | None = None) -> RomParseError:
        """Crea un RomParseError alla posizione `pos` (default: corrente) con riga e colonna."""
        p = self.i if pos is None else pos
        p = min(p, self.n)
        line = self.text.count("\n", 0, p) + 1
        col = p - (self.text.rfind("\n", 0, p) + 1) + 1
        return RomParseError(message, line, col, self.context, self.filename)

    def lineno(self, pos: int | None = None) -> int:
        """Numero di riga (1-based) di `pos` (default: posizione corrente)."""
        p = self.i if pos is None else pos
        return self.text.count("\n", 0, min(p, self.n)) + 1

    # -- primitivi --------------------------------------------------------------------------
    def eof(self) -> bool:
        """True se non resta altro che spazi bianchi."""
        j = self.i
        while j < self.n and self.text[j] in _WS:
            j += 1
        return j >= self.n

    def skip_ws(self) -> None:
        """Salta gli spazi bianchi."""
        while self.i < self.n and self.text[self.i] in _WS:
            self.i += 1

    def peek_letter(self) -> str:
        """Prossimo carattere non bianco senza consumare nulla ('' a fine file)."""
        j = self.i
        while j < self.n and self.text[j] in _WS:
            j += 1
        return self.text[j] if j < self.n else ""

    def letter(self) -> str:
        """`fread_letter`: salta gli spazi e consuma un carattere."""
        self.skip_ws()
        if self.i >= self.n:
            raise self.error("fine file inattesa")
        c = self.text[self.i]
        self.i += 1
        return c

    def number(self) -> int:
        """`fread_number`: intero con segno opzionale e somme con `|`."""
        self.skip_ws()
        start = self.i
        sign = False
        if self.i < self.n and self.text[self.i] == "+":
            self.i += 1
        elif self.i < self.n and self.text[self.i] == "-":
            sign = True
            self.i += 1
        if self.i >= self.n or not self.text[self.i].isdigit() or not self.text[self.i].isascii():
            raise self.error("numero atteso", start)
        j = self.i
        while j < self.n and self.text[j].isdigit() and self.text[j].isascii():
            j += 1
        value = int(self.text[self.i:j])
        self.i = j
        if sign:
            value = -value
        if self.i < self.n and self.text[self.i] == "|":
            self.i += 1
            value += self.number()
        elif self.i < self.n and self.text[self.i] == " ":
            self.i += 1
        return value

    def flag(self) -> int:
        """`fread_flag`: bit string a lettere/numeri/`|` (vedi `flags.parse_flags`)."""
        from .flags import letter_to_bit

        self.skip_ws()
        start = self.i
        negative = False
        if self.i < self.n and self.text[self.i] == "-":
            negative = True
            self.i += 1
        value = 0
        consumed = False
        if not (self.i < self.n and self.text[self.i].isdigit()):
            while self.i < self.n and self.text[self.i].isascii() and self.text[self.i].isalpha():
                value += letter_to_bit(self.text[self.i])
                self.i += 1
                consumed = True
        while self.i < self.n and self.text[self.i].isdigit() and self.text[self.i].isascii():
            value = value * 10 + int(self.text[self.i])
            self.i += 1
            consumed = True
        if not consumed:
            raise self.error("flag atteso", start)
        if negative:
            value = -value
        if self.i < self.n and self.text[self.i] == "|":
            self.i += 1
            value += self.flag()
        elif self.i < self.n and self.text[self.i] == " ":
            self.i += 1
        return value

    def word(self) -> str:
        """`fread_word`: parola delimitata da spazi, oppure da apici `'..'` / `".."` (apici esclusi)."""
        self.skip_ws()
        if self.i >= self.n:
            raise self.error("parola attesa, fine file")
        c = self.text[self.i]
        if c in "'\"":
            end = self.text.find(c, self.i + 1)
            if end < 0:
                raise self.error("apice non chiuso", self.i)
            w = self.text[self.i + 1:end]
            self.i = end + 1
            return w
        j = self.i
        while j < self.n and self.text[j] not in _WS:
            j += 1
        w = self.text[self.i:j]
        self.i = j
        return w

    def raw_token(self) -> tuple[str, bool]:
        """Come `word` ma restituisce anche se era tra apici: (valore, quoted)."""
        self.skip_ws()
        quoted = self.i < self.n and self.text[self.i] in "'\""
        return self.word(), quoted

    def string(self) -> str:
        """`fread_string`: salta gli spazi iniziali, legge fino a `~` (esclusa), scarta i `\\r`."""
        self.skip_ws()
        start = self.i
        end = self.text.find("~", self.i)
        if end < 0:
            raise self.error("stringa senza '~' finale", start)
        s = self.text[self.i:end]
        self.i = end + 1
        return s.replace("\r", "")

    def string_eol(self) -> str:
        """`fread_string_eol`: salta gli spazi iniziali e legge fino a fine riga."""
        self.skip_ws()
        j = self.i
        while j < self.n and self.text[j] not in "\r\n":
            j += 1
        s = self.text[self.i:j]
        self.i = j
        return s

    def rest_of_line(self) -> str:
        """Testo fino a fine riga (escluso); consuma anche il terminatore di riga."""
        j = self.i
        while j < self.n and self.text[j] not in "\r\n":
            j += 1
        s = self.text[self.i:j]
        if j < self.n:
            if self.text[j] == "\r" and j + 1 < self.n and self.text[j + 1] == "\n":
                j += 1
            j += 1
        self.i = j
        return s

    def end_item(self) -> None:
        """Se il resto della riga e' bianco lo consuma (compreso il newline): fissa il confine di un elemento."""
        j = self.i
        while j < self.n and self.text[j] in " \t\f\v":
            j += 1
        if j >= self.n:
            self.i = j
        elif self.text[j] == "\r" and j + 1 < self.n and self.text[j + 1] == "\n":
            self.i = j + 2
        elif self.text[j] in "\r\n":
            self.i = j + 1

    def dice(self) -> tuple[int, int, int]:
        """`fread_dice`: `NdT+B` (il segno `-` davanti al bonus e' accettato come negativo)."""
        number = self.number()
        self.letter()  # 'd'
        size = self.number()
        sign = self.letter()  # '+'
        bonus = self.number()
        if sign == "-":
            bonus = -bonus
        return number, size, bonus
