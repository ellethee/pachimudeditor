"""Fixture dello stack applicativo di prova: DB di gioco temporaneo, app, utente e client autenticato."""

import atexit
import shutil
import sys
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from tests.support import stack

# L'ambiente va impostato PRIMA di importare l'app: la config e gli engine sono cache di processo.
WORKDIR = Path(tempfile.mkdtemp(prefix="pachimudeditor-pytest-"))
atexit.register(shutil.rmtree, WORKDIR, ignore_errors=True)
ENV = stack.apply_environment(WORKDIR)
stack.create_test_user()

from pachimudeditor.app import create_editor_app  # noqa: E402
from pachimudeditor.common.adapters.plugins import available_kinds  # noqa: E402
from pachimudeditor.common.adapters.registry import get_registry  # noqa: E402

app = create_editor_app(extra_kinds=available_kinds())

__all__ = ["ENV", "WORKDIR", "_guard_real_db", "anon", "app", "client", "game_db", "token"]


@pytest.fixture(scope="session", autouse=True)
def _guard_real_db() -> None:
    """Rete di sicurezza: il mondo pachimud in uso deve puntare al database temporaneo."""
    params = get_registry().get("pachimud").params  # type: ignore[attr-defined]
    assert params.sqlite_file is not None and params.sqlite_file.parent == WORKDIR, params.database_url
    assert params.definitions_path is not None and params.definitions_path.parent == WORKDIR


async def _dispose_game_engine() -> None:
    """Chiude l'engine con i modelli del gioco usato dai test (se importato)."""
    gamedb = sys.modules.get("tests.support.gamedb")
    if gamedb is not None:
        await gamedb.dispose()


@pytest_asyncio.fixture(autouse=True)
async def game_db() -> AsyncIterator[None]:
    """Un database di gioco nuovo e seminato per ogni test (l'adapter rilegge lo schema e riapre l'engine)."""
    await get_registry().aclose_all()
    await _dispose_game_engine()
    stack.seed_game_db(WORKDIR)
    yield
    await get_registry().aclose_all()
    await _dispose_game_engine()


@pytest_asyncio.fixture(scope="session")
async def token() -> str:
    """Access token dell'utente di test."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as anon:
        response = await anon.post("/api/auth/token", data={"username": stack.TEST_USER, "password": stack.TEST_PASSWORD})
        assert response.status_code == 200, response.text
        return response.json()["access_token"]


@pytest_asyncio.fixture
async def anon() -> AsyncIterator[httpx.AsyncClient]:
    """Client senza credenziali."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def client(token: str) -> AsyncIterator[httpx.AsyncClient]:
    """Client autenticato; le risposte vanno lette con `data(response)`."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as c:
        yield c
