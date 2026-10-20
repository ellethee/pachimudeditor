"""Limite di richieste sugli endpoint costosi (conversioni, import di zone), basato su `pachifast.ratelimit.rate_limit`.

Le rotte costose usano la dipendenza `heavy_rate_limit()`: contatore per utente autenticato (ripiego: indirizzo IP),
scope `heavy` condiviso tra le rotte. Limite e finestra sono le impostazioni di pachifast `rate_limit.default` e
`rate_limit.window_seconds` (env `PACHIFAST_RATE_LIMIT_DEFAULT`/`PACHIFAST_RATE_LIMIT_WINDOW_SECONDS`); a differenza di
pachifast (spento), l'editor le imposta a 60/60 s se non sono scritte, e `0` le spegne.
"""

import os
from typing import Any

from fastapi import Depends
from pachifast.config import get_settings
from pachifast.ratelimit import rate_limit

HEAVY_LIMIT_DEFAULT = 60


def heavy_rate_limit() -> Any:
    """Dipendenza FastAPI per le rotte costose (`dependencies=[heavy_rate_limit()]`)."""
    return Depends(rate_limit(key="user", scope="heavy"))


def apply_rate_limit_defaults() -> None:
    """Default dell'editor: 60 richieste per finestra, salvo `rate_limit.*` esplicito (yaml/env di pachifast).

    Alias deprecati `WEBEDITOR_HEAVY_RATE_LIMIT`/`WEBEDITOR_HEAVY_RATE_WINDOW`: valgono solo se la chiave pachifast
    corrispondente non e' scritta.
    """
    settings = get_settings()
    for field, legacy, default in (
        ("rate_limit_default", "WEBEDITOR_HEAVY_RATE_LIMIT", HEAVY_LIMIT_DEFAULT),
        ("rate_limit_window_seconds", "WEBEDITOR_HEAVY_RATE_WINDOW", None),
    ):
        if field in settings.model_fields_set:
            continue
        value = os.environ.get(legacy)
        if value is not None and value.isdigit() and (int(value) > 0 or field == "rate_limit_default"):
            setattr(settings, field, int(value))
        elif default is not None:
            setattr(settings, field, default)
