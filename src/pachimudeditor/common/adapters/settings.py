"""Impostazioni dei mondi dell'editor: `webeditor_worlds` e `webeditor_default_world`.

Sorgenti, dalla piu' alla meno prioritaria: variabili d'ambiente `WEBEDITOR_WORLDS` (JSON) e
`WEBEDITOR_DEFAULT_WORLD` (alias `PACHIMUDEDITOR_WORLDS` / `PACHIMUDEDITOR_DEFAULT_WORLD`; i nomi `WEBEDITOR_*`
hanno la precedenza), poi le chiavi omonime di `pachimudeditor.yaml` (il file letto da pachifast, vedi
`PACHIFAST_CONFIG_FILE`; il CLI lo imposta sulla cartella di lavoro). Senza
nulla di configurato non c'e' nessun mondo. Esempio in `pachimudeditor.yaml`::

    webeditor_worlds:
      - {id: pachimud, kind: pachimud, name: Pachimud}
      - {id: basedmud, kind: basedmud, name: BasedMud, path: /percorso/a/basedmud/area, read_only: true}
      - {id: tba, kind: mapping, name: tbaMUD, mapping: /percorso/a/tba.mapping.yaml, path: /percorso/a/tba/lib}
    webeditor_default_world: pachimud
"""

import json
import os
from typing import Any

from pachifast.config.yaml_source import load_config_data


def load_world_settings() -> tuple[list[dict[str, Any]] | None, str | None]:
    """`(mondi, mondo_di_default)` da ambiente e `pachimudeditor.yaml`; `None` dove non configurati."""
    yaml_data = load_config_data()
    worlds: Any = None
    env_worlds = os.environ.get("WEBEDITOR_WORLDS") or os.environ.get("PACHIMUDEDITOR_WORLDS")
    if env_worlds:
        worlds = json.loads(env_worlds)
    elif yaml_data.get("webeditor_worlds"):
        worlds = yaml_data["webeditor_worlds"]
    default = (
        os.environ.get("WEBEDITOR_DEFAULT_WORLD")
        or os.environ.get("PACHIMUDEDITOR_DEFAULT_WORLD")
        or yaml_data.get("webeditor_default_world")
    )
    return (list(worlds) if worlds else None), default


def register_settings(settings: object) -> None:
    """Espone i valori anche su `get_settings()` (`settings.webeditor_worlds`, `settings.webeditor_default_world`)."""
    worlds, default = load_world_settings()
    setattr(settings, "webeditor_worlds", worlds)
    setattr(settings, "webeditor_default_world", default)
