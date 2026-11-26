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
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

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
    max_level: int = 50
    """Livello massimo di accesso (default 50, il gioco non lo applica ancora); `min_level` dei vecchi file e' ignorato."""
    lifespan_minutes: int = 30
    reset_mode: str = "ALWAYS"
    climate: Literal["temperate", "desert", "arctic"] = "temperate"
    enabled: bool = True
    prototypes_only: bool = False
    extends_zone: Optional[int] = None
    email: str = ""
    """Email dell'autore (il gioco non la usa)."""
    difficulty: str = ""
    """Difficolta' media per cui la zona e' pensata (testo libero)."""
    civilized: bool = False
    """Zona civilizzata: ci si parla in Comune."""

    @field_validator("reset_mode")
    @classmethod
    def _check_reset_mode(cls, v: str) -> str:
        """Nome di `ZoneResetMode`."""
        return enum_name(ZoneResetMode, v)


class LoaderResetContent(BaseModel):
    """Un oggetto senza stanza: dentro un contenitore o nell'inventario di un mob."""

    obj_vnum: int
    max_existing: int | None = None
    repop_percent: list[Annotated[float, Field(ge=0, le=100)]] = []
    """Probabilita' (%) per la 1a, 2a, 3a... copia nel mondo (l'ultima vale per le successive)."""
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
    repop_percent: list[Annotated[float, Field(ge=0, le=100)]] = []
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


TRIGGER_TYPES = (
    "speech",
    "greet",
    "give",
    "random",
    "death",
    "fight",
    "hitprcnt",
    "act",
    "tell",
    "bribe",
    "all_greet",
    "entry",
    "command",
    "init",
    "reset",
    "hour",
    "listen",
    "exit",
    "get",
    "drop",
    "wear",
    "fightwashit",
    "wield",
    "throw",
    "remove",
    "put",
    "ocommand",
    "enter",
    "open",
    "rcommand",
)
"""Tutti gli eventi dei trigger (come `TriggerType` del gioco)."""
OWNER_TYPES: dict[str, tuple[str, ...]] = {
    "mob": (
        "speech", "greet", "give", "random", "death", "fight", "hitprcnt", "act", "tell", "bribe", "all_greet", "entry", "command", "init",
        "reset", "hour", "listen", "exit",
    ),
    "object": (
        "get", "drop", "wear", "give", "random", "init", "reset", "greet", "exit", "listen", "fight", "fightwashit", "wield", "throw",
        "remove", "put", "ocommand",
    ),
    "room": ("enter", "exit", "speech", "random", "init", "reset", "hour", "listen", "open", "rcommand"),
}  # fmt: skip
"""Gli eventi ammessi per chi possiede il trigger (`OWNER_TYPES` del gioco)."""
MP_VERBS = (
    "mptransfer", "mpgoto", "mpat", "mpload", "mppurge", "mpkill", "mpforce", "mpset", "mpunset", "mpadd", "mpdamage", "mpheal", "mpgiveexp",
    "mpgivemoney", "mpcast", "mpscast", "block", "mpopen", "mpclose", "mpcommand", "mpjunk", "mpscrap", "mpprendo", "mpposo", "mpimpugno",
    "mpaggressive", "mpposition",
)  # fmt: skip
"""Comandi MP veri (oltre a `mpecho*`/`mpasound`, validi per tutti)."""
MOB_ONLY_MP = ("mpgoto", "mpkill", "mpforce", "mpcast", "mpscast", "mpcommand", "mpjunk", "mpscrap", "mpprendo", "mpposo", "mpimpugno")
"""I comandi MP che richiedono un corpo: oggetti e stanze non li usano (e nemmeno `mppurge self`)."""
CMP = re.compile(r"\s*(==|!=|<=|>=|<|>)?\s*(-?\d+)\s*")
"""Un confronto numerico di una condizione: `10`, `>= 10`, `!= 3` (come `CMP` del gioco)."""
MAX_IF_DEPTH = 25
"""Quanti `if` possono stare uno dentro l'altro."""


