"""Scanner che imita le primitive di lettura del gioco (`db.c`: `fread_string`, `fread_number`, `fscanf`, `fgets`).

Il testo e' una `str` ottenuta con `latin-1` (un carattere per byte: round-trip esatto). Ogni metodo riproduce il
comportamento della funzione C corrispondente, **inclusi** i fallimenti (restituiscono `None`/0 e lasciano la posizione
come farebbe il C) e li registra in `errors` quando il C emetterebbe un `mudlog`. Il parser tollerante e l'emulazione
"stretta" del loader usata nei test condividono queste primitive.
"""

from __future__ import annotations

MAX_STRING_LENGTH = 20480
"""`MAX_STRING_LENGTH` di `structs.h`: oltre `MAX - 3` caratteri `fread_string` segnala errore."""

_WS = " \t\n\r\v\f"


class CScan:
    """Cursore su un testo con le primitive di I/O del gioco."""

    def __init__(self, text: str, pos: int = 0) -> None:
        """Parte da `pos`; `errors` raccoglie le anomalie che il C scriverebbe nel log."""
        self.text = text
        self.pos = pos
        self.errors: list[str] = []

    # ------------------------------------------------------------------ basi

    @property
    def eof(self) -> bool:
        """True a fine testo."""
        return self.pos >= len(self.text)

    def rest(self) -> str:
        """Il testo non ancora letto."""
        return self.text[self.pos :]

    def line_of(self, pos: int | None = None) -> int:
        """Numero di riga (1-based) di `pos` (default: posizione corrente)."""
        return self.text.count("\n", 0, self.pos if pos is None else pos) + 1

    def getc(self) -> str:
        """`getc`: un carattere o `""` a EOF."""
        if self.pos >= len(self.text):
            return ""
        c = self.text[self.pos]
        self.pos += 1
        return c

    def skip_ws(self) -> None:
        """`fscanf(" ")`: salta tutti gli spazi bianchi (anche newline)."""
        t, n = self.text, len(self.text)
        while self.pos < n and t[self.pos] in _WS:
            self.pos += 1

    # ------------------------------------------------------------------ fscanf

    def scan_int(self) -> int | None:
        """`fscanf(" %d")`: salta gli spazi, legge `[+-]cifre`; `None` (senza consumare il carattere) se non e' un intero."""
        self.skip_ws()
        t, n, p = self.text, len(self.text), self.pos
        q = p
        if q < n and t[q] in "+-":
            q += 1
        start = q
        while q < n and t[q].isdigit() and t[q].isascii():
            q += 1
        if q == start:
            return None
        self.pos = q
        return int(t[p:q])

    def scan_char(self) -> str | None:
        """`fscanf(" %c")`: salta gli spazi e legge un carattere (`None` a EOF)."""
        self.skip_ws()
        c = self.getc()
        return c or None

    def scan_word(self, limit: int = 160) -> str | None:
        """`fscanf(" %160s \\n")`: parola (max `limit`), poi salta TUTTI gli spazi che seguono; `None` a EOF."""
        self.skip_ws()
        t, n, p = self.text, len(self.text), self.pos
        q = p
        while q < n and t[q] not in _WS and q - p < limit:
            q += 1
        if q == p:
            return None
        self.pos = q
        self.skip_ws()
        return t[p:q]

    def scan_dice(self) -> tuple[int, int, int] | None:
        """`fscanf(" %ldd%ld+%ld ")`: `(n, m, k)` oppure `None` se il testo non ha esattamente quella forma."""
        save = self.pos
        a = self.scan_int()
        if a is None or self.getc() != "d":
            self.pos = save
            return None
        b = self._int_nows()
        if b is None or self.getc() != "+":
            self.pos = save
            return None
        c = self._int_nows()
        if c is None:
            self.pos = save
            return None
        self.skip_ws()
        return a, b, c

    def _int_nows(self) -> int | None:
        """Intero senza saltare gli spazi (i campi di un dado sono attaccati)."""
        if self.pos < len(self.text) and self.text[self.pos] in _WS:
            return None
        return self.scan_int()

    def scan_float_token(self) -> str | None:
        """`fscanf("%f \\n")`: il token numerico come testo (conserva `1.1`, `.001`); `None` se non e' un numero."""
        self.skip_ws()
        t, n, p = self.text, len(self.text), self.pos
        q = p
        while q < n and t[q] not in _WS:
            q += 1
        token = t[p:q]
        try:
            float(token)
        except ValueError:
            return None
        self.pos = q
        self.skip_ws()
        return token

    def fgets(self, size: int) -> str:
        """`fgets(buf, size)`: al piu' `size - 1` caratteri, fermandosi dopo un newline."""
        t, p = self.text, self.pos
        end = min(len(t), p + size - 1)
        nl = t.find("\n", p, end)
        if nl >= 0:
            end = nl + 1
        self.pos = end
        return t[p:end]

    # ------------------------------------------------------------------ funzioni di db.c

    def fread_string(self) -> str:
        """`fread_string`: testo fino alla `~` (esclusa), poi scarta UN carattere. Errori in `errors` come il `mudlog`."""
        t, p = self.text, self.pos
        end = t.find("~", p)
        if end < 0:
            self.errors.append("EOF in fread_string (manca la ~)")
            self.pos = len(t)
            return t[p:]
        body = t[p:end]
        if len(body) + body.count("\n") >= MAX_STRING_LENGTH - 3:
            self.errors.append("stringa troppo lunga (fread_string)")
        self.pos = min(len(t), end + 2)
        return body

    def fread_number(self) -> int:
        """`fread_number`: intero con segno; se segue `|` somma il termine successivo. Dato non numerico: errore e 0."""
        t, n = self.text, len(self.text)
        c = self.getc()
        while c and c in _WS:
            c = self.getc()
        sign = False
        if c == "+":
            c = self.getc()
        elif c == "-":
            sign = True
            c = self.getc()
        if not (c and c.isascii() and c.isdigit()):
            self.errors.append(f"fread_number: formato errato (carattere {c!r})")
            if c:
                self.pos -= 1
            return 0
        number = 0
        while c and c.isascii() and c.isdigit():
            number = number * 10 + int(c)
            c = self.getc()
        if sign:
            number = -number
        if c == "|":
            number += self.fread_number()
        elif c != " " and c:
            self.pos -= 1
        return number
