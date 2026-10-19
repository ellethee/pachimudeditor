"""Integrita' dei dati: validazione reset, guardie su vnum/delete, coerenza zone/uscite, null su NOT NULL."""

import httpx
from pachimudeditor.common.enums import Sex
from pachimudeditor_adapter_pachimud.game_models.character import PlayerCharacter
from pachimudeditor_adapter_pachimud.game_models.account import Account
from pachimudeditor_adapter_pachimud.game_models.mob import MobInstance
from pachimudeditor_adapter_pachimud.game_models.object import ObjectInstance

from tests.support.gamedb import get_session_factory
from tests.helpers import by_vnum, data, error_code


async def _zone_id(client: httpx.AsyncClient, vnum: int = 10) -> int:
    """Id della zona con il vnum dato."""
    return (await by_vnum(client, "zones", vnum))["id"]


def _put(client: httpx.AsyncClient, zone_id: int, commands: list[dict]) -> "object":
    """PUT dello script di reset."""
    return client.put(f"/api/zones/{zone_id}/reset-commands", json={"commands": commands})


# --- 1. script di reset -------------------------------------------------------------------------


async def test_reset_structural_422(client: httpx.AsyncClient) -> None:
    """Argomenti mancanti, negativi, direzione/stato porta errati, argStr non ammesso: 422 e nulla salvato."""
    zid = await _zone_id(client)
    bad_commands = [
        {"commandType": 0, "arg1": 1000, "arg2": 1},  # manca la stanza
        {"commandType": 1, "arg1": -1, "arg2": 1, "arg3": 1000},
        {"commandType": 2},  # manca l'oggetto
        {"commandType": 3, "arg1": 1000},  # manca lo slot
        {"commandType": 4, "arg1": 1000},  # manca il contenitore
        {"commandType": 5, "arg1": 1000, "arg2": 6, "argStr": "OPEN"},
        {"commandType": 5, "arg1": 1000, "arg2": 0, "argStr": "ajar"},
        {"commandType": 5, "arg1": 1000, "arg2": 0},
        {"commandType": 6},
        {"commandType": 6, "arg1": 1000, "argStr": "x"},
        {"commandType": 0, "arg1": 1000, "arg2": 1, "arg3": 1000, "argStr": "x"},
    ]
    for bad in bad_commands:
        response = await _put(client, zid, [bad])
        assert response.status_code == 422, bad
    assert len(data(await client.get(f"/api/zones/{zid}/reset-commands"))) == 2


async def test_reset_valid_script_accepted(client: httpx.AsyncClient) -> None:
    """Uno script completo e ben formato viene salvato (stato porta anche minuscolo)."""
    zid = await _zone_id(client)
    script = [
        {"commandType": 0, "arg1": 1000, "arg2": 1, "arg3": 1000},
        {"commandType": 2, "arg1": 1001},
        {"commandType": 3, "arg1": 1000, "argStr": "WIELD"},
        {"commandType": 1, "arg1": 1001, "arg2": 1, "arg3": 1001},
        {"commandType": 4, "arg1": 1000, "arg3": 1001},
        {"commandType": 5, "arg1": 1000, "arg2": 0, "argStr": "closed"},
        {"commandType": 6, "arg1": 1001},
    ]
    assert len(data(await _put(client, zid, script))) == 7


async def test_reset_unknown_vnum_422(client: httpx.AsyncClient) -> None:
    """Vnum inesistenti: 422 con codice stabile, indice del passo e vnum nei params."""
    zid = await _zone_id(client)
    cases = [
        ({"commandType": 0, "arg1": 9999, "arg2": 1, "arg3": 1000}, "zones.reset_unknown_mob", 9999),
        ({"commandType": 0, "arg1": 1000, "arg2": 1, "arg3": 8888}, "zones.reset_unknown_room", 8888),
        ({"commandType": 1, "arg1": 7777, "arg2": 1, "arg3": 1000}, "zones.reset_unknown_object", 7777),
        ({"commandType": 4, "arg1": 1000, "arg3": 6666}, "zones.reset_unknown_object", 6666),
        ({"commandType": 5, "arg1": 5555, "arg2": 0, "argStr": "OPEN"}, "zones.reset_unknown_room", 5555),
    ]
    ok = {"commandType": 6, "arg1": 1000}
    for bad, code, vnum in cases:
        response = await _put(client, zid, [ok, bad])
        assert error_code(response, 422) == code
        assert response.json()["detail"][0]["params"] == {"index": 1, "vnum": vnum}
    assert len(data(await client.get(f"/api/zones/{zid}/reset-commands"))) == 2


