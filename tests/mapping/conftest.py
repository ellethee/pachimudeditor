"""Fixture dei test del MappingAdapter: indipendenti dallo stack applicativo (niente DB di gioco) e su copie dei dati."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.support import mapping_worlds as worlds


@pytest.fixture(scope="session", autouse=True)
def _guard_real_db() -> None:
    """Override: questi test non usano database."""


@pytest.fixture(autouse=True)
def game_db() -> None:
    """Override: nessun database di gioco da seminare."""


@pytest.fixture(scope="session", autouse=True)
def _originals_untouched() -> Iterator[None]:
    """A fine sessione gli originali (aree ROM e `lib` di Diku Modificato) devono avere gli stessi hash di prima."""
    roots = [p for p in (worlds.ROM_AREA, worlds.DIKUMOD_LIB) if p.is_dir()]
    before = {p: worlds.digest(p) for p in roots}
    yield
    for p in roots:
        assert worlds.digest(p) == before[p], f"{p} non deve essere modificata dai test"


@pytest.fixture
def rom_dir(tmp_path: Path) -> Path:
    """Copia temporanea delle aree reali di basedmud."""
    if not worlds.ROM_AREA.is_dir():
        pytest.skip(f"aree basedmud non trovate in {worlds.ROM_AREA}")
    return worlds.copy_rom_area(tmp_path / "area")


@pytest.fixture
def dikumod_dir(tmp_path: Path) -> Path:
    """Mondo `dikumoddata.*` sintetico con record reali di Diku Modificato."""
    if not worlds.DIKUMOD_LIB.is_dir():
        pytest.skip(f"dati Diku Modificato non trovati in {worlds.DIKUMOD_LIB}")
    root = tmp_path / "lib"
    worlds.build_dikumod_world(root)
    return root
