"""Modulo C: il parser JSON si compila da solo e regge il fuzz (richiede g++, altrimenti salta)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[2] / "adapters" / "dikumod" / "mud-module"


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ non trovato")
def test_json_parser_fuzz(tmp_path: Path) -> None:
    """Compila `livectl_json.c` con ASan+UBSan (`-std=gnu++98`, come il gioco) ed esegue il fuzz semplice."""
    exe = tmp_path / "fuzz_json"
    build = subprocess.run(
        ["g++", "-std=gnu++98", "-O1", "-g", "-Wall", "-Werror", "-fsanitize=address,undefined", "-fno-sanitize-recover=undefined", f"-I{MODULE}",
         str(MODULE / "fuzz" / "fuzz_json.c"), str(MODULE / "livectl_json.c"), "-o", str(exe)],
        capture_output=True, text=True,
    )  # fmt: skip
    assert build.returncode == 0, build.stderr
    run = subprocess.run([str(exe), "100000", "7"], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr
    assert "nessun crash" in run.stdout
