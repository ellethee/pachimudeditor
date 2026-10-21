"""Dati reali locali (fuori repo) e marcatori per i test che li richiedono davvero.

I test normali girano su mondi sintetici (`tests/support/synthetic_worlds.py`) quando i dati reali mancano; quelli che
asseriscono su contenuti precisi dei dati reali sono marcati `real_rom` / `real_dikumod` e si saltano se mancano.

Variabili d'ambiente:

- `BASEDMUD_AREA_DIR` (alias `ROM_AREA_DIR`): cartella `area/` di basedmud (default: `../basedmud/area` accanto al repo);
- `DIKUMOD_LIB`: cartella `lib/` dei dati reali di Diku Modificato (DikuMod1, "leu"); default `/dati/luca/muds/leu/lib` se esiste;
- `DIKUMOD_PREFIX`: prefisso dei file dati (`<prefisso>.wld`, ...); default `leudata` se i file di `leu` esistono, altrimenti `dikumoddata`;
- `DIKUMOD_SRC`: radice del progetto (Makefile, `src/`, `lib/`), usata solo da `tests/live`; default `/dati/luca/muds/leu`.
"""

import os
from pathlib import Path

ROM_AREA = Path(
    os.environ.get("BASEDMUD_AREA_DIR") or os.environ.get("ROM_AREA_DIR") or Path(__file__).resolve().parents[3] / "basedmud" / "area"
)
"""Cartella `area/` reale di basedmud (sola lettura)."""
HAVE_ROM = ROM_AREA.is_dir()
LEU_ROOT = Path("/dati/luca/muds/leu")
"""Cartella ufficiale dei sorgenti e dei dati di Diku Modificato (solo DikuMod1)."""
DIKUMOD_SRC = Path(os.environ.get("DIKUMOD_SRC") or LEU_ROOT)
"""Radice del progetto Diku Modificato (`DIKUMOD_SRC`)."""
DIKUMOD_LIB = Path(os.environ.get("DIKUMOD_LIB") or LEU_ROOT / "lib")
"""Cartella `lib/` reale (sola lettura): `DIKUMOD_LIB`, altrimenti quella di `leu`."""
DIKUMOD_PREFIX = os.environ.get("DIKUMOD_PREFIX") or ("leudata" if (DIKUMOD_LIB / "leudata.wld").is_file() else "dikumoddata")
"""Prefisso dei file dati reali (`DIKUMOD_PREFIX`)."""
HAVE_DIKUMOD = (DIKUMOD_LIB / f"{DIKUMOD_PREFIX}.wld").is_file()

MARKERS = {
    "real_rom": (HAVE_ROM, f"aree reali di basedmud non trovate in {ROM_AREA} (BASEDMUD_AREA_DIR)"),
    "real_dikumod": (HAVE_DIKUMOD, f"dati reali Diku Modificato non trovati in {DIKUMOD_LIB} (DIKUMOD_LIB, DIKUMOD_PREFIX)"),
}
"""Marcatore -> (dati presenti, motivo dello skip)."""
