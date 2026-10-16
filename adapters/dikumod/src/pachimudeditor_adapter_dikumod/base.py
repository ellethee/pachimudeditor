"""Supporto comune ai mixin di `DikumodAdapter`: archivio, lock di scrittura, ricerca per id, uso dei vnum, range di zona."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pachimudeditor_adapter_dikumod.dikumod_lib import DikumodWriteError, Raw
from pachimudeditor_adapter_dikumod.dikumod_lib import DEFAULT_PREFIX, validate_prefix
from pachifast.i18n import api_error

from pachimudeditor_adapter_dikumod import mapping
from pachimudeditor_adapter_dikumod.store import DikumodStore, Ref, ZoneRef, resolve
from pachimudeditor.sdk import rules
from pachimudeditor.common.adapters.models import EntityKind, ResetUsage
from pachimudeditor.sdk import WorldConfig

VARIANTS = ("dikumod", "dikumod2")


class DikumodSupport:
    """Stato condiviso dai mixin: configurazione, archivio dei file, lock di scrittura."""

    def __init__(self, config: WorldConfig) -> None:
        """Risolve `lib/` (`config.path`), legge `params.variant` e `params.data_prefix` e decide la sola lettura (**vero se non configurato**)."""
        self.config = config
        prefix = validate_prefix(config.params.get("data_prefix", DEFAULT_PREFIX))
        self.store = DikumodStore(resolve(config.path, prefix), prefix)
        self.lock = asyncio.Lock()
        """Un solo scrittore per volta: una scrittura puo' toccare piu' file (uscite entranti, negozio, script)."""
        self.read_only = config.read_only if "read_only" in config.model_fields_set else True
        variant = config.params.get("variant")
        if variant is not None and variant not in VARIANTS:
            raise ValueError(f"params.variant deve essere uno tra {VARIANTS}, non {variant!r}")
        self.variant: str = variant or ("dikumod2" if self.store.paths.gui.exists() or self.store.paths.overrides("room") else "dikumod")

    # ------------------------------------------------------------------ scrittura

    def ensure_writable(self) -> None:
        """409 `world.read_only` se il mondo e' in sola lettura (ultima difesa dell'adapter)."""
        if self.read_only:
            raise api_error(409, "world.read_only")

    def sync(self) -> DikumodStore:
        """Riallinea la cache al disco e restituisce l'archivio."""
        self.store.refresh()
        return self.store

    @asynccontextmanager
    async def writing(self) -> AsyncIterator[DikumodStore]:
        """Sezione di scrittura: controllo `read_only`, lock unico, cache aggiornata; se qualcosa fallisce la cache e'
        invalidata (le modifiche in memoria non salvate non devono sopravvivere) e `DikumodWriteError` diventa 422."""
        self.ensure_writable()
        async with self.lock:
            store = self.sync()
            try:
                yield store
            except DikumodWriteError as error:
                store.invalidate()
                raise api_error(422, "dikumod.unsafe_text", reason=str(error)) from error
            except BaseException:
                store.invalidate()
                raise

    # ------------------------------------------------------------------ ricerca per id

    def zone_or_404(self, zone_id: int) -> ZoneRef:
        """La zona `zone_id` (indice di posizione); 404 `zones.not_found`."""
        zone = self.sync().zone(zone_id)
        if zone is None:
            raise api_error(404, "zones.not_found")
        return zone

    def editable_zone(self, zone_id: int) -> ZoneRef:
        """Come `zone_or_404` ma 409 `dikumod.record_corrupted` se la zona e' illeggibile."""
        zone = self.zone_or_404(zone_id)
        if zone.raw:
            raise api_error(409, "dikumod.record_corrupted", vnum=zone.item.vnum, reason=zone.item.error)  # type: ignore[union-attr]
        return zone

    def find_or_404(self, kind: EntityKind, vnum: int, code: str) -> Ref:
        """`Ref` di stanza/mob/oggetto per vnum (404 `code`). Un mob corrotto non e' qui (vedi `corrupted`)."""
        store = self.sync()
        ref = {"room": store.rooms, "mob": store.mobs, "object": store.objs}[kind].get(vnum)
        if ref is None:
            raise api_error(404, code)
        return ref

    def corrupted(self, vnum: int) -> Raw | None:
        """Il mob corrotto con quel vnum (se non c'e' un record sano con lo stesso vnum)."""
        store = self.sync()
        return store.raw_mobs.get(vnum) if vnum not in store.mobs else None

    def zone_id_of(self, vnum: int) -> int:
        """L'indice della zona che possiede `vnum`, `-1` se e' oltre l'ultima zona."""
        z = self.store.zone_of(vnum)
        return -1 if z is None else z

    def check_vnum_in_zone(self, zone_id: int, vnum: int) -> None:
        """422 `dikumod.zone_derived` se `zone_id` non e' la zona di `vnum`; 422 `dikumod.vnum_out_of_range` se nessuna lo e'."""
        owner = self.store.zone_of(vnum)
        if owner is None:
            raise api_error(422, "dikumod.vnum_out_of_range", vnum=vnum, bottom="-", top=self.store.tops[-1] if self.store.tops else "-")
        if owner != zone_id:
            low, high = self.store.bounds(zone_id) if 0 <= zone_id < len(self.store.zones) else (0, 0)
            raise api_error(422, "dikumod.vnum_out_of_range", vnum=vnum, bottom=low, top=high)

    # ------------------------------------------------------------------ uso dei vnum

    def find_usage(self, kind: EntityKind, vnum: int, *, include_exit_keys: bool = True) -> list[ResetUsage]:
        """Comandi (di ogni zona) che referenziano `vnum` come `kind`; per gli oggetti anche le chiavi delle uscite."""
        fields: dict[Any, list[str]] = {}
        for command_type, name in rules.USAGE_FIELDS[kind]:
            fields.setdefault(command_type, []).append(name)
        usage: list[ResetUsage] = []
        for zone in self.store.zones:
            name = zone.item.name if hasattr(zone.item, "name") else f"#{zone.index}"
            for index, cmd in enumerate(zone.commands()):
                out = mapping.reset_out(zone.index, index, cmd)
                hit = any(getattr(out, f) == vnum for f in fields.get(out.command_type, ()))
                if kind == "mob" and not hit:
                    hit = (out.command_type == rules.CHARM_MOB and out.arg1 == vnum) or (
                        out.command_type in (rules.SET_HATE, rules.SET_FEAR) and out.arg1 == rules.HATE_FEAR_MOB_TYPE and out.arg2 == vnum
                    )
                if hit:
                    usage.append(
                        ResetUsage(
                            zone_id=zone.index, zone_name=name, reset_command_id=index, order_index=index, command_type=out.command_type
                        )
                    )
        if kind == "object" and include_exit_keys and vnum > 0:
            for room_vnum, ref in sorted(self.store.rooms.items()):
                zid = self.zone_id_of(room_vnum)
                zone = self.store.zone(zid)
                usage.extend(
                    ResetUsage(
                        zone_id=zid, zone_name=getattr(zone.item, "name", "") if zone else "", source="exit_key",
                        exit_id=mapping.exit_id(room_vnum, x.door), room_id=room_vnum, room_vnum=room_vnum,
                    )
                    for x in ref.item.exits
                    if x.key == vnum
                )  # fmt: skip
        return usage

    def ensure_unused(self, kind: EntityKind, vnum: int, code: str, *, include_exit_keys: bool = True, skip_doors: bool = False) -> None:
        """409 `code` se `vnum` e' referenziato (con `skip_doors` i comandi `D` di una stanza non contano)."""
        usage = self.find_usage(kind, vnum, include_exit_keys=include_exit_keys)
        if skip_doors:
            from pachimudeditor.common.enums import ZoneCommandType

            usage = [u for u in usage if u.command_type != ZoneCommandType.SET_DOOR_STATE]
        rules.raise_if_used(usage, code)


class DikumodResetLookup:
    """`rules.ResetLookup` sui file Diku Modificato."""

    def __init__(self, store: DikumodStore) -> None:
        """Usa l'archivio (gia' sincronizzato)."""
        self.store = store

    async def existing_vnums(self, kind: EntityKind, vnums: set[int]) -> set[int]:
        """Quali tra `vnums` esistono come stanza/mob/oggetto."""
        index = {"room": self.store.rooms, "mob": self.store.mobs, "object": self.store.objs}[kind]
        return {v for v in vnums if v in index or (kind == "mob" and v in self.store.raw_mobs)}

    async def exit_has_door(self, room_vnum: int, direction: int) -> bool | None:
        """`None` se la stanza non ha l'uscita, altrimenti se e' una porta."""
        ref = self.store.rooms.get(room_vnum)
        ex = ref.item.exit_for(direction) if ref else None
        return None if ex is None else bool(ex.info & mapping.EX_ISDOOR)
