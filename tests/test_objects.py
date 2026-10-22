"""Object prototype: CRUD, vnum duplicato, uso nei reset, validazione."""

import httpx

from tests.helpers import by_vnum, data, error_code


async def _body(client: httpx.AsyncClient, vnum: int, /, **extra: object) -> dict:
    """Corpo minimo di creazione di un oggetto nella zona 10."""
    zone = await by_vnum(client, "zones", 10)
    return {"vnum": vnum, "zoneId": zone["id"], "keywords": "elmo", "shortDescription": "un elmo"} | extra


async def test_crud_happy_path(client: httpx.AsyncClient) -> None:
    """Crea con flag e affects, legge, modifica, elimina."""
    obj = data(
        await client.post(
            "/api/objects",
            json=await _body(client, 1060, extraFlags=["glow"], wearFlags=["head"], affects={"hitroll": 2}, objectType=9, value0=3),
        ),
        201,
    )
    assert obj["extraFlags"] == ["glow"] and obj["wearFlags"] == ["head"] and obj["affects"] == {"hitroll": 2}
    assert obj["objectType"] == 9 and obj["value0"] == 3 and obj["value1"] is None
    patched = data(await client.put(f"/api/objects/{obj['id']}", json={"extraFlags": [], "cost": 7}))
    assert patched["extraFlags"] == [] and patched["cost"] == 7 and patched["wearFlags"] == ["head"]
    assert data(await client.get(f"/api/objects/{obj['id']}"))["keywords"] == "elmo"
    assert (await client.delete(f"/api/objects/{obj['id']}")).status_code == 204
    assert error_code(await client.get(f"/api/objects/{obj['id']}"), 404) == "objects.not_found"


async def test_duplicate_vnum_409(client: httpx.AsyncClient) -> None:
    """Vnum duplicato: 409 `objects.vnum_taken`, anche in modifica."""
    response = await client.post("/api/objects", json=await _body(client, 1000))
    assert error_code(response, 409) == "objects.vnum_taken"
    assert response.json()["detail"][0]["params"]["vnum"] == 1000
    obj = await by_vnum(client, "objects", 1001)
    assert error_code(await client.put(f"/api/objects/{obj['id']}", json={"vnum": 1000}), 409) == "objects.vnum_taken"


async def test_validation_422(client: httpx.AsyncClient) -> None:
    """Keywords vuote, tipo inesistente, affects non numerici."""
    for bad in ({"keywords": ""}, {"objectType": 9999}, {"affects": {"x": "abc"}}):
        assert (await client.post("/api/objects", json=await _body(client, 1061, **bad))).status_code == 422, bad


async def test_delete_in_use_by_reset_409(client: httpx.AsyncClient) -> None:
    """Oggetto referenziato da un reset: 409 `objects.in_reset_usage`; si puo' eliminare quello libero."""
    obj = await by_vnum(client, "objects", 1000)
    assert len(data(await client.get(f"/api/objects/{obj['id']}/usage"))) == 1
    assert error_code(await client.delete(f"/api/objects/{obj['id']}"), 409) == "objects.in_reset_usage"
    free = await by_vnum(client, "objects", 1001)
    assert (await client.delete(f"/api/objects/{free['id']}")).status_code == 204


async def test_container_counts_as_usage(client: httpx.AsyncClient) -> None:
    """Un oggetto usato come contenitore (arg3 di PUT_OBJECT) e' considerato in uso."""
    zone = await by_vnum(client, "zones", 10)
    cmds = {"commands": [{"commandType": 4, "arg1": 1000, "arg2": 1, "arg3": 1001, "arg4": 1}]}
    data(await client.put(f"/api/zones/{zone['id']}/reset-commands", json=cmds))
    free = await by_vnum(client, "objects", 1001)
    assert error_code(await client.delete(f"/api/objects/{free['id']}"), 409) == "objects.in_reset_usage"


async def test_list_filters_and_ordering_http(client: httpx.AsyncClient) -> None:
    """Filtri/ordinamenti sulle statistiche via query string (alias camelCase, parametri ripetuti), rent compreso."""
    specs = {
        1070: {"objectType": 1, "weight": 5, "cost": 100, "rent": 10, "value0": 2, "extraFlags": ["glow"], "wearFlags": ["take"], "affects": {"hitroll": 3}},
        1071: {"objectType": 2, "weight": 20, "cost": 50, "rent": 5, "value0": -4, "extraFlags": ["glow", "hum"], "wearFlags": ["take", "body"]},
        1072: {"objectType": 9, "weight": 1, "cost": 500, "rent": 0},
    }  # fmt: skip
    for vnum, spec in specs.items():
        data(await client.post("/api/objects", json=await _body(client, vnum, **spec)), 201)

    async def vnums(**params: object) -> list[int]:
        page = data(await client.get("/api/objects", params={"search": "elmo", "orderBy": "vnum", **params}))
        return [o["vnum"] for o in page["items"] if o["vnum"] >= 1070]

    assert await vnums() == [1070, 1071, 1072]
    assert await vnums(objectType=[1, 9]) == [1070, 1072]
    assert await vnums(minRent=1, maxRent=9) == [1071]
    assert await vnums(minCost=60) == [1070, 1072] and await vnums(maxWeight=5) == [1070, 1072]
    assert await vnums(minValue0=-10, maxValue0=0) == [1071]  # value0 nullo (1072) escluso dagli intervalli
    assert await vnums(objectType="1,9") == [1070, 1072] and await vnums(wearFlag="take,body") == [1071]  # elenco con virgole (alova)
    assert await vnums(extraFlag=["glow", "hum"]) == [1071] and await vnums(wearFlag="body") == [1071]
    assert await vnums(affect="hitroll", minAffect=3) == [1070] and await vnums(affect="hitroll", minAffect=4) == []
    assert await vnums(orderBy="-cost") == [1072, 1070, 1071] and await vnums(orderBy="rent") == [1072, 1071, 1070]
    assert await vnums(orderBy="-value0") == [1070, 1071, 1072] and await vnums(orderBy="value0") == [1071, 1070, 1072]
    assert await vnums(orderBy="shortDescription,-weight") == [1071, 1070, 1072]


async def test_list_invalid_filters_422(client: httpx.AsyncClient) -> None:
    """Parametri di lista non validi: 422 (codici stabili dove previsto), mai 500."""
    assert error_code(await client.get("/api/objects", params={"minCost": 9, "maxCost": 1}), 422) == "objects.invalid_range"
    assert error_code(await client.get("/api/objects", params={"objectType": 999}), 422) == "objects.invalid_object_type"
    assert error_code(await client.get("/api/objects", params={"minAffect": 1}), 422) == "objects.affect_required"
    assert error_code(await client.get("/api/objects", params={"orderBy": "nope"}), 422) == "api.invalid_order_by"
    for bad in ({"minCost": "x"}, {"objectType": "abc"}, {"maxValue2": 10**12}):
        assert (await client.get("/api/objects", params=bad)).status_code == 422, bad
