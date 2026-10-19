"""Il `MappingAdapter` dietro le route reali: selezione del mondo con `X-World`, DTO, scritture, errori stabili.

Il kind `mapping` si registra importando `adapters.mapping.module` (in produzione lo fa `src/pachimudeditor/modules.py`).
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pachimudeditor_adapter_mapping.module  # noqa: F401  (registra `kind: mapping`)
import httpx
import pytest_asyncio

from pachimudeditor.common.adapters import registry as registry_module
from pachimudeditor.common.adapters.registry import WorldConfig, WorldRegistry, set_registry
from tests.support import stack
from tests.helpers import data, error_code
from tests.support.mapping_worlds import DIKU_MAPPING, ROM_MAPPING
from tests.support.real_data import HAVE_DIKUMOD, HAVE_ROM

if HAVE_ROM:  # dati reali di basedmud
    ZONES, ZONE, ZONE_NAME, FILE, ROOMS, ROOM, MOB, SEARCH, NEXT, NEW = (
        49, 3000, "Midgaard", "midgaard.are", 143, 3001, 3000, "wizard", 10600, 3390,
    )  # fmt: skip
else:  # aree sintetiche (tests/support/synthetic_worlds.py)
    ZONES, ZONE, ZONE_NAME, FILE, ROOMS, ROOM, MOB, SEARCH, NEXT, NEW = 2, 5000, "Prato", "prato.are", 4, 5000, 5000, "maestro", 6100, 5090
if HAVE_DIKUMOD:  # record reali di Diku Modificato: zone [0, 49, 199, 249]
    DZONES, DZONE, DROOM, DTARGET, DLAST = [0, 49, 199, 249], 49, 5, 98, 249
else:  # mondo sintetico: zone [0, 99, 199]
    DZONES, DZONE, DROOM, DTARGET, DLAST = [0, 99, 199], 99, 2, 1, 199

ROM = {"X-World": "rom"}
DIKUMOD = {"X-World": "dikumod"}


@pytest_asyncio.fixture(autouse=True)
async def worlds(rom_dir: Path, dikumod_dir: Path) -> AsyncIterator[None]:
    """Registro con pachimud (default), `rom` e `dikumod` scrivibili e `rom-ro` in sola lettura sulla stessa copia ROM."""
    set_registry(
        WorldRegistry(
            [
                WorldConfig(id="pachimud", name="Pachimud", params=stack.current_params()),
                WorldConfig(id="rom", kind="mapping", name="ROM (mapping)", mapping=str(ROM_MAPPING), path=str(rom_dir)),
                WorldConfig(id="rom-ro", kind="mapping", mapping=str(ROM_MAPPING), path=str(rom_dir), read_only=True),
                WorldConfig(
                    id="dikumod", kind="mapping", name="Diku Modificato (mapping)", mapping=str(DIKU_MAPPING), path=str(dikumod_dir)
                ),
            ]
        )
    )
    yield
    await registry_module._registry.aclose_all()  # noqa: SLF001 - chiude gli engine aiosqlite prima della fine del loop
    set_registry(None)


async def test_worlds_lists_mapping_worlds(client: httpx.AsyncClient) -> None:
    """`/api/worlds` elenca i mondi `mapping` con capability e descrittori (flag legati alle tabelle esposte)."""
    worlds = {w["id"]: w for w in data(await client.get("/api/worlds"))}
    rom = worlds["rom"]
    assert rom["kind"] == "mapping" and rom["name"] == "ROM (mapping)" and rom["default"] is False
    assert rom["capabilities"]["supportsResetScripts"] and not rom["capabilities"]["supportsPlayers"]
    room = next(r for r in rom["resources"] if r["type"] == "room")
    assert next(f for f in room["fields"] if f["name"] == "flags")["enum"] == "romRoomFlags"
    assert any(f["name"] == "extra" and f["type"] == "dict" for f in room["fields"])
    assert worlds["rom-ro"]["capabilities"]["readOnly"] is True and worlds["dikumod"]["name"] == "Diku Modificato (mapping)"


async def test_rom_world_over_http(client: httpx.AsyncClient, rom_dir: Path) -> None:
    """Zone, stanze, mob, oggetti, reset e meta di un mondo ROM descritto da YAML."""
    zones = data(await client.get("/api/zones", headers=ROM))
    assert zones["total"] == ZONES and any(z["name"] == ZONE_NAME for z in zones["items"])
    assert data(await client.get("/api/zones"))["total"] == 2  # senza header: pachimud
    assert data(await client.get(f"/api/zones/{ZONE}?world=rom"))["extra"]["file"] == FILE
    rooms = data(await client.get("/api/rooms", params={"zoneId": ZONE, "pageSize": 3, "page": 1}, headers=ROM))
    assert rooms["total"] == ROOMS and len(rooms["items"]) == 3
    room = data(await client.get(f"/api/rooms/{ROOM}", headers=ROM))
    assert room["exits"][0]["targetRoomName"] and room["extra"]["sector"] == (0 if HAVE_ROM else 1)
    assert data(await client.get("/api/mobs", params={"search": SEARCH}, headers=ROM))["total"] >= 1
    assert data(await client.get(f"/api/zones/{ZONE}/reset-commands", headers=ROM))[0]["commandType"] == 0
    assert data(await client.get("/api/zones/next-vnum", headers=ROM))["bottomVnum"] == NEXT
    assert "romMobFlags" in data(await client.get("/api/meta/enums", headers=ROM))
    assert error_code(await client.get("/api/mobs/999999", headers=ROM), 404) == "mobs.not_found"
    assert error_code(await client.get("/api/zones", headers={"X-World": "nope"}), 404) == "world.not_found"


async def test_rom_writes_over_http(client: httpx.AsyncClient, rom_dir: Path) -> None:
    """PUT/POST/DELETE scrivono il file `.are`; errori con codici stabili; sola lettura = 409."""
    mob = data(await client.put(f"/api/mobs/{MOB}", json={"level": 31, "extra": {"size": "large"}}, headers=ROM))
    assert mob["level"] == 31 and mob["extra"]["size"] == "large"
    assert " large " in (rom_dir / FILE).read_text(encoding="latin-1")
    created = data(
        await client.post("/api/rooms", json={"vnum": NEW, "zoneId": ZONE, "name": "Nuova", "flags": ["dark"]}, headers=ROM), 201
    )
    assert created["flags"] == ["dark"]
    assert (
        error_code(await client.post("/api/rooms", json={"vnum": NEW, "zoneId": ZONE, "name": "Doppia"}, headers=ROM), 409)
        == "rooms.vnum_taken"
    )
    assert error_code(await client.put(f"/api/mobs/{MOB}", json={"extra": {"x": 1}}, headers=ROM), 422) == "mapping.extra_unknown"
    assert error_code(await client.put(f"/api/mobs/{MOB}", json={"experience": 5}, headers=ROM), 422) == "mapping.field_unsupported"
    assert error_code(await client.put(f"/api/rooms/{NEW}", json={"vnum": 9999}, headers=ROM), 422) == "mapping.vnum_out_of_range"
    assert (await client.delete(f"/api/rooms/{NEW}", headers=ROM)).status_code == 204
    assert error_code(await client.get(f"/api/rooms/{NEW}", headers=ROM), 404) == "rooms.not_found"
    ro = {"X-World": "rom-ro"}
    assert data(await client.get(f"/api/mobs/{MOB}", headers=ro))["level"] == 31
    assert error_code(await client.put(f"/api/mobs/{MOB}", json={"level": 1}, headers=ro), 409) == "world.read_only"
    for path in ("/api/players/accounts", "/api/world/overview", "/api/instances/mobs", "/api/content/races"):
        assert error_code(await client.get(path, headers=ROM), 409) == "world.capability_missing", path


async def test_diku_world_over_http(client: httpx.AsyncClient, dikumod_dir: Path) -> None:
    """Il mondo Diku classico: zone a catena, stanze con uscite, creazione ordinata, regole di range."""
    zones = data(await client.get("/api/zones", headers=DIKUMOD))
    assert [z["id"] for z in zones["items"]] == DZONES and zones["items"][1]["bottomVnum"] == 1
    room = data(await client.get(f"/api/rooms/{DROOM}", headers=DIKUMOD))
    assert room["zoneId"] == DZONE and room["exits"][0]["targetRoomId"] == DTARGET
    free = data(await client.get(f"/api/zones/{DZONE}/next-vnum", params={"kind": "room"}, headers=DIKUMOD))
    assert 1 <= free <= DZONE  # il primo vnum libero dentro il range della zona
    new = data(
        await client.post("/api/rooms", json={"vnum": free, "zoneId": DZONE, "name": "Nuova", "sectorType": 1}, headers=DIKUMOD), 201
    )
    assert new["zoneId"] == DZONE and f"#{free}\nNuova~" in (dikumod_dir / "dikumoddata.wld").read_text(encoding="latin-1")
    assert (
        error_code(await client.post("/api/rooms", json={"vnum": 500, "zoneId": DZONE, "name": "Fuori"}, headers=DIKUMOD), 422)
        == "mapping.vnum_out_of_range"
    )
    response = await client.post(
        "/api/zones", json={"vnum": DLAST + 200, "name": "Salto", "bottomVnum": DLAST + 151, "topVnum": DLAST + 200}, headers=DIKUMOD
    )
    assert error_code(response, 422) == "mapping.zone_bottom_derived"
    created = data(
        await client.post(
            "/api/zones", json={"vnum": DLAST + 100, "name": "Nuova zona", "bottomVnum": DLAST + 1, "topVnum": DLAST + 100}, headers=DIKUMOD
        ),
        201,
    )
    assert created["id"] == DLAST + 100 and "Nuova zona~" in (dikumod_dir / "dikumoddata.zon").read_text(encoding="latin-1")
    assert (
        error_code(await client.post(f"/api/zones/{DLAST + 100}/clone", json={"vnum": 1, "name": "x"}, headers=DIKUMOD), 422)
        == "mapping.clone_unsupported"
    )