class LoaderCondition(BaseModel):
    """Le verifiche di un `if` (copia di `Condition` del gioco); le chiavi sconosciute si tengono: le segnala `content.validate`."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    chance: Optional[int] = Field(default=None, ge=1, le=100)
    level: Union[int, str, None] = None
    hp: Union[int, str, None] = None
    sex: Optional[Literal["male", "female", "other"]] = None
    race: Optional[str] = None
    class_: Optional[str] = Field(default=None, alias="class")
    carries: Optional[str] = None
    is_player: Optional[bool] = None
    time: Union[int, str, None] = None
    is_night: Optional[bool] = None
    is_fighting: Optional[bool] = None
    has_effect: Optional[str] = None
    vnum: Union[int, str, None] = None
    var: Optional[
        dict[str, Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)]]
    ] = None
    """Variabili di stato di chi ha il trigger (`mpset`): nome -> valore o confronto numerico."""
    who: Literal["n", "i"] = "n"

    @model_validator(mode="after")
    def _check(self) -> "LoaderCondition":
        """`time` e `vnum` sono un numero o un confronto; `time` e' un'ora 0-23."""
        for name in ("time", "vnum"):
            value = getattr(self, name)
            if value is None:
                continue
            if not (m := CMP.fullmatch(str(value))):
                raise ValueError(f"{name}: '{value}' non e' un numero o un confronto (es. '>= 10')")
            if name == "time" and not 0 <= int(m[2]) <= 23:
                raise ValueError(f"time: '{value}' deve essere un'ora tra 0 e 23")
        return self


class LoaderIfBlock(BaseModel):
    """Un blocco `{if, then, else}` tra le azioni di un trigger."""

    model_config = ConfigDict(populate_by_name=True)

    if_: LoaderCondition = Field(alias="if")
    then: list["LoaderAction"] = Field(min_length=1)
    else_: list["LoaderAction"] = Field(default_factory=list, alias="else")


LoaderAction = Annotated[
    Union[
        Annotated[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)], Tag("str")],
        Annotated[LoaderIfBlock, Tag("block")],
    ],
    Discriminator(lambda v: "block" if isinstance(v, (dict, LoaderIfBlock)) else "str"),
]
"""Un'azione: un comando (stringa non vuota) o un blocco `if`; il discriminatore tiene leggibile il percorso degli errori."""
LoaderIfBlock.model_rebuild()


def if_depth(actions: list[Any]) -> int:
    """Quanti `if` stanno uno dentro l'altro, al massimo."""
    return max((1 + if_depth([*a.then, *a.else_]) for a in actions if isinstance(a, LoaderIfBlock)), default=0)


class LoaderTrigger(BaseModel):
    """Un trigger di mob, oggetto (`scripts`) o stanza (copia di `Trigger` del gioco): a `type` il proprietario esegue le `actions`."""

    type: Literal[
        "speech", "greet", "give", "random", "death", "fight", "hitprcnt", "act", "tell", "bribe", "all_greet", "entry", "command", "init", "reset", "hour", "listen", "exit", "get", "drop", "wear", "fightwashit", "wield", "throw", "remove", "put", "ocommand", "enter", "open", "rcommand",
    ]  # fmt: skip
    argument: str = ""
    block: bool = False
    """Solo `command`: se scatta, il comando del giocatore non viene eseguito."""
    chance: int = Field(default=100, ge=1, le=100)
    actions: list[LoaderAction] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> "LoaderTrigger":
        """`hitprcnt` e `bribe` vogliono un numero positivo (`hitprcnt` fino a 100); al massimo 3 `if` annidati."""
        if self.type in ("hitprcnt", "bribe") and not (self.argument.strip().isdigit() and int(self.argument) >= 1):
            raise ValueError(f"il trigger {self.type} vuole in argument un numero positivo")
        if self.type == "command" and not self.argument.strip():
            raise ValueError("il trigger command vuole in argument il nome del comando")
        if (
            self.type == "hour"
            and self.argument.strip() not in ("", "-1")
            and not (self.argument.strip().isdigit() and 1 <= int(self.argument) <= 24)
        ):
            raise ValueError("hour: argument vuoto o -1 (ogni ora) oppure un'ora da 1 a 24")
        if self.type in ("ocommand", "rcommand") and not re.fullmatch(r"[pi] \S+( \S+)*", self.argument.strip()):
            raise ValueError(f"{self.type}: argument vuole 'p' o 'i' e poi l'azione e il bersaglio (es. 'i premo borchia')")
        if self.type == "hitprcnt" and int(self.argument) > 100:
            raise ValueError("hitprcnt: la percentuale e' al massimo 100")
        if if_depth(self.actions) > MAX_IF_DEPTH:
            raise ValueError(f"al massimo {MAX_IF_DEPTH} if uno dentro l'altro")
        return self


