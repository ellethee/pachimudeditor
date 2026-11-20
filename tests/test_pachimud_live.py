"""Canale live del mondo pachimud contro il FINTO server (profilo pachimud): capability dal `hello`, `who`/`player.get`/`zone.list` con i
formati del gioco, `zone.reload`, `instances.list`, comandi assenti (409), sola lettura e permessi."""

import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio

from pachimudeditor.common.adapters import registry as registry_module
from pachimudeditor.common.adapters.registry import WorldConfig, WorldRegistry, set_registry
from tests.helpers import data, error_code
from tests.support import stack
from tests.support.live_fake_server import FakePachimudServer

TOKEN = "p" * 20 + "7" * 20
ENV = "TEST_PACHIMUD_LIVE_TOKEN"
LIVE = "/api/world/live"
H = {"X-World": "pachimud"}


@pytest_asyncio.fixture
async def fake(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakePachimudServer]:
    """Il finto server (profilo pachimud) su un socket temporaneo e il token nell'ambiente."""
    tmp = Path(tempfile.mkdtemp(prefix="lp-", dir="/tmp"))
    monkeypatch.setenv(ENV, TOKEN)
    server = FakePachimudServer(tmp / "l.sock", TOKEN)
    await server.start()
    yield server
    await server.stop()
    shutil.rmtree(tmp, ignore_errors=True)


def world(world_id: str, sock: str | None, **config: Any) -> WorldConfig:
    """Un mondo pachimud (stessi file dei test), con il canale live se c'e' `sock`."""
    params: dict[str, Any] = dict(stack.current_params())
    if sock:
        params["live"] = {"socket": sock, "token_env": ENV, "timeout_ms": 1500}
    return WorldConfig(id=world_id, kind="pachimud", name=world_id, params=params, **config)


@pytest_asyncio.fixture(autouse=True)
async def worlds(fake: FakePachimudServer) -> AsyncIterator[None]:
    """`pachimud` (scrivibile, live), `pachimud-ro` (sola lettura, live), `pachimud-nolive`."""
    set_registry(
        WorldRegistry(
            [world("pachimud", fake.path, read_only=False), world("pachimud-ro", fake.path, read_only=True), world("pachimud-nolive", None)]
        )
    )
    yield
    await registry_module._registry.aclose_all()  # noqa: SLF001
    set_registry(None)


async def test_capabilities(client: httpx.AsyncClient) -> None:
    """`supportsLive` solo con `params.live`; mai l'inventario live (il gioco non lo ha)."""
    worlds_ = {w["id"]: w["capabilities"] for w in data(await client.get("/api/worlds"))}
    assert {k: v["supportsLive"] for k, v in worlds_.items()} == {"pachimud": True, "pachimud-ro": True, "pachimud-nolive": False}
    assert not any(v["supportsLiveInventory"] for v in worlds_.values())
    r = await client.get(f"{LIVE}/status", headers={"X-World": "pachimud-nolive"})
    assert error_code(r, 409) == "world.capability_missing"


async def test_status_discovery(client: httpx.AsyncClient) -> None:
    """Il `hello` dichiara comandi ed estensioni: niente `player.set`/`load.*`/`echo`, features solo di contenuti e bacheche, campi di sola lettura."""
    status = data(await client.get(f"{LIVE}/status", headers=H))
    assert (
        status["state"] == "connected"
        and status["mud"]["kind"] == "pachimud"
        and status["features"] == ["content.validate", "content.reload", "board.delete", "board.clear"]
    )
    assert {"zone.reload", "instances.list", "zone.reset"} <= set(status["commands"])
    assert not {"player.set", "load.mob", "load.obj", "echo", "player.inventory"} & set(status["commands"])
    assert status["editableFields"] == []


async def test_reads(client: httpx.AsyncClient) -> None:
    """Formati di pachimud: razza stringa, `levels` della sola classe, zone con `bottom`, campi senza `move`."""
    who = data(await client.get(f"{LIVE}/who", headers=H))
    tester = next(p for p in who["players"] if p["name"] == "Tester")
    assert tester["race"] == "human" and tester["levels"] == {"warrior": 5} and tester["zone"] == 10 and tester["sex"] == 1
    zones = data(await client.get(f"{LIVE}/zones", headers=H))["zones"]
    assert zones[0]["index"] == zones[0]["num"] == 10 and zones[0]["bottom"] == 1000 and zones[0]["top"] == 1099
    fields = data(await client.get(f"{LIVE}/players/tester", headers=H))["fields"]
    assert fields["level"] == 5 and fields["roomVnum"] == 1001 and "move" not in fields
    assert error_code(await client.get(f"{LIVE}/players/ghost", headers=H), 409) == "worldlive.player_not_playing"


