"""Supporto comune ai mixin di `PachimudAdapter`: sessione sul database di gioco del mondo e conversioni DTO."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from pachifast.database import AliasedBaseModel
from pachifast.database.pagination import paginate
from pachifast.i18n import api_error
from pachifast.schemas.responses import PageParams, PaginatedResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.connection import PachimudConnection
from pachimudeditor_adapter_pachimud.params import PachimudConfigError, PachimudParams, resolve_params
from pachimudeditor_adapter_pachimud.schema import GameModels, SchemaUnavailable, schema_unavailable_error
from pachimudeditor.sdk import WorldConfig
from pachimudeditor_adapter_pachimud.editor.pagination import default_order

DtoT = TypeVar("DtoT", bound=AliasedBaseModel)


class PachimudSupport:
    """Stato e utility condivisi dai mixin: configurazione del mondo, connessione e sessioni."""

    def __init__(self, config: WorldConfig) -> None:
        """Risolve i parametri del mondo (`database_url`, `definitions_path`, ...); il DB si apre al primo uso.

        Raises:
            PachimudConfigError: parametri mancanti o non validi.
        """
        self.config = config
        self.params: PachimudParams = resolve_params(config)
        self.connection = PachimudConnection(self.params)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Una `AsyncSession` sul database del mondo (503 `world.unavailable` se non e' utilizzabile)."""
        try:
            async with self.connection.session() as session:
                yield session
        except SchemaUnavailable as exc:
            raise schema_unavailable_error(exc) from exc

    def models(self) -> GameModels:
        """Le classi mappate del mondo (503 `world.unavailable` se il DB non e' utilizzabile)."""
        try:
            return self.connection.schema().models
        except SchemaUnavailable as exc:
            raise schema_unavailable_error(exc) from exc

    async def close(self) -> None:
        """Chiude engine e connessioni del mondo."""
        await self.connection.dispose()

    def ensure_writable(self) -> None:
        """409 `world.read_only` se il mondo e' configurato in sola lettura (ultima difesa dell'adapter)."""
        if self.config.read_only:
            raise api_error(409, "world.read_only")

    @staticmethod
    def values(data: BaseModel, *, exclude_unset: bool = False) -> dict[str, Any]:
        """I campi del DTO per nome Python, senza `extra`: pachimud non ha campi aggiuntivi (422 se valorizzato)."""
        if getattr(data, "extra", None):
            raise api_error(422, "world.extra_unsupported")
        return data.model_dump(by_alias=False, exclude_unset=exclude_unset, exclude={"extra"})

    @staticmethod
    async def page(session: AsyncSession, model: type, params: PageParams, dto: type[DtoT]) -> PaginatedResponse[DtoT]:
        """Lista paginata del modello mappato convertita in `PaginatedResponse[dto]` (ordine di default: vnum)."""
        raw = await paginate(session, model, params, extra_filters=[default_order("vnum")])
        return PaginatedResponse[dto](  # type: ignore[valid-type]
            items=[dto.model_validate(row) for row in raw.items],
            total=raw.total,
            page=raw.page,
            pageSize=raw.pageSize,
            pages=raw.pages,
        )


__all__ = ["PachimudConfigError", "PachimudSupport"]
