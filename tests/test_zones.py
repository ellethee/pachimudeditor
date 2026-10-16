"""Zone: CRUD, clone, next-vnum, script di reset, cancellazione."""

import httpx

from tests.helpers import by_vnum, data, error_code

NEW = {
    "vnum": 30,
    "name": "Zona Nuova",
    "builder": "luca",
    "bottomVnum": 3000,
    "topVnum": 3099,
    "minLevel": 1,
    "maxLevel": 20,
    "lifespanMinutes": 10,
    "resetMode": 2,
    "enabled": True,
}


async def test_crud_happy_path(client: httpx.AsyncClient) -> None:
    """Crea, legge, modifica (patch parziale), elimina."""
    zone = data(await client.post("/api/zones", json=NEW), 201)
    assert zone["vnum"] == 30 and zone["resetMode"] == 2 and zone["bottomVnum"] == 3000
    assert data(await client.get(f"/api/zones/{zone['id']}"))["name"] == "Zona Nuova"
    patched = data(await client.put(f"/api/zones/{zone['id']}", json={"name": "Rinominata", "enabled": False}))
    assert patched["name"] == "Rinominata" and patched["enabled"] is False and patched["builder"] == "luca"
    assert (await client.delete(f"/api/zones/{zone['id']}")).status_code == 204
    assert error_code(await client.get(f"/api/zones/{zone['id']}"), 404) == "zones.not_found"


async def test_snake_case_input_accepted(client: httpx.AsyncClient) -> None:
    """Il body accetta anche snake_case."""
    body = {**NEW, "vnum": 31, "bottom_vnum": 3100, "top_vnum": 3199}
    del body["bottomVnum"], body["topVnum"]
    assert data(await client.post("/api/zones", json=body), 201)["bottomVnum"] == 3100


async def test_duplicate_vnum_409(client: httpx.AsyncClient) -> None:
    """Vnum duplicato in creazione e in modifica: 409 `zones.vnum_taken` con param vnum."""
    response = await client.post("/api/zones", json={**NEW, "vnum": 10})
    assert error_code(response, 409) == "zones.vnum_taken"
    assert response.json()["detail"][0]["params"]["vnum"] == 10
    zone = await by_vnum(client, "zones", 20)
    assert error_code(await client.put(f"/api/zones/{zone['id']}", json={"vnum": 10}), 409) == "zones.vnum_taken"
    assert data(await client.put(f"/api/zones/{zone['id']}", json={"vnum": 20}))["vnum"] == 20


async def test_validation_422(client: httpx.AsyncClient) -> None:
    """bottomVnum > topVnum, livelli invertiti, nome vuoto, vnum negativo: 422."""
    for bad in ({"bottomVnum": 5000, "topVnum": 10}, {"minLevel": 9, "maxLevel": 2}, {"name": ""}, {"vnum": -1}):
        response = await client.post("/api/zones", json={**NEW, **bad})
        assert error_code(response, 422) is None, bad


async def test_delete_not_empty_409(client: httpx.AsyncClient) -> None:
    """Zona con contenuto: 409 `zones.not_empty` con i conteggi; la zona resta."""
    zone = await by_vnum(client, "zones", 10)
    response = await client.delete(f"/api/zones/{zone['id']}")
    assert error_code(response, 409) == "zones.not_empty"
    assert response.json()["detail"][0]["params"] == {"rooms": 3, "mobs": 2, "objects": 2}
    assert data(await client.get(f"/api/zones/{zone['id']}"))["vnum"] == 10


async def test_delete_cascades_reset_script(client: httpx.AsyncClient) -> None:
    """Eliminare una zona vuota elimina anche il suo script di reset."""
    zone = await by_vnum(client, "zones", 20)
    put = await client.put(
        f"/api/zones/{zone['id']}/reset-commands",
        json={"commands": [{"commandType": 0, "arg1": 1001, "arg2": 1, "arg3": 1002, "arg4": 1}]},
    )
    assert len(data(put)) == 1
    assert (await client.delete(f"/api/zones/{zone['id']}")).status_code == 204
    from tests.support.gamedb import get_session_factory
    from pachimud.zone.models import ZoneResetCommand
    from sqlalchemy import func, select

    async with get_session_factory()() as session:
        left = (
            await session.execute(select(func.count()).select_from(ZoneResetCommand).where(ZoneResetCommand.zone_id == zone["id"]))
        ).scalar_one()
    assert left == 0