async def test_zone_reload(client: httpx.AsyncClient, fake: FakePachimudServer) -> None:
    """`POST /zones/reload`: conteggi, audit con l'attore; zona sconosciuta 404; sola lettura 409; mai ritentato."""
    out = data(await client.post(f"{LIVE}/zones/reload", json={"vnum": 10}, headers=H))
    assert out == {"zone": 10, "name": "Zona Alfa", "reloaded": True, "rooms": 3, "mobs": 2, "objects": 4}
    assert fake.reloaded == [10] and any(f"actor={stack.TEST_USER} cmd=zone.reload" in line for line in fake.audit)
    assert error_code(await client.post(f"{LIVE}/zones/reload", json={"vnum": 77}, headers=H), 404) == "worldlive.not_found"
    assert (
        error_code(await client.post(f"{LIVE}/zones/reload", json={"vnum": 10}, headers={"X-World": "pachimud-ro"}), 409)
        == "world.read_only"
    )
    assert fake.reloaded == [10]


async def test_zone_reload_failed_is_explained(client: httpx.AsyncClient, fake: FakePachimudServer) -> None:
    """`reload_failed`: 409 con messaggio chiaro (zona intatta), non un errore generico."""
    fake.broken_zones.add(10)
    r = await client.post(f"{LIVE}/zones/reload", json={"vnum": 10}, headers=H)
    assert error_code(r, 409) == "worldlive.reload_failed"
    assert "10" in r.json()["detail"][0]["msg"] and "rimasta" in r.json()["detail"][0]["msg"]


async def test_zone_reload_failed_carries_file_and_line_from_validate(client: httpx.AsyncClient, fake: FakePachimudServer) -> None:
    """Il gioco non dice quale file e' rotto: l'adapter lo ricava da `content.validate` e li mette in `issues` (solo errori)."""
    fake.broken_zones.add(10)
    fake.content_errors = [
        {"severity": "warning", "code": "translation-missing", "message": "manca en", "file": "a.yaml", "line": 3},
        {"severity": "error", "code": "yaml-syntax", "message": "YAML non valido", "file": "zones/Z/mobs.yaml", "line": 7},
    ]
    r = await client.post(f"{LIVE}/zones/reload", json={"vnum": 10}, headers=H)
    assert error_code(r, 409) == "worldlive.reload_failed"
    params = r.json()["detail"][0]["params"]
    assert [(i["file"], i["line"]) for i in params["issues"]] == [("zones/Z/mobs.yaml", 7)]
    fake.content_errors = []  # validate non trova nulla: resta l'errore semplice, senza problemi
    r = await client.post(f"{LIVE}/zones/reload", json={"vnum": 10}, headers=H)
    assert error_code(r, 409) == "worldlive.reload_failed" and "issues" not in r.json()["detail"][0]["params"]


async def test_zone_reload_disabled_without_allow_write(client: httpx.AsyncClient, fake: FakePachimudServer) -> None:
    """Gioco con `allow_write: false`: il comando non c'e', 409 `worldlive.command_disabled`."""
    fake.write = False
    r = await client.post(f"{LIVE}/zones/reload", json={"vnum": 10}, headers=H)
    assert error_code(r, 409) == "worldlive.command_disabled"
    assert data(await client.get(f"{LIVE}/status", headers=H))["classes"] == ["read"]


async def test_instances(client: httpx.AsyncClient) -> None:
    """`GET /instances`: per stanza, mob o oggetto; `limit` e `truncated`; un solo criterio (422)."""
    out = data(await client.get(f"{LIVE}/instances", params={"roomVnum": 1001}, headers=H))
    assert out["count"] == 3 and {i["kind"] for i in out["instances"]} == {"mob", "obj"} and out["instances"][0]["roomVnum"] == 1001
    mobs = data(await client.get(f"{LIVE}/instances", params={"mobVnum": 5000, "limit": 1}, headers=H))
    assert mobs["count"] == 1 and mobs["truncated"] is True and mobs["instances"][0]["instanceId"] == 1
    zone = data(await client.get(f"{LIVE}/instances", params={"zoneVnum": 10}, headers=H))
    assert zone["count"] == 4
    assert error_code(await client.get(f"{LIVE}/instances", params={"zoneVnum": 99}, headers=H), 404) == "worldlive.not_found"
    assert error_code(await client.get(f"{LIVE}/instances", headers=H), 422) == "worldlive.bad_params"
    both = {"roomVnum": 1, "mobVnum": 2}
    assert error_code(await client.get(f"{LIVE}/instances", params=both, headers=H), 422) == "worldlive.bad_params"
    assert data(await client.get(f"{LIVE}/instances", params={"roomVnum": 1001}, headers={"X-World": "pachimud-ro"}))["count"] == 3


