"""Comportamenti comuni a tutte le risorse: auth, liste, paginazione, ordinamento, slash finale."""

import httpx
import pytest

from tests.helpers import data, error_code

RESOURCES = ["zones", "rooms", "mobs", "objects"]
PROTECTED = [
    *(f"/api/{r}" for r in RESOURCES),
    "/api/rooms/graph?zoneId=1",
    "/api/meta/enums",
    "/api/meta/races",
    "/api/meta/classes",
    "/api/zones/1/reset-commands",
    "/api/zones/next-vnum",
]


@pytest.mark.parametrize("path", PROTECTED)
async def test_requires_token(anon: httpx.AsyncClient, path: str) -> None:
    """Senza token ogni route risponde 401."""
    assert (await anon.get(path)).status_code == 401


async def test_wrong_password_rejected(anon: httpx.AsyncClient) -> None:
    """Credenziali sbagliate: nessun token."""
    response = await anon.post("/api/auth/token", data={"username": "e2e-user", "password": "sbagliata-sbagliata"})
    assert response.status_code in (400, 401)


@pytest.mark.parametrize("resource", RESOURCES)
async def test_trailing_slash(client: httpx.AsyncClient, anon: httpx.AsyncClient, resource: str) -> None:
    """`/api/<risorsa>/` e' accettato come senza slash, ma resta protetto."""
    assert data(await client.get(f"/api/{resource}/"))["total"] >= 1
    assert (await anon.get(f"/api/{resource}/")).status_code == 401


@pytest.mark.parametrize("resource", RESOURCES)
async def test_list_envelope_and_default_order(client: httpx.AsyncClient, resource: str) -> None:
    """Senza page/pageSize tornano tutte le righe, ordinate per vnum."""
    page = data(await client.get(f"/api/{resource}"))
    assert {"items", "total", "page", "pageSize", "pages"} <= set(page)
    assert len(page["items"]) == page["total"]
    vnums = [i["vnum"] for i in page["items"]]
    assert vnums == sorted(vnums)


@pytest.mark.parametrize("resource", RESOURCES)
async def test_paging(client: httpx.AsyncClient, resource: str) -> None:
    """Con page+pageSize si pagina; pagine oltre la fine sono vuote."""
    page = data(await client.get(f"/api/{resource}", params={"page": 1, "pageSize": 1}))
    assert len(page["items"]) == 1 and page["pageSize"] == 1
    assert page["pages"] == page["total"]
    last = data(await client.get(f"/api/{resource}", params={"page": page["total"], "pageSize": 1}))
    assert len(last["items"]) == 1
    beyond = data(await client.get(f"/api/{resource}", params={"page": page["total"] + 1, "pageSize": 1}))
    assert beyond["items"] == []


@pytest.mark.parametrize("resource", RESOURCES)
async def test_order_by_desc(client: httpx.AsyncClient, resource: str) -> None:
    """`orderBy=-vnum` ordina in modo decrescente."""
    vnums = [i["vnum"] for i in data(await client.get(f"/api/{resource}", params={"orderBy": "-vnum"}))["items"]]
    assert vnums == sorted(vnums, reverse=True)


@pytest.mark.parametrize("resource", RESOURCES)
async def test_invalid_order_by(client: httpx.AsyncClient, resource: str) -> None:
    """Campo non ammesso: 422 con codice stabile e loc query/orderBy."""
    response = await client.get(f"/api/{resource}", params={"orderBy": "nonexistent"})
    assert error_code(response, 422) == "api.invalid_order_by"
    assert response.json()["detail"][0]["loc"] == ["query", "orderBy"]


@pytest.mark.parametrize(
    ("resource", "term", "vnum"),
    [
        ("zones", "Alfa", 10),
        ("rooms", "Cantina", 1002),
        ("mobs", "ratto", 1001),
        ("objects", "sasso", 1001),
        ("zones", "20", 20),
    ],
)
async def test_search(client: httpx.AsyncClient, resource: str, term: str, vnum: int) -> None:
    """`search` filtra per nome/descrizione/vnum."""
    items = data(await client.get(f"/api/{resource}", params={"search": term}))["items"]
    assert [i["vnum"] for i in items] == [vnum]


@pytest.mark.parametrize("resource", ["rooms", "mobs", "objects"])
async def test_zone_filter(client: httpx.AsyncClient, resource: str) -> None:
    """Filtro `zoneId`: la zona vuota non ha contenuto."""
    zones = data(await client.get("/api/zones"))["items"]
    empty = next(z for z in zones if z["vnum"] == 20)
    assert data(await client.get(f"/api/{resource}", params={"zoneId": empty["id"]}))["total"] == 0


@pytest.mark.parametrize("resource", RESOURCES)
async def test_not_found(client: httpx.AsyncClient, resource: str) -> None:
    """Id inesistente: 404 con codice `<risorsa>.not_found`."""
    assert error_code(await client.get(f"/api/{resource}/999999"), 404) == f"{resource}.not_found"
