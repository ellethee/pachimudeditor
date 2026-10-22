"""Pezzi comuni dei filtri e ordinamenti sulle statistiche delle liste (mob, stanze), condivisi dagli adapter.

`mob_query` e `room_query` li compongono: gli adapter su file applicano i filtri in memoria sui DTO (`page_filtered`),
pachimud li traduce in SQL e usa qui solo `parse_order`, `check_ranges` e `has_flags`: stessi risultati.
"""

import re
from collections.abc import Callable, Iterable
from typing import Any

from pachifast.errors import InvalidOrderByError
from pachifast.i18n import api_error
from pachifast.schemas.responses import PageParams, PaginatedResponse
from pachifast.utils.helpers import to_snake

from pachimudeditor.common.adapters.paging import make_page, paginate_list


def parse_order(params: PageParams, order_fields: Iterable[str]) -> list[tuple[str, bool]]:
    """`orderBy` come `[(campo snake_case, discendente)]` (`thac0`/`value_0` con o senza `_`); 422 se un campo non e' ammesso."""
    allowed = set(order_fields)
    out: list[tuple[str, bool]] = []
    for part in (p.strip() for p in (params.orderBy or "").split(",")):
        if not part:
            continue
        name = part.lstrip("-")
        snake = to_snake(name)
        candidates = (name, snake, re.sub(r"(?<=\D)(?=\d)", "_", snake))
        field = next((c for c in candidates if c in allowed), None)
        if field is None:
            raise InvalidOrderByError(name)
        out.append((field, part.startswith("-")))
    return out


def check_ranges(params: Any, fields: Iterable[str], code: str) -> None:
    """422 `<code>` (`mobs.invalid_range`, ...) se un `min_<campo>` supera il `max_<campo>` (`field`, `min`, `max` nel messaggio)."""
    for field in fields:
        low, high = getattr(params, f"min_{field}"), getattr(params, f"max_{field}")
        if low is not None and high is not None and low > high:
            raise api_error(422, code, loc=("query", f"min_{field}"), field=field, min=low, max=high)


def in_ranges(item: Any, params: Any, fields: Iterable[str]) -> bool:
    """`True` se i valori di `item` rispettano gli intervalli richiesti (un valore nullo non ne soddisfa uno)."""
    for field in fields:
        low, high = getattr(params, f"min_{field}"), getattr(params, f"max_{field}")
        if low is None and high is None:
            continue
        value = getattr(item, field)
        if value is None or (low is not None and value < low) or (high is not None and value > high):
            return False
    return True


def has_flags(flags: Iterable[str], wanted: Iterable[str]) -> bool:
    """`True` se `flags` contiene tutti i nomi di `wanted` (AND, senza maiuscole)."""
    have = {f.lower() for f in flags}
    return all(w.lower() in have for w in wanted)


def page_filtered(
    outs: list[Any],
    params: Any,
    dto: type[Any],
    match: Callable[[Any], bool],
    text_of: Callable[[Any], Iterable[Any]],
    order_fields: Iterable[str],
) -> PaginatedResponse[Any]:
    """Filtra (`match` + ricerca), ordina (nulli in fondo, a parita' per vnum) e pagina dei DTO gia' filtrati per zona."""
    order = ",".join(("-" if desc else "") + field for field, desc in parse_order(params, order_fields))
    window = params.model_copy(update={"orderBy": order or None})
    kept = sorted((o for o in outs if match(o)), key=lambda o: o.vnum)
    items, total = paginate_list(kept, window, text_of, lambda o, f: o.vnum if f == "id" else getattr(o, f), order_fields)
    return make_page(dto, items, total, params)
