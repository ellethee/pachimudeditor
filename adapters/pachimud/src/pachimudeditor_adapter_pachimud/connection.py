"""Connessione di un mondo pachimud: engine/sessioni SQLAlchemy async e schema riflesso, gestiti dall'adapter.

Ogni mondo ha la sua `PachimudConnection`, creata al primo uso e chiusa da `dispose()` (spegnimento dell'app, test).
Il database NON e' quello di autenticazione di pachifast: l'editor ha un DB suo (utenti, opzioni) e qui si apre quello
del gioco, indicato da `database_url`. Le impostazioni SQLite sono quelle del game server (`pachimud.database`):
`busy_timeout` (impostato per primo), `journal_mode=WAL` e `foreign_keys=ON`, cosi' l'editor convive con il gioco acceso.
"""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from pachimudeditor_adapter_pachimud.params import PachimudParams
from pachimudeditor_adapter_pachimud.schema import GameSchema, SchemaUnavailable, load_schema

log = logging.getLogger(__name__)

RETRY_AFTER_SECONDS = 2.0
"""Un caricamento fallito non viene ritentato prima di questo tempo (evita di martellare un DB assente)."""


def configure_sqlite(engine: AsyncEngine) -> None:
    """Pragma di connessione SQLite uguali a quelli del game server (`busy_timeout`, WAL, chiavi esterne)."""
    if engine.sync_engine.dialect.name != "sqlite":
        return

    @sa.event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: object, _record: object) -> None:
        """`busy_timeout` per primo: anche il passaggio a WAL puo' dover aspettare un lock."""
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class PachimudConnection:
    """Schema riflesso, engine e sessionmaker di un mondo; tutto creato al primo uso."""

    def __init__(self, params: PachimudParams) -> None:
        """Non apre nulla finche' non serve."""
        self.params = params
        self._schema: GameSchema | None = None
        self._failure: tuple[float, SchemaUnavailable] | None = None
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    def schema(self, *, refresh: bool = False) -> GameSchema:
        """Lo schema riflesso (sincrono: la prima volta apre il DB in un thread).

        Raises:
            SchemaUnavailable: DB assente/illeggibile o schema incompatibile (il fallimento e' ricordato per
                `RETRY_AFTER_SECONDS`).
        """
        if self._schema is not None and not refresh:
            return self._schema
        if self._failure is not None and not refresh and time.monotonic() - self._failure[0] < RETRY_AFTER_SECONDS:
            raise self._failure[1]
        try:
            database = self.params.sqlite_file
            if database is not None and not database.is_file():
                raise SchemaUnavailable(f"file del database non trovato: {database}")
            schema = load_schema(self.params.database_url)
        except SchemaUnavailable as exc:
            self._failure = (time.monotonic(), exc)
            self._schema = None
            raise
        self._failure = None
        self._schema = schema
        return schema

    def engine(self) -> AsyncEngine:
        """L'engine del mondo (creato al primo uso, nel loop corrente)."""
        if self._engine is None:
            self._engine = create_async_engine(self.params.database_url)
            configure_sqlite(self._engine)
            self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Una `AsyncSession` sul DB di gioco, con le classi mappate in `session.info["models"]`."""
        models = self.schema().models
        self.engine()
        assert self._sessionmaker is not None
        async with self._sessionmaker() as session:
            session.info["models"] = models
            yield session

    async def dispose(self) -> None:
        """Chiude l'engine e dimentica lo schema (un uso successivo riapre e rilegge tutto)."""
        engine, self._engine, self._sessionmaker, self._schema = self._engine, None, None, None
        if engine is not None:
            await engine.dispose()
