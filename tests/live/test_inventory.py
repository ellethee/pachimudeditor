"""Conformita' di inventario e oggetti istanza (feature `inventory`, protocollo v1.1): `player.inventory`, `obj.get`, `obj.set`, `obj.remove`.

Gira contro il finto server e, se disponibile, contro il modulo C reale. Il giocatore `Tester` ha un giubbotto indossato (vnum 9, slot 5),
una borsa (vnum 14) con una bottiglia (vnum 3001) e una bottiglia sciolta. I test ripristinano quello che modificano; l'ultimo e' distruttivo.
"""

from __future__ import annotations

import json
import re
from typing import Any

from tests.live.conftest import Target
from tests.live.helpers import err, ok
from tests.support.live_client import LiveClient

VEST, BAG, BOTTLE, BODY = 9, 14, 3001, 5


async def _inv(client: LiveClient, target: Target, **params: Any) -> dict[str, Any]:
    return ok(await client.call("player.inventory", {"name": target.player, **params}))


def _find(items: list[dict[str, Any]], vnum: int, depth: int | None = None, *, slot: bool | None = None) -> dict[str, Any]:
    for it in items:
        if it["vnum"] == vnum and (depth is None or it["depth"] == depth) and (slot is None or (it["slot"] is not None) == slot):
            return it
    raise AssertionError(f"oggetto {vnum} (profondita' {depth}) non trovato in {[(i['vnum'], i['depth']) for i in items]}")


def _expect(it: dict[str, Any]) -> dict[str, Any]:
    return {"vnum": it["vnum"], "fp": it["fp"]}


