"""Le enum neutre dell'editor devono restare identiche a quelle di `pachimud` (nomi e valori)."""

import pytest

from pachimudeditor.common import enums

MODULES = {
    "pachimud.character.enums": ["Sex", "Position"],
    "pachimud.object.enums": ["ObjectType"],
    "pachimud.zone.enums": ["ZoneCommandType", "ZoneResetMode"],
    "pachimud.zone.room.enums": ["SectorType", "Direction", "DoorFlag"],
}


@pytest.mark.parametrize("module,names", MODULES.items())
def test_enums_match_pachimud(module: str, names: list[str]) -> None:
    """Stessi membri e valori."""
    original = pytest.importorskip(module)
    for name in names:
        assert {m.name: m.value for m in getattr(original, name)} == {m.name: m.value for m in getattr(enums, name)}
