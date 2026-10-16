"""Mob prototype: CRUD, vnum duplicato, uso nei reset, validazione."""

import httpx

from tests.helpers import by_vnum, data, error_code


async def _body(client: httpx.AsyncClient, vnum: int, /, **extra: object) -> dict:
    """Corpo minimo di creazione di un mob nella zona 10."""
    zone = await by_vnum(client, "zones", 10)
    return {"vnum": vnum, "zoneId": zone["id"], "keywords": "goblin", "shortDescription": "un goblin"} | extra


async def test_crud_happy_path(client: httpx.AsyncClient) -> None:
    """Crea con flag, legge, modifica, elimina."""
    mob = data(await client.post("/api/mobs", json=await _body(client, 1050, flags=["sentinel", "aggressive"], level=5)), 201)
    assert mob["flags"] == ["sentinel", "aggressive"] and mob["level"] == 5 and mob["hpDieSize"] == 8
    patched = data(await client.put(f"/api/mobs/{mob['id']}", json={"flags": ["sentinel"], "gold": 50, "sex": 1}))
    assert patched["flags"] == ["sentinel"] and patched["gold"] == 50 and patched["sex"] == 1
    assert data(await client.get(f"/api/mobs/{mob['id']}"))["shortDescription"] == "un goblin"
    assert (await client.delete(f"/api/mobs/{mob['id']}")).status_code == 204
    assert error_code(await client.delete(f"/api/mobs/{mob['id']}"), 404) == "mobs.not_found"


async def test_duplicate_vnum_409(client: httpx.AsyncClient) -> None:
    """Vnum duplicato: 409 `mobs.vnum_taken`, anche in modifica."""
    response = await client.post("/api/mobs", json=await _body(client, 1000))
    assert error_code(response, 409) == "mobs.vnum_taken"
    assert response.json()["detail"][0]["params"]["vnum"] == 1000
    mob = await by_vnum(client, "mobs", 1001)
    assert error_code(await client.put(f"/api/mobs/{mob['id']}", json={"vnum": 1000}), 409) == "mobs.vnum_taken"


async def test_validation_422(client: httpx.AsyncClient) -> None:
    """Keywords vuote, dado a 0, allineamento fuori range."""
    for bad in ({"keywords": ""}, {"hpDieSize": 0}, {"alignment": 5000}, {"vnum": -5}):
        assert (await client.post("/api/mobs", json=await _body(client, 1051, **bad))).status_code == 422, bad


async def test_delete_in_use_by_reset_409(client: httpx.AsyncClient) -> None:
    """Mob referenziato da un reset: 409 `mobs.in_reset_usage`; usage lo elenca."""
    mob = await by_vnum(client, "mobs", 1000)
    assert len(data(await client.get(f"/api/mobs/{mob['id']}/usage"))) == 1
    response = await client.delete(f"/api/mobs/{mob['id']}")
    assert error_code(response, 409) == "mobs.in_reset_usage"
    assert response.json()["detail"][0]["params"]["count"] == 1
    free = await by_vnum(client, "mobs", 1001)
    assert data(await client.get(f"/api/mobs/{free['id']}/usage")) == []
    assert (await client.delete(f"/api/mobs/{free['id']}")).status_code == 204


async def test_order_by_level(client: httpx.AsyncClient) -> None:
    """Ordinamento per level."""
    data(await client.post("/api/mobs", json=await _body(client, 1052, level=9)), 201)
    items = data(await client.get("/api/mobs", params={"orderBy": "-level"}))["items"]
    assert items[0]["vnum"] == 1052
