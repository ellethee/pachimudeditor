"""Avvio dei mondi senza il pacchetto `pachimud`: moduli opzionali, mondo pachimud funzionante, nessun import del gioco."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pachimudeditor.modules import build_modules
from tests.support import mapping_worlds as worlds
from tests.support import stack

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CHILD = PACKAGE_ROOT / "tests" / "support" / "isolated_child.py"


def run_child(mode: str, **args: object) -> subprocess.CompletedProcess[str]:
    """Esegue il figlio isolato (`python -I`, pachimud nascosto) e ne restituisce l'esito."""
    payload = json.dumps({"repo": str(PACKAGE_ROOT), **args})
    return subprocess.run([sys.executable, "-I", str(CHILD), mode, payload], capture_output=True, text=True, timeout=120, cwd=PACKAGE_ROOT)


def test_optional_modules_only_with_pachimud_world() -> None:
    """Senza mondo pachimud i moduli world/players/instances/transfer/content non sono registrati."""
    names = {m.name for m in build_modules(["basedmud", "dikumod", "mapping"])}
    optional = {"world", "players", "instances", "transfer", "content"}
    assert not names & optional and {"zones", "rooms", "convert"} <= names
    assert optional <= {m.name for m in build_modules(["pachimud"])}


# ------------------------------------------------------------------ processo senza pachimud


def test_mapping_world_runs_without_pachimud(tmp_path: Path) -> None:
    """Avvio e uso di un mondo non-pachimud con `pachimud` NON importabile; le rotte opzionali sono 404."""
    if not worlds.ROM_AREA.is_dir():
        pytest.skip("aree basedmud non trovate")
    area = worlds.copy_rom_area(tmp_path / "area")
    based = tmp_path / "based"
    shutil.copytree(area, based / "area")
    (based / "src").mkdir()
    shutil.copy(worlds.ROM_AREA.parent / "src" / "tables.c", based / "src" / "tables.c")
    config = [{"id": "rom", "kind": "mapping", "mapping": str(worlds.ROM_MAPPING), "path": str(area), "read_only": True}]
    result = run_child("serve", workdir=str(tmp_path / "w"), worlds=config)
    assert result.returncode == 0 and "OK zones=" in result.stdout, result.stdout + result.stderr
    config = [{"id": "bm", "kind": "basedmud", "path": str(based / "area"), "read_only": True}]
    result = run_child("serve", workdir=str(tmp_path / "w2"), worlds=config)
    assert result.returncode == 0 and "OK zones=" in result.stdout, result.stdout + result.stderr


def test_pachimud_world_params_without_game(tmp_path: Path) -> None:
    """Un mondo pachimud con `database_url` e' accettato senza il gioco; senza parametri l'errore e' chiaro."""
    ok = [{"id": "p", "kind": "pachimud", "params": {"database_url": f"sqlite+aiosqlite:///{tmp_path}/g.db"}}]
    result = run_child("setup", worlds=ok)
    assert result.returncode == 0 and result.stdout.strip() == "OK ['p'] None", result.stdout + result.stderr
    result = run_child("setup", worlds=[{"id": "p", "kind": "pachimud"}])
    assert result.returncode == 0 and result.stdout.startswith("ERR Mondo 'p'") and "database_url" in result.stdout, result.stdout


def test_pachimud_world_runs_without_pachimud_package(tmp_path: Path) -> None:
    """L'app completa con un mondo pachimud funziona con il pacchetto `pachimud` BLOCCATO (python -I + meta_path),
    su un DB di gioco preesistente (qui: schema e dati di test, in una cartella temporanea)."""
    workdir = tmp_path / "w"
    workdir.mkdir()
    stack.seed_game_db(workdir)
    result = run_child("pachimud", workdir=str(workdir))
    assert result.returncode == 0 and "OK pachimud-world" in result.stdout, result.stdout + result.stderr
