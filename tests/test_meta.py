"""Meta: enum per le select, razze e classi, health."""

import httpx

from tests.helpers import data


async def test_enums(client: httpx.AsyncClient) -> None:
    """Tutte le enum previste, come coppie {value, label} con value intero."""
    enums = data(await client.get("/api/meta/enums"))
    assert set(enums) == {"sectorType", "direction", "doorFlag", "zoneResetMode", "sex", "objectType", "zoneCommandType"}
    for options in enums.values():
        assert options and all(isinstance(o["value"], int) and o["label"] for o in options)
    assert [o["value"] for o in enums["direction"]] == [0, 1, 2, 3, 4, 5]
    assert enums["zoneCommandType"][0] == {"value": 0, "label": "Load mob"}


async def test_races_and_classes(client: httpx.AsyncClient) -> None:
    """Razze e classi dagli YAML di definitions/ (config temporanea, path assoluto)."""
    for name in ("races", "classes"):
        items = data(await client.get(f"/api/meta/{name}"))
        assert items and all({"id", "name"} == set(i) for i in items)


async def test_health_is_public(anon: httpx.AsyncClient) -> None:
    """Il liveness probe e' pubblico."""
    assert (await anon.get("/api/health/")).status_code == 200
