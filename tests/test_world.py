"""Test dell'app `world` (panoramica, grafo zone, ricerca, prossimo range).

L'app non e' ancora registrata in `src/pachimudeditor/modules.py`: qui si monta un'app dedicata con i moduli
del progetto piu' `world`, sugli stessi database temporanei della suite.
"""

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from pachifast import create_app
from pachimudeditor_adapter_pachimud.game_models.zone import Zone
from pachimudeditor_adapter_pachimud.game_models.enums import Direction, SectorType
from pachimudeditor_adapter_pachimud.game_models.room import Exit, Room
from pachimudeditor.common.adapters.plugins import available_kinds
from pachimudeditor.modules import build_modules

MODULES = build_modules(available_kinds())
from sqlalchemy import select

from pachimudeditor_adapter_pachimud.apps.world.module import module as world_module
from tests.support import gamedb
from tests.helpers import data, error_code


@pytest_asyncio.fixture
async def wclient(token: str) -> AsyncIterator[httpx.AsyncClient]:
    """Client autenticato su un'app con il modulo `world` incluso."""
    modules = MODULES if world_module in MODULES else (*MODULES, world_module)
    app = create_app(modules)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": f"Bearer {token}"}
    ) as c:
        yield c


async def _add_cross_zone_content() -> None:
    """Zona 30 (range 3000-3009) con una stanza vuota e fuori range, un'uscita verso la zona 10, e un'uscita
    pendente nella stanza 1002 della zona 10."""
    async with gamedb.get_session_factory()() as s:
        alpha = (await s.execute(select(Zone).where(Zone.vnum == 10))).scalar_one()
        third = Zone(
            vnum=30,
            name="Zona Terza",
            builder="t",
            bottom_vnum=3000,
            top_vnum=3009,
            min_level=1,
            max_level=2,
            lifespan_minutes=5,
            reset_mode=alpha.reset_mode,
            enabled=False,
        )
        s.add(third)
        await s.flush()
        stray = Room(vnum=5000, zone_id=third.id, name="Fuori", description="  ", sector_type=SectorType.CITY, flags=[])
        s.add(stray)
        await s.flush()
        piazza = (await s.execute(select(Room).where(Room.vnum == 1000))).scalar_one()
        cantina = (await s.execute(select(Room).where(Room.vnum == 1002))).scalar_one()
        s.add_all(
            [
                Exit(room_id=stray.id, direction=Direction.EAST, target_room_id=piazza.id),
                Exit(room_id=cantina.id, direction=Direction.WEST, target_room_id=None),
            ]
        )
        await s.commit()


async def test_requires_auth(anon: httpx.AsyncClient) -> None:
    """Senza token il modulo risponde 401 (se registrato) o 404 (non ancora registrato): mai 200."""
    modules = MODULES if world_module in MODULES else (*MODULES, world_module)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(modules)), base_url="http://test") as c:
        assert (await c.get("/api/world/overview")).status_code == 401


async def test_overview_counts_and_zones(wclient: httpx.AsyncClient) -> None:
    """Conteggi e riepilogo per zona sul seed di base."""
    body = data(await wclient.get("/api/world/overview"))
    assert body["counts"]["zones"] == 2
    assert body["counts"]["zonesEnabled"] == 2
    assert body["counts"]["rooms"] == 3
    assert body["counts"]["mobs"] == 2
    assert body["counts"]["objects"] == 2
    assert body["counts"]["accounts"] == 0
    alpha = next(z for z in body["zones"] if z["vnum"] == 10)
    assert (alpha["rooms"], alpha["mobs"], alpha["objects"], alpha["resetCommands"]) == (3, 2, 2, 2)
    # vnum distinti in 1000-1099: 1000, 1001, 1002 -> 3 su 100
    assert alpha["rangeUsagePct"] == 3.0


