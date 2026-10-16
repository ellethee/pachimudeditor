"""I/O su file: salvataggio atomico, stile newline, area.lst."""

import os
from pathlib import Path

import pytest

from pachimudeditor_adapter_basedmud.rom_lib import (
    RomParseError,
    add_area_to_list,
    load_area_file,
    parse_area_list,
    read_area_list,
    remove_area_from_list,
    save_area_file,
)

from . import samples as S


def test_load_save_roundtrip_and_crlf(tmp_path: Path) -> None:
    p = tmp_path / "t.are"
    data = (S.FULL).replace("\n", "\r\n").encode()
    p.write_bytes(data)
    area = load_area_file(p)
    assert area.newline == "\r\n" and area.filename == "t.are"
    area.find_mobile(100).level = 7
    save_area_file(p, area)
    out = p.read_bytes()
    assert out.endswith(b"#$\r\n") and b"\r\n" in out and b"\n" not in out.replace(b"\r\n", b"")
    assert load_area_file(p).find_mobile(100).level == 7
    assert sorted(x.name for x in tmp_path.iterdir()) == ["t.are"]  # nessun temporaneo residuo


def test_save_preserves_mode_and_unchanged_bytes(tmp_path: Path) -> None:
    p = tmp_path / "t.are"
    p.write_text(S.FULL)
    os.chmod(p, 0o640)
    area = load_area_file(p)
    save_area_file(p, area)
    assert p.read_text() == S.FULL and (p.stat().st_mode & 0o777) == 0o640


def test_latin1_encoding_preserved(tmp_path: Path) -> None:
    p = tmp_path / "t.are"
    raw = S.FULL.replace("A rat scurries.", "Un topo e' qui \xe0.").encode("latin-1")
    p.write_bytes(raw)
    area = load_area_file(p)
    assert area.encoding == "latin-1"
    area.find_mobile(100).level = 3
    save_area_file(p, area)
    assert b"\xe0" in p.read_bytes()


def test_parse_error_has_filename(tmp_path: Path) -> None:
    p = tmp_path / "bad.are"
    p.write_text("#MOBILES\n#1\nname~\n")
    with pytest.raises(RomParseError) as info:
        load_area_file(p)
    assert "bad.are" in str(info.value) and info.value.line >= 3


def test_failed_save_leaves_original(tmp_path: Path) -> None:
    p = tmp_path / "t.are"
    p.write_text(S.FULL)
    area = load_area_file(p)
    area.resets.append(__import__("pachimudeditor_adapter_basedmud.rom_lib", fromlist=["x"]).Reset("M", [1]))
    with pytest.raises(ValueError):
        save_area_file(p, area)
    assert p.read_text() == S.FULL and len(list(tmp_path.iterdir())) == 1


def test_area_list(tmp_path: Path) -> None:
    p = tmp_path / "area.lst"
    p.write_text("social.are\n# commento\nmidgaard.are\n$\n")
    lst = read_area_list(p)
    assert lst.names == ["social.are", "midgaard.are"] and "midgaard.are" in lst
    assert lst.to_text() == p.read_text()
    assert add_area_to_list(p, "nuova.are") is True
    assert add_area_to_list(p, "nuova.are") is False
    assert p.read_text() == "social.are\n# commento\nmidgaard.are\nnuova.are\n$\n"
    assert remove_area_from_list(p, "midgaard.are") is True
    assert remove_area_from_list(p, "midgaard.are") is False
    assert p.read_text() == "social.are\n# commento\nnuova.are\n$\n"
    add_area_to_list(p, "prima.are", index=0)
    assert read_area_list(p).names[0] == "prima.are"
    assert p.read_text().rstrip().endswith("$")


def test_area_list_missing_terminator_and_invalid_names(tmp_path: Path) -> None:
    lst = parse_area_list("a.are\nb.are\n")
    assert lst.to_text() == "a.are\nb.are\n$\n"
    for bad in ("", "a b", "#x", "$"):
        with pytest.raises(ValueError):
            lst.add(bad)
    crlf = parse_area_list("a.are\r\n$\r\n")
    crlf.add("b.are")
    assert crlf.to_text() == "a.are\r\nb.are\r\n$\r\n"