CURRENT_SECTORS = ("WATER_SWIM", "WATER_NOSWIM", "UNDERWATER")
"""I settori in cui vale la corrente d'acqua."""


class RoomCurrent(BaseModel):
    """Corrente d'acqua: ogni `speed` pulse trascina verso `direction`."""

    speed: int = Field(default=30, ge=1)
    direction: str = "NORTH"

    @field_validator("direction")
    @classmethod
    def _check_direction(cls, v: str) -> str:
        """Nome di `Direction`."""
        return enum_name(Direction, v)


class RoomTeleport(BaseModel):
    """Stanza teletrasporto: ogni `time` pulse porta chi e' in stanza nella stanza `room`."""

    time: int = Field(default=60, ge=1)
    room: int
    look: bool = False
    countdown: Optional[int] = Field(default=None, ge=1)
    random_time: bool = False
    no_mob: bool = False
    no_objects: bool = False


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
    climate: Optional[Literal["temperate", "desert", "arctic"]] = None
    """Clima della stanza; vuoto = quello della zona."""
    exits: dict[str, LoaderExit] = {}
    extra_descriptions: list[LoaderExtraDescription] = []
    triggers: list[LoaderTrigger] = []
    spec: Optional[str] = None
    """Procedura speciale (nome del catalogo `specs.json`)."""
    current: Optional[RoomCurrent] = None
    teleport: Optional[RoomTeleport] = None

    @model_validator(mode="after")
    def _check_current_sector(self) -> "LoaderRoom":
        """La corrente d'acqua vale solo nei settori d'acqua."""
        if self.current is not None and self.sector_type not in CURRENT_SECTORS:
            raise ValueError(f"la corrente d'acqua vale solo nei settori {', '.join(CURRENT_SECTORS)}, non in {self.sector_type}")
        return self

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
    "LIFESAVER", "BOOK", "CORPSE", "PORTAL", "FURNISHING", "PRECIOUS", "RAW_MATERIAL", "PROCESSED_MATERIAL", "CRAFTED", "MERCHANT",
    "MOUNT_FOOD", "ALCHEMY", "OINTMENT",
)  # fmt: skip
"""I nomi dei tipi oggetto del gioco (`ObjectType`), per i `trades` di un negozio."""


_SPAN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d$")


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
    hours: list[str] = []
    """Fasce `hh:mm-hh:mm` (ora di gioco, al massimo due): se ci sono valgono al posto di `open1`..`close2`."""
    inventory_closed: bool = False
    """Chiuso per inventario: il negoziante non tratta con nessuno."""

    @field_validator("hours")
    @classmethod
    def _check_hours(cls, value: list[str]) -> list[str]:
        """Al massimo due fasce `hh:mm-hh:mm`."""
        if len(value) > 2:
            raise ValueError("al massimo due fasce orarie")
        for span in value:
            if not _SPAN.match(span):
                raise ValueError(f"fascia oraria {span!r} non valida, atteso 'hh:mm-hh:mm' (es. '08:00-13:00')")
        return value

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


MobPosition = Literal["SLEEPING", "RESTING", "SITTING", "STANDING"]
"""Le posizioni di partenza ammesse per un mob."""


