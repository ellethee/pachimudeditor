"""Mondi sintetici piccoli e versionati (contenuti inventati) per i test che altrimenti richiederebbero dati reali fuori repo.

- ROM/basedmud: `write_rom_area` scrive un `area.lst` e due aree (`prato.are` in stile `#AREADATA`, `fucina.are` in stile `#AREA`);
- Diku Modificato: `write_dikumod_world` scrive i file `<prefisso>.{wld,mob,obj,zon,shp}` (prefisso predefinito `dikumoddata`).

Le funzioni scrivono solo nella cartella indicata. Le fixture che le usano come ripiego dei dati reali sono in `tests/conftest.py`.
"""

from pathlib import Path

# ----------------------------------------------------------------------------- ROM

_ROM_MOBS = """#MOBILES
#{m0}
maestro nome~
il maestro~
Un maestro passeggia qui.
~
Il maestro sembra anziano.
~
human~
ABV D 900 0
23 2 1d1+999 1d1+999 1d8+32 magic
-15 -15 -15 -15
AF ABCD 0 0
stand stand male 15000
0 0 medium 0
#{m1}
topo~
un topo~
Un topo squittisce qui.
~
Un topo.
~
rodent~
0 0 0 0
1 0 1d2+1 1d1+0 1d2+0 bite
0 0 0 0
0 0 0 0
stand stand none 0
0 0 tiny 0
#0

"""

_ROM_OBJECTS = """#OBJECTS
#{o0}
spada lama~
una spada lunga~
Una spada lunga giace qui.~
steel~
weapon BI AN
sword 4 10 slash EF
20 100 500 P
A
18 3
E
spada~
Acciaio fine.
~
#{o1}
bottiglia~
una bottiglia~
Una bottiglia e' qui.~
glass~
drink 0 A
16 16 'local specialty' 0 0
0 10 5 G
#{o2}
borsa~
una borsa~
Una borsa.~
cloth~
container 0 A
50 AB 0 100 100
0 10 5 P
#{o3}
pozione~
una pozione~
Una pozione.~
glass~
potion 0 A
10 'sanctuary' 'cure light' '' ''
0 1 1 P
#{o4}
chiave ferro~
una chiave di ferro~
Una chiave di ferro.~
iron~
key 0 A
0 0 0 0 0
0 1 1 P
#0

"""

_ROM_ROOMS = """#ROOMS
#{r0}
La Sala~
Una sala ampia.
Seconda riga.
~
0 CDS 1
D0
Il nord e' buio.
~
porta~
1 {o4} {r1}
D2
~
~
0 -1 {r2}
E
targa~
Una targa.
~
O Anna~
S
#{r1}
Il Ripostiglio~
Un ripostiglio.
~
0 0 0
D2
~
porta~
1 {o4} {r0}
S
#{r2}
Il Giardino~
Un giardino.
~
0 0 2
D0
~
~
0 -1 {r0}
D1
~
~
0 -1 {link}
S
#{r3}
Il Pozzo~
Un pozzo.
~
0 0 0
S
#0

"""

_ROM_RESETS = """#RESETS
M 0 {m0} 1 {r0} 1	* il maestro
E 1 {o0} -1 16
G 1 {o1} -1
O 0 {o2} 1 {r0}
P 0 {o3} 1 {o2} 1
M 0 {m1} 3 {r2} 2
D 0 {r0} 0 2
R 0 {r0} 2
* una nota
S

"""

_ROM_SHOPS = """#SHOPS
{m0}  2  3  4 10  0 	 105  15 	 0 23 	* il maestro
0

"""

_ROM_SPECIALS = """#SPECIALS
M {m0} spec_cast_mage  	* il maestro
* nota
S

"""

_ROM_HEADERS = {
    "AREADATA": "#AREADATA\nName {name}~\nBuilders {builder}~\nVNUMs {low} {high}\nCredits {builder} {name}~\nSecurity 5\nEnd\n\n",
    "AREA": "#AREA\n{file}~\n{name}~\n{{ 1 10}} {builder}  {name}~\n{low} {high}\n\n",
}


def _rom_area(style: str, file: str, name: str, base: int, link: int, *, full: bool) -> str:
    """Il testo di un'area ROM con vnum a partire da `base` (`full` aggiunge negozio e special; `link`: stanza di un'altra area)."""
    v = {
        "m0": base, "m1": base + 1, "o0": base, "o1": base + 1, "o2": base + 2, "o3": base + 3, "o4": base + 4,
        "r0": base, "r1": base + 1, "r2": base + 2, "r3": base + 3, "link": link,
    }  # fmt: skip
    head = _ROM_HEADERS[style].format(file=file, name=name, builder="Tester", low=base, high=base + 99)
    parts = [_ROM_MOBS, _ROM_OBJECTS, _ROM_ROOMS, _ROM_RESETS]
    if full:
        parts += [_ROM_SHOPS, _ROM_SPECIALS]
    return head + "".join(parts).format(**v) + "#$\n"


