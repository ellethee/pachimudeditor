"""Istanze vive di mob e oggetti: lista/filtri, creazione da prototipo, validazione, spostamenti, despawn.

L'app `instances` puo' non essere ancora registrata in `src/pachimudeditor/modules.py`: in tal caso il router viene
montato a mano sull'app dei test.
"""

import httpx
import pytest

from pachimudeditor.app import create_editor_app
from pachimudeditor.common.adapters.plugins import available_kinds

app = create_editor_app(extra_kinds=available_kinds())
from tests.helpers import by_vnum, data, error_code

if not any(getattr(route, "path", "").startswith("/api/instances") for route in app.routes):
    from pachimudeditor_adapter_pachimud.apps.instances.root import router

    app.include_router(router, prefix="/api")
    # il mount della SPA su "/" cattura tutto: va riportato in coda dopo la route aggiunta
    _spa = [r for r in app.router.routes if getattr(r, "name", None) == "spa"]
    for _route in _spa:
        app.router.routes.remove(_route)
        app.router.routes.append(_route)

BASE = "/api/instances"


async def _room(client: httpx.AsyncClient, vnum: int) -> int:
    """Id della stanza con il vnum dato."""
    return (await by_vnum(client, "rooms", vnum))["id"]


async def _proto(client: httpx.AsyncClient, resource: str, vnum: int) -> int:
    """Id del prototipo (mobs/objects) con il vnum dato."""
    return (await by_vnum(client, resource, vnum))["id"]


async def _object_proto(client: httpx.AsyncClient, vnum: int, **extra: object) -> int:
    """Crea un prototipo di oggetto nella zona 10 e ne restituisce l'id."""
    zone = await by_vnum(client, "zones", 10)
    body = {"vnum": vnum, "zoneId": zone["id"], "keywords": "x", "shortDescription": f"oggetto {vnum}"} | extra
    return data(await client.post("/api/objects", json=body), 201)["id"]


async def _spawn_mob(client: httpx.AsyncClient, mob_vnum: int = 1000, room_vnum: int = 1000, **extra: object) -> dict:
    """Genera un mob vivo."""
    body = {"prototypeId": await _proto(client, "mobs", mob_vnum), "roomId": await _room(client, room_vnum)} | extra
    return data(await client.post(f"{BASE}/mobs", json=body), 201)


async def _spawn_object(client: httpx.AsyncClient, proto_id: int, kind: str, target: int, **extra: object) -> httpx.Response:
    """POST di un oggetto vivo (risposta grezza)."""
    location = {"kind": kind, "targetId": target} | {k: v for k, v in extra.items() if k == "equippedSlot"}
    body = {"prototypeId": proto_id, "location": location} | {k: v for k, v in extra.items() if k != "equippedSlot"}
    return await client.post(f"{BASE}/objects", json=body)


async def test_spawn_and_get_mob(client: httpx.AsyncClient) -> None:
    """PF tirati dal prototipo (1d8), stanza e zona risolte; GET e lista coerenti."""
    mob = await _spawn_mob(client)
    assert 1 <= mob["hitPointsCurrent"] <= 8 and mob["hitPointsCurrent"] == mob["hitPointsMax"]
    assert mob["roomVnum"] == 1000 and mob["zoneName"] == "Zona Alfa" and mob["prototypeVnum"] == 1000
    assert mob["items"] == [] and mob["gold"] is None and mob["prototypeZoneId"] > 0
    assert data(await client.get(f"{BASE}/mobs/{mob['id']}"))["id"] == mob["id"]
    page = data(await client.get(f"{BASE}/mobs"))
    assert page["total"] == 1 and page["items"][0]["prototypeName"] == "una guardia"


async def test_spawn_mob_validation(client: httpx.AsyncClient) -> None:
    """Prototipo/stanza inesistenti, PF o oro non validi."""
    proto, room = await _proto(client, "mobs", 1000), await _room(client, 1000)
    bad = await client.post(f"{BASE}/mobs", json={"prototypeId": 99999, "roomId": room})
    assert error_code(bad, 422) == "instances.mob_prototype_not_found"
    bad = await client.post(f"{BASE}/mobs", json={"prototypeId": proto, "roomId": 99999})
    assert error_code(bad, 422) == "instances.room_not_found"
    bad = await client.post(f"{BASE}/mobs", json={"prototypeId": proto, "roomId": room, "hitPoints": 0})
    assert error_code(bad, 422) == "instances.hp_min"
    bad = await client.post(f"{BASE}/mobs", json={"prototypeId": proto, "roomId": room, "gold": -1})
    assert error_code(bad, 422) == "instances.negative_value"


