"""Conformita' del protocollo `livectl` v1 (docs/backend/live-control-protocol.md).

Gira contro il finto server e, se disponibile, contro il modulo C reale (vedi `conftest.py`).
"""

from __future__ import annotations

import asyncio
import json

from tests.live.conftest import Target
from tests.live.helpers import err, ok
from tests.support.live_client import LiveClient

# ---- handshake e autenticazione -------------------------------------------------------------------------------------------


async def test_hello_capability_discovery(target: Target, raw: LiveClient) -> None:
    """`hello` riuscito: versione, MUD, limiti, comandi con classe."""
    r = ok(await raw.hello(target.token))
    assert r["protocol"] == 1
    assert r["mud"]["kind"] and r["mud"]["version"]
    assert r["limits"]["max_line"] == 4096 and r["limits"]["max_text"] == 400
    assert {"ping", "info", "who", "player.get", "zone.list"} <= set(r["commands"])
    assert {"player.set", "zone.reset", "load.mob", "load.obj", "echo"} <= set(r["commands"])
    assert r["commands"]["ping"]["class"] == "read" and r["commands"]["player.set"]["class"] == "write"
    assert "gold" in r["commands"]["player.set"]["fields"]
    for reserved in ("exec", "force", "server.shutdown", "server.reboot", "player.kick"):
        assert reserved not in r["commands"]


async def test_command_before_hello(raw: LiveClient) -> None:
    """Prima del `hello` ogni comando e' rifiutato."""
    err(await raw.call("ping"), "auth_required")
    err(await raw.call("who"), "auth_required")


async def test_wrong_token(target: Target, raw: LiveClient) -> None:
    """Token errato: `auth_failed`, senza dettagli; il token non compare nella risposta."""
    resp = err(await raw.hello("x" * 40), "auth_failed")
    assert "x" * 40 not in json.dumps(resp)
    err(await raw.call("ping"), "auth_required")


async def test_protocol_unsupported(target: Target, raw: LiveClient) -> None:
    """Nessuna versione in comune."""
    resp = await raw.call("hello", {"protocols": [99], "token": target.token})
    assert err(resp, "protocol_unsupported")["params"]["supported"] == [1]


async def test_second_hello_rejected(client: LiveClient, target: Target) -> None:
    """Un secondo `hello` sulla stessa connessione e' una richiesta errata."""
    err(await client.hello(target.token), "bad_request")


# ---- framing e richieste malformate --------------------------------------------------------------------------------------


async def test_malformed_requests(client: LiveClient) -> None:
    """Riga non JSON, chiavi duplicate, float, UTF-8 invalido: `bad_json` con id nullo, la connessione resta."""
    for data in (
        b"not json\n",
        b'{"id":1,"id":2,"cmd":"ping"}\n',
        b'{"id":1,"cmd":"ping","params":{"x":1.5}}\n',
        b'{"id":1,"cmd":"\xff"}\n',
    ):
        await client.send_raw(data)
        resp = await client.read()
        assert resp is not None and resp["id"] is None
        err(resp, "bad_json")
    ok(await client.call("ping"))


async def test_bad_request_shapes(client: LiveClient) -> None:
    """Id mancante/di tipo errato, cmd non stringa, chiavi di primo livello sconosciute, params non oggetto."""
    for data in (b'{"cmd":"ping"}\n', b'{"id":true,"cmd":"ping"}\n', b'{"id":-1,"cmd":"ping"}\n', b"[1,2]\n"):
        await client.send_raw(data)
        resp = await client.read()
        assert resp is not None
        err(resp, "bad_request")
    for data in (
        b'{"id":1,"cmd":5}\n',
        b'{"id":1,"cmd":"ping","extra":1}\n',
        b'{"id":1,"cmd":"ping","params":[]}\n',
        b'{"id":1,"cmd":"Ping"}\n',
    ):
        await client.send_raw(data)
        resp = await client.read()
        assert resp is not None and resp["id"] == 1
        err(resp, "bad_request")


