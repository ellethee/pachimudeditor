"""Le enum neutre dell'editor devono restare identiche a quelle copiate del gioco (`game_models.enums`: nomi e valori).

Il confronto con il MUD vero e' opzionale (`tests/test_game_compat.py`).
"""

import pytest

from pachimudeditor.common import enums
from pachimudeditor_adapter_pachimud.game_models import enums as game_enums

NAMES = ["Sex", "Position", "ObjectType", "ZoneCommandType", "ZoneResetMode", "SectorType", "Direction", "DoorFlag"]


@pytest.mark.parametrize("name", NAMES)
def test_enums_match_copied_game_enums(name: str) -> None:
    """Stessi membri e valori."""
    assert {m.name: m.value for m in getattr(game_enums, name)} == {m.name: m.value for m in getattr(enums, name)}