async def test_reset_validate_endpoint(client: httpx.AsyncClient) -> None:
    """`validate` riporta errori e warning per passo senza salvare."""
    zid = await _zone_id(client)
    script = [
        {"commandType": 2, "arg1": 1000, "ifFlag": True},  # G senza mob prima + ifFlag sul primo
        {"commandType": 4, "arg1": 1000, "arg3": 1001},  # contenitore non caricato
        {"commandType": 0, "arg1": 9999, "arg2": 0, "arg3": 1000, "arg4": 5},  # mob ignoto, max 0, cap > max
        {"commandType": 1, "arg1": 1000, "arg2": 500, "arg3": 1000},  # max alto
        {"commandType": 5, "arg1": 1002, "arg2": 0, "argStr": "OPEN"},  # nessuna uscita a nord
        {"commandType": 5, "arg1": 1000, "arg2": 0, "argStr": "OPEN"},  # uscita senza porta
        {"commandType": 3, "arg1": 1000},  # slot mancante (errore strutturale)
    ]
    response = await client.post(f"/api/zones/{zid}/reset-commands/validate", json={"commands": script})
    result = data(response)
    assert result["ok"] is False
    found = {(i["index"], i["code"], i["severity"]) for i in result["issues"]}
    assert (0, "zones.reset_if_flag_first", "warning") in found
    assert (0, "zones.reset_no_mob_before", "warning") in found
    assert (1, "zones.reset_container_not_loaded", "warning") in found
    assert (2, "zones.reset_unknown_mob", "error") in found
    assert (2, "zones.reset_max_zero", "warning") in found
    assert (2, "zones.reset_room_cap_above_max", "warning") in found
    assert (3, "zones.reset_max_high", "warning") in found
    assert (4, "zones.reset_no_such_exit", "warning") in found
    assert (5, "zones.reset_exit_without_door", "warning") in found
    assert (6, "zones.reset_slot_required", "error") in found
    assert all(i["message"] and i["message"] != i["code"] for i in result["issues"])
    assert len(data(await client.get(f"/api/zones/{zid}/reset-commands"))) == 2  # non salvato


async def test_reset_validate_ok_and_404(client: httpx.AsyncClient) -> None:
    """Script pulito: ok senza issue; zona inesistente: 404; lingua inglese via Accept-Language."""
    zid = await _zone_id(client)
    script = [{"commandType": 0, "arg1": 1000, "arg2": 1, "arg3": 1000}, {"commandType": 2, "arg1": 1000}]
    assert data(await client.post(f"/api/zones/{zid}/reset-commands/validate", json={"commands": script})) == {"ok": True, "issues": []}
    gone = await client.post("/api/zones/999999/reset-commands/validate", json={"commands": []})
    assert error_code(gone, 404) == "zones.not_found"
    en = await client.post(
        f"/api/zones/{zid}/reset-commands/validate",
        json={"commands": [{"commandType": 0, "arg1": 9999, "arg2": 1, "arg3": 1000}]},
        headers={"Accept-Language": "en"},
    )
    assert data(en)["issues"][0]["message"].startswith("Command 0")


# --- 2. guardie su vnum e delete ----------------------------------------------------------------


async def test_vnum_change_blocked_when_used_by_reset(client: httpx.AsyncClient) -> None:
    """Stanza/mob/oggetto usati da un reset: cambio vnum 409; se liberi (o stesso vnum) e' ammesso."""
    room = await by_vnum(client, "rooms", 1000)
    mob = await by_vnum(client, "mobs", 1000)
    obj = await by_vnum(client, "objects", 1000)
    for kind, row, code in (
        ("rooms", room, "rooms.vnum_in_use"),
        ("mobs", mob, "mobs.vnum_in_use"),
        ("objects", obj, "objects.vnum_in_use"),
    ):
        response = await client.put(f"/api/{kind}/{row['id']}", json={"vnum": 1500})
        assert error_code(response, 409) == code, kind
        assert response.json()["detail"][0]["params"]["count"] >= 1
        same = await client.put(
            f"/api/{kind}/{row['id']}", json={"vnum": row["vnum"], "name": "x"} if kind == "rooms" else {"vnum": row["vnum"]}
        )
        assert same.status_code == 200
    free_room = await by_vnum(client, "rooms", 1002)
    free_mob = await by_vnum(client, "mobs", 1001)
    free_obj = await by_vnum(client, "objects", 1001)
    assert data(await client.put(f"/api/rooms/{free_room['id']}", json={"vnum": 1502}))["vnum"] == 1502
    assert data(await client.put(f"/api/mobs/{free_mob['id']}", json={"vnum": 1501}))["vnum"] == 1501
    assert data(await client.put(f"/api/objects/{free_obj['id']}", json={"vnum": 1503}))["vnum"] == 1503