async def test_string_ids_are_echoed(client: LiveClient) -> None:
    """Gli id stringa tornano identici."""
    await client.send_raw(b'{"id":"abc-1","cmd":"ping"}\n')
    resp = await client.read()
    assert resp is not None and resp["id"] == "abc-1"
    ok(resp)


async def test_line_too_long_closes(client: LiveClient) -> None:
    """Una riga oltre 4096 byte: `line_too_long` e connessione chiusa."""
    await client.send_raw(b'{"id":1,"cmd":"ping","params":{"x":"' + b"a" * 5000 + b'"}}\n')
    resp = await client.read()
    assert resp is not None
    err(resp, "line_too_long")
    assert await client.read() is None


async def test_line_without_newline_closes(client: LiveClient) -> None:
    """Dati senza fine riga oltre il limite: la connessione si chiude, il server non accumula all'infinito."""
    await client.send_raw(b"a" * 9000)
    try:
        resp = await client.read(5)
    except TimeoutError:
        resp = None
    assert resp is None or resp["error"]["code"] == "line_too_long"


async def test_unknown_and_reserved_commands(client: LiveClient) -> None:
    """Comandi non definiti (compresi quelli riservati/pericolosi): `unknown_command`."""
    for cmd in ("nope", "exec", "force", "server.shutdown", "player.kick"):
        err(await client.call(cmd, {}), "unknown_command")


async def test_unknown_params_rejected(client: LiveClient) -> None:
    """Il server e' severo: parametri sconosciuti -> `bad_params`."""
    assert err(await client.call("ping", {"x": 1}), "bad_params")["params"]["field"] == "x"
    err(await client.call("who", {"verbose": True}), "bad_params")


async def test_pipelined_requests_answered_in_order(client: LiveClient) -> None:
    """Piu' richieste in una sola scrittura: risposte in ordine."""
    await client.send_raw(b"".join(json.dumps({"id": i, "cmd": "ping"}).encode() + b"\n" for i in (11, 12, 13)))
    ids = [(await client.read())["id"] for _ in range(3)]  # type: ignore[index]
    assert ids == [11, 12, 13]


# ---- comandi di lettura --------------------------------------------------------------------------------------------------


async def test_ping_and_info(client: LiveClient) -> None:
    """`ping` e `info`: forma delle risposte."""
    assert ok(await client.call("ping"))["pong"] is True
    info = ok(await client.call("info"))
    assert info["uptime_s"] >= 0 and info["started_at"] <= info["now"]
    assert info["players"]["playing"] >= 1 and info["world"]["zones"] >= 1
    assert "password" not in json.dumps(info).lower()


async def test_who(client: LiveClient, target: Target) -> None:
    """`who` mostra il giocatore in gioco, senza indirizzi di rete."""
    r = ok(await client.call("who"))
    mine = next(p for p in r["players"] if p["name"] == target.player)
    assert mine["state"] == "playing" and mine["room"] == target.room and mine["level"] >= 1
    assert r["count"] == len(r["players"]) and r["truncated"] is False
    assert not {"host", "ip", "address"} & set(mine)
    assert [p["name"] for p in ok(await client.call("who", {"prefix": "tes"}))["players"]] == [target.player]
    assert ok(await client.call("who", {"prefix": "zzzz"}))["players"] == []
    err(await client.call("who", {"limit": 0}), "value_out_of_range")
    err(await client.call("who", {"limit": 1000}), "value_out_of_range")
    assert len(ok(await client.call("who", {"limit": 1}))["players"]) == 1


async def test_player_get(client: LiveClient, target: Target) -> None:
    """`player.get`: campi correnti, nome senza maiuscole/minuscole, errori."""
    r = ok(await client.call("player.get", {"name": target.player.lower()}))
    assert r["name"] == target.player and r["state"] == "playing"
    f = r["fields"]
    assert {"gold", "exp", "hit", "str", "conditions", "levels", "roomVnum"} <= set(f)
    assert set(f["conditions"]) == {"drunk", "full", "thirst"}
    assert "password" not in json.dumps(r).lower() and "pwd" not in json.dumps(r).lower()
    assert err(await client.call("player.get", {"name": "Nessuno"}), "not_found")["params"]["what"] == "player"
    err(await client.call("player.get", {"name": "../etc"}), "bad_params")
    err(await client.call("player.get", {}), "bad_params")


