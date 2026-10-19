"""Accesso OPZIONALE a un checkout del MUD pachimud, solo per i test di allineamento (`tests/test_game_compat.py`).

Il MUD non e' una dipendenza: i modelli sono copiati nell'adapter (`game_models`) e la suite gira senza gioco. Se la
variabile `PACHIMUD_GAME_ROOT` punta a un checkout (cartella con `src/pachimud` o `pachimud`) i test di confronto
carichino il pacchetto vero per verificare che la copia non sia in ritardo; altrimenti vengono saltati.
Le dipendenze del MUD (pydantic, telnetlib3...) devono essere importabili (es. `PYTHONPATH` sul `site-packages` del suo venv).
Il caricamento e' dinamico (nome del modulo composto a runtime): nessun `import` statico del MUD nel repo.
"""

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType

ENV_VAR = "PACHIMUD_GAME_ROOT"
PACKAGE = "pachimud"


def game_root() -> Path | None:
    """La radice del checkout del MUD se `PACHIMUD_GAME_ROOT` e' impostata e valida, altrimenti `None`."""
    value = os.environ.get(ENV_VAR)
    if not value:
        return None
    root = Path(value).expanduser().resolve()
    return root if (root / "src" / PACKAGE).is_dir() or (root / PACKAGE).is_dir() else None


def load(submodule: str = "") -> ModuleType:
    """Importa `pachimud[.submodule]` dal checkout (aggiunge il suo `src` a `sys.path`)."""
    root = game_root()
    if root is None:
        raise RuntimeError(f"{ENV_VAR} non impostata o non valida")
    src = str(root / "src" if (root / "src" / PACKAGE).is_dir() else root)
    if src not in sys.path:
        sys.path.insert(0, src)
    return importlib.import_module(f"{PACKAGE}.{submodule}" if submodule else PACKAGE)
