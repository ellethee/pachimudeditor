"""Schemi dei file YAML di zona (`definitions/zones/<Nome>/{zone,rooms,mobs,objects,resets}.yaml`).

Copie dei `Loader*` del gioco (`zone/schema`, `zone/room/schema`, `mob/schema`, `object/schema`): stessi campi, default e
validazioni (nomi di enum in maiuscolo, notazione dadi `XdY+Z`, uscite per direzione), cosi' un file valido per
l'importer del gioco lo e' anche qui e viceversa (`tests/test_equivalence.py`).
"""

import re
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Optional, TypeVar, Union

from pydantic import BaseModel, Field, field_validator, model_validator
import yaml

from pachimudeditor.common.enums import Direction, DoorFlag, ObjectType, SectorType, Sex, ZoneResetMode

EnumType = TypeVar("EnumType", bound=Enum)

_DICE_RE = re.compile(r"^\s*-?\d+d-?\d+\+-?\d+\s*$")


def validate_enum_name(enum_cls: type[EnumType], value: str) -> str:
    """Il nome (case-insensitive) di un membro di `enum_cls`, normalizzato in maiuscolo; `ValueError` se ignoto."""
    name = value.strip().upper()
    if name not in enum_cls.__members__:
        valid = ", ".join(enum_cls.__members__)
        raise ValueError(f"valore non valido {value!r} per {enum_cls.__name__}, atteso uno tra: {valid}")
    return name


def load_yaml(path: Path, schema: type[BaseModel]) -> BaseModel:
    """Legge e valida un file YAML (parser sicuro)."""
    return schema.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


# ------------------------------------------------------------------------------ zone


class LoaderZone(BaseModel):
    """`zone.yaml`."""

    zone_id: str
    vnum: int
    name: str
    builder: str
    bottom_vnum: int
    top_vnum: int
    min_level: int = 1
    max_level: int = 1
    lifespan_minutes: int = 30
    reset_mode: str = "ALWAYS"
    enabled: bool = True

    @field_validator("reset_mode")
    @classmethod
    def _check_reset_mode(cls, v: str) -> str:
        """Nome valido di `ZoneResetMode`."""
        return validate_enum_name(ZoneResetMode, v)


# ------------------------------------------------------------------------------ stanze


class LoaderExit(BaseModel):
    """Un'uscita di `rooms.yaml`."""

    target_vnum: Optional[int] = None
    description: Optional[str] = None
    keywords: Optional[str] = None
    door_flag: str = "NONE"
    is_open: bool = True
    is_locked: bool = False
    key_vnum: Optional[int] = None

    @field_validator("door_flag")
    @classmethod
    def _check_door_flag(cls, v: str) -> str:
        """Nome valido di `DoorFlag`."""
        return validate_enum_name(DoorFlag, v)


class LoaderExtraDescription(BaseModel):
    """Una extra description di stanza."""

    keywords: str
    text: str


class LoaderRoom(BaseModel):
    """Una stanza di `rooms.yaml` (uscite come dict per direzione)."""

    vnum: int
    name: str
    description: str
    sector_type: str = "INSIDE"
    flags: list[str] = []
    heal_rate: int = 100
    mana_rate: int = 100
    clan_id: Optional[str] = None
    owner: Optional[str] = None
    exits: dict[str, LoaderExit] = {}
    extra_descriptions: list[LoaderExtraDescription] = []

    @field_validator("sector_type")
    @classmethod
    def _check_sector_type(cls, v: str) -> str:
        """Nome valido di `SectorType`."""
        return validate_enum_name(SectorType, v)

    @model_validator(mode="after")
    def _check_exit_directions(self) -> "LoaderRoom":
        """Normalizza le chiavi delle uscite (nomi di `Direction`, maiuscolo)."""
        self.exits = {validate_enum_name(Direction, key): exit_ for key, exit_ in self.exits.items()}
        return self


class LoaderRoomsFile(BaseModel):
    """`rooms.yaml`."""

    rooms: list[LoaderRoom] = []


# ------------------------------------------------------------------------------ mob


