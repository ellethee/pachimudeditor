"""Le enum neutre dell'editor devono restare identiche a quelle copiate del gioco (`game_models.enums`: nomi e valori).

`game_models` copia solo le enum del personaggio (`Sex`, `Position`): quelle dei contenuti (zone, stanze, reset) e i tipi oggetto sono
nel confronto opzionale col MUD vero (`tests/test_game_compat.py`).
"""

import pytest

from pachimudeditor.common import enums
from pachimudeditor_adapter_pachimud.game_models import enums as game_enums

NAMES = ["Sex", "Position"]


@pytest.mark.parametrize("name", NAMES)
def test_enums_match_copied_game_enums(name: str) -> None:
    """Stessi membri e valori."""
    assert {m.name: m.value for m in getattr(game_enums, name)} == {m.name: m.value for m in getattr(enums, name)}


def test_object_types_cover_the_game_ones() -> None:
    """Tutti i tipi oggetto del gioco (LeU) hanno un `ObjectType` (il `DRINKCON` del file e' `LIQUID_CONTAINER`)."""
    from pachimudeditor_adapter_pachimud.loaders import TYPE_MODELS
    from pachimudeditor_adapter_pachimud.mapping import type_enum

    assert {type_enum(name).name for name in TYPE_MODELS} == {m.name for m in enums.ObjectType}
