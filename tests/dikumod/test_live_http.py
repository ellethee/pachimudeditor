"""Canale live via `/api/world/live` contro il FINTO server: permessi, capability, sola lettura, mappatura degli errori, immortali,
canale spento, e integrazione con i giocatori su file (`online`, conferma «server acceso»)."""

import asyncio
import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio

from pachimudeditor_adapter_dikumod import live as live_module
from pachimudeditor.common.adapters import registry as registry_module
from pachimudeditor.common.adapters.registry import WorldConfig, WorldRegistry, set_registry
from tests.helpers import data, error_code
from tests.support import stack
from tests.support.dikumod_players import standard_players
from tests.support.live_fake_server import FakeLiveServer
from tests.support.live_scripted import Scripted

TOKEN = "k" * 20 + "9" * 20
ENV = "TEST_LIVE_TOKEN"
H = {"X-World": "dikumod"}
LIVE = "/api/world/live"


@pytest_asyncio.fixture
async def fake(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakeLiveServer]:
    """Il finto server su un socket temporaneo (percorso breve) e il token nell'ambiente."""
    tmp = Path(tempfile.mkdtemp(prefix="lh-", dir="/tmp"))
    monkeypatch.setenv(ENV, TOKEN)
    server = FakeLiveServer(tmp / "l.sock", TOKEN)
    await server.start()
    yield server
    await server.stop()  # `worlds` (che dipende da questa fixture) ha gia' chiuso le connessioni dei client
    shutil.rmtree(tmp, ignore_errors=True)


def world(world_id: str, lib: Path, variant: str, sock: str | None, **config: Any) -> WorldConfig:
    """Un mondo dikumod, con il canale live se c'e' `sock`."""
    params: dict[str, Any] = {"variant": variant}
    if sock:
        params["live"] = {"socket": sock, "token_env": ENV, "timeout_ms": 1500}
    return WorldConfig(id=world_id, kind="dikumod", name=world_id, path=str(lib), params=params, **config)


@pytest_asyncio.fixture(autouse=True)
async def worlds(lib: Path, variant: str, fake: FakeLiveServer, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """`dikumod` (scrivibile, live), `dikumod-ro` (sola lettura, live), `dikumod-nolive` (scrivibile, senza canale) e pachimud.
    La cache di `who` e' spenta (i test cambiano il MUD fra una richiesta e l'altra); `test_who_cache` la riaccende."""
    monkeypatch.setattr(live_module, "WHO_TTL", 0.0)
    standard_players(lib)
    sock = fake.path
    set_registry(
        WorldRegistry(
            [
                WorldConfig(id="pachimud", name="Pachimud", params=stack.current_params()),
                world("dikumod", lib, variant, sock, read_only=False),
                world("dikumod-ro", lib, variant, sock),
                world("dikumod-nolive", lib, variant, None, read_only=False),
            ]
        )
    )
    yield
    await registry_module._registry.aclose_all()  # noqa: SLF001
    set_registry(None)


@pytest_asyncio.fixture
async def plain(anon: httpx.AsyncClient) -> httpx.AsyncClient:
    """Client autenticato come utente NON superuser."""
    from pachifast.auth.cruds import create_user
    from pachifast.auth.schemas import UserCreate
    from pachifast.database.engine import get_core_sessionmaker

    async with get_core_sessionmaker()() as session:
        try:
            await create_user(session, UserCreate(username="semplice", password=stack.TEST_PASSWORD, is_superuser=False))
        except Exception:  # noqa: BLE001  (gia' creato da un test precedente)
            await session.rollback()
    response = await anon.post("/api/auth/token", data={"username": "semplice", "password": stack.TEST_PASSWORD})
    anon.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return anon


# ------------------------------------------------------------------------------------------------------------ permessi


async def test_capability_only_where_configured(client: httpx.AsyncClient) -> None:
    """`supportsLive` solo per i mondi dikumod con `params.live`."""
    caps = {w["id"]: w["capabilities"]["supportsLive"] for w in data(await client.get("/api/worlds"))}
    assert caps == {"pachimud": False, "dikumod": True, "dikumod-ro": True, "dikumod-nolive": False}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/status", None), ("GET", "/who", None), ("GET", "/info", None), ("GET", "/zones", None), ("GET", "/players/tester", None),
        ("PATCH", "/players/tester", {"fields": {"gold": 1}}), ("POST", "/zones/reset", {"zone": 1}),
        ("POST", "/load/mob", {"vnum": 3000, "room": 3001}), ("POST", "/load/obj", {"vnum": 3001, "room": 3001}),
        ("POST", "/echo", {"text": "x", "all": True}),
    ],
)  # fmt: skip
async def test_every_route_requires_superuser(
    anon: httpx.AsyncClient, plain: httpx.AsyncClient, fake: FakeLiveServer, method: str, path: str, body: Any
) -> None:
    """Nessuna sessione: 401. Utente non superuser: 403 `access.superuser_required`, e il MUD non vede nulla."""
    async with httpx.AsyncClient(transport=anon._transport, base_url="http://test") as nobody:  # noqa: SLF001
        assert (await nobody.request(method, LIVE + path, json=body, headers=H)).status_code == 401
    response = await plain.request(method, LIVE + path, json=body, headers=H)
    assert error_code(response, 403) == "access.superuser_required"
    assert fake.calls == [] and fake.audit == []