async def test_zone_list(client: LiveClient, target: Target) -> None:
    """`zone.list`: indici, nomi, top crescenti."""
    zones = ok(await client.call("zone.list"))["zones"]
    assert zones and [z["index"] for z in zones] == list(range(len(zones)))
    assert all({"index", "num", "name", "top", "lifespan", "age", "reset_mode", "started"} <= set(z) for z in zones)


# ---- scritture ------------------------------------------------------------------------------------------------------------


async def _get(client: LiveClient, name: str) -> dict:  # type: ignore[type-arg]
    return ok(await client.call("player.get", {"name": name}))["fields"]


async def test_player_set_applies_and_restores(client: LiveClient, target: Target) -> None:
    """`player.set` cambia i valori, risponde old/new e `saved`; il valore si legge con `player.get`."""
    before = await _get(client, target.player)
    r = ok(await client.call("player.set", {"name": target.player, "set": {"gold": 4321, "conditions": {"drunk": 1}}}))
    assert r["applied"]["gold"] == {"old": before["gold"], "new": 4321}
    assert r["applied"]["conditions.drunk"]["new"] == 1
    assert r["saved"] is True and r["warnings"] == []
    after = await _get(client, target.player)
    assert after["gold"] == 4321 and after["conditions"]["drunk"] == 1
    # idempotente a parita' di valori
    again = ok(await client.call("player.set", {"name": target.player, "set": {"gold": 4321}, "save": False}))
    assert again["applied"]["gold"] == {"old": 4321, "new": 4321} and again["saved"] is False
    ok(
        await client.call(
            "player.set", {"name": target.player, "set": {"gold": before["gold"], "conditions": {"drunk": before["conditions"]["drunk"]}}}
        )
    )
    assert (await _get(client, target.player))["gold"] == before["gold"]


async def test_player_set_is_atomic(client: LiveClient, target: Target) -> None:
    """Un campo non valido annulla l'intera richiesta: nessuna modifica parziale."""
    before = await _get(client, target.player)
    e = err(await client.call("player.set", {"name": target.player, "set": {"gold": 9999, "dex": 99}}), "value_out_of_range")
    assert e["params"]["field"] == "dex" and e["params"]["max"] == 25
    err(await client.call("player.set", {"name": target.player, "set": {"gold": 9999, "nonesiste": 1}}), "bad_params")
    assert (await _get(client, target.player))["gold"] == before["gold"]


async def test_player_set_validation(client: LiveClient, target: Target) -> None:
    """Intervalli, tipi, campi non modificabili e forma di `set`."""
    n = target.player
    err(await client.call("player.set", {"name": n, "set": {"gold": -1}}), "value_out_of_range")
    err(await client.call("player.set", {"name": n, "set": {"gold": "5"}}), "bad_params")
    err(await client.call("player.set", {"name": n, "set": {"gold": True}}), "bad_params")
    for field in ("maxHit", "race", "password", "pwd", "title", "armor"):
        err(await client.call("player.set", {"name": n, "set": {field: 1}}), "bad_params")
    err(await client.call("player.set", {"name": n, "set": {}}), "bad_params")
    err(await client.call("player.set", {"name": n, "set": {"conditions": {"nope": 1}}}), "bad_params")
    err(await client.call("player.set", {"name": n, "set": {"conditions": {"drunk": 99}}}), "value_out_of_range")
    err(await client.call("player.set", {"name": "Nessuno", "set": {"gold": 1}}), "not_found")
    err(await client.call("player.set", {"name": n}), "bad_params")


