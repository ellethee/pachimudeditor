"""Adapter pachimud su file YAML: descrittori, file per area, oggetti per tipo, zone nuove, file rotti, vnum duplicate."""

from pathlib import Path

import httpx
import pytest

from pachimudeditor.common.adapters.registry import get_registry
from tests.helpers import by_vnum, data, error_code
from tests.support.describe_check import assert_describe_matches, emitted_extra_keys
from tests.support.stack import edit_world_file, write_world_file, zones_dir

INVALID = tuple(f"pachimud.invalid_{k}" for k in ("entry", "choice", "range", "type", "unknown", "missing", "length"))
"""Codici 422 di una voce non valida (`pachimud.invalid_entry` o il caso comune localizzato)."""

ALFA = "ZonaAlfa"


async def test_describe_matches_emitted_extra() -> None:
    """Le chiavi di `extra` dichiarate coincidono con quelle emesse sul mondo di prova."""
    adapter = get_registry().get("pachimud")
    info = adapter.describe()
    assert_describe_matches(info, await emitted_extra_keys(adapter))
    enums = await adapter.enums()
    assert {"sectorType", "objectType", "zoneCommandType"} <= set(enums)
    assert len(enums["objectType"]) == 27  # i tipi LeU del gioco
    assert all(o.value != 6 or o.label for o in enums["zoneCommandType"]) and 6 not in {o.value for o in enums["zoneCommandType"]}
    caps = info.capabilities
    assert caps.supports_players and caps.supports_transfer and caps.supports_content_races and not caps.supports_instances


async def test_new_entities_go_to_area_files(client: httpx.AsyncClient) -> None:
    """`extra.area` sceglie il file `rooms_<area>.yaml` (creato se manca); cambiarla sposta la stanza."""
    zone = await by_vnum(client, "zones", 10)
    body = {"vnum": 1050, "zoneId": zone["id"], "name": "Nord", "description": "d", "extra": {"area": "nord"}}
    room = data(await client.post("/api/rooms", json=body), 201)
    assert room["extra"]["area"] == "nord"
    assert (zones_dir() / ALFA / "rooms_nord.yaml").is_file() and "vnum: 1050" in (zones_dir() / ALFA / "rooms_nord.yaml").read_text()
    assert "1050" not in (zones_dir() / ALFA / "rooms.yaml").read_text()
    moved = data(await client.put(f"/api/rooms/{room['id']}", json={"extra": {"area": ""}}))
    assert moved["extra"]["area"] == ""  # nessuna area = testo vuoto (cosi' il form non risulta modificato)
    assert "vnum: 1050" in (zones_dir() / ALFA / "rooms.yaml").read_text()
    # una nuova stanza senza area va nel file base
    plain = data(await client.post("/api/rooms", json={"vnum": 1051, "zoneId": zone["id"], "name": "Base"}), 201)
    assert plain["extra"] == {"enabled": True, "area": "", "climate": None}
    # clima della stanza: scelta valida, valore errato 422, vuoto = eredita dalla zona (la chiave sparisce dal file)
    assert data(await client.put(f"/api/rooms/{plain['id']}", json={"extra": {"climate": "desert"}}))["extra"]["climate"] == "desert"
    assert "climate: desert" in (zones_dir() / ALFA / "rooms.yaml").read_text()
    assert error_code(await client.put(f"/api/rooms/{plain['id']}", json={"extra": {"climate": "tropicale"}}), 422)
    assert data(await client.put(f"/api/rooms/{plain['id']}", json={"extra": {"climate": ""}}))["extra"]["climate"] is None
    assert "climate:" not in (zones_dir() / ALFA / "rooms.yaml").read_text()
    assert error_code(await client.put(f"/api/rooms/{plain['id']}", json={"extra": {"colore": "rosso"}}), 422) == "pachimud.extra_unknown"
    # il form svuota il campo: testo vuoto = nessuna area (non 422)
    assert data(await client.put(f"/api/rooms/{plain['id']}", json={"name": "Base 2", "extra": {"area": ""}}))["extra"]["area"] == ""
    bad = {"vnum": 1052, "zoneId": zone["id"], "name": "Fuori", "extra": {"area": "../../fuori"}}
    assert error_code(await client.post("/api/rooms", json=bad), 422) == "pachimud.invalid_area"


