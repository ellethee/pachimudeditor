"""CRUD async generico sopra le classi mappate del database di pachimud (vedi `adapters.pachimud.schema`).

Ogni helper prende la `AsyncSession` del mondo (`adapter.session()` / `common.editor.db.SessionDep`) e fa il proprio commit.
Le scritture mappano `IntegrityError` a HTTP 409 con un codice stabile (FK ancora referenziata,
duplicato, ...). Le liste usano `pachifast.database.pagination.paginate` direttamente nelle route.
"""

from collections.abc import Mapping
from typing import Any, TypeVar

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.schema import strip_unsupported
from pachimudeditor.sdk import conflict, not_found

ModelT = TypeVar("ModelT")


def _integrity_error(error: IntegrityError, *, deleting: bool) -> HTTPException:
    """Traduce un errore di integrita' del DB nell'`HTTPException` 409 con il codice adatto."""
    text = str(error.orig).lower()
    if deleting and "not null" in text:
        return conflict("common.editor.in_use")
    if "foreign key" in text:
        return conflict("common.editor.in_use" if deleting else "common.editor.invalid_reference")
    if "unique" in text:
        return conflict("common.editor.duplicate")
    return conflict("common.editor.constraint_violation")


async def get_or_404(session: AsyncSession, model: type[ModelT], row_id: int, *, code: str) -> ModelT:
    """La riga con chiave primaria `row_id`, o un 404 con il codice `code` (es. `zones.not_found`)."""
    row = await session.get(model, row_id)
    if row is None:
        raise not_found(code, id=row_id)
    return row


async def create(session: AsyncSession, model: type[ModelT], data: BaseModel | Mapping[str, Any]) -> ModelT:
    """Inserisce un `model` costruito da `data` (campi dello schema per nome Python) e lo restituisce aggiornato."""
    values = data.model_dump(by_alias=False) if isinstance(data, BaseModel) else dict(data)
    row = model(**strip_unsupported(model, values))  # type: ignore[call-arg]
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise _integrity_error(error, deleting=False) from error
    await session.refresh(row)
    return row


async def update(
    session: AsyncSession,
    model: type[ModelT],
    row_id: int,
    data: BaseModel | Mapping[str, Any],
    *,
    code: str,
) -> ModelT:
    """Aggiornamento parziale: solo i campi effettivamente inviati (`exclude_unset`) vengono scritti."""
    row = await get_or_404(session, model, row_id, code=code)
    values = data.model_dump(exclude_unset=True, by_alias=False) if isinstance(data, BaseModel) else dict(data)
    for name, value in strip_unsupported(model, values).items():
        setattr(row, name, value)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise _integrity_error(error, deleting=False) from error
    await session.refresh(row)
    return row


async def delete(session: AsyncSession, model: type[ModelT], row_id: int, *, code: str) -> None:
    """Elimina una riga; una FK che punta ancora ad essa diventa HTTP 409, una riga mancante HTTP 404."""
    row = await get_or_404(session, model, row_id, code=code)
    await session.delete(row)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise _integrity_error(error, deleting=True) from error
