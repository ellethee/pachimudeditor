"""Fixture dei test della libreria Diku Modificato: copie temporanee dei dati reali; gli originali non si toccano mai."""

import hashlib
import os
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

# Nessun default: senza `DIKUMOD_ROOT` le cartelle non esistono e i test sui dati reali si saltano.
ROOT = Path(os.environ.get("DIKUMOD_ROOT") or "/DIKUMOD_ROOT-non-impostata")
"""Cartella che contiene `dikumod/lib` e `dikumod2/lib` (sola lettura), da `DIKUMOD_ROOT`."""
PREFIX = os.environ.get("DIKUMOD_PREFIX") or "dikumoddata"
"""Prefisso dei file dati reali (`DIKUMOD_PREFIX`): nelle copie di lavoro i file diventano `dikumoddata.*`."""
VARIANTS = ("dikumod", "dikumod2")
_COPIED = ("dikumoddata.wld", "dikumoddata.mob", "dikumoddata.obj", "dikumoddata.zon", "dikumoddata.shp", "scripts.dat", "dikumoddata.gui")
_COPIED_DIRS = ("rooms", "objects", "zones", "scripts", "gilde")


def lib_of(variant: str) -> Path:
    """`<ROOT>/<variant>/lib`."""
    return ROOT / variant / "lib"


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
    for d in _COPIED_DIRS:
        for p in sorted((lib / d).glob("*")) if (lib / d).is_dir() else []:
            if p.is_file():
                out[f"{d}/{p.name}"] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture(scope="session", autouse=True)
def _originals_untouched() -> Iterator[None]:
    """A fine sessione i dati originali di dikumod e dikumod2 devono avere gli stessi hash di prima."""
    before = {v: digest(lib_of(v)) for v in VARIANTS}
    yield
    after = {v: digest(lib_of(v)) for v in VARIANTS}
    assert after == before, "i dati originali di Diku Modificato non devono essere modificati"


def copy_lib(variant: str, dest: Path) -> Path:
    """Copia i dati di `variant` in `dest/lib` e restituisce il percorso (salta se mancano gli originali)."""
    src = lib_of(variant)
    if not (src / real_name("dikumoddata.wld")).is_file():
        pytest.skip(f"dati Diku Modificato {variant} non trovati in {src}")
    out = dest / "lib"
    out.mkdir(parents=True)
    for name in _COPIED:
        if (src / real_name(name)).is_file():
            shutil.copy2(src / real_name(name), out / name)
    for d in _COPIED_DIRS:
        if (src / d).is_dir():
            shutil.copytree(src / d, out / d)
    return out


@pytest.fixture(params=VARIANTS)
def variant(request: pytest.FixtureRequest) -> str:
    """`dikumod` e `dikumod2`."""
    return request.param


@pytest.fixture
def lib(variant: str, tmp_path: Path) -> Path:
    """Copia temporanea scrivibile della cartella `lib/` della variante."""
    return copy_lib(variant, tmp_path)


@pytest.fixture
def make_lib(tmp_path: Path) -> Callable[[str], Path]:
    """Factory: copia temporanea di una variante scelta."""
    counter = iter(range(100))

    def build(name: str) -> Path:
        """Copia `name` in una sottocartella nuova."""
        return copy_lib(name, tmp_path / f"w{next(counter)}")

    return build
