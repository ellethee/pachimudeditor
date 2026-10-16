"""Selezione del mondo BasedMud via `X-World` contro i router reali (`/api/zones`, `rooms`, `mobs`, `objects`, `worlds`)."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest_asyncio

from pachimudeditor.common.adapters import registry as registry_module
from pachimudeditor.common.adapters.registry import WorldConfig, WorldRegistry, set_registry
from tests.support import stack
from tests.helpers import data, error_code

H = {"X-World": "basedmud"}


@pytest_asyncio.fixture(autouse=True)
async def worlds(area_dir: Path) -> AsyncIterator[None]:
    """Registro con pachimud (default), `basedmud` scrivibile e `basedmud-ro` in sola lettura sulla stessa copia."""
    set_registry(
        WorldRegistry(
            [
                WorldConfig(id="pachimud", name="Pachimud", params=stack.current_params()),
                WorldConfig(id="basedmud", kind="basedmud", name="BasedMud", path=str(area_dir.parent)),
                WorldConfig(id="basedmud-ro", kind="basedmud", path=str(area_dir), read_only=True),
            ]
        )
    )
    yield
    await registry_module._registry.aclose_all()  # noqa: SLF001 - chiude gli engine aiosqlite prima della fine del loop
    set_registry(None)


async def test_worlds_lists_basedmud(client: httpx.AsyncClient) -> None:
    """`/api/worlds` elenca il mondo con capability e descrittori (flag legati alle tabelle ROM)."""
    worlds = {w["id"]: w for w in data(await client.get("/api/worlds"))}
    world = worlds["basedmud"]
    assert world["kind"] == "basedmud" and world["default"] is False and worlds["pachimud"]["default"] is True
    caps = world["capabilities"]
    assert caps["supportsResetScripts"] and caps["supportsExtraDescriptions"] and caps["readOnly"] is False
    assert not any(
        caps[k] for k in ("supportsWorldOverview", "supportsInstances", "supportsPlayers", "supportsTransfer", "supportsContentRaces")
    )
    room = next(r for r in world["resources"] if r["type"] == "room")
    assert next(f for f in room["fields"] if f["name"] == "flags")["enum"] == "romRoomFlags"
    assert any(f["name"] == "extra" and f["type"] == "dict" for f in room["fields"])
    assert worlds["basedmud-ro"]["capabilities"]["readOnly"] is True


async def test_core_routes_on_basedmud(client: httpx.AsyncClient) -> None:
    """Zone, stanze, mob, oggetti e meta rispondono sul mondo scelto; senza header resta pachimud."""
    zones = data(await client.get("/api/zones", headers=H))
    assert zones["total"] == 49 and any(z["name"] == "Midgaard" for z in zones["items"])
    assert data(await client.get("/api/zones"))["total"] == 2  # default: pachimud
    midgaard = data(await client.get("/api/zones/3000?world=basedmud"))
    assert midgaard["extra"]["file"] == "midgaard.are"
    rooms = data(await client.get("/api/rooms", params={"zoneId": 3000, "pageSize": 5, "page": 1}, headers=H))
    assert rooms["total"] == 143 and len(rooms["items"]) == 5
    room = data(await client.get("/api/rooms/3001", headers=H))
    assert room["exits"][0]["targetRoomName"] and room["extra"]["sector"] == 0
    mobs = data(await client.get("/api/mobs", params={"search": "wizard"}, headers=H))
    assert mobs["total"] >= 1
    objects = data(await client.get("/api/objects", params={"zoneId": 3000, "orderBy": "-vnum", "pageSize": 3, "page": 1}, headers=H))
    assert [o["vnum"] for o in objects["items"]] == sorted((o["vnum"] for o in objects["items"]), reverse=True)
    assert data(await client.get("/api/zones/3000/reset-commands", headers=H))[0]["commandType"] == 0
    assert data(await client.get("/api/zones/next-vnum", headers=H))["bottomVnum"] == 10600
    enums = data(await client.get("/api/meta/enums", headers=H))
    assert "romMobFlags" in enums and data(await client.get("/api/meta/races", headers=H)) == []
    assert error_code(await client.get("/api/mobs/999999", headers=H), 404) == "mobs.not_found"


async def test_writes_over_http(client: httpx.AsyncClient, area_dir: Path) -> None:
    """PUT/POST/DELETE su BasedMud scrivono il file `.are`; gli errori hanno i codici stabili."""
    mob = data(await client.put("/api/mobs/3000", json={"level": 31, "extra": {"size": "large"}}, headers=H))
    assert mob["level"] == 31 and mob["extra"]["size"] == "large"
    assert " large " in (area_dir / "midgaard.are").read_text(encoding="latin-1")
    created = data(await client.post("/api/rooms", json={"vnum": 3390, "zoneId": 3000, "name": "Nuova", "flags": ["dark"]}, headers=H), 201)
    assert created["flags"] == ["dark"]
    response = await client.post("/api/rooms", json={"vnum": 3390, "zoneId": 3000, "name": "Doppia"}, headers=H)
    assert error_code(response, 409) == "rooms.vnum_taken"
    assert error_code(await client.put("/api/mobs/3000", json={"extra": {"x": 1}}, headers=H), 422) == "basedmud.extra_unknown"
    assert error_code(await client.put("/api/mobs/3000", json={"experience": 5}, headers=H), 422) == "basedmud.field_unsupported"
    assert (await client.delete("/api/rooms/3390", headers=H)).status_code == 204
    assert error_code(await client.get("/api/rooms/3390", headers=H), 404) == "rooms.not_found"
    msg = (await client.put("/api/mobs/3000", json={"extra": {"x": 1}}, headers={**H, "Accept-Language": "en"})).json()
    assert "Unknown extra key" in msg["detail"][0]["msg"]


async def test_read_only_and_capabilities_over_http(client: httpx.AsyncClient) -> None:
    """Mondo in sola lettura: 409 `world.read_only`; aree opzionali: 409 `world.capability_missing`."""
    ro = {"X-World": "basedmud-ro"}
    assert data(await client.get("/api/mobs/3000", headers=ro))["level"] == 23
    assert error_code(await client.put("/api/mobs/3000", json={"level": 1}, headers=ro), 409) == "world.read_only"
    assert error_code(await client.post("/api/zones", json={"vnum": 1, "name": "X"}, headers=ro), 409) == "world.read_only"
    for path in ("/api/players/accounts", "/api/world/overview", "/api/instances/mobs", "/api/content/races"):
        assert error_code(await client.get(path, headers=H), 409) == "world.capability_missing", path