async def test_capability_missing_and_read_only(client: httpx.AsyncClient, fake: FakeLiveServer) -> None:
    """Senza capability 409 `world.capability_missing` (anche per pachimud); mondo `read_only`: letture si', scritture 409 `world.read_only`."""
    for world_id in ("dikumod-nolive", "pachimud"):
        r = await client.get(f"{LIVE}/status", headers={"X-World": world_id})
        assert error_code(r, 409) == "world.capability_missing" and r.json()["detail"][0]["params"]["capability"] == "supports_live"
    ro = {"X-World": "dikumod-ro"}
    assert data(await client.get(f"{LIVE}/who", headers=ro))["count"] == 2
    writes = [
        ("PATCH", "/players/tester", {"fields": {"gold": 1}}), ("POST", "/zones/reset", {"zone": 1}),
        ("POST", "/load/mob", {"vnum": 3000, "room": 3001}), ("POST", "/load/obj", {"vnum": 3001, "room": 3001}),
        ("POST", "/echo", {"text": "x", "all": True}),
    ]  # fmt: skip
    for method, path, body in writes:
        assert error_code(await client.request(method, LIVE + path, json=body, headers=ro), 409) == "world.read_only"
    assert [c for c, _ in fake.calls if c in ("player.set", "zone.reset", "load.mob", "load.obj", "echo")] == []


# ------------------------------------------------------------------------------------------------------------- letture


async def test_status_who_info_zones_player(client: httpx.AsyncClient, fake: FakeLiveServer) -> None:
    """Stato (versione, classi, comandi, latenza; mai socket o token) e letture."""
    response = await client.get(f"{LIVE}/status", headers=H)
    status = data(response)
    assert status["state"] == "connected" and status["reachable"] and status["protocol"] == 1 and status["classes"] == ["read", "write"]
    assert "player.set" in status["commands"] and "gold" in status["editableFields"] and isinstance(status["latencyMs"], int)
    assert fake.path not in response.text and TOKEN not in response.text and "socket" not in response.text.lower()
    who = data(await client.get(f"{LIVE}/who", headers=H))
    assert {p["name"]: p["state"] for p in who["players"]} == {"Tester": "playing", "Ghost": "linkdead"} and who["truncated"] is False
    info = data(await client.get(f"{LIVE}/info", headers=H))
    assert info["world"]["zones"] == 5 and info["players"]["playing"] == 1 and info["uptimeS"] >= 0
    zones = data(await client.get(f"{LIVE}/zones", headers=H))["zones"]
    assert zones[3] == {"index": 3, "num": 14, "name": "Midgaard", "top": 3999, "lifespan": 20, "age": 0, "resetMode": 2, "started": True}
    player = data(await client.get(f"{LIVE}/players/Tester", headers=H))
    assert player["fields"]["gold"] == 150 and player["fields"]["levels"] == {"cleric": 3} and "levels" in player["editableFields"]


