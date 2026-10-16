"""Schemi dell'API di conversione tra mondi (camelCase)."""

from pachifast.database import AliasedBaseModel
from pydantic import Field

from pachimudeditor.common.adapters.convert.models import ConvertPlan


class ConvertRequest(ConvertPlan):
    """Corpo di `POST /preview` e `POST /run`: i mondi (per id, non da `X-World`), il piano e le sicurezze."""

    source_world: str = Field(min_length=1)
    target_world: str = Field(min_length=1)
    dry_run: bool = True
    """`POST /run` scrive solo con `dryRun=false` **e** `confirm=true`; `/preview` e' sempre un dry-run."""
    confirm: bool = False


class WorldRef(AliasedBaseModel):
    """Un mondo configurato, come lo vede la pagina di conversione."""

    id: str
    kind: str
    name: str
    read_only: bool


class PairInfo(AliasedBaseModel):
    """Una coppia ordinata (sorgente, arrivo) e se si puo' convertire."""

    source: str
    target: str
    source_kind: str
    target_kind: str
    converter: str
    """`specific` (regole proprie della coppia) oppure `generic` (nucleo copiato, `extra` scartato)."""
    allowed: bool
    reason: str | None = None
    """Se non ammessa: `same_world` o `target_read_only`."""


class PairsResponse(AliasedBaseModel):
    """`GET /pairs`."""

    worlds: list[WorldRef]
    pairs: list[PairInfo]
    journal_enabled: bool
