"""Mondi di prova per i test del `MappingAdapter`: copie temporanee di dati reali (mai scrittura sugli originali).

- ROM: le aree `.are` di basedmud (`area.lst` + `*.are`);
- Diku classico: un mondo sintetico piccolo costruito con record **reali** di Diku Modificato (`dikumoddata.{zon,wld,mob,obj,shp}` di
  `<DIKUMOD_ROOT>/dikumod2/lib`): le prime quattro zone e tutto cio' che cade nei loro range di vnum. I reset che puntano a vnum
fuori dal mondo sintetico sono tolti (`prune_resets`), cosi' gli script passano la validazione dei riferimenti.
"""

import hashlib
import os
import re
import shutil
from pathlib import Path

ROM_AREA = Path(os.environ.get("BASEDMUD_AREA_DIR", Path(__file__).resolve().parents[3] / "basedmud" / "area"))
"""Cartella `area/` reale di basedmud (sola lettura)."""
# Nessun default: senza `DIKUMOD_ROOT` la cartella non esiste e i test che la usano si saltano.
PREFIX = os.environ.get("DIKUMOD_PREFIX") or "dikumoddata"
"""Prefisso dei file dati reali (`DIKUMOD_PREFIX`)."""
DIKUMOD_LIB: Path | None = Path(root) / "dikumod2" / "lib" if (root := os.environ.get("DIKUMOD_ROOT")) else None
"""Cartella `lib/` reale della variante `dikumod2` (sola lettura, solo da `DIKUMOD_ROOT`); `None` se non impostata."""
EXAMPLES = Path(__file__).resolve().parents[2] / "adapters" / "mapping" / "src" / "pachimudeditor_adapter_mapping" / "examples"
ROM_MAPPING = EXAMPLES / "rom.yaml"
DIKU_MAPPING = EXAMPLES / "diku_classic.yaml"
DIKUMOD_ZONES = 4
"""Quante zone (in ordine di file) entrano nel mondo sintetico: #1, #2, #3, #4 (top 0, 49, 199, 249)."""


def digest(folder: Path) -> dict[str, str]:
    """SHA-256 di ogni file (non ricorsivo) della cartella."""
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}


def copy_rom_area(dest: Path) -> Path:
    """Copia le aree reali (`*.are`, `area.lst`) in `dest`."""
    dest.mkdir(parents=True, exist_ok=True)
    for p in ROM_AREA.iterdir():
        if p.is_file() and (p.suffix == ".are" or p.name == "area.lst"):
            shutil.copy2(p, dest / p.name)
    return dest


def chunks(text: str, pattern: str) -> list[str]:
    """Spezza `text` in blocchi che iniziano a ogni riga che corrisponde a `pattern` (il testo prima del primo e' scartato)."""
    return [p for p in re.split(rf"(?m)^(?={pattern})", text) if p.startswith("#")]


def prune_resets(zone_chunk: str, rooms: set[int], mobs: set[int], objects: set[int]) -> str:
    """Toglie da una zona i comandi che puntano a vnum fuori dal mondo sintetico (e i G/E/H/F/C/Z del mob scartato);
    commenti, `O` con 4 numeri e ogni altra riga restano come nei dati reali."""
    out: list[str] = []
    mob_ok = True
    for line in zone_chunk.splitlines(keepends=True):
        t = line.split()
        if len(t) < 3 or t[0] not in "MCOPGEDHFZ" or len(t[0]) != 1:
            out.append(line)
            continue
        n = [int(x) for x in t[1:] if re.fullmatch(r"-?\d+", x)]
        if t[0] == "M":
            mob_ok = n[1] in mobs and n[3] in rooms
            keep = mob_ok
        elif t[0] == "O":
            keep = n[1] in objects and n[3] in rooms
        elif t[0] == "P":
            keep = n[1] in objects and n[3] in objects
        elif t[0] in "GE":
            keep = mob_ok and n[1] in objects
        elif t[0] == "D":
            keep = n[1] in rooms
        else:
            keep = mob_ok  # C, H, F, Z seguono il mob corrente
        if keep:
            out.append(line)
    return "".join(out)


def dikumod_text(name: str) -> str:
    """Un file reale di Diku Modificato come testo (latin-1: round trip esatto)."""
    real = PREFIX + name[len("dikumoddata") :]  # i file reali usano `DIKUMOD_PREFIX`
    assert DIKUMOD_LIB is not None
    return (DIKUMOD_LIB / real).read_text(encoding="latin-1")


def build_dikumod_world(dest: Path) -> dict[str, int]:
    """Scrive in `dest` un mondo `dikumoddata.*` con i record reali di Diku Modificato dentro le prime `DIKUMOD_ZONES` zone.

    Restituisce i conteggi `{zones, rooms, mobs, objects, shops, top}`.
    """
    from pachimudeditor_adapter_mapping.grammar import parse_document
    from pachimudeditor_adapter_mapping.schema import load_mapping

    zone_chunks = chunks(dikumod_text("dikumoddata.zon"), r"#\d+\s*$")[:DIKUMOD_ZONES]
    top = int(re.search(r"(?m)^(\d+) \d+ \d+", zone_chunks[-1]).group(1))  # type: ignore[union-attr]
    vnum = lambda chunk: int(re.match(r"#(\d+)", chunk).group(1))  # noqa: E731
    rooms = [c for c in chunks(dikumod_text("dikumoddata.wld"), r"#\d+\s*$") if vnum(c) <= top]
    mobs = [c for c in chunks(dikumod_text("dikumoddata.mob"), r"#\d+\s*$") if vnum(c) <= top]
    objects = [c for c in chunks(dikumod_text("dikumoddata.obj"), r"#\d+\s*$") if vnum(c) <= top]
    present = ({vnum(c) for c in rooms}, {vnum(c) for c in mobs}, {vnum(c) for c in objects})
    zone_chunks = [prune_resets(c, *present) for c in zone_chunks]
    spec = load_mapping(DIKU_MAPPING)
    shops: list[str] = []
    for chunk in chunks(dikumod_text("dikumoddata.shp"), r"#\d+~\s*$"):
        try:
            doc = parse_document(spec, "shp", chunk + "$~\n")
        except ValueError:
            continue  # negozio troncato dei dati reali: non entra nel mondo sintetico
        if doc.sections[0].records and len(shops) < 5:
            shops.append(chunk)  # i primi negozi leggibili (i keeper sono mob di altre zone: qui non si controlla)
    dest.mkdir(parents=True, exist_ok=True)
    files = {
        "dikumoddata.zon": "".join(zone_chunks) + "#9999999\n$~\n",
        "dikumoddata.wld": "".join(rooms),
        "dikumoddata.mob": "".join(mobs) + "%%~\n",
        "dikumoddata.obj": "".join(objects) + "%%~\n",
        "dikumoddata.shp": "".join(shops) + "$~\n",
    }
    for name, text in files.items():
        (dest / name).write_bytes(text.encode("latin-1"))
    return {"zones": len(zone_chunks), "rooms": len(rooms), "mobs": len(mobs), "objects": len(objects), "shops": len(shops), "top": top}
