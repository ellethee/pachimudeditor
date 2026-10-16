"""App di test che include i moduli `transfer` e `content` anche se non ancora registrati in `project_modules`."""

import httpx
from pachifast import AppModule, create_app

from pachimudeditor_adapter_pachimud.apps.content.module import module as content_module
from pachimudeditor_adapter_pachimud.apps.transfer.module import module as transfer_module
from pachimudeditor.common.adapters.plugins import available_kinds
from pachimudeditor.modules import build_modules

MODULES = build_modules(available_kinds())

_EXTRA = (transfer_module, content_module)


def build_app():  # type: ignore[no-untyped-def]
    """App pachifast con i moduli di progetto piu' `transfer`/`content` (senza duplicarli se registrati)."""
    registered = {module.name for module in MODULES}
    extra: tuple[AppModule, ...] = tuple(m for m in _EXTRA if m.name not in registered)
    return create_app((*MODULES, *extra))


def make_client(app, token: str) -> httpx.AsyncClient:  # type: ignore[no-untyped-def]
    """Client HTTP autenticato in-process verso `app`."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": f"Bearer {token}"})
