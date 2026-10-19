"""Fixture dei test di conversione: mondi su copie temporanee (mai scrittura sugli originali)."""

import hashlib
import shutil
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
import pytest_asyncio

from pachimudeditor_adapter_basedmud.adapter import BasedMudAdapter
from pachimudeditor_adapter_dikumod.adapter import DikumodAdapter
from pachimudeditor_adapter_pachimud.adapter import PachimudAdapter
from pachimudeditor.common.adapters.registry import WorldConfig
from tests.basedmud.conftest import AREA_DIR
from tests.support import stack
from tests.support.synthetic_worlds import write_rom_area
from tests.dikumod_lib.conftest import (  # noqa: F401  (fixture condivise: guardia sugli hash degli originali, copie)
    VARIANTS,
    _originals_untouched,
    copy_lib,
)

AREAS = ("midgaard.are", "school.are", "haon.are")
"""Le aree reali di basedmud copiate nei test (piccole, con reset, porte, negozi)."""


def tree_digest(folder: Path) -> dict[str, str]:
    """SHA-256 di ogni file (ricorsivo) della cartella."""
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob("*")) if p.is_file()}


@pytest.fixture(scope="session", autouse=True)
def _originals_basedmud_untouched():  # type: ignore[no-untyped-def]
    """A fine sessione le aree originali di basedmud devono avere gli stessi hash di prima."""
    if not AREA_DIR.is_dir():
        yield
        return
    before = tree_digest(AREA_DIR)
    yield
    assert tree_digest(AREA_DIR) == before, "le aree originali di basedmud non devono essere modificate"


def make_rom_dir(dest: Path, areas: tuple[str, ...] = AREAS) -> Path:
    """Una cartella `area/` ROM con solo `areas` copiate da basedmud e un `area.lst` che le elenca (aree sintetiche se mancano)."""
    if not AREA_DIR.is_dir():
        return write_rom_area(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for name in areas:
        shutil.copy2(AREA_DIR / name, dest / name)
    (dest / "area.lst").write_text("\n".join(areas) + "\n$\n")
    return dest


@pytest.fixture
def rom_world(tmp_path: Path) -> Callable[..., BasedMudAdapter]:
    """Factory di mondo BasedMud su una copia ridotta (`read_only` opzionale)."""
    root = make_rom_dir(tmp_path / "rom" / "area")

    def build(read_only: bool = False, world_id: str = "rom") -> BasedMudAdapter:
        """Un adapter nuovo sulla copia."""
        return BasedMudAdapter(WorldConfig(id=world_id, kind="basedmud", name="ROM", path=str(root), read_only=read_only))

    return build


@pytest.fixture
def empty_rom(tmp_path: Path) -> BasedMudAdapter:
    """Mondo BasedMud vuoto e scrivibile."""
    root = tmp_path / "empty" / "area"
    root.mkdir(parents=True)
    (root / "area.lst").write_text("$\n")
    return BasedMudAdapter(WorldConfig(id="empty-rom", kind="basedmud", name="Vuoto", path=str(root)))


@pytest_asyncio.fixture
async def pachimud_world() -> AsyncIterator[PachimudAdapter]:
    """Mondo pachimud sul DB di gioco temporaneo e seminato dei test (default: due zone)."""
    world = PachimudAdapter(WorldConfig(id="pachimud-t", kind="pachimud", name="Pachimud", params=stack.current_params()))
    yield world
    await world.close()


@pytest.fixture
def dikumod_world(tmp_path: Path) -> Callable[..., DikumodAdapter]:
    """Factory di mondo Diku Modificato (copia dei dati di dikumod2) scrivibile."""
    lib = copy_lib("dikumod2", tmp_path / "dikumod")

    def build(read_only: bool = False, world_id: str = "dikumod") -> DikumodAdapter:
        """Un adapter nuovo sulla copia."""
        return DikumodAdapter(
            WorldConfig(
                id=world_id, kind="dikumod", name="Diku Modificato", path=str(lib), read_only=read_only, params={"variant": "dikumod2"}
            )
        )

    return build
