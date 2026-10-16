"""Servizio statico della SPA (frontend buildato) impacchettata in `pachimudeditor/static`."""

from importlib.resources import as_file, files
from pathlib import Path

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles


def static_dir() -> Path | None:
    """La cartella della SPA buildata (contiene `index.html`), o `None` se non e' stata costruita.

    Nel wheel la cartella e' un normale pacchetto di dati su filesystem; in un checkout di sviluppo
    la crea `pachimudeditor build-frontend`.
    """
    with as_file(files("pachimudeditor") / "static") as path:
        return path if (path / "index.html").is_file() else None


class SpaStaticFiles(StaticFiles):
    """`StaticFiles` con fallback SPA: un path senza file (es. `/zones`, `/rooms/map`, ricaricando la
    pagina) serve `index.html`, così il router del frontend (history mode) risolve la route.

    Restano 404 veri i path sotto `api/` e quelli che sembrano un file (estensione): un asset
    mancante non deve diventare una pagina HTML.
    """

    async def get_response(self, path: str, scope):  # type: ignore[no-untyped-def]
        """Come `StaticFiles.get_response`, ma i 404 di route client tornano `index.html`."""
        try:
            response = await super().get_response(path, scope)
            missing = response.status_code == 404
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            response, missing = None, True
        if missing and not path.startswith("api/") and "." not in path.rsplit("/", 1)[-1]:
            return await super().get_response("index.html", scope)
        if response is None:
            raise StarletteHTTPException(404)
        return response