async def test_read_error_mapping(client: httpx.AsyncClient) -> None:
    """Giocatore inesistente 404, non in gioco 409, nome non valido 404 (mai inviato al MUD)."""
    r = await client.get(f"{LIVE}/players/nessuno", headers=H)
    assert error_code(r, 404) == "worldlive.not_found" and r.json()["detail"][0]["params"]["what"] == "player"
    assert error_code(await client.get(f"{LIVE}/players/ghost", headers=H), 409) == "worldlive.player_not_playing"
    assert error_code(await client.get(f"{LIVE}/players/..%2Fx", headers=H), 404) in ("worldlive.not_found", None)
    assert error_code(await client.get(f"{LIVE}/players/9bad", headers=H), 404) == "worldlive.not_found"


# ------------------------------------------------------------------------------------------------------------ scritture


async def test_patch_player_saves_by_default_and_audits_actor(client: httpx.AsyncClient, fake: FakeLiveServer) -> None:
    """`save` e' vero di default; `save: false` non salva; l'attore dell'audit del MUD e' l'utente dell'editor."""
    out = data(await client.patch(f"{LIVE}/players/tester", json={"fields": {"gold": 999, "conditions": {"drunk": 0}}}, headers=H))
    assert out["saved"] is True and out["applied"]["gold"] == {"old": 150, "new": 999} and out["applied"]["conditions.drunk"]["new"] == 0
    assert fake.saves == ["Tester"] and fake.players["tester"]["fields"]["gold"] == 999
    out = data(await client.patch(f"{LIVE}/players/tester", json={"fields": {"gold": 5}, "save": False}, headers=H))
    assert out["saved"] is False and fake.saves == ["Tester"]
    assert any(f"actor={stack.TEST_USER} cmd=player.set" in line for line in fake.audit)


async def test_patch_error_mapping_and_immortal_confirmation(client: httpx.AsyncClient, fake: FakeLiveServer) -> None:
    """Fuori intervallo 422 con campo e limiti, campo non modificabile 422, classe non posseduta 409; livello >= 51 solo con `confirmImmortal`."""
    r = await client.patch(f"{LIVE}/players/tester", json={"fields": {"gold": -5}}, headers=H)
    detail = r.json()["detail"][0]
    assert error_code(r, 422) == "worldlive.value_out_of_range" and detail["params"]["field"] == "gold" and "gold" in detail["msg"]
    assert (
        error_code(await client.patch(f"{LIVE}/players/tester", json={"fields": {"maxHit": 9}}, headers=H), 422) == "worldlive.bad_params"
    )
    r = await client.patch(f"{LIVE}/players/tester", json={"fields": {"levels": {"warrior": 5}}}, headers=H)
    assert error_code(r, 409) == "worldlive.class_not_owned" and "warrior" in r.json()["detail"][0]["msg"]
    # immortale: senza conferma niente cambia (nemmeno gli altri campi della stessa richiesta)
    r = await client.patch(f"{LIVE}/players/tester", json={"fields": {"gold": 1, "levels": {"cleric": 55}}}, headers=H)
    assert error_code(r, 409) == "worldlive.immortal_confirmation_required" and "55" in r.json()["detail"][0]["msg"]
    assert fake.players["tester"]["fields"]["gold"] == 150 and fake.players["tester"]["levels"] == {"cleric": 3}
    ok = data(await client.patch(f"{LIVE}/players/tester", json={"fields": {"levels": {"cleric": 55}}, "confirmImmortal": True}, headers=H))
    assert ok["warnings"] == ["immortal_level"] and fake.players["tester"]["levels"] == {"cleric": 55}
    assert error_code(await client.patch(f"{LIVE}/players/tester", json={"fields": {}}, headers=H), 422) is None  # validazione Pydantic
    assert (
        error_code(await client.patch(f"{LIVE}/players/ghost", json={"fields": {"gold": 1}}, headers=H), 409)
        == "worldlive.player_not_playing"
    )


