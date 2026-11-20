"""Canale live del gioco pachimud (mixin di `PachimudAdapter`, SDK 1.5): protocollo `livectl` v1 verso il componente asyncio del gioco.

Il client e' quello dell'SDK (`pachimudeditor.sdk.LiveClient`): qui c'e' solo la connessione per mondo (configurazione in `live_config.py`)
e le estensioni pachimud `zone.reload`, `instances.list`, `content.validate` e `content.reload`. Il canale e' opzionale: se il gioco e' spento ogni funzione dell'editor
ripiega sui file. Le capability vere (comandi, campi) le dichiara il `hello` del gioco: un comando assente = funzione non offerta.
"""

import os

from pachimudeditor.sdk import (
    LiveAdapter,
    LiveClient,
    LiveContentReloadIn,
    LiveContentReloadOut,
    LiveContentValidateOut,
    LiveInstances,
    LivePlayerState,
    LiveServerInfo,
    LiveStatus,
    LiveWho,
    LiveZoneReloadIn,
    LiveZoneReloadOut,
    LiveZoneResetIn,
    LiveZoneResetOut,
    LiveZones,
)
from pachimudeditor_adapter_pachimud.base import PachimudSupport


class LiveMixin(LiveAdapter, PachimudSupport):
    """Canale live del mondo (vedi docstring del modulo). Il gioco non ha `player.set`, `load.*`, `echo` e inventario: restano 409."""

    _live_client: LiveClient | None = None

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
        """Zone come le vede il gioco (`index == num ==` vnum)."""
        return await self._client().zones()

    async def live_player_get(self, name: str) -> LivePlayerState:
        """Valori correnti (sola lettura) di un giocatore connesso."""
        return await self._client().player_get(name)

    async def live_zone_reset(self, reset: LiveZoneResetIn, *, actor: str | None = None) -> LiveZoneResetOut:
        """Forza il reset di una zona (il gioco lo accetta solo con `allow_write`)."""
        self.ensure_writable()
        return await self._client().zone_reset(reset, actor=actor)

    async def live_zone_reload(self, reload: LiveZoneReloadIn, *, actor: str | None = None) -> LiveZoneReloadOut:
        """Il gioco rilegge dai YAML la zona e rifa' il reset."""
        self.ensure_writable()
        return await self._client().zone_reload(reload, actor=actor)

    async def live_instances(
        self,
        *,
        room_vnum: int | None = None,
        mob_vnum: int | None = None,
        obj_vnum: int | None = None,
        zone_vnum: int | None = None,
        limit: int = 100,
    ) -> LiveInstances:
        """Istanze in memoria per stanza, prototipo o zona."""
        client = self._client()
        return await client.instances(room_vnum=room_vnum, mob_vnum=mob_vnum, obj_vnum=obj_vnum, zone_vnum=zone_vnum, limit=limit)

    async def live_content_validate(self, *, strict: bool = False) -> LiveContentValidateOut:
        """Il gioco controlla i file dei contenuti (stessi loader del server; lettura)."""
        return await self._client().content_validate(strict=strict)

    async def live_content_reload(self, reload: LiveContentReloadIn, *, actor: str | None = None) -> LiveContentReloadOut:
        """Il gioco rilegge razze, classi, skill, tabelle, social o cataloghi (tutto o niente)."""
        self.ensure_writable()
        return await self._client().content_reload(reload, actor=actor)
