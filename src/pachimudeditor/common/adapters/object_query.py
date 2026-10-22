"""Filtri e ordinamenti sulle statistiche degli oggetti (`ObjectPageParams`), condivisi dagli adapter.

Gli adapter su file li applicano in memoria sui `ObjectOut` (`page_objects`); pachimud traduce in SQL gli stessi
parametri e usa qui solo `check`, `parse_order` e `match_json` (flag/affect stanno in colonne JSON): stessi risultati.
"""

import re
from typing import Any

from pachifast.errors import InvalidOrderByError
from pachifast.schemas.responses import PaginatedResponse
from pachifast.i18n import api_error

from pachimudeditor.common.adapters.models import ObjectOut, ObjectPageParams
from pachimudeditor.common.adapters.paging import make_page, paginate_list
from pachimudeditor.common.enums import ObjectType

RANGE_FIELDS = ("weight", "cost", "rent", "value_0", "value_1", "value_2", "value_3")
"""Campi numerici con filtro `min_<campo>`/`max_<campo>`."""
LEGACY_ORDER = frozenset({"id", "vnum", "object_type"})
"""Ordinamenti che gli adapter su file sapevano gia' fare senza costruire i DTO."""
_FILTERS = ("object_type", "wear_flag", "extra_flag", "affect", "min_affect") + tuple(
    f"{b}_{f}" for f in RANGE_FIELDS for b in ("min", "max")
)


def has_filters(params: ObjectPageParams) -> bool:
    """`True` se la richiesta usa almeno uno dei filtri sulle statistiche."""
    return any(getattr(params, name) not in (None, []) for name in _FILTERS)


def parse_order(params: ObjectPageParams) -> list[tuple[str, bool]]:
    """`orderBy` come `[(campo snake_case, discendente)]` (`value0` e `value_0` equivalenti); 422 se un campo non e' ammesso."""
    out: list[tuple[str, bool]] = []
    for part in (p.strip() for p in (params.orderBy or "").split(",")):
        if not part:
            continue
        name = part.lstrip("-")
        field = (
            name if name in ObjectPageParams.order_fields else re.sub(r"(?<=\D)(?=\d)", "_", re.sub(r"(?<!^)(?=[A-Z])", "_", name)).lower()
        )
        if field not in (ObjectPageParams.order_fields or []):
            raise InvalidOrderByError(name)
        out.append((field, part.startswith("-")))
    return out


def check(params: ObjectPageParams) -> None:
    """Validazione dei filtri: 422 `objects.invalid_object_type`, `objects.invalid_range` (min > max, `field`),
    `objects.affect_required` (`minAffect` senza `affect`)."""
    for value in params.object_type or []:
        if value not in set(ObjectType):
            raise api_error(422, "objects.invalid_object_type", loc=("query", "objectType"), value=value)
    for field in RANGE_FIELDS:
        low, high = getattr(params, f"min_{field}"), getattr(params, f"max_{field}")
        if low is not None and high is not None and low > high:
            raise api_error(422, "objects.invalid_range", loc=("query", f"min_{field}"), field=field, min=low, max=high)
    if params.min_affect is not None and not params.affect:
        raise api_error(422, "objects.affect_required", loc=("query", "minAffect"))


def match_json(extra_flags: list[str], wear_flags: list[str], affects: dict[str, int], params: ObjectPageParams) -> bool:
    """Filtri su flag extra/indossabilita' (AND, senza maiuscole) e affect (presente, con `minAffect` opzionale)."""
    extra = {f.lower() for f in extra_flags}
    wear = {f.lower() for f in wear_flags}
    if not all(f.lower() in extra for f in params.extra_flag or []):
        return False
    if not all(f.lower() in wear for f in params.wear_flag or []):
        return False
    if params.affect:
        value = next((v for k, v in affects.items() if k.lower() == params.affect.lower()), None)
        if value is None or (params.min_affect is not None and value < params.min_affect):
            return False
    return True


def needs_json(params: ObjectPageParams) -> bool:
    """`True` se servono le colonne JSON (flag/affect)."""
    return bool(params.extra_flag or params.wear_flag or params.affect)


def _match(o: ObjectOut, params: ObjectPageParams) -> bool:
    """Tutti i filtri sulle statistiche per un `ObjectOut`."""
    if params.object_type and int(o.object_type) not in params.object_type:
        return False
    for field in RANGE_FIELDS:
        low, high = getattr(params, f"min_{field}"), getattr(params, f"max_{field}")
        if low is None and high is None:
            continue
        value = getattr(o, field)
        if value is None or (low is not None and value < low) or (high is not None and value > high):
            return False
    return match_json(o.extra_flags, o.wear_flags, o.affects, params)


def is_extended(params: ObjectPageParams) -> bool:
    """`True` se la richiesta ha filtri nuovi o un ordinamento che richiede i DTO (altrimenti vale il percorso storico)."""
    return has_filters(params) or any(field not in LEGACY_ORDER for field, _ in parse_order(params))


def page_objects(outs: list[ObjectOut], params: ObjectPageParams) -> PaginatedResponse[Any]:
    """Filtra (statistiche + ricerca), ordina (nulli in fondo, a parita' per vnum) e pagina dei `ObjectOut` gia' filtrati per zona."""
    check(params)
    order = ",".join(("-" if desc else "") + field for field, desc in parse_order(params))
    window = params.model_copy(update={"orderBy": order or None})
    kept = sorted((o for o in outs if _match(o, params)), key=lambda o: o.vnum)
    items, total = paginate_list(
        kept, window, lambda o: (o.short_description, o.keywords, o.vnum), lambda o, f: o.vnum if f == "id" else getattr(o, f),
        ObjectPageParams.order_fields or [],
    )  # fmt: skip
    return make_page(ObjectOut, items, total, params)
