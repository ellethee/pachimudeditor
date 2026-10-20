"""`pachimudeditor.sdk.atomic_write_bytes`: symlink, permessi, pulizia del temporaneo."""

import os
import stat
from pathlib import Path

import pytest

from pachimudeditor.sdk import SDK_VERSION, atomic_write_bytes


def test_sdk_version_exposes_helper() -> None:
    """L'helper e' un'aggiunta compatibile: SDK 1.2."""
    assert SDK_VERSION == "1.2"


def test_symlink_stays_a_symlink_and_target_changes(tmp_path: Path) -> None:
    """Scrivere su un symlink aggiorna il file reale e lascia il link."""
    real = tmp_path / "real" / "a.are"
    real.parent.mkdir()
    real.write_bytes(b"old")
    link = tmp_path / "link.are"
    link.symlink_to(real)
    atomic_write_bytes(link, b"new")
    assert link.is_symlink() and os.readlink(link) == str(real)
    assert real.read_bytes() == b"new" and link.read_bytes() == b"new"
    assert sorted(p.name for p in real.parent.iterdir()) == ["a.are"]


@pytest.mark.parametrize("mode", [0o600, 0o664, 0o755])
def test_permissions_are_preserved(tmp_path: Path, mode: int) -> None:
    """I permessi del file esistente sopravvivono alla riscrittura; un file nuovo e' 0644."""
    path = tmp_path / "f"
    path.write_bytes(b"x")
    path.chmod(mode)
    atomic_write_bytes(path, b"y")
    assert stat.S_IMODE(path.stat().st_mode) == mode
    fresh = tmp_path / "new"
    atomic_write_bytes(fresh, b"z")
    assert stat.S_IMODE(fresh.stat().st_mode) == 0o644


def test_error_leaves_no_temp_and_original_intact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Se il replace fallisce il temporaneo e' rimosso e il file originale e' intatto."""
    path = tmp_path / "f"
    path.write_bytes(b"old")

    def boom(*_: object) -> None:
        raise OSError("replace fallito")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="replace fallito"):
        atomic_write_bytes(path, b"new")
    assert path.read_bytes() == b"old" and [p.name for p in tmp_path.iterdir()] == ["f"]