async def test_missing_commands_are_409(client: httpx.AsyncClient, fake: FakePachimudServer) -> None:
    """`player.set`, `load.*` e `echo` non esistono nel gioco: 409 `worldlive.command_disabled`."""
    calls = [("PATCH", "/players/tester", {"fields": {"gold": 1}}), ("POST", "/load/mob", {"vnum": 5000, "room": 1001}),
             ("POST", "/echo", {"text": "x", "all": True})]  # fmt: skip
    for method, path, body in calls:
        r = await client.request(method, LIVE + path, json=body, headers=H)
        assert error_code(r, 409) in ("worldlive.command_disabled", "world.capability_missing")
    assert fake.calls == []


async def test_requires_superuser(anon: httpx.AsyncClient) -> None:
    """Senza sessione 401 anche per le nuove rotte."""
    async with httpx.AsyncClient(transport=anon._transport, base_url="http://test") as nobody:  # noqa: SLF001
        assert (await nobody.post(f"{LIVE}/zones/reload", json={"vnum": 1}, headers=H)).status_code == 401
        assert (await nobody.get(f"{LIVE}/instances?roomVnum=1", headers=H)).status_code == 401


async def test_content_validate_and_reload(client: httpx.AsyncClient, fake: FakePachimudServer) -> None:
    """`content.validate` (lettura) e `content.reload` (scrittura, audit con l'attore); comandi nelle capability del `hello`."""
    status = data(await client.get(f"{LIVE}/status", headers=H))
    assert {"content.validate", "content.reload"} <= set(status["commands"]) and "content.reload" in status["features"]
    ok = data(await client.get(f"{LIVE}/content/validate", headers=H))
    assert ok == {"ok": True, "errors": 0, "warnings": 0, "issues": []}
    out = data(await client.post(f"{LIVE}/content/reload", json={"kind": "skills"}, headers=H))
    assert out["ok"] and out["kind"] == "skills" and out["reloaded"]["skills"] == ["fireball"]
    assert fake.content_reloads == ["skills"] and any(f"actor={stack.TEST_USER} cmd=content.reload" in line for line in fake.audit)
    assert (await client.post(f"{LIVE}/content/reload", json={"kind": "mondo"}, headers=H)).status_code == 422
    r = await client.post(f"{LIVE}/content/reload", json={"kind": "all"}, headers={"X-World": "pachimud-ro"})
    assert error_code(r, 409) == "world.read_only" and fake.content_reloads == ["skills"]


async def test_content_issues_and_reload_failed(client: httpx.AsyncClient, fake: FakePachimudServer) -> None:
    """Problemi con file e riga in `validate`; con un errore `reload` fallisce 409 `worldlive.content_reload_failed` e porta i problemi."""
    fake.content_errors = [
        {"severity": "warning", "code": "translation-missing", "message": "manca en", "file": "skills/a.yaml", "line": 3},
        {"severity": "error", "code": "skill-unknown", "message": "la skill 'x' non esiste", "file": "zones/Z/mobs.yaml", "line": 98},
    ]
    out = data(await client.get(f"{LIVE}/content/validate", headers=H))
    assert (
        (out["ok"], out["errors"], out["warnings"]) == (False, 1, 1)
        and out["issues"][1]["file"] == "zones/Z/mobs.yaml"
        and out["issues"][1]["line"] == 98
    )
    r = await client.post(f"{LIVE}/content/reload", json={"kind": "all"}, headers=H)
    assert error_code(r, 409) == "worldlive.content_reload_failed"
    detail = r.json()["detail"][0]
    assert detail["params"]["issues"][0] == {
        "severity": "error",
        "code": "skill-unknown",
        "message": "la skill 'x' non esiste",
        "file": "zones/Z/mobs.yaml",
        "line": 98,
    }
    assert fake.content_reloads == []
    fake.content_errors = fake.content_errors[:1]  # solo avvisi: si ricarica
    assert data(await client.get(f"{LIVE}/content/validate", params={"strict": "true"}, headers=H))["ok"] is False
    assert data(await client.post(f"{LIVE}/content/reload", json={"kind": "all"}, headers=H))["ok"]


