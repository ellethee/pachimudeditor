"""DTO neutri dell'API dell'editor, condivisi da router e adapter (`common.adapters.base.WorldAdapter`).

Sono i modelli Pydantic camelCase che il frontend gia' consuma: nessun tipo SQLAlchemy.
Il campo `id` e' scelto dall'adapter (pachimud: chiave primaria della riga; adapter su file:
`id == vnum`). Le entita' principali (zona, stanza, mob, oggetto) hanno un `extra: dict` per i campi
specifici di un MUD che non fanno parte del modello neutro (pachimud lo lascia vuoto).
Le enum (`SectorType`, `Direction`, ...) sono quelle di `pachimud.*`: valori interi condivisi.
"""

from typing import Annotated, Any, Literal

from fastapi import Query
from pachifast.database import AliasedBaseModel
from pachifast.schemas.responses import PageParams
from pachimudeditor.common.enums import Sex
from pachimudeditor.common.enums import ObjectType
from pachimudeditor.common.enums import ZoneCommandType, ZoneResetMode
from pachimudeditor.common.enums import Direction, DoorFlag, SectorType
from pydantic import BeforeValidator, Field, model_validator

from pachimudeditor.common.editor.schemas import PatchModel


MAX_INT = 2**31 - 1
"""Massimo di vnum e argomenti dei reset: ben oltre ogni vnum reale, ma sotto i limiti degli INTEGER dei DB."""


class NeutralOut(AliasedBaseModel):
    """Base delle entita' in uscita: `extra` contiene i campi specifici del MUD (vuoto per pachimud)."""

    extra: dict[str, Any] = Field(default_factory=dict)


class NeutralIn(AliasedBaseModel):
    """Base delle entita' in creazione: `extra` per i campi specifici del MUD."""

    extra: dict[str, Any] = Field(default_factory=dict)


class NeutralPatch(PatchModel):
    """Base degli aggiornamenti parziali: `extra` per i campi specifici del MUD."""

    extra: dict[str, Any] | None = None


EntityKind = Literal["room", "mob", "object"]
"""Tipi di contenuto di una zona identificati da vnum."""


class ZoneOut(NeutralOut):
    """Una zona."""

    id: int
    vnum: int
    name: str
    builder: str
    bottom_vnum: int
    top_vnum: int
    min_level: int
    max_level: int
    lifespan_minutes: int
    reset_mode: ZoneResetMode
    enabled: bool


class ZoneIn(NeutralIn):
    """Crea una zona."""

    vnum: int = Field(ge=0, le=MAX_INT)
    name: str = Field(min_length=1)
    builder: str = ""
    bottom_vnum: int = Field(default=0, ge=0, le=MAX_INT)
    top_vnum: int = Field(default=0, ge=0, le=MAX_INT)
    min_level: int = Field(default=1, ge=1)
    max_level: int = Field(default=1, ge=1)
    lifespan_minutes: int = Field(default=30, ge=0)
    reset_mode: ZoneResetMode = ZoneResetMode.EMPTY
    enabled: bool = True

    @model_validator(mode="after")
    def _ranges_are_ordered(self) -> "ZoneIn":
        """`bottomVnum`/`minLevel` non possono superare i rispettivi massimi."""
        if self.bottom_vnum > self.top_vnum:
            raise ValueError("Il vnum minimo non può superare il vnum massimo.")
        if self.min_level > self.max_level:
            raise ValueError("Il livello minimo non può superare il livello massimo.")
        return self


class ZonePatch(NeutralPatch):
    """Aggiornamento parziale di una zona (nessuna colonna e' nullable: `null` esplicito = 422)."""

    vnum: int | None = Field(default=None, ge=0, le=MAX_INT)
    name: str | None = Field(default=None, min_length=1)
    builder: str | None = None
    bottom_vnum: int | None = Field(default=None, ge=0, le=MAX_INT)
    top_vnum: int | None = Field(default=None, ge=0, le=MAX_INT)
    min_level: int | None = Field(default=None, ge=1)
    max_level: int | None = Field(default=None, ge=1)
    lifespan_minutes: int | None = Field(default=None, ge=0)
    reset_mode: ZoneResetMode | None = None
    enabled: bool | None = None


