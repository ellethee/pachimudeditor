"""Negozi del gioco: l'elenco dei mob con il campo `shop:` (o con il vecchio `shop_id`, che non fa niente). Prefisso `/api/content`.

Un negozio non e' un file: e' il campo `shop` del mob e si modifica nella scheda del mob (`extra.shop`). Qui c'e' solo la vista
d'insieme, con le merci e la stanza risolte per nome.
"""

from pachifast.database import AliasedBaseModel
from pachifast.router_factory import get_router

from fastapi import Depends
from pachimudeditor.sdk import require_capability
from pachimudeditor_adapter_pachimud.editor.db import PachimudDep
from pachimudeditor_adapter_pachimud.loaders import GAME_OBJECT_TYPES, SHOP_MESSAGE_KEYS

router = get_router(name="content", deps=[Depends(require_capability("supports_content_races"))])


class ShopGood(AliasedBaseModel):
    """Un oggetto sempre in vendita."""

    vnum: int
    name: str | None
    """Descrizione breve dell'oggetto; `None` se non esiste (il controllo del gioco lo segnala: `shop-object-missing`)."""


class ShopItem(AliasedBaseModel):
    """Un negoziante: il mob e il suo negozio (se ha il campo `shop`)."""

    vnum: int
    name: str
    zone_id: int
    zone_name: str
    has_shop: bool
    legacy_shop_id: str | None
    """`shop_id` dei vecchi file: il gioco lo ignora, un negoziante ha il campo `shop`."""
    produces: list[ShopGood] = []
    trades: list[str] = []
    profit_buy: float = 1.0
    profit_sell: float = 0.0
    room: int | None = None
    room_name: str | None = None
    open1: int = 0
    close1: int = 28
    open2: int = 0
    close2: int = 0
    handler: str | None = None
    hours: list[str] = []
    inventory_closed: bool = False


class ShopOptions(AliasedBaseModel):
    """Valori ammessi dai campi del negozio (per i select della scheda del mob)."""

    object_types: list[str]
    """Tipi di oggetto che un negoziante puo' comprare (`trades`)."""
    message_keys: list[str]
    """I sette messaggi che un negozio puo' sostituire (`messages`)."""


@router.get("/shops/options", response_model=ShopOptions)
async def shop_options() -> ShopOptions:
    """Tipi di oggetto e chiavi dei messaggi ammessi in `shop:`."""
    return ShopOptions(object_types=list(GAME_OBJECT_TYPES), message_keys=list(SHOP_MESSAGE_KEYS))


@router.get("/shops", response_model=list[ShopItem])
async def list_shops(adapter: PachimudDep) -> list[ShopItem]:
    """I mob con un negozio o con un `shop_id` legacy, in ordine di vnum, con merci e stanza risolte per nome."""
    store = adapter.sync()
    rooms = store.room_names()
    out: list[ShopItem] = []
    for mob in sorted(store.all_items("mob"), key=lambda m: m.vnum):
        model = mob.model
        if model.shop is None and not model.shop_id:
            continue
        item = ShopItem(
            vnum=mob.vnum,
            name=model.short_description,
            zone_id=mob.zone.vnum,
            zone_name=mob.zone.model.name,
            has_shop=model.shop is not None,
            legacy_shop_id=model.shop_id or None,
        )
        if model.shop is not None:
            shop = model.shop
            goods = []
            for vnum in shop.produces:
                found = store.find("object", vnum)
                goods.append(ShopGood(vnum=vnum, name=found.model.short_description if found else None))
            item = item.model_copy(
                update={
                    "produces": goods,
                    "trades": list(shop.trades),
                    "profit_buy": shop.profit_buy,
                    "profit_sell": shop.profit_sell,
                    "room": shop.room,
                    "room_name": rooms.get(shop.room) if shop.room is not None else None,
                    "open1": shop.open1,
                    "close1": shop.close1,
                    "open2": shop.open2,
                    "close2": shop.close2,
                    "handler": shop.handler,
                    "hours": list(shop.hours),
                    "inventory_closed": shop.inventory_closed,
                }
            )
        out.append(item)
    return out