class MobNoise(BaseModel):
    """Mob rumoroso: suono vicino (stanza) e lontano (stanze adiacenti)."""

    near: str = ""
    far: str = ""
    chance: int = Field(default=3, ge=1, le=100)


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
    triggers: list[LoaderTrigger] = []
    position: MobPosition = "STANDING"
    """Posizione di default (a ogni reset e a fine combattimento)."""
    clan_id: Optional[str] = None
    """Clan del mob: i mob dello stesso clan non si attaccano; `0` o vuoto = nessuno."""
    noise: Optional[MobNoise] = None
    affects: list[str] = []
    """Effetti permanenti (`FLYING`, `SANCTUARY`...)."""
    immunity: list[str] = []
    resistance: list[str] = []
    vulnerability: list[str] = []
    """Nomi di `ResistanceFlags`, sommati a quelli della razza."""
    spec: Optional[str] = None
    """Procedura speciale (nome del catalogo `specs.json`)."""

    @field_validator("position", mode="before")
    @classmethod
    def _upper_position(cls, v: object) -> object:
        """Maiuscole."""
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("clan_id", mode="before")
    @classmethod
    def _clan_text(cls, v: object) -> object:
        """Un numero vale come testo; `0` o vuoto = nessun clan."""
        return None if v in (None, "", 0, "0") else str(v)

    @field_validator("affects")
    @classmethod
    def _check_affects(cls, v: list[str]) -> list[str]:
        """Nomi in maiuscolo."""
        return [a.strip().upper() for a in v]

    @field_validator("immunity", "resistance", "vulnerability")
    @classmethod
    def _check_resistances(cls, v: list[str]) -> list[str]:
        """Nomi di `ResistanceFlags`."""
        from pachimudeditor_adapter_pachimud.race_enums import ResistanceFlags

        return [enum_name(ResistanceFlags, a) for a in v]

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
    rent: int = Field(default=0, ge=-1)
    """Affitto al giorno; -1 = non affittabile."""
    durability: int = Field(default=-1, ge=-1)
    min_level: Optional[int] = Field(default=None, ge=1, le=70)
    max_level: Optional[int] = Field(default=None, ge=1, le=70)
    sex: str = "NEUTRAL"
    material: Optional[Literal["METAL", "MINERAL", "ORGANIC"]] = None
    spec: Optional[str] = None
    extra_flags: list[str] = []
    wear_flags: list[str] = []
    affects: dict[str, int] = {}
    extra_descriptions: list[LoaderExtraDescription] = []
    scripts: list[LoaderTrigger] = []

    @field_validator("sex")
    @classmethod
    def _check_sex(cls, value: str) -> str:
        """Nome di `Sex`."""
        return enum_name(Sex, value)

    @model_validator(mode="after")
    def _check_levels(self) -> "ObjectBaseProto":
        """`min_level` non supera `max_level`."""
        if self.min_level is not None and self.max_level is not None and self.min_level > self.max_level:
            raise ValueError("min_level non puo' superare max_level")
        return self

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
    break_chance: int = Field(default=0, ge=0, le=100)
    """Probabilita' (%) che l'arma si spezzi lanciata."""


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
    max_armor_class: Optional[int] = None
    decay_percent: int = Field(default=0, ge=0, le=100)


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
    "LIFESAVER", "FURNISHING", "PRECIOUS", "RAW_MATERIAL", "PROCESSED_MATERIAL", "CRAFTED", "MERCHANT", "MOUNT_FOOD",
)  # fmt: skip


class GenericProto(ObjectBaseProto):
    """Tipi senza valori."""

    object_type: Literal[
        "TREASURE", "WORN", "OTHER", "TRASH",
        "NOTE", "PEN", "BOAT", "TREE", "ROCK", "FOUNTAIN",
        "LIFESAVER", "FURNISHING", "PRECIOUS", "RAW_MATERIAL", "PROCESSED_MATERIAL", "CRAFTED", "MERCHANT", "MOUNT_FOOD",
    ]  # fmt: skip


class PortalProto(ObjectBaseProto):
    """Portale magico: `enter <portale>` porta alla stanza `destination`."""

    object_type: Literal["PORTAL"]
    duration: int = Field(default=-1, ge=-1)
    destination: Optional[int] = None


class BookProto(ObjectBaseProto):
    """Libro (la lingua e' dichiarata, senza comportamento)."""

    object_type: Literal["BOOK"]
    language: str = "common"


class CorpseProto(ObjectBaseProto):
    """Cadavere come tipo dell'oggetto."""

    object_type: Literal["CORPSE"]
    souls: int = Field(default=0, ge=0)


class OintmentProto(ObjectBaseProto):
    """Unguento (dichiarato, senza comportamento)."""

    object_type: Literal["OINTMENT"]
    level: int = 1
    max_uses: int = 1
    uses: int = 1
    spell: Optional[str] = None


class AlchemyProto(ObjectBaseProto):
    """Composto alchemico (dichiarato, senza comportamento)."""

    object_type: Literal["ALCHEMY"]
    applies_to: int = 0
    duration: int = 0
    effect: int = 0


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
    | PortalProto
    | BookProto
    | CorpseProto
    | OintmentProto
    | AlchemyProto
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
    "PORTAL": PortalProto,
    "BOOK": BookProto,
    "CORPSE": CorpseProto,
    "OINTMENT": OintmentProto,
    "ALCHEMY": AlchemyProto,
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
