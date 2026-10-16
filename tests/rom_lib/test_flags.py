"""Test dei flag ROM (fread_flag / fwrite_flag)."""

import pytest

from pachimudeditor_adapter_basedmud.rom_lib import (
    flag_names,
    flags_to_letters,
    format_flags,
    has_flag,
    letters_to_flags,
    names_to_flags,
    parse_flags,
    set_flag,
)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("0", 0),
        ("A", 1),
        ("ABV", 1 | 2 | (1 << 21)),
        ("a", 1 << 26),
        ("ee", 1 << 31),
        ("16", 16),
        ("A|C|8", 1 | 4 | 8),
        ("-1", -1),
        ("A5", 15),
    ],
)
def test_parse_flags(text: str, value: int) -> None:
    assert parse_flags(text) == value


@pytest.mark.parametrize("text", ["", "|", "A|", "A-", "!", "Aé"])
def test_parse_flags_invalid(text: str) -> None:
    with pytest.raises(ValueError):
        parse_flags(text)


def test_format_flags_like_fwrite_flag() -> None:
    assert format_flags(0) == "0"
    assert format_flags(1) == "A"
    assert format_flags(parse_flags("DAB")) == "ABD"
    assert format_flags(1 << 26) == "a"
    assert format_flags(parse_flags("AZaf")) == "AZaf"
    assert format_flags(-1) == "-1"


def test_roundtrip_all_single_bits() -> None:
    for bit in range(52):
        v = 1 << bit
        assert parse_flags(format_flags(v)) == v


def test_letters_helpers() -> None:
    v = letters_to_flags("ACz")
    assert flags_to_letters(v) == frozenset("ACz")
    assert has_flag(v, "C") and not has_flag(v, "B")
    assert set_flag(v, "B") == v | 2
    assert set_flag(v, "A", False) == v & ~1


def test_named_tables() -> None:
    names = flag_names("room_flags", parse_flags("D"))
    assert names_to_flags("room_flags", names) == parse_flags("D")
    assert flag_names("mob_flags", 1 << 51)[0].startswith("[")
    assert names_to_flags("mob_flags", ["[Z]"]) == 1 << 25
    with pytest.raises(KeyError):
        names_to_flags("mob_flags", ["inesistente"])
