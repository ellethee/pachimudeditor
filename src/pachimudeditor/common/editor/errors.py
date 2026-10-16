"""Helper per gli errori HTTP con codice stabile condivisi da ogni app dell'editor."""

from fastapi import HTTPException
from pachifast.i18n import api_error


def not_found(code: str, **params: object) -> HTTPException:
    """404 per una riga mancante; `code` e' il codice del catalogo (es. `zones.not_found`)."""
    return api_error(404, code, **params)


def conflict(code: str, **params: object) -> HTTPException:
    """409 per una violazione di vincolo (vnum duplicato, FK ancora referenziata, ...)."""
    return api_error(409, code, **params)
