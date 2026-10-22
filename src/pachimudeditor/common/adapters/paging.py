"""Paginazione in memoria per gli adapter su file: ricerca, ordinamento (`orderBy` come pachifast) e finestra."""

from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from pachifast.errors import InvalidOrderByError
from pachifast.schemas.responses import PageParams, PaginatedResponse
from pachifast.utils.helpers import to_snake

T = TypeVar("T")


def paginate_list(
    items: list[T],
    params: PageParams,
    text_of: Callable[[T], Iterable[Any]],
    key_of: Callable[[T, str], Any],
    order_fields: Iterable[str],
) -> tuple[list[T], int]:
    """`(elementi della pagina, totale)`: ricerca (substring senza maiuscole su `text_of`), ordinamento (`orderBy`
    come pachifast: `a,-b`, 422 se il campo non e' ammesso) e finestra `page`/`pageSize`. Ordine di default: quello
    di `items`; i valori nulli vanno in fondo in entrambe le direzioni."""
    if params.search:
        needle = params.search.lower()
        items = [i for i in items if any(needle in str(t).lower() for t in text_of(i))]
    allowed = set(order_fields)
    for part in reversed([p.strip() for p in (params.orderBy or "").split(",") if p.strip()]):
        name = part.lstrip("-")
        field = name if name in allowed else to_snake(name)
        if field not in allowed:
            raise InvalidOrderByError(name)
        keyed = [(key_of(i, field), i) for i in items]
        present = sorted((k for k in keyed if k[0] is not None), key=lambda k: k[0], reverse=part.startswith("-"))  # type: ignore[misc]
        items = [i for _, i in present] + [i for k, i in keyed if k is None]  # nulli sempre in fondo, in entrambe le direzioni
    total = len(items)
    if params.page and params.pageSize:
        items = items[(params.page - 1) * params.pageSize : params.page * params.pageSize]
    return items, total


def make_page(dto: type[Any], items: list[Any], total: int, params: PageParams) -> PaginatedResponse[Any]:
    """`PaginatedResponse[dto]` con la finestra della richiesta."""
    return PaginatedResponse[dto](  # type: ignore[valid-type]
        items=items, total=total, page=params.page, pageSize=params.pageSize
    )