async def test_object_types_and_type_fields(client: httpx.AsyncClient) -> None:
    """Gli oggetti hanno solo i campi del loro tipo: `typeFields`, `value0..3` derivati, cambio di tipo, 422 sui campi estranei."""
    zone = await by_vnum(client, "zones", 10)
    base = {"vnum": 1600, "zoneId": zone["id"], "keywords": "spada", "shortDescription": "una spada", "objectType": 1}
    weapon = data(
        await client.post("/api/objects", json={**base, "extra": {"typeFields": {"dice_count": 3, "die_size": 8, "weapon_type": 11}}}), 201
    )
    assert weapon["extra"]["typeFields"] == {"dice_count": 3, "die_size": 8, "weapon_type": 11}
    assert (weapon["value1"], weapon["value2"], weapon["value3"], weapon["value0"]) == (3, 8, 11, None)
    text = (zones_dir() / ALFA / "objects.yaml").read_text()
    assert "object_type: WEAPON" in text and "dice_count: 3" in text
    # i value_N numerici sono scritti sui campi giusti
    armor = data(await client.post("/api/objects", json={**base, "vnum": 1601, "objectType": 2, "value0": 4}), 201)
    assert armor["extra"]["typeFields"] == {"armor_class": 4}
    # campo di un altro tipo: 422 e nulla scritto
    bad = await client.put(f"/api/objects/{armor['id']}", json={"extra": {"typeFields": {"dice_count": 1}}})
    assert error_code(bad, 422) in INVALID
    assert data(await client.get(f"/api/objects/{armor['id']}"))["extra"]["typeFields"] == {"armor_class": 4}
    # cambio di tipo: i campi del vecchio tipo spariscono dal file
    changed = data(await client.put(f"/api/objects/{weapon['id']}", json={"objectType": 8, "extra": {"typeFields": {"dice_count": 3}}}))
    assert changed["objectType"] == 8 and changed["extra"]["typeFields"] == {"key_type": 0}
    assert "dice_count: 3" not in (zones_dir() / ALFA / "objects.yaml").read_text()
    # un tipo che nell'enum del core si chiama LIQUID_CONTAINER e' DRINKCON nel file
    drink = data(
        await client.post("/api/objects", json={**base, "vnum": 1602, "objectType": 4, "extra": {"typeFields": {"liquid": "wine"}}}), 201
    )
    assert "object_type: DRINKCON" in (zones_dir() / ALFA / "objects.yaml").read_text() and drink["extra"]["typeFields"]["liquid"] == "wine"
    assert (
        error_code(await client.post("/api/objects", json={**base, "vnum": 1603, "extra": {"typeFields": {"liquid": "acido"}}}), 422)
        in INVALID
    )


async def test_mob_dice_and_stats(client: httpx.AsyncClient) -> None:
    """I dadi `XdY+Z` sono spezzati nel DTO e ricomposti (bonus negativo `+-N`); le statistiche stanno in `extra`."""
    zone = await by_vnum(client, "zones", 10)
    body = {
        "vnum": 1700,
        "zoneId": zone["id"],
        "keywords": "orco",
        "shortDescription": "un orco",
        "hpDiceCount": 3,
        "hpDieSize": 8,
        "hpBonus": -2,
    }
    mob = data(await client.post("/api/mobs", json={**body, "extra": {"strength": 17}}), 201)
    assert (mob["hpDiceCount"], mob["hpDieSize"], mob["hpBonus"], mob["extra"]["strength"]) == (3, 8, -2, 17)
    text = (zones_dir() / ALFA / "mobs.yaml").read_text()
    assert "hp_dice: 3d8+-2" in text and "strength: 17" in text
    patched = data(await client.put(f"/api/mobs/{mob['id']}", json={"hpBonus": 5}))
    assert (patched["hpDiceCount"], patched["hpBonus"]) == (3, 5)


async def test_new_zone_is_a_folder_and_delete_removes_it(client: httpx.AsyncClient) -> None:
    """Una zona nuova e' una cartella con `zone.yaml`; eliminarla toglie i suoi file e la cartella."""
    zone = data(await client.post("/api/zones", json={"vnum": 55, "name": "Foresta Nera", "bottomVnum": 5500, "topVnum": 5599}), 201)
    assert zone["id"] == 55 and zone["extra"]["folder"] == "ForestaNera"
    assert (zones_dir() / "ForestaNera" / "zone.yaml").is_file()
    assert (
        error_code(await client.post("/api/zones", json={"vnum": 56, "name": "X", "extra": {"folder": "ForestaNera"}}), 409)
        == "pachimud.folder_exists"
    )
    assert (
        error_code(await client.post("/api/zones", json={"vnum": 57, "name": "X", "extra": {"folder": "../fuori"}}), 422)
        == "pachimud.invalid_folder"
    )
    data(await client.post("/api/rooms", json={"vnum": 5500, "zoneId": 55, "name": "Radura"}), 201)
    assert (zones_dir() / "ForestaNera" / "rooms.yaml").is_file()
    assert error_code(await client.delete("/api/zones/55"), 409) == "zones.not_empty"
    assert (await client.delete("/api/rooms/5500")).status_code == 204
    assert (await client.delete("/api/zones/55")).status_code == 204
    assert not (zones_dir() / "ForestaNera").exists()