async def test_zone_reset_load_and_echo(client: httpx.AsyncClient, fake: FakeLiveServer) -> None:
    """Reset per indice o stanza, creazione di mob e oggetti, messaggi; regole del MUD mappate (zona 0, deny-list, testo non latin-1)."""
    assert data(await client.post(f"{LIVE}/zones/reset", json={"zone": 3}, headers=H)) == {"zone": 3, "name": "Midgaard", "executed": True}
    assert data(await client.post(f"{LIVE}/zones/reset", json={"room": 3001, "onlyIfEmpty": True}, headers=H))["executed"] is False
    assert fake.resets == [3]
    assert error_code(await client.post(f"{LIVE}/zones/reset", json={"zone": 0}, headers=H), 409) == "worldlive.zone_forbidden"
    assert error_code(await client.post(f"{LIVE}/zones/reset", json={"zone": 1, "room": 2}, headers=H), 422) is None
    assert error_code(await client.post(f"{LIVE}/zones/reset", json={"zone": 99}, headers=H), 404) == "worldlive.not_found"
    mob = data(await client.post(f"{LIVE}/load/mob", json={"vnum": 3000, "room": 3001, "count": 2}, headers=H))
    assert [m["name"] for m in mob["loaded"]] == ["Magus", "Magus"]
    obj = data(await client.post(f"{LIVE}/load/obj", json={"vnum": 3001, "player": "Tester"}, headers=H))
    assert obj["loaded"][0]["where"] == "player"
    r = await client.post(f"{LIVE}/load/obj", json={"vnum": 1600, "room": 3001}, headers=H)
    assert error_code(r, 409) == "worldlive.object_denied" and "1600" in r.json()["detail"][0]["msg"]
    assert error_code(await client.post(f"{LIVE}/load/mob", json={"vnum": 1, "room": 3001}, headers=H), 404) == "worldlive.not_found"
    assert error_code(await client.post(f"{LIVE}/load/mob", json={"vnum": 3000, "room": 3001, "count": 11}, headers=H), 422) is None
    assert error_code(await client.post(f"{LIVE}/load/mob", json={"vnum": 3000, "player": "../x"}, headers=H), 422) is None
    assert data(await client.post(f"{LIVE}/echo", json={"text": "Benvenuti", "all": True}, headers=H)) == {"recipients": 1}
    assert data(await client.post(f"{LIVE}/echo", json={"text": "ciao", "player": "Tester"}, headers=H))["recipients"] == 1
    assert fake.echoes == [("all", "Benvenuti"), ("player", "ciao")]
    assert (
        error_code(await client.post(f"{LIVE}/echo", json={"text": "ciao ☃", "all": True}, headers=H), 422) == "worldlive.unencodable_text"
    )
    assert error_code(await client.post(f"{LIVE}/echo", json={"text": "x"}, headers=H), 422) is None
    assert error_code(await client.post(f"{LIVE}/echo", json={"text": "x", "all": True, "room": 1}, headers=H), 422) is None


async def test_writes_disabled_in_the_mud(client: httpx.AsyncClient, fake: FakeLiveServer) -> None:
    """Le scritture disattivate nel MUD (classe `write` spenta): il comando non e' in `hello` e la rotta risponde 409 `worldlive.command_disabled`."""
    fake.write = False
    status = data(await client.get(f"{LIVE}/status", headers=H))
    assert status["classes"] == ["read"] and status["editableFields"] == []
    assert error_code(await client.post(f"{LIVE}/echo", json={"text": "x", "all": True}, headers=H), 409) == "worldlive.command_disabled"
    assert (
        error_code(await client.patch(f"{LIVE}/players/tester", json={"fields": {"gold": 1}}, headers=H), 409)
        == "worldlive.command_disabled"
    )
    assert fake.echoes == []


