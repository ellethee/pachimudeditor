"""Input malformato: eccezione RomParseError con riga, colonna e contesto."""

import pytest

from pachimudeditor_adapter_basedmud.rom_lib import RomParseError, RomWriteError, parse_area, write_area
from pachimudeditor_adapter_basedmud.rom_lib.model import Area, Reset

from . import samples as S


def err(text: str) -> RomParseError:
    with pytest.raises(RomParseError) as info:
        parse_area(text, filename="x.are")
    return info.value


def test_missing_hash() -> None:
    e = err("#AREA\nx~\nx~\nx~\n1 2\n\nMOBILES\n")
    assert e.line == 7 and "'#' atteso" in e.message and "x.are" in str(e)


def test_unterminated_string_reports_start_line() -> None:
    e = err("#ROOMS\n#100\nName~\nDescrizione senza tilde\n0 0 0\nS\n#0\n")
    assert e.line == 4 and "'~'" in e.message and "ROOMS vnum 100" in str(e)


def test_bad_number_in_mob() -> None:
    bad = S.MOBILES.replace("900 0\n23 2", "9x0 0\n23 2")
    e = err(bad)
    assert e.line == 10 and e.column == 8 and "numero atteso" in e.message
    assert "MOBILES vnum 100" in str(e)


def test_bad_reset_command() -> None:
    e = err("#RESETS\nM 0 1 1 1 1\nX 0 1\nS\n")
    assert e.line == 3 and "'X'" in e.message


def test_reset_missing_terminator() -> None:
    e = err("#RESETS\nM 0 1 1 1 1\n")
    assert "manca 'S'" in e.message


def test_bad_room_letter_and_door() -> None:
    assert err("#ROOMS\n#1\nn~\nd~\n0 0 0\nZ\n#0\n").line == 6
    assert "uscita" in err("#ROOMS\n#1\nn~\nd~\n0 0 0\nD9\n~\n~\n0 -1 1\nS\n#0\n").message
    assert "locks" in err("#ROOMS\n#1\nn~\nd~\n0 0 0\nD0\n~\n~\n7 -1 1\nS\n#0\n").message


def test_bad_object_affect_type() -> None:
    txt = S.OBJECTS.replace("A 12 -2 F", "Q 12 -2 F") + "#$\n"
    e = err(txt)
    assert "bit_type" in e.message


def test_unterminated_list_section_and_eof() -> None:
    assert "manca '#0'" in err("#MOBILES\n").message
    assert "numero atteso" in err("#SHOPS\n100 1 2").message
    assert err("#SPECIALS\nM 1\n").line >= 2


def test_areadata_without_end() -> None:
    assert "End" in err("#AREADATA\nName x~\n").message


def test_junk_before_section() -> None:
    assert err("ciao\n").line == 1


def test_write_errors() -> None:
    area = Area()
    area.resets.append(Reset("M", [1, 2]))
    with pytest.raises(RomWriteError):
        write_area(area)
    area.resets[0] = Reset("Z", [])
    with pytest.raises(RomWriteError):
        write_area(area)
