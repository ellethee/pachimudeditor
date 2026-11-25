"""Trigger dei mob pachimud: il campo `triggers:` (`extra.triggers`), validazione e scrittura selettiva."""

import re

import httpx

from tests.helpers import by_vnum, data, error_code
from tests.support.stack import zones_dir

TRIGGER = {"type": "speech", "argument": "aiuto", "chance": 50, "actions": ["say Ciao $n", "emote sorride a $n"]}


def _text() -> str:
    """Il testo dei file `mobs*.yaml` della zona di prova."""
    return "".join(p.read_text() for p in (zones_dir() / "ZonaAlfa").glob("mobs*.yaml"))


async def test_triggers_roundtrip_and_untouched(client: httpx.AsyncClient) -> None:
    """Si scrivono e si rileggono; un PUT che non li tocca o li ripete uguali non cambia il file; `[]` li toglie."""
    mob = await by_vnum(client, "mobs", 1000)
    assert mob["extra"]["triggers"] == []
    out = data(
        await client.put(f"/api/mobs/{mob['id']}", json={"extra": {"triggers": [TRIGGER, {"type": "death", "actions": ["say Ahi"]}]}})
    )
    assert out["extra"]["triggers"][0] == TRIGGER and out["extra"]["triggers"][1]["chance"] == 100
    written = _text()
    assert "triggers:" in written and "chance: 100" not in written
    # invariato: stesso file
    data(await client.put(f"/api/mobs/{mob['id']}", json={"extra": {"triggers": out["extra"]["triggers"]}}))
    data(await client.put(f"/api/mobs/{mob['id']}", json={"level": mob["level"]}))
    assert _text() == written
    cleared = data(await client.put(f"/api/mobs/{mob['id']}", json={"extra": {"triggers": []}}))
    assert cleared["extra"]["triggers"] == []
    assert "triggers:" not in _text()


async def test_triggers_invalid(client: httpx.AsyncClient) -> None:
    """Tipo, probabilita' e azioni non valide sono 422 con code stabile."""
    mob = await by_vnum(client, "mobs", 1000)
    url = f"/api/mobs/{mob['id']}"
    bad_type = {**TRIGGER, "type": "nope"}
    assert error_code(await client.put(url, json={"extra": {"triggers": [bad_type]}}), 422) == "pachimud.invalid_choice"
    assert error_code(await client.put(url, json={"extra": {"triggers": [{**TRIGGER, "chance": 101}]}}), 422) == "pachimud.invalid_range"
    assert error_code(await client.put(url, json={"extra": {"triggers": [{**TRIGGER, "chance": 0}]}}), 422) == "pachimud.invalid_range"
    assert error_code(await client.put(url, json={"extra": {"triggers": [{**TRIGGER, "actions": []}]}}), 422) == "pachimud.invalid_length"


async def test_triggers_blank_action_and_readable_messages(client: httpx.AsyncClient) -> None:
    """Un'azione di soli spazi e' 422 `invalid_length`; il messaggio mostra `triggers[0].chance` e il limite `≤ 100`, la scelta senza apici ne' «or»."""
    mob = await by_vnum(client, "mobs", 1000)
    url = f"/api/mobs/{mob['id']}"
    blank = await client.put(url, json={"extra": {"triggers": [{**TRIGGER, "actions": ["  "]}]}})
    assert error_code(blank, 422) == "pachimud.invalid_length"
    over = await client.put(url, json={"extra": {"triggers": [{**TRIGGER, "chance": 101}]}}, headers={"Accept-Language": "it"})
    assert "triggers[0].chance" in over.text and "≤ 100" in over.text and "ge " not in over.text and "le 100" not in over.text
    wrong = await client.put(url, json={"extra": {"triggers": [{**TRIGGER, "type": "nope"}]}}, headers={"Accept-Language": "it"})
    assert "speech, greet, give, random, death, fight" in wrong.text and "'" not in wrong.text.split("ammette solo")[-1].split('"')[0]