class LoaderMob(BaseModel):
    """Un mob di `mobs.yaml` (dadi in notazione `XdY+Z`)."""

    vnum: int
    keywords: str
    short_description: str
    long_description: str
    detailed_description: str
    level: int
    thac0: int
    armor_class: int
    hp_dice: str
    damage_dice: str
    gold: int = 0
    experience: int = 0
    sex: str = "NEUTRAL"
    flags: list[str] = []
    alignment: int = 0
    race_id: Optional[str] = None
    class_id: Optional[str] = None
    debuff_skill_id: Optional[str] = None
    shop_id: Optional[str] = None
    quest_ids: list[str] = []
    is_banker: bool = False
    teaches_class_ids: Optional[list[str]] = None
    teaches_skill_ids: Optional[list[str]] = None

    @field_validator("hp_dice", "damage_dice")
    @classmethod
    def _check_dice(cls, v: str) -> str:
        """Notazione dadi `XdY+Z`."""
        if not _DICE_RE.match(v):
            raise ValueError(f"formato dadi non valido {v!r}, atteso 'XdY+Z' (es. '3d8+10')")
        return v.strip()

    @field_validator("sex")
    @classmethod
    def _check_sex(cls, v: str) -> str:
        """Nome valido di `Sex`."""
        return validate_enum_name(Sex, v)


class LoaderMobsFile(BaseModel):
    """`mobs.yaml`."""

    mobs: list[LoaderMob] = []


# ------------------------------------------------------------------------------ oggetti


class LoaderObject(BaseModel):
    """Un prototipo di oggetto di `objects.yaml`."""

    vnum: int
    keywords: str
    short_description: str
    long_description: str
    action_description: Optional[str] = None
    object_type: str = "OTHER"
    weight: int = 0
    cost: int = 0
    rent: int = 0
    value_0: Optional[int] = None
    value_1: Optional[int] = None
    value_2: Optional[int] = None
    value_3: Optional[int] = None
    extra_flags: list[str] = []
    wear_flags: list[str] = []
    affects: dict[str, int] = {}

    @field_validator("object_type")
    @classmethod
    def _check_object_type(cls, v: str) -> str:
        """Nome valido di `ObjectType`."""
        return validate_enum_name(ObjectType, v)


class LoaderObjectsFile(BaseModel):
    """`objects.yaml`."""

    objects: list[LoaderObject] = []


# ------------------------------------------------------------------------------ reset


class LoaderResetBase(BaseModel):
    """Campo comune a ogni reset: esegui solo se il precedente e' andato a buon fine."""

    if_flag: bool = False


class LoaderLoadMob(LoaderResetBase):
    """`LOAD_MOB`."""

    type: Literal["LOAD_MOB"]
    mob_vnum: int
    max_existing: int = 1
    room_vnum: int
    room_limit: Optional[int] = None


class LoaderLoadObject(LoaderResetBase):
    """`LOAD_OBJECT`."""

    type: Literal["LOAD_OBJECT"]
    obj_vnum: int
    max_existing: int = 1
    room_vnum: int
    room_limit: Optional[int] = None


class LoaderGiveObject(LoaderResetBase):
    """`GIVE_OBJECT`."""

    type: Literal["GIVE_OBJECT"]
    obj_vnum: int
    max_existing: int = 1


class LoaderEquipObject(LoaderResetBase):
    """`EQUIP_OBJECT`."""

    type: Literal["EQUIP_OBJECT"]
    obj_vnum: int
    max_existing: int = 1
    wear_slot: str


class LoaderPutObject(LoaderResetBase):
    """`PUT_OBJECT`."""

    type: Literal["PUT_OBJECT"]
    obj_vnum: int
    max_existing: int = 1
    container_vnum: int


class LoaderSetDoorState(LoaderResetBase):
    """`SET_DOOR_STATE`."""

    type: Literal["SET_DOOR_STATE"]
    room_vnum: int
    direction: str
    state: Literal["OPEN", "CLOSED", "LOCKED"] = "CLOSED"

    @field_validator("direction")
    @classmethod
    def _check_direction(cls, v: str) -> str:
        """Nome valido di `Direction`."""
        return validate_enum_name(Direction, v)


class LoaderRandomizeExits(LoaderResetBase):
    """`RANDOMIZE_EXITS`."""

    type: Literal["RANDOMIZE_EXITS"]
    room_vnum: int


LoaderReset = Annotated[
    Union[
        LoaderLoadMob,
        LoaderLoadObject,
        LoaderGiveObject,
        LoaderEquipObject,
        LoaderPutObject,
        LoaderSetDoorState,
        LoaderRandomizeExits,
    ],
    Field(discriminator="type"),
]


class LoaderResetsFile(BaseModel):
    """`resets.yaml`."""

    resets: list[LoaderReset] = []
