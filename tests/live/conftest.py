"""Fixture della suite di conformita' del canale live.

Ogni test gira contro il **finto server** (sempre) e, se disponibile, contro il **modulo C reale**:
- `LIVECTL_TEST_SOCKET` + `LIVECTL_TEST_TOKEN`: un MUD gia' acceso con il modulo (classi `read,write`, giocatore `Tester` in gioco);
- oppure `DIKUMOD_SRC` + `DIKUMOD_LIB` (+ g++, make, patch): il MUD viene costruito e avviato su copie temporanee (`real_mud.py`).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.live import real_mud
from tests.support.live_client import LiveClient
from tests.support.live_fake_server import FakeLiveServer

FAKE_TOKEN = "f" * 16 + "a" * 24


@dataclass
class Target:
    """Il server sotto prova e i valori noti del suo mondo."""

    kind: str
    socket: str
    token: str
    audit_lines: Callable[[], list[str]]
    fake: FakeLiveServer | None = None
    player: str = "Tester"
    room: int = 3001
    mob_vnum: int = 3000
    obj_vnum: int = 3001
    denied_obj: int = 1600
    max_conn: int = 4


def _real_params() -> list[str]:
    """`real` solo se si puo' provare davvero (niente test saltati altrimenti)."""
    if os.environ.get("LIVECTL_TEST_SOCKET") and os.environ.get("LIVECTL_TEST_TOKEN"):
        return ["real"]
    return ["real"] if real_mud.available() is None else []


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrizza `target` su fake (+ real se disponibile)."""
    if "target" in metafunc.fixturenames:
        metafunc.parametrize("target", ["fake", *_real_params()], indirect=True, scope="session")


async def _sync_room(t: Target) -> Target:
    """La stanza del giocatore di prova dipende dal file di partenza: la si legge dal server."""
    c = await LiveClient.connect(t.socket)
    try:
        await c.hello(t.token, actor="fixture")
        who = (await c.call("who"))["result"]["players"]
        t.room = next(p["room"] for p in who if p["name"] == t.player)
    finally:
        await c.close()
    return t


@pytest.fixture(scope="session")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    """Avvia (o si collega a) il server sotto prova."""
    tmp = Path(tempfile.mkdtemp(prefix="lf-", dir="/tmp"))
    try:
        if request.param == "fake":
            fake = FakeLiveServer(tmp / "f.sock", FAKE_TOKEN)
            await fake.start()
            yield Target("fake", str(tmp / "f.sock"), FAKE_TOKEN, lambda: list(fake.audit), fake=fake)
            await fake.stop()
        elif os.environ.get("LIVECTL_TEST_SOCKET"):
            audit_path = os.environ.get("LIVECTL_TEST_AUDIT")
            lines = (lambda: Path(audit_path).read_text().splitlines()) if audit_path else (lambda: [])
            yield await _sync_room(Target("real", os.environ["LIVECTL_TEST_SOCKET"], os.environ["LIVECTL_TEST_TOKEN"], lines))
        else:
            mud = await real_mud.start()
            try:
                yield await _sync_room(
                    Target("real", mud.socket, real_mud.TOKEN, lambda: mud.audit.read_text().splitlines() if mud.audit.exists() else [])
                )
            finally:
                mud.stop()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
async def client(target: Target) -> AsyncIterator[LiveClient]:
    """Connessione gia' autenticata."""
    c = await LiveClient.connect(target.socket)
    resp = await c.hello(target.token, actor="pytest")
    assert resp["ok"], resp
    yield c
    await c.close()


@pytest.fixture
async def raw(target: Target) -> AsyncIterator[LiveClient]:
    """Connessione NON autenticata."""
    c = await LiveClient.connect(target.socket)
    yield c
    await c.close()