async def _key_exit(client: httpx.AsyncClient, key_vnum: int) -> dict:
    """Crea sulla stanza 1002 un'uscita a nord chiusa a chiave con la chiave data."""
    room = await by_vnum(client, "rooms", 1002)
    body = {"direction": 0, "doorFlag": 1, "isOpen": False, "isLocked": True, "keyVnum": key_vnum}
    return data(await client.post(f"/api/rooms/{room['id']}/exits", json=body), 201)


async def test_exit_key_blocks_object_vnum_change_and_delete(client: httpx.AsyncClient) -> None:
    """Un oggetto usato come chiave: niente cambio vnum ne' delete; compare in /usage; sbloccato togliendo la chiave."""
    exit_row = await _key_exit(client, 1001)
    obj = await by_vnum(client, "objects", 1001)
    usage = data(await client.get(f"/api/objects/{obj['id']}/usage"))
    assert [(u["source"], u["exitId"], u["roomVnum"], u["commandType"]) for u in usage] == [("exit_key", exit_row["id"], 1002, None)]
    assert error_code(await client.put(f"/api/objects/{obj['id']}", json={"vnum": 1600}), 409) == "objects.vnum_in_use"
    response = await client.delete(f"/api/objects/{obj['id']}")
    assert error_code(response, 409) == "objects.in_exit_key_usage"
    assert response.json()["detail"][0]["params"]["count"] == 1
    room = await by_vnum(client, "rooms", 1002)
    data(await client.put(f"/api/rooms/{room['id']}/exits/{exit_row['id']}", json={"isLocked": False, "keyVnum": None}))
    assert (await client.delete(f"/api/objects/{obj['id']}")).status_code == 204


async def test_delete_with_live_instances_409(client: httpx.AsyncClient) -> None:
    """Istanze vive di mob/oggetto/personaggi: codici dedicati con i conteggi."""
    mob = await by_vnum(client, "mobs", 1001)
    obj = await by_vnum(client, "objects", 1001)
    room = await by_vnum(client, "rooms", 1002)
    async with get_session_factory()() as session:
        account = Account(username="p", password_hash="x")
        session.add(account)
        await session.flush()
        session.add_all(
            [
                MobInstance(prototype_id=mob["id"], room_id=room["id"], hit_points_current=5, hit_points_max=5),
                ObjectInstance(prototype_id=obj["id"], room_id=room["id"]),
                PlayerCharacter(
                    account_id=account.id,
                    name="Pg",
                    hit_points_current=1,
                    hit_points_max=1,
                    current_room_id=room["id"],
                    sex=Sex.NEUTRAL,
                    class_id="c",
                    race_id="r",
                    strength=10,
                    dexterity=10,
                    constitution=10,
                    intelligence=10,
                    wisdom=10,
                    charisma=10,
                    mana_current=1,
                    mana_max=1,
                ),
            ]
        )
        await session.commit()
    response = await client.delete(f"/api/mobs/{mob['id']}")
    assert error_code(response, 409) == "mobs.has_instances"
    assert response.json()["detail"][0]["params"] == {"count": 1}
    response = await client.delete(f"/api/objects/{obj['id']}")
    assert error_code(response, 409) == "objects.has_instances"
    assert response.json()["detail"][0]["params"] == {"count": 1}
    response = await client.delete(f"/api/rooms/{room['id']}")
    assert error_code(response, 409) == "rooms.has_instances"
    assert response.json()["detail"][0]["params"] == {"mobs": 1, "objects": 1, "players": 1}


async def test_room_delete_not_blocked_by_incoming_exits(client: httpx.AsyncClient) -> None:
    """Le uscite altrui verso la stanza NON bloccano la delete (stanza 1001 ha un'uscita entrante da 1000)."""
    room = await by_vnum(client, "rooms", 1001)
    assert (await client.delete(f"/api/rooms/{room['id']}")).status_code == 204


