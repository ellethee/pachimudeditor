"""Configurazione del canale live di un mondo (`params.live`) e sua validazione.

Esempio (il segreto sta nel `.env` della cartella di lavoro, qui solo il NOME della variabile)::

    params:
      live:
        socket: /percorso/assoluto/livectl.sock
        token_env: DIKUMOD_LIVE_TOKEN
        timeout_ms: 3000       # facoltativo, default 3000
        enabled: true          # facoltativo; false = canale spento senza togliere la configurazione

La validazione segnala solo parametri incoerenti: NON controlla che il socket esista o che il MUD sia acceso (il canale e' opzionale
e si riprova a ogni richiesta) e non fallisce se la variabile del token manca (lo stato del canale dira' `token_missing`).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from pachimudeditor.sdk import WorldConfig

log = logging.getLogger(__name__)

SOCKET_MAX = 107
"""Lunghezza massima del percorso di un socket Unix (`sun_path` di Linux e' 108 byte con il terminatore)."""
KEYS = frozenset({"transport", "socket", "token_env", "timeout_ms", "enabled"})
ENV_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class LiveSettings:
    """Parametri validati del canale live."""

    socket: str
    token_env: str
    timeout_ms: int = 3000


def parse_live_settings(params: dict[str, Any]) -> LiveSettings | None:
    """`LiveSettings` di `params.live`; `None` se non configurato o con `enabled: false`. `ValueError` (messaggio per l'utente) se incoerente."""
    raw = params.get("live")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("params.live deve essere un oggetto (socket, token_env, timeout_ms, enabled)")
    unknown = sorted(set(raw) - KEYS)
    if unknown:
        raise ValueError(f"params.live: chiavi sconosciute {unknown}")
    if raw.get("transport", "unix") != "unix":
        raise ValueError("params.live.transport: e' supportato solo 'unix' (il TCP non e' implementato dall'editor)")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("params.live.enabled deve essere true o false")
    sock, env, timeout = raw.get("socket"), raw.get("token_env"), raw.get("timeout_ms", 3000)
    if not isinstance(sock, str) or not os.path.isabs(sock) or "\0" in sock:
        raise ValueError("params.live.socket: serve il percorso ASSOLUTO del socket Unix (il MUD fa chdir nella cartella dati)")
    if len(sock.encode()) > SOCKET_MAX:
        raise ValueError(f"params.live.socket: percorso troppo lungo (massimo {SOCKET_MAX} byte)")
    if not isinstance(env, str) or not ENV_NAME_RE.fullmatch(env):
        raise ValueError("params.live.token_env: serve il NOME di una variabile d'ambiente (mai il token nel yaml)")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 200 <= timeout <= 60000:
        raise ValueError("params.live.timeout_ms: intero tra 200 e 60000")
    return LiveSettings(socket=sock, token_env=env, timeout_ms=timeout) if enabled else None


def validate_world(config: WorldConfig) -> None:
    """`validate` del plugin: parametri incoerenti sono un errore all'avvio; un MUD spento o un token non ancora impostato no (avviso nel log)."""
    settings = parse_live_settings(config.params)
    if settings is not None and not os.environ.get(settings.token_env):
        log.info(
            "Mondo %r: la variabile %s (token del canale live) non e' impostata: il canale risultera' 'token_missing'",
            config.id,
            settings.token_env,
        )