BLOCK = {
    "type": "fight",
    "chance": 30,
    "actions": [
        "say Basta!",
        {
            "if": {"level": ">= 10", "class": "mago", "who": "i"},
            "then": ["say Collega!", {"if": {"chance": 50, "is_player": True}, "then": ["emote ride"], "else": ["emote tace"]}],
            "else": ["say Benvenuto."],
        },
    ],
}


def _text_of(pattern: str) -> str:
    """Il testo dei file `<pattern>*.yaml` della zona di prova."""
    return "".join(p.read_text() for p in (zones_dir() / "ZonaAlfa").glob(f"{pattern}*.yaml"))


async def test_new_mob_types_and_nested_if(client: httpx.AsyncClient) -> None:
    """Nuovi tipi (fight, hitprcnt, act, tell, bribe) e blocchi if/else annidati: round trip, nessun diff se invariati, `else` vuoto assente."""
    mob = await by_vnum(client, "mobs", 1000)
    url = f"/api/mobs/{mob['id']}"
    extra = [
        BLOCK,
        {"type": "hitprcnt", "argument": "30", "actions": ["flee"]},
        {"type": "bribe", "argument": "100", "actions": ["say Grazie"]},
    ]
    out = data(await client.put(url, json={"extra": {"triggers": extra}}))["extra"]["triggers"]
    assert out[0]["actions"][1]["if"] == {"level": ">= 10", "class": "mago", "who": "i"}  # alias `class`, `if`/`then`/`else` come nel file
    assert out[0]["actions"][1]["then"][1]["else"] == ["emote tace"]
    written = _text_of("mobs")
    assert "if:" in written and "else:" in written and "class: mago" in written and "who: n" not in written
    data(await client.put(url, json={"extra": {"triggers": out}}))
    assert _text_of("mobs") == written
    data(await client.put(url, json={"extra": {"triggers": []}}))
    assert "triggers:" not in _text_of("mobs")


async def test_if_blocks_keep_comments(client: httpx.AsyncClient) -> None:
    """Un trigger invariato tra altri modificati conserva il suo commento nel file."""
    mob = await by_vnum(client, "mobs", 1000)
    url = f"/api/mobs/{mob['id']}"
    data(await client.put(url, json={"extra": {"triggers": [TRIGGER, BLOCK]}}))
    path = next(p for p in (zones_dir() / "ZonaAlfa").glob("mobs*.yaml"))
    path.write_text(re.sub(r"^( *)- type: speech", r"\1# saluto\n\1- type: speech", path.read_text(), count=1, flags=re.M))
    current = data(await client.get(url))["extra"]["triggers"]
    data(await client.put(url, json={"extra": {"triggers": [current[0], {**current[1], "chance": 40}]}}))
    assert "# saluto" in path.read_text() and "chance: 40" in path.read_text()
    data(await client.put(url, json={"extra": {"triggers": []}}))


async def test_trigger_validation_new(client: httpx.AsyncClient) -> None:
    """Tipo non ammesso al proprietario, argomento di hitprcnt/bribe, troppi if annidati, condizione non valida: 422 leggibili."""
    mob = await by_vnum(client, "mobs", 1000)
    url = f"/api/mobs/{mob['id']}"
    put = lambda trigger: client.put(url, json={"extra": {"triggers": [trigger]}}, headers={"Accept-Language": "it"})  # noqa: E731
    wrong = await put({"type": "enter", "actions": ["say x"]})
    assert error_code(wrong, 422) == "pachimud.invalid_choice" and "triggers[0].type" in wrong.text
    assert error_code(await put({"type": "bribe", "actions": ["say x"]}), 422) == "pachimud.invalid_entry"
    assert error_code(await put({"type": "hitprcnt", "argument": "101", "actions": ["flee"]}), 422) == "pachimud.invalid_entry"
    deep: dict = {"if": {"chance": 5}, "then": ["say x"]}
    for _ in range(3):
        deep = {"if": {"chance": 5}, "then": [deep]}
    assert error_code(await put({"type": "fight", "actions": [deep]}), 422) == "pachimud.invalid_entry"
    bad = await put({"type": "fight", "actions": [{"if": {"chance": 500}, "then": ["say x"]}]})
    assert error_code(bad, 422) == "pachimud.invalid_range" and "triggers[0].actions[0].if.chance" in bad.text
    assert error_code(await put({"type": "fight", "actions": [{"if": {"sex": "x"}, "then": ["say x"]}]}), 422) == "pachimud.invalid_choice"
    assert error_code(await put({"type": "fight", "actions": [{"if": {}, "then": []}]}), 422) == "pachimud.invalid_length"


