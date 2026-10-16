"""Logica di `scripts/release_check.py` (tag -> pacchetto/versione, classificatore Private, contenuto del wheel)."""

import importlib.util
import zipfile
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("release_check", Path(__file__).parents[2] / "scripts" / "release_check.py")
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)


def _pkg(root: Path, name: str, version: str, private: bool) -> None:
    d = root if name == rc.CORE else root / "adapters" / name.removeprefix("pachimudeditor-adapter-")
    d.mkdir(parents=True, exist_ok=True)
    cls = '["Private :: Do Not Upload"]' if private else "[]"
    (d / "pyproject.toml").write_text(f'[project]\nname = "{name}"\nversion = "{version}"\nclassifiers = {cls}\n')


@pytest.mark.parametrize(
    "tag,expected",
    [
        ("pachimudeditor-v0.1.0", ("pachimudeditor", "0.1.0")),
        ("refs/tags/pachimudeditor-adapter-dikumod-v12.3.45", ("pachimudeditor-adapter-dikumod", "12.3.45")),
    ],
)
def test_parse_tag_ok(tag, expected):
    assert rc.parse_tag(tag) == expected


@pytest.mark.parametrize(
    "tag",
    ["v0.1.0", "pachimudeditor-0.1.0", "pachimudeditor-v1.0", "other-v1.0.0", "pachimudeditor-adapter-v1.0.0", "pachimudeditor-v1.0.0rc1"],
)
def test_parse_tag_invalid(tag):
    with pytest.raises(rc.ReleaseError):
        rc.parse_tag(tag)


def test_check_release(tmp_path):
    _pkg(tmp_path, "pachimudeditor-adapter-dikumod", "0.2.0", private=False)
    assert rc.check_release("pachimudeditor-adapter-dikumod", "0.2.0", tmp_path) == "0.2.0"
    with pytest.raises(rc.ReleaseError, match="versione"):
        rc.check_release("pachimudeditor-adapter-dikumod", "0.3.0", tmp_path)
    _pkg(tmp_path, "pachimudeditor-adapter-dikumod", "0.2.0", private=True)
    with pytest.raises(rc.ReleaseError, match="Private"):
        rc.check_release("pachimudeditor-adapter-dikumod", "0.2.0", tmp_path)
    with pytest.raises(rc.ReleaseError, match="sconosciuto"):
        rc.check_release("pachimudeditor-adapter-nope", None, tmp_path)


def test_check_dist_core_needs_spa(tmp_path):
    _pkg(tmp_path, "pachimudeditor", "0.1.0", private=False)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "pachimudeditor-0.1.0.tar.gz").write_bytes(b"")
    whl = dist / "pachimudeditor-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(whl, "w") as z:
        z.writestr("pachimudeditor/__init__.py", "")
    with pytest.raises(rc.ReleaseError, match="index.html"):
        rc.check_dist("pachimudeditor", dist, tmp_path)
    with zipfile.ZipFile(whl, "w") as z:
        z.writestr("pachimudeditor/static/index.html", "")
    rc.check_dist("pachimudeditor", dist, tmp_path)


def test_real_repo_tags_match_pyprojects():
    """I 5 pacchetti reali sono riconosciuti e la versione del pyproject e' leggibile (il Private puo' esserci ancora)."""
    for name in ["pachimudeditor", *(f"pachimudeditor-adapter-{k}" for k in ("pachimud", "basedmud", "dikumod", "mapping"))]:
        assert rc.load_project(name)["name"] == name
