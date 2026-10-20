"""Difese HTTP dell'app: header di sicurezza su ogni risposta e limite di richieste sugli endpoint costosi.

Header (sempre, senza sovrascrivere quelli gia' presenti): `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer` e una `Content-Security-Policy`. La SPA Quasar non usa script inline (solo `style`
inline, che Quasar imposta, e il font Geist da Google Fonts, caricato dai pacchetti `@ilpachi`), quindi la CSP e' stretta; Swagger UI (`/docs*`, che FastAPI carica da jsDelivr e con uno
script inline) ha una CSP piu' larga limitata a quei percorsi. HSTS non c'e': si imposta sul reverse proxy TLS.

Limite: contatore a finestra fissa per indirizzo client, nella cache di pachifast (in memoria del processo, oppure
Redis con `cache_url`), per le conversioni (`POST /api/convert/*`) e l'import di zone (`POST /api/transfer/zones/import`).
`WEBEDITOR_HEAVY_RATE_LIMIT` = richieste per finestra (default 60, `0` = nessun limite);
`WEBEDITOR_HEAVY_RATE_WINDOW` = secondi (default 60). Dietro un reverse proxy avvia uvicorn con gli header del proxy
(`--proxy-headers`), altrimenti tutti i client condividono l'indirizzo del proxy.
"""

import os
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pachifast.cache import get_cache
from pachifast.i18n import error_item

CSP_APP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data: blob:; font-src 'self' data: https://fonts.gstatic.com; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
CSP_DOCS = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
    "worker-src blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
)
HEAVY_LIMIT_DEFAULT = 60
HEAVY_WINDOW_DEFAULT = 60


def is_heavy(method: str, path: str) -> bool:
    """Vero per gli endpoint costosi: conversione (anteprima ed esecuzione) e import di zone."""
    return method == "POST" and (path.startswith("/api/convert/") or path.rstrip("/") == "/api/transfer/zones/import")


async def heavy_rate_limited(request: Request) -> Response | None:
    """`429` (con `Retry-After`) se l'indirizzo ha esaurito le richieste costose della finestra, altrimenti `None`."""
    limit = int(os.environ.get("WEBEDITOR_HEAVY_RATE_LIMIT", HEAVY_LIMIT_DEFAULT))
    if limit <= 0 or not is_heavy(request.method, request.scope["path"]):
        return None
    window = int(os.environ.get("WEBEDITOR_HEAVY_RATE_WINDOW", HEAVY_WINDOW_DEFAULT))
    now = time.time()
    bucket = int(now // window)
    host = request.client.host if request.client else "unknown"
    if await get_cache().incr(f"heavy:{host}:{bucket}", window) <= limit:
        return None
    retry_after = max(1, int((bucket + 1) * window - now) + 1)
    return JSONResponse({"detail": [error_item("auth.rate_limited")]}, status_code=429, headers={"Retry-After": str(retry_after)})


def install_http_guard(app: FastAPI) -> None:
    """Registra il middleware (limite sugli endpoint costosi + header di sicurezza)."""

    @app.middleware("http")
    async def http_guard(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Applica il limite, poi aggiunge gli header di sicurezza alla risposta."""
        response = await heavy_rate_limited(request) or await call_next(request)
        docs = request.scope["path"].startswith("/docs")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Content-Security-Policy", CSP_DOCS if docs else CSP_APP)
        return response