async def test_update_mob(client: httpx.AsyncClient) -> None:
    """Modifica PF, oro e stanza; vincoli su PF e stanza."""
    mob = await _spawn_mob(client, hitPoints=10)
    new_room = await _room(client, 1001)
    done = data(
        await client.put(f"{BASE}/mobs/{mob['id']}", json={"hitPointsMax": 20, "hitPointsCurrent": 15, "gold": 40, "roomId": new_room})
    )
    assert (done["hitPointsMax"], done["hitPointsCurrent"], done["gold"], done["roomVnum"]) == (20, 15, 40, 1001)
    url = f"{BASE}/mobs/{mob['id']}"
    assert error_code(await client.put(url, json={"hitPointsCurrent": 99}), 422) == "instances.hp_exceeds_max"
    assert error_code(await client.put(url, json={"hitPointsMax": 5}), 422) == "instances.hp_exceeds_max"
    assert error_code(await client.put(url, json={"hitPointsCurrent": 0}), 422) == "instances.hp_min"
    assert error_code(await client.put(url, json={"gold": -5}), 422) == "instances.negative_value"
    assert error_code(await client.put(url, json={"roomId": 424242}), 422) == "instances.room_not_found"
    assert data(await client.put(url, json={"gold": None}))["gold"] is None
    assert error_code(await client.put(f"{BASE}/mobs/9999", json={"gold": 1}), 404) == "instances.mob_not_found"


async def test_list_filters_search_order_and_paging(client: httpx.AsyncClient) -> None:
    """Filtri per vnum prototipo / stanza / zona, ricerca, ordinamento, paginazione, orderBy invalido."""
    await _spawn_mob(client, 1000, 1000)
    await _spawn_mob(client, 1001, 1001)
    await _spawn_mob(client, 1001, 1001)

    async def total(**params: object) -> int:
        return data(await client.get(f"{BASE}/mobs", params=params))["total"]

    assert await total() == 3
    assert await total(prototypeVnum=1001) == 2
    assert await total(roomId=await _room(client, 1000)) == 1
    assert await total(zoneId=(await by_vnum(client, "zones", 10))["id"]) == 3
    assert await total(zoneId=(await by_vnum(client, "zones", 20))["id"]) == 0
    assert await total(search="ratto") == 2
    assert await total(search="Piazza") == 1
    page = data(await client.get(f"{BASE}/mobs", params={"page": 1, "pageSize": 2, "orderBy": "prototypeVnum"}))
    assert len(page["items"]) == 2 and page["total"] == 3 and page["pages"] == 2
    assert page["items"][0]["prototypeVnum"] == 1000
    bad = await client.get(f"{BASE}/mobs", params={"orderBy": "nope"})
    assert error_code(bad, 422) == "api.invalid_order_by"


async def test_spawn_object_in_room_and_filters(client: httpx.AsyncClient) -> None:
    """Oggetto a terra: stanza effettiva, filtri kind/holder/prototipo/tipo."""
    sword = await _proto(client, "objects", 1000)
    room = await _room(client, 1000)
    obj = data(await _spawn_object(client, sword, "room", room), 201)
    assert obj["locationKind"] == "room" and obj["roomVnum"] == 1000 and obj["zoneName"] == "Zona Alfa"
    got = data(await client.get(f"{BASE}/objects", params={"kind": "room", "holderId": room}))
    assert got["total"] == 1
    assert data(await client.get(f"{BASE}/objects", params={"prototypeVnum": 1001}))["total"] == 0
    assert data(await client.get(f"{BASE}/objects", params={"objectType": 6}))["total"] == 1
    assert data(await client.get(f"{BASE}/objects", params={"roomId": room}))["total"] == 1
    bad = await client.get(f"{BASE}/objects", params={"kind": "boh"})
    assert error_code(bad, 422) == "instances.invalid_location_kind"


