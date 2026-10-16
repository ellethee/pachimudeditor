"""Ordinamento di default per le liste paginate con `pachifast.database.pagination.paginate`."""

from typing import Any

from pachifast.database.types import ExtraFilter
from sqlalchemy import Select


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
