"""Comportamenti propri del finto server (configurazioni che il modulo C reale cambia solo al riavvio)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from tests.live.conftest import FAKE_TOKEN
from tests.live.helpers import err, ok
from tests.support.live_client import LiveClient
from tests.support.live_fake_server import FakeLiveServer


async def test_write_class_disabled() -> None:
    """Con la classe `write` spenta i comandi non compaiono in `hello` e rispondono `command_disabled`."""
    with tempfile.TemporaryDirectory(prefix="lf-", dir="/tmp") as tmp:
        srv = FakeLiveServer(Path(tmp) / "f.sock", FAKE_TOKEN, write=False)
        await srv.start()
        c = await LiveClient.connect(srv.path)
        try:
            cmds = ok(await c.hello(FAKE_TOKEN))["commands"]
            assert set(cmds) == {"ping", "info", "who", "player.get", "zone.list"}
            err(await c.call("player.set", {"name": "Tester", "set": {"gold": 1}}), "command_disabled")
            err(await c.call("echo", {"text": "x", "to": {"all": True}}), "command_disabled")
            ok(await c.call("who"))
        finally:
            await c.close()
            await srv.stop()


async def test_three_failed_hellos_close_the_connection() -> None:
    """Tre `hello` falliti chiudono la connessione."""
    with tempfile.TemporaryDirectory(prefix="lf-", dir="/tmp") as tmp:
        srv = FakeLiveServer(Path(tmp) / "f.sock", FAKE_TOKEN)
        await srv.start()
        c = await LiveClient.connect(srv.path)
        try:
            for _ in range(3):
                err(await c.hello("x" * 40), "auth_failed")
            assert await c.read() is None
        finally:
            await c.close()
            await srv.stop()


async def test_hello_timeout() -> None:
    """Connessione muta: il server la chiude entro `hello_timeout`."""
    with tempfile.TemporaryDirectory(prefix="lf-", dir="/tmp") as tmp:
        srv = FakeLiveServer(Path(tmp) / "f.sock", FAKE_TOKEN, hello_timeout=0.3)
        await srv.start()
        c = await LiveClient.connect(srv.path)
        try:
            assert await asyncio.wait_for(c.reader.read(), 3) == b""
        finally:
            await c.close()
            await srv.stop()


async def test_state_is_observable() -> None:
    """L'editor puo' ispezionare cosa e' stato chiamato (`calls`, `loaded`, `resets`, `saves`)."""
    with tempfile.TemporaryDirectory(prefix="lf-", dir="/tmp") as tmp:
        srv = FakeLiveServer(Path(tmp) / "f.sock", FAKE_TOKEN)
        await srv.start()
        c = await LiveClient.connect(srv.path)
        try:
            ok(await c.hello(FAKE_TOKEN))
            ok(await c.call("zone.reset", {"zone": 3}))
            ok(await c.call("player.set", {"name": "tester", "set": {"gold": 7}}))
            assert srv.resets == [3] and srv.saves == ["Tester"] and srv.players["tester"]["fields"]["gold"] == 7
            assert [name for name, _ in srv.calls] == ["zone.reset", "player.set"]
        finally:
            await c.close()
            await srv.stop()
