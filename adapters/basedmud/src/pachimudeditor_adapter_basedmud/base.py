"""Supporto comune ai mixin di `BasedMudAdapter`: archivio, lock di scrittura, paginazione in memoria, uso dei vnum."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pachimudeditor_adapter_basedmud.rom_lib import Reset, RomUnencodableError, RomWriteError
from pachifast.i18n import api_error
from pachimudeditor.common.enums import Direction

from pachimudeditor_adapter_basedmud.mapping import reset_out
from pachimudeditor_adapter_basedmud.store import AreaEntry, AreaStore, Kind, resolve_area_dir
from pachimudeditor.sdk import rules
from pachimudeditor.common.adapters.models import EntityKind, ResetUsage
from pachimudeditor.sdk import make_page, paginate_list  # noqa: F401  (ri-esportati per i mixin)
from pachimudeditor.sdk import WorldConfig


def real_resets(entry: AreaEntry) -> list[Reset]:
    """I reset veri dell'area (senza le righe di commento `*`)."""
    section = entry.area.section("RESETS", create=False)
    return [r for r in section.items if isinstance(r, Reset)] if section is not None else []


class BasedMudSupport:
    """Stato condiviso dai mixin: configurazione, archivio dei file, lock di scrittura."""

    def __init__(self, config: WorldConfig) -> None:
        """Risolve la cartella delle aree (`config.path`) e prepara l'archivio (nessuna lettura finche' non serve)."""
        self.config = config
        self.store = AreaStore(resolve_area_dir(config.path))
        self.lock = asyncio.Lock()
        """Un solo scrittore per volta: le scritture possono toccare piu' file (uscite entranti, spostamenti)."""

    def ensure_writable(self) -> None:
        """409 `world.read_only` se il mondo e' in sola lettura (ultima difesa dell'adapter)."""
        if self.config.read_only:
            raise api_error(409, "world.read_only")

    def sync(self) -> AreaStore:
        """Riallinea la cache al disco e restituisce l'archivio."""
        self.store.refresh()
        return self.store

    @asynccontextmanager
    async def writing(self) -> AsyncIterator[AreaStore]:
        """Sezione di scrittura: lock unico e cache aggiornata; se qualcosa fallisce la cache e' invalidata (le modifiche
        in memoria non salvate non devono restare ne' finire su disco al salvataggio successivo); `RomWriteError` diventa
        422 `basedmud.unsafe_text` (`basedmud.unencodable_text` per i caratteri fuori dall'encoding del file)."""
        async with self.lock:
            store = self.sync()
            try:
                yield store
            except RomUnencodableError as error:
                store.invalidate()
                raise api_error(422, "basedmud.unencodable_text", reason=str(error)) from error
            except RomWriteError as error:
                store.invalidate()
                raise api_error(422, "basedmud.unsafe_text", reason=str(error)) from error
            except BaseException:
                store.invalidate()
                raise

    # ------------------------------------------------------------------ ricerca per id

    def zone_or_404(self, zone_id: int) -> AreaEntry:
        """La zona `zone_id` (404 `zones.not_found`)."""
        entry = self.sync().zone_by_id(zone_id)
        if entry is None:
            raise api_error(404, "zones.not_found")
        return entry

    def find_or_404(self, kind: Kind, vnum: int, code: str) -> tuple[AreaEntry, Any]:
        """`(zona, elemento)` per vnum (404 `code`)."""
        found = self.sync().find(kind, vnum)
        if found is None:
            raise api_error(404, code)
        return found

    # ------------------------------------------------------------------ uso dei vnum

    def find_usage(self, kind: EntityKind, vnum: int, *, include_exit_keys: bool = True) -> list[ResetUsage]:
        """Reset (di ogni zona) che referenziano `vnum` come `kind`; per gli oggetti anche le chiavi delle uscite."""
        fields: dict[Any, list[str]] = {}
        for command_type, name in rules.USAGE_FIELDS[kind]:
            fields.setdefault(command_type, []).append(name)
        usage: list[ResetUsage] = []
        for entry in self.store.zones:
            for index, reset in enumerate(real_resets(entry)):
                out = reset_out(entry.zone_id, index, reset)
                if out.command_type in fields and any(getattr(out, f) == vnum for f in fields[out.command_type]):
                    usage.append(
                        ResetUsage(
                            zone_id=entry.zone_id,
                            zone_name=entry.header.name,
                            reset_command_id=index,
                            order_index=index,
                            command_type=out.command_type,
                        )
                    )
        if kind == "object" and include_exit_keys:
            for entry in self.store.zones:
                for room in entry.items("room"):
                    usage.extend(
                        ResetUsage(
                            zone_id=entry.zone_id,
                            zone_name=entry.header.name,
                            source="exit_key",
                            exit_id=room.vnum * 10 + x.door,
                            room_id=room.vnum,
                            room_vnum=room.vnum,
                        )
                        for x in room.exits
                        if x.key == vnum and vnum > 0
                    )
        return usage

    def ensure_unused(self, kind: EntityKind, vnum: int, code: str, *, include_exit_keys: bool = True) -> None:
        """409 `code` se `vnum` e' referenziato (reset e, per gli oggetti, chiavi di uscite)."""
        rules.raise_if_used(self.find_usage(kind, vnum, include_exit_keys=include_exit_keys), code)

    def check_vnum_in_range(self, entry: AreaEntry, vnum: int) -> None:
        """422 `basedmud.vnum_out_of_range` se la zona dichiara un range e `vnum` ne e' fuori."""
        header = entry.header
        if (header.min_vnum, header.max_vnum) != (0, 0) and not header.min_vnum <= vnum <= header.max_vnum:
            raise api_error(422, "basedmud.vnum_out_of_range", vnum=vnum, bottom=header.min_vnum, top=header.max_vnum)


class BasedMudResetLookup:
    """`rules.ResetLookup` sui file `.are`."""

    def __init__(self, store: AreaStore) -> None:
        """Usa l'archivio (gia' sincronizzato) per le verifiche di esistenza."""
        self.store = store

    async def existing_vnums(self, kind: EntityKind, vnums: set[int]) -> set[int]:
        """Quali tra `vnums` esistono come stanza/mob/oggetto in qualsiasi zona."""
        return {v for v in vnums if self.store.find(kind, v) is not None}

    async def exit_has_door(self, room_vnum: int, direction: int) -> bool | None:
        """`None` se la stanza non ha l'uscita, altrimenti se e' una porta."""
        found = self.store.find("room", room_vnum)
        exit_ = found[1].exit_for(Direction(direction).value) if found else None
        return None if exit_ is None else exit_.is_door