async def test_container_rules(client: httpx.AsyncClient) -> None:
    """Contenitore: bersaglio valido, capacita', niente annidamento, effective room dei contenuti."""
    sack = await _object_proto(client, 1070, objectType=3, value0=1)
    sword = await _proto(client, "objects", 1000)
    stone = await _proto(client, "objects", 1001)
    room = await _room(client, 1000)
    bag = data(await _spawn_object(client, sack, "room", room), 201)
    inside = data(await _spawn_object(client, sword, "container", bag["id"]), 201)
    assert inside["locationKind"] == "container" and inside["roomVnum"] == 1000
    full = await _spawn_object(client, stone, "container", bag["id"])
    assert error_code(full, 422) == "instances.container_full"
    detail = data(await client.get(f"{BASE}/objects/{bag['id']}"))
    assert detail["contentCount"] == 1 and [c["id"] for c in detail["contents"]] == [inside["id"]]
    # non e' un contenitore / inesistente / contenitore dentro contenitore
    assert error_code(await _spawn_object(client, stone, "container", inside["id"]), 422) == "instances.not_a_container"
    assert error_code(await _spawn_object(client, stone, "container", 99999), 422) == "instances.container_not_found"
    assert error_code(await _spawn_object(client, sack, "container", bag["id"]), 422) == "instances.container_in_container"
    # un oggetto non si mette dentro se stesso
    put = await client.put(f"{BASE}/objects/{bag['id']}", json={"location": {"kind": "container", "targetId": bag["id"]}})
    assert error_code(put, 422) == "instances.container_self"
    # lo spostamento nello stesso contenitore pieno e' ammesso
    same = await client.put(f"{BASE}/objects/{inside['id']}", json={"location": {"kind": "container", "targetId": bag["id"]}})
    assert data(same)["locationKind"] == "container"


async def test_equip_on_mob(client: httpx.AsyncClient) -> None:
    """Indossare su un mob: slot dai wearFlags, occupato, non ammesso fuori da mob/personaggio."""
    helm = await _object_proto(client, 1071, wearFlags=["take", "head"])
    helm2 = await _object_proto(client, 1072, wearFlags=["take", "head"])
    mob = await _spawn_mob(client)
    ok = data(await _spawn_object(client, helm, "mob", mob["id"], equippedSlot="head"), 201)
    assert ok["equippedSlot"] == "head" and ok["roomVnum"] == 1000 and ok["wearSlots"] == ["head"]
    assert data(await client.get(f"{BASE}/mobs/{mob['id']}"))["itemCount"] == 1
    assert error_code(await _spawn_object(client, helm2, "mob", mob["id"], equippedSlot="head"), 422) == "instances.slot_taken"
    assert error_code(await _spawn_object(client, helm2, "mob", mob["id"], equippedSlot="feet"), 422) == "instances.slot_invalid"
    assert error_code(await _spawn_object(client, helm2, "mob", mob["id"], equippedSlot="take"), 422) == "instances.slot_invalid"
    room = await _room(client, 1000)
    assert error_code(await _spawn_object(client, helm2, "room", room, equippedSlot="head"), 422) == "instances.slot_not_allowed"
    assert error_code(await _spawn_object(client, helm2, "mob", 99999), 422) == "instances.holder_not_found"
    assert error_code(await _spawn_object(client, helm2, "character", 99999), 422) == "instances.holder_not_found"
    assert error_code(await _spawn_object(client, helm2, "boh", 1), 422) == "instances.invalid_location_kind"
    # spostamento dell'oggetto equipaggiato a terra: slot azzerato
    moved = data(await client.put(f"{BASE}/objects/{ok['id']}", json={"location": {"kind": "room", "targetId": room}}))
    assert moved["locationKind"] == "room" and moved["equippedSlot"] is None


