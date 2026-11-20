"""Loader YAML del gioco pachimud: copie minime dei modelli `Loader*` del MUD (`zone/schema`, `zone/room/schema`,
`mob/schema`, `object/schema`).

L'editor NON importa il gioco: questi modelli sono la copia da riallineare a mano quando cambia il formato dei file
(vedi `docs/contributing.md`, sezione «Riallineare i loader YAML»). Stessi campi, default e validatori del gioco, cosi'
un file valido per il gioco lo e' anche qui e viceversa. Regole del gioco che contano per l'editor:

- le voci sono validate una a una (un file con una voce rotta non impedisce di leggere le altre, vedi `store.py`);
- i nomi di enum (`sector_type`, `door_flag`, `sex`, `reset_mode`, direzioni delle uscite) sono confrontati senza
  distinzione di maiuscole e normalizzati in MAIUSCOLO;
- ogni voce di oggetto ha `object_type` e SOLO i campi del suo tipo (`extra="forbid"`).
"""

import re
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, field_validator, model_validator

from pachimudeditor.common.enums import Direction, DoorFlag, SectorType, Sex, ZoneResetMode

AreaName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]
"""Etichetta libera dell'«area» di un file o di una voce (`rooms_<area>.yaml`)."""

_DICE_RE = re.compile(r"^\s*-?\d+d-?\d+\+-?\d+\s*$")
DICE_PARTS = re.compile(r"^\s*(-?\d+)d(-?\d+)\+(-?\d+)\s*$")


def enum_name(enum_cls: type, value: str) -> str:
    """Il nome MAIUSCOLO del membro di `enum_cls` indicato da `value` (senza distinzione di maiuscole).

    Raises:
        ValueError: se `value` non e' il nome di un membro.
    """
    name = str(value).strip().upper()
    if name not in enum_cls.__members__:
        raise ValueError(f"valore non valido {value!r} per {enum_cls.__name__}, atteso uno tra: {', '.join(enum_cls.__members__)}")
    return name


def split_dice(text: str) -> tuple[int, int, int]:
    """`"3d8+10"` -> `(3, 8, 10)`."""
    match = DICE_PARTS.match(text)
    if match is None:
        raise ValueError(f"formato dadi non valido {text!r}")
    return int(match[1]), int(match[2]), int(match[3])


def join_dice(count: int, size: int, bonus: int) -> str:
    """`(3, 8, 10)` -> `"3d8+10"` (bonus negativo: `"3d8+-2"`, come richiede il gioco)."""
    return f"{count}d{size}+{bonus}"


# --------------------------------------------------------------------------------------------- zona e reset


class LoaderZone(BaseModel):
    """`zone.yaml`."""

    zone_id: str
    vnum: int
    name: str
    builder: str
    description: str = ""
    bottom_vnum: int
    top_vnum: int
    min_level: int = 1
    max_level: int = 1
    lifespan_minutes: int = 30
    reset_mode: str = "ALWAYS"
    climate: Literal["temperate", "desert", "arctic"] = "temperate"
    enabled: bool = True
    prototypes_only: bool = False
    extends_zone: Optional[int] = None

    @field_validator("reset_mode")
    @classmethod
    def _check_reset_mode(cls, v: str) -> str:
        """Nome di `ZoneResetMode`."""
        return enum_name(ZoneResetMode, v)


class LoaderResetContent(BaseModel):
    """Un oggetto senza stanza: dentro un contenitore o nell'inventario di un mob."""

    obj_vnum: int
    max_existing: int | None = None
    contains: list["LoaderResetContent"] = []


class LoaderResetObject(LoaderResetContent):
    """Un oggetto a terra in una stanza."""

    room_vnum: int
    room_limit: int


class LoaderResetObjectInventory(LoaderResetContent):
    """Un oggetto dell'inventario di un mob (`wear_slot` assente = resta nell'inventario)."""

    wear_slot: Optional[str] = None


