"""Fixture della suite: app pachifast contro database temporanei (mai `pachimud.db` reale).

`tests/core/` non richiede nessun adapter. Il resto della suite (adapter, HTTP) richiede tutti
gli adapter del monorepo (nessun checkout del gioco: i modelli sono copiati in `game_models`): se mancano viene saltato
in raccolta.
"""

from importlib.util import find_spec
from pathlib import Path

import pytest

STACK_MODULES = (
    "pachimudeditor_adapter_pachimud",
    "pachimudeditor_adapter_basedmud",
    "pachimudeditor_adapter_dikumod",
    "pachimudeditor_adapter_mapping",
)
HAVE_STACK = all(find_spec(name) is not None for name in STACK_MODULES)
_KEEP = {"core", "support", "__init__.py", "conftest.py", "helpers.py", "__pycache__"}
collect_ignore = [] if HAVE_STACK else [p.name for p in Path(__file__).parent.iterdir() if p.name not in _KEEP]

if HAVE_STACK:
    from tests.stack_fixtures import *  # noqa: F403  (app, token, client, anon, game_db, ...)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Salta i test marcati `real_rom` / `real_dikumod` quando i dati reali locali mancano (vedi `tests/support/real_data.py`)."""
    from tests.support.real_data import MARKERS

    for item in items:
        for name, (present, reason) in MARKERS.items():
            if not present and name in item.keywords:
                item.add_marker(pytest.mark.skip(reason=reason))
