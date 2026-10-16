"""Modelli (camelCase) del flusso di conversione tra mondi: piano, voci di perdita e rapporto.

Il piano (`ConvertPlan`) dice *cosa* convertire e con quali politiche; il rapporto (`ConvertReport`) dice cosa e'
stato (o sarebbe stato, in dry-run) creato/sostituito, la tabella di rimappatura dei vnum, tutto cio' che la
conversione ha perso (`LossItem`) e i conflitti trovati. Vedi `docs/conversion.md`.
"""

from typing import Any, Literal

from pachifast.database import AliasedBaseModel
from pydantic import Field, model_validator

Severity = Literal["info", "warning", "dropped"]
"""Gravita' di una perdita: `info` (trasformazione senza perdita sostanziale), `warning` (approssimato) o `dropped`
(dato perso o elemento non convertito)."""

LossEntity = Literal["zone", "room", "exit", "extra_description", "mob", "object", "reset"]
"""Tipo di elemento a cui si riferisce una voce di perdita."""

VnumMode = Literal["keep", "offset", "shift_to"]
"""`keep` = vnum invariati; `offset` = somma `offset`; `shift_to` = primo intervallo libero del mondo di arrivo."""


class VnumPolicy(AliasedBaseModel):
    """Come cambiano i vnum nel mondo di arrivo."""

    mode: VnumMode = "keep"
    offset: int = 0
    """Solo per `mode: offset` (puo' essere negativo)."""

    @model_validator(mode="after")
    def _offset_only_with_offset_mode(self) -> "VnumPolicy":
        """`offset` diverso da 0 ha senso solo con `mode: offset`."""
        if self.mode != "offset" and self.offset:
            raise ValueError("`offset` e' ammesso solo con mode=offset")
        return self


class ConvertPlan(AliasedBaseModel):
    """Il piano di una conversione (indipendente dai mondi, che si passano a parte)."""

    zone_ids: list[int] = Field(min_length=1)
    """Id delle zone **sorgente** (come in `GET /api/zones` del mondo sorgente)."""
    vnum_policy: VnumPolicy = Field(default_factory=VnumPolicy)
    on_conflict: Literal["skip", "replace"] = "skip"
    """Zona gia' presente nel mondo di arrivo: `skip` la salta; `replace` ne svuota il contenuto e lo riscrive."""
    convert_resets: bool = True
    convert_exits: bool = True
    convert_extra_descriptions: bool = True


class LossItem(AliasedBaseModel):
    """Una cosa persa, approssimata o trasformata dalla conversione di un elemento."""

    entity: LossEntity
    vnum: int | None = None
    """Vnum **sorgente** dell'elemento (per i reset: `None`, vedi `index`)."""
    zone_vnum: int | None = None
    """Vnum della zona sorgente a cui appartiene."""
    index: int | None = None
    """Per i reset: posizione nello script sorgente."""
    field: str
    code: str
    """Codice stabile del catalogo i18n (`convert.loss.*`)."""
    params: dict[str, Any] = Field(default_factory=dict)
    severity: Severity
    message: str = ""
    """Testo tradotto (riempito dal livello API)."""


class EntityCounts(AliasedBaseModel):
    """Conteggi per tipo di elemento."""

    create: int = 0
    replace: int = 0
    """Elementi del mondo di arrivo che una zona `replace` svuota e riscrive."""
    skip: int = 0
    """Elementi sorgente non convertiti perche' la zona e' saltata/bloccata."""
    dropped: int = 0
    """Elementi sorgente scartati dalla conversione (es. record corrotto, riferimento mancante)."""


class ZoneAction(AliasedBaseModel):
    """Cosa succede a una zona sorgente."""

    source_zone_id: int
    source_vnum: int
    name: str
    action: Literal["create", "replace", "skip", "blocked"]
    target_vnum: int
    target_zone_id: int | None = None
    """Id della zona nel mondo di arrivo (gia' esistente per `replace`; valorizzato dopo la scrittura per `create`)."""
    source_bottom_vnum: int
    source_top_vnum: int
    bottom_vnum: int
    top_vnum: int
    offset: int
    counts: dict[str, int] = Field(default_factory=dict)
    """Elementi convertiti (`rooms`, `mobs`, `objects`, `exits`, `extraDescriptions`, `resets`)."""


class ConvertConflict(AliasedBaseModel):
    """Un ostacolo alla scrittura di una zona."""

    zone_vnum: int
    kind: Literal["zone_exists", "range_overlap", "vnum_taken"]
    entity: str | None = None
    vnum: int | None = None
    other_zone: str | None = None
    resolved: bool = False
    """`True` se il piano lo risolve (es. `zone_exists` con `onConflict=replace`)."""


class ReportError(AliasedBaseModel):
    """Un errore (della validazione o della scrittura) con codice stabile."""

    code: str
    params: dict[str, Any] = Field(default_factory=dict)
    message: str = ""
    zone_vnum: int | None = None


class JournalInfo(AliasedBaseModel):
    """Il giornale della conversione (se configurato)."""

    enabled: bool = False
    file: str | None = None
    """Solo il nome del file."""


class ConvertReport(AliasedBaseModel):
    """Esito (o anteprima) di una conversione."""

    dry_run: bool
    applied: bool = False
    source_world: str
    target_world: str
    source_kind: str
    target_kind: str
    converter: Literal["specific", "generic"]
    zones: list[ZoneAction] = Field(default_factory=list)
    totals: dict[str, EntityCounts] = Field(default_factory=dict)
    """Per `zones`, `rooms`, `mobs`, `objects`, `exits`, `extraDescriptions`, `resets`."""
    remap: dict[str, dict[int, int]] = Field(default_factory=dict)
    """`rooms`/`mobs`/`objects`: vnum sorgente -> vnum di arrivo (solo quelli che cambiano non e' garantito: e' completa)."""
    losses: list[LossItem] = Field(default_factory=list)
    loss_summary: dict[str, int] = Field(default_factory=dict)
    conflicts: list[ConvertConflict] = Field(default_factory=list)
    errors: list[ReportError] = Field(default_factory=list)
    rolled_back: bool = False
    rollback_errors: list[ReportError] = Field(default_factory=list)
    journal: JournalInfo = Field(default_factory=JournalInfo)
