"""Giocatori: account, personaggi, inventario. Prefisso `/api/players`."""

from fastapi import Depends
from pachifast.router_factory import get_router

from pachimudeditor_adapter_pachimud.editor.db import ReadOnlyGuard

from pachimudeditor.sdk import require_capability

from . import accounts, characters, inventory

router = get_router(deps=[Depends(require_capability("supports_players")), ReadOnlyGuard])
router.include_router(accounts.router)
router.include_router(characters.router)
router.include_router(inventory.router)
