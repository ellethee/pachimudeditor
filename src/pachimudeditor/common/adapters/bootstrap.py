"""Avvio dei mondi: lettura della configurazione e verifica di kind e parametri dei mondi.

Per ogni mondo configurato si controlla che l'adapter del suo `kind` sia installato (altrimenti l'errore dice quale
extra installare) e si esegue la `validate` del plugin (parametri sensati), per dare un errore chiaro prima di avviare il
server.
"""

import logging

from pachimudeditor.common.adapters import plugins
from pachimudeditor.common.adapters.registry import WorldConfig, check_kind, load_world_configs

log = logging.getLogger(__name__)


class WorldSetupError(Exception):
    """Configurazione dei mondi non utilizzabile (messaggio pensato per essere mostrato all'utente)."""


def prepare_worlds() -> tuple[list[WorldConfig], str | None]:
    """Mondi configurati e default, con kind installati e parametri gia' verificati.

    Raises:
        WorldSetupError: configurazione dei mondi non valida (JSON, campi) o adapter mancante / parametri non validi.
    """
    try:
        configs, default = load_world_configs()
    except ValueError as exc:
        raise WorldSetupError(f"Configurazione dei mondi non valida: {exc}") from exc
    for config in configs:
        try:
            check_kind(config.kind)
            plugins.validate_world(config)
        except ValueError as exc:  # AdapterUnavailable e' un ValueError
            raise WorldSetupError(f"Mondo {config.id!r}: {exc}") from exc
    if default not in {c.id for c in configs}:
        default = None
    return configs, default
