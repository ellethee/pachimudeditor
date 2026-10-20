"""Factory dell'app pachifast del webeditor di pachimud.

Avvio consigliato: `pachimudeditor serve --workdir DIR` (vedi `pachimudeditor.cli`). Direttamente con uvicorn,
dalla cartella di lavoro (`.env` e `pachimudeditor.yaml`)::

    PACHIFAST_CONFIG_FILE=pachimudeditor.yaml uvicorn pachimudeditor.app:create_editor_app --factory
"""

from collections.abc import Awaitable, Callable, Iterable

from fastapi import FastAPI, Request, Response
from pachifast import create_app

from pachimudeditor.common.adapters.bootstrap import prepare_worlds
from pachimudeditor.common.adapters.registry import WorldRegistry, set_registry
from pachimudeditor.modules import build_modules
from pachimudeditor.spa import SpaStaticFiles, static_dir

CORS_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:8123",
    "http://127.0.0.1:8123",
    "http://localhost:9000",
    "http://127.0.0.1:9000",
]

_EDITOR_PREFIXES = (
    "/api/zones",
    "/api/rooms",
    "/api/mobs",
    "/api/objects",
    "/api/instances",
    "/api/players",
    "/api/world",
    "/api/worlds",
)


def create_editor_app(*, serve_spa: bool = True, extra_kinds: Iterable[str] = ()) -> FastAPI:
    """Costruisce l'app dell'editor: API pachifast e, se presente `static/`, la SPA sullo stesso processo/porta.

    La SPA e' montata DOPO `create_app`, quindi dopo tutte le route (`/api/*`, `/docs`, openapi), che restano
    prioritarie. `html=True` serve `index.html` su "/"; le route client ricaricate cadono nel fallback SPA.
    `extra_kinds`: kind di cui caricare i moduli API oltre a quelli dei mondi configurati (test, mondi aggiunti a runtime).
    """
    # config mondi -> moduli opzionali solo se servono e `pachimud` e' importabile -> registro
    configs, default = prepare_worlds()
    app = create_app(build_modules({c.kind for c in configs} | set(extra_kinds)), cors_origins=CORS_ORIGINS)
    set_registry(WorldRegistry(configs, default))

    @app.middleware("http")
    async def strip_trailing_slash(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Accetta `/api/<risorsa>/` come `/api/<risorsa>` (pachi-table2 posta con lo slash finale)."""
        path = request.scope["path"]
        if len(path) > 1 and path.endswith("/") and path.startswith(_EDITOR_PREFIXES):
            request.scope["path"] = path.rstrip("/")
        return await call_next(request)

    directory = static_dir() if serve_spa else None
    if directory is not None:
        app.mount("/", SpaStaticFiles(directory=directory, html=True), name="spa")
    return app
