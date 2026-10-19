"""Stanze: CRUD, uscite, extra description, clone, grafo, cancellazione."""

import httpx

from tests.helpers import by_vnum, data, error_code


async def _zone_id(client: httpx.AsyncClient, vnum: int = 10) -> int:
    """Id della zona con il vnum dato."""
    return (await by_vnum(client, "zones", vnum))["id"]


async def _new_room(client: httpx.AsyncClient, vnum: int, **extra: object) -> dict:
    """Crea una stanza nella zona 10."""
    body = {"vnum": vnum, "zoneId": await _zone_id(client), "name": f"Stanza {vnum}", "description": "d", **extra}
    return data(await client.post("/api/rooms", json=body), 201)


async def test_crud_happy_path(client: httpx.AsyncClient) -> None:
    """Crea (con flag), legge il dettaglio, modifica, elimina."""
    room = await _new_room(client, 1010, sectorType=3, flags=["dark", "nomob"])
    assert room["sectorType"] == 3 and room["flags"] == ["dark", "nomob"]
    assert room["exits"] == [] and room["extraDescriptions"] == []
    patched = data(await client.put(f"/api/rooms/{room['id']}", json={"name": "Nuovo nome", "flags": []}))
    assert patched["name"] == "Nuovo nome" and patched["flags"] == [] and patched["sectorType"] == 3
    assert data(await client.get(f"/api/rooms/{room['id']}"))["name"] == "Nuovo nome"
    assert (await client.delete(f"/api/rooms/{room['id']}")).status_code == 204
    assert error_code(await client.get(f"/api/rooms/{room['id']}"), 404) == "rooms.not_found"


async def test_duplicate_vnum_409(client: httpx.AsyncClient) -> None:
    """Vnum duplicato in creazione, modifica e clone."""
    zone_id = await _zone_id(client)
    response = await client.post("/api/rooms", json={"vnum": 1000, "zoneId": zone_id, "name": "x"})
    assert error_code(response, 409) == "rooms.vnum_taken"
    assert response.json()["detail"][0]["params"]["vnum"] == 1000
    room = await by_vnum(client, "rooms", 1002)
    assert error_code(await client.put(f"/api/rooms/{room['id']}", json={"vnum": 1000}), 409) == "rooms.vnum_taken"
    assert error_code(await client.post(f"/api/rooms/{room['id']}/clone", json={"vnum": 1000}), 409) == "rooms.vnum_taken"


async def test_validation_422(client: httpx.AsyncClient) -> None:
    """Nome vuoto, zona mancante, enum fuori range."""
    zone_id = await _zone_id(client)
    assert (await client.post("/api/rooms", json={"vnum": 1020, "zoneId": zone_id, "name": ""})).status_code == 422
    assert (await client.post("/api/rooms", json={"vnum": 1020, "name": "x"})).status_code == 422
    bad = await client.post("/api/rooms", json={"vnum": 1020, "zoneId": zone_id, "name": "x", "sectorType": 99})
    assert bad.status_code == 422


async def test_invalid_zone_reference_409(client: httpx.AsyncClient) -> None:
    """Zona inesistente: viola la FK -> 409 `common.editor.invalid_reference`."""
    response = await client.post("/api/rooms", json={"vnum": 1021, "zoneId": 999999, "name": "x"})
    assert error_code(response, 409) == "common.editor.invalid_reference"


async def test_detail_has_resolved_exit_targets(client: httpx.AsyncClient) -> None:
    """Il dettaglio risolve vnum e nome della destinazione delle uscite."""
    room = await by_vnum(client, "rooms", 1000)
    detail = data(await client.get(f"/api/rooms/{room['id']}"))
    assert [(e["direction"], e["targetRoomVnum"], e["targetRoomName"]) for e in detail["exits"]] == [(0, 1001, "Vicolo")]
    extra = data(await client.get(f"/api/rooms/{(await by_vnum(client, 'rooms', 1002))['id']}"))
    assert extra["extraDescriptions"][0]["keywords"] == "botte"