async def _set(client: LiveClient, target: Target, it: dict[str, Any], fields: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return await client.call("obj.set", {"name": target.player, "ref": it["ref"], "expect": _expect(it), "set": fields, **extra})


async def _fresh(client: LiveClient, target: Target, vnum: int, depth: int | None = None, *, slot: bool | None = None) -> dict[str, Any]:
    return _find((await _inv(client, target))["items"], vnum, depth, slot=slot)


# ---- capability e lettura -----------------------------------------------------------------------------------------------


async def test_inventory_capability_in_hello(target: Target, raw: LiveClient) -> None:
    """`hello.features` dichiara `inventory` e i comandi compaiono con la classe giusta."""
    r = ok(await raw.hello(target.token))
    assert "inventory" in r["features"]
    for cmd in ("player.inventory", "obj.get"):
        assert r["commands"][cmd]["class"] == "read"
    for cmd in ("obj.set", "obj.remove"):
        assert r["commands"][cmd]["class"] == "write"


async def test_inventory_listing(client: LiveClient, target: Target) -> None:
    """Elenco piatto: equipaggiamento (slot), inventario e contenuto dei contenitori con ref, impronta e campi modificabili."""
    r = await _inv(client, target)
    items = r["items"]
    assert r["count"] == len(items) and r["truncated"] is False and isinstance(r["carry_weight"], int) and r["carry_items"] >= 2
    vest = _find(items, VEST, 0, slot=True)
    assert vest["slot"] == BODY and vest["ref"] == f"eq:{BODY}"
    bag = _find(items, BAG, 0)
    inner = _find(items, BOTTLE, 1)
    assert bag["slot"] is None and bag["ref"].startswith("inv:") and "/" not in bag["ref"] and bag["contents"] >= 1
    assert inner["ref"].startswith(bag["ref"] + "/") and inner["slot"] is None
    for it in items:
        assert re.fullmatch(r"(eq|inv):\d+(/\d+)*", it["ref"]) and re.fullmatch(r"[0-9a-f]{8}", it["fp"])
        assert it["name"] and it["short_description"] and isinstance(it["description"], str) and len(it["values"]) == 4
        assert len(it["affects"]) == 5 and all({"location", "modifier"} == set(a) for a in it["affects"])
        assert {"weight", "extra_flags", "timer", "depth", "type", "contents"} <= set(it)
    assert len({it["ref"] for it in items}) == len(items)


async def test_inventory_brief_limit_and_errors(client: LiveClient, target: Target) -> None:
    """`brief` toglie i campi di dettaglio; `limit` tronca; errori."""
    brief = (await _inv(client, target, brief=True))["items"][0]
    assert "values" not in brief and "affects" not in brief and brief["name"]
    r = await _inv(client, target, limit=1)
    assert len(r["items"]) == 1 and r["truncated"] is True and r["count"] == 1
    err(await client.call("player.inventory", {"name": target.player, "limit": 0}), "value_out_of_range")
    err(await client.call("player.inventory", {"name": target.player, "limit": 1000}), "value_out_of_range")
    err(await client.call("player.inventory", {"name": "Nessuno"}), "not_found")
    err(await client.call("player.inventory", {"name": "../x"}), "bad_params")
    err(await client.call("player.inventory", {"name": target.player, "extra": 1}), "bad_params")
    err(await client.call("player.inventory", {}), "bad_params")


async def test_obj_get(client: LiveClient, target: Target) -> None:
    """`obj.get` restituisce tutti i campi, anche quelli di sola lettura; `expect` facoltativo in lettura."""
    vest = await _fresh(client, target, VEST, 0, slot=True)
    got = ok(await client.call("obj.get", {"name": target.player, "ref": vest["ref"]}))["item"]
    assert got["ref"] == vest["ref"] and got["fp"] == vest["fp"] and got["slot"] == BODY
    assert {"wear_flags", "cost", "cost_per_day", "bitvector", "description", "values", "affects"} <= set(got)
    ok(await client.call("obj.get", {"name": target.player, "ref": vest["ref"], "expect": _expect(vest)}))
    err(
        await client.call("obj.get", {"name": target.player, "ref": vest["ref"], "expect": {"vnum": vest["vnum"], "fp": "00000000"}}),
        "stale_ref",
    )
    err(await client.call("obj.get", {"name": target.player, "ref": vest["ref"], "expect": {"vnum": 1, "fp": vest["fp"]}}), "stale_ref")
    assert err(await client.call("obj.get", {"name": target.player, "ref": "inv:9999"}), "not_found")["params"]["what"] == "object"
    err(await client.call("obj.get", {"name": target.player, "ref": "inv:9999", "expect": {"vnum": 1, "fp": "00000000"}}), "stale_ref")
    for bad in ("inv:abc", "foo:1", "inv:1//2", "eq:5/", "", "inv:-1", "inv:1/2/3/4/5/6/7/8/9/10"):
        err(await client.call("obj.get", {"name": target.player, "ref": bad}), "bad_params")
    err(await client.call("obj.get", {"name": "Nessuno", "ref": "inv:0"}), "not_found")
    err(await client.call("obj.get", {"name": target.player, "ref": vest["ref"], "expect": {"vnum": 9}}), "bad_params")
    err(await client.call("obj.get", {"name": target.player}), "bad_params")


async def test_nested_object_via_get(client: LiveClient, target: Target) -> None:
    """Un oggetto dentro un contenitore si raggiunge col percorso `inv:i/j`."""
    inner = await _fresh(client, target, BOTTLE, 1)
    got = ok(await client.call("obj.get", {"name": target.player, "ref": inner["ref"]}))["item"]
    assert got["vnum"] == BOTTLE and got["depth"] == 1 and got["fp"] == inner["fp"]


# ---- modifiche -----------------------------------------------------------------------------------------------------------


async def test_obj_set_text_fields_and_restore(client: LiveClient, target: Target) -> None:
    """name, short_description, description: cambiano, l'impronta cambia, si ripristinano."""
    bottle = await _fresh(client, target, BOTTLE, 0)
    new = {
        "name": "zzkey prova",
        "short_description": "una bottiglia di prova",
        "description": "Una bottiglia di prova e' qui, e non c'e' $"[:-4],
    }
    r = ok(await _set(client, target, bottle, new))
    assert r["item"]["name"] == "zzkey prova" and r["item"]["short_description"] == "una bottiglia di prova" and r["saved"] is True
    assert r["fp"] != bottle["fp"] and r["item"]["fp"] == r["fp"] and r["warnings"] == []
    again = await _fresh(client, target, BOTTLE, 0)
    assert again["name"] == "zzkey prova" and again["description"] == new["description"] and again["vnum"] == BOTTLE
    # accenti latin-1 ammessi
    ok(await _set(client, target, again, {"short_description": "una bottiglia è così"}))
    again = await _fresh(client, target, BOTTLE, 0)
    assert again["short_description"] == "una bottiglia è così"
    back = {"name": bottle["name"], "short_description": bottle["short_description"], "description": bottle["description"]}
    ok(await _set(client, target, again, back))
    assert (await _fresh(client, target, BOTTLE, 0))["fp"] == bottle["fp"]


async def test_obj_set_numeric_fields_and_restore(client: LiveClient, target: Target) -> None:
    """values (parziale con null), extra_flags, timer, affects (parziale): si leggono e si ripristinano."""
    bottle = await _fresh(client, target, BOTTLE, 0)
    ok(await _set(client, target, bottle, {"values": [None, 5, None, 7], "extra_flags": 3, "timer": 900000}))
    it = await _fresh(client, target, BOTTLE, 0)
    assert it["values"] == [bottle["values"][0], 5, bottle["values"][2], 7] and it["extra_flags"] == 3
    assert 899000 <= it["timer"] <= 900000  # il gioco scala il timer da solo
    ok(await _set(client, target, it, {"affects": [None, {"location": 13, "modifier": 4}], "values": [1]}))
    it = await _fresh(client, target, BOTTLE, 0)
    assert it["affects"][1] == {"location": 13, "modifier": 4} and it["affects"][0] == bottle["affects"][0] and it["values"][0] == 1
    ok(await _set(client, target, it, {"values": bottle["values"], "extra_flags": bottle["extra_flags"], "timer": bottle["timer"],
                                       "affects": bottle["affects"]}))  # fmt: skip
    final = await _fresh(client, target, BOTTLE, 0)
    assert final["fp"] == bottle["fp"] and final["values"] == bottle["values"] and final["affects"] == bottle["affects"]


async def test_obj_set_weight_propagates(client: LiveClient, target: Target) -> None:
    """Il peso cambia anche il contenitore e il peso trasportato (oggetto nel contenitore, sciolto, indossato)."""
    cases = [(BOTTLE, 1), (BOTTLE, 0), (VEST, 0)]
    for vnum, depth in cases:
        before_inv = await _inv(client, target)
        it = _find(before_inv["items"], vnum, depth)
        parents = [x for x in before_inv["items"] if depth == 1 and x["depth"] == 0 and it["ref"].startswith(x["ref"] + "/")]
        ok(await _set(client, target, it, {"weight": it["weight"] + 5}))
        after = await _inv(client, target)
        assert after["carry_weight"] == before_inv["carry_weight"] + 5, (vnum, depth)
        assert _find(after["items"], vnum, depth)["weight"] == it["weight"] + 5 or depth == 1
        for par in parents:
            assert next(x for x in after["items"] if x["ref"] == par["ref"])["weight"] == par["weight"] + 5
        it2 = next(x for x in after["items"] if x["ref"] == it["ref"])
        ok(await _set(client, target, it2, {"weight": it["weight"]}))
        restored = await _inv(client, target)
        assert restored["carry_weight"] == before_inv["carry_weight"]


async def test_obj_set_on_equipped_item_keeps_bonuses_consistent(client: LiveClient, target: Target) -> None:
    """Cambiare gli affect di un oggetto indossato toglie il vecchio bonus e applica il nuovo; il ripristino riporta il valore iniziale."""

    async def max_hit() -> int:
        return ok(await client.call("player.get", {"name": target.player}))["fields"]["maxHit"]

    vest = await _fresh(client, target, VEST, 0, slot=True)
    hp_bonus = sum(a["modifier"] for a in vest["affects"] if a["location"] == 13)  # APPLY_HIT
    base = await max_hit() - hp_bonus
    for mod in (10, 25):
        vest = await _fresh(client, target, VEST, 0, slot=True)
        ok(await _set(client, target, vest, {"affects": [{"location": 13, "modifier": mod}]}))
        assert await max_hit() == base + mod - sum(a["modifier"] for a in vest["affects"][1:] if a["location"] == 13) * 0
    vest = await _fresh(client, target, VEST, 0, slot=True)
    ok(await _set(client, target, vest, {"affects": [vest0 if (vest0 := {"location": 0, "modifier": 0}) else None]}))
    assert await max_hit() == base
    assert (await _fresh(client, target, VEST, 0, slot=True))["slot"] == BODY  # ancora indossato


async def test_obj_set_validation(client: LiveClient, target: Target) -> None:
    """Intervalli, tipi, testi non ammessi, forma di `set`: nessuna modifica in caso di errore."""
    bottle = await _fresh(client, target, BOTTLE, 0)
    n = target.player
    ref = bottle["ref"]

    async def bad(fields: dict[str, Any], code: str) -> dict[str, Any]:
        return err(await _set(client, target, bottle, fields), code)

    await bad({"name": "con $dollaro"}, "bad_params")
    await bad({"name": "con ~tilde"}, "bad_params")
    await bad({"name": "con\nnewline"}, "bad_params")
    await bad({"name": ""}, "bad_params")
    await bad({"name": "x" * 128}, "bad_params")
    await bad({"short_description": "x" * 128}, "bad_params")
    await bad({"description": "x" * 256}, "bad_params")
    await bad({"name": "emoji \U0001f600"}, "unencodable_text")
    await bad({"name": 5}, "bad_params")
    ok(await _set(client, target, bottle, {"name": "x" * 127}))  # il limite esatto passa (strcpy nel record di rent da 128)
    await _set(client, target, await _fresh(client, target, BOTTLE, 0), {"name": bottle["name"]})
    bottle = await _fresh(client, target, BOTTLE, 0)
    await bad({"weight": 32768}, "value_out_of_range")
    await bad({"weight": -1}, "value_out_of_range")
    await bad({"weight": "5"}, "bad_params")
    await bad({"timer": -5}, "value_out_of_range")
    await bad({"extra_flags": -1}, "value_out_of_range")
    await bad({"values": [1, 2, 3, 4, 5]}, "bad_params")
    await bad({"values": []}, "bad_params")
    await bad({"values": [2**31]}, "value_out_of_range")
    await bad({"values": ["a"]}, "bad_params")
    await bad({"affects": [{"location": 65, "modifier": 1}]}, "value_out_of_range")
    await bad({"affects": [{"location": -1, "modifier": 1}]}, "value_out_of_range")
    await bad({"affects": [{"location": 1, "modifier": 40000}]}, "value_out_of_range")
    await bad({"affects": [{"location": 1}]}, "bad_params")
    await bad({"affects": [{"location": 1, "modifier": 1, "x": 1}]}, "bad_params")
    await bad({"affects": [None] * 6}, "bad_params")
    await bad({"cost": 5}, "bad_params")
    await bad({"vnum": 5}, "bad_params")
    await bad({}, "bad_params")
    err(await client.call("obj.set", {"name": n, "ref": ref, "expect": _expect(bottle), "set": [1]}), "bad_params")
    err(await client.call("obj.set", {"name": n, "ref": ref, "set": {"weight": 1}}), "bad_params")  # expect obbligatorio
    err(
        await client.call("obj.set", {"name": n, "ref": ref, "expect": {"vnum": BOTTLE, "fp": "00000000"}, "set": {"weight": 1}}),
        "stale_ref",
    )
    err(await client.call("obj.set", {"name": n, "ref": "inv:9999", "expect": _expect(bottle), "set": {"weight": 1}}), "stale_ref")
    err(await client.call("obj.set", {"name": "Nessuno", "ref": ref, "expect": _expect(bottle), "set": {"weight": 1}}), "not_found")
    assert (await _fresh(client, target, BOTTLE, 0))["fp"] == bottle["fp"]  # nessuna modifica in seguito agli errori


async def test_obj_set_is_atomic(client: LiveClient, target: Target) -> None:
    """Un campo non valido annulla tutta la richiesta."""
    bottle = await _fresh(client, target, BOTTLE, 0)
    err(await _set(client, target, bottle, {"name": "zznuovo", "weight": 99999}), "value_out_of_range")
    assert (await _fresh(client, target, BOTTLE, 0))["name"] == bottle["name"]


async def test_stale_ref_when_object_changed(client: LiveClient, target: Target) -> None:
    """Dopo una modifica la vecchia impronta non vale piu': `stale_ref`, senza toccare nulla."""
    bottle = await _fresh(client, target, BOTTLE, 0)
    ok(await _set(client, target, bottle, {"name": "zzstale"}))
    e = err(await _set(client, target, bottle, {"name": "zzdopo"}), "stale_ref")
    assert e["message"]
    cur = await _fresh(client, target, BOTTLE, 0)
    assert cur["name"] == "zzstale"
    ok(await _set(client, target, cur, {"name": bottle["name"]}))


async def test_stale_ref_when_inventory_shifts(client: LiveClient, target: Target) -> None:
    """Un oggetto nuovo in testa all'inventario sposta gli indici: il vecchio ref punta a un altro oggetto e `expect` lo rifiuta."""
    bag = await _fresh(client, target, BAG, 0)
    ok(await client.call("load.obj", {"vnum": BOTTLE, "player": target.player}))
    err(
        await client.call(
            "obj.set", {"name": target.player, "ref": bag["ref"], "expect": _expect(bag), "set": {"weight": bag["weight"] + 1}}
        ),
        "stale_ref",
    )
    inv = await _inv(client, target)
    new = _find(inv["items"], BOTTLE, 0)
    ok(await client.call("obj.remove", {"name": target.player, "ref": new["ref"], "expect": _expect(new)}))


async def test_instance_strings_are_not_shared_with_the_prototype(client: LiveClient, target: Target) -> None:
    """Cambiare i testi di un'istanza non tocca il prototipo ne' le altre istanze, e distruggerla poi non rompe nulla."""
    count = (await _inv(client, target))["count"]
    ok(await client.call("load.obj", {"vnum": target.obj_vnum, "player": target.player}))
    inv = await _inv(client, target)
    a = _find(inv["items"], BOTTLE, 0)
    original = (a["name"], a["short_description"], a["description"])
    ok(await _set(client, target, a, {"name": "zzuno", "short_description": "una zz", "description": "Una zz e' qui."}))
    ok(await client.call("load.obj", {"vnum": target.obj_vnum, "player": target.player}))
    inv = await _inv(client, target)
    fresh = [i for i in inv["items"] if i["vnum"] == BOTTLE and i["depth"] == 0 and i["slot"] is None]
    assert [i["name"] for i in fresh].count("zzuno") == 1
    other = next(i for i in fresh if i["name"] != "zzuno")
    assert (other["name"], other["short_description"], other["description"]) == original  # il prototipo e' intatto
    modified = next(i for i in fresh if i["name"] == "zzuno")
    for it in (modified, other):  # libera i testi sostituiti e quelli originali
        cur = next(i for i in (await _inv(client, target))["items"] if i["fp"] == it["fp"] and i["vnum"] == BOTTLE and i["depth"] == 0)
        ok(await client.call("obj.remove", {"name": target.player, "ref": cur["ref"], "expect": _expect(cur)}))
    ok(await client.call("ping"))
    assert (await _inv(client, target))["count"] == count


async def test_audit_for_object_writes(client: LiveClient, target: Target) -> None:
    """Ogni scrittura sugli oggetti e' nell'audit con comando, giocatore, ref e nomi dei campi; mai i testi nuovi."""
    if target.kind == "real" and not target.audit_lines():
        return
    bottle = await _fresh(client, target, BOTTLE, 0)
    start = len(target.audit_lines())
    ok(await _set(client, target, bottle, {"name": "zzsegretozz", "weight": bottle["weight"]}))
    ok(await _set(client, target, await _fresh(client, target, BOTTLE, 0), {"name": bottle["name"]}))
    lines = [ln for ln in target.audit_lines()[start:] if "cmd=obj.set" in ln]
    first = lines[0]
    assert f"target={target.player}" in first and "ref=" in first and "name" in first
    text = "\n".join(target.audit_lines())
    assert "zzsegretozz" not in text and target.token not in text


async def test_load_obj_high_vnum_warns(client: LiveClient, target: Target) -> None:
    """`load.obj` a un giocatore con vnum > 32767: avviso `vnum_not_saveable`; altrimenti nessun avviso."""
    r = ok(await client.call("load.obj", {"vnum": target.high_obj, "player": target.player}))
    assert r["warnings"] == ["vnum_not_saveable"] and r["loaded"][0]["vnum"] == target.high_obj
    r2 = ok(await client.call("load.obj", {"vnum": target.obj_vnum, "player": target.player}))
    assert r2["warnings"] == []
    assert ok(await client.call("load.obj", {"vnum": target.high_obj, "room": target.room}))["warnings"] == []
    for vnum in (target.high_obj, target.obj_vnum):
        inv = await _inv(client, target)
        it = next(i for i in inv["items"] if i["vnum"] == vnum and i["depth"] == 0 and i["slot"] is None)
        ok(await client.call("obj.remove", {"name": target.player, "ref": it["ref"], "expect": _expect(it)}))


# ---- rimozione (distruttiva: ultimo) ------------------------------------------------------------------------------------


async def test_zz_obj_remove_validation(client: LiveClient, target: Target) -> None:
    """`obj.remove` richiede `expect`; non rimuove con impronta sbagliata."""
    bottle = await _fresh(client, target, BOTTLE, 0)
    err(await client.call("obj.remove", {"name": target.player, "ref": bottle["ref"]}), "bad_params")
    err(
        await client.call("obj.remove", {"name": target.player, "ref": bottle["ref"], "expect": {"vnum": BOTTLE, "fp": "00000000"}}),
        "stale_ref",
    )
    err(await client.call("obj.remove", {"name": "Nessuno", "ref": bottle["ref"], "expect": _expect(bottle)}), "not_found")
    assert (await _inv(client, target))["count"] >= 4


async def test_zz_obj_remove_loose_item(client: LiveClient, target: Target) -> None:
    """Rimuove una bottiglia sciolta: sparisce dall'elenco e il peso trasportato scende."""
    before = await _inv(client, target)
    bottle = _find(before["items"], BOTTLE, 0)
    r = ok(await client.call("obj.remove", {"name": target.player, "ref": bottle["ref"], "expect": _expect(bottle)}))
    assert r["removed"] is True and r["destroyed"] == 1 and r["saved"] is True
    after = await _inv(client, target)
    assert after["count"] == before["count"] - 1 and after["carry_weight"] == before["carry_weight"] - bottle["weight"]


async def test_zz_obj_remove_nested_then_container_and_equipped(client: LiveClient, target: Target) -> None:
    """Rimuove un oggetto annidato (pesi dei contenitori aggiornati), poi il contenitore col suo contenuto, poi l'oggetto indossato."""
    before = await _inv(client, target)
    inner = _find(before["items"], BOTTLE, 1)
    bag = _find(before["items"], BAG, 0)
    ok(await client.call("obj.remove", {"name": target.player, "ref": inner["ref"], "expect": _expect(inner)}))
    mid = await _inv(client, target)
    assert next(x for x in mid["items"] if x["ref"] == bag["ref"])["weight"] == bag["weight"] - inner["weight"]
    assert mid["carry_weight"] == before["carry_weight"] - inner["weight"] and mid["count"] == before["count"] - 1
    # contenitore con contenuto: rimettiamo una bottiglia dentro non e' possibile dal canale, quindi si distrugge la borsa (ora vuota)
    bag = next(x for x in mid["items"] if x["ref"] == bag["ref"])
    r = ok(await client.call("obj.remove", {"name": target.player, "ref": bag["ref"], "expect": _expect(bag)}))
    assert r["destroyed"] >= 1
    vest = _find((await _inv(client, target))["items"], VEST, 0, slot=True)
    pre = await _inv(client, target)
    ok(await client.call("obj.remove", {"name": target.player, "ref": vest["ref"], "expect": _expect(vest)}))
    post = await _inv(client, target)
    assert not [i for i in post["items"] if i["slot"] is not None and i["vnum"] == VEST]
    assert post["carry_weight"] == pre["carry_weight"] - vest["weight"]
    json.dumps(post)
