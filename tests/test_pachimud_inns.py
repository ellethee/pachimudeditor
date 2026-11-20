"""Locande pachimud: il flag `receptionist` del mob e l'elenco `/api/content/inns`."""

import httpx

from tests.helpers import by_vnum, data


async def test_inns_list_rooms_and_unspawned(client: httpx.AsyncClient) -> None:
    """Un mob `receptionist` compare con le stanze dei reset che lo caricano; senza reset ha `rooms` vuoto; togliendo il flag sparisce."""
    spawned = await by_vnum(client, "mobs", 1000)
    lonely = await by_vnum(client, "mobs", 1001)
    for mob in (spawned, lonely):
        data(await client.put(f"/api/mobs/{mob['id']}", json={"extra": {"receptionist": True}}))
    rows = {r["vnum"]: r for r in data(await client.get("/api/content/inns"))}
    assert rows[1000]["rooms"] == [{"vnum": 1000, "name": rows[1000]["rooms"][0]["name"]}] and rows[1000]["rooms"][0]["name"]
    assert rows[1001]["rooms"] == [] and rows[1001]["zoneName"] == "Zona Alfa"
    data(await client.put(f"/api/mobs/{lonely['id']}", json={"extra": {"receptionist": False}}))
    data(await client.put(f"/api/mobs/{spawned['id']}", json={"extra": {"receptionist": False}}))
    assert data(await client.get("/api/content/inns")) == []
