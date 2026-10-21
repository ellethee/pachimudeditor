"""Canale live di Diku Modificato (mixin di `DikumodAdapter`, SDK 1.5): protocollo `livectl` verso il modulo C del gioco.

Il client del protocollo e' quello dell'SDK (`pachimudeditor.sdk.LiveClient`): qui c'e' solo la configurazione del mondo
(`live_config.py`), una connessione per mondo e il legame con i giocatori su file: `online` di elenco e dettaglio, e la certezza che un
giocatore connesso non vada scritto su file senza la conferma «server acceso». Il canale e' opzionale: se il MUD e' spento ogni funzione
ripiega sui file senza errori (stato `unreachable`), e si riprova a ogni richiesta (salvo una cache di pochi secondi di `who`).
"""

from __future__ import annotations

import os
import time
from typing import Literal

from pachimudeditor_adapter_dikumod.base import DikumodSupport
from pachimudeditor.sdk import (
    LiveAdapter,
    LiveClient,
    LiveEchoIn,
    LiveEchoOut,
    LiveError,
    LiveLoadIn,
    LiveLoadOut,
    LivePlayerSetIn,
    LivePlayerSetOut,
    LivePlayerState,
    LiveServerInfo,
    LiveStatus,
    LiveWho,
    LiveWhoPlayer,
    LiveZoneResetIn,
    LiveZoneResetOut,
    LiveZones,
)

WHO_TTL = 2.0
"""Secondi di validita' del `who` usato per `online`: abbastanza breve da non mentire, abbastanza lungo per un elenco di 100 righe."""


class LiveMixin(LiveAdapter, DikumodSupport):
    """Canale live del mondo (vedi docstring del modulo)."""

    _live_client: LiveClient | None = None
    _who_cache: tuple[float, dict[str, LiveWhoPlayer] | None, bool] | None = None

    def _client(self) -> LiveClient:
        """Il client del mondo (creato al primo uso: nessun I/O finche' non serve)."""
        settings = self.live_settings
        assert settings is not None
        if self._live_client is None:
            env = settings.token_env
            self._live_client = LiveClient(settings.socket, lambda: os.environ.get(env), timeout=settings.timeout_ms / 1000)
        return self._live_client

    async def close(self) -> None:
        """Chiude la connessione del canale (se aperta)."""
        if self._live_client is not None:
            await self._live_client.close()
            self._live_client = None
        await super().close()

    # ------------------------------------------------------------------ giocatori connessi (usato dai giocatori su file)

    async def live_players(self) -> tuple[dict[str, LiveWhoPlayer] | None, bool]:
        """`(giocatori connessi per nome minuscolo, elenco completo)`; `(None, False)` se il canale non risponde. Cache di `WHO_TTL` secondi,
        anche per i fallimenti (un MUD che non risponde non rallenta ogni riga dell'elenco); mai un'eccezione."""
        if self.live_settings is None:
            return None, False
        cached = self._who_cache
        if cached is not None and time.monotonic() - cached[0] < WHO_TTL:
            return cached[1], cached[2]
        try:
            who = await self._client().who()
            players, complete = {p.name.lower(): p for p in who.players}, not who.truncated
        except LiveError:
            players, complete = None, False
        self._who_cache = (time.monotonic(), players, complete)
        return players, complete

    async def live_online(self, name: str) -> bool | None:
        """`True` se connesso, `False` se il canale risponde (elenco completo) e non c'e', `None` se non si sa."""
        players, complete = await self.live_players()
        if players is None:
            return None
        if name.lower() in players:
            return True
        return False if complete else None

    async def live_reachable(self) -> bool:
        """Il canale ha risposto al `who` recente: il server di gioco e' acceso con certezza."""
        return (await self.live_players())[0] is not None

    def _live_changed(self) -> None:
        """Dopo una scrittura live: la cache di `who` (livelli, stanza) non e' piu' attendibile."""
        self._who_cache = None

    # ------------------------------------------------------------------ LiveAdapter

    async def live_status(self) -> LiveStatus:
        """Stato del canale (`hello` + `ping`, sempre una risposta)."""
        return await self._client().status()

    async def live_who(self) -> LiveWho:
        """Giocatori connessi."""
        return await self._client().who()

    async def live_server_info(self) -> LiveServerInfo:
        """Stato del server."""
        return await self._client().info()

    async def live_zones(self) -> LiveZones:
        """Zone come le vede il gioco."""
        return await self._client().zones()

    async def live_player_get(self, name: str) -> LivePlayerState:
        """Valori correnti di un giocatore connesso."""
        return await self._client().player_get(name)

    async def live_player_set(self, name: str, change: LivePlayerSetIn, *, actor: str | None = None) -> LivePlayerSetOut:
        """Modifica un giocatore connesso (ultima difesa: mondo non `read_only`)."""
        self.ensure_writable()
        try:
            return await self._client().player_set(name, change, actor=actor)
        finally:
            self._live_changed()

    async def live_zone_reset(self, reset: LiveZoneResetIn, *, actor: str | None = None) -> LiveZoneResetOut:
        """Forza il reset di una zona."""
        self.ensure_writable()
        return await self._client().zone_reset(reset, actor=actor)

    async def live_load(self, kind: Literal["mob", "obj"], load: LiveLoadIn, *, actor: str | None = None) -> LiveLoadOut:
        """Crea mob o oggetti."""
        self.ensure_writable()
        return await self._client().load(kind, load, actor=actor)

    async def live_echo(self, echo: LiveEchoIn, *, actor: str | None = None) -> LiveEchoOut:
        """Manda un messaggio."""
        self.ensure_writable()
        return await self._client().echo(echo, actor=actor)
