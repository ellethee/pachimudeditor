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


async def test_list_filters_and_ordering_http(client: httpx.AsyncClient) -> None:
    """Filtri/ordinamenti sulle statistiche via query string (alias camelCase, parametri ripetuti, elenchi con virgole)."""
    specs = {
        1070: {"level": 30, "sex": 1, "gold": 100, "armorClass": 10, "thac0": 5, "alignment": -300, "flags": ["sentinel", "aggressive"], "hpBonus": 7},
        1071: {"level": 31, "sex": 2, "gold": 0, "armorClass": -5, "thac0": 8, "alignment": 300, "flags": ["sentinel"]},
        1072: {"level": 32, "sex": 0, "gold": 500, "armorClass": 0, "thac0": 5, "alignment": 0},
    }  # fmt: skip
    for vnum, spec in specs.items():
        data(await client.post("/api/mobs", json=await _body(client, vnum, **spec)), 201)

    async def vnums(**params: object) -> list[int]:
        page = data(await client.get("/api/mobs", params={"minLevel": 30, "orderBy": "vnum", **params}))
        return [m["vnum"] for m in page["items"]]

    assert await vnums() == [1070, 1071, 1072]
    assert await vnums(sex=[1, 2]) == [1070, 1071] and await vnums(sex="1,2") == [1070, 1071]  # ripetuto e con virgole (alova)
    assert await vnums(flag=["sentinel", "aggressive"]) == [1070] and await vnums(flag="SENTINEL") == [1070, 1071]
    assert await vnums(minGold=1, maxGold=100) == [1070] and await vnums(minAlignment=0) == [1071, 1072]
    assert await vnums(minThac0=5, maxThac0=5) == [1070, 1072] and await vnums(maxArmorClass=0) == [1071, 1072]
    assert await vnums(minHpBonus=1) == [1070] and await vnums(minLevel=31, maxLevel=31) == [1071]
    assert await vnums(orderBy="-gold") == [1072, 1070, 1071] and await vnums(orderBy="armorClass") == [1071, 1072, 1070]
    assert await vnums(orderBy="thac0,-vnum") == [1072, 1070, 1071] and await vnums(orderBy="-alignment") == [1071, 1072, 1070]
    assert await vnums(orderBy="-raceId") == [1070, 1071, 1072]  # nessuna razza: tutti nulli, decide il vnum
    assert await vnums(raceId="orco,elfo") == [] and await vnums(classId=["guerriero"]) == []
    assert await vnums(zoneId=(await by_vnum(client, "zones", 10))["id"], flag="aggressive") == [1070]


async def test_list_invalid_filters_422(client: httpx.AsyncClient) -> None:
    """Parametri di lista non validi: 422 (codici stabili dove previsto), mai 500."""
    assert error_code(await client.get("/api/mobs", params={"minLevel": 9, "maxLevel": 1}), 422) == "mobs.invalid_range"
    assert error_code(await client.get("/api/mobs", params={"minHpBonus": 9, "maxHpBonus": 1}), 422) == "mobs.invalid_range"
    assert error_code(await client.get("/api/mobs", params={"sex": 99}), 422) == "mobs.invalid_sex"
    assert error_code(await client.get("/api/mobs", params={"orderBy": "nope"}), 422) == "api.invalid_order_by"
    for bad in ({"minLevel": "x"}, {"sex": "abc"}, {"maxGold": 10**12}):
        assert (await client.get("/api/mobs", params=bad)).status_code == 422, bad


async def test_trainer_filter_http(client: httpx.AsyncClient) -> None:
    """`trainer` (booleano, true/false) filtra i mob con il flag `guildmaster`; `isTrainer` e' nel DTO; valori non validi: 422."""
    data(await client.post("/api/mobs", json=await _body(client, 1080, level=40, flags=["guildmaster"])), 201)
    data(await client.post("/api/mobs", json=await _body(client, 1081, level=40, flags=["sentinel"])), 201)

    async def vnums(**params: object) -> list[int]:
        page = data(await client.get("/api/mobs", params={"minLevel": 40, "orderBy": "vnum", **params}))
        return [m["vnum"] for m in page["items"]]

    assert await vnums() == [1080, 1081]
    assert await vnums(trainer="true") == [1080] and await vnums(trainer="false") == [1081]
    assert await vnums(trainer=True) == [1080] and await vnums(trainer=True, flag="guildmaster") == [1080]
    items = {m["vnum"]: m for m in data(await client.get("/api/mobs", params={"minLevel": 40}))["items"]}
    assert items[1080]["isTrainer"] is True and items[1081]["isTrainer"] is False
    assert (await client.get("/api/mobs", params={"trainer": "forse"})).status_code == 422
