"""Fixture dei test dell'adapter Diku Modificato: copie temporanee dei dati reali (dikumod e dikumod2), originali mai scritti."""

from collections.abc import Callable
from pathlib import Path

import pytest

from pachimudeditor_adapter_dikumod.adapter import DikumodAdapter
from pachimudeditor.common.adapters.registry import WorldConfig
from tests.dikumod_lib.conftest import (  # noqa: F401  (fixture condivise: guardia sugli hash degli originali, copie)
    VARIANTS,
    _originals_untouched,
    copy_lib,
    lib,
    make_lib,
    variant,
)

MOB_SPEC = {"dikumod": (2093, 33), "dikumod2": (2097, 33)}
"""(mob interpretati, mob corrotti) attesi sui dati locali (vedi `docs/formats/dikumod.md`)."""
SPEC = {
    "dikumod": {"rooms": 3841, "mobs": 2093 + 33, "objects": 2025, "zones": 93},
    "dikumod2": {"rooms": 3856, "mobs": 2097 + 33, "objects": 2041, "zones": 93},
}
DUPLICATES = {"dikumod": {"rooms": 1, "mobs": 4, "objects": 3}, "dikumod2": {"rooms": 1, "mobs": 4, "objects": 3}}
"""Vnum ripetuti nei file (stanza 6542, mob 3703 16053 19208 21356, oggetti 16056 16207 21361): l'API ne mostra uno solo."""


@pytest.fixture
def make_adapter(lib: Path, variant: str) -> Callable[..., DikumodAdapter]:
    """Factory di adapter sulla copia; senza argomenti e' **in sola lettura** (il default del kind)."""

    def build(**config: object) -> DikumodAdapter:
        """Un adapter nuovo (cache vuota) sulla copia; `read_only=False` per scrivere."""
        return DikumodAdapter(
            WorldConfig(id="dikumod", kind="dikumod", name="Diku Modificato", path=str(lib), params={"variant": variant}, **config)
        )  # type: ignore[arg-type]

    return build


@pytest.fixture
def ro(make_adapter: Callable[..., DikumodAdapter]) -> DikumodAdapter:
    """Adapter con la configurazione di default (sola lettura)."""
    return make_adapter()


@pytest.fixture
def rw(make_adapter: Callable[..., DikumodAdapter]) -> DikumodAdapter:
    """Adapter scrivibile (`read_only: false` esplicito)."""
    return make_adapter(read_only=False)