async def test_player_set_immortal_requires_confirmation(client: LiveClient, target: Target) -> None:
    """Livello >= 51: rifiutato senza `confirm_immortal`, consentito con avvertenza; poi si ripristina."""
    levels = (await _get(client, target.player))["levels"]
    cls, old = next(iter(levels.items()))
    e = err(await client.call("player.set", {"name": target.player, "set": {"levels": {cls: 51}}}), "forbidden_by_policy")
    assert e["params"]["reason"] == "immortal_level" and e["params"]["level"] == 51
    assert (await _get(client, target.player))["levels"][cls] == old
    r = ok(await client.call("player.set", {"name": target.player, "set": {"levels": {cls: 51}}, "confirm_immortal": True}))
    assert r["warnings"][0] == "immortal_level" and r["applied"][f"levels.{cls}"] == {"old": old, "new": 51}
    ok(await client.call("player.set", {"name": target.player, "set": {"levels": {cls: 51}}}))  # nessuna promozione: niente conferma
    ok(await client.call("player.set", {"name": target.player, "set": {"levels": {cls: old}}}))
    assert (await _get(client, target.player))["levels"][cls] == old
    err(await client.call("player.set", {"name": target.player, "set": {"levels": {cls: 60}}}), "value_out_of_range")
    other = "magic_user" if cls != "magic_user" else "thief"
    err(await client.call("player.set", {"name": target.player, "set": {"levels": {other: 5}}}), "forbidden_by_policy")


async def test_zone_reset(client: LiveClient, target: Target) -> None:
    """`zone.reset` per stanza o per indice; zona 0 vietata; parametri esclusivi."""
    zones = ok(await client.call("zone.list"))["zones"]
    mine = next(p for p in ok(await client.call("who"))["players"] if p["name"] == target.player)["zone"]
    r = ok(await client.call("zone.reset", {"room": target.room}))
    assert r["zone"] == mine and r["executed"] is True and r["name"]
    assert ok(await client.call("zone.reset", {"zone": mine, "only_if_empty": True}))["executed"] is False  # il giocatore e' nella zona
    err(await client.call("zone.reset", {"zone": 0}), "forbidden_by_policy")
    err(await client.call("zone.reset", {"zone": len(zones) + 5}), "not_found")
    err(await client.call("zone.reset", {"room": 99999999}), "not_found")
    err(await client.call("zone.reset", {"zone": 1, "room": 3001}), "bad_params")
    err(await client.call("zone.reset", {}), "bad_params")


async def test_load_mob_and_obj(client: LiveClient, target: Target) -> None:
    """`load.mob`/`load.obj` in stanza e a un giocatore; deny-list; errori."""
    r = ok(await client.call("load.mob", {"vnum": target.mob_vnum, "room": target.room, "count": 2}))
    assert len(r["loaded"]) == 2 and r["loaded"][0]["vnum"] == target.mob_vnum and r["loaded"][0]["room"] == target.room
    r = ok(await client.call("load.obj", {"vnum": target.obj_vnum, "player": target.player}))
    assert r["loaded"][0]["vnum"] == target.obj_vnum
    ok(await client.call("load.obj", {"vnum": target.obj_vnum, "room": target.room}))
    assert (
        err(await client.call("load.obj", {"vnum": target.denied_obj, "room": target.room}), "forbidden_by_policy")["params"]["reason"]
        == "deny_list"
    )
    assert err(await client.call("load.mob", {"vnum": 999999, "room": target.room}), "not_found")["params"]["what"] == "mob"
    err(await client.call("load.obj", {"vnum": 999999, "room": target.room}), "not_found")
    err(await client.call("load.mob", {"vnum": target.mob_vnum, "room": 99999999}), "not_found")
    err(await client.call("load.mob", {"vnum": target.mob_vnum, "room": target.room, "count": 11}), "value_out_of_range")
    err(await client.call("load.mob", {"vnum": target.mob_vnum}), "bad_params")
    err(await client.call("load.mob", {"vnum": target.mob_vnum, "room": 1, "player": target.player}), "bad_params")


