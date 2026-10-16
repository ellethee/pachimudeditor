"""Fixture di tests/core: adapter fittizi al posto di quelli reali."""

import sys
from collections.abc import Iterator
from importlib.metadata import EntryPoint

import pytest

from pachimudeditor.common.adapters import plugins

FAKE = "tests.core.fake_adapter"


def entry_points(**values: str) -> list[EntryPoint]:
    """Entry point sintetici `nome = valore` nel gruppo degli adapter."""
    return [EntryPoint(name=n, value=v, group=plugins.ENTRY_POINT_GROUP) for n, v in values.items()]


@pytest.fixture
def fake_plugins(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Gli unici adapter installati sono `fake` e `fake2`; la scoperta si azzera prima e dopo."""
    monkeypatch.setattr(plugins, "_entry_points", lambda: entry_points(fake=f"{FAKE}.plugin:plugin", fake2=f"{FAKE}.plugin:plugin2"))
    plugins.reset_discovery()
    for name in [m for m in sys.modules if m.startswith(f"{FAKE}.") and m != f"{FAKE}.plugin"]:
        del sys.modules[name]
    yield
    plugins.reset_discovery()