class LoaderResetMob(BaseModel):
    """Un mob da caricare in una stanza, con il suo inventario."""

    mob_vnum: int
    max_existing: int
    room_vnum: int
    room_limit: int
    inventory: list[LoaderResetObjectInventory] = []


class LoaderResetDoor(BaseModel):
    """Stato di una porta al reset."""

    room_vnum: int
    state: str = "OPEN"
    direction: str = "NORTH"


class LoaderReset(BaseModel):
    """Il contenuto di `resets:`."""

    mobs: list[LoaderResetMob] = []
    objects: list[LoaderResetObject] = []
    doors: list[LoaderResetDoor] = []


class LoaderResetFile(BaseModel):
    """`resets*.yaml`."""

    area: Optional[AreaName] = None
    resets: LoaderReset


# --------------------------------------------------------------------------------------------- stanze


OPEN_COMMANDS = ("pull", "push", "lift", "turn", "twist", "dig", "cut")
"""I comandi che possono aprire una porta al posto di `open`/`close` (`open_cmd` delle uscite)."""


class LoaderExit(BaseModel):
    """Un'uscita."""

    target_vnum: Optional[int] = None
    description: Optional[str] = None
    keywords: Optional[str] = None
    is_male: bool = False
    door_flag: str = "NONE"
    is_open: bool = True
    is_locked: bool = False
    key_vnum: Optional[int] = None
    open_cmd: Optional[str] = None
    climb: bool = False

    @field_validator("door_flag")
    @classmethod
    def _check_door_flag(cls, v: str) -> str:
        """Nome di `DoorFlag`."""
        return enum_name(DoorFlag, v)

    @field_validator("open_cmd")
    @classmethod
    def _check_open_cmd(cls, v: Optional[str]) -> Optional[str]:
        """Uno di `OPEN_COMMANDS` (o assente)."""
        if v is not None and v not in OPEN_COMMANDS:
            raise ValueError(f"open_cmd deve essere uno di {', '.join(OPEN_COMMANDS)}")
        return v


class LoaderExtraDescription(BaseModel):
    """Una extra description di stanza."""

    keywords: str
    text: str


class LoaderRoom(BaseModel):
    """Una voce di `rooms*.yaml`."""

    vnum: int
    name: str
    enabled: bool = True
    description: str
    sector_type: str = "INSIDE"
    flags: list[str] = []
    heal_rate: int = 100
    mana_rate: int = 100
    clan_id: Optional[str] = None
    owner: Optional[str] = None
    area: Optional[AreaName] = None
    exits: dict[str, LoaderExit] = {}
    extra_descriptions: list[LoaderExtraDescription] = []

    @field_validator("sector_type")
    @classmethod
    def _check_sector_type(cls, v: str) -> str:
        """Nome di `SectorType`."""
        return enum_name(SectorType, v)

    @model_validator(mode="after")
    def _check_exit_directions(self) -> "LoaderRoom":
        """Direzioni valide e non duplicate (anche a meno delle maiuscole)."""
        seen: set[str] = set()
        for key in self.exits:
            name = enum_name(Direction, key)
            if name in seen:
                raise ValueError(f"direzione duplicata {key!r}")
            seen.add(name)
        return self


# --------------------------------------------------------------------------------------------- mob

SHOP_MESSAGE_KEYS = ("no_such_item1", "no_such_item2", "do_not_buy", "missing_cash1", "missing_cash2", "message_buy", "message_sell")
"""I sette messaggi del negoziante che un negozio puo' sostituire (per lingua)."""
GAME_OBJECT_TYPES: tuple[str, ...] = (
    "LIGHT", "SCROLL", "WAND", "STAFF", "WEAPON", "FIREWEAPON", "MISSILE", "TREASURE", "ARMOR", "POTION", "WORN", "OTHER",
    "TRASH", "TRAP", "CONTAINER", "NOTE", "DRINKCON", "KEY", "FOOD", "MONEY", "PEN", "BOAT", "AUDIO", "BOARD", "TREE", "ROCK", "FOUNTAIN",
)  # fmt: skip
"""I nomi dei tipi oggetto del gioco (`ObjectType`), per i `trades` di un negozio."""


