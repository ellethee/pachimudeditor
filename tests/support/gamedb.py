"""Accesso diretto al database di gioco di test con i modelli ORM COPIATI dal gioco (`game_models`).

I test lo usano per seminare e verificare righe come farebbe il game server, indipendentemente dall'adapter
dell'editor (che legge le tabelle riflesse). Nessuna dipendenza dal pacchetto `pachimud`.
"""

import os

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

import pachimudeditor_adapter_pachimud.game_models  # noqa: F401  registra i modelli
from pachimudeditor_adapter_pachimud.connection import configure_sqlite

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine(database_url: str) -> AsyncEngine:
    """Engine async con i pragma SQLite del game server."""
    engine = create_async_engine(database_url)
    configure_sqlite(engine)
    return engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Il session factory (modelli copiati) sul DB di test indicato da `PACHIMUD_DATABASE_URL`."""
    global _engine, _factory
    if _factory is None:
        _engine = create_engine(os.environ["PACHIMUD_DATABASE_URL"])
        _factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _factory


async def dispose() -> None:
    """Chiude l'engine (il file viene ricreato a ogni test)."""
    global _engine, _factory
    engine, _engine, _factory = _engine, None, None
    if engine is not None:
        await engine.dispose()