def write_rom_area(dest: Path) -> Path:
    """Scrive in `dest` (creata) `area.lst` e due aree ROM sintetiche; restituisce `dest`.

    `prato.are` (stile `#AREADATA`, vnum 5000-5099, con negozio e special; una uscita porta a `fucina.are` e viceversa) e `fucina.are` (stile `#AREA`, vnum 6000-6099, anch'essa con negozio e special).
    """
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "prato.are").write_bytes(_rom_area("AREADATA", "prato.are", "Prato", 5000, 7000, full=True).encode("latin-1"))
    (dest / "fucina.are").write_bytes(_rom_area("AREA", "fucina.are", "Fucina", 6000, 5000, full=True).encode("latin-1"))
    (dest / "area.lst").write_text("prato.are\nfucina.are\n$\n")
    return dest


# ----------------------------------------------------------------------------- Diku Modificato

DIKUMOD_WLD = """#1
La piazza~
   Una piazza inventata.
~
0 0 1
D0
~
~
0 -1 2
D1
Una porta di legno.
~
porta~
1 4 3
E
fontana~
Una fontana di pietra.
~
S
#2
La via~
   Una via stretta.
~
0 8 1
D2
~
~
0 -1 1
S
#3
La bottega~
   Una bottega con un bancone.
~
0 0 0
D3
~
porta~
1 4 1
S
#100
Il sentiero~
   Un sentiero nel bosco.
~
0 0 3
D1
~
~
0 -1 101
S
#101
La radura~
   Una radura soleggiata.
~
0 0 2
D3
~
~
0 -1 100
S
"""

DIKUMOD_MOB = """#1
guardia~
La guardia~
Una guardia sorveglia l'ingresso.
~
Una guardia robusta.
~
2097153 0 1000 S
26 1 -10 5d10+550 4d6+3
-1 5000 155 9
8 8 5 0 1 0
#2
mercante~
Il mercante~
Un mercante attende i clienti.
~
Un mercante grassoccio.
~
7 0 500 S
10 5 3 2d8+20 1d6+2
1000 200
8 8 1
#100
scoiattolo~
Lo scoiattolo~
Uno scoiattolo salta tra i rami.
~
Uno scoiattolo.
~
129 34146306 -1000 A 2
45 0 -5 100 3d6+6
-1 0 4 29
8 8 4 64 17152 0
%%~
"""

DIKUMOD_OBJ = """#1
spada ferro~
Una spada di ferro~
Una spada di ferro e' stata lasciata qui.
~
~
5 64 8193
0 2 6 3
10 500 10
A
18 2
#2
forziere legno~
Un forziere di legno~
Un forziere di legno e' qui.
~
~
15 0 0
100 1 4 0
50 100 0
E
forziere~
Un forziere robusto.
~
#3
mela~
Una mela~
Una mela rossa giace qui.
~
~
19 0 1
5 0 0 0
1 5 0
#4
chiave rame~
Una chiave di rame~
Una chiave di rame.
~
~
18 0 1
0 0 0 0
1 10 0
#100
fiasca~
Una fiasca~
Una fiasca di cuoio.
~
~
17 0 1
10 10 0 0
2 20 0
%%~
"""

DIKUMOD_ZON = """#1
Zona di servizio~
0 0 0
S
#2
La valle di prova~
99 20 2
* commento
M 0 1 1 1		guardia
E 1 1 1 16
M 0 2 1 3		mercante
G 1 3 1
O 0 2 1 1 0
P 0 3 1 2
D 0 1 1 1
S
#3
I monti di prova~
199 30 2
M 0 100 2 100
O -5 100 1 101 0
S
#9999999
$~
"""

DIKUMOD_SHP = """#1~
3
-1
-1
-1
-1
1.500000
0.500000
19
0
0
0
0
%s Non l'ho.~
%s Non hai niente.~
%s Non compro questo.~
%s Non hai abbastanza oro.~
%s Non hai abbastanza oro.~
%s Costa %d monete.~
%s Ne ricevi %d monete.~
0
0
2
0
3
0
28
0
0
$~
"""


def write_dikumod_world(lib: Path, prefix: str = "dikumoddata") -> Path:
    """Scrive i cinque file `<prefisso>.{wld,mob,obj,zon,shp}` nella cartella `lib` (creata) e la restituisce.

    Due zone oltre a quella di servizio (stanze 1-3 e 100-101), tre mob (tipi `S` e `A`, un negoziante), cinque oggetti,
    reset `M E G O P D`, porte, extra description e un negozio.
    """
    lib.mkdir(parents=True, exist_ok=True)
    files = {"wld": DIKUMOD_WLD, "mob": DIKUMOD_MOB, "obj": DIKUMOD_OBJ, "zon": DIKUMOD_ZON, "shp": DIKUMOD_SHP}
    for ext, text in files.items():
        (lib / f"{prefix}.{ext}").write_bytes(text.encode("latin-1"))
    return lib
