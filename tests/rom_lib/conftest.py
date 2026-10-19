"""Fixture dei test della libreria `.are`: indipendenti dallo stack applicativo (niente DB di gioco)."""

import hashlib
import shutil
from pathlib import Path

import pytest

from tests.support.real_data import ROM_AREA as AREA_DIR  # aree reali (BASEDMUD_AREA_DIR), sola lettura: si lavora su copie
from tests.support.synthetic_worlds import write_rom_area


@pytest.fixture(scope="session", autouse=True)
def _guard_real_db() -> None:
    """Override: la libreria non usa database."""


@pytest.fixture(autouse=True)
def game_db() -> None:
    """Override: nessun database di gioco da seminare per questi test."""


def _digest(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}


@pytest.fixture(scope="session")
def real_area_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copia temporanea delle aree reali (area.lst, *.are, olc.hlp), o le aree sintetiche se mancano; a fine sessione l'originale e' intatto."""
    dest = tmp_path_factory.mktemp("rom_area")
    if not AREA_DIR.is_dir():
        yield write_rom_area(dest)
        return
    before = _digest(AREA_DIR)
    for p in AREA_DIR.iterdir():
        if p.is_file() and (p.suffix in (".are", ".hlp") or p.name == "area.lst"):
            shutil.copy2(p, dest / p.name)
    yield dest
    assert _digest(AREA_DIR) == before, "le aree originali di basedmud non devono essere modificate"
