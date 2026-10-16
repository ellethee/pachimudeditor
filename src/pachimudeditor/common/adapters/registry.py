"""Registro dei mondi configurati e selezione dell'adapter per richiesta.

Configurazione :

- `pachimudeditor.yaml` (o variabile d'ambiente `WEBEDITOR_WORLDS`, JSON; vedi `common.adapters.settings`): lista `webeditor_worlds` di
  `{id, kind, name, path?, mapping?, params?, read_only?}`;
- `webeditor_default_world`: id del mondo di default (altrimenti `pachimud` se presente, o il primo).

Senza configurazione non esiste nessun mondo (`/api/worlds` e' vuoto): il mondo `pachimud` non e' piu' implicito.

I `kind` arrivano dai pacchetti adapter, scoperti con gli entry point del gruppo `pachimudeditor.adapters`
(`common.adapters.plugins`): `pachimud`, `basedmud`, `dikumod`, `mapping` (adapter generico guidato da un YAML di
mappatura) o adapter di terzi. `register_kind(kind, factory)` registra un kind a mano (test, uso programmatico) e
ha la precedenza sui plugin. Un kind senza adapter installato e' un errore leggibile che indica cosa installare.

La selezione per richiesta usa l'header `X-World` o la query `world`; assenti = mondo di default.
"""

import logging
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from pachifast.database import AliasedBaseModel
from pachifast.i18n import api_error
from pydantic import Field

from pachimudeditor.common.adapters import plugins
from pachimudeditor.common.adapters.base import AdapterCapabilities, AdapterInfo, WorldAdapter
from pachimudeditor.common.adapters.plugins import AdapterUnavailable
from pachimudeditor.common.adapters.settings import load_world_settings

log = logging.getLogger(__name__)

DEFAULT_WORLD_ID = "pachimud"
WORLD_HEADER = "X-World"
WORLD_QUERY = "world"


class WorldConfig(AliasedBaseModel):
    """Un mondo configurato."""

    id: str
    kind: str = "pachimud"
    name: str | None = None
    path: str | None = None
    """Cartella/file dei dati (adapter su file)."""
    mapping: str | None = None
    """Per `kind: mapping`: path del YAML di mappatura."""
    params: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = False
    config_path: str | None = None
    """Per `kind: pachimud`: path del `pachimud.yaml` del game server, da cui leggere `database_url`/`definition_path`
    se non sono dati come `params` (equivale a `params.config_path`; vedi l'adapter pachimud)."""


AdapterFactory = Callable[[WorldConfig], WorldAdapter]

_FACTORIES: dict[str, AdapterFactory] = {}


def register_kind(kind: str, factory: AdapterFactory) -> None:
    """Registra la factory degli adapter di tipo `kind` (sovrascrive una registrazione precedente)."""
    _FACTORIES[kind] = factory


def registered_kinds() -> list[str]:
    """I `kind` utilizzabili: registrati a mano o con un plugin installato che si importa."""
    return sorted({*_FACTORIES, *plugins.available_kinds()})


def check_kind(kind: str) -> None:
    """Alza `AdapterUnavailable` (con cosa installare) se non c'e' modo di creare adapter di tipo `kind`."""
    if kind not in _FACTORIES:
        plugins.get_plugin(kind)


def _factory(kind: str) -> AdapterFactory:
    """La factory di `kind`: quella registrata a mano oppure quella del plugin (importata ora)."""
    return _FACTORIES.get(kind) or plugins.load_factory(kind)