# --- 3. coerenza --------------------------------------------------------------------------------


async def test_zone_patch_final_ranges(client: httpx.AsyncClient) -> None:
    """Il patch parziale e' valutato sui valori finali (stored + patch)."""
    zid = await _zone_id(client)  # 1000-1099, livelli 1-10
    r = await client.put(f"/api/zones/{zid}", json={"topVnum": 500})
    assert error_code(r, 422) == "zones.invalid_vnum_range"
    assert error_code(await client.put(f"/api/zones/{zid}", json={"bottomVnum": 1200}), 422) == "zones.invalid_vnum_range"
    assert error_code(await client.put(f"/api/zones/{zid}", json={"minLevel": 11}), 422) == "zones.invalid_level_range"
    assert error_code(await client.put(f"/api/zones/{zid}", json={"maxLevel": 0}), 422) is None  # ge=1 (Pydantic)
    assert data(await client.put(f"/api/zones/{zid}", json={"bottomVnum": 1010, "minLevel": 3}))["bottomVnum"] == 1010
    assert data(await client.get(f"/api/zones/{zid}"))["topVnum"] == 1099


async def test_zone_clone_range(client: httpx.AsyncClient) -> None:
    """Clone: range omesso -> 0-0; range nuovo valido ok; sovrapposto 409; incompleto o invertito 422."""
    zid = await _zone_id(client)
    plain = data(await client.post(f"/api/zones/{zid}/clone", json={"vnum": 50, "name": "A"}), 201)
    assert (plain["bottomVnum"], plain["topVnum"]) == (0, 0)
    ranged = data(await client.post(f"/api/zones/{zid}/clone", json={"vnum": 51, "name": "B", "bottomVnum": 5000, "topVnum": 5099}), 201)
    assert (ranged["bottomVnum"], ranged["topVnum"]) == (5000, 5099)
    clash = await client.post(f"/api/zones/{zid}/clone", json={"vnum": 52, "name": "C", "bottomVnum": 1050, "topVnum": 1200})
    assert error_code(clash, 409) == "zones.range_overlap"
    assert clash.json()["detail"][0]["params"]["zone_vnum"] == 10
    assert error_code(await client.post(f"/api/zones/{zid}/clone", json={"vnum": 52, "name": "C", "bottomVnum": 6000}), 422) is None
    assert (
        error_code(await client.post(f"/api/zones/{zid}/clone", json={"vnum": 52, "name": "C", "bottomVnum": 7, "topVnum": 3}), 422) is None
    )


async def test_patch_null_on_not_null_is_422(client: httpx.AsyncClient) -> None:
    """`null` esplicito su colonne NOT NULL: 422 (non 409); sui campi opzionali resta ammesso."""
    zone = await by_vnum(client, "zones", 10)
    room = await by_vnum(client, "rooms", 1002)
    mob = await by_vnum(client, "mobs", 1001)
    obj = await by_vnum(client, "objects", 1001)
    for url, field in (
        (f"/api/zones/{zone['id']}", "name"),
        (f"/api/zones/{zone['id']}", "builder"),
        (f"/api/rooms/{room['id']}", "description"),
        (f"/api/rooms/{room['id']}", "flags"),
        (f"/api/mobs/{mob['id']}", "gold"),
        (f"/api/mobs/{mob['id']}", "flags"),
        (f"/api/objects/{obj['id']}", "weight"),
        (f"/api/objects/{obj['id']}", "affects"),
    ):
        assert error_code(await client.put(url, json={field: None}), 422) is None, (url, field)
    assert data(await client.put(f"/api/rooms/{room['id']}", json={"owner": None, "clanId": None}))["owner"] is None
    assert data(await client.put(f"/api/mobs/{mob['id']}", json={"raceId": None}))["raceId"] is None
    assert data(await client.put(f"/api/objects/{obj['id']}", json={"value0": None}))["value0"] is None
    exits = data(await client.get(f"/api/rooms/{(await by_vnum(client, 'rooms', 1000))['id']}"))["exits"]
    ex = exits[0]
    base = f"/api/rooms/{ex['roomId']}/exits/{ex['id']}"
    assert error_code(await client.put(base, json={"isOpen": None}), 422) is None
    assert data(await client.put(base, json={"description": None, "keyVnum": None}))["keyVnum"] is None