async def test_object_scripts(client: httpx.AsyncClient) -> None:
    """`extra.scripts` degli oggetti (get/drop/wear/give): round trip, `triggers:` delle trappole intatto, tipi dei mob rifiutati."""
    obj = await by_vnum(client, "objects", 1000)
    assert obj["extra"]["scripts"] == []
    url = f"/api/objects/{obj['id']}"
    script = {"type": "get", "actions": ["mpechoat $n Senti un brivido.", {"if": {"level": "< 5"}, "then": ["mpecho Un lampo!"]}]}
    out = data(await client.put(url, json={"extra": {"scripts": [script]}}))["extra"]["scripts"]
    assert out[0]["type"] == "get" and "scripts:" in _text_of("objects")
    written = _text_of("objects")
    data(await client.put(url, json={"extra": {"scripts": out}}))
    data(await client.put(url, json={"weight": 1}))
    assert _text_of("objects") == written
    assert (
        error_code(await client.put(url, json={"extra": {"scripts": [{"type": "death", "actions": ["mpecho x"]}]}}), 422)
        == "pachimud.invalid_choice"
    )
    assert (
        error_code(await client.put(url, json={"extra": {"scripts": [{"type": "get", "actions": []}]}}), 422) == "pachimud.invalid_length"
    )
    data(await client.put(url, json={"extra": {"scripts": []}}))
    assert "scripts:" not in _text_of("objects")


async def test_room_triggers(client: httpx.AsyncClient) -> None:
    """`extra.triggers` delle stanze (enter/exit/speech): round trip, nessun diff se invariati, svuotando la chiave sparisce."""
    room = await by_vnum(client, "rooms", 1002)
    assert room["extra"]["triggers"] == []
    url = f"/api/rooms/{room['id']}"
    trig = [
        {"type": "enter", "chance": 60, "actions": ["mpecho Un soffio gelido."]},
        {"type": "speech", "argument": "p apriti sesamo", "actions": ["mpecho Nulla."]},
    ]
    out = data(await client.put(url, json={"extra": {"triggers": trig}}))["extra"]["triggers"]
    assert [t["type"] for t in out] == ["enter", "speech"]
    written = _text_of("rooms")
    data(await client.put(url, json={"extra": {"triggers": out}}))
    data(await client.put(url, json={"name": room["name"]}))
    assert _text_of("rooms") == written
    assert (
        error_code(await client.put(url, json={"extra": {"triggers": [{"type": "get", "actions": ["mpecho x"]}]}}), 422)
        == "pachimud.invalid_choice"
    )
    data(await client.put(url, json={"extra": {"triggers": []}}))
    assert "triggers:" not in _text_of("rooms")


