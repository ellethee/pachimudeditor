"""Supporto comune ai mixin di `PachimudAdapter`: archivio YAML, lock di scrittura, ricerca per id, uso dei vnum, DB giocatori."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pachifast.i18n import api_error
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor.common.adapters.models import EntityKind, ResetUsage
from pachimudeditor.common.enums import Direction
from pachimudeditor.sdk import WorldConfig, make_page, paginate_list, rules  # noqa: F401  (ri-esportati per i mixin)
from pachimudeditor_adapter_pachimud import mapping, resets
from pachimudeditor_adapter_pachimud.connection import PachimudConnection
from pachimudeditor_adapter_pachimud.live_config import LiveSettings, parse_live_settings
from pachimudeditor_adapter_pachimud.params import PachimudConfigError, PachimudParams, resolve_params
from pachimudeditor_adapter_pachimud.schema import SchemaUnavailable, schema_unavailable_error
from pachimudeditor_adapter_pachimud.store import Item, Kind, YamlStore, ZoneEntry

log = logging.getLogger(__name__)


class PachimudSupport:
    """Stato condiviso dai mixin: configurazione, archivio dei file YAML, lock di scrittura, DB dei giocatori."""

    def __init__(self, config: WorldConfig) -> None:
        """Risolve i parametri del mondo (`definitions_path`, `database_url`...); nessuna lettura finche' non serve.

        Raises:
            PachimudConfigError: parametri mancanti o non validi.
        """
        self.config = config
        self.params: PachimudParams = resolve_params(config)
        self.store = YamlStore(self.params.definitions_path)
        self.connection = PachimudConnection(self.params) if self.params.database_url else None
        self.live_settings: LiveSettings | None = parse_live_settings(config.params)
        """Parametri del canale live (`params.live`), `None` se non configurato o spento: senza, niente capability `supports_live`."""
        self.lock = asyncio.Lock()
        """Un solo scrittore per volta: una scrittura puo' toccare piu' file (uscite entranti, spostamenti)."""

    def ensure_writable(self) -> None:
        """409 `world.read_only` se il mondo e' in sola lettura (ultima difesa dell'adapter)."""
        if self.config.read_only:
            raise api_error(409, "world.read_only")

    def sync(self) -> YamlStore:
        """Riallinea la cache al disco e restituisce l'archivio.

        Raises:
            HTTPException: 503 `world.unavailable` se la cartella delle definizioni non esiste (il dettaglio va solo nel log).
        """
        if not self.params.definitions_path.is_dir():
            log.warning(
                "mondo pachimud %r non utilizzabile: cartella delle definizioni non trovata: %s",
                self.config.id,
                self.params.definitions_path,
            )
            raise api_error(503, "world.unavailable")
        self.store.refresh()
        return self.store

    @asynccontextmanager
    async def writing(self) -> AsyncIterator[YamlStore]:
        """Sezione di scrittura: lock unico e cache aggiornata; se qualcosa fallisce la cache e' invalidata (le modifiche
        in memoria non salvate non devono restare ne' finire su disco al salvataggio successivo)."""
        async with self.lock:
            store = self.sync()
            try:
                yield store
            except ValidationError as error:
                store.invalidate()
                raise mapping.invalid(error) from error
            except BaseException:
                store.invalidate()
                raise

    # ------------------------------------------------------------------ ricerca per id

    def zone_or_404(self, zone_id: int) -> ZoneEntry:
        """La zona `zone_id` (404 `zones.not_found`)."""
        zone = self.sync().zone(zone_id)
        if zone is None:
            raise api_error(404, "zones.not_found")
        return zone

    def find_or_404(self, kind: Kind, vnum: int, code: str) -> Item:
        """La voce per vnum (404 `code`)."""
        item = self.sync().find(kind, vnum)
        if item is None:
            raise api_error(404, code)
        return item

    # ------------------------------------------------------------------ DB dei giocatori

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Una `AsyncSession` sul database dei giocatori (503 `world.unavailable` se non e' configurato o utilizzabile)."""
        if self.connection is None:
            raise api_error(409, "world.capability_missing", capability="supports_players")
        try:
            async with self.connection.session() as session:
                yield session
        except SchemaUnavailable as exc:
            raise schema_unavailable_error(exc) from exc
        except OverflowError as exc:  # id/page/pageSize oltre i 64 bit di SQLite: input non valido, non un guasto
            raise api_error(422, "world.value_out_of_range") from exc

    async def players_in_room(self, room_vnum: int) -> int:
        """Quanti personaggi hanno `room_vnum` come ultima stanza (0 se il DB dei giocatori non c'e' o non si legge)."""
        if self.connection is None:
            return 0
        from sqlalchemy import func, select

        try:
            async with self.connection.session() as session:
                model = session.info["models"].PlayerCharacter
                if model is None:
                    return 0
                return int(
                    (
                        await session.execute(select(func.count()).select_from(model).where(model.current_room_vnum == room_vnum))
                    ).scalar_one()
                )
        except Exception:  # noqa: BLE001 - il controllo e' di cortesia: un DB illeggibile non blocca le modifiche ai contenuti
            return 0

    async def close(self) -> None:
        """Chiude engine e connessioni del mondo."""
        if self.connection is not None:
            await self.connection.dispose()

    # ------------------------------------------------------------------ uso dei vnum

    def find_usage(self, kind: EntityKind, vnum: int, *, include_exit_keys: bool = True) -> list[ResetUsage]:
        """Reset (di ogni zona) che referenziano `vnum` come `kind`; per gli oggetti anche le chiavi delle uscite."""
        fields: dict[Any, list[int]] = {}
        for command_type, name in rules.USAGE_FIELDS[kind]:
            fields.setdefault(command_type, []).append(int(name[3:]))  # "arg3" -> posizione 3 nella tupla (arg1 = 1)
        usage: list[ResetUsage] = []
        for zone in self.store.zones:
            for index, command in enumerate(resets.flatten(zone)):
                if command[0] in fields and any(command[slot] == vnum for slot in fields[command[0]]):
                    usage.append(
                        ResetUsage(
                            zone_id=zone.vnum,
                            zone_name=zone.model.name,
                            reset_command_id=index,
                            order_index=index,
                            command_type=command[0],
                        )
                    )
        if kind == "object" and include_exit_keys:
            for room in self.store.all_items("room"):
                for key, x in room.model.exits.items():
                    if x.key_vnum == vnum:
                        usage.append(
                            ResetUsage(
                                zone_id=room.zone.vnum,
                                zone_name=room.zone.model.name,
                                source="exit_key",
                                exit_id=room.vnum * mapping.EXIT_STRIDE + int(Direction[key.upper()]),
                                room_id=room.vnum,
                                room_vnum=room.vnum,
                            )
                        )
        return usage

    def ensure_unused(self, kind: EntityKind, vnum: int, code: str, *, include_exit_keys: bool = True) -> None:
        """409 `code` se `vnum` e' referenziato (reset e, per gli oggetti, chiavi di uscite)."""
        rules.raise_if_used(self.find_usage(kind, vnum, include_exit_keys=include_exit_keys), code)


class PachimudResetLookup:
    """`rules.ResetLookup` sull'archivio YAML."""

    def __init__(self, store: YamlStore) -> None:
        """Usa l'archivio (gia' sincronizzato) per le verifiche di esistenza."""
        self.store = store

    async def existing_vnums(self, kind: EntityKind, vnums: set[int]) -> set[int]:
        """Quali tra `vnums` esistono come stanza/mob/oggetto in qualsiasi zona."""
        return vnums & self.store.vnums(kind)

    async def exit_has_door(self, room_vnum: int, direction: int) -> bool | None:
        """`None` se la stanza non ha l'uscita, altrimenti se e' una porta (`door_flag` != NONE)."""
        room = self.store.find("room", room_vnum)
        key = mapping.direction_key(room.model.exits, direction) if room else None
        return None if key is None else room.model.exits[key].door_flag != "NONE"  # type: ignore[union-attr]


__all__ = ["PachimudConfigError", "PachimudResetLookup", "PachimudSupport"]
