"""Selezione del mondo Diku Modificato via `X-World` contro i router reali (`/api/zones`, `rooms`, `mobs`, `objects`, `worlds`, `meta`)."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest_asyncio

from pachimudeditor.common.adapters import registry as registry_module
from pachimudeditor.common.adapters.registry import WorldConfig, WorldRegistry, set_registry
from tests.support import stack
from tests.helpers import data, error_code

H = {"X-World": "dikumod"}
RO = {"X-World": "dikumod-ro"}


@pytest_asyncio.fixture(autouse=True)
async def worlds(lib: Path, variant: str) -> AsyncIterator[None]:
    """Registro con pachimud (default), `dikumod` scrivibile e `dikumod-ro` con la configurazione di default (sola lettura)."""
    set_registry(
        WorldRegistry(
            [
                WorldConfig(id="pachimud", name="Pachimud", params=stack.current_params()),
                WorldConfig(
                    id="dikumod", kind="dikumod", name="Diku Modificato", path=str(lib), read_only=False, params={"variant": variant}
                ),
                WorldConfig(id="dikumod-ro", kind="dikumod", path=str(lib.parent)),
            ]
        )
    )
    yield
    await registry_module._registry.aclose_all()  # noqa: SLF001 - chiude gli engine aiosqlite prima della fine del loop
    set_registry(None)


async def test_worlds_lists_dikumod(client: httpx.AsyncClient) -> None:
    """`/api/worlds`: capability (solo reset script e extra description), `readOnly` di default vero, flag legati a `dikumod*`."""
    worlds = {w["id"]: w for w in data(await client.get("/api/worlds"))}
    world = worlds["dikumod"]
    assert world["kind"] == "dikumod" and world["default"] is False and worlds["pachimud"]["default"] is True
    caps = world["capabilities"]
    assert caps["supportsResetScripts"] and caps["supportsExtraDescriptions"] and caps["readOnly"] is False
    assert not any(
        caps[k] for k in ("supportsWorldOverview", "supportsInstances", "supportsPlayers", "supportsTransfer", "supportsContentRaces")
    )
    assert worlds["dikumod-ro"]["capabilities"]["readOnly"] is True  # nessun read_only configurato: sola lettura
    room = next(r for r in world["resources"] if r["type"] == "room")
    assert next(f for f in room["fields"] if f["name"] == "flags")["enum"] == "dikumodRoomFlags"
    mob = next(r for r in world["resources"] if r["type"] == "mob")
    assert next(f for f in mob["fields"] if f["name"] == "flags")["enum"] == "dikumodActFlags"


async def test_core_routes_on_dikumod(client: httpx.AsyncClient, variant: str) -> None:
    """Zone, stanze, mob (anche corrotti), oggetti, reset e meta rispondono sul mondo scelto."""
    zones = data(await client.get("/api/zones", params={"pageSize": 200}, headers=H))
    assert zones["total"] == 93 and zones["items"][1]["name"] == "LIMBO"
    assert data(await client.get("/api/zones"))["total"] == 2  # default: pachimud
    rooms = data(await client.get("/api/rooms", params={"zoneId": 1, "pageSize": 5, "page": 1}, headers=H))
    assert rooms["total"] > 0 and len(rooms["items"]) == min(5, rooms["total"])
    room = data(await client.get("/api/rooms/3001", headers=H))
    assert room["exits"][0]["targetRoomName"] and "sector" in room["extra"] and "exitInfo" in room["exits"][0]["extra"]
    mob = data(await client.get("/api/mobs/2111", headers=H))
    assert mob["extra"]["corrupted"] is True and mob["extra"]["warning"]
    assert data(await client.get("/api/mobs", params={"search": "magus"}, headers=H))["total"] >= 1
    objs = data(await client.get("/api/objects", params={"orderBy": "-vnum", "pageSize": 3, "page": 1}, headers=H))
    assert [o["vnum"] for o in objs["items"]] == sorted((o["vnum"] for o in objs["items"]), reverse=True)
    commands = data(await client.get("/api/zones/3/reset-commands", headers=H))
    assert commands[0]["commandType"] == 0 and "ifValue" in commands[0] and "comment" in commands[0]
    assert data(await client.get("/api/zones/next-vnum", headers=H))["vnum"] == 93
    enums = data(await client.get("/api/meta/enums", headers=H))
    assert "dikumodRoomFlags" in enums and {o["value"] for o in enums["zoneCommandType"]} >= {7, 8, 9, 10}
    assert len(data(await client.get("/api/meta/races", headers=H))) == 85
    assert error_code(await client.get("/api/mobs/999999", headers=H), 404) == "mobs.not_found"


async def test_writes_over_http(client: httpx.AsyncClient, lib: Path) -> None:
    """PUT/POST/DELETE su Diku Modificato scrivono i file; gli errori hanno codici stabili e messaggi tradotti."""
    mob = data(await client.put("/api/mobs/3000", json={"level": 31, "extra": {"position": 5}}, headers=H))
    assert mob["level"] == 31 and mob["extra"]["position"] == 5
    assert "\n31 " in (lib / "dikumoddata.mob").read_text(encoding="latin-1")
    free = data(await client.get("/api/zones/10/summary", headers=H))
    assert free["roomCount"] >= 0
    vnum = (await client.get("/api/rooms", params={"zoneId": 10, "pageSize": 1000, "orderBy": "-vnum"}, headers=H)).json()["data"]["items"][
        0
    ]["vnum"] + 1
    created = data(await client.post("/api/rooms", json={"vnum": vnum, "zoneId": 10, "name": "Nuova", "flags": ["dark"]}, headers=H), 201)
    assert created["flags"] == ["dark"]
    assert (
        error_code(await client.post("/api/rooms", json={"vnum": vnum, "zoneId": 10, "name": "Doppia"}, headers=H), 409)
        == "rooms.vnum_taken"
    )
    assert error_code(await client.put("/api/mobs/3000", json={"extra": {"x": 1}}, headers=H), 422) == "dikumod.extra_unknown"
    assert error_code(await client.put("/api/mobs/2111", json={"level": 3}, headers=H), 409) == "dikumod.record_corrupted"
    assert error_code(await client.put("/api/rooms/3001", json={"description": "a~b"}, headers=H), 422) == "dikumod.unsafe_text"
    assert (await client.delete(f"/api/rooms/{vnum}", headers=H)).status_code == 204
    assert error_code(await client.get(f"/api/rooms/{vnum}", headers=H), 404) == "rooms.not_found"
    msg = (await client.put("/api/mobs/3000", json={"extra": {"x": 1}}, headers={**H, "Accept-Language": "en"})).json()
    assert "Unknown extra key" in msg["detail"][0]["msg"]
    response = await client.post(
        "/api/zones/3/reset-commands/validate",
        json={"commands": [{"commandType": 8, "arg1": 7, "arg2": 999999}, {"commandType": 99}]},
        headers=H,
    )
    assert response.status_code == 422  # 99 non e' un tipo di comando


async def test_read_only_default_and_capabilities_over_http(client: httpx.AsyncClient) -> None:
    """Mondo con la configurazione di default: 409 `world.read_only`; aree opzionali: 409 `world.capability_missing`."""
    assert data(await client.get("/api/mobs/3000", headers=RO))["level"] > 0
    assert error_code(await client.put("/api/mobs/3000", json={"level": 1}, headers=RO), 409) == "world.read_only"
    assert error_code(await client.post("/api/zones", json={"vnum": 1, "name": "X"}, headers=RO), 409) == "world.read_only"
    for path in ("/api/players/accounts", "/api/world/overview", "/api/instances/mobs", "/api/content/races"):
        assert error_code(await client.get(path, headers=H), 409) == "world.capability_missing", path
