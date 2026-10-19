"""Accesso al database di gioco del mondo pachimud ATTIVO per la richiesta (`X-World` / `?world=`).

Non c'e' piu' una sessione globale: l'engine e le sessioni appartengono all'adapter del mondo
(`adapters.pachimud.PachimudAdapter`) e il mondo scelto dalla richiesta decide quale database si apre. Se il mondo
attivo non e' di tipo pachimud, le route che usano `SessionDep`/`PachimudDep` rispondono 409 `world.not_pachimud`.

Il database di autenticazione di pachifast (utenti dell'editor) e' un altro e non passa di qui.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from pachifast.i18n import api_error
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.adapter import PachimudAdapter
from pachimudeditor.sdk import AdapterDep


def get_pachimud(adapter: AdapterDep) -> PachimudAdapter:
    """Dipendenza: l'adapter pachimud del mondo scelto dalla richiesta (409 `world.not_pachimud` se e' un altro tipo)."""
    if not isinstance(adapter, PachimudAdapter):
        raise api_error(409, "world.not_pachimud", kind=getattr(getattr(adapter, "config", None), "kind", "?"))
    return adapter


PachimudDep = Annotated[PachimudAdapter, Depends(get_pachimud)]
"""L'adapter pachimud attivo (accesso alle sessioni, ai parametri e alle definizioni del mondo)."""


async def get_db(adapter: PachimudDep) -> AsyncIterator[AsyncSession]:
    """Dipendenza FastAPI: una `AsyncSession` sul database del mondo pachimud attivo, per richiesta."""
    async with adapter.session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_db)]
"""Da usare come `session: SessionDep` nelle firme delle route (le classi mappate: `models_of(session)`)."""


def reject_writes_if_read_only(request: Request, adapter: PachimudDep) -> None:
    """Dipendenza di router: 409 `world.read_only` su ogni metodo non sicuro se il mondo e' in sola lettura.

    Da mettere su interi router (players, instances, content) cosi' una nuova rotta di scrittura non resta scoperta.
    """
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        adapter.ensure_writable()


ReadOnlyGuard = Depends(reject_writes_if_read_only)
"""`get_router(deps=[..., ReadOnlyGuard])`."""
