"""Stanze, uscite ed extra description (mixin di `BasedMudAdapter`).

Convenzioni degli `id`: stanza = vnum; uscita = `vnum * 10 + direzione`; extra description = `vnum * 1000 + posizione`
nella lista della stanza (cancellare una extra fa scalare le successive). Lo stato porta (`isOpen`/`isLocked`) vive nei
reset `D` della zona della stanza: viene letto da li' e scritto li' (nessun `D` = porta aperta).
"""

import dataclasses
from typing import Any

from pachimudeditor_adapter_basedmud.rom_lib import Exit, ExtraDescription, Reset, Room
from pachifast.i18n import api_error
from pachifast.schemas.responses import PaginatedResponse
from pachimudeditor.common.enums import ZoneCommandType
from pachimudeditor.common.enums import Direction

from pachimudeditor_adapter_basedmud import mapping
from pachimudeditor_adapter_basedmud.base import BasedMudSupport, make_page, paginate_list
from pachimudeditor_adapter_basedmud.store import AreaEntry
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
from pachimudeditor.sdk import conflict


def _door_resets(entry: AreaEntry) -> list[Reset]:
    """I reset `D` dell'area."""
    section = entry.area.section("RESETS", create=False)
    return [r for r in (section.items if section else []) if isinstance(r, Reset) and r.command == "D"]


def set_door_state(entry: AreaEntry, room_vnum: int, door: int, is_open: bool, is_locked: bool) -> None:
    """Allinea il reset `D` di (stanza, direzione): 0 aperta (nessun reset), 1 chiusa, 2 chiusa e serrata."""
    want = 2 if is_locked else (0 if is_open else 1)
    current = next((r for r in _door_resets(entry) if r.args[1] == room_vnum and r.args[2] == door), None)
    if current is None:
        if want:
            entry.area.resets.append(Reset.make("D", room_vnum=room_vnum, direction=door, locks=want))
    elif want == 0:
        entry.area.resets.remove(current)
    elif current.args[3] != want:
        current.args[3] = want


def drop_door_resets(entry: AreaEntry, room_vnum: int, door: int | None = None) -> bool:
    """Toglie i reset `D` della stanza (di una sola direzione se `door`); True se ne ha tolto qualcuno."""
    gone = [r for r in _door_resets(entry) if r.args[1] == room_vnum and (door is None or r.args[2] == door)]
    for reset in gone:
        entry.area.resets.remove(reset)
    return bool(gone)