async def test_object_state_rules(client: httpx.AsyncClient) -> None:
    """Cariche solo per bacchette/bastoni, liquido solo per contenitori di liquido, niente negativi."""
    wand = await _object_proto(client, 1073, objectType=13)
    bottle = await _object_proto(client, 1074, objectType=4)
    sword = await _proto(client, "objects", 1000)
    room = await _room(client, 1000)
    good = data(await _spawn_object(client, wand, "room", room, charges=3), 201)
    assert good["charges"] == 3
    assert error_code(await _spawn_object(client, sword, "room", room, charges=1), 422) == "instances.charges_not_allowed"
    assert error_code(await _spawn_object(client, sword, "room", room, liquidAmount=1), 422) == "instances.liquid_not_allowed"
    assert error_code(await _spawn_object(client, wand, "room", room, charges=-1), 422) == "instances.negative_value"
    drink = data(await _spawn_object(client, bottle, "room", room, liquidAmount=5), 201)
    upd = data(await client.put(f"{BASE}/objects/{drink['id']}", json={"liquidAmount": 2, "liquidPoisoned": True}))
    assert upd["liquidAmount"] == 2 and upd["liquidPoisoned"] is True
    bad = await client.put(f"{BASE}/objects/{drink['id']}", json={"location": None})
    assert error_code(bad, 422) == "instances.location_empty"
    assert error_code(await _spawn_object(client, 99999, "room", room), 422) == "instances.object_prototype_not_found"
    assert error_code(await client.get(f"{BASE}/objects/99999"), 404) == "instances.object_not_found"


@pytest.mark.parametrize("policy", ["destroy", "drop"])
async def test_despawn_mob_contents(client: httpx.AsyncClient, policy: str) -> None:
    """Despawn di un mob: `destroy` elimina gli oggetti, `drop` li lascia nella stanza senza slot."""
    helm = await _object_proto(client, 1075, wearFlags=["head"])
    mob = await _spawn_mob(client)
    held = data(await _spawn_object(client, helm, "mob", mob["id"], equippedSlot="head"), 201)
    assert (await client.delete(f"{BASE}/mobs/{mob['id']}", params={"contents": policy})).status_code == 204
    assert error_code(await client.get(f"{BASE}/mobs/{mob['id']}"), 404) == "instances.mob_not_found"
    after = await client.get(f"{BASE}/objects/{held['id']}")
    if policy == "destroy":
        assert error_code(after, 404) == "instances.object_not_found"
    else:
        obj = data(after)
        assert obj["locationKind"] == "room" and obj["equippedSlot"] is None and obj["roomVnum"] == 1000


@pytest.mark.parametrize("policy", ["destroy", "drop"])
async def test_despawn_container_contents(client: httpx.AsyncClient, policy: str) -> None:
    """Despawn di un contenitore: contenuto distrutto o lasciato nella stanza."""
    sack = await _object_proto(client, 1076, objectType=3)
    sword = await _proto(client, "objects", 1000)
    room = await _room(client, 1000)
    bag = data(await _spawn_object(client, sack, "room", room), 201)
    inner = data(await _spawn_object(client, sword, "container", bag["id"]), 201)
    assert (await client.delete(f"{BASE}/objects/{bag['id']}", params={"contents": policy})).status_code == 204
    after = await client.get(f"{BASE}/objects/{inner['id']}")
    if policy == "destroy":
        assert error_code(after, 404) == "instances.object_not_found"
    else:
        assert data(after)["locationKind"] == "room"
    bad = await client.delete(f"{BASE}/objects/{bag['id']}", params={"contents": "boh"})
    assert error_code(bad, 422) == "instances.invalid_contents_policy"


async def test_prototype_delete_blocked_by_instance(client: httpx.AsyncClient) -> None:
    """Il prototipo con istanze vive non si elimina (409 `mobs.has_instances`); dopo il despawn si'."""
    mob = await _spawn_mob(client, 1001, 1001)
    proto = await _proto(client, "mobs", 1001)
    assert error_code(await client.delete(f"/api/mobs/{proto}"), 409) == "mobs.has_instances"
    assert (await client.delete(f"{BASE}/mobs/{mob['id']}")).status_code == 204
    assert (await client.delete(f"/api/mobs/{proto}")).status_code == 204


async def test_requires_auth(anon: httpx.AsyncClient) -> None:
    """Senza token: 401."""
    assert (await anon.get(f"{BASE}/mobs")).status_code == 401
