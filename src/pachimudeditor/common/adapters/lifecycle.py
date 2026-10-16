"""Avvio e spegnimento dei mondi (hook del modulo `common.adapters`).

All'avvio ogni mondo che sa controllare il proprio schema (oggi `kind: pachimud`) scrive nel log revisione e avvisi;
non fallisce mai l'avvio: un mondo non utilizzabile risponde 503 alle richieste, gli altri funzionano. Allo spegnimento
si chiudono gli engine degli adapter.
"""

import logging

from pachimudeditor.common.adapters.registry import get_registry

log = logging.getLogger(__name__)


def startup() -> None:
    """Controlla e logga lo schema dei mondi che lo prevedono (`log_schema_report`)."""
    registry = get_registry()
    for world_id in registry.world_ids:
        try:
            adapter = registry.get(world_id)
            report = getattr(adapter, "log_schema_report", None)
            if report is not None:
                report()
        except Exception:  # noqa: BLE001 - l'avvio non deve cadere per un mondo
            log.exception("Controllo del mondo %r non riuscito", world_id)


async def shutdown() -> None:
    """Chiude gli adapter istanziati."""
    await get_registry().aclose_all()
