"""Fixture della suite: app pachifast contro database temporanei (mai `pachimud.db` reale).

`tests/core/` non richiede nessun adapter. Il resto della suite (adapter, HTTP, equivalenza con il gioco) richiede tutti
gli adapter del monorepo piu' il gioco `pachimud` (non e' una dipendenza: `uv pip install -e ../pachimud`): se mancano viene
saltato in raccolta.
"""

from importlib.util import find_spec
from pathlib import Path

STACK_MODULES = (
    "pachimud",
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
