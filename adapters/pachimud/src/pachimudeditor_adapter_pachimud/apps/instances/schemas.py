"""Schemi dell'app instances: mob e oggetti vivi nel mondo (`MobInstance`/`ObjectInstance`)."""

from pachifast.database import AliasedBaseModel

LOCATION_KINDS: tuple[str, ...] = ("room", "container", "mob", "character")
"""Dove puo' stare un oggetto: a terra in una stanza, dentro un contenitore, addosso a un mob o a un personaggio."""

CONTENTS_POLICIES: tuple[str, ...] = ("destroy", "drop")
"""Cosa fare del contenuto di cio' che si elimina: distruggerlo o lasciarlo dov'era chi lo teneva."""


class LocationIn(AliasedBaseModel):
    """Posizione di un oggetto: `kind` + id del bersaglio (stanza, istanza contenitore, istanza mob, personaggio).

    `equippedSlot` ha senso solo per `mob`/`character`: uno dei `wearFlags` del prototipo
    (es. `body`, `wield`); vuoto = trasportato nell'inventario.
    """

    kind: str
    target_id: int
    equipped_slot: str | None = None


class ObjectOut(AliasedBaseModel):
    """Un oggetto vivo, con prototipo e posizione risolti in testo.

    `roomId`/`roomVnum`/`roomName`/`zoneId`/`zoneName` sono la stanza *effettiva* (dove giace, o dove sta
    il contenitore/mob/personaggio che lo porta); nulli se non ne ha una.
    """

    id: int
    prototype_id: int
    prototype_vnum: int
    prototype_name: str
    prototype_zone_id: int
    object_type: int
    wear_slots: list[str]
    location_kind: str
    location_id: int
    location_label: str
    equipped_slot: str | None = None
    room_id: int | None = None
    room_vnum: int | None = None
    room_name: str | None = None
    zone_id: int | None = None
    zone_name: str | None = None
    charges: int | None = None
    liquid_amount: int | None = None
    liquid_type: int | None = None
    liquid_poisoned: bool | None = None
    content_count: int = 0


class ObjectDetail(ObjectOut):
    """`ObjectOut` piu' gli oggetti contenuti (se e' un contenitore)."""

    contents: list[ObjectOut] = []


class ObjectCreate(AliasedBaseModel):
    """Corpo di POST `/objects`: prototipo, posizione e stato iniziale opzionale."""

    prototype_id: int
    location: LocationIn
    charges: int | None = None
    liquid_amount: int | None = None


class ObjectPatch(AliasedBaseModel):
    """Corpo di PUT `/objects/{id}`: solo i campi inviati; `null` riporta il valore a quello del prototipo."""

    charges: int | None = None
    liquid_amount: int | None = None
    liquid_type: int | None = None
    liquid_poisoned: bool | None = None
    location: LocationIn | None = None


class MobOut(AliasedBaseModel):
    """Un mob vivo con prototipo e stanza risolti e il numero di oggetti che porta."""

    id: int
    prototype_id: int
    prototype_vnum: int
    prototype_name: str
    prototype_zone_id: int
    shop_id: str | None = None
    room_id: int
    room_vnum: int
    room_name: str
    zone_id: int
    zone_name: str
    hit_points_current: int
    hit_points_max: int
    gold: int | None = None
    item_count: int = 0


class MobDetail(MobOut):
    """`MobOut` piu' gli oggetti che il mob porta o indossa."""

    items: list[ObjectOut] = []


class MobCreate(AliasedBaseModel):
    """Corpo di POST `/mobs`: `hitPoints`, se assente, si tira dai dadi del prototipo (come il reset di zona)."""

    prototype_id: int
    room_id: int
    hit_points: int | None = None
    gold: int | None = None


class MobPatch(AliasedBaseModel):
    """Corpo di PUT `/mobs/{id}`: solo i campi inviati (`gold: null` azzera la cassa)."""

    hit_points_current: int | None = None
    hit_points_max: int | None = None
    gold: int | None = None
    room_id: int | None = None