async def test_echo(client: LiveClient, target: Target) -> None:
    """`echo` a un giocatore, a una stanza, a tutti; testi non ammessi."""
    assert ok(await client.call("echo", {"text": "Ciao è bello $c0012", "to": {"player": target.player}}))["recipients"] == 1
    assert ok(await client.call("echo", {"text": "ciao", "to": {"room": target.room}}))["recipients"] >= 1
    assert ok(await client.call("echo", {"text": "ciao a tutti", "to": {"all": True}}))["recipients"] >= 1
    err(await client.call("echo", {"text": "emoji \U0001f600", "to": {"all": True}}), "unencodable_text")
    err(await client.call("echo", {"text": "a\nb", "to": {"all": True}}), "bad_params")
    err(await client.call("echo", {"text": "x" * 401, "to": {"all": True}}), "bad_params")
    err(await client.call("echo", {"text": "", "to": {"all": True}}), "bad_params")
    err(await client.call("echo", {"text": "x", "to": {"all": True, "room": 1}}), "bad_params")
    err(await client.call("echo", {"text": "x", "to": {"player": "Nessuno"}}), "not_found")
    err(await client.call("echo", {"text": "x"}), "bad_params")


# ---- limiti, audit, sicurezza --------------------------------------------------------------------------------------------


async def test_audit_trail(client: LiveClient, target: Target) -> None:
    """Le scritture lasciano una riga di audit con attore e comando; mai il token."""
    if target.kind == "real" and not target.audit_lines():
        return  # server esterno senza LIVECTL_TEST_AUDIT
    ok(await client.call("echo", {"text": "audit", "to": {"player": target.player}}))
    lines = "\n".join(target.audit_lines())
    assert "cmd=hello" in lines and "cmd=echo" in lines and "actor=pytest" in lines
    assert target.token not in lines


async def test_too_many_connections(target: Target) -> None:
    """Oltre `max_conn` connessioni: la successiva riceve `too_many_connections` e viene chiusa."""
    held = []
    try:
        for _ in range(target.max_conn):
            c = await LiveClient.connect(target.socket)
            ok(await c.hello(target.token))
            held.append(c)
        extra = await LiveClient.connect(target.socket)
        held.append(extra)
        resp = await extra.read()
        assert resp is not None
        err(resp, "too_many_connections")
    finally:
        for c in held:
            await c.close()
    await asyncio.sleep(0.8)  # il server deve accorgersi delle chiusure


async def test_zz_rate_limit(client: LiveClient) -> None:
    """Una raffica di richieste supera il limite: `rate_limited` o `busy`, mai un crash; poi il canale riprende."""
    n = 80
    await client.send_raw(b"".join(json.dumps({"id": i, "cmd": "ping"}).encode() + b"\n" for i in range(1, n + 1)))
    codes = []
    for _ in range(n):
        resp = await client.read(15)
        assert resp is not None
        codes.append("ok" if resp["ok"] else resp["error"]["code"])
    assert set(codes) <= {"ok", "rate_limited", "busy"} and codes.count("ok") < n
    await asyncio.sleep(1.5)
    ok(await client.call("ping"))


async def test_garbage_does_not_break_the_server(target: Target) -> None:
    """Righe casuali, nidificazioni profonde e binari: la connessione puo' chiudersi, il server no."""
    import random

    rnd = random.Random(1234)
    garbage = [bytes(rnd.randrange(256) for _ in range(rnd.randrange(1, 300))).replace(b"\n", b" ") + b"\n" for _ in range(15)]
    garbage += [b"[" * 3000 + b"\n", b"{" * 3000 + b"\n", b'{"id":1,"cmd":"ping","params":' + b"[" * 50 + b"\n", b"\xff\xfe\x00\n"]
    c = await LiveClient.connect(target.socket)
    try:
        ok(await c.hello(target.token))
        for g in garbage:
            await c.send_raw(g)
            await asyncio.sleep(0.05)
        await asyncio.sleep(1.5)
    finally:
        await c.close()
    fresh = await LiveClient.connect(target.socket)
    try:
        ok(await fresh.hello(target.token))
        ok(await fresh.call("ping"))
    finally:
        await fresh.close()
