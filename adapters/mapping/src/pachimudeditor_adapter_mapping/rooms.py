"""Stanze, uscite ed extra description (mixin di `MappingAdapter`).

`id`: stanza = vnum; uscita = `vnum * exit_id_stride + direzione`; extra description = `vnum * extra_id_stride + posizione`
nella lista della stanza (cancellare una extra fa scalare le successive). Con `exit.door_state: resets` lo stato porta
(`isOpen`/`isLocked`) vive nei reset `D` della zona della stanza (nessun `D` = porta aperta).
"""

import copy
from enum import Enum
from typing import Any

from pachifast.i18n import api_error
from pachifast.schemas.responses import PaginatedResponse
from pachimudeditor.common.enums import ZoneCommandType
from pachimudeditor.common.enums import Direction

from pachimudeditor_adapter_mapping.base import MappingSupport
from pachimudeditor_adapter_mapping.grammar import Record
from pachimudeditor_adapter_mapping.store import ZoneUnit
from pachimudeditor.sdk import rules
from pachimudeditor.common.adapters.models import (
    ExitIn,
    ExitOut,
    ExitPatch,
    ExtraDescriptionIn,
    ExtraDescriptionOut,
    ExtraDescriptionPatch,
    ResetCommandDraft,
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

_ROOM_STRUCTURAL = frozenset({"vnum", "zone_id", "extra"})


def mutate(rec_fields: dict[str, Any], fn: Any) -> None:
    """Applica `fn(copia)` ai campi e, solo se non solleva, li sostituisce: un errore a meta' non lascia stato sporco."""
    new = copy.deepcopy(rec_fields)
    fn(new)
    rec_fields.clear()
    rec_fields.update(new)


class RoomsMixin(MappingSupport):
    """Operazioni su stanze, uscite ed extra description."""

    # ------------------------------------------------------------------ liste annidate

    def _exits(self, rec: Record) -> list[dict[str, Any]]:
        """Le uscite (dict) della stanza."""
        return rec.fields.setdefault(self.spec.model.room.exits, [])

    def _extras(self, rec: Record) -> list[dict[str, Any]]:
        """Le extra description (dict) della stanza (lista vuota se il MUD non le ha)."""
        name = self.spec.model.room.extra_descriptions
        return rec.fields.setdefault(name, []) if name else []

    def _need_extras(self) -> None:
        """409 `world.capability_missing` se la mappatura non dichiara le extra description."""
        if not self.spec.model.room.extra_descriptions:
            raise api_error(409, "world.capability_missing", capability="supports_extra_descriptions")

    def _dir(self, x: dict[str, Any]) -> int:
        """Direzione (0-5) di un'uscita."""
        return int(self.exit_map.bindings["direction"].read(x))

    def _sort_exits(self, rec: Record) -> None:
        """Ordina le uscite per direzione (se il modello lo chiede)."""
        if self.spec.model.exit.sort_by_direction:
            self._exits(rec).sort(key=self._dir)

    # ------------------------------------------------------------------ stato porta (reset `D`)

    def _door_reset(self, unit: ZoneUnit, room_vnum: int, direction: int) -> dict[str, Any] | None:
        """Il reset che imposta lo stato della porta (stanza, direzione), se esiste."""
        for f in self.commands(unit):
            o = self.reset_map.out(unit.zone_id, 0, f)
            if o.command_type == ZoneCommandType.SET_DOOR_STATE and o.arg1 == room_vnum and o.arg2 == direction:
                return f
        return None

    def _door_state(self, unit: ZoneUnit, room_vnum: int, direction: int) -> tuple[bool, bool]:
        """`(is_open, is_locked)` dal reset (assente = aperta)."""
        f = self._door_reset(unit, room_vnum, direction)
        state = self.reset_map.out(unit.zone_id, 0, f).arg_str if f is not None else "OPEN"
        return state in (None, "OPEN"), state == "LOCKED"

    def set_door_state(self, unit: ZoneUnit, room_vnum: int, direction: int, is_open: bool, is_locked: bool) -> None:
        """Allinea il reset della porta: aperta = nessun reset, altrimenti `CLOSED`/`LOCKED`."""
        want = "LOCKED" if is_locked else ("OPEN" if is_open else "CLOSED")
        current, items = self._door_reset(unit, room_vnum, direction), self.reset_fields(unit)
        built = (
            self.reset_map.build(
                ResetCommandDraft(command_type=ZoneCommandType.SET_DOOR_STATE, arg1=room_vnum, arg2=direction, arg_str=want), {}
            )
            if want != "OPEN"
            else None
        )
        if current is None and built is not None:
            self.set_reset_fields(unit, [*items, built])
        elif current is not None and built is None:
            self.set_reset_fields(unit, [f for f in items if f is not current])
        elif (
            current is not None
            and built is not None
            and self.reset_map.key(unit.zone_id, current) != self.reset_map.key(unit.zone_id, built)
        ):
            current.clear()
            current.update(built)

    def drop_door_resets(self, unit: ZoneUnit, room_vnum: int, direction: int | None = None) -> bool:
        """Toglie i reset di porta della stanza (di una sola direzione se `direction`); `True` se ne ha tolto."""
        gone = [
            f for f in self.commands(unit)
            if (o := self.reset_map.out(unit.zone_id, 0, f)).command_type == ZoneCommandType.SET_DOOR_STATE
            and o.arg1 == room_vnum and (direction is None or o.arg2 == direction)
        ]  # fmt: skip
        if gone:
            self.set_reset_fields(unit, [f for f in self.reset_fields(unit) if not any(f is g for g in gone)])
        return bool(gone)

    # ------------------------------------------------------------------ DTO

    def _room_out(self, unit: ZoneUnit, rec: Record) -> RoomOut:
        """DTO di una stanza."""
        values = self.room_map.read(rec.fields)
        extra = values.pop("extra")
        vnum = self.vnum(rec)
        return RoomOut(id=vnum, vnum=vnum, zone_id=unit.zone_id, extra=extra, **values)

    def _exit_out(self, unit: ZoneUnit, rec: Record, x: dict[str, Any]) -> ExitOut:
        """DTO di un'uscita con la destinazione risolta."""
        model = self.spec.model.exit
        values = self.exit_map.read(x)
        values.pop("extra", None)
        vnum, direction = self.vnum(rec), self._dir(x)
        raw = x.get(model.target_field)
        has_target = raw is not None and raw != model.no_target
        target = self.store.find("room", raw) if has_target else None
        if model.door_state == "resets":
            is_open, is_locked = self._door_state(unit, vnum, direction)
        else:
            is_open, is_locked = values.pop("is_open"), values.pop("is_locked")
        return ExitOut(
            id=vnum * self.rules.exit_id_stride + direction, room_id=vnum, is_open=is_open, is_locked=is_locked,
            target_room_id=raw if target else None, target_room_vnum=raw if has_target else None,
            target_room_name=self.room_map.bindings["name"].read(target[1].fields) if target else None, **values,
        )  # fmt: skip

    def _detail(self, vnum: int) -> RoomDetail:
        """`RoomDetail` della stanza `vnum` (letta dall'archivio aggiornato)."""
        unit, rec = self.find_or_404("room", vnum, "rooms.not_found")
        base = self._room_out(unit, rec).model_dump(by_alias=False)
        stride = self.rules.extra_id_stride
        extras = [
            ExtraDescriptionOut(
                id=vnum * stride + i, room_id=vnum, **{k: v for k, v in self.extra_desc_map.read(d).items() if k != "extra"}
            )
            for i, d in enumerate(self._extras(rec))
        ]
        return RoomDetail(**base, exits=[self._exit_out(unit, rec, x) for x in self._exits(rec)], extra_descriptions=extras)

    def _key(self, mapper: Any, rec: Record, field: str) -> Any:
        """Chiave di ordinamento di un campo del DTO del record."""
        if field in ("id", "vnum"):
            return self.vnum(rec)
        value = mapper.bindings[field].read(rec.fields)
        return int(value) if isinstance(value, Enum) else value

    def _text(self, mapper: Any, rec: Record, fields: tuple[str, ...]) -> list[Any]:
        """Valori ricercabili di un record."""
        return [self.vnum(rec) if f == "vnum" else mapper.bindings[f].read(rec.fields) for f in fields]

    # ------------------------------------------------------------------ stanze

    async def list_rooms(self, params: RoomPageParams) -> PaginatedResponse[RoomOut]:
        """Stanze paginate (ordine di default per vnum), filtro `zoneId`, ricerca su nome/vnum."""
        self.sync()
        pairs = self.store.all_items("room")
        if params.zone_id is not None:
            pairs = [p for p in pairs if p[0].zone_id == params.zone_id]
        items, total = paginate_list(
            pairs, params, lambda p: self._text(self.room_map, p[1], ("name", "vnum")),
            lambda p, f: self._key(self.room_map, p[1], f), RoomPageParams.order_fields or [],
        )  # fmt: skip
        return make_page(RoomOut, [self._room_out(u, r) for u, r in items], total, params)

    async def get_room(self, room_id: int) -> RoomDetail:
        """Una stanza con uscite ed extra description."""
        self.find_or_404("room", room_id, "rooms.not_found")
        return self._detail(room_id)

    async def create_room(self, data: RoomIn) -> RoomDetail:
        """Crea una stanza nella zona (vnum libero e dentro il range della zona)."""
        self.ensure_writable()
        values = data.model_dump(by_alias=False, exclude=_ROOM_STRUCTURAL)
        async with self.writing():
            self.sync()
            if self.store.find("room", data.vnum) is not None:
                raise conflict("rooms.vnum_taken", vnum=data.vnum)
            unit = self.zone_or_404(data.zone_id)
            self.check_vnum_in_range(unit, data.vnum)
            fields = self.room_map.new_fields(self.spec, self.entity_record["room"])
            fields[self.key_name("room")] = data.vnum
            self.room_map.apply(fields, values, data.extra)
            _, entry = self.store.add_record(unit, "room", fields)
            self.store.save(entry)
            return self._detail(data.vnum)

    async def update_room(self, room_id: int, data: RoomPatch) -> RoomDetail:
        """Aggiornamento parziale. Cambiare il vnum e' 409 `rooms.vnum_in_use` se un reset lo usa; le uscite di altre
        stanze che portano qui seguono il nuovo vnum. `zoneId` sposta la stanza (altro file, o altro range)."""
        self.ensure_writable()
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude=_ROOM_STRUCTURAL)
        async with self.writing():
            unit, rec = self.find_or_404("room", room_id, "rooms.not_found")
            old_vnum = self.vnum(rec)
            new_vnum = data.vnum if data.vnum is not None else old_vnum
            if new_vnum != old_vnum:
                if self.store.find("room", new_vnum) is not None:
                    raise conflict("rooms.vnum_taken", vnum=new_vnum)
                self.ensure_unused("room", old_vnum, "rooms.vnum_in_use", include_exit_keys=False)
            target = self.zone_or_404(data.zone_id) if data.zone_id not in (None, unit.zone_id) else unit
            if new_vnum != old_vnum or target is not unit:
                self.check_vnum_in_range(target, new_vnum)
            mutate(rec.fields, lambda f: (self.room_map.apply(f, changes, data.extra), f.__setitem__(self.key_name("room"), new_vnum)))
            touched = {self.store.file_of(rec)}
            if new_vnum != old_vnum:
                for _, other in self.store.all_items("room"):
                    for x in self._exits(other):
                        if x.get(self.spec.model.exit.target_field) == old_vnum:
                            x[self.spec.model.exit.target_field] = new_vnum
                            touched.add(self.store.file_of(other))
            if target is not unit or new_vnum != old_vnum:
                self.store.remove_record(rec)
                touched.add(self.store.insert_record(target, rec))
            self.store.save(*touched)
            return self._detail(new_vnum)

    async def delete_room(self, room_id: int) -> None:
        """Elimina la stanza: 409 `rooms.in_reset_usage` se un reset (diverso da quelli di stato porta, che vanno via
        con lei) la referenzia. Le uscite di altre stanze verso di lei restano senza destinazione."""
        self.ensure_writable()
        async with self.writing():
            unit, rec = self.find_or_404("room", room_id, "rooms.not_found")
            usage = [
                u for u in self.find_usage("room", room_id, include_exit_keys=False) if u.command_type != ZoneCommandType.SET_DOOR_STATE
            ]
            rules.raise_if_used(usage, "rooms.in_reset_usage")
            touched = {self.store.remove_record(rec)}
            for zone in self.store.zones:
                if self.drop_door_resets(zone, room_id):
                    touched.add(zone.file)
            model = self.spec.model.exit
            for _, other in self.store.all_items("room"):
                for x in self._exits(other):
                    if x.get(model.target_field) == room_id:
                        x[model.target_field] = model.no_target
                        touched.add(self.store.file_of(other))
            self.store.save(*touched)

    async def clone_room(self, room_id: int, data: RoomCloneIn) -> RoomDetail:
        """Duplica la stanza nella stessa zona (senza uscite, con le extra description)."""
        self.ensure_writable()
        async with self.writing():
            unit, rec = self.find_or_404("room", room_id, "rooms.not_found")
            if self.store.find("room", data.vnum) is not None:
                raise conflict("rooms.vnum_taken", vnum=data.vnum)
            self.check_vnum_in_range(unit, data.vnum)
            fields = copy.deepcopy(rec.fields)
            fields[self.key_name("room")] = data.vnum
            fields[self.spec.model.room.exits] = []
            if data.name:
                self.room_map.apply(fields, {"name": data.name})
            _, entry = self.store.add_record(unit, "room", fields)
            self.store.save(entry)
            return self._detail(data.vnum)

    async def room_graph(self, zone_id: int) -> RoomGraph:
        """Stanze della zona e uscite tra loro, con layout a bussola calcolato dal server."""
        unit = self.zone_or_404(zone_id)
        stride = self.rules.exit_id_stride
        model = self.spec.model.exit
        exits: list[rules.GraphExit] = []
        rooms: list[rules.GraphRoom] = []
        for r in unit.items["room"]:
            out = self._room_out(unit, r)
            rooms.append(rules.GraphRoom(out.vnum, out.vnum, out.name, out.sector_type, out.flags))
            for x in self._exits(r):
                raw = x.get(model.target_field)
                d = self._dir(x)
                exits.append(
                    rules.GraphExit(
                        out.vnum * stride + d,
                        out.vnum,
                        Direction(d),
                        self.exit_map.bindings["door_flag"].read(x),
                        raw if raw is not None and self.store.find("room", raw) else None,
                    )  # fmt: skip
                )
        return rules.build_room_graph(rooms, exits)

    async def room_usage(self, room_id: int) -> list[ResetUsage]:
        """I reset che referenziano la stanza per vnum."""
        self.find_or_404("room", room_id, "rooms.not_found")
        return self.find_usage("room", room_id, include_exit_keys=False)

    # ------------------------------------------------------------------ uscite

    def _exit_or_404(self, room_id: int, exit_id: int) -> tuple[ZoneUnit, Record, dict[str, Any]]:
        """`(zona, stanza, uscita)` per `exit_id`: 404 `rooms.exit_not_found`, 409 `rooms.exit_not_in_room`."""
        self.sync()
        stride = self.rules.exit_id_stride
        found = self.store.find("room", exit_id // stride) if exit_id >= 0 else None
        x = next((e for e in self._exits(found[1]) if self._dir(e) == exit_id % stride), None) if found else None
        if found is None or x is None:
            raise api_error(404, "rooms.exit_not_found")
        if self.vnum(found[1]) != room_id:
            raise conflict("rooms.exit_not_in_room")
        return found[0], found[1], x

    def _key_exists(self):  # type: ignore[no-untyped-def]
        """Callback di `rules.check_exit`: la chiave deve esistere come oggetto."""

        async def exists(vnum: int) -> bool:
            """Esiste un oggetto con quel vnum?"""
            return self.store.find("object", vnum) is not None

        return exists

    def _check_target(self, target_room_id: int | None) -> None:
        """404 `rooms.not_found` se la destinazione non esiste."""
        if target_room_id is not None and self.store.find("room", target_room_id) is None:
            raise api_error(404, "rooms.not_found")

    def _exit_by_id(self, exit_id: int) -> ExitOut:
        """`ExitOut` da un id (letto dall'archivio aggiornato)."""
        unit, rec = self.find_or_404("room", exit_id // self.rules.exit_id_stride, "rooms.not_found")
        x = next(e for e in self._exits(rec) if self._dir(e) == exit_id % self.rules.exit_id_stride)
        return self._exit_out(unit, rec, x)

    def _exit_values(self, source: dict[str, Any]) -> dict[str, Any]:
        """Campi di `ExitIn`/`ExitPatch` che il mapper delle uscite sa scrivere."""
        return {k: v for k, v in source.items() if k in self.exit_map.bindings}

    async def create_exit(self, room_id: int, data: ExitIn) -> ExitOut:
        """Crea un'uscita (una per direzione); con `door_state: resets` lo stato porta va nel reset della zona."""
        self.ensure_writable()
        model = self.spec.model.exit
        async with self.writing():
            unit, rec = self.find_or_404("room", room_id, "rooms.not_found")
            if any(self._dir(x) == int(data.direction) for x in self._exits(rec)):
                raise conflict("rooms.exit_direction_taken", direction=data.direction.name)
            await rules.check_exit(room_id, data.model_dump(by_alias=False), set(ExitIn.model_fields), self._key_exists())
            self._check_target(data.target_room_id)
            x = copy.deepcopy(model.defaults)
            self.exit_map.apply(x, self._exit_values(data.model_dump(by_alias=False)))
            x[model.target_field] = data.target_room_id if data.target_room_id is not None else model.no_target
            self._exits(rec).append(x)
            self._sort_exits(rec)
            if model.door_state == "resets":
                self.set_door_state(unit, room_id, int(data.direction), data.is_open, data.is_locked)
            self.store.save(unit.file, self.store.file_of(rec))
            return self._exit_by_id(room_id * self.rules.exit_id_stride + int(data.direction))

    async def update_exit(self, room_id: int, exit_id: int, data: ExitPatch) -> ExitOut:
        """Aggiornamento parziale di un'uscita (cambiando direzione cambia anche l'`id`)."""
        self.ensure_writable()
        changes = data.model_dump(by_alias=False, exclude_unset=True)
        model = self.spec.model.exit
        async with self.writing():
            unit, rec, x = self._exit_or_404(room_id, exit_id)
            current = self._exit_by_id(exit_id)
            if "direction" in changes and changes["direction"] != current.direction:
                if any(self._dir(o) == int(changes["direction"]) for o in self._exits(rec)):
                    raise conflict("rooms.exit_direction_taken", direction=changes["direction"].name)
            final = {name: changes.get(name, getattr(current, name)) for name in ExitIn.model_fields}
            await rules.check_exit(room_id, final, set(changes), self._key_exists())
            if "target_room_id" in changes:
                self._check_target(changes["target_room_id"])
            old_dir = self._dir(x)

            def apply(f: dict[str, Any]) -> None:
                """Scrive i campi cambiati nella copia."""
                self.exit_map.apply(f, self._exit_values(changes))
                if "target_room_id" in changes:
                    f[model.target_field] = changes["target_room_id"] if changes["target_room_id"] is not None else model.no_target

            mutate(x, apply)
            self._sort_exits(rec)
            new_dir = self._dir(x)
            if model.door_state == "resets" and changes.keys() & {"direction", "door_flag", "is_open", "is_locked"}:
                if new_dir != old_dir:
                    self.drop_door_resets(unit, room_id, old_dir)
                self.set_door_state(unit, room_id, new_dir, final["is_open"], final["is_locked"])
            self.store.save(unit.file, self.store.file_of(rec))
            return self._exit_by_id(room_id * self.rules.exit_id_stride + new_dir)

    async def delete_exit(self, room_id: int, exit_id: int) -> None:
        """Elimina un'uscita (e il suo reset di stato porta)."""
        self.ensure_writable()
        async with self.writing():
            unit, rec, x = self._exit_or_404(room_id, exit_id)
            direction = self._dir(x)
            self._exits(rec).remove(x)
            if self.spec.model.exit.door_state == "resets":
                self.drop_door_resets(unit, room_id, direction)
            self.store.save(unit.file, self.store.file_of(rec))

    # ------------------------------------------------------------------ extra description

    def _extra_or_404(self, room_id: int, extra_id: int) -> tuple[Record, dict[str, Any], int]:
        """`(stanza, extra, posizione)`: 404 `rooms.extra_not_found`, 409 `rooms.extra_not_in_room`."""
        self.sync()
        stride = self.rules.extra_id_stride
        found = self.store.find("room", extra_id // stride) if extra_id >= 0 else None
        index = extra_id % stride
        if found is None or index >= len(self._extras(found[1])):
            raise api_error(404, "rooms.extra_not_found")
        if self.vnum(found[1]) != room_id:
            raise conflict("rooms.extra_not_in_room")
        return found[1], self._extras(found[1])[index], index

    def _extra_out(self, room_id: int, index: int) -> ExtraDescriptionOut:
        """DTO dell'extra `index` della stanza (dall'archivio aggiornato)."""
        _, rec = self.find_or_404("room", room_id, "rooms.not_found")
        values = self.extra_desc_map.read(self._extras(rec)[index])
        values.pop("extra", None)
        return ExtraDescriptionOut(id=room_id * self.rules.extra_id_stride + index, room_id=room_id, **values)

    async def create_extra_description(self, room_id: int, data: ExtraDescriptionIn) -> ExtraDescriptionOut:
        """Aggiunge un'extra description in coda."""
        self.ensure_writable()
        self._need_extras()
        async with self.writing():
            unit, rec = self.find_or_404("room", room_id, "rooms.not_found")
            d = copy.deepcopy(self.spec.model.extra_description.defaults)
            self.extra_desc_map.apply(d, data.model_dump(by_alias=False))
            self._extras(rec).append(d)
            index = len(self._extras(rec)) - 1
            self.store.save(self.store.file_of(rec))
            return self._extra_out(room_id, index)

    async def update_extra_description(self, room_id: int, extra_id: int, data: ExtraDescriptionPatch) -> ExtraDescriptionOut:
        """Aggiornamento parziale di un'extra description."""
        self.ensure_writable()
        self._need_extras()
        async with self.writing():
            rec, d, index = self._extra_or_404(room_id, extra_id)
            mutate(d, lambda f: self.extra_desc_map.apply(f, data.model_dump(by_alias=False, exclude_unset=True)))
            self.store.save(self.store.file_of(rec))
            return self._extra_out(room_id, index)

    async def delete_extra_description(self, room_id: int, extra_id: int) -> None:
        """Elimina un'extra description (le successive scalano di una posizione)."""
        self.ensure_writable()
        self._need_extras()
        async with self.writing():
            rec, _, index = self._extra_or_404(room_id, extra_id)
            del self._extras(rec)[index]
            self.store.save(self.store.file_of(rec))
