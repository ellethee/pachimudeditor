"""Negozi pachimud: il campo `shop:` del mob (`extra.shop`) e l'elenco `/api/content/shops`."""

import httpx

from tests.helpers import by_vnum, data, error_code
from tests.support.stack import zones_dir


async def test_shops_list_options_and_edit(client: httpx.AsyncClient) -> None:
    """Un mob diventa negoziante con `extra.shop`: l'elenco risolve merci e stanza; un negozio non valido e' 422; `null` lo toglie."""
    options = data(await client.get("/api/content/shops/options"))
    assert "WEAPON" in options["objectTypes"] and "message_buy" in options["messageKeys"]
    before = data(await client.get("/api/content/shops"))
    mob = await by_vnum(client, "mobs", 1000)
    obj = await by_vnum(client, "objects", 1000)
    shop = {
        "produces": [obj["vnum"], 999999],
        "trades": ["weapon"],
        "profit_buy": 1.5,
        "close1": 20,
        "messages": {"message_buy": {"it": "Grazie {player}"}},
    }
    updated = data(await client.put(f"/api/mobs/{mob['id']}", json={"extra": {"shop": shop}}))
    assert updated["extra"]["shop"]["trades"] == ["WEAPON"] and updated["extra"]["shop"]["profit_sell"] == 0.0
    assert "shop:" in "".join(p.read_text() for p in (zones_dir() / "ZonaAlfa").glob("mobs*.yaml"))
    rows = data(await client.get("/api/content/shops"))
    row = next(r for r in rows if r["vnum"] == mob["vnum"])
    assert len(rows) == len(before) + 1 and row["hasShop"] and row["profitBuy"] == 1.5 and row["close1"] == 20
    assert row["produces"] == [{"vnum": obj["vnum"], "name": obj["shortDescription"]}, {"vnum": 999999, "name": None}]
    # un negozio non valido non si salva
    assert (
        error_code(await client.put(f"/api/mobs/{mob['id']}", json={"extra": {"shop": {"trades": ["NOPE"]}}}), 422)
        == "pachimud.invalid_entry"
    )
    # `null` toglie il negozio
    assert data(await client.put(f"/api/mobs/{mob['id']}", json={"extra": {"shop": None}}))["extra"]["shop"] is None
    assert all(r["vnum"] != mob["vnum"] for r in data(await client.get("/api/content/shops")))


async def test_legacy_shop_id_is_listed(client: httpx.AsyncClient) -> None:
    """Un mob con il vecchio `shop_id` e senza `shop` compare nell'elenco come legacy (il gioco lo ignora)."""
    mob = await by_vnum(client, "mobs", 1001)
    data(await client.put(f"/api/mobs/{mob['id']}", json={"shopId": "fabbro"}))
    row = next(r for r in data(await client.get("/api/content/shops")) if r["vnum"] == mob["vnum"])
    assert row["legacyShopId"] == "fabbro" and row["hasShop"] is False and row["produces"] == []
