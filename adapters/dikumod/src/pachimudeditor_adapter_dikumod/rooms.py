"""Stanze, uscite ed extra description (mixin di `DikumodAdapter`).

Convenzioni degli `id`: stanza = vnum; uscita = `vnum * 10 + direzione`; extra description = `vnum * 1000 + posizione`
(cancellarne una fa scalare le successive). Una stanza con un file `rooms/<vnum>` viene letta e **scritta** li'. Lo stato
porta (`isOpen`/`isLocked`) e' nei bit `exit_info` del file ma i comandi `D` delle zone lo sovrascrivono al reset: viene
letto dal `D` se c'e', altrimenti dai bit; la scrittura aggiorna i bit e l'eventuale `D` esistente.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from pachimudeditor_adapter_dikumod.dikumod_lib import Exit, ExtraDesc, RecordFile, Room, insert_sorted
from pachifast.i18n import api_error
from pachifast.schemas.responses import PaginatedResponse
from pachimudeditor.common.enums import Direction

from pachimudeditor_adapter_dikumod import mapping
from pachimudeditor_adapter_dikumod.base import DikumodSupport
from pachimudeditor_adapter_dikumod.store import DikumodStore, Ref
from pachimudeditor.sdk import rules
from pachimudeditor.common.adapters.models import (
    ExitIn,
    ExitOut,
    ExitPatch,
    ExtraDescriptionIn,
    ExtraDescriptionOut,
    ExtraDescriptionPatch,
    ResetUsage,
    RoomCloneIn,
    RoomDetail,
    RoomGraph,
    RoomIn,
    RoomOut,
    RoomPageParams,
    RoomPatch,
)
from pachimudeditor.sdk import make_page, paginate_list
from pachimudeditor.sdk import conflict


def _drop(rf: RecordFile, item: Any) -> None:
    """Toglie `item` (per identita') dal file."""
    rf.items[:] = [i for i in rf.items if i is not item]


class RoomsMixin(DikumodSupport):
    """Operazioni su stanze, uscite ed extra description."""

    # ------------------------------------------------------------------ comandi D

    def _door_commands(self, room_vnum: int, door: int | None = None) -> list[tuple[Any, Any]]:
        """`(zona, comando D)` per la stanza (e direzione)."""
        return [
            (z, c)
            for z in self.store.zones
            for c in z.commands()
            if c.letter == "D" and len(c.args) >= 3 and c.args[0] == room_vnum and (door is None or c.args[1] == door)
        ]  # fmt: skip

    def _d_state(self, room_vnum: int, door: int) -> int | None:
        """Lo stato dell'ultimo `D` per la porta (0 aperta, 1 chiusa, 2 serrata) o `None`."""
        found = self._door_commands(room_vnum, door)
        return found[-1][1].args[2] if found else None

    def _save_zones(self, zones: set[Any], store: DikumodStore) -> None:
        """Salva `dikumoddata.zon` e/o i file `zones/<n>.zon` delle zone toccate."""
        if any(z.override is None for z in zones):
            store.save(store.zon)  # type: ignore[arg-type]
        for z in zones:
            if z.override is not None:
                store.save_zone_override(z)

    # ------------------------------------------------------------------ DTO

    def _exit_out(self, room: Room, ex: Exit) -> ExitOut:
        """DTO di un'uscita con la destinazione risolta."""
        names = {v: r.item.name for v, r in self.store.rooms.items()}
        return mapping.exit_out(room.vnum, ex, names, self._d_state(room.vnum, ex.door))

    def _detail(self, vnum: int) -> RoomDetail:
        """`RoomDetail` della stanza `vnum` (dall'archivio aggiornato)."""
        ref = self.find_or_404("room", vnum, "rooms.not_found")
        room: Room = ref.item
        base = mapping.room_out(room, self.zone_id_of(vnum), override=ref.override, duplicate=vnum in self.store.duplicates["room"])
        return RoomDetail(
            **base.model_dump(by_alias=False),
            exits=[self._exit_out(room, x) for x in sorted(room.exits, key=lambda e: e.door)],
            extra_descriptions=[mapping.extra_desc_out(vnum, i, e) for i, e in enumerate(room.extra_descs)],
        )

    # ------------------------------------------------------------------ stanze

    async def list_rooms(self, params: RoomPageParams) -> PaginatedResponse[RoomOut]:
        """Stanze paginate (ordine di default per vnum), filtro `zoneId`, ricerca su nome/vnum."""
        store = self.sync()
        refs = sorted(store.rooms.values(), key=lambda r: r.vnum)
        if params.zone_id is not None:
            refs = [r for r in refs if self.zone_id_of(r.vnum) == params.zone_id]
        keys = {"id": lambda r: r.vnum, "vnum": lambda r: r.vnum, "name": lambda r: r.item.name,
                "sector_type": lambda r: int(mapping.sector_out(r.item.sector))}  # fmt: skip
        items, total = paginate_list(
            refs, params, lambda r: (r.item.name, r.vnum), lambda r, f: keys[f](r), RoomPageParams.order_fields or []
        )
        dup = store.duplicates["room"]
        out = [mapping.room_out(r.item, self.zone_id_of(r.vnum), override=r.override, duplicate=r.vnum in dup) for r in items]
        return make_page(RoomOut, out, total, params)

    async def get_room(self, room_id: int) -> RoomDetail:
        """Una stanza con uscite ed extra description."""
        self.find_or_404("room", room_id, "rooms.not_found")
        return self._detail(room_id)

    async def create_room(self, data: RoomIn) -> RoomDetail:
        """Crea una stanza in `dikumoddata.wld` (vnum libero e nella zona indicata)."""
        values = data.model_dump(by_alias=False, exclude={"extra"})
        async with self.writing() as store:
            if data.vnum in store.rooms:
                raise conflict("rooms.vnum_taken", vnum=data.vnum)
            self.zone_or_404(data.zone_id)
            self.check_vnum_in_zone(data.zone_id, data.vnum)
            room = Room(vnum=data.vnum, zone_ignored=data.zone_id)
            mapping.apply_room_fields(room, values)
            mapping.apply_extra(data.extra, mapping.room_extra_handlers(room))
            insert_sorted(store.wld, room)  # type: ignore[arg-type]
            store.save(store.wld)  # type: ignore[arg-type]
            return self._detail(data.vnum)

    async def update_room(self, room_id: int, data: RoomPatch) -> RoomDetail:
        """Aggiornamento parziale. Cambiare il vnum e' 409 `rooms.vnum_in_use` se un reset (non `D`) lo usa; le uscite
        e i `D` che portano li' seguono. `zoneId` deve essere la zona del vnum (derivata). Una stanza con file
        `rooms/<vnum>` e' scritta li' e non puo' cambiare vnum (422 `dikumod.override_vnum_locked`)."""
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude={"extra"})
        async with self.writing() as store:
            ref = self.find_or_404("room", room_id, "rooms.not_found")
            room: Room = ref.item
            old, new = room.vnum, changes.get("vnum", room.vnum)
            touched: set[RecordFile] = set()
            touched_zones: set[Any] = set()
            before = repr(room)
            if new != old:
                if ref.override:
                    raise api_error(422, "dikumod.override_vnum_locked", vnum=old)
                if new in store.rooms:
                    raise conflict("rooms.vnum_taken", vnum=new)
                self.ensure_unused("room", old, "rooms.vnum_in_use", include_exit_keys=False, skip_doors=True)
                if store.zone_of(new) is None:
                    raise api_error(422, "dikumod.vnum_out_of_range", vnum=new, bottom="-", top=store.tops[-1] if store.tops else "-")
            want_zone = changes.get("zone_id")
            if want_zone is not None and want_zone != self.zone_id_of(new):
                raise api_error(422, "dikumod.zone_derived", vnum=new, expected=self.zone_id_of(new))
            mapping.apply_room_fields(room, changes)
            mapping.apply_extra(data.extra or {}, mapping.room_extra_handlers(room))
            if repr(room) != before:
                touched.add(ref.rf)
            if new != old:
                touched.add(ref.rf)
                room.vnum = new
                _drop(ref.rf, room)
                insert_sorted(ref.rf, room)
                for other in list(store.rooms.values()):
                    for x in other.item.exits:
                        if x.to_room == old:
                            x.to_room = new
                            touched.add(other.rf)
                for zone, cmd in self._door_commands(old):
                    cmd.args[0] = new
                    touched_zones.add(zone)
            if touched:
                store.save(*touched)
            if touched_zones:
                self._save_zones(touched_zones, store)
            return self._detail(new)

    async def delete_room(self, room_id: int) -> None:
        """Elimina la stanza (e il suo `rooms/<vnum>`): 409 `rooms.in_reset_usage` se un reset (non `D`) la usa. Le uscite
        di altre stanze verso di lei restano senza destinazione; i suoi comandi `D` vanno via."""
        async with self.writing() as store:
            self.find_or_404("room", room_id, "rooms.not_found")
            self.ensure_unused("room", room_id, "rooms.in_reset_usage", include_exit_keys=False, skip_doors=True)
            touched: set[RecordFile] = {store.wld}  # type: ignore[arg-type]
            store.wld.items[:] = [i for i in store.wld.items if getattr(i, "vnum", None) != room_id]  # type: ignore[union-attr]
            override_path = store.room_overrides.get(room_id)
            for other in store.rooms.values():
                if other.vnum == room_id:
                    continue
                for x in other.item.exits:
                    if x.to_room == room_id:
                        x.to_room = -1
                        touched.add(other.rf)
            zones: set[Any] = set()
            for zone, cmd in self._door_commands(room_id):
                zone.items()[:] = [i for i in zone.items() if i is not cmd]
                zones.add(zone)
            store.save(*touched)
            if zones:
                self._save_zones(zones, store)
            if override_path is not None:
                store.delete_file(override_path)

    async def clone_room(self, room_id: int, data: RoomCloneIn) -> RoomDetail:
        """Duplica la stanza (senza uscite, con le extra description) nello stesso file principale."""
        async with self.writing() as store:
            ref = self.find_or_404("room", room_id, "rooms.not_found")
            if data.vnum in store.rooms:
                raise conflict("rooms.vnum_taken", vnum=data.vnum)
            self.check_vnum_in_zone(self.zone_id_of(room_id), data.vnum)
            clone = dataclasses.replace(
                ref.item, vnum=data.vnum, name=data.name or ref.item.name, exits=[],
                extra_descs=[ExtraDesc(e.keyword, e.description) for e in ref.item.extra_descs], _src=None, _fp=None,
            )  # fmt: skip
            insert_sorted(store.wld, clone)  # type: ignore[arg-type]
            store.save(store.wld)  # type: ignore[arg-type]
            return self._detail(data.vnum)

    async def room_graph(self, zone_id: int) -> RoomGraph:
        """Stanze della zona e uscite tra loro, con layout a bussola calcolato dal server."""
        store = self.sync()
        self.zone_or_404(zone_id)
        refs = sorted((r for r in store.rooms.values() if store.zone_of(r.vnum) == zone_id), key=lambda r: r.vnum)
        exits = [
            rules.GraphExit(
                mapping.exit_id(r.vnum, x.door), r.vnum, Direction(x.door), mapping.door_flag_out(x.info),
                x.to_room if x.to_room in store.rooms else None,
            )
            for r in refs
            for x in r.item.exits
        ]  # fmt: skip
        rooms = [rules.GraphRoom(r.vnum, r.vnum, r.item.name, mapping.sector_out(r.item.sector), [])
                 for r in refs]  # fmt: skip
        from pachimudeditor_adapter_dikumod.dikumod_lib import tables as T

        rooms = [dataclasses.replace(g, flags=T.flag_names(T.ROOM_FLAGS, store.rooms[g.vnum].item.flags)) for g in rooms]
        return rules.build_room_graph(rooms, exits)

    async def room_usage(self, room_id: int) -> list[ResetUsage]:
        """I comandi che referenziano la stanza per vnum."""
        self.find_or_404("room", room_id, "rooms.not_found")
        return self.find_usage("room", room_id, include_exit_keys=False)

    # ------------------------------------------------------------------ uscite

    def _exit_or_404(self, room_id: int, exit_id: int) -> tuple[Ref, Exit]:
        """`(stanza, uscita)` per `exit_id`: 404 `rooms.exit_not_found`, 409 `rooms.exit_not_in_room`."""
        store = self.sync()
        ref = store.rooms.get(exit_id // mapping.EXIT_STRIDE) if exit_id >= 0 else None
        ex = ref.item.exit_for(exit_id % mapping.EXIT_STRIDE) if ref else None
        if ref is None or ex is None:
            raise api_error(404, "rooms.exit_not_found")
        if ref.vnum != room_id:
            raise conflict("rooms.exit_not_in_room")
        return ref, ex

    def _key_exists(self):  # type: ignore[no-untyped-def]
        """Callback di `rules.check_exit`: la chiave deve esistere come oggetto."""

        async def exists(vnum: int) -> bool:
            """Esiste un oggetto con quel vnum?"""
            return vnum in self.store.objs

        return exists

    def _check_target(self, target_room_id: int | None) -> None:
        """404 `rooms.not_found` se la destinazione non esiste."""
        if target_room_id is not None and target_room_id not in self.store.rooms:
            raise api_error(404, "rooms.not_found")

    def _exit_by_id(self, exit_id: int) -> ExitOut:
        """`ExitOut` da un id (dall'archivio aggiornato)."""
        ref = self.find_or_404("room", exit_id // mapping.EXIT_STRIDE, "rooms.not_found")
        return self._exit_out(ref.item, ref.item.exit_for(exit_id % mapping.EXIT_STRIDE))  # type: ignore[arg-type]

    def _set_d_states(self, room: int, door: int, is_open: bool, is_locked: bool) -> set[Any]:
        """Allinea i comandi `D` esistenti alla porta; restituisce le zone toccate."""
        state = 2 if is_locked else (0 if is_open else 1)
        zones: set[Any] = set()
        for zone, cmd in self._door_commands(room, door):
            if cmd.args[2] != state:
                cmd.args[2] = state
                zones.add(zone)
        return zones

    async def create_exit(self, room_id: int, data: ExitIn) -> ExitOut:
        """Crea un'uscita (una per direzione); lo stato porta va nei bit `exit_info`."""
        async with self.writing() as store:
            ref = self.find_or_404("room", room_id, "rooms.not_found")
            room: Room = ref.item
            if room.exit_for(int(data.direction)) is not None:
                raise conflict("rooms.exit_direction_taken", direction=data.direction.name)
            await rules.check_exit(room_id, data.model_dump(by_alias=False), set(ExitIn.model_fields), self._key_exists())
            self._check_target(data.target_room_id)
            room.exits.append(
                Exit(
                    door=int(data.direction),
                    description=mapping.clean_text(data.description or "", newline=True, lstrip=True),
                    keyword=mapping.clean_text(data.keywords or ""),
                    info=mapping.info_from(data.door_flag, data.is_open, data.is_locked, 0),
                    key=data.key_vnum if data.key_vnum is not None else -1,
                    to_room=data.target_room_id if data.target_room_id is not None else -1,
                )
            )
            room.exits.sort(key=lambda x: x.door)
            store.save(ref.rf)
            return self._exit_by_id(mapping.exit_id(room_id, int(data.direction)))

    async def update_exit(self, room_id: int, exit_id: int, data: ExitPatch) -> ExitOut:
        """Aggiornamento parziale di un'uscita (cambiando direzione cambia anche l'`id`). `extra`: `exitInfo` (bit
        grezzi, prevalgono su porta/stato) e `openCmd`."""
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude={"extra"})
        async with self.writing() as store:
            ref, ex = self._exit_or_404(room_id, exit_id)
            room: Room = ref.item
            current = self._exit_by_id(exit_id)
            if "direction" in changes and changes["direction"] != current.direction:
                if room.exit_for(int(changes["direction"])) is not None:
                    raise conflict("rooms.exit_direction_taken", direction=changes["direction"].name)
            final = {name: changes.get(name, getattr(current, name)) for name in ExitIn.model_fields}
            await rules.check_exit(room_id, final, set(changes), self._key_exists())
            if "target_room_id" in changes:
                self._check_target(changes["target_room_id"])
            old_door = ex.door
            if "direction" in changes:
                ex.door = int(changes["direction"])
            if "description" in changes:
                ex.description = mapping.clean_text(changes["description"] or "", newline=True, lstrip=True)
            if "keywords" in changes:
                ex.keyword = mapping.clean_text(changes["keywords"] or "")
            door_touched = changes.keys() & {"door_flag", "is_open", "is_locked"}
            if door_touched:
                ex.info = mapping.info_from(final["door_flag"], final["is_open"], final["is_locked"], ex.info)
            if "key_vnum" in changes:
                ex.key = changes["key_vnum"] if changes["key_vnum"] is not None else -1
            if "target_room_id" in changes:
                ex.to_room = changes["target_room_id"] if changes["target_room_id"] is not None else -1
            for key, value in (data.extra or {}).items():
                if key == "exitInfo":
                    ex.info = mapping._int("exitInfo", value, 0)
                elif key == "openCmd":
                    ex.open_cmd = None if value is None else mapping._int("openCmd", value)
                elif key != "dState":
                    raise api_error(422, "dikumod.extra_unknown", key=key, known="exitInfo, openCmd")
            room.exits.sort(key=lambda x: x.door)
            zones: set[Any] = set()
            if ex.door != old_door:
                for zone, cmd in self._door_commands(room_id, old_door):
                    cmd.args[1] = ex.door
                    zones.add(zone)
            if door_touched or "exitInfo" in (data.extra or {}):
                zones |= self._set_d_states(room_id, ex.door, *mapping.door_state(ex.info, None))
            store.save(ref.rf)
            if zones:
                self._save_zones(zones, store)
            return self._exit_by_id(mapping.exit_id(room_id, ex.door))

    async def delete_exit(self, room_id: int, exit_id: int) -> None:
        """Elimina un'uscita (i suoi comandi `D` restano: segnalati dalla validazione)."""
        async with self.writing() as store:
            ref, ex = self._exit_or_404(room_id, exit_id)
            ref.item.exits.remove(ex)
            store.save(ref.rf)

    # ------------------------------------------------------------------ extra description

    def _extra_or_404(self, room_id: int, extra_id: int) -> tuple[Ref, int]:
        """`(stanza, posizione)`: 404 `rooms.extra_not_found`, 409 `rooms.extra_not_in_room`."""
        store = self.sync()
        stride = mapping.EXTRA_DESC_STRIDE
        ref = store.rooms.get(extra_id // stride) if extra_id >= 0 else None
        index = extra_id % stride
        if ref is None or index >= len(ref.item.extra_descs):
            raise api_error(404, "rooms.extra_not_found")
        if ref.vnum != room_id:
            raise conflict("rooms.extra_not_in_room")
        return ref, index

    async def create_extra_description(self, room_id: int, data: ExtraDescriptionIn) -> ExtraDescriptionOut:
        """Aggiunge un'extra description in coda."""
        async with self.writing() as store:
            ref = self.find_or_404("room", room_id, "rooms.not_found")
            ref.item.extra_descs.append(ExtraDesc(mapping.clean_text(data.keywords), mapping.clean_text(data.text, newline=True)))
            index = len(ref.item.extra_descs) - 1
            store.save(ref.rf)
            return mapping.extra_desc_out(room_id, index, self.store.rooms[room_id].item.extra_descs[index])

    async def update_extra_description(self, room_id: int, extra_id: int, data: ExtraDescriptionPatch) -> ExtraDescriptionOut:
        """Aggiornamento parziale di un'extra description."""
        changes: dict[str, Any] = data.model_dump(by_alias=False, exclude_unset=True)
        async with self.writing() as store:
            ref, index = self._extra_or_404(room_id, extra_id)
            extra = ref.item.extra_descs[index]
            if "keywords" in changes:
                extra.keyword = mapping.clean_text(changes["keywords"])
            if "text" in changes:
                extra.description = mapping.clean_text(changes["text"], newline=True)
            store.save(ref.rf)
            return mapping.extra_desc_out(room_id, index, self.store.rooms[room_id].item.extra_descs[index])

    async def delete_extra_description(self, room_id: int, extra_id: int) -> None:
        """Elimina un'extra description (le successive scalano di una posizione)."""
        async with self.writing() as store:
            ref, index = self._extra_or_404(room_id, extra_id)
            del ref.item.extra_descs[index]
            store.save(ref.rf)
