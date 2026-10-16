"""Account di gioco: lista/ricerca, creazione, email, ban, password, eliminazione."""

from typing import Annotated, Any

from fastapi import Query
from pachifast.database.pagination import paginate
from pachifast.router_factory import get_router
from pachifast.schemas.responses import PageParams, PaginatedResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.schema import models_of
from pachimudeditor_adapter_pachimud.security import hash_password
from pachimudeditor_adapter_pachimud.editor import crud
from pachimudeditor_adapter_pachimud.editor.db import SessionDep
from pachimudeditor.sdk import conflict
from pachimudeditor_adapter_pachimud.editor.pagination import default_order

from .helpers import collect_item_ids, count_characters, delete_items
from .schemas import AccountIn, AccountOut, AccountPatch, PasswordIn

router = get_router(prefix="")


class AccountPageParams(PageParams):
    """Lista account: `search` su username/email, filtro esatto `isBanned`."""

    search_fields = ["username", "email"]
    order_fields = ["id", "username", "email", "created_at", "last_login_at", "is_banned"]
    is_banned: bool | None = Query(None)


async def _out(session: AsyncSession, account: Any) -> AccountOut:
    """`AccountOut` con il conteggio dei personaggi."""
    out = AccountOut.model_validate(account)
    out.character_count = (await count_characters(session, [account.id])).get(account.id, 0)
    return out


async def _ensure_unique(session: AsyncSession, *, username: str | None, email: str | None, ignore_id: int | None = None) -> None:
    """409 `players.username_taken` / `players.email_taken` se gia' usati da un altro account."""
    Account = models_of(session).Account  # noqa: N806
    if username is not None:
        other = (await session.execute(select(Account).where(Account.username == username))).scalars().first()
        if other is not None and other.id != ignore_id:
            raise conflict("players.username_taken", username=username)
    if email is not None:
        other = (await session.execute(select(Account).where(Account.email == email))).scalars().first()
        if other is not None and other.id != ignore_id:
            raise conflict("players.email_taken", email=email)


@router.get("/accounts", response_model=PaginatedResponse[AccountOut])
async def list_accounts(params: Annotated[AccountPageParams, Query()], session: SessionDep) -> PaginatedResponse[AccountOut]:
    """Account paginati (ricerca username/email, filtro `isBanned`); ordine di default per username."""
    page = await paginate(session, models_of(session).Account, params, extra_filters=[default_order("username")])
    counts = await count_characters(session, [a.id for a in page.items])
    items = []
    for account in page.items:
        out = AccountOut.model_validate(account)
        out.character_count = counts.get(account.id, 0)
        items.append(out)
    page.items = items
    return page


@router.post("/accounts", response_model=AccountOut, status_code=201)
async def create_account(data: AccountIn, session: SessionDep) -> AccountOut:
    """Crea un account (password hashata Argon2id); 409 se username o email sono gia' usati."""
    await _ensure_unique(session, username=data.username, email=data.email)
    account = await crud.create(
        session,
        models_of(session).Account,
        {"username": data.username, "email": data.email, "password_hash": hash_password(data.password)},
    )
    return await _out(session, account)


@router.get("/accounts/{account_id}", response_model=AccountOut)
async def get_account(account_id: int, session: SessionDep) -> AccountOut:
    """Un account (mai l'hash della password)."""
    account = await crud.get_or_404(session, models_of(session).Account, account_id, code="players.account_not_found")
    return await _out(session, account)


@router.put("/accounts/{account_id}", response_model=AccountOut)
async def update_account(account_id: int, data: AccountPatch, session: SessionDep) -> AccountOut:
    """Modifica l'email dell'account (409 se gia' usata da un altro)."""
    Account = models_of(session).Account  # noqa: N806
    await crud.get_or_404(session, Account, account_id, code="players.account_not_found")
    if "email" in data.model_fields_set:
        await _ensure_unique(session, username=None, email=data.email, ignore_id=account_id)
    account = await crud.update(session, Account, account_id, data, code="players.account_not_found")
    return await _out(session, account)


async def _set_ban(session: AsyncSession, account_id: int, banned: bool) -> AccountOut:
    """Imposta `is_banned` e restituisce l'account."""
    account = await crud.update(session, models_of(session).Account, account_id, {"is_banned": banned}, code="players.account_not_found")
    return await _out(session, account)


@router.post("/accounts/{account_id}/ban", response_model=AccountOut)
async def ban_account(account_id: int, session: SessionDep) -> AccountOut:
    """Banna l'account (idempotente)."""
    return await _set_ban(session, account_id, True)


@router.post("/accounts/{account_id}/unban", response_model=AccountOut)
async def unban_account(account_id: int, session: SessionDep) -> AccountOut:
    """Rimuove il ban (idempotente)."""
    return await _set_ban(session, account_id, False)


@router.post("/accounts/{account_id}/password", response_model=AccountOut)
async def set_password(account_id: int, data: PasswordIn, session: SessionDep) -> AccountOut:
    """Imposta una nuova password (hash Argon2id); la risposta non contiene l'hash."""
    account = await crud.update(
        session,
        models_of(session).Account,
        account_id,
        {"password_hash": hash_password(data.password)},
        code="players.account_not_found",
    )
    return await _out(session, account)


@router.delete("/accounts/{account_id}", status_code=204, response_model=None, skip_envelope=True)
async def delete_account(account_id: int, session: SessionDep, cascade: bool = Query(False)) -> None:
    """Elimina un account. Con personaggi: 409 `players.account_has_characters`, salvo `?cascade=true`
    che elimina anche personaggi e relativo inventario."""
    m = models_of(session)
    PlayerCharacter = m.PlayerCharacter  # noqa: N806
    account = await crud.get_or_404(session, m.Account, account_id, code="players.account_not_found")
    characters = (await session.execute(select(PlayerCharacter).where(PlayerCharacter.account_id == account_id))).scalars().all()
    if characters and not cascade:
        raise conflict("players.account_has_characters", count=len(characters))
    for character in characters:
        await delete_items(session, await collect_item_ids(session, character.id))
        await session.delete(character)
    await session.flush()
    await session.delete(account)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise conflict("common.editor.in_use") from error
