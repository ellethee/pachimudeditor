"""Fixture dei test della libreria Diku Modificato: copie temporanee dei dati reali; gli originali non si toccano mai."""

import hashlib
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.support import real_data
from tests.support.synthetic_worlds import write_dikumod_world

# Senza dati reali la cartella non esiste e `copy_lib` ripiega sul mondo sintetico.
LIB = real_data.DIKUMOD_LIB
"""Cartella `lib/` reale di Diku Modificato (sola lettura): `DIKUMOD_LIB`, default `/dati/luca/muds/leu/lib`."""
PREFIX = real_data.DIKUMOD_PREFIX
"""Prefisso dei file dati reali (`DIKUMOD_PREFIX`): nelle copie di lavoro i file diventano `dikumoddata.*`."""
_COPIED = ("dikumoddata.wld", "dikumoddata.mob", "dikumoddata.obj", "dikumoddata.zon", "dikumoddata.shp", "scripts.dat", "dikumoddata.gui")
_COPIED_DIRS = ("rooms", "objects", "zones", "scripts", "gilde")
_HASHED_ONLY_DIRS = ("players", "rent")
"""Giocatori e rent reali: non si copiano mai nelle copie di lavoro (hanno hash di password), ma l'hash a fine sessione li protegge."""


def real_name(name: str) -> str:
    """Il nome del file nei dati reali: `dikumoddata.<ext>` diventa `<DIKUMOD_PREFIX>.<ext>`."""
    return PREFIX + name[len("dikumoddata") :] if name.startswith("dikumoddata") else name


def digest(lib: Path) -> dict[str, str]:
    """SHA-256 dei file che i test copiano (dati principali e cartelle per-vnum)."""
    out: dict[str, str] = {}
    if not lib.is_dir():
        return out
    for name in _COPIED:
        if (lib / real_name(name)).is_file():
            out[name] = hashlib.sha256((lib / real_name(name)).read_bytes()).hexdigest()
    for d in (*_COPIED_DIRS, *_HASHED_ONLY_DIRS):
        for p in sorted((lib / d).glob("*")) if (lib / d).is_dir() else []:
            if p.is_file():
                out[f"{d}/{p.name}"] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture(scope="session", autouse=True)
def _originals_untouched() -> Iterator[None]:
    """A fine sessione i dati originali di Diku Modificato devono avere gli stessi hash di prima."""
    before = digest(LIB)
    yield
    after = digest(LIB)
    assert after == before, "i dati originali di Diku Modificato non devono essere modificati"


def copy_lib(dest: Path) -> Path:
    """Copia i dati reali in `dest/lib` e restituisce il percorso (mondo sintetico se mancano gli originali)."""
    src = LIB
    out = dest / "lib"
    if not (src / real_name("dikumoddata.wld")).is_file():
        return write_dikumod_world(out)
    out.mkdir(parents=True)
    for name in _COPIED:
        if (src / real_name(name)).is_file():
            shutil.copy2(src / real_name(name), out / name)
    for d in _COPIED_DIRS:
        if (src / d).is_dir():
            shutil.copytree(src / d, out / d)
    return out


@pytest.fixture
def lib(tmp_path: Path) -> Path:
    """Copia temporanea scrivibile della cartella `lib/` reale."""
    return copy_lib(tmp_path)
