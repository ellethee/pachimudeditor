"""Difese HTTP dell'app: header di sicurezza su ogni risposta.

Header (sempre, senza sovrascrivere quelli gia' presenti): `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer` e una `Content-Security-Policy`. La SPA Quasar non usa script inline (solo `style`
inline, che Quasar imposta, e il font Geist da Google Fonts, caricato dai pacchetti `@ilpachi`), quindi la CSP e' stretta; Swagger UI (`/docs*`, che FastAPI carica da jsDelivr e con uno
script inline) ha una CSP piu' larga limitata a quei percorsi. HSTS non c'e': si imposta sul reverse proxy TLS.

Il limite di richieste sugli endpoint costosi sta in `common/rate_limit.py` (dipendenza pachifast sulle rotte).
"""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

CSP_APP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data: blob:; font-src 'self' data: https://fonts.gstatic.com; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
CSP_DOCS = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
    "worker-src blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
)


def install_http_guard(app: FastAPI) -> None:
    """Registra il middleware degli header di sicurezza."""

    @app.middleware("http")
    async def http_guard(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Aggiunge gli header di sicurezza alla risposta."""
        response = await call_next(request)
        docs = request.scope["path"].startswith("/docs")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Content-Security-Policy", CSP_DOCS if docs else CSP_APP)
        return response
