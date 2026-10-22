"""Filtri e ordinamenti sulle statistiche dei mob (`MobPageParams`), condivisi dagli adapter.

Gli adapter su file li applicano in memoria sui `MobOut` (`page_mobs`); pachimud traduce in SQL gli stessi
parametri e usa qui solo `check`, `parse_order` e `match_flags` (i flag stanno in una colonna JSON): stessi risultati.
"""

from typing import Any

from pachifast.i18n import api_error
from pachifast.schemas.responses import PaginatedResponse

from pachimudeditor.common.adapters import list_query
from pachimudeditor.common.adapters.models import MobOut, MobPageParams
from pachimudeditor.common.enums import Sex

RANGE_FIELDS = (
    "level", "thac0", "armor_class", "hp_dice_count", "hp_die_size", "hp_bonus",
    "damage_dice_count", "damage_die_size", "damage_bonus", "gold", "experience", "alignment",
)  # fmt: skip
"""Campi numerici con filtro `min_<campo>`/`max_<campo>`."""
LEGACY_ORDER = frozenset({"id", "vnum", "level"})
"""Ordinamenti che gli adapter su file sapevano gia' fare senza costruire i DTO."""
_FILTERS = ("sex", "flag", "race_id", "class_id") + tuple(f"{b}_{f}" for f in RANGE_FIELDS for b in ("min", "max"))


def has_filters(params: MobPageParams) -> bool:
    """`True` se la richiesta usa almeno uno dei filtri sulle statistiche."""
    return any(getattr(params, name) not in (None, []) for name in _FILTERS)


def parse_order(params: MobPageParams) -> list[tuple[str, bool]]:
    """`orderBy` come `[(campo snake_case, discendente)]`; 422 se un campo non e' ammesso."""
    return list_query.parse_order(params, MobPageParams.order_fields or [])


def check(params: MobPageParams) -> None:
    """Validazione dei filtri: 422 `mobs.invalid_sex` e `mobs.invalid_range` (min > max, `field`)."""
    for value in params.sex or []:
        if value not in set(Sex):
            raise api_error(422, "mobs.invalid_sex", loc=("query", "sex"), value=value)
    list_query.check_ranges(params, RANGE_FIELDS, "mobs.invalid_range")


def match_flags(flags: list[str], params: MobPageParams) -> bool:
    """Filtro sui flag del mob (tutti quelli richiesti, senza maiuscole)."""
    return list_query.has_flags(flags, params.flag or [])


def _match(m: MobOut, params: MobPageParams) -> bool:
    """Tutti i filtri sulle statistiche per un `MobOut`."""
    if params.sex and int(m.sex) not in params.sex:
        return False
    if params.race_id and m.race_id not in params.race_id:
        return False
    if params.class_id and m.class_id not in params.class_id:
        return False
    return list_query.in_ranges(m, params, RANGE_FIELDS) and match_flags(m.flags, params)


def is_extended(params: MobPageParams) -> bool:
    """`True` se la richiesta ha filtri nuovi o un ordinamento che richiede i DTO (altrimenti vale il percorso storico)."""
    return has_filters(params) or any(field not in LEGACY_ORDER for field, _ in parse_order(params))


def page_mobs(outs: list[MobOut], params: MobPageParams) -> PaginatedResponse[Any]:
    """Filtra, ordina (nulli in fondo, a parita' per vnum) e pagina dei `MobOut` gia' filtrati per zona."""
    check(params)
    return list_query.page_filtered(
        outs,
        params,
        MobOut,
        lambda m: _match(m, params),
        lambda m: (m.short_description, m.keywords, m.vnum),
        MobPageParams.order_fields or [],
    )
