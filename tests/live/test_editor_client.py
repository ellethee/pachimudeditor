"""Client del canale live dell'editor (`pachimudeditor.sdk.LiveClient`): framing, errori, timeout, token, limiti, riconnessione.

Contro il finto server (comandi reali del protocollo) e contro piccoli server scriptati che sbagliano apposta.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from pachimudeditor.sdk import LiveClient, LiveEchoIn, LiveError, LiveLoadIn, LivePlayerSetIn, LiveZoneResetIn
from tests.support.live_fake_server import FakeLiveServer
from tests.support.live_scripted import Scripted, answer

TOKEN = "s3cret-" + "x" * 33


@pytest.fixture
def sock(tmp_path: Path) -> str:
    """Percorso di un socket (breve: il limite di `sun_path` e' 107)."""
    return str(tmp_path / "l.sock")


@pytest.fixture
async def fake(sock: str) -> AsyncIterator[FakeLiveServer]:
    """Il finto server con scritture attive."""
    server = FakeLiveServer(sock, TOKEN)
    await server.start()
    yield server
    await stop(server)


OPEN: list[LiveClient] = []


def make(sock: str, token: str | None = TOKEN, timeout: float = 1.0) -> LiveClient:
    """Un client col token dato (chiuso da `stop` prima di fermare il server: `wait_closed` aspetta le connessioni aperte)."""
    client = LiveClient(sock, lambda: token, timeout=timeout)
    OPEN.append(client)
    return client


async def stop(server: FakeLiveServer | Scripted) -> None:
    """Chiude i client aperti e ferma il server."""
    for client in OPEN:
        await client.close()
    await server.stop()


async def test_status_and_typed_calls(fake: FakeLiveServer, sock: str) -> None:
    """`status` dichiara comandi e campi; who/info/zone/player/echo/load passano per i DTO."""
    client = make(sock)
    status = await client.status()
    assert status.state == "connected" and status.reachable and status.protocol == 1 and status.latency_ms is not None
    assert "player.set" in status.commands and "gold" in status.editable_fields and status.classes == ["read", "write"]
    who = await client.who()
    assert {p.name for p in who.players} == {"Tester", "Ghost"} and (await client.zones()).zones[1].name == "LIMBO"
    assert (await client.info()).world["zones"] == 5
    state = await client.player_get("tester")
    assert state.fields["gold"] == 150 and "levels" in state.editable_fields
    out = await client.player_set("tester", LivePlayerSetIn(fields={"gold": 500, "levels": {"cleric": 4}}), actor="mario")
    assert out.saved and out.applied["gold"].old == 150 and out.applied["levels.cleric"].new == 4
    assert (await client.zone_reset(LiveZoneResetIn(room=3001), actor="mario")).executed
    assert (await client.load("mob", LiveLoadIn(vnum=3000, room=3001, count=2))).loaded[1]["name"] == "Magus"
    assert (await client.echo(LiveEchoIn(text="ciao", all=True))).recipients == 1
    assert fake.echoes == [("all", "ciao")]
    await client.close()


async def test_unreachable_is_a_state_not_an_error(sock: str) -> None:
    """Senza socket: `status` risponde `unreachable`, `call` alza `LiveError('unreachable')` senza il percorso nel messaggio."""
    client = make(sock)
    status = await client.status()
    assert (status.state, status.reachable, status.code) == ("unreachable", False, "worldlive.unreachable")
    with pytest.raises(LiveError) as info:
        await client.who()
    assert info.value.code == "unreachable" and sock not in str(info.value)


async def test_token_missing_and_wrong_token_never_leak(fake: FakeLiveServer, sock: str, caplog: pytest.LogCaptureFixture) -> None:
    """Token assente: `token_missing` senza connettersi; sbagliato: `auth_failed`. Il token non e' in `repr`, errori, stato o log."""
    caplog.set_level(logging.DEBUG)
    assert (await make(sock, token=None).status()).state == "token_missing"
    bad = make(sock, token="WRONG-" + "y" * 40)
    status = await bad.status()
    assert status.state == "auth_failed" and not status.reachable
    with pytest.raises(LiveError) as info:
        await bad.who()
    for text in (repr(bad), str(info.value), status.model_dump_json(), caplog.text, *(a for a in fake.audit)):
        assert "WRONG-" not in text and TOKEN not in text
    good = make(sock)
    await good.who()
    assert TOKEN not in repr(good) + caplog.text + " ".join(fake.audit)


async def test_protocol_errors_keep_their_params(fake: FakeLiveServer, sock: str) -> None:
    """Gli errori del MUD diventano `LiveError` con `code` e `params` del protocollo."""
    client = make(sock)
    with pytest.raises(LiveError) as e1:
        await client.player_get("nessuno")
    assert (e1.value.code, e1.value.params) == ("not_found", {"what": "player"})
    with pytest.raises(LiveError) as e2:
        await client.player_set("tester", LivePlayerSetIn(fields={"gold": -1}))
    assert e2.value.code == "value_out_of_range" and e2.value.params["field"] == "gold" and e2.value.params["min"] == 0
    with pytest.raises(LiveError) as e3:
        await client.player_set("tester", LivePlayerSetIn(fields={"levels": {"cleric": 55}}))
    assert e3.value.code == "forbidden_by_policy" and e3.value.params["reason"] == "immortal_level"
    ok = await client.player_set("tester", LivePlayerSetIn(fields={"levels": {"cleric": 55}}, confirm_immortal=True))
    assert ok.warnings == ["immortal_level"]
    with pytest.raises(LiveError) as e4:
        await client.player_get("ghost")
    assert e4.value.code == "player_not_playing"


async def test_undeclared_command_is_not_sent(sock: str) -> None:
    """Con le scritture disattivate nel MUD il comando non e' in `hello`: `command_disabled` senza inviare nulla."""
    server = FakeLiveServer(sock, TOKEN, write=False)
    await server.start()
    try:
        client = make(sock)
        assert (await client.status()).editable_fields == [] and (await client.status()).classes == ["read"]
        with pytest.raises(LiveError) as info:
            await client.echo(LiveEchoIn(text="x", all=True))
        assert info.value.code == "command_disabled" and [c for c, _ in server.calls if c == "echo"] == []
    finally:
        await stop(server)


async def test_lazy_reconnection_after_restart(sock: str) -> None:
    """Il MUD si riavvia: la prima richiesta dopo il riavvio riconnette da sola (lettura ritentata una volta)."""
    server = FakeLiveServer(sock, TOKEN)
    await server.start()
    client = make(sock)
    assert (await client.who()).count == 2
    await stop(server)
    with pytest.raises(LiveError) as info:
        await client.who()
    assert info.value.code == "unreachable"
    server = FakeLiveServer(sock, TOKEN)
    await server.start()
    try:
        assert (await client.who()).count == 2
    finally:
        await stop(server)


async def test_actor_change_reopens_connection_for_writes_only(fake: FakeLiveServer, sock: str) -> None:
    """L'`actor` dell'audit e' quello dell'`hello`: una scrittura con un attore diverso riapre la connessione, una lettura no."""
    client = make(sock)
    await client.call("echo", {"text": "a", "to": {"all": True}}, actor="anna", write=True)
    await client.call("who", actor="bruno")
    await client.call("echo", {"text": "b", "to": {"all": True}}, actor="bruno", write=True)
    actors = [line.split("actor=")[1].split()[0] for line in fake.audit if "cmd=echo" in line]
    assert actors == ["anna", "bruno"] and any("actor=anna cmd=who" in line for line in fake.audit)
    await client.close()


async def test_read_retried_once_write_never(sock: str, tmp_path: Path) -> None:
    """Connessione chiusa senza risposta: la lettura e' ritentata (riconnessione), la scrittura e' `outcome_unknown` e NON rimandata."""

    async def behavior(n: int, req: dict[str, Any], writer: asyncio.StreamWriter) -> bool:
        """La prima connessione cade dopo ogni richiesta; le successive rispondono."""
        if n == 1:
            return True
        await answer(writer, req, {"players": [], "count": 0, "truncated": False, "recipients": 3})
        return False

    server = Scripted(Path(sock), behavior)
    await server.start()
    try:
        client = make(sock)
        assert (await client.who()).count == 0 and server.connections == 2
        await client.close()
        server.connections = 0
        with pytest.raises(LiveError) as info:
            await client.echo(LiveEchoIn(text="x", all=True))
        assert info.value.code == "outcome_unknown" and [r["cmd"] for r in server.requests].count("echo") == 1
        assert (await client.echo(LiveEchoIn(text="x", all=True))).recipients == 3  # la connessione e' stata scartata: si riapre
    finally:
        await stop(server)


async def test_timeout_drops_connection(sock: str) -> None:
    """Nessuna risposta: lettura = `timeout`, scrittura = `outcome_unknown`; la connessione non si riusa (una risposta tardiva la sfaserebbe)."""
    silent = True

    async def behavior(_n: int, req: dict[str, Any], writer: asyncio.StreamWriter) -> bool:
        """Tace finche' `silent`."""
        if not silent:
            await answer(writer, req, {"players": [], "count": 0, "truncated": False})
        return False

    server = Scripted(Path(sock), behavior)
    await server.start()
    try:
        client = make(sock, timeout=0.3)
        with pytest.raises(LiveError) as e1:
            await client.who()
        assert e1.value.code == "timeout"
        with pytest.raises(LiveError) as e2:
            await client.echo(LiveEchoIn(text="x", all=True))
        assert e2.value.code == "outcome_unknown"
        silent = False
        assert (await client.who()).count == 0 and server.connections == 3
        await client.close()
    finally:
        await stop(server)


async def test_oversized_response_and_flood(sock: str) -> None:
    """Risposta oltre `max_response` dichiarato in `hello` o flusso senza `\\n`: `response_too_large` e connessione chiusa."""
    mode = "big"

    async def behavior(_n: int, req: dict[str, Any], writer: asyncio.StreamWriter) -> bool:
        """Manda una riga di 500 byte oppure 3 MB senza newline."""
        if mode == "big":
            await answer(writer, req, {"players": [], "pad": "p" * 500})
        else:
            writer.write(b"x" * (3 << 20))
            await writer.drain()
        return False

    server = Scripted(Path(sock), behavior, limits={"max_line": 4096, "max_response": 200})
    await server.start()
    try:
        client = make(sock)
        with pytest.raises(LiveError) as e1:
            await client.who()
        assert e1.value.code == "response_too_large"
        mode = "flood"
        with pytest.raises(LiveError) as e2:
            await client.who()
        assert e2.value.code == "response_too_large" and server.connections == 2
    finally:
        await stop(server)


async def test_request_larger_than_max_line_is_not_sent(sock: str) -> None:
    """`max_line` di `hello`: una richiesta piu' lunga e' un errore locale e il MUD non la vede."""

    async def behavior(_n: int, req: dict[str, Any], writer: asyncio.StreamWriter) -> bool:
        """Risponde a tutto."""
        await answer(writer, req, {"recipients": 1})
        return False

    server = Scripted(Path(sock), behavior, limits={"max_line": 64, "max_response": 4096})
    await server.start()
    try:
        client = make(sock)
        with pytest.raises(LiveError) as info:
            await client.echo(LiveEchoIn(text="t" * 100, all=True))
        assert info.value.code == "request_too_large" and server.requests == []
        assert (await client.echo(LiveEchoIn(text="ok", all=True))).recipients == 1
    finally:
        await stop(server)


async def test_garbage_and_wrong_id_are_protocol_errors(sock: str) -> None:
    """Risposta non JSON o con id inatteso: `protocol_error`, connessione scartata."""
    replies = [b"non e' json\n", json.dumps({"id": 999, "ok": True, "result": {}}).encode() + b"\n"]

    async def behavior(_n: int, _req: dict[str, Any], writer: asyncio.StreamWriter) -> bool:
        """Manda le risposte sbagliate in ordine."""
        writer.write(replies.pop(0))
        await writer.drain()
        return False

    server = Scripted(Path(sock), behavior)
    await server.start()
    try:
        client = make(sock)
        for _ in range(2):
            with pytest.raises(LiveError) as info:
                await client.who()
            assert info.value.code == "protocol_error"
        assert server.connections == 2
    finally:
        await stop(server)
