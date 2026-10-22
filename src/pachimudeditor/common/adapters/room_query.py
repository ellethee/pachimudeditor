"""Filtri e ordinamenti sulle statistiche delle stanze (`RoomPageParams`), condivisi dagli adapter.

Gli adapter su file li applicano in memoria sui `RoomOut` (`page_rooms`); pachimud traduce in SQL gli stessi
parametri e usa qui solo `check`, `parse_order` e `match_flags` (i flag stanno in una colonna JSON): stessi risultati.
"""

from typing import Any

from pachifast.i18n import api_error
from pachifast.schemas.responses import PaginatedResponse

from pachimudeditor.common.adapters import list_query
from pachimudeditor.common.adapters.models import RoomOut, RoomPageParams
from pachimudeditor.common.enums import SectorType

RANGE_FIELDS = ("heal_rate", "mana_rate")
"""Campi numerici con filtro `min_<campo>`/`max_<campo>`."""
LEGACY_ORDER = frozenset({"id", "vnum", "name", "sector_type"})
"""Ordinamenti che gli adapter su file sapevano gia' fare senza costruire i DTO."""
_FILTERS = ("sector_type", "flag", "clan_id", "owner") + tuple(f"{b}_{f}" for f in RANGE_FIELDS for b in ("min", "max"))


def has_filters(params: RoomPageParams) -> bool:
    """`True` se la richiesta usa almeno uno dei filtri sulle statistiche."""
    return any(getattr(params, name) not in (None, [], "") for name in _FILTERS)


def parse_order(params: RoomPageParams) -> list[tuple[str, bool]]:
    """`orderBy` come `[(campo snake_case, discendente)]`; 422 se un campo non e' ammesso."""
    return list_query.parse_order(params, RoomPageParams.order_fields or [])


def check(params: RoomPageParams) -> None:
    """Validazione dei filtri: 422 `rooms.invalid_sector_type` e `rooms.invalid_range` (min > max, `field`)."""
    for value in params.sector_type or []:
        if value not in set(SectorType):
            raise api_error(422, "rooms.invalid_sector_type", loc=("query", "sectorType"), value=value)
    list_query.check_ranges(params, RANGE_FIELDS, "rooms.invalid_range")


def match_flags(flags: list[str], params: RoomPageParams) -> bool:
    """Filtro sui flag della stanza (tutti quelli richiesti, senza maiuscole)."""
    return list_query.has_flags(flags, params.flag or [])


def _match(r: RoomOut, params: RoomPageParams) -> bool:
    """Tutti i filtri sulle statistiche per un `RoomOut`."""
    if params.sector_type and int(r.sector_type) not in params.sector_type:
        return False
    if params.clan_id and r.clan_id not in params.clan_id:
        return False
    if params.owner and params.owner.lower() not in (r.owner or "").lower():
        return False
    return list_query.in_ranges(r, params, RANGE_FIELDS) and match_flags(r.flags, params)


def is_extended(params: RoomPageParams) -> bool:
    """`True` se la richiesta ha filtri nuovi o un ordinamento che richiede i DTO (altrimenti vale il percorso storico)."""
    return has_filters(params) or any(field not in LEGACY_ORDER for field, _ in parse_order(params))


def page_rooms(outs: list[RoomOut], params: RoomPageParams) -> PaginatedResponse[Any]:
    """Filtra, ordina (nulli in fondo, a parita' per vnum) e pagina dei `RoomOut` gia' filtrati per zona."""
    check(params)
    return list_query.page_filtered(
        outs, params, RoomOut, lambda r: _match(r, params), lambda r: (r.name, r.vnum), RoomPageParams.order_fields or []
    )