async def test_broken_files_do_not_stop_the_world(client: httpx.AsyncClient) -> None:
    """Un YAML rotto e una voce non valida sono segnalati con file e riga; il resto del mondo si legge."""
    write_world_file("ZonaRotta/zone.yaml", "zone_id: [non chiuso\nvnum: 77\n")
    edit_world_file(f"{ALFA}/mobs.yaml", "    thac0: 20\n", "    thac0: venti\n")  # il mob 1000 diventa non valido
    overview = data(await client.get("/api/world/overview"))
    problems = overview["fileProblems"]
    assert any(p["path"].endswith("ZonaRotta/zone.yaml") for p in problems)
    mob = next(p for p in problems if p["path"].endswith("mobs.yaml"))
    assert mob["line"] and "thac0" in mob["message"]
    assert overview["counts"]["zones"] == 2 and overview["counts"]["mobs"] == 1  # 1001 resta
    assert error_code(await client.get("/api/mobs/1000"), 404) == "mobs.not_found"
    # scrivere altrove funziona e non tocca il file rotto
    before = (zones_dir() / "ZonaRotta" / "zone.yaml").read_text()
    data(await client.put("/api/mobs/1001", json={"level": 4}))
    assert (zones_dir() / "ZonaRotta" / "zone.yaml").read_text() == before
    assert "thac0: venti" in (zones_dir() / ALFA / "mobs.yaml").read_text()  # la voce non valida non si perde


async def test_duplicate_vnums_and_integrity_warnings(client: httpx.AsyncClient) -> None:
    """Vnum duplicate, reset e chiavi inesistenti e uscite verso stanze mancanti sono segnalate."""
    write_world_file("ZonaDoppia/zone.yaml", "zone_id: d\nvnum: 30\nname: Doppia\nbuilder: t\nbottom_vnum: 3000\ntop_vnum: 3099\n")
    write_world_file(
        "ZonaDoppia/rooms.yaml",
        "rooms:\n  - vnum: 1000\n    name: Doppione\n    description: x\n  - vnum: 3000\n    name: Z\n    description: x\n"
        "    exits:\n      north:\n        target_vnum: 424242\n        door_flag: CLOSABLE\n        key_vnum: 999999\n",
    )
    write_world_file(
        "ZonaDoppia/resets.yaml",
        "resets:\n  mobs:\n    - mob_vnum: 888888\n      max_existing: 1\n      room_vnum: 3000\n      room_limit: 1\n",
    )
    overview = data(await client.get("/api/world/overview"))
    totals = overview["warningTotals"]
    for kind in ("duplicate_vnum", "exit_without_target", "exit_key_missing", "reset_unknown_mob"):
        assert totals.get(kind) == 1, (kind, totals)
    assert (await by_vnum(client, "rooms", 1000))["name"] == "Piazza"  # vince la prima voce
    dangling = data(await client.get("/api/rooms/3000"))["exits"][0]
    assert dangling["targetRoomId"] is None and dangling["targetRoomVnum"] == 424242
    assert (
        data(await client.put("/api/rooms/3000/exits/30000", json={"targetRoomId": None}))["targetRoomVnum"] == 424242
    )  # il vnum non si perde


async def test_external_edits_are_seen_immediately(client: httpx.AsyncClient) -> None:
    """Il gioco non scrive i file, ma l'utente si': una modifica a mano e' vista alla richiesta successiva."""
    assert data(await client.get("/api/rooms/1000"))["name"] == "Piazza"
    edit_world_file(f"{ALFA}/rooms.yaml", "    name: Piazza\n", "    name: Piazza Grande\n")
    assert data(await client.get("/api/rooms/1000"))["name"] == "Piazza Grande"


