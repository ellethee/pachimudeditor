"""Rete di sicurezza di `save_area_file`: il testo generato viene riletto prima del replace."""

from pathlib import Path

import pytest
from pachimudeditor_adapter_basedmud.rom_lib import RomUnencodableError, RomWriteError, load_area_file, save_area_file

from tests.support.synthetic_worlds import write_rom_area


def test_record_count_change_is_refused_and_file_untouched(tmp_path: Path) -> None:
    """Un campo numerico con righe iniettate (non coperto dalla validazione dei token) tronca il file: rifiutato, nulla scritto."""
    path = write_rom_area(tmp_path / "area") / "prato.are"
    raw = path.read_bytes()
    area = load_area_file(path)
    area.mobiles[0].sex = "1\n#0\n#999"  # type: ignore[assignment]
    with pytest.raises(RomWriteError, match="rileggibile|record diversi"):
        save_area_file(path, area)
    assert path.read_bytes() == raw
    assert [p.name for p in path.parent.iterdir() if p.name.startswith(".")] == []


def test_unencodable_text_raises_dedicated_error(tmp_path: Path) -> None:
    """Un carattere fuori dall'encoding del file e' `RomUnencodableError` (sottoclasse di `RomWriteError`)."""
    path = write_rom_area(tmp_path / "area") / "prato.are"
    path.write_bytes(path.read_bytes().replace(b"passeggia qui.", b"passeggia qu\xec."))
    area = load_area_file(path)
    area.mobiles[0].short_descr = "\U0001f600"
    with pytest.raises(RomUnencodableError):
        save_area_file(path, area)
