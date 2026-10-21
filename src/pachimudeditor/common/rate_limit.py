"""Limite di richieste sugli endpoint costosi (conversioni, import di zone), basato su `pachifast.ratelimit.rate_limit`.

Le rotte costose usano la dipendenza `heavy_rate_limit()`: contatore per utente autenticato (ripiego: indirizzo IP),
scope `heavy` condiviso tra le rotte. Limite e finestra sono le impostazioni di pachifast `rate_limit.default` e
`rate_limit.window_seconds` (env `PACHIFAST_RATE_LIMIT_DEFAULT`/`PACHIFAST_RATE_LIMIT_WINDOW_SECONDS`); a differenza di
pachifast (spento), l'editor usa 60 richieste se `rate_limit.default` non e' scritto (`rate_limit(default=60)`), e `0` le spegne.
"""

import os
from typing import Any

from fastapi import Depends
from pachifast.ratelimit import rate_limit

HEAVY_LIMIT_DEFAULT = 60


def _legacy(name: str, default: int | None) -> int | None:
    """Alias deprecato `WEBEDITOR_HEAVY_RATE_*` (intero positivo), altrimenti `default`."""
    value = os.environ.get(name)
    return int(value) if value is not None and value.isdigit() and int(value) > 0 else default


def heavy_rate_limit() -> Any:
    """Dipendenza FastAPI per le rotte costose (`dependencies=[heavy_rate_limit()]`).

    Il limite e' `rate_limit.default` di pachifast se scritto (`0` = spento), altrimenti l'alias
    `WEBEDITOR_HEAVY_RATE_LIMIT`, altrimenti 60. La finestra e' `rate_limit.window_seconds`, o l'alias
    `WEBEDITOR_HEAVY_RATE_WINDOW` (che in tal caso vince).
    """
    default = _legacy("WEBEDITOR_HEAVY_RATE_LIMIT", HEAVY_LIMIT_DEFAULT)
    return Depends(rate_limit(window=_legacy("WEBEDITOR_HEAVY_RATE_WINDOW", None), key="user", scope="heavy", default=default))