class ZoneSummary(AliasedBaseModel):
    """Quanto contenuto ha una zona."""

    room_count: int
    mob_count: int
    object_count: int


class ZonePageParams(PageParams):
    """Parametri di lista delle zone: `search` su nome/builder/vnum."""

    search_fields = ["name", "builder", "vnum"]
    order_fields = ["id", "vnum", "name", "builder", "lifespan_minutes", "reset_mode", "enabled"]


class NextZoneVnum(AliasedBaseModel):
    """`GET /zones/next-vnum`: un vnum di zona libero e un range che non si sovrappone a nessun'altra."""

    vnum: int
    bottom_vnum: int
    top_vnum: int


class ZoneCloneIn(AliasedBaseModel):
    """Clona una zona: stessa configurazione, nuovo vnum/nome.

    `bottomVnum`/`topVnum` (entrambi o nessuno): range vnum della copia. Se omessi la copia nasce con
    range 0-0 ("da assegnare", ignorato da `next-vnum`) invece di duplicare quello della sorgente."""

    vnum: int = Field(ge=0, le=MAX_INT)
    name: str = Field(min_length=1)
    copy_reset_commands: bool = False
    bottom_vnum: int | None = Field(default=None, ge=0, le=MAX_INT)
    top_vnum: int | None = Field(default=None, ge=0, le=MAX_INT)

    @model_validator(mode="after")
    def _range_is_coherent(self) -> "ZoneCloneIn":
        """Il range va dato per intero e `bottomVnum` non puo' superare `topVnum`."""
        if (self.bottom_vnum is None) != (self.top_vnum is None):
            raise ValueError("Indicare sia il vnum minimo sia il vnum massimo, oppure nessuno dei due.")
        if self.bottom_vnum is not None and self.top_vnum is not None and self.bottom_vnum > self.top_vnum:
            raise ValueError("Il vnum minimo non può superare il vnum massimo.")
        return self


EXTENDED_COMMAND_TYPES: frozenset[int] = frozenset({7, 8, 9, 10})
"""Comandi di reset che esistono solo in alcuni MUD (Diku Modificato: 7 charm, 8 odio, 9 paura, 10 zona del mob)."""


def _coerce_command_type(value: Any) -> Any:
    """Gli interi 0-6 diventano `ZoneCommandType`, 7-10 restano interi (comandi propri di un MUD), il resto e' invalido."""
    if isinstance(value, int) and not isinstance(value, ZoneCommandType):
        if value in EXTENDED_COMMAND_TYPES:
            return value
        try:
            return ZoneCommandType(value)
        except ValueError:
            raise ValueError(f"tipo di comando di reset non valido: {value}") from None
    return value


ResetCommandType = Annotated[ZoneCommandType | int, BeforeValidator(_coerce_command_type)]
"""Tipo di un comando di reset: `ZoneCommandType` (M/O/G/E/P/D/R di ROM) oppure un intero >= 7 per i comandi che solo
alcuni MUD hanno (Diku Modificato: 7 charm `C`, 8 odio `H`, 9 paura `F`, 10 zona `Z`); vedi `common.adapters.rules`."""


class ResetCommandOut(AliasedBaseModel):
    """Un passo dello script di reset di una zona (ROM's M/O/G/E/P/D/R).

    Il significato di `arg1`..`arg4`/`argStr` dipende da `commandType` — vedi il
    docstring di `ZoneResetCommand` nel modello — e sono sempre **vnum**, mai id
    interni di riga, per restare stabili tra un import YAML e l'altro."""

    id: int
    zone_id: int
    order_index: int
    command_type: ResetCommandType
    if_flag: bool
    arg1: int | None
    arg2: int | None
    arg3: int | None
    arg4: int | None
    arg_str: str | None
    if_value: int | None = None
    """`if_flag` come intero, per i MUD in cui non e' un booleano (Diku Modificato: `> 0` condizionato, `<= 0` sempre, es. -5)."""
    comment: str | None = None
    """Commento della riga (per i MUD che lo conservano; pachimud: None)."""
    extra: dict[str, Any] = Field(default_factory=dict)


