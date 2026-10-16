"""Accesso diretto al database di gioco di test con i modelli ORM del GIOCO (dipendenza di solo sviluppo).

I test lo usano per seminare e verificare righe come farebbe il game server, indipendentemente dall'adapter
dell'editor (che legge le tabelle riflesse). Richiede il pacchetto `pachimud`; senza, i test che lo importano si saltano.
"""

import os

import pytest

pytest.importorskip("pachimud")

from pachimud.database.database import create_engine, create_session_factory  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker  # noqa: E402

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Il session factory (modelli del gioco) sul DB di test indicato da `PACHIMUD_DATABASE_URL`."""
    global _engine, _factory
    if _factory is None:
        _engine = create_engine(os.environ["PACHIMUD_DATABASE_URL"])
        _factory = create_session_factory(_engine)
    return _factory


async def dispose() -> None:
    """Chiude l'engine (il file viene ricreato a ogni test)."""
    global _engine, _factory
    engine, _engine, _factory = _engine, None, None
    if engine is not None:
        await engine.dispose()
