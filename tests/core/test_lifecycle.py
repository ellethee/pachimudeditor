"""Avvio e spegnimento dei mondi (`common/adapters/lifecycle.py`): mai un'eccezione all'avvio, chiusura di tutti gli adapter."""

import logging
from collections.abc import Iterator
from typing import Any

import pytest

from pachimudeditor.common.adapters import lifecycle
from pachimudeditor.common.adapters.registry import WorldConfig, WorldRegistry, set_registry


class _Stub:
    """Adapter finto: registra le chiamate; `report` e `close_error` simulano un mondo non disponibile."""

    def __init__(self, report: Any = None, close_error: Exception | None = None) -> None:
        """Se `report` e' un'eccezione viene alzata da `log_schema_report`."""
        self.reported = 0
        self.closed = 0
        self._report = report
        self._close_error = close_error
        if report is not None:
            self.log_schema_report = self._log_schema_report

    def _log_schema_report(self) -> None:
        """Conta la chiamata ed eventualmente fallisce."""
        self.reported += 1
        if isinstance(self._report, Exception):
            raise self._report

    async def close(self) -> None:
        """Conta la chiusura ed eventualmente fallisce."""
        self.closed += 1
        if self._close_error:
            raise self._close_error


@pytest.fixture
def registry(fake_plugins: None) -> Iterator[WorldRegistry]:
    """Registro con tre mondi `fake` (a, b, c) i cui adapter sono sostituiti dai test; azzerato a fine test."""
    reg = WorldRegistry([WorldConfig(id=i, kind="fake", path="/x") for i in "abc"])
    set_registry(reg)
    yield reg
    set_registry(None)


def test_startup_reports_schema_and_skips_adapters_without_check(registry: WorldRegistry) -> None:
    """Solo i mondi che sanno controllare lo schema vengono interrogati."""
    with_check, without = _Stub(report=True), _Stub()
    registry._adapters.update({"a": with_check, "b": without, "c": _Stub(report=True)})  # noqa: SLF001
    lifecycle.startup()
    assert with_check.reported == 1 and registry._adapters["c"].reported == 1  # noqa: SLF001


def test_startup_never_fails_for_unavailable_world(
    registry: WorldRegistry, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Un mondo che fallisce al controllo, o che non si istanzia, e' solo loggato: gli altri mondi vengono comunque controllati."""
    from pachimudeditor.common.adapters import registry as registry_module

    def boom(_config: WorldConfig) -> Any:
        raise RuntimeError("non istanziabile")

    monkeypatch.setitem(registry_module._FACTORIES, "fake", boom)  # noqa: SLF001
    ok = _Stub(report=True)
    registry._adapters.update({"a": _Stub(report=RuntimeError("db giu'")), "c": ok})  # noqa: SLF001
    with caplog.at_level(logging.ERROR, logger=lifecycle.log.name):
        lifecycle.startup()  # 'b' non e' in cache: la factory alza
    assert ok.reported == 1
    assert "'a'" in caplog.text and "'b'" in caplog.text


def test_startup_without_worlds() -> None:
    """Senza mondi configurati non succede nulla."""
    set_registry(WorldRegistry([]))
    try:
        lifecycle.startup()
    finally:
        set_registry(None)


async def test_shutdown_closes_every_instantiated_adapter(registry: WorldRegistry) -> None:
    """Allo spegnimento si chiudono gli adapter istanziati (non quelli mai usati)."""
    a, b = _Stub(), _Stub()
    registry._adapters.update({"a": a, "b": b})  # noqa: SLF001
    await lifecycle.shutdown()
    assert (a.closed, b.closed) == (1, 1) and "c" not in registry._adapters  # noqa: SLF001