async def test_content_commands_disabled_without_allow_write(client: httpx.AsyncClient, fake: FakePachimudServer) -> None:
    """Gioco con `allow_write: false`: `content.reload` non c'e' (409 `command_disabled`), `content.validate` si'."""
    fake.write = False
    assert error_code(await client.post(f"{LIVE}/content/reload", json={"kind": "all"}, headers=H), 409) == "worldlive.command_disabled"
    assert data(await client.get(f"{LIVE}/content/validate", headers=H))["ok"] is True


async def test_cli_content(fake: FakePachimudServer, monkeypatch: pytest.MonkeyPatch) -> None:
    """`live content validate|reload` contro il finto server pachimud: `{"ok": true, "result": ...}`; kind sconosciuto -> errore del gioco."""
    import asyncio
    import json

    from typer.testing import CliRunner

    from pachimudeditor.cli import app

    monkeypatch.setenv(ENV, TOKEN)
    base = ["live", "--socket", fake.path, "--token-env", ENV]
    run = CliRunner()
    out = await asyncio.to_thread(run.invoke, app, [*base, "content", "validate"])
    assert out.exit_code == 0 and json.loads(out.stdout)["result"]["ok"] is True
    out = await asyncio.to_thread(run.invoke, app, [*base, "content", "reload", "skills"])
    assert out.exit_code == 0 and json.loads(out.stdout)["result"]["kind"] == "skills" and fake.content_reloads == ["skills"]
    out = await asyncio.to_thread(run.invoke, app, [*base, "content", "reload", "mondo"])
    assert out.exit_code != 0


async def test_board_moderation(client: httpx.AsyncClient, fake: FakePachimudServer) -> None:
    """`board.delete` (id riga, non posizione) e `board.clear` passano dal canale con l'attore; id o bacheca sconosciuti 404; sola lettura 409."""
    status = data(await client.get(f"{LIVE}/status", headers=H))
    assert {"board.delete", "board.clear"} <= set(status["commands"])
    out = data(await client.delete(f"{LIVE}/boards/piazza/messages/1", headers=H))
    assert out == {"ok": True, "boardId": "piazza", "id": 1, "remaining": 1}
    assert fake.boards["piazza"] == [2] and any(f"actor={stack.TEST_USER} cmd=board.delete" in line for line in fake.audit)
    assert error_code(await client.delete(f"{LIVE}/boards/piazza/messages/1", headers=H), 404) == "worldlive.not_found"  # gia' tolto
    assert (
        error_code(await client.delete(f"{LIVE}/boards/altra/messages/2", headers=H), 404) == "worldlive.not_found"
    )  # id di un'altra bacheca
    ro = {"X-World": "pachimud-ro"}
    assert error_code(await client.delete(f"{LIVE}/boards/piazza", headers=ro), 409) == "world.read_only" and fake.boards["piazza"] == [2]
    assert data(await client.delete(f"{LIVE}/boards/piazza", headers=H)) == {"ok": True, "boardId": "piazza", "removed": 1}
    assert fake.boards["piazza"] == []
    fake.write = False
    assert error_code(await client.delete(f"{LIVE}/boards/piazza", headers=H), 409) == "worldlive.command_disabled"


async def test_cli_board(fake: FakePachimudServer, monkeypatch: pytest.MonkeyPatch) -> None:
    """`live board delete|clear` contro il finto server pachimud."""
    import asyncio
    import json

    from typer.testing import CliRunner

    from pachimudeditor.cli import app

    monkeypatch.setenv(ENV, TOKEN)
    base = ["live", "--socket", fake.path, "--token-env", ENV]
    run = CliRunner()
    out = await asyncio.to_thread(run.invoke, app, [*base, "board", "delete", "piazza", "1"])
    assert out.exit_code == 0 and json.loads(out.stdout)["result"]["remaining"] == 1
    out = await asyncio.to_thread(run.invoke, app, [*base, "board", "clear", "piazza"])
    assert out.exit_code == 0 and json.loads(out.stdout)["result"]["removed"] == 1 and fake.boards["piazza"] == []
