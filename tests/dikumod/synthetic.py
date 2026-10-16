"""Mondo Diku Modificato sintetico e minuscolo, costruito con record campione presi dai dati reali (stanze 0-2, mob 1, oggetto 1)."""

from pathlib import Path

WLD = """#0
Il vuoto~
  Incredibile ti senti di volare nel nulla...

~
0 0 0
D1
~
~
0 -1 1 -1
S
#1
Il cortile~
   Sei in un cortile.
~
0 0 1
D3
Una porta verso ovest.
~
porta~
1 -1 0 -1
E
sign cartello~
Un cartello di legno.
~
S
#2
Il giardino~
   Un giardino.
~
1 8 -1 30 6 1 0
D1
~
~
0 -1 98 -1
S
"""
MOB = """#1
Puff~
Puff~
Puff the Magic Dragon is here, attempting to sell Magic Mushrooms.
~
You see nothing special
~
2097153 0 1000 S
26 1 -10 5d10+550 4d6+3
-1 5000 155 9
8 8 5 0 1 0
#2
nazgul spettro anello~
Lo Spettro dell'Anello~
Une dei terribili spettri dell'anello e' qui!
~
Vestito di nero.
~
129 34146306 -1000 A 2
45 0 -5 100 3d6+6
-1 0 4 29
8 8 4 64 17152 0
%%~
"""
OBJ = """#1
gile pelle ~
Un gile in pelle~
Un gile' di pelle nera pieno di toppe
~
~
9 1|16|64 1|1024
9 9 0 0
1 30000 0
A
40 5
A
1 3
%%~
"""
ZON = """#1
Scratch Zone For Static Game~
0 0 0
S
#2
LIMBO~
49 1 0
M 0 1 1 1		Puff
E 1 1 1 16   ; gile
O 0 1 1 2
S
#9999999
$~
"""
SHP = "$~\n"


def write_world(lib: Path, prefix: str = "dikumoddata") -> Path:
    """Scrive i cinque file `<prefisso>.*` nella cartella `lib` (creata) e la restituisce."""
    lib.mkdir(parents=True, exist_ok=True)
    for name, text in (("wld", WLD), ("mob", MOB), ("obj", OBJ), ("zon", ZON), ("shp", SHP)):
        (lib / f"{prefix}.{name}").write_bytes(text.encode("latin-1"))
    return lib
