"""Dati reali locali (fuori repo) e marcatori per i test che li richiedono davvero.

I test normali girano su mondi sintetici (`tests/support/synthetic_worlds.py`) quando i dati reali mancano; quelli che
asseriscono su contenuti precisi dei dati reali sono marcati `real_rom` / `real_dikumod` e si saltano se mancano.

Variabili d'ambiente:

- `BASEDMUD_AREA_DIR` (alias `ROM_AREA_DIR`): cartella `area/` di basedmud (default: `../basedmud/area` accanto al repo);
- `DIKUMOD_ROOT`: cartella che contiene `dikumod/lib` e `dikumod2/lib`;
- `DIKUMOD_PREFIX`: prefisso dei file dati reali (default `dikumoddata`; i dati locali ne usano un altro).
"""

import os
from pathlib import Path

ROM_AREA = Path(
    os.environ.get("BASEDMUD_AREA_DIR") or os.environ.get("ROM_AREA_DIR") or Path(__file__).resolve().parents[3] / "basedmud" / "area"
)
"""Cartella `area/` reale di basedmud (sola lettura)."""
HAVE_ROM = ROM_AREA.is_dir()
DIKUMOD_ROOT = Path(os.environ["DIKUMOD_ROOT"]) if os.environ.get("DIKUMOD_ROOT") else None
"""Radice dei dati reali Diku Modificato (`DIKUMOD_ROOT`), `None` se non impostata."""
DIKUMOD_PREFIX = os.environ.get("DIKUMOD_PREFIX") or "dikumoddata"
HAVE_DIKUMOD = DIKUMOD_ROOT is not None and (DIKUMOD_ROOT / "dikumod2" / "lib").is_dir()

MARKERS = {
    "real_rom": (HAVE_ROM, f"aree reali di basedmud non trovate in {ROM_AREA} (BASEDMUD_AREA_DIR)"),
    "real_dikumod": (HAVE_DIKUMOD, "dati reali Diku Modificato non trovati (DIKUMOD_ROOT, DIKUMOD_PREFIX)"),
}
"""Marcatore -> (dati presenti, motivo dello skip)."""