class WorldRegistry:
    """I mondi configurati (adapter istanziati al primo uso) e quello di default. Puo' essere vuoto (nessun mondo)."""

    def __init__(self, configs: list[WorldConfig], default_id: str | None = None) -> None:
        """Valida id univoci e `kind` noti; `default_id` o il primo mondo e' il default."""
        ids = [c.id for c in configs]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Id di mondo duplicati: {ids}")
        for config in configs:
            try:
                check_kind(config.kind)
            except AdapterUnavailable as exc:
                raise AdapterUnavailable(f"Mondo {config.id!r}: {exc}") from exc
        self._configs = {c.id: c for c in configs}
        self._adapters: dict[str, WorldAdapter] = {}
        self.default_id = default_id or (DEFAULT_WORLD_ID if DEFAULT_WORLD_ID in self._configs else (ids[0] if ids else ""))
        if self.default_id and self.default_id not in self._configs:
            raise ValueError(f"Mondo di default sconosciuto: {self.default_id!r}")

    @property
    def world_ids(self) -> list[str]:
        """Gli id dei mondi nell'ordine di configurazione."""
        return list(self._configs)

    def get(self, world_id: str | None = None) -> WorldAdapter:
        """L'adapter del mondo (default se `None`); 404 `world.not_found` se non esiste."""
        if not self._configs:
            raise api_error(404, "world.none_configured")
        world_id = world_id or self.default_id
        config = self._configs.get(world_id) if world_id else None
        if config is None:
            raise api_error(404, "world.not_found", world=world_id)
        adapter = self._adapters.get(world_id)
        if adapter is None:
            adapter = self._adapters[world_id] = _factory(config.kind)(config)
        return adapter

    async def aclose_all(self) -> None:
        """Chiude gli adapter gia' istanziati (engine e connessioni): allo spegnimento dell'app e nei test."""
        for adapter in list(self._adapters.values()):
            await adapter.close()

    def describe_all(self) -> list[AdapterInfo]:
        """`describe()` di ogni mondo, con `default` valorizzato."""
        infos = []
        for world_id in self._configs:
            info = self.get(world_id).describe()
            infos.append(info.model_copy(update={"default": world_id == self.default_id}))
        return infos


def load_world_configs() -> tuple[list[WorldConfig], str | None]:
    """I mondi configurati (validati) e il default; nessun mondo implicito: senza configurazione l'elenco e' vuoto."""
    raw, default = load_world_settings()
    return [WorldConfig.model_validate(item) for item in raw or []], default


def build_registry() -> WorldRegistry:
    """Costruisce il registro dalla configurazione (puo' essere vuoto)."""
    configs, default = load_world_configs()
    return WorldRegistry(configs, default)


_registry: WorldRegistry | None = None


def get_registry() -> WorldRegistry:
    """Il registro del processo, creato al primo utilizzo."""
    global _registry
    if _registry is None:
        _registry = build_registry()
    return _registry


def set_registry(registry: WorldRegistry | None) -> None:
    """Sostituisce (o azzera con `None`) il registro del processo: per i test."""
    global _registry
    _registry = registry


def get_adapter(request: Request) -> WorldAdapter:
    """Dipendenza FastAPI: l'adapter del mondo scelto da `X-World`/`?world=` (default se assenti)."""
    world_id = request.headers.get(WORLD_HEADER) or request.query_params.get(WORLD_QUERY)
    return get_registry().get(world_id)


AdapterDep = Annotated[WorldAdapter, Depends(get_adapter)]
"""Da usare come `adapter: AdapterDep` nelle firme delle route."""


def get_write_adapter(adapter: AdapterDep) -> WorldAdapter:
    """Come `get_adapter` ma 409 `world.read_only` se il mondo e' in sola lettura."""
    if adapter.capabilities().read_only:
        raise api_error(409, "world.read_only")
    return adapter


WriteAdapterDep = Annotated[WorldAdapter, Depends(get_write_adapter)]
"""Adapter per le route che scrivono (POST/PUT/DELETE)."""


def require_capability(name: str) -> Callable[..., None]:
    """Dipendenza che risponde 409 `world.capability_missing` se il mondo attivo non ha la capability `name`.

    Uso: `get_router(deps=[Depends(require_capability("supports_players"))])`.
    """

    def _check(adapter: AdapterDep) -> None:
        """Verifica la capability sull'adapter attivo."""
        if not getattr(adapter.capabilities(), name, False):
            raise api_error(409, "world.capability_missing", capability=name)

    return _check


__all__ = [
    "AdapterCapabilities",
    "AdapterDep",
    "WorldConfig",
    "WorldRegistry",
    "WriteAdapterDep",
    "build_registry",
    "check_kind",
    "get_adapter",
    "get_registry",
    "register_kind",
    "registered_kinds",
    "require_capability",
    "set_registry",
]