async def test_new_game_fields_round_trip(client: httpx.AsyncClient) -> None:
    """TRAP, `corpse`, descrizioni extra degli oggetti, `is_male` delle uscite, `climate`/`extends_zone` delle zone, `name`/`attacks`/`persona` dei mob."""
    zone = await by_vnum(client, "zones", 10)
    base = {"vnum": 1800, "zoneId": zone["id"], "keywords": "tagliola", "shortDescription": "una tagliola", "objectType": 19}
    trap = data(
        await client.post(
            "/api/objects",
            json={
                **base,
                "extra": {
                    "typeFields": {"triggers": ["MOVE", "NORTH"], "damage": "fire", "level": 3},
                    "extraDescriptions": [{"keywords": "denti", "text": "Aguzzi."}],
                },
            },
        ),
        201,
    )
    assert trap["extra"]["typeFields"] == {"triggers": ["MOVE", "NORTH"], "damage": "fire", "level": 3, "charges": 1}
    assert trap["value2"] == 3 and trap["extra"]["extraDescriptions"] == [{"keywords": "denti", "text": "Aguzzi."}]
    bag = data(
        await client.post(
            "/api/objects",
            json={**base, "vnum": 1801, "objectType": 3, "extra": {"typeFields": {"corpse": True, "container_flags": ["NO_WEIGHT"]}}},
        ),
        201,
    )
    assert bag["extra"]["typeFields"]["corpse"] is True and bag["value3"] == 1
    assert (
        error_code(await client.post("/api/objects", json={**base, "vnum": 1802, "extra": {"typeFields": {"triggers": ["SIDEWAYS"]}}}), 422)
        in INVALID
    )
    ex = data(await client.get("/api/rooms/1000"))["exits"][0]
    assert ex["extra"] == {"isMale": False, "openCmd": None, "climb": False}
    assert data(await client.put(f"/api/rooms/1000/exits/{ex['id']}", json={"extra": {"isMale": True}}))["extra"]["isMale"] is True
    assert "is_male: true" in (zones_dir() / ALFA / "rooms.yaml").read_text()
    z = data(await client.put(f"/api/zones/{zone['id']}", json={"extra": {"climate": "desert", "extendsZone": 99}}))
    assert z["extra"]["climate"] == "desert" and z["extra"]["extendsZone"] == 99
    mob = data(await client.put("/api/mobs/1001", json={"extra": {"name": "Ratto", "attacks": 2, "persona": "Squittisce."}}))
    assert (mob["extra"]["name"], mob["extra"]["attacks"], mob["extra"]["persona"]) == ("Ratto", 2, "Squittisce.")


async def test_new_game_fields_of_recent_game_versions(client: httpx.AsyncClient) -> None:
    """Uscite `openCmd`/`climb`, zona `prototypesOnly`, mob `shop`/`postmaster`/`receptionist`/`weaponImmunity`/`breath`, oggetti
    FIREWEAPON/MISSILE/BOARD: si leggono, si scrivono nel file e i valori non validi sono 422."""
    zone = await by_vnum(client, "zones", 10)
    ex = data(await client.get("/api/rooms/1000"))["exits"][0]
    out = data(await client.put(f"/api/rooms/1000/exits/{ex['id']}", json={"extra": {"openCmd": "pull", "climb": True}}))
    assert out["extra"]["openCmd"] == "pull" and out["extra"]["climb"] is True
    text = (zones_dir() / ALFA / "rooms.yaml").read_text()
    assert "open_cmd: pull" in text and "climb: true" in text
    assert error_code(await client.put(f"/api/rooms/1000/exits/{ex['id']}", json={"extra": {"openCmd": "kick"}}), 422) in INVALID
    out = data(await client.put(f"/api/rooms/1000/exits/{ex['id']}", json={"extra": {"openCmd": None, "climb": False}}))
    assert out["extra"]["openCmd"] is None and "open_cmd" not in (zones_dir() / ALFA / "rooms.yaml").read_text()
    z = data(await client.put(f"/api/zones/{zone['id']}", json={"extra": {"prototypesOnly": True}}))
    assert z["extra"]["prototypesOnly"] is True and "prototypes_only: true" in (zones_dir() / ALFA / "zone.yaml").read_text()
    shop = {
        "produces": [1800],
        "trades": ["weapon"],
        "profit_buy": 1.2,
        "open1": 6,
        "close1": 20,
        "messages": {"message_buy": {"it": "Grazie {player}."}},
    }
    mob = data(
        await client.put(
            "/api/mobs/1001",
            json={
                "extra": {"shop": shop, "postmaster": True, "receptionist": True, "weaponImmunity": 2, "breath": ["fire"], "breathCost": 40}
            },
        )
    )
    assert (
        mob["extra"]["shop"]["trades"] == ["WEAPON"] and mob["extra"]["shop"]["profit_buy"] == 1.2 and mob["extra"]["shop"]["room"] is None
    )
    assert (mob["extra"]["postmaster"], mob["extra"]["receptionist"], mob["extra"]["weaponImmunity"]) == (True, True, 2)
    assert (mob["extra"]["breath"], mob["extra"]["breathCost"]) == (["fire"], 40)
    text = (zones_dir() / ALFA / "mobs.yaml").read_text()
    assert "shop:" in text and "postmaster: true" in text and "weapon_immunity: 2" in text
    for bad in ({"shop": {"trades": ["NOPE"]}}, {"shop": {"messages": {"x": {}}}}, {"weaponImmunity": 9}):
        assert error_code(await client.put("/api/mobs/1001", json={"extra": bad}), 422) in (*INVALID, "validation_error")
    cleared = data(await client.put("/api/mobs/1001", json={"extra": {"shop": None, "weaponImmunity": None, "postmaster": False}}))
    assert (
        cleared["extra"]["shop"] is None
        and cleared["extra"]["weaponImmunity"] is None
        and "shop:" not in (zones_dir() / ALFA / "mobs.yaml").read_text()
    )
    base = {"zoneId": zone["id"], "shortDescription": "x"}
    bow = data(
        await client.post(
            "/api/objects",
            json={**base, "vnum": 1810, "keywords": "arco", "objectType": 16, "extra": {"typeFields": {"strength": 12, "ammo_type": 1}}},
        ),
        201,
    )
    assert bow["extra"]["typeFields"] == {"strength": 12, "range_bonus": 0, "ammo_type": 1} and bow["value0"] == 12 and bow["value3"] == 1
    arrow = data(
        await client.post(
            "/api/objects",
            json={**base, "vnum": 1811, "keywords": "freccia", "objectType": 17, "extra": {"typeFields": {"break_chance": 20}}},
        ),
        201,
    )
    assert arrow["extra"]["typeFields"]["break_chance"] == 20 and arrow["extra"]["typeFields"]["die_size"] == 4
    board = data(
        await client.post(
            "/api/objects",
            json={
                **base,
                "vnum": 1812,
                "keywords": "bacheca",
                "objectType": 24,
                "extra": {"typeFields": {"board_id": "citta", "min_write_level": 5}},
            },
        ),
        201,
    )
    assert board["extra"]["typeFields"]["board_id"] == "citta" and board["extra"]["typeFields"]["max_messages"] == 99


