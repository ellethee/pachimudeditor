"""App players: account, personaggi, inventario. Monta il modulo da se' se non e' ancora registrato."""

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from pachifast import create_app

from pachimudeditor_adapter_pachimud.apps.players.module import module as players_module
from pachimudeditor.common.adapters.plugins import available_kinds
from pachimudeditor.modules import build_modules

MODULES = build_modules(available_kinds())
from tests.helpers import by_vnum, data, error_code

_modules = MODULES if any(m.name == "players" for m in MODULES) else (*MODULES, players_module)
players_app = create_app(_modules)


@pytest_asyncio.fixture
async def pc(token: str) -> AsyncIterator[httpx.AsyncClient]:
    """Client autenticato verso l'app con il modulo players."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=players_app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as c:
        yield c


async def _account(c: httpx.AsyncClient, username: str = "mario", email: str | None = "mario@example.com") -> dict:
    """Crea un account di prova."""
    return data(await c.post("/api/players/accounts", json={"username": username, "password": "password123", "email": email}), 201)


async def _char(c: httpx.AsyncClient, account_id: int, name: str = "Gandalf", **extra: object) -> int:
    """Inserisce un personaggio direttamente nel DB di test (non esiste un endpoint di creazione)."""
    from pachimudeditor_adapter_pachimud.game_models.enums import Sex
    from pachimudeditor_adapter_pachimud.game_models.character import PlayerCharacter

    from tests.support.gamedb import get_session_factory

    async with get_session_factory()() as s:
        row = PlayerCharacter(
            account_id=account_id,
            name=name,
            hit_points_current=10,
            hit_points_max=10,
            sex=Sex.MALE,
            class_id="warrior",
            race_id="human",
            strength=12,
            dexterity=12,
            constitution=12,
            intelligence=12,
            wisdom=12,
            charisma=12,
            mana_current=5,
            mana_max=5,
            **extra,
        )
        s.add(row)
        await s.commit()
        return row.id


async def test_auth_required(anon: httpx.AsyncClient) -> None:
    """Senza token: 401."""
    assert (
        await httpx.AsyncClient(transport=httpx.ASGITransport(app=players_app), base_url="http://t").get("/api/players/accounts")
    ).status_code == 401


async def test_account_crud_and_no_hash(pc: httpx.AsyncClient) -> None:
    """Crea, legge, lista, modifica email, ban/unban, password: mai `passwordHash`."""
    acc = await _account(pc)
    assert "passwordHash" not in acc and "password_hash" not in acc and acc["isBanned"] is False
    page = data(await pc.get("/api/players/accounts", params={"page": 1, "pageSize": 10, "search": "mar"}))
    assert page["total"] == 1 and "passwordHash" not in page["items"][0]
    got = data(await pc.put(f"/api/players/accounts/{acc['id']}", json={"email": "nuovo@example.com"}))
    assert got["email"] == "nuovo@example.com"
    assert data(await pc.post(f"/api/players/accounts/{acc['id']}/ban"))["isBanned"] is True
    assert data(await pc.get("/api/players/accounts", params={"isBanned": True}))["total"] == 1
    assert data(await pc.post(f"/api/players/accounts/{acc['id']}/unban"))["isBanned"] is False
    data(await pc.post(f"/api/players/accounts/{acc['id']}/password", json={"password": "altrapassword1"}))
    from pachimudeditor_adapter_pachimud.security import verify_password
    from pachimudeditor_adapter_pachimud.game_models.account import Account

    from tests.support.gamedb import get_session_factory

    async with get_session_factory()() as s:
        row = await s.get(Account, acc["id"])
        assert verify_password(row.password_hash, "altrapassword1")
    assert (await pc.delete(f"/api/players/accounts/{acc['id']}")).status_code == 204
    assert error_code(await pc.get(f"/api/players/accounts/{acc['id']}"), 404) == "players.account_not_found"


async def test_account_unique_and_validation(pc: httpx.AsyncClient) -> None:
    """Username/email duplicati: 409 con codici; password corta: 422."""
    await _account(pc)
    r = await pc.post("/api/players/accounts", json={"username": "mario", "password": "password123"})
    assert error_code(r, 409) == "players.username_taken"
    r = await pc.post("/api/players/accounts", json={"username": "luigi", "password": "password123", "email": "mario@example.com"})
    assert error_code(r, 409) == "players.email_taken"
    other = await _account(pc, "luigi", None)
    r = await pc.put(f"/api/players/accounts/{other['id']}", json={"email": "mario@example.com"})
    assert error_code(r, 409) == "players.email_taken"
    assert (await pc.post("/api/players/accounts", json={"username": "x1y2", "password": "corta"})).status_code == 422
    assert (await pc.post("/api/players/accounts", json={"username": "abc", "password": "password123", "email": "no"})).status_code == 422


async def test_account_delete_blocked_and_cascade(pc: httpx.AsyncClient) -> None:
    """Con personaggi: 409; con cascade elimina account, personaggi e oggetti."""
    acc = await _account(pc)
    cid = await _char(pc, acc["id"])
    data(await pc.post(f"/api/players/characters/{cid}/inventory", json={"vnum": 1000}), 201)
    r = await pc.delete(f"/api/players/accounts/{acc['id']}")
    assert error_code(r, 409) == "players.account_has_characters"
    assert r.json()["detail"][0]["params"]["count"] == 1
    assert data(await pc.get(f"/api/players/accounts/{acc['id']}"))["characterCount"] == 1
    assert (await pc.delete(f"/api/players/accounts/{acc['id']}", params={"cascade": True})).status_code == 204
    assert error_code(await pc.get(f"/api/players/characters/{cid}"), 404) == "players.character_not_found"


async def test_characters_list_edit_teleport_delete(pc: httpx.AsyncClient) -> None:
    """Lista filtrata per account, modifica con validazioni FK, teletrasporto, delete."""
    a1, a2 = await _account(pc), await _account(pc, "luigi", None)
    c1 = await _char(pc, a1["id"], "Gandalf")
    await _char(pc, a2["id"], "Frodo")
    page = data(await pc.get("/api/players/characters", params={"accountId": a1["id"]}))
    assert [i["name"] for i in page["items"]] == ["Gandalf"] and page["items"][0]["accountUsername"] == "mario"
    assert data(await pc.get("/api/players/characters", params={"search": "frod"}))["total"] == 1

    room = await by_vnum(pc, "rooms", 1001)
    tp = data(await pc.post(f"/api/players/characters/{c1}/teleport", json={"roomId": room["id"]}))
    assert tp["currentRoomId"] == room["id"] and tp["currentRoomVnum"] == 1001
    assert error_code(await pc.post(f"/api/players/characters/{c1}/teleport", json={"roomId": 99999}), 422) == "players.invalid_room"

    ok = data(
        await pc.put(
            f"/api/players/characters/{c1}", json={"level": 7, "gold": 50, "title": "il Grigio", "position": 5, "currentRoomId": None}
        )
    )
    assert ok["level"] == 7 and ok["position"] == 5 and ok["currentRoomId"] is None
    bad = {"accountId": 9999}, {"currentRoomId": 9999}, {"classId": "nope"}, {"raceId": "nope"}
    codes = ["players.invalid_account", "players.invalid_room", "players.invalid_class", "players.invalid_race"]
    for body, code in zip(bad, codes):
        assert error_code(await pc.put(f"/api/players/characters/{c1}", json=body), 422) == code
    assert error_code(await pc.put(f"/api/players/characters/{c1}", json={"name": "Frodo"}), 409) == "players.name_taken"
    assert (await pc.put(f"/api/players/characters/{c1}", json={"level": None})).status_code == 422
    assert data(await pc.put(f"/api/players/characters/{c1}", json={"accountId": a2["id"], "classId": "mage"}))["accountId"] == a2["id"]
    assert (await pc.delete(f"/api/players/characters/{c1}")).status_code == 204


async def test_lookups(pc: httpx.AsyncClient) -> None:
    """Opzioni sesso/posizione e contenuti YAML."""
    lk = data(await pc.get("/api/players/lookups"))
    assert lk["sex"] and lk["position"] and lk["races"] and lk["classes"]


async def test_inventory(pc: httpx.AsyncClient) -> None:
    """Aggiunta per vnum/id, equip, rimozione; blocco delete personaggio e cascade."""
    acc = await _account(pc)
    cid = await _char(pc, acc["id"])
    base = f"/api/players/characters/{cid}/inventory"
    sword = data(await pc.post(base, json={"vnum": 1000}), 201)
    proto = await by_vnum(pc, "objects", 1001)
    rock = data(await pc.post(base, json={"prototypeId": proto["id"]}), 201)
    assert sword["shortDescription"] == "una spada" and rock["vnum"] == 1001
    assert error_code(await pc.post(base, json={"vnum": 99999}), 422) == "players.invalid_prototype"
    assert error_code(await pc.post(base, json={}), 422) == "players.prototype_required"
    eq = data(await pc.put(f"{base}/{sword['id']}", json={"equippedSlot": "wield"}))
    assert eq["equippedSlot"] == "wield"
    assert data(await pc.put(f"{base}/{sword['id']}", json={"equippedSlot": None}))["equippedSlot"] is None
    assert len(data(await pc.get(base))) == 2
    assert data(await pc.get(f"/api/players/characters/{cid}"))["itemCount"] == 2
    assert error_code(await pc.delete(f"/api/players/characters/{cid}"), 409) == "players.character_has_items"
    assert (await pc.delete(f"{base}/{rock['id']}")).status_code == 204
    assert error_code(await pc.delete(f"{base}/{rock['id']}"), 404) == "players.item_not_found"
    assert (await pc.delete(f"/api/players/characters/{cid}", params={"cascade": True})).status_code == 204


async def test_inventory_container_contents(pc: httpx.AsyncClient) -> None:
    """Gli oggetti dentro un contenitore del personaggio compaiono e non sono equipaggiabili."""
    from pachimudeditor_adapter_pachimud.game_models.object import ObjectInstance

    from tests.support.gamedb import get_session_factory

    acc = await _account(pc)
    cid = await _char(pc, acc["id"])
    base = f"/api/players/characters/{cid}/inventory"
    bag = data(await pc.post(base, json={"vnum": 1000}), 201)
    proto = await by_vnum(pc, "objects", 1001)
    async with get_session_factory()() as s:
        inner = ObjectInstance(prototype_id=proto["id"], container_instance_id=bag["id"])
        s.add(inner)
        await s.commit()
        inner_id = inner.id
    items = data(await pc.get(base))
    assert {i["id"] for i in items} == {bag["id"], inner_id}
    assert error_code(await pc.put(f"{base}/{inner_id}", json={"equippedSlot": "held"}), 422) == "players.item_in_container"
    assert (await pc.delete(f"{base}/{bag['id']}")).status_code == 204
    assert data(await pc.get(base)) == []