async def test_exits_crud(client: httpx.AsyncClient) -> None:
    """Crea/modifica/elimina un'uscita; una sola per direzione; uscita di un'altra stanza -> 409."""
    a = await by_vnum(client, "rooms", 1002)
    b = await by_vnum(client, "rooms", 1000)
    ex = data(await client.post(f"/api/rooms/{a['id']}/exits", json={"direction": 1, "targetRoomId": b["id"], "doorFlag": 1}), 201)
    assert ex["targetRoomVnum"] == 1000 and ex["doorFlag"] == 1
    dup = await client.post(f"/api/rooms/{a['id']}/exits", json={"direction": 1})
    assert error_code(dup, 409) == "rooms.exit_direction_taken"
    upd = data(await client.put(f"/api/rooms/{a['id']}/exits/{ex['id']}", json={"isLocked": True, "keyVnum": 1000, "direction": 4}))
    assert upd["isLocked"] is True and upd["direction"] == 4
    other = data(await client.get(f"/api/rooms/{b['id']}"))["exits"][0]
    assert error_code(await client.put(f"/api/rooms/{a['id']}/exits/{other['id']}", json={}), 409) == "rooms.exit_not_in_room"
    assert error_code(await client.delete(f"/api/rooms/{a['id']}/exits/{other['id']}"), 409) == "rooms.exit_not_in_room"
    clash = await client.put(f"/api/rooms/{b['id']}/exits/{other['id']}", json={"direction": 0})
    assert clash.status_code == 200  # stessa direzione: nessun conflitto con se stessa
    assert (await client.delete(f"/api/rooms/{a['id']}/exits/{ex['id']}")).status_code == 204
    assert error_code(await client.delete(f"/api/rooms/{a['id']}/exits/{ex['id']}"), 404) == "rooms.exit_not_found"


async def test_extra_descriptions_crud(client: httpx.AsyncClient) -> None:
    """CRUD extra description e controlli di appartenenza."""
    a = await by_vnum(client, "rooms", 1000)
    b = await by_vnum(client, "rooms", 1002)
    extra = data(await client.post(f"/api/rooms/{a['id']}/extra-descriptions", json={"keywords": "tavolo", "text": "Un tavolo."}), 201)
    assert (await client.post(f"/api/rooms/{a['id']}/extra-descriptions", json={"keywords": "", "text": "x"})).status_code == 422
    upd = data(await client.put(f"/api/rooms/{a['id']}/extra-descriptions/{extra['id']}", json={"text": "Altro."}))
    assert upd["text"] == "Altro." and upd["keywords"] == "tavolo"
    wrong = await client.put(f"/api/rooms/{b['id']}/extra-descriptions/{extra['id']}", json={"text": "x"})
    assert error_code(wrong, 409) == "rooms.extra_not_in_room"
    assert (await client.delete(f"/api/rooms/{a['id']}/extra-descriptions/{extra['id']}")).status_code == 204
    assert error_code(await client.delete(f"/api/rooms/{a['id']}/extra-descriptions/{extra['id']}"), 404) == "rooms.extra_not_found"


async def test_clone(client: httpx.AsyncClient) -> None:
    """Clone: copia i campi e le extra description, non le uscite."""
    src = await by_vnum(client, "rooms", 1002)
    clone = data(await client.post(f"/api/rooms/{src['id']}/clone", json={"vnum": 1030}), 201)
    assert clone["name"] == "Cantina" and clone["zoneId"] == src["zoneId"] and clone["id"] != src["id"]
    assert [e["keywords"] for e in clone["extraDescriptions"]] == ["botte"] and clone["exits"] == []
    named = data(await client.post(f"/api/rooms/{src['id']}/clone", json={"vnum": 1031, "name": "Cantina bis"}), 201)
    assert named["name"] == "Cantina bis"
    with_exits = await by_vnum(client, "rooms", 1000)
    c2 = data(await client.post(f"/api/rooms/{with_exits['id']}/clone", json={"vnum": 1032}), 201)
    assert c2["exits"] == []