async def test_overview_warnings(wclient: httpx.AsyncClient) -> None:
    """Warning: mob/oggetti mai caricati, reset vuoto, descrizione vuota, uscita pendente, fuori range."""
    await _add_cross_zone_content()
    body = data(await wclient.get("/api/world/overview"))
    totals = body["warningTotals"]
    assert totals["mob_never_loaded"] == 1  # 1001 "ratto"
    assert totals["object_never_loaded"] == 1  # 1001 "sasso"
    assert totals["room_empty_description"] == 1  # stanza 5000
    assert totals["exit_without_target"] == 1
    assert totals["vnum_out_of_range"] == 1
    assert "zone_empty_reset_script" not in totals  # zona 30 non ha mob/oggetti, zona 20 neppure
    by_kind = {w["kind"]: w for w in body["warnings"]}
    assert by_kind["vnum_out_of_range"]["entityType"] == "room"
    assert by_kind["vnum_out_of_range"]["params"] == {"bottom": 3000, "top": 3009}
    assert by_kind["exit_without_target"]["params"] == {"direction": int(Direction.WEST)}
    assert by_kind["mob_never_loaded"]["vnum"] == 1001


async def test_zone_graph(wclient: httpx.AsyncClient) -> None:
    """Un'uscita tra zone diverse genera un arco; le zone senza collegamenti sono isolate."""
    graph = data(await wclient.get("/api/world/zone-graph"))
    assert graph["edges"] == []
    assert all(n["isolated"] for n in graph["nodes"])
    await _add_cross_zone_content()
    graph = data(await wclient.get("/api/world/zone-graph"))
    ids = {n["vnum"]: n["id"] for n in graph["nodes"]}
    assert graph["edges"] == [{"fromZoneId": ids[30], "toZoneId": ids[10], "count": 1}]
    isolated = {n["vnum"]: n["isolated"] for n in graph["nodes"]}
    assert isolated == {10: False, 20: True, 30: False}


async def test_search(wclient: httpx.AsyncClient) -> None:
    """Ricerca per nome, keywords e prefisso di vnum, con filtro sui tipi e limite."""
    res = data(await wclient.get("/api/world/search", params={"q": "guardia"}))
    assert [m["vnum"] for m in res["mobs"]["items"]] == [1000]
    assert res["mobs"]["items"][0]["keywords"] == "guardia"
    assert res["rooms"]["total"] == 0
    res = data(await wclient.get("/api/world/search", params={"q": "100", "types": "room,zone"}))
    assert res["rooms"]["total"] == 3
    assert res["zones"]["total"] == 0 and res["mobs"]["items"] == []
    res = data(await wclient.get("/api/world/search", params={"q": "100", "types": "room", "limit": 2}))
    assert len(res["rooms"]["items"]) == 2 and res["rooms"]["total"] == 3
    res = data(await wclient.get("/api/world/search", params={"q": "zona"}))
    assert res["zones"]["total"] == 2
    assert res["zones"]["items"][0]["zoneId"] == res["zones"]["items"][0]["id"]


async def test_search_wildcards_are_literal(wclient: httpx.AsyncClient) -> None:
    """`%` e `_` non sono jolly."""
    for q in ("%", "_", "g_ardia", "\\"):
        res = data(await wclient.get("/api/world/search", params={"q": q}))
        assert res["mobs"]["total"] == 0 and res["rooms"]["total"] == 0 and res["zones"]["total"] == 0


async def test_search_errors(wclient: httpx.AsyncClient) -> None:
    """Tipi ignoti e testo vuoto sono 422."""
    assert error_code(await wclient.get("/api/world/search", params={"q": "a", "types": "foo"}), 422) == ("world.invalid_types")
    assert error_code(await wclient.get("/api/world/search", params={"q": "   "}), 422) == "world.empty_query"
    assert (await wclient.get("/api/world/search")).status_code == 422


async def test_next_zone_range(wclient: httpx.AsyncClient) -> None:
    """Il primo range libero parte da 1 e riempie i buchi."""
    assert data(await wclient.get("/api/world/next-zone-range", params={"span": 100})) == {"bottomVnum": 1, "topVnum": 100}
    assert data(await wclient.get("/api/world/next-zone-range", params={"span": 1000})) == {"bottomVnum": 2100, "topVnum": 3099}
    assert data(await wclient.get("/api/world/next-zone-range")) == {"bottomVnum": 1, "topVnum": 100}
    assert (await wclient.get("/api/world/next-zone-range", params={"span": 0})).status_code == 422
