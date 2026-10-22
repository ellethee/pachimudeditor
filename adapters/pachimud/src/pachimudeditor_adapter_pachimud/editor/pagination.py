"""Ordinamento di default per le liste paginate con `pachifast.database.pagination.paginate`."""

from collections.abc import Iterable
from typing import Any, TypeVar

from pachifast.database.pagination import paginate
from pachifast.database.types import ExtraFilter
from pachifast.schemas.responses import PageParams, PaginatedResponse
from sqlalchemy import ColumnElement, Select
from sqlalchemy.ext.asyncio import AsyncSession

DtoT = TypeVar("DtoT")


def default_order(*columns: str) -> ExtraFilter:
    """Extra filter che ordina per `columns` (nomi di colonna) solo se il client non ha chiesto `orderBy`.

    Con `orderBy` presente l'ordinamento richiesto dal client sostituisce quello di default.
    """

    def _apply(params: Any, filter_kwargs: dict[str, Any], stmt: Select, model: type) -> tuple[dict[str, Any], Select]:
        """Aggiunge l'ORDER BY di default allo statement se `params.orderBy` e' vuoto."""
        if not params.orderBy:
            stmt = stmt.order_by(*(getattr(model, name) for name in columns))
        return filter_kwargs, stmt

    return _apply


def order_clause(model: Any, field: str, desc: bool) -> ColumnElement[Any]:
    """ORDER BY di un campo, con i nulli sempre in fondo."""
    column = getattr(model, field)
    return column.desc().nulls_last() if desc else column.asc().nulls_last()


def range_clauses(model: Any, params: Any, fields: Iterable[str]) -> list[ColumnElement[bool]]:
    """Clausole SQL degli intervalli `min_<campo>`/`max_<campo>` (inclusivi; un valore nullo non ne soddisfa uno)."""
    clauses: list[ColumnElement[bool]] = []
    for field in fields:
        low, high = getattr(params, f"min_{field}"), getattr(params, f"max_{field}")
        if low is not None:
            clauses.append(getattr(model, field) >= low)
        if high is not None:
            clauses.append(getattr(model, field) <= high)
    return clauses


async def paginate_filtered(
    session: AsyncSession,
    model: type,
    params: PageParams,
    dto: type[DtoT],
    clauses: list[ColumnElement[bool]],
    ordering: list[ColumnElement[Any]],
) -> PaginatedResponse[DtoT]:
    """Pagina `model` con `clauses` e `ORDER BY` espliciti (poi il vnum come spareggio) in aggiunta a ricerca e `zoneId`.

    I parametri di filtro sulle statistiche (i campi di `params` oltre a quelli di `PageParams` e `zone_id`) non sono
    uguaglianze su colonna: si tolgono dalla copia data a pachifast, che altrimenti li userebbe come tali."""
    own = set(type(params).model_fields) - set(PageParams.model_fields) - {"zone_id"}

    def apply(_params: PageParams, kwargs: dict[str, Any], stmt: Select, _model: type) -> tuple[dict[str, Any], Select]:
        """Aggiunge filtri e ORDER BY."""
        return kwargs, stmt.where(*clauses).order_by(*ordering)

    plain = params.model_copy(update={"orderBy": None, **dict.fromkeys(own)})
    raw = await paginate(session, model, plain, extra_filters=[apply, default_order("vnum")])
    return PaginatedResponse[dto](  # type: ignore[valid-type]
        items=[dto.model_validate(r) for r in raw.items], total=raw.total, page=raw.page, pageSize=raw.pageSize, pages=raw.pages
    )