class ResetCommandIn(AliasedBaseModel):
    """Un passo dello script come inviato dall'editor (l'ordine è la posizione nella lista).

    Validato per `commandType`: argomenti obbligatori presenti, nessun valore negativo, direzione 0-5 e
    stato porta OPEN/CLOSED/LOCKED (senza distinzione maiuscole/minuscole, salvato com'e') per `SET_DOOR_STATE`, `argStr` solo dove ha significato (slot di
    `EQUIP_OBJECT`, stato di `SET_DOOR_STATE`). Vedi `apps.zones.reset_script`."""

    command_type: ResetCommandType
    if_flag: bool = False
    arg1: int | None = Field(default=None, ge=0, le=MAX_INT)
    arg2: int | None = Field(default=None, ge=0, le=MAX_INT)
    arg3: int | None = Field(default=None, ge=0, le=MAX_INT)
    arg4: int | None = Field(default=None, ge=0, le=MAX_INT)
    arg_str: str | None = None
    if_value: int | None = None
    """Se presente prevale su `ifFlag` (MUD con `if_flag` intero)."""
    comment: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _coherent_with_type(self) -> "ResetCommandIn":
        """Rifiuta (422) i comandi con argomenti mancanti o non ammessi per il proprio tipo."""
        from pachimudeditor.common.adapters.rules import first_structural_message

        message = first_structural_message(
            self.command_type, arg1=self.arg1, arg2=self.arg2, arg3=self.arg3, arg4=self.arg4, arg_str=self.arg_str
        )
        if message:
            raise ValueError(message)
        return self


class ResetDraftScriptIn(AliasedBaseModel):
    """Script da validare senza salvarlo: nessun vincolo per comando (li riporta `validate`)."""

    commands: list[ResetCommandDraft]


class ResetScriptIn(AliasedBaseModel):
    """Lo script di reset intero, sostituisce quello salvato."""

    commands: list[ResetCommandIn]


class ResetCommandDraft(AliasedBaseModel):
    """Un comando di reset come arriva al validatore: nessun vincolo, i problemi vengono riportati."""

    command_type: ResetCommandType
    if_flag: bool = False
    arg1: int | None = None
    arg2: int | None = None
    arg3: int | None = None
    arg4: int | None = None
    arg_str: str | None = None
    if_value: int | None = None
    comment: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ResetIssue(AliasedBaseModel):
    """Un problema del comando in posizione `index` (0-based) dello script."""

    index: int
    severity: Literal["error", "warning"]
    code: str
    params: dict[str, Any]
    message: str


class ResetValidation(AliasedBaseModel):
    """Esito di `POST /zones/{id}/reset-commands/validate`: `ok` e' vero se non ci sono errori."""

    ok: bool
    issues: list[ResetIssue] = Field(default_factory=list)


class ExitOut(AliasedBaseModel):
    """Un'uscita, con vnum/nome della destinazione risolti quando presente."""

    id: int
    room_id: int
    direction: Direction
    description: str | None
    keywords: str | None
    door_flag: DoorFlag
    is_open: bool
    is_locked: bool
    key_vnum: int | None
    target_room_id: int | None
    target_room_vnum: int | None = None
    target_room_name: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    """Dati propri del MUD (Diku Modificato: `exitInfo` grezzo, `openCmd`); pachimud: vuoto."""


class ExitIn(AliasedBaseModel):
    """Crea un'uscita da una stanza (una per direzione)."""

    direction: Direction
    description: str | None = None
    keywords: str | None = None
    door_flag: DoorFlag = DoorFlag.NONE
    is_open: bool = True
    is_locked: bool = False
    key_vnum: int | None = Field(default=None, ge=0, le=MAX_INT)
    target_room_id: int | None = None


class ExitPatch(PatchModel):
    """Aggiornamento parziale di un'uscita (`null` ammesso solo su descrizione, parole chiave, chiave e destinazione)."""

    nullable_fields = frozenset({"description", "keywords", "key_vnum", "target_room_id"})

    direction: Direction | None = None
    description: str | None = None
    keywords: str | None = None
    door_flag: DoorFlag | None = None
    is_open: bool | None = None
    is_locked: bool | None = None
    key_vnum: int | None = Field(default=None, ge=0, le=MAX_INT)
    target_room_id: int | None = None
    extra: dict[str, Any] | None = None
    """Dati propri del MUD; pachimud li rifiuta (422 `world.extra_unsupported`)."""


