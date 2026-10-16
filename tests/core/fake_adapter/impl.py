"""Adapter fittizio: tutti i metodi astratti sono stub che alzano `NotImplementedError`."""

from typing import Any

from pachimudeditor.sdk import AdapterCapabilities, AdapterInfo, WorldAdapter, WorldConfig


def _stub(*args: Any, **kwargs: Any) -> Any:
    """Metodo non implementato."""
    raise NotImplementedError


_Base = type("_Base", (WorldAdapter,), {name: _stub for name in WorldAdapter.__abstractmethods__})


class FakeAdapter(_Base):
    """Adapter che non fa nulla: basta a istanziare il kind."""

    def __init__(self, config: WorldConfig) -> None:
        """Conserva la configurazione."""
        self.config = config

    def capabilities(self) -> AdapterCapabilities:
        """Solo il nucleo."""
        return AdapterCapabilities()

    def describe(self) -> AdapterInfo:
        """Nessuna risorsa descritta."""
        return AdapterInfo(
            id=self.config.id, kind=self.config.kind, name=self.config.name or "", capabilities=self.capabilities(), resources=[]
        )


def validate(config: WorldConfig) -> None:
    """Un mondo fittizio senza `path` e' inutilizzabile."""
    if not config.path:
        raise ValueError("manca path (fake)")