async def test_delete_cascades_exits_and_extras(client: httpx.AsyncClient) -> None:
    """Eliminare una stanza elimina le sue uscite/extra; le uscite altrui verso di lei restano senza destinazione."""
    from tests.support.gamedb import get_session_factory
    from pachimudeditor_adapter_pachimud.game_models.room import Exit, RoomExtraDescription
    from sqlalchemy import select

    room = await _new_room(client, 1040)
    data(await client.post(f"/api/rooms/{room['id']}/exits", json={"direction": 0}), 201)
    data(await client.post(f"/api/rooms/{room['id']}/extra-descriptions", json={"keywords": "k", "text": "t"}), 201)
    neighbour = await by_vnum(client, "rooms", 1002)
    inbound = data(await client.post(f"/api/rooms/{neighbour['id']}/exits", json={"direction": 2, "targetRoomId": room["id"]}), 201)
    assert (await client.delete(f"/api/rooms/{room['id']}")).status_code == 204
    async with get_session_factory()() as session:
        assert (await session.execute(select(Exit).where(Exit.room_id == room["id"]))).scalars().all() == []
        assert (await session.execute(select(RoomExtraDescription).where(RoomExtraDescription.room_id == room["id"]))).scalars().all() == []
    survivor = data(await client.get(f"/api/rooms/{neighbour['id']}"))["exits"]
    assert [e["id"] for e in survivor if e["id"] == inbound["id"]] == [inbound["id"]]
    assert next(e for e in survivor if e["id"] == inbound["id"])["targetRoomId"] is None


async def test_delete_in_use_by_reset_409(client: httpx.AsyncClient) -> None:
    """Stanza referenziata da un reset: 409 `rooms.in_reset_usage`, e `usage` la elenca."""
    room = await by_vnum(client, "rooms", 1000)
    usage = data(await client.get(f"/api/rooms/{room['id']}/usage"))
    assert len(usage) == 2 and usage[0]["zoneName"] == "Zona Alfa"
    response = await client.delete(f"/api/rooms/{room['id']}")
    assert error_code(response, 409) == "rooms.in_reset_usage"
    assert response.json()["detail"][0]["params"]["count"] == 2
    assert data(await client.get(f"/api/rooms/{room['id']}"))["vnum"] == 1000
    free = await by_vnum(client, "rooms", 1002)
    assert data(await client.get(f"/api/rooms/{free['id']}/usage")) == []


async def test_graph(client: httpx.AsyncClient) -> None:
    """Grafo: nodi con coordinate, un arco two-way per la coppia 1000/1001, uscite pendenti contate."""
    zone_id = await _zone_id(client)
    graph = data(await client.get("/api/rooms/graph", params={"zoneId": zone_id}))
    assert [n["vnum"] for n in graph["nodes"]] == [1000, 1001, 1002]
    assert all(isinstance(n["x"], (int, float)) and isinstance(n["y"], (int, float)) for n in graph["nodes"])
    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    assert edge["twoWay"] is True and edge["reverseExitId"] is not None
    cantina = await by_vnum(client, "rooms", 1002)
    data(await client.post(f"/api/rooms/{cantina['id']}/exits", json={"direction": 0}), 201)
    graph = data(await client.get("/api/rooms/graph", params={"zoneId": zone_id}))
    assert next(n for n in graph["nodes"] if n["vnum"] == 1002)["danglingExits"] == 1
    empty = data(await client.get("/api/rooms/graph", params={"zoneId": await _zone_id(client, 20)}))
    assert empty == {"nodes": [], "edges": []}
    assert (await client.get("/api/rooms/graph")).status_code == 422