# ---------------------------------------------------------------------------------------------------- canale non pronto


async def test_channel_off_is_a_state_and_clear_errors(
    client: httpx.AsyncClient, fake: FakeLiveServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MUD spento: `status` 200 `unreachable`, le altre rotte 503 `worldlive.unreachable`. Token assente o sbagliato: stati e codici propri."""
    monkeypatch.delenv(ENV)
    assert data(await client.get(f"{LIVE}/status", headers=H))["state"] == "token_missing"
    assert error_code(await client.get(f"{LIVE}/who", headers=H), 503) == "worldlive.token_missing"
    monkeypatch.setenv(ENV, "sbagliato-" + "z" * 30)
    r = await client.get(f"{LIVE}/status", headers=H)
    assert data(r)["state"] == "auth_failed" and "sbagliato" not in r.text
    assert error_code(await client.get(f"{LIVE}/who", headers=H), 503) == "worldlive.auth_failed"
    monkeypatch.setenv(ENV, TOKEN)
    await registry_module._registry.aclose_all()  # noqa: SLF001
    await fake.stop()
    status = data(await client.get(f"{LIVE}/status", headers=H))
    assert (status["state"], status["reachable"], status["code"]) == ("unreachable", False, "worldlive.unreachable")
    assert error_code(await client.get(f"{LIVE}/who", headers=H), 503) == "worldlive.unreachable"
    assert error_code(await client.post(f"{LIVE}/echo", json={"text": "x", "all": True}, headers=H), 503) == "worldlive.unreachable"


async def test_timeout_and_unknown_outcome(client: httpx.AsyncClient, lib: Path, variant: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """MUD che non risponde: lettura 504 `worldlive.timeout`, scrittura 504 `worldlive.outcome_unknown` (mai ritentata)."""
    tmp = Path(tempfile.mkdtemp(prefix="lt-", dir="/tmp"))
    silent = Scripted(tmp / "s.sock", lambda *_: asyncio.sleep(0, result=False))

    async def never(_n: int, _req: dict[str, Any], _w: asyncio.StreamWriter) -> bool:
        """Non risponde mai."""
        return False

    silent.behavior = never
    await silent.start()
    config = world("lento", lib, variant, str(tmp / "s.sock"), read_only=False)
    config.params["live"]["timeout_ms"] = 300
    set_registry(WorldRegistry([WorldConfig(id="pachimud", name="P", params=stack.current_params()), config]))
    try:
        slow = {"X-World": "lento"}
        assert error_code(await client.get(f"{LIVE}/who", headers=slow), 504) == "worldlive.timeout"
        assert (
            error_code(await client.post(f"{LIVE}/echo", json={"text": "x", "all": True}, headers=slow), 504) == "worldlive.outcome_unknown"
        )
        assert [r["cmd"] for r in silent.requests].count("echo") == 1
    finally:
        await registry_module._registry.aclose_all()  # noqa: SLF001
        await silent.stop()
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------------------------- integrazione giocatori su file

PLAYERS = "/api/world/players"


def connect(fake: FakeLiveServer, name: str, state: str = "playing") -> None:
    """Fa risultare connesso (nel MUD finto) un giocatore che esiste anche su file."""
    fake.players[name.lower()] = FakeLiveServer._new_player(name, {"warrior": 12}, state)  # noqa: SLF001


async def test_players_online_from_channel(client: httpx.AsyncClient, fake: FakeLiveServer) -> None:
    """Con il canale raggiungibile `online` e' vero/falso (anche per un collegamento caduto); senza canale resta sconosciuto."""
    connect(fake, "Tizio")
    connect(fake, "Caio", "linkdead")
    rows = {p["id"]: p for p in data(await client.get(PLAYERS, headers=H))["items"]}
    assert {k: v["online"] for k, v in rows.items()} == {"tizio": True, "caio": True, "sempronio": False, "mevio": False}
    assert rows["tizio"]["extra"]["liveState"] == "playing" and rows["caio"]["extra"]["liveState"] == "linkdead"
    assert data(await client.get(f"{PLAYERS}/tizio", headers=H))["online"] is True
    assert data(await client.get(f"{PLAYERS}/mevio", headers=H))["online"] is False
    # mondo senza canale: sconosciuto, come prima
    nolive = {"X-World": "dikumod-nolive"}
    assert {p["online"] for p in data(await client.get(PLAYERS, headers=nolive))["items"]} == {None}
    # canale spento: sconosciuto (nessun errore)
    await registry_module._registry.aclose_all()  # noqa: SLF001
    await fake.stop()
    assert {p["online"] for p in data(await client.get(PLAYERS, headers=H))["items"]} == {None}
    assert data(await client.get(f"{PLAYERS}/status", headers=H))["serverRunning"] is None


async def test_file_write_of_connected_player_needs_server_confirmation(client: httpx.AsyncClient, fake: FakeLiveServer, lib: Path) -> None:
    """Giocatore connesso: la scrittura su file e' «server acceso» certo (409 senza `confirmServerRunning`). Non connesso ma server su (canale
    risponde): resta l'avviso best-effort. Canale spento: si scrive come prima."""
    body = {"details": {"title": "il Nuovo"}}
    connect(fake, "Tizio")
    status = data(await client.get(f"{PLAYERS}/status", headers=H))
    assert (status["serverRunning"], status["detection"]) == (True, "live")
    r = await client.patch(f"{PLAYERS}/tizio", json=body, headers=H)
    assert error_code(r, 409) == "worldplayers.server_running"
    assert (lib / "players" / ".tizio.dat.bak").exists() is False
    assert (
        data(await client.patch(f"{PLAYERS}/tizio", json={**body, "confirmServerRunning": True}, headers=H))["details"]["title"]
        == "il Nuovo"
    )
    # Mevio non e' connesso, il server e' acceso: avviso best-effort (stesso codice, si conferma)
    assert error_code(await client.patch(f"{PLAYERS}/mevio", json=body, headers=H), 409) == "worldplayers.server_running"
    assert (
        data(await client.patch(f"{PLAYERS}/mevio", json={**body, "confirmServerRunning": True}, headers=H))["details"]["title"]
        == "il Nuovo"
    )
    # inventario: stessa regola
    r = await client.delete(f"{PLAYERS}/tizio/inventory/items/0", headers=H)
    assert error_code(r, 409) == "worldplayers.server_running"
    # mondo senza canale: nessuna conferma (il server non e' rilevabile)
    assert data(await client.patch(f"{PLAYERS}/caio", json=body, headers={"X-World": "dikumod-nolive"}))["details"]["title"] == "il Nuovo"
    # canale spento: come senza canale
    await registry_module._registry.aclose_all()  # noqa: SLF001
    await fake.stop()
    assert data(await client.patch(f"{PLAYERS}/sempronio", json=body, headers=H))["details"]["title"] == "il Nuovo"


async def test_who_cache_is_short_and_failures_do_not_slow_the_list(
    client: httpx.AsyncClient, fake: FakeLiveServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Piu' richieste ravvicinate usano un solo `who`; dopo la scadenza si interroga di nuovo."""
    monkeypatch.setattr(live_module, "WHO_TTL", 60.0)
    for _ in range(3):
        data(await client.get(PLAYERS, headers=H))
        data(await client.get(f"{PLAYERS}/tizio", headers=H))
    assert [c for c, _ in fake.calls].count("who") == 1
    monkeypatch.setattr(live_module, "WHO_TTL", 0.0)
    data(await client.get(PLAYERS, headers=H))
    assert [c for c, _ in fake.calls].count("who") == 2
