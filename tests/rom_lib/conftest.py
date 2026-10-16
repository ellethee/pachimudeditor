"""Fixture dei test della libreria `.are`: indipendenti dallo stack applicativo (niente DB di gioco)."""

import hashlib
import os
import shutil
from pathlib import Path

import pytest

#: Cartella delle aree reali di basedmud (override con ROM_AREA_DIR). Sola lettura: si lavora su copie.
AREA_DIR = Path(os.environ.get("ROM_AREA_DIR", str(Path(__file__).resolve().parents[3] / "basedmud" / "area")))


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
    """Copia temporanea delle aree reali (area.lst, *.are, olc.hlp); verifica a fine sessione che l'originale sia intatto."""
    if not AREA_DIR.is_dir():
        pytest.skip(f"aree basedmud non trovate in {AREA_DIR}")
    before = _digest(AREA_DIR)
    dest = tmp_path_factory.mktemp("rom_area")
    for p in AREA_DIR.iterdir():
        if p.is_file() and (p.suffix in (".are", ".hlp") or p.name == "area.lst"):
            shutil.copy2(p, dest / p.name)
    yield dest
    assert _digest(AREA_DIR) == before, "le aree originali di basedmud non devono essere modificate"
