"""Fixture dei test dell'adapter BasedMud: copie temporanee delle aree reali, mai scrittura sull'originale."""

import hashlib
import os
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pachimudeditor_adapter_basedmud.adapter import BasedMudAdapter
from pachimudeditor.common.adapters.registry import WorldConfig

AREA_DIR = Path(os.environ.get("BASEDMUD_AREA_DIR", str(Path(__file__).resolve().parents[3] / "basedmud" / "area")))
"""Cartella `area/` reale di basedmud: sola lettura, si lavora su copie."""


def digest(folder: Path) -> dict[str, str]:
    """SHA-256 di ogni file della cartella."""
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}


@pytest.fixture(scope="session", autouse=True)
def _original_untouched() -> Iterator[None]:
    """A fine sessione l'originale `basedmud/area` deve avere gli stessi hash di prima."""
    if not AREA_DIR.is_dir():
        yield
        return
    before = digest(AREA_DIR)
    yield
    assert digest(AREA_DIR) == before, "le aree originali di basedmud non devono essere modificate"


@pytest.fixture
def area_dir(tmp_path: Path) -> Path:
    """Copia temporanea di `area/` (aree, `area.lst`, `olc.hlp`) piu' un `src/tables.c` minimo per razze e classi."""
    if not AREA_DIR.is_dir():
        pytest.skip(f"aree basedmud non trovate in {AREA_DIR}")
    dest = tmp_path / "root" / "area"
    dest.mkdir(parents=True)
    for p in AREA_DIR.iterdir():
        if p.is_file() and (p.suffix in (".are", ".hlp") or p.name == "area.lst"):
            shutil.copy2(p, dest / p.name)
    return dest


@pytest.fixture
def make_adapter(area_dir: Path) -> Callable[..., BasedMudAdapter]:
    """Factory di adapter sulla copia (`read_only` opzionale)."""

    def build(read_only: bool = False) -> BasedMudAdapter:
        """Un adapter nuovo (cache vuota) sulla copia."""
        return BasedMudAdapter(WorldConfig(id="basedmud", kind="basedmud", name="BasedMud", path=str(area_dir), read_only=read_only))

    return build


@pytest.fixture
def adapter(make_adapter: Callable[..., BasedMudAdapter]) -> BasedMudAdapter:
    """Adapter scrivibile sulla copia."""
    return make_adapter()