async def test_trigger_phase3(client: httpx.AsyncClient) -> None:
    """Fase 3: `random` per oggetti e stanze, nuove condizioni (round trip e 422), comandi MP solo per i mob."""
    cond = {"time": ">= 20", "is_night": True, "is_fighting": False, "has_effect": "sanctuary", "vnum": 1000}
    mob = await by_vnum(client, "mobs", 1000)
    murl = f"/api/mobs/{mob['id']}"
    mp = {"type": "random", "chance": 10, "actions": [{"if": cond, "then": ["mpload obj 1000 inv", "mpat 1002 mpecho Ciao"]}]}
    out = data(await client.put(murl, json={"extra": {"triggers": [mp]}}))["extra"]["triggers"]
    assert out[0]["actions"][0]["if"] == {**cond, "who": "n"}
    put = lambda trigger: client.put(murl, json={"extra": {"triggers": [trigger]}}, headers={"Accept-Language": "it"})  # noqa: E731
    for bad in ({"time": 24}, {"time": "tardi"}, {"vnum": "x"}):
        res = await put({"type": "fight", "actions": [{"if": bad, "then": ["say x"]}]})
        assert error_code(res, 422) == "pachimud.invalid_entry" and ("time" in res.text or "vnum" in res.text)
    data(await client.put(murl, json={"extra": {"triggers": []}}))

    obj = await by_vnum(client, "objects", 1000)
    ourl = f"/api/objects/{obj['id']}"
    data(await client.put(ourl, json={"extra": {"scripts": [{"type": "random", "chance": 5, "actions": ["mpecho Brilla."]}]}}))
    res = await client.put(ourl, json={"extra": {"scripts": [{"type": "get", "actions": ["mpkill $n"]}]}})
    assert error_code(res, 422) == "pachimud.invalid_entry" and "mpkill" in res.text
    data(await client.put(ourl, json={"extra": {"scripts": []}}))

    room = await by_vnum(client, "rooms", 1002)
    rurl = f"/api/rooms/{room['id']}"
    data(await client.put(rurl, json={"extra": {"triggers": [{"type": "random", "actions": ["mpecho Un fruscio."]}]}}))
    nested = {"if": {"chance": 5}, "then": ["mpgoto 1000"]}
    res = await client.put(rurl, json={"extra": {"triggers": [{"type": "enter", "actions": [nested]}]}})
    assert error_code(res, 422) == "pachimud.invalid_entry" and "mpgoto" in res.text
    data(await client.put(rurl, json={"extra": {"triggers": []}}))


async def test_f9_events_block_var_and_verbs(client: httpx.AsyncClient) -> None:
    """Gioco F9: eventi `all_greet`/`entry`/`command` (solo mob; `command` vuole l'argomento), `block`, condizione `var`, verbi `mpset`/`mpunset`/`mpadd`; oggetti e stanze usano `mptransfer`/`mpload`/`mpset` ma non `mppurge self`."""
    mob = await by_vnum(client, "mobs", 1000)
    murl = f"/api/mobs/{mob['id']}"
    cond = {"var": {"visite": ">= 3", "stato": "attivo"}}
    command = {
        "type": "command",
        "argument": "pull",
        "block": True,
        "actions": [{"if": cond, "then": ["mpadd visite 1"], "else": ["mpset stato attivo"]}],
    }
    out = data(
        await client.put(
            murl,
            json={
                "extra": {
                    "triggers": [
                        command,
                        {"type": "all_greet", "actions": ["say ${stato}"]},
                        {"type": "entry", "actions": ["mpunset stato"]},
                    ]
                }
            },
        )
    )
    triggers = out["extra"]["triggers"]
    assert triggers[0]["block"] is True and triggers[0]["actions"][0]["if"]["var"] == cond["var"]
    assert "block: true" in _text() and "var:" in _text()
    res = await client.put(murl, json={"extra": {"triggers": [{"type": "command", "actions": ["say x"]}]}})
    assert error_code(res, 422) == "pachimud.invalid_entry" and "command" in res.text
    data(await client.put(murl, json={"extra": {"triggers": []}}))

    obj = await by_vnum(client, "objects", 1000)
    ourl = f"/api/objects/{obj['id']}"
    ok = {"type": "get", "actions": ["mptransfer $n 1002", "mpload mob 1000", "mpset visto si", "mppurge"]}
    data(await client.put(ourl, json={"extra": {"scripts": [ok]}}))
    res = await client.put(ourl, json={"extra": {"scripts": [{"type": "get", "actions": ["mppurge self"]}]}})
    assert error_code(res, 422) == "pachimud.invalid_entry" and "mppurge" in res.text
    res = await client.put(ourl, json={"extra": {"scripts": [{"type": "entry", "actions": ["mpecho x"]}]}})
    assert error_code(res, 422) == "pachimud.invalid_choice"
    data(await client.put(ourl, json={"extra": {"scripts": []}}))