async def test_summary(client: httpx.AsyncClient) -> None:
    """Conteggi del contenuto."""
    zone = await by_vnum(client, "zones", 10)
    assert data(await client.get(f"/api/zones/{zone['id']}/summary")) == {"roomCount": 3, "mobCount": 2, "objectCount": 2}


async def test_next_vnum(client: httpx.AsyncClient) -> None:
    """Vnum liberi per zona e per contenuto della zona."""
    nxt = data(await client.get("/api/zones/next-vnum", params={"span": 49}))
    assert nxt["vnum"] == 21 and nxt["topVnum"] - nxt["bottomVnum"] == 49
    assert not (nxt["bottomVnum"] <= 2099 and nxt["topVnum"] >= 1000)
    zone = await by_vnum(client, "zones", 10)
    assert data(await client.get(f"/api/zones/{zone['id']}/next-vnum", params={"kind": "room"})) == 1003
    assert data(await client.get(f"/api/zones/{zone['id']}/next-vnum", params={"kind": "mob"})) == 1002
    assert data(await client.get(f"/api/zones/{zone['id']}/next-vnum", params={"kind": "object"})) == 1002
    empty = await by_vnum(client, "zones", 20)
    assert data(await client.get(f"/api/zones/{empty['id']}/next-vnum", params={"kind": "room"})) == 2000
    assert (await client.get(f"/api/zones/{zone['id']}/next-vnum", params={"kind": "bogus"})).status_code == 422


async def test_clone(client: httpx.AsyncClient) -> None:
    """Clone con e senza script di reset; vnum duplicato -> 409."""
    zone = await by_vnum(client, "zones", 10)
    plain = data(await client.post(f"/api/zones/{zone['id']}/clone", json={"vnum": 40, "name": "Copia"}), 201)
    assert plain["name"] == "Copia" and plain["bottomVnum"] == 0 and plain["topVnum"] == 0 and plain["builder"] == "tester"
    assert data(await client.get(f"/api/zones/{plain['id']}/reset-commands")) == []
    full = data(await client.post(f"/api/zones/{zone['id']}/clone", json={"vnum": 41, "name": "Copia2", "copyResetCommands": True}), 201)
    commands = data(await client.get(f"/api/zones/{full['id']}/reset-commands"))
    assert [c["arg1"] for c in commands] == [1000, 1000] and all(c["zoneId"] == full["id"] for c in commands)
    dup = await client.post(f"/api/zones/{zone['id']}/clone", json={"vnum": 10, "name": "x"})
    assert error_code(dup, 409) == "zones.vnum_taken"
    assert error_code(await client.post("/api/zones/999999/clone", json={"vnum": 99, "name": "x"}), 404) == "zones.not_found"


async def test_reset_commands_get_and_replace(client: httpx.AsyncClient) -> None:
    """GET dello script seminato; PUT sostituisce tutto rinumerando orderIndex."""
    zone = await by_vnum(client, "zones", 10)
    current = data(await client.get(f"/api/zones/{zone['id']}/reset-commands"))
    assert [c["orderIndex"] for c in current] == [0, 1] and current[0]["commandType"] == 0
    new = {
        "commands": [
            {"commandType": 1, "ifFlag": True, "arg1": 1001, "arg2": 2, "arg3": 1000},
            {"commandType": 5, "arg1": 1000, "arg2": 0, "argStr": "closed"},
            {"commandType": 0, "arg1": 1001, "arg2": 1, "arg3": 1001, "arg4": 1},
        ]
    }
    replaced = data(await client.put(f"/api/zones/{zone['id']}/reset-commands", json=new))
    assert [c["orderIndex"] for c in replaced] == [0, 1, 2]
    assert [c["commandType"] for c in replaced] == [1, 5, 0]
    assert replaced[0]["ifFlag"] is True and replaced[1]["argStr"] == "closed"
    assert data(await client.get(f"/api/zones/{zone['id']}/reset-commands")) == replaced
    assert data(await client.put(f"/api/zones/{zone['id']}/reset-commands", json={"commands": []})) == []
    assert error_code(await client.put("/api/zones/999999/reset-commands", json={"commands": []}), 404) == "zones.not_found"
    bad = await client.put(f"/api/zones/{zone['id']}/reset-commands", json={"commands": [{"commandType": 99}]})
    assert bad.status_code == 422