def test_database_url_env_expansion(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """`${VARIABILE}` si espande come nel gioco; una variabile mancante e' un errore chiaro; `sslmode=` diventa `ssl=` per asyncpg."""
    import pytest

    from pachimudeditor_adapter_pachimud.params import PachimudConfigError, expand_env

    monkeypatch.setenv("PG_PASSWORD", "segreta")
    assert expand_env("postgresql+asyncpg://u:${PG_PASSWORD}@h/db?sslmode=require") == "postgresql+asyncpg://u:segreta@h/db?ssl=require"
    monkeypatch.delenv("PG_PASSWORD")
    with pytest.raises(PachimudConfigError):
        expand_env("postgresql+asyncpg://u:${PG_PASSWORD}@h/db")


def test_invalid_errors_are_localized_codes() -> None:
    """I casi comuni di pydantic hanno un codice con messaggio it/en (`field`, `limit`), non il testo inglese del modello."""
    from pydantic import ValidationError

    from pachimudeditor_adapter_pachimud.loaders import LoaderShop
    from pachimudeditor_adapter_pachimud.mapping import invalid

    def code_of(raw: dict) -> tuple[str, dict]:
        with pytest.raises(ValidationError) as caught:
            LoaderShop.model_validate(raw)
        detail = invalid(caught.value).detail[0]
        return detail["code"], detail["params"]

    assert code_of({"profit_buy": "x"}) == ("pachimud.invalid_type", {"field": "profit_buy"})
    assert code_of({"trades": ["NOPE"]})[0] in INVALID
    assert "Value error" not in code_of({"trades": ["NOPE"]})[1]["detail"]


async def test_extra_definition_paths_are_reported_not_read(tmp_path: Path) -> None:
    """Le cartelle `extra_definition_paths` del gioco non sono lette dall'editor: `worlds check` lo dice con un avviso."""
    from pachimudeditor.common.adapters.registry import WorldConfig
    from pachimudeditor_adapter_pachimud.adapter import PachimudAdapter

    game = tmp_path / "pachimud.yaml"
    game.write_text(f"definition_path: {zones_dir().parent}\nextra_definition_paths: [/srv/extra]\n")
    adapter = PachimudAdapter(WorldConfig(id="p", kind="pachimud", name="p", params={"config_path": str(game)}))
    report = adapter.schema_report()
    assert report is not None and "extra_definition_paths_ignored" in [i.code for i in report.problems]