class ExtraDescriptionOut(AliasedBaseModel):
    """Una voce "guarda <parole chiave>" della stanza."""

    id: int
    room_id: int
    keywords: str
    text: str


class ExtraDescriptionIn(AliasedBaseModel):
    """Crea un'extra description."""

    keywords: str = Field(min_length=1)
    text: str = Field(min_length=1)


class ExtraDescriptionPatch(PatchModel):
    """Aggiornamento parziale di un'extra description."""

    keywords: str | None = Field(default=None, min_length=1)
    text: str | None = Field(default=None, min_length=1)


class RoomOut(NeutralOut):
    """Una stanza (senza uscite/extra description: vedi `RoomDetail`)."""

    id: int
    vnum: int
    zone_id: int
    name: str
    description: str
    sector_type: SectorType
    flags: list[str]
    heal_rate: int
    mana_rate: int
    clan_id: str | None
    owner: str | None


class RoomDetail(RoomOut):
    """Una stanza completa di uscite ed extra description, per il dialog di modifica."""

    exits: list[ExitOut]
    extra_descriptions: list[ExtraDescriptionOut]


class RoomIn(NeutralIn):
    """Crea una stanza."""

    vnum: int = Field(ge=0, le=MAX_INT)
    zone_id: int
    name: str = Field(min_length=1)
    description: str = ""
    sector_type: SectorType = SectorType.INSIDE
    flags: list[str] = []
    heal_rate: int = Field(default=100, ge=0)
    mana_rate: int = Field(default=100, ge=0)
    clan_id: str | None = None
    owner: str | None = None


class GraphNode(AliasedBaseModel):
    """Una stanza sul canvas della mappa, con la posizione calcolata dal server."""

    id: int
    vnum: int
    name: str
    sector_type: SectorType
    flags: list[str]
    x: float
    y: float
    dangling_exits: int
    """Numero di uscite della stanza senza destinazione (`targetRoomId` nullo)."""


class GraphEdge(AliasedBaseModel):
    """Una o due uscite tra due stanze (`twoWay`: l'uscita di ritorno esiste nella direzione opposta)."""

    id: int
    from_room_id: int
    to_room_id: int
    direction: Direction
    door_flag: DoorFlag
    two_way: bool
    reverse_exit_id: int | None = None