async def test_non_negative_numbers(client: httpx.AsyncClient) -> None:
    """weight/cost/rent/gold/experience/healRate/manaRate non negativi."""
    zid = await _zone_id(client)
    obj = {"vnum": 1700, "zoneId": zid, "keywords": "a", "shortDescription": "a"}
    for field in ("weight", "cost", "rent"):
        assert (await client.post("/api/objects", json={**obj, field: -1})).status_code == 422, field
    mob = {"vnum": 1701, "zoneId": zid, "keywords": "a", "shortDescription": "a"}
    for field in ("gold", "experience"):
        assert (await client.post("/api/mobs", json={**mob, field: -1})).status_code == 422, field
    room = {"vnum": 1702, "zoneId": zid, "name": "a"}
    for field in ("healRate", "manaRate"):
        assert (await client.post("/api/rooms", json={**room, field: -1})).status_code == 422, field
    row = await by_vnum(client, "rooms", 1002)
    assert (await client.put(f"/api/rooms/{row['id']}", json={"healRate": -5})).status_code == 422
    assert (await client.put(f"/api/mobs/{(await by_vnum(client, 'mobs', 1001))['id']}", json={"gold": -5})).status_code == 422
    assert (await client.put(f"/api/objects/{(await by_vnum(client, 'objects', 1001))['id']}", json={"cost": -5})).status_code == 422
    assert data(await client.post("/api/rooms", json={**room, "healRate": 0}), 201)["healRate"] == 0


async def test_exit_coherence(client: httpx.AsyncClient) -> None:
    """Regole delle uscite: porta assente, serrata senza chiave, chiave inesistente, uscita su se stessa."""
    room = await by_vnum(client, "rooms", 1002)
    url = f"/api/rooms/{room['id']}/exits"
    cases = [
        ({"direction": 0, "isOpen": False}, "rooms.exit_door_state_invalid"),
        (
            {"direction": 0, "isLocked": True, "doorFlag": 1, "keyVnum": 1000, "isOpen": True} | {"doorFlag": 0},
            "rooms.exit_door_state_invalid",
        ),
        ({"direction": 0, "doorFlag": 1, "isOpen": False, "isLocked": True}, "rooms.exit_locked_needs_key"),
        ({"direction": 0, "doorFlag": 1, "isOpen": False, "isLocked": True, "keyVnum": 4242}, "rooms.exit_key_unknown"),
        ({"direction": 0, "targetRoomId": room["id"]}, "rooms.exit_self_loop"),
    ]
    for body, code in cases:
        assert error_code(await client.post(url, json=body), 422) == code, body
    ok = data(await client.post(url, json={"direction": 0, "doorFlag": 1, "isOpen": False, "isLocked": True, "keyVnum": 1000}), 201)
    # modifica: porta rimossa ma ancora chiusa / chiave inesistente / punta a se stessa
    assert error_code(await client.put(f"{url}/{ok['id']}", json={"doorFlag": 0}), 422) == "rooms.exit_door_state_invalid"
    assert error_code(await client.put(f"{url}/{ok['id']}", json={"keyVnum": None}), 422) == "rooms.exit_locked_needs_key"
    assert error_code(await client.put(f"{url}/{ok['id']}", json={"keyVnum": 4242}), 422) == "rooms.exit_key_unknown"
    assert error_code(await client.put(f"{url}/{ok['id']}", json={"targetRoomId": room["id"]}), 422) == "rooms.exit_self_loop"
    assert data(await client.put(f"{url}/{ok['id']}", json={"description": "ok"}))["description"] == "ok"


async def test_exit_legacy_inconsistent_data_still_editable(client: httpx.AsyncClient) -> None:
    """Un'uscita preesistente incoerente resta modificabile finche' il patch non tocca i campi coinvolti."""
    from pachimudeditor_adapter_pachimud.game_models.room import Exit
    from sqlalchemy import select

    room = await by_vnum(client, "rooms", 1000)
    async with get_session_factory()() as session:
        row = (await session.execute(select(Exit).where(Exit.room_id == room["id"]))).scalars().one()
        row.is_open = False  # doorFlag NONE ma chiusa: incoerente
        await session.commit()
        exit_id = row.id
    done = await client.put(f"/api/rooms/{room['id']}/exits/{exit_id}", json={"description": "x"})
    assert data(done)["description"] == "x"
