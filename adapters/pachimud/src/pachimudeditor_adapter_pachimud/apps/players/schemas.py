"""Schemi di richiesta/risposta dell'app players (account, personaggi, inventario)."""

from datetime import datetime

from pachifast.database import AliasedBaseModel
from pydantic import Field, field_validator

from pachimudeditor.sdk import PatchModel
from pachimudeditor.common.enums import ObjectType, Position, Sex

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
"""Controllo minimale di un indirizzo email (niente dipendenza da email-validator)."""


def _clean_email(value: str | None) -> str | None:
    """Email ripulita dagli spazi; stringa vuota -> `None`."""
    if value is None:
        return None
    value = value.strip()
    return value or None


class AccountOut(AliasedBaseModel):
    """Un account di gioco. L'hash della password non e' MAI esposto."""

    id: int
    username: str
    email: str | None
    created_at: datetime
    last_login_at: datetime | None
    is_banned: bool
    character_count: int = 0


class AccountIn(AliasedBaseModel):
    """Crea un account; la password in chiaro viene hashata con Argon2id."""

    username: str = Field(min_length=3, max_length=32, pattern=r"^\S+$")
    password: str = Field(min_length=8, max_length=128)
    email: str | None = Field(default=None, max_length=255, pattern=None)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        """Normalizza e valida l'email (opzionale)."""
        import re

        value = _clean_email(value)
        if value is not None and not re.match(EMAIL_PATTERN, value):
            raise ValueError("Indirizzo email non valido.")
        return value


class AccountPatch(PatchModel):
    """Modifica di un account: solo l'email (`null` o stringa vuota = rimuovi)."""

    nullable_fields = frozenset({"email"})

    email: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        """Normalizza e valida l'email."""
        import re

        value = _clean_email(value)
        if value is not None and not re.match(EMAIL_PATTERN, value):
            raise ValueError("Indirizzo email non valido.")
        return value


class PasswordIn(AliasedBaseModel):
    """Nuova password in chiaro per un account."""

    password: str = Field(min_length=8, max_length=128)


class CharacterSummary(AliasedBaseModel):
    """Riga della lista personaggi."""

    id: int
    account_id: int
    account_username: str | None = None
    name: str
    level: int
    class_id: str
    race_id: str
    sex: Sex
    gold: int
    hit_points_current: int
    hit_points_max: int
    current_room_id: int | None
    current_room_vnum: int | None = None
    current_room_name: str | None = None
    created_at: datetime
    last_played_at: datetime | None


class CharacterDetail(CharacterSummary):
    """Scheda completa di un personaggio (campi persistiti + contesto di lookup)."""

    experience: int
    mana_current: int
    mana_max: int
    strength: int
    strength_percentile: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int
    practices: int
    alignment: int
    position: Position
    hunger: int
    thirst: int
    drunk: int
    poison_ticks: int
    wimpy_level: int
    is_player_killer: bool
    title: str
    quest_points: int
    bank_gold: int
    known_skill_ids: list[str]
    preferences: list[str]
    active_quest_ids: list[str]
    completed_quest_ids: list[str]
    skill_percentages: dict[str, int]
    quest_progress: dict[str, int]
    item_count: int = 0

    @field_validator("position", mode="before")
    @classmethod
    def _position_name(cls, value: object) -> object:
        """La colonna del gioco salva il NOME della posizione (`"STANDING"`): lo si traduce nell'enum."""
        return Position[value.upper()] if isinstance(value, str) and value.upper() in Position.__members__ else value


class CharacterPatch(PatchModel):
    """Aggiornamento parziale di un personaggio. Account, stanza, classe e razza sono validati."""

    nullable_fields = frozenset({"current_room_id"})

    account_id: int | None = None
    name: str | None = Field(default=None, min_length=2, max_length=32, pattern=r"^\S+$")
    level: int | None = Field(default=None, ge=1)
    experience: int | None = Field(default=None, ge=0)
    hit_points_current: int | None = None
    hit_points_max: int | None = Field(default=None, ge=1)
    mana_current: int | None = None
    mana_max: int | None = Field(default=None, ge=0)
    gold: int | None = Field(default=None, ge=0)
    bank_gold: int | None = Field(default=None, ge=0)
    current_room_id: int | None = None
    sex: Sex | None = None
    class_id: str | None = Field(default=None, min_length=1)
    race_id: str | None = Field(default=None, min_length=1)
    strength: int | None = Field(default=None, ge=1, le=25)
    strength_percentile: int | None = Field(default=None, ge=0, le=100)
    dexterity: int | None = Field(default=None, ge=1, le=25)
    constitution: int | None = Field(default=None, ge=1, le=25)
    intelligence: int | None = Field(default=None, ge=1, le=25)
    wisdom: int | None = Field(default=None, ge=1, le=25)
    charisma: int | None = Field(default=None, ge=1, le=25)
    practices: int | None = Field(default=None, ge=0)
    alignment: int | None = Field(default=None, ge=-1000, le=1000)
    position: Position | None = None
    hunger: int | None = Field(default=None, ge=-1)
    thirst: int | None = Field(default=None, ge=-1)
    drunk: int | None = Field(default=None, ge=-1)
    poison_ticks: int | None = Field(default=None, ge=0)
    wimpy_level: int | None = Field(default=None, ge=0, le=500)
    is_player_killer: bool | None = None
    title: str | None = Field(default=None, max_length=80)
    quest_points: int | None = Field(default=None, ge=0)
    known_skill_ids: list[str] | None = None
    preferences: list[str] | None = None
    active_quest_ids: list[str] | None = None
    completed_quest_ids: list[str] | None = None


class TeleportIn(AliasedBaseModel):
    """Destinazione del teletrasporto: id (non vnum) della stanza."""

    room_id: int


class ItemOut(AliasedBaseModel):
    """Un'istanza di oggetto posseduta (direttamente o in un contenitore) da un personaggio."""

    id: int
    prototype_id: int
    vnum: int
    keywords: str
    short_description: str
    object_type: ObjectType
    equipped_slot: str | None
    container_instance_id: int | None
    wear_flags: list[str]
    liquid_amount: int | None
    charges: int | None


class ItemIn(AliasedBaseModel):
    """Aggiunge all'inventario un'istanza di un prototipo (per `prototypeId` oppure per `vnum`)."""

    prototype_id: int | None = None
    vnum: int | None = None
    equipped_slot: str | None = Field(default=None, max_length=32)


class ItemPatch(PatchModel):
    """Equipaggia (slot) o rimuove dall'equipaggiamento (`null`) un oggetto portato direttamente."""

    nullable_fields = frozenset({"equipped_slot"})

    equipped_slot: str | None = Field(default=None, max_length=32)


class OptionOut(AliasedBaseModel):
    """Opzione di select."""

    value: int
    label: str


class RefOut(AliasedBaseModel):
    """Riferimento a un contenuto YAML (razza/classe)."""

    id: str
    name: str


class LookupsOut(AliasedBaseModel):
    """Elenchi per i form: enum del personaggio e contenuti validi per classe/razza."""

    sex: list[OptionOut]
    position: list[OptionOut]
    races: list[RefOut]
    classes: list[RefOut]