class RoomGraph(AliasedBaseModel):
    """Nodi e archi del grafo delle stanze di una zona."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]


class RoomPatch(NeutralPatch):
    """Aggiornamento parziale di una stanza (`null` esplicito ammesso solo su `clanId` e `owner`)."""

    nullable_fields = frozenset({"clan_id", "owner"})

    vnum: int | None = Field(default=None, ge=0, le=MAX_INT)
    zone_id: int | None = None
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    sector_type: SectorType | None = None
    flags: list[str] | None = None
    heal_rate: int | None = Field(default=None, ge=0)
    mana_rate: int | None = Field(default=None, ge=0)
    clan_id: str | None = None
    owner: str | None = None


class RoomPageParams(PageParams):
    """Parametri di lista delle stanze: `search` su nome/vnum, filtro esatto `zoneId`."""

    search_fields = ["name", "vnum"]
    order_fields = ["id", "vnum", "name", "sector_type"]
    zone_id: int | None = Query(None)


class RoomCloneIn(AliasedBaseModel):
    """Clona una stanza: stessi campi (non le uscite — diventerebbero collegamenti a senso
    unico verso gli stessi vicini, non utili), stesso nuovo vnum, extra description copiate."""

    vnum: int = Field(ge=0, le=MAX_INT)
    name: str | None = None


class MobOut(NeutralOut):
    """Un mob prototype."""

    id: int
    vnum: int
    zone_id: int
    keywords: str
    short_description: str
    long_description: str
    detailed_description: str
    level: int
    thac0: int
    armor_class: int
    hp_dice_count: int
    hp_die_size: int
    hp_bonus: int
    damage_dice_count: int
    damage_die_size: int
    damage_bonus: int
    gold: int
    experience: int
    sex: Sex
    flags: list[str]
    race_id: str | None
    class_id: str | None
    alignment: int
    debuff_skill_id: str | None
    shop_id: str | None
    quest_ids: list[str]
    is_banker: bool
    teaches_class_ids: list[str] | None
    teaches_skill_ids: list[str] | None


class MobIn(NeutralIn):
    """Crea un mob prototype."""

    vnum: int = Field(ge=0, le=MAX_INT)
    zone_id: int
    keywords: str = Field(min_length=1)
    short_description: str = Field(min_length=1)
    long_description: str = ""
    detailed_description: str = ""
    level: int = Field(default=1, ge=0)
    thac0: int = 20
    armor_class: int = 0
    hp_dice_count: int = Field(default=1, ge=1)
    hp_die_size: int = Field(default=8, ge=1)
    hp_bonus: int = 0
    damage_dice_count: int = Field(default=1, ge=1)
    damage_die_size: int = Field(default=4, ge=1)
    damage_bonus: int = 0
    gold: int = Field(default=0, ge=0)
    experience: int = Field(default=0, ge=0)
    sex: Sex = Sex.NEUTRAL
    flags: list[str] = []
    race_id: str | None = None
    class_id: str | None = None
    alignment: int = Field(default=0, ge=-1000, le=1000)
    debuff_skill_id: str | None = None
    shop_id: str | None = None
    quest_ids: list[str] = []
    is_banker: bool = False
    teaches_class_ids: list[str] | None = None
    teaches_skill_ids: list[str] | None = None


class MobPatch(NeutralPatch):
    """Aggiornamento parziale di un mob prototype (`null` esplicito ammesso solo sui campi opzionali)."""

    nullable_fields = frozenset({"race_id", "class_id", "debuff_skill_id", "shop_id", "teaches_class_ids", "teaches_skill_ids"})

    vnum: int | None = Field(default=None, ge=0, le=MAX_INT)
    zone_id: int | None = None
    keywords: str | None = Field(default=None, min_length=1)
    short_description: str | None = Field(default=None, min_length=1)
    long_description: str | None = None
    detailed_description: str | None = None
    level: int | None = Field(default=None, ge=0)
    thac0: int | None = None
    armor_class: int | None = None
    hp_dice_count: int | None = Field(default=None, ge=1)
    hp_die_size: int | None = Field(default=None, ge=1)
    hp_bonus: int | None = None
    damage_dice_count: int | None = Field(default=None, ge=1)
    damage_die_size: int | None = Field(default=None, ge=1)
    damage_bonus: int | None = None
    gold: int | None = Field(default=None, ge=0)
    experience: int | None = Field(default=None, ge=0)
    sex: Sex | None = None
    flags: list[str] | None = None
    race_id: str | None = None
    class_id: str | None = None
    alignment: int | None = Field(default=None, ge=-1000, le=1000)
    debuff_skill_id: str | None = None
    shop_id: str | None = None
    quest_ids: list[str] | None = None
    is_banker: bool | None = None
    teaches_class_ids: list[str] | None = None
    teaches_skill_ids: list[str] | None = None


class MobPageParams(PageParams):
    """Parametri di lista dei mob: `search` su descrizione/keywords/vnum, filtro esatto `zoneId`."""

    search_fields = ["short_description", "keywords", "vnum"]
    order_fields = ["id", "vnum", "level"]
    zone_id: int | None = Query(None)


class ObjectOut(NeutralOut):
    """Un object prototype."""

    id: int
    vnum: int
    zone_id: int
    keywords: str
    short_description: str
    long_description: str
    action_description: str | None
    object_type: ObjectType
    weight: int
    cost: int
    rent: int
    value_0: int | None
    value_1: int | None
    value_2: int | None
    value_3: int | None
    extra_flags: list[str]
    wear_flags: list[str]
    affects: dict[str, int]


class ObjectIn(NeutralIn):
    """Crea un object prototype."""

    vnum: int = Field(ge=0, le=MAX_INT)
    zone_id: int
    keywords: str = Field(min_length=1)
    short_description: str = Field(min_length=1)
    long_description: str = ""
    action_description: str | None = None
    object_type: ObjectType = ObjectType.OTHER
    weight: int = Field(default=0, ge=0)
    cost: int = Field(default=0, ge=0)
    rent: int = Field(default=0, ge=0)
    value_0: int | None = None
    value_1: int | None = None
    value_2: int | None = None
    value_3: int | None = None
    extra_flags: list[str] = []
    wear_flags: list[str] = []
    affects: dict[str, int] = {}


class ObjectPatch(NeutralPatch):
    """Aggiornamento parziale di un object prototype (`null` esplicito ammesso solo sui campi opzionali)."""

    nullable_fields = frozenset({"action_description", "value_0", "value_1", "value_2", "value_3"})

    vnum: int | None = Field(default=None, ge=0, le=MAX_INT)
    zone_id: int | None = None
    keywords: str | None = Field(default=None, min_length=1)
    short_description: str | None = Field(default=None, min_length=1)
    long_description: str | None = None
    action_description: str | None = None
    object_type: ObjectType | None = None
    weight: int | None = Field(default=None, ge=0)
    cost: int | None = Field(default=None, ge=0)
    rent: int | None = Field(default=None, ge=0)
    value_0: int | None = None
    value_1: int | None = None
    value_2: int | None = None
    value_3: int | None = None
    extra_flags: list[str] | None = None
    wear_flags: list[str] | None = None
    affects: dict[str, int] | None = None


class ObjectPageParams(PageParams):
    """Parametri di lista degli oggetti: `search` su descrizione/keywords/vnum, filtro esatto `zoneId`."""

    search_fields = ["short_description", "keywords", "vnum"]
    order_fields = ["id", "vnum", "object_type"]
    zone_id: int | None = Query(None)


class Option(AliasedBaseModel):
    """Una opzione di `<select>`. `value` e' l'intero effettivamente scritto sul campo
    (gli IntEnum sono serializzati come int, non come nome): il frontend usa lo stesso valore
    sia per popolare la select sia per inviarlo."""

    value: int
    label: str


class ContentRef(AliasedBaseModel):
    """Un riferimento a un contenuto YAML (razza/classe): id interno + nome leggibile."""

    id: str
    name: str


class ResetUsage(AliasedBaseModel):
    """Un riferimento al vnum cercato: un comando di reset (`source == "reset"`) o, per gli
    oggetti, la chiave di un'uscita (`source == "exit_key"`, `zone_id` e' quella della stanza)."""

    zone_id: int
    zone_name: str
    reset_command_id: int | None = None
    order_index: int | None = None
    command_type: ResetCommandType | None = None
    source: Literal["reset", "exit_key"] = "reset"
    exit_id: int | None = None
    room_id: int | None = None
    room_vnum: int | None = None


class VnumChange(AliasedBaseModel):
    """Cosa succederebbe a un elemento: `create`, `update` o `unchanged`."""

    vnum: int
    name: str
    action: str


class KindDiff(AliasedBaseModel):
    """Riepilogo per tipo di contenuto (stanze, mob, oggetti)."""

    create: int = 0
    update: int = 0
    unchanged: int = 0
    items: list[VnumChange] = []
    kept_not_in_file: list[int] = []
    """Vnum presenti nella zona nel DB ma non nei file: l'import non li cancella mai."""


class ResetDiff(AliasedBaseModel):
    """I reset sono sostituiti per intero: conteggi e se il contenuto cambia."""

    in_file: int
    in_db: int
    changed: bool


class ImportWarning(AliasedBaseModel):
    """Una segnalazione non bloccante: `code` + `params` (tradotti dal frontend)."""

    code: str
    params: dict[str, Any] = {}


class Conflict(AliasedBaseModel):
    """Un vnum del file che nel DB appartiene a un'altra zona: l'import vero e' bloccato."""

    kind: str
    vnum: int
    zone_vnum: int
    zone_name: str


class ImportPreview(AliasedBaseModel):
    """Esito dell'anteprima (e, con `applied`, dell'import eseguito)."""

    zone: VnumChange
    rooms: KindDiff
    mobs: KindDiff
    objects: KindDiff
    resets: ResetDiff
    warnings: list[ImportWarning] = []
    conflicts: list[Conflict] = []
    applied: bool = False


class ZoneBundle(AliasedBaseModel):
    """I cinque file YAML di una zona, come testo."""

    zone_vnum: int
    zone_name: str
    folder: str
    files: dict[str, str]
    warnings: list[str] = []
    """Eventuali problemi di validazione dei file generati (dati incoerenti nel DB)."""