class RoomsMixin(BasedMudSupport):
    """Operazioni su stanze, uscite ed extra description."""

    # ------------------------------------------------------------------ DTO

    def _door_lock(self, entry: AreaEntry, room_vnum: int, door: int) -> int | None:
        """Il valore del reset `D` per la porta (None = nessun reset)."""
        found = next((r for r in _door_resets(entry) if r.args[1] == room_vnum and r.args[2] == door), None)
        return found.args[3] if found else None

    def _exit_out(self, entry: AreaEntry, room: Room, exit_: Exit) -> ExitOut:
        """DTO di un'uscita con la destinazione risolta."""
        names = self.store.rooms_names()
        return mapping.exit_out(room.vnum, exit_, names, self._door_lock(entry, room.vnum, exit_.door))

    def _detail(self, vnum: int) -> RoomDetail:
        """`RoomDetail` della stanza `vnum` (letta dall'archivio aggiornato)."""
        entry, room = self.find_or_404("room", vnum, "rooms.not_found")
        base = mapping.room_out(room, entry.zone_id).model_dump(by_alias=False)
        return RoomDetail(
            **base,
            exits=[self._exit_out(entry, room, x) for x in sorted(room.exits, key=lambda e: e.door) if 0 <= x.door <= 5],
            extra_descriptions=[mapping.extra_desc_out(room.vnum, i, e) for i, e in enumerate(room.extra_descs)],
        )

    # ------------------------------------------------------------------ stanze

    async def list_rooms(self, params: RoomPageParams) -> PaginatedResponse[RoomOut]:
        """Stanze paginate (ordine di default per vnum), filtro `zoneId`, ricerca su nome/vnum."""
        self.sync()
        pairs = self.store.all_items("room")
        if params.zone_id is not None:
            pairs = [p for p in pairs if p[0].zone_id == params.zone_id]
        keys = {
            "id": lambda r: r.vnum, "vnum": lambda r: r.vnum, "name": lambda r: r.name,
            "sector_type": lambda r: int(mapping.sector_out(r.sector)),
        }  # fmt: skip
        items, total = paginate_list(
            pairs, params, lambda p: (p[1].name, p[1].vnum), lambda p, f: keys[f](p[1]), RoomPageParams.order_fields or []
        )
        return make_page(RoomOut, [mapping.room_out(r, e.zone_id) for e, r in items], total, params)

    async def get_room(self, room_id: int) -> RoomDetail:
        """Una stanza con uscite ed extra description."""
        self.find_or_404("room", room_id, "rooms.not_found")
        return self._detail(room_id)

    async def create_room(self, data: RoomIn) -> RoomDetail:
        """Crea una stanza nella zona (vnum libero e dentro il range della zona)."""
        self.ensure_writable()
        values = data.model_dump(by_alias=False, exclude={"extra"})
        async with self.writing():
            self.sync()
            if self.store.find("room", data.vnum) is not None:
                raise conflict("rooms.vnum_taken", vnum=data.vnum)
            entry = self.zone_or_404(data.zone_id)
            self.check_vnum_in_range(entry, data.vnum)
            first = next(iter(entry.items("room")), None)
            room = Room(vnum=data.vnum, area_number=first.area_number if first else 0)
            mapping.apply_room_fields(room, values)
            mapping.apply_room_extra(room, data.extra)
            entry.writable_items("room").append(room)
            self.store.save(entry)
            return self._detail(data.vnum)

    async def update_room(self, room_id: int, data: RoomPatch) -> RoomDetail:
        """Aggiornamento parziale. Cambiare il vnum e' 409 `rooms.vnum_in_use` se un reset lo usa; le uscite di altre
        stanze che portano qui seguono il nuovo vnum. `zoneId` sposta la stanza in un altro file."""
        self.ensure_writable()
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude={"extra"})
        async with self.writing():
            entry, room = self.find_or_404("room", room_id, "rooms.not_found")
            old_vnum, touched = room.vnum, {entry}
            target = entry
            new_vnum = changes.get("vnum", old_vnum)
            if new_vnum != old_vnum:
                if self.store.find("room", new_vnum) is not None:
                    raise conflict("rooms.vnum_taken", vnum=new_vnum)
                self.ensure_unused("room", old_vnum, "rooms.vnum_in_use", include_exit_keys=False)
            if changes.get("zone_id", entry.zone_id) != entry.zone_id:
                target = self.zone_or_404(changes["zone_id"])
                touched.add(target)
            if new_vnum != old_vnum or target is not entry:
                self.check_vnum_in_range(target, new_vnum)
            mapping.apply_room_fields(room, changes)
            mapping.apply_room_extra(room, data.extra or {})
            if new_vnum != old_vnum:
                room.vnum = new_vnum
                for other, other_room in self.store.all_items("room"):
                    for x in other_room.exits:
                        if x.to_vnum == old_vnum:
                            x.to_vnum = new_vnum
                            touched.add(other)
                for zone in self.store.zones:  # i reset D della stanza seguono il nuovo vnum
                    for reset in _door_resets(zone):
                        if reset.args[1] == old_vnum:
                            reset.args[1] = new_vnum
                            touched.add(zone)
            if target is not entry:
                entry.remove("room", room)
                target.writable_items("room").append(room)
            self.store.save(*touched)
            return self._detail(new_vnum)

    async def delete_room(self, room_id: int) -> None:
        """Elimina la stanza: 409 `rooms.in_reset_usage` se un reset (diverso dai `D` delle sue porte, che vanno
        via con lei) la referenzia. Le uscite di altre stanze verso di lei restano senza destinazione."""
        self.ensure_writable()
        async with self.writing():
            entry, room = self.find_or_404("room", room_id, "rooms.not_found")
            usage = [
                u for u in self.find_usage("room", room_id, include_exit_keys=False)
                if u.command_type is not ZoneCommandType.SET_DOOR_STATE
            ]  # fmt: skip
            rules.raise_if_used(usage, "rooms.in_reset_usage")
            touched = {entry}
            entry.remove("room", room)
            for zone in self.store.zones:
                if drop_door_resets(zone, room_id):
                    touched.add(zone)
            for other, other_room in self.store.all_items("room"):
                for x in other_room.exits:
                    if x.to_vnum == room_id:
                        x.to_vnum = -1
                        touched.add(other)
            self.store.save(*touched)

    async def clone_room(self, room_id: int, data: RoomCloneIn) -> RoomDetail:
        """Duplica la stanza nella stessa zona (senza uscite, con le extra description)."""
        self.ensure_writable()
        async with self.writing():
            entry, room = self.find_or_404("room", room_id, "rooms.not_found")
            if self.store.find("room", data.vnum) is not None:
                raise conflict("rooms.vnum_taken", vnum=data.vnum)
            self.check_vnum_in_range(entry, data.vnum)
            clone = dataclasses.replace(
                room,
                vnum=data.vnum,
                name=data.name or room.name,
                exits=[],
                extra_descs=[ExtraDescription(e.keyword, e.description) for e in room.extra_descs],
                _src=None,
                _fp=None,
            )
            entry.writable_items("room").append(clone)
            self.store.save(entry)
            return self._detail(data.vnum)

    async def room_graph(self, zone_id: int) -> RoomGraph:
        """Stanze della zona e uscite tra loro, con layout a bussola calcolato dal server."""
        entry = self.zone_or_404(zone_id)
        rooms = entry.items("room")
        exits = [
            rules.GraphExit(
                mapping.exit_id(r.vnum, x.door), r.vnum, Direction(x.door), mapping.door_flag_out(x),
                x.to_vnum if self.store.find("room", x.to_vnum) else None,
            )
            for r in rooms
            for x in r.exits
            if 0 <= x.door <= 5
        ]  # fmt: skip
        return rules.build_room_graph(
            [rules.GraphRoom(r.vnum, r.vnum, r.name, mapping.sector_out(r.sector), r.flag_names) for r in rooms], exits
        )

    async def room_usage(self, room_id: int) -> list[ResetUsage]:
        """I reset che referenziano la stanza per vnum."""
        self.find_or_404("room", room_id, "rooms.not_found")
        return self.find_usage("room", room_id, include_exit_keys=False)

    # ------------------------------------------------------------------ uscite

    def _exit_or_404(self, room_id: int, exit_id: int) -> tuple[AreaEntry, Room, Exit]:
        """`(zona, stanza, uscita)` per `exit_id`: 404 `rooms.exit_not_found`, 409 `rooms.exit_not_in_room`."""
        self.sync()
        found = self.store.find("room", exit_id // mapping.EXIT_STRIDE)
        exit_ = found[1].exit_for(exit_id % mapping.EXIT_STRIDE) if found and exit_id >= 0 else None
        if found is None or exit_ is None:
            raise api_error(404, "rooms.exit_not_found")
        if found[1].vnum != room_id:
            raise conflict("rooms.exit_not_in_room")
        return found[0], found[1], exit_

    def _key_exists(self):  # type: ignore[no-untyped-def]
        """Callback `rules.check_exit`: la chiave deve esistere come oggetto."""

        async def exists(vnum: int) -> bool:
            """Esiste un oggetto con quel vnum?"""
            return self.store.find("object", vnum) is not None

        return exists

    def _check_target(self, target_room_id: int | None) -> None:
        """404 `rooms.not_found` se la destinazione non esiste."""
        if target_room_id is not None and self.store.find("room", target_room_id) is None:
            raise api_error(404, "rooms.not_found")

    async def create_exit(self, room_id: int, data: ExitIn) -> ExitOut:
        """Crea un'uscita (una per direzione); lo stato porta va nel reset `D` della zona."""
        self.ensure_writable()
        async with self.writing():
            entry, room = self.find_or_404("room", room_id, "rooms.not_found")
            if room.exit_for(int(data.direction)) is not None:
                raise conflict("rooms.exit_direction_taken", direction=data.direction.name)
            await rules.check_exit(room_id, data.model_dump(by_alias=False), set(ExitIn.model_fields), self._key_exists())
            self._check_target(data.target_room_id)
            room.exits.append(
                Exit(
                    door=int(data.direction),
                    description=data.description or "",
                    keyword=data.keywords or "",
                    locks=mapping.locks_from(data.door_flag),
                    key=data.key_vnum if data.key_vnum is not None else -1,
                    to_vnum=data.target_room_id if data.target_room_id is not None else -1,
                )
            )
            room.exits.sort(key=lambda x: x.door)
            set_door_state(entry, room_id, int(data.direction), data.is_open, data.is_locked)
            self.store.save(entry)
            return self._exit_by_id(mapping.exit_id(room_id, int(data.direction)))

    def _exit_by_id(self, exit_id: int) -> ExitOut:
        """`ExitOut` da un id (letto dall'archivio aggiornato)."""
        entry, room = self.find_or_404("room", exit_id // mapping.EXIT_STRIDE, "rooms.not_found")
        return self._exit_out(entry, room, room.exit_for(exit_id % mapping.EXIT_STRIDE))  # type: ignore[arg-type]

    async def update_exit(self, room_id: int, exit_id: int, data: ExitPatch) -> ExitOut:
        """Aggiornamento parziale di un'uscita (cambiando direzione cambia anche l'`id`)."""
        self.ensure_writable()
        changes = data.model_dump(by_alias=False, exclude_unset=True)
        async with self.writing():
            entry, room, exit_ = self._exit_or_404(room_id, exit_id)
            current = self._exit_by_id(exit_id)
            if "direction" in changes and changes["direction"] != current.direction:
                if room.exit_for(int(changes["direction"])) is not None:
                    raise conflict("rooms.exit_direction_taken", direction=changes["direction"].name)
            final = {name: changes.get(name, getattr(current, name)) for name in ExitIn.model_fields}
            await rules.check_exit(room_id, final, set(changes), self._key_exists())
            if "target_room_id" in changes:
                self._check_target(changes["target_room_id"])
            old_door = exit_.door
            if "direction" in changes:
                exit_.door = int(changes["direction"])
            if "description" in changes:
                exit_.description = changes["description"] or ""
            if "keywords" in changes:
                exit_.keyword = changes["keywords"] or ""
            if "door_flag" in changes:
                exit_.locks = mapping.locks_from(changes["door_flag"], exit_.locks)
            if "key_vnum" in changes:
                exit_.key = changes["key_vnum"] if changes["key_vnum"] is not None else -1
            if "target_room_id" in changes:
                exit_.to_vnum = changes["target_room_id"] if changes["target_room_id"] is not None else -1
            room.exits.sort(key=lambda x: x.door)
            if changes.keys() & {"direction", "door_flag", "is_open", "is_locked"}:
                if exit_.door != old_door:
                    drop_door_resets(entry, room_id, old_door)
                set_door_state(entry, room_id, exit_.door, final["is_open"], final["is_locked"])
            self.store.save(entry)
            return self._exit_by_id(mapping.exit_id(room_id, exit_.door))

    async def delete_exit(self, room_id: int, exit_id: int) -> None:
        """Elimina un'uscita (e il suo reset `D`)."""
        self.ensure_writable()
        async with self.writing():
            entry, room, exit_ = self._exit_or_404(room_id, exit_id)
            room.exits.remove(exit_)
            drop_door_resets(entry, room_id, exit_.door)
            self.store.save(entry)

    # ------------------------------------------------------------------ extra description

    def _extra_or_404(self, room_id: int, extra_id: int) -> tuple[AreaEntry, Room, ExtraDescription, int]:
        """`(zona, stanza, extra, posizione)`: 404 `rooms.extra_not_found`, 409 `rooms.extra_not_in_room`."""
        self.sync()
        stride = mapping.EXTRA_DESC_STRIDE
        found = self.store.find("room", extra_id // stride) if extra_id >= 0 else None
        index = extra_id % stride
        if found is None or index >= len(found[1].extra_descs):
            raise api_error(404, "rooms.extra_not_found")
        if found[1].vnum != room_id:
            raise conflict("rooms.extra_not_in_room")
        return found[0], found[1], found[1].extra_descs[index], index

    async def create_extra_description(self, room_id: int, data: ExtraDescriptionIn) -> ExtraDescriptionOut:
        """Aggiunge un'extra description in coda."""
        self.ensure_writable()
        async with self.writing():
            entry, room = self.find_or_404("room", room_id, "rooms.not_found")
            room.extra_descs.append(ExtraDescription(data.keywords, data.text))
            index = len(room.extra_descs) - 1
            self.store.save(entry)
            return self._extra_out(room_id, index)

    def _extra_out(self, room_id: int, index: int) -> ExtraDescriptionOut:
        """DTO dell'extra `index` della stanza (dall'archivio aggiornato)."""
        _, room = self.find_or_404("room", room_id, "rooms.not_found")
        return mapping.extra_desc_out(room_id, index, room.extra_descs[index])

    async def update_extra_description(self, room_id: int, extra_id: int, data: ExtraDescriptionPatch) -> ExtraDescriptionOut:
        """Aggiornamento parziale di un'extra description."""
        self.ensure_writable()
        changes: dict[str, Any] = data.model_dump(by_alias=False, exclude_unset=True)
        async with self.writing():
            entry, _, extra, index = self._extra_or_404(room_id, extra_id)
            if "keywords" in changes:
                extra.keyword = changes["keywords"]
            if "text" in changes:
                extra.description = changes["text"]
            self.store.save(entry)
            return self._extra_out(room_id, index)

    async def delete_extra_description(self, room_id: int, extra_id: int) -> None:
        """Elimina un'extra description (le successive scalano di una posizione)."""
        self.ensure_writable()
        async with self.writing():
            entry, room, _, index = self._extra_or_404(room_id, extra_id)
            del room.extra_descs[index]
            self.store.save(entry)
