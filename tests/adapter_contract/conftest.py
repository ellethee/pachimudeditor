"""Fixture della suite di contratto: `adapter` parametrizzata sugli adapter da verificare.

Per aggiungere un adapter (es. BasedMud) basta registrare una factory in `ADAPTER_FACTORIES`: ogni test del
pacchetto verra' eseguito anche su di esso. La factory restituisce un adapter su un mondo **pulito e
scrivibile** (per pachimud il DB temporaneo seminato di `tests/stack_fixtures.py`; per un adapter su file una
cartella temporanea copiata da una fixture). La suite non assume dati preesistenti: crea tutto dall'interfaccia.
"""

import atexit
import shutil
import tempfile
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
import pytest_asyncio

from pachimudeditor.common.adapters.base import WorldAdapter
from pachimudeditor.common.adapters.registry import WorldConfig
from tests.support import real_data
from tests.support.synthetic_worlds import write_rom_area


def _pachimud() -> WorldAdapter:
    """Adapter pachimud sul database di gioco temporaneo."""
    from pachimudeditor_adapter_pachimud.adapter import PachimudAdapter

    from tests.support import stack

    return PachimudAdapter(WorldConfig(id="contract", kind="pachimud", name="Contract", params=stack.current_params()))


def _basedmud() -> WorldAdapter:
    """Adapter BasedMud su una cartella `area/` nuova con il solo `area.lst` (mondo vuoto e scrivibile)."""
    from pachimudeditor_adapter_basedmud.adapter import BasedMudAdapter

    root = Path(tempfile.mkdtemp(prefix="basedmud-contract-"))
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    (root / "area").mkdir()
    (root / "area" / "area.lst").write_text("$\n")
    return BasedMudAdapter(WorldConfig(id="contract", kind="basedmud", name="Contract", path=str(root)))


def _dikumod() -> WorldAdapter:
    """Adapter Diku Modificato su un mondo minuscolo e scrivibile (campioni di record reali, vedi `tests/dikumod/synthetic.py`)."""
    from pachimudeditor_adapter_dikumod.adapter import DikumodAdapter
    from tests.dikumod.synthetic import write_world

    root = Path(tempfile.mkdtemp(prefix="dikumod-contract-"))
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    write_world(root / "lib")
    return DikumodAdapter(WorldConfig(id="contract", kind="dikumod", name="Contract", path=str(root), read_only=False))


ADAPTER_FACTORIES: dict[str, Callable[[], WorldAdapter]] = {"pachimud": _pachimud, "basedmud": _basedmud, "dikumod": _dikumod}
"""Nome -> factory di un adapter scrivibile e pulito. Estendere qui per i nuovi adapter."""


ROM_MAPPING = (
    Path(__file__).resolve().parents[2] / "adapters" / "mapping" / "src" / "pachimudeditor_adapter_mapping" / "examples" / "rom.yaml"
)
"""Mappatura ROM di esempio del `MappingAdapter`."""


def _mapping_adapter(root: Path) -> WorldAdapter:
    """`MappingAdapter` con `rom.yaml` sulla cartella dati `root`."""
    from pachimudeditor_adapter_mapping.adapter import MappingAdapter

    return MappingAdapter(WorldConfig(id="contract", kind="mapping", name="Contract", mapping=str(ROM_MAPPING), path=str(root)))


def _mapping() -> WorldAdapter:
    """`MappingAdapter` (rom.yaml) su una cartella nuova con il solo `area.lst` (mondo vuoto e scrivibile)."""
    root = Path(tempfile.mkdtemp(prefix="mapping-contract-"))
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    (root / "area.lst").write_text("$\n")
    return _mapping_adapter(root)


def _mapping_rom_copy() -> WorldAdapter:
    """`MappingAdapter` (rom.yaml) su una copia temporanea delle aree reali di basedmud, o sintetiche se mancano (la suite crea il suo contenuto)."""
    root = Path(tempfile.mkdtemp(prefix="mapping-contract-rom-"))
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    source = real_data.ROM_AREA
    if not source.is_dir():  # niente dati reali: aree sintetiche
        write_rom_area(root)
        return _mapping_adapter(root)
    for p in source.iterdir():
        if p.is_file() and (p.suffix == ".are" or p.name == "area.lst"):
            shutil.copy2(p, root / p.name)
    return _mapping_adapter(root)


ADAPTER_FACTORIES["mapping"] = _mapping
ADAPTER_FACTORIES["mapping_rom_copy"] = _mapping_rom_copy


@pytest_asyncio.fixture(params=sorted(ADAPTER_FACTORIES))
async def adapter(request: pytest.FixtureRequest) -> AsyncIterator[WorldAdapter]:
    """Un adapter per ogni voce di `ADAPTER_FACTORIES` (chiuso a fine test)."""
    instance = ADAPTER_FACTORIES[request.param]()
    yield instance
    await instance.close()
