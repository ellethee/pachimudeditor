"""`params.data_prefix`: prefisso dei file dati configurabile, validato, con errore chiaro quando i file non si trovano."""

from pathlib import Path

import pytest

from pachimudeditor.common.adapters.models import ZonePageParams
from pachimudeditor.common.adapters.registry import WorldConfig
from pachimudeditor_adapter_dikumod.adapter import DikumodAdapter
from pachimudeditor_adapter_dikumod.dikumod_lib import DikumodParseError, load_world, resolve_lib, validate_prefix
from tests.dikumod.synthetic import write_world


def _adapter(path: Path, **params: object) -> DikumodAdapter:
    """Adapter scrivibile su una cartella sintetica."""
    return DikumodAdapter(WorldConfig(id="p", kind="dikumod", path=str(path), read_only=False, params=params))


async def test_custom_prefix_reads_and_writes(tmp_path: Path) -> None:
    """Con `data_prefix` i file `miomondo.*` si leggono e la scrittura resta nei file con quel prefisso."""
    lib = write_world(tmp_path / "lib", "miomondo")
    adapter = _adapter(lib, data_prefix="miomondo")
    zones = await adapter.list_zones(ZonePageParams())
    assert zones.total > 0
    assert sorted(p.name for p in lib.iterdir()) == sorted(f"miomondo.{e}" for e in ("wld", "mob", "obj", "zon", "shp"))
    assert load_world(lib, "miomondo").paths.wld.name == "miomondo.wld"


def test_default_prefix_unchanged(tmp_path: Path) -> None:
    """Senza parametro vale `dikumoddata`."""
    lib = write_world(tmp_path / "lib")
    assert _adapter(lib).store.paths.wld.name == "dikumoddata.wld"


@pytest.mark.parametrize("bad", ["", "a/b", "../x", "a.b", "a b", 3, None])
def test_invalid_prefix_rejected(bad: object, tmp_path: Path) -> None:
    """Solo `[A-Za-z0-9_-]`, niente percorsi."""
    with pytest.raises(ValueError, match="data_prefix"):
        validate_prefix(bad)
    with pytest.raises(ValueError, match="data_prefix"):
        _adapter(write_world(tmp_path / "lib"), data_prefix=bad)


def test_missing_files_give_clear_error(tmp_path: Path) -> None:
    """I file hanno un altro prefisso: l'errore indica il prefisso cercato e il parametro da impostare."""
    lib = write_world(tmp_path / "lib", "altro")
    with pytest.raises(DikumodParseError, match=r"nessun file dikumoddata\.wld in .*imposta params\.data_prefix"):
        resolve_lib(lib)
    with pytest.raises(ValueError, match=r"nessun file dikumoddata\.wld.*params\.data_prefix"):
        _adapter(lib)
    assert _adapter(lib, data_prefix="altro").store.lib == lib.resolve()


def test_describe_exposes_params(tmp_path: Path) -> None:
    """`describe().params` riporta prefisso e variante (informativi)."""
    lib = write_world(tmp_path / "lib", "miomondo")
    info = _adapter(lib, data_prefix="miomondo", variant="dikumod").describe()
    assert info.params == {"variant": "dikumod", "data_prefix": "miomondo"}