class LoaderShop(BaseModel):
    """Il campo `shop:` di un mob (copia di `ShopProto`)."""

    produces: list[int] = []
    profit_buy: float = 1.0
    profit_sell: float = 0.0
    trades: list[str] = []
    room: Optional[int] = None
    open1: int = 0
    close1: int = 28
    open2: int = 0
    close2: int = 0
    no_money_reaction: Literal["puke", "grin", "none"] = "puke"
    attacked_reaction: Literal["warn", "insult", "none"] = "warn"
    messages: dict[str, dict[str, str]] = {}
    handler: Optional[str] = None

    @field_validator("trades")
    @classmethod
    def _check_trades(cls, value: list[str]) -> list[str]:
        """Nomi di tipi oggetto del gioco (senza distinzione di maiuscole, normalizzati in MAIUSCOLO)."""
        names = []
        for v in value:
            name = str(v).strip().upper()
            if name not in GAME_OBJECT_TYPES:
                raise ValueError(f"tipo oggetto non valido {v!r}, atteso uno tra: {', '.join(GAME_OBJECT_TYPES)}")
            names.append(name)
        return names

    @field_validator("messages")
    @classmethod
    def _check_messages(cls, value: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
        """Solo le chiavi di `SHOP_MESSAGE_KEYS`."""
        unknown = set(value) - set(SHOP_MESSAGE_KEYS)
        if unknown:
            raise ValueError(f"messaggi sconosciuti {sorted(unknown)}, attesi tra: {', '.join(SHOP_MESSAGE_KEYS)}")
        return value


class LoaderMob(BaseModel):
    """Una voce di `mobs*.yaml`."""

    vnum: int
    area: Optional[AreaName] = None
    keywords: str
    name: Optional[str] = ""
    short_description: str
    long_description: str
    detailed_description: str
    level: int
    thac0: int
    attacks: int = 1
    armor_class: int
    hp_dice: str
    damage_dice: str
    strength: int = 0
    dexterity: int = 0
    constitution: int = 0
    intelligence: int = 0
    wisdom: int = 0
    charisma: int = 0
    gold: int = 0
    experience: int = 0
    sex: str = "NEUTRAL"
    flags: list[str] = []
    alignment: int = 0
    race_id: Optional[str] = None
    class_id: Optional[str] = None
    debuff_skill_id: Optional[str] = None
    persona: str = ""
    shop_id: Optional[str] = None
    shop: Optional[LoaderShop] = None
    quest_ids: list[str] = []
    is_banker: bool = False
    postmaster: bool = False
    receptionist: bool = False
    weapon_immunity: Optional[int] = Field(default=None, ge=0, le=4)
    breath: list[str] = []
    breath_cost: int = 30
    teaches_class_ids: Optional[list[str]] = None
    teaches_skill_ids: Optional[list[str]] = None

    @field_validator("hp_dice", "damage_dice")
    @classmethod
    def _check_dice(cls, v: str) -> str:
        """Notazione `XdY+Z`."""
        if not _DICE_RE.match(v):
            raise ValueError(f"formato dadi non valido {v!r}, atteso 'XdY+Z' (es. '3d8+10')")
        return v.strip()

    @field_validator("sex")
    @classmethod
    def _check_sex(cls, v: str) -> str:
        """Nome di `Sex`."""
        return enum_name(Sex, v)


# --------------------------------------------------------------------------------------------- oggetti

MAX_OBJ_AFFECT = 5
ContainerFlag = Literal["CLOSEABLE", "PICKPROOF", "CLOSED", "LOCKED", "NO_WEIGHT"]
LIQUIDS: tuple[str, ...] = (
    "water", "beer", "wine", "ale", "darkale", "whisky", "lemonade", "firebrt",
    "localspc", "slime", "milk", "tea", "coffee", "blood", "saltwater", "coke",
)  # fmt: skip
Liquid = Literal[
    "water", "beer", "wine", "ale", "darkale", "whisky", "lemonade", "firebrt",
    "localspc", "slime", "milk", "tea", "coffee", "blood", "saltwater", "coke",
]  # fmt: skip


class ObjectBaseProto(BaseModel):
    """Campi comuni a ogni oggetto."""

    model_config = ConfigDict(extra="forbid")

    vnum: int
    area: Optional[AreaName] = None
    keywords: str
    short_description: str
    long_description: str
    action_description: Optional[str] = None
    weight: int = 0
    cost: int = 0
    rent: int = 0
    extra_flags: list[str] = []
    wear_flags: list[str] = []
    affects: dict[str, int] = {}
    extra_descriptions: list[LoaderExtraDescription] = []

    @field_validator("affects")
    @classmethod
    def _max_affects(cls, value: dict[str, int]) -> dict[str, int]:
        """Al massimo `MAX_OBJ_AFFECT` affects."""
        if len(value) > MAX_OBJ_AFFECT:
            raise ValueError(f"al massimo {MAX_OBJ_AFFECT} affects")
        return value


class LightProto(ObjectBaseProto):
    """LIGHT."""

    object_type: Literal["LIGHT"]
    hours: int = -1


class ScrollProto(ObjectBaseProto):
    """SCROLL, POTION."""

    object_type: Literal["SCROLL", "POTION"]
    level: int = 1
    spells: Annotated[list[str], Field(max_length=3)] = []


class WandProto(ObjectBaseProto):
    """WAND, STAFF."""

    object_type: Literal["WAND", "STAFF"]
    level: int = 1
    max_charges: int = 1
    charges: int = 1
    spell: Optional[str] = None


class WeaponProto(ObjectBaseProto):
    """WEAPON."""

    object_type: Literal["WEAPON"]
    dice_count: int = 1
    die_size: int = 4
    weapon_type: int = 3


class FireWeaponProto(ObjectBaseProto):
    """FIREWEAPON (arco, balestra)."""

    object_type: Literal["FIREWEAPON"]
    strength: int = 0
    range_bonus: int = 0
    ammo_type: int = 0


class MissileProto(ObjectBaseProto):
    """MISSILE (freccia, dardo)."""

    object_type: Literal["MISSILE"]
    break_chance: int = 0
    dice_count: int = 1
    die_size: int = 4
    ammo_type: int = 0


class ArmorProto(ObjectBaseProto):
    """ARMOR."""

    object_type: Literal["ARMOR"]
    armor_class: int = 0


class ContainerProto(ObjectBaseProto):
    """CONTAINER."""

    object_type: Literal["CONTAINER"]
    max_weight: int = 0
    container_flags: list[ContainerFlag] = []
    key_vnum: Optional[int] = None
    corpse: bool = False


class DrinkConProto(ObjectBaseProto):
    """DRINKCON."""

    object_type: Literal["DRINKCON"]
    capacity: int = 0
    units: int = 0
    liquid: Liquid = "water"
    poisoned: bool = False
    permanent: bool = False


class FoodProto(ObjectBaseProto):
    """FOOD."""

    object_type: Literal["FOOD"]
    hours: int = 0
    poisoned: bool = False


class MoneyProto(ObjectBaseProto):
    """MONEY."""

    object_type: Literal["MONEY"]
    gold: int = 0


class KeyProto(ObjectBaseProto):
    """KEY."""

    object_type: Literal["KEY"]
    key_type: int = 0


class AudioProto(ObjectBaseProto):
    """AUDIO."""

    object_type: Literal["AUDIO"]
    frequency: int = 0


TrapTrigger = Literal["MOVE", "OBJECT", "ROOM", "NORTH", "EAST", "SOUTH", "WEST", "UP", "DOWN"]
TrapDamage = Literal["sleep", "teleport", "poison", "fire", "cold", "acid", "energy", "blunt", "pierce", "slash"]


class TrapProto(ObjectBaseProto):
    """TRAP."""

    object_type: Literal["TRAP"]
    triggers: list[TrapTrigger] = []
    damage: TrapDamage = "pierce"
    level: int = 1
    charges: int = 1


class BoardProto(ObjectBaseProto):
    """BOARD (bacheca): i messaggi stanno nel DB del gioco, uno stesso `board_id` e' la stessa bacheca ovunque."""

    object_type: Literal["BOARD"]
    board_id: str = ""
    min_read_level: int = 0
    min_write_level: int = 1
    min_remove_level: int = 51
    max_messages: int = Field(default=99, gt=0)
    max_length: int = Field(default=2048, gt=0)


GENERIC_TYPES: tuple[str, ...] = (
    "TREASURE", "WORN", "OTHER", "TRASH",
    "NOTE", "PEN", "BOAT", "TREE", "ROCK", "FOUNTAIN",
)  # fmt: skip


class GenericProto(ObjectBaseProto):
    """Tipi senza valori."""

    object_type: Literal[
        "TREASURE", "WORN", "OTHER", "TRASH",
        "NOTE", "PEN", "BOAT", "TREE", "ROCK", "FOUNTAIN",
    ]  # fmt: skip


ObjectProto = Annotated[
    LightProto
    | ScrollProto
    | WandProto
    | WeaponProto
    | FireWeaponProto
    | MissileProto
    | ArmorProto
    | ContainerProto
    | DrinkConProto
    | FoodProto
    | MoneyProto
    | KeyProto
    | AudioProto
    | TrapProto
    | BoardProto
    | GenericProto,
    Field(discriminator="object_type"),
]

TYPE_MODELS: dict[str, type[ObjectBaseProto]] = {
    **{t: LightProto for t in ("LIGHT",)},
    **{t: ScrollProto for t in ("SCROLL", "POTION")},
    **{t: WandProto for t in ("WAND", "STAFF")},
    "WEAPON": WeaponProto,
    "FIREWEAPON": FireWeaponProto,
    "MISSILE": MissileProto,
    "BOARD": BoardProto,
    "ARMOR": ArmorProto,
    "CONTAINER": ContainerProto,
    "DRINKCON": DrinkConProto,
    "FOOD": FoodProto,
    "MONEY": MoneyProto,
    "KEY": KeyProto,
    "AUDIO": AudioProto,
    "TRAP": TrapProto,
    **{t: GenericProto for t in GENERIC_TYPES},
}
"""`object_type` -> modello dei campi di quel tipo."""

COMMON_OBJECT_FIELDS: frozenset[str] = frozenset(ObjectBaseProto.model_fields)
"""Campi comuni a ogni tipo (incluso `vnum`/`area`)."""


OBJECT_ADAPTER: TypeAdapter[Any] = TypeAdapter(ObjectProto)
"""Validatore dell'unione discriminata degli oggetti (creato una volta: costruirlo costa millisecondi)."""


def type_fields(object_type: str) -> list[str]:
    """I nomi dei campi specifici del tipo (esclusi i comuni e `object_type`)."""
    return [n for n in TYPE_MODELS[object_type].model_fields if n not in COMMON_OBJECT_FIELDS and n != "object_type"]


def validate_entry(kind: str, data: dict[str, Any]) -> BaseModel:
    """Valida una voce `rooms`/`mobs`/`objects` (dict normale); `ValidationError` se non valida."""
    if kind == "rooms":
        return LoaderRoom.model_validate(data)
    if kind == "mobs":
        return LoaderMob.model_validate(data)
    return OBJECT_ADAPTER.validate_python(data)  # type: ignore[no-any-return]
