"""Stanze, uscite ed extra description (mixin di `PachimudAdapter`).

Convenzioni degli `id`: stanza = vnum; uscita = `vnum * 10 + direzione`; extra description = `vnum * 1000 + posizione`
nella lista della stanza (cancellare una extra fa scalare le successive). Le uscite stanno nel dict `exits` della
voce (chiave = nome della direzione); lo stato porta (`is_open`/`is_locked`) e' nell'uscita stessa.
"""

import copy
from typing import Any

from pachifast.i18n import api_error
from pachifast.schemas.responses import PaginatedResponse
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from pachimudeditor.common.adapters.models import (
    ExitIn,
    ExitOut,
    ExitPatch,
    ExtraDescriptionIn,
    ExtraDescriptionOut,
    ExtraDescriptionPatch,
    IncomingExit,
    ResetUsage,
    RoomCloneIn,
    RoomDetail,
    RoomGraph,
    RoomIn,
    RoomOut,
    RoomPageParams,
    RoomPatch,
)
from pachimudeditor.common.enums import Direction, DoorFlag, SectorType
from pachimudeditor.sdk import conflict, room_query, rules
from pachimudeditor_adapter_pachimud import mapping, simple_extra
from pachimudeditor_adapter_pachimud.base import PachimudSupport
from pachimudeditor_adapter_pachimud.loaders import LoaderRoom
from pachimudeditor_adapter_pachimud.store import Item, plain

ROOM_EXTRA = frozenset({"enabled", "area", "climate", "triggers", *simple_extra.keys("room")})
EXIT_EXTRA = frozenset({"isMale", "openCmd", "climb"})


def check_extra(extra: dict[str, Any], allowed: frozenset[str]) -> None:
    """422 `pachimud.extra_unknown` per chiavi di `extra` che il tipo non ha."""
    for key in extra:
        if key not in allowed:
            raise api_error(422, "pachimud.extra_unknown", key=key)


def norm_area(value: Any) -> str | None:
    """L'area richiesta in `extra`: il testo vuoto (campo svuotato nel form) vale «nessuna area»."""
    text = str(value).strip() if value is not None else ""
    return text or None


def move_raw(item: Item, target_file: Any) -> None:
    """Sposta la voce (per identita') dalla lista del suo file a quella di `target_file`."""
    source = item.file.list_of()
    assert source is not None
    for index, candidate in enumerate(source):
        if candidate is item.raw:
            del source[index]
            break
    target_file.list_of(create=True).append(item.raw)


class RoomsMixin(PachimudSupport):
    """Operazioni su stanze, uscite ed extra description."""

    # ------------------------------------------------------------------ DTO

    def _detail(self, vnum: int) -> RoomDetail:
        """`RoomDetail` della stanza `vnum` (letta dall'archivio aggiornato)."""
        room = self.find_or_404("room", vnum, "rooms.not_found")
        names = self.store.room_names()
        base = mapping.room_out(room, room.zone.vnum).model_dump(by_alias=False)
        return RoomDetail(
            **base,
            exits=[mapping.exit_out(room, k, names) for k in sorted(room.model.exits, key=lambda k: Direction[k.upper()])],
            extra_descriptions=[mapping.extra_desc_out(vnum, i, e) for i, e in enumerate(room.model.extra_descriptions)],
        )

    def _apply_extra(self, item: Item, extra: dict[str, Any]) -> Any:
        """Applica `extra` (`enabled`, `area`, `climate`) alla voce; restituisce l'area richiesta (`...` se non indicata)."""
        check_extra(extra, ROOM_EXTRA)
        if "enabled" in extra:
            mapping.put(item.raw, "enabled", bool(extra["enabled"]), default=True)
        if "climate" in extra:
            mapping.put(item.raw, "climate", extra["climate"] or None)
        if "triggers" in extra:
            mapping.apply_triggers(item.raw, extra["triggers"], "room", "triggers")
        simple_extra.apply("room", item.raw, extra)
        return norm_area(extra["area"]) if "area" in extra else ...

    # ------------------------------------------------------------------ stanze

    async def list_rooms(self, params: RoomPageParams) -> PaginatedResponse[RoomOut]:
        """Stanze paginate (ordine di default per vnum), filtro `zoneId`, ricerca su nome/vnum."""
        self.sync()
        rooms = self.store.all_items("room")
        if params.zone_id is not None:
            rooms = [r for r in rooms if r.zone.vnum == params.zone_id]
        return room_query.page_rooms([mapping.room_out(r, r.zone.vnum) for r in rooms], params)

    async def get_room(self, room_id: int) -> RoomDetail:
        """Una stanza con uscite ed extra description."""
        self.find_or_404("room", room_id, "rooms.not_found")
        return self._detail(room_id)

    async def create_room(self, data: RoomIn) -> RoomDetail:
        """Crea una stanza nel file `rooms.yaml` della zona (o in quello dell'area `extra.area`)."""
        self.ensure_writable()
        values = data.model_dump(by_alias=False, exclude={"extra", "zone_id"})
        check_extra(data.extra, ROOM_EXTRA)
        async with self.writing():
            self.sync()
            if self.store.find("room", data.vnum) is not None:
                raise conflict("rooms.vnum_taken", vnum=data.vnum)
            zone = self.zone_or_404(data.zone_id)
            file = self.store.file_for(zone, "room", norm_area(data.extra.get("area")))
            raw = CommentedMap()
            mapping.room_apply(
                raw, {"vnum": values.pop("vnum"), "name": values.pop("name"), "description": values.pop("description"), **values}
            )
            if "enabled" in data.extra:
                mapping.put(raw, "enabled", bool(data.extra["enabled"]), default=True)
            if "climate" in data.extra:
                mapping.put(raw, "climate", data.extra["climate"] or None)
            if "triggers" in data.extra:
                mapping.apply_triggers(raw, data.extra["triggers"], "room", "triggers")
            simple_extra.apply("room", raw, data.extra)
            LoaderRoom.model_validate(plain(raw))
            file.list_of(create=True).append(raw)
            self.store.save(file)
            return self._detail(data.vnum)

    async def update_room(self, room_id: int, data: RoomPatch) -> RoomDetail:
        """Aggiornamento parziale. Cambiare il vnum e' 409 `rooms.vnum_in_use` se un reset lo usa; le uscite di altre
        stanze che portano qui seguono il nuovo vnum. `zoneId` (o `extra.area`) sposta la stanza in un altro file."""
        self.ensure_writable()
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude={"extra"})
        async with self.writing():
            room = self.find_or_404("room", room_id, "rooms.not_found")
            old_vnum, touched = room.vnum, {room.file}
            new_vnum = changes.get("vnum", old_vnum)
            if new_vnum != old_vnum:
                if self.store.find("room", new_vnum) is not None:
                    raise conflict("rooms.vnum_taken", vnum=new_vnum)
                self.ensure_unused("room", old_vnum, "rooms.vnum_in_use", include_exit_keys=False)
                players = await self.players_in_room(old_vnum)
                if players:
                    raise conflict("rooms.has_instances", mobs=0, objects=0, players=players)
            area = self._apply_extra(room, data.extra or {})
            mapping.room_apply(room.raw, {k: v for k, v in changes.items() if k != "zone_id"})
            target_zone = self.zone_or_404(changes["zone_id"]) if changes.get("zone_id", room.zone.vnum) != room.zone.vnum else room.zone
            target_area = room.area if area is ... else area
            room.revalidate()
            if target_zone is not room.zone or target_area != room.area:
                target_file = self.store.file_for(target_zone, "room", target_area)
                if target_file is not room.file:
                    move_raw(room, target_file)
                    touched.add(target_file)
            if new_vnum != old_vnum:
                for other in self.store.all_items("room"):
                    for key, x in other.model.exits.items():
                        if x.target_vnum == old_vnum:
                            other.raw["exits"][key]["target_vnum"] = new_vnum
                            other.revalidate()
                            touched.add(other.file)
            self.store.save(*touched)
            return self._detail(new_vnum)

    async def delete_room(self, room_id: int) -> None:
        """Elimina la stanza: 409 `rooms.in_reset_usage` se un reset la referenzia, `rooms.has_instances` se un
        personaggio ci si trova. Le uscite di altre stanze verso di lei restano senza destinazione (segnalate)."""
        self.ensure_writable()
        async with self.writing():
            room = self.find_or_404("room", room_id, "rooms.not_found")
            self.ensure_unused("room", room_id, "rooms.in_reset_usage", include_exit_keys=False)
            players = await self.players_in_room(room_id)
            if players:
                raise conflict("rooms.has_instances", mobs=0, objects=0, players=players)
            seq = room.file.list_of()
            assert seq is not None
            for index, candidate in enumerate(seq):
                if candidate is room.raw:
                    del seq[index]
                    break
            self.store.save(room.file)

    async def clone_room(self, room_id: int, data: RoomCloneIn) -> RoomDetail:
        """Duplica la stanza nello stesso file (senza uscite, con le extra description)."""
        self.ensure_writable()
        async with self.writing():
            room = self.find_or_404("room", room_id, "rooms.not_found")
            if self.store.find("room", data.vnum) is not None:
                raise conflict("rooms.vnum_taken", vnum=data.vnum)
            ordered = copy.deepcopy(room.raw)
            ordered.pop("exits", None)
            ordered["vnum"] = data.vnum
            ordered["name"] = data.name or room.model.name
            room.file.list_of(create=True).append(ordered)
            self.store.save(room.file)
            return self._detail(data.vnum)

    async def room_graph(self, zone_id: int) -> RoomGraph:
        """Stanze della zona e uscite tra loro, con layout a bussola calcolato dal server."""
        zone = self.zone_or_404(zone_id)
        rooms = zone.items["room"]
        exits = [
            rules.GraphExit(
                r.vnum * mapping.EXIT_STRIDE + int(Direction[k.upper()]),
                r.vnum,
                Direction[k.upper()],
                DoorFlag[x.door_flag],
                x.target_vnum if self.store.find("room", x.target_vnum) is not None else None,  # type: ignore[arg-type]
            )
            for r in rooms
            for k, x in r.model.exits.items()
        ]
        return rules.build_room_graph(
            [rules.GraphRoom(r.vnum, r.vnum, r.model.name, SectorType[r.model.sector_type], list(r.model.flags)) for r in rooms],
            exits,
        )

    async def room_usage(self, room_id: int) -> list[ResetUsage]:
        """I reset che referenziano la stanza per vnum."""
        self.find_or_404("room", room_id, "rooms.not_found")
        return self.find_usage("room", room_id, include_exit_keys=False)

    async def incoming_exits(self, room_id: int) -> list[IncomingExit]:
        """Le uscite di altre stanze (di qualsiasi zona) che portano a `room_id`: una sola scansione dei file gia' in memoria."""
        self.find_or_404("room", room_id, "rooms.not_found")
        return [
            IncomingExit(
                exit_id=room.vnum * mapping.EXIT_STRIDE + int(Direction[key.upper()]),
                room_id=room.vnum,
                room_vnum=room.vnum,
                room_name=room.model.name,
                zone_id=room.zone.vnum,
                direction=Direction[key.upper()],
            )
            for room in self.store.all_items("room")
            if room.vnum != room_id
            for key, x in room.model.exits.items()
            if x.target_vnum == room_id
        ]

    # ------------------------------------------------------------------ uscite

    def _exit_or_404(self, room_id: int, exit_id: int) -> tuple[Item, str]:
        """`(stanza, chiave dell'uscita)` per `exit_id`: 404 `rooms.exit_not_found`, 409 `rooms.exit_not_in_room`."""
        self.sync()
        room = self.store.find("room", exit_id // mapping.EXIT_STRIDE) if exit_id >= 0 else None
        direction = exit_id % mapping.EXIT_STRIDE
        key = mapping.direction_key(room.model.exits, direction) if room is not None and direction <= 5 else None
        if room is None or key is None:
            raise api_error(404, "rooms.exit_not_found")
        if room.vnum != room_id:
            raise conflict("rooms.exit_not_in_room")
        return room, key

    @staticmethod
    def _apply_exit_extra(node: Any, exit_extra: dict[str, Any]) -> None:
        """Scrive nel nodo dell'uscita le chiavi di `extra` (`isMale`, `openCmd`, `climb`); `openCmd` vuoto toglie il campo."""
        if "isMale" in exit_extra:
            mapping.put(node, "is_male", bool(exit_extra["isMale"]), default=False)
        if "openCmd" in exit_extra:
            mapping.put(node, "open_cmd", exit_extra["openCmd"] or None)
        if "climb" in exit_extra:
            mapping.put(node, "climb", bool(exit_extra["climb"]), default=False)

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

    def _exit_by_id(self, exit_id: int) -> ExitOut:
        """`ExitOut` da un id (letto dall'archivio aggiornato)."""
        room = self.find_or_404("room", exit_id // mapping.EXIT_STRIDE, "rooms.not_found")
        key = mapping.direction_key(room.model.exits, exit_id % mapping.EXIT_STRIDE)
        assert key is not None
        return mapping.exit_out(room, key, self.store.room_names())

    async def create_exit(self, room_id: int, data: ExitIn) -> ExitOut:
        """Crea un'uscita (una per direzione)."""
        self.ensure_writable()
        async with self.writing():
            room = self.find_or_404("room", room_id, "rooms.not_found")
            if mapping.direction_key(room.model.exits, int(data.direction)) is not None:
                raise conflict("rooms.exit_direction_taken", direction=data.direction.name)
            await rules.check_exit(room_id, data.model_dump(by_alias=False), set(ExitIn.model_fields), self._key_exists())
            self._check_target(data.target_room_id)
            exits = room.raw.get("exits")
            if exits is None:
                exits = room.raw["exits"] = CommentedMap()
            node = CommentedMap()
            for key, value, default in (
                ("target_vnum", data.target_room_id, None),
                ("description", data.description, None),
                ("keywords", data.keywords, None),
                ("door_flag", data.door_flag.name, "NONE"),
                ("is_open", data.is_open, True),
                ("is_locked", data.is_locked, False),
                ("key_vnum", data.key_vnum, None),
            ):
                mapping.put(node, key, value, default=default)
            exits[data.direction.name.lower()] = node
            room.revalidate()
            self.store.save(room.file)
            return self._exit_by_id(room_id * mapping.EXIT_STRIDE + int(data.direction))

    async def update_exit(self, room_id: int, exit_id: int, data: ExitPatch) -> ExitOut:
        """Aggiornamento parziale di un'uscita (cambiando direzione cambia anche l'`id`)."""
        self.ensure_writable()
        changes = data.model_dump(by_alias=False, exclude_unset=True)
        exit_extra = changes.pop("extra", None) or {}
        if set(exit_extra) - EXIT_EXTRA:
            raise api_error(422, "pachimud.extra_unknown", key=sorted(set(exit_extra) - EXIT_EXTRA)[0])
        async with self.writing():
            room, key = self._exit_or_404(room_id, exit_id)
            current = self._exit_by_id(exit_id)
            if "direction" in changes and changes["direction"] != current.direction:
                if mapping.direction_key(room.model.exits, int(changes["direction"])) is not None:
                    raise conflict("rooms.exit_direction_taken", direction=changes["direction"].name)
            final = {name: changes.get(name, getattr(current, name)) for name in ExitIn.model_fields}
            await rules.check_exit(room_id, final, set(changes), self._key_exists())
            if "target_room_id" in changes:
                self._check_target(changes["target_room_id"])
            node = room.raw["exits"][key]
            for field, name, default in (
                ("target_room_id", "target_vnum", None),
                ("description", "description", None),
                ("keywords", "keywords", None),
                ("door_flag", "door_flag", "NONE"),
                ("is_open", "is_open", True),
                ("is_locked", "is_locked", False),
                ("key_vnum", "key_vnum", None),
            ):
                if field in changes:
                    value = changes[field].name if field == "door_flag" else changes[field]
                    if field == "target_room_id" and value is None and self.store.find("room", node.get("target_vnum")) is None:
                        continue  # un'uscita verso una stanza inesistente appare senza destinazione: non si perde il vnum (si elimina l'uscita)
                    mapping.put(node, name, value, default=default)
            self._apply_exit_extra(node, exit_extra)
            new_dir = int(changes.get("direction", current.direction))
            if new_dir != int(current.direction):
                exits = room.raw["exits"]
                del exits[key]
                exits[Direction(new_dir).name.lower()] = node
            room.revalidate()
            self.store.save(room.file)
            return self._exit_by_id(room_id * mapping.EXIT_STRIDE + new_dir)

    async def delete_exit(self, room_id: int, exit_id: int) -> None:
        """Elimina un'uscita."""
        self.ensure_writable()
        async with self.writing():
            room, key = self._exit_or_404(room_id, exit_id)
            del room.raw["exits"][key]
            if not room.raw["exits"]:
                del room.raw["exits"]
            room.revalidate()
            self.store.save(room.file)

    # ------------------------------------------------------------------ extra description

    def _extra_or_404(self, room_id: int, extra_id: int) -> tuple[Item, int]:
        """`(stanza, posizione)`: 404 `rooms.extra_not_found`, 409 `rooms.extra_not_in_room`."""
        self.sync()
        stride = mapping.EXTRA_DESC_STRIDE
        room = self.store.find("room", extra_id // stride) if extra_id >= 0 else None
        index = extra_id % stride
        if room is None or index >= len(room.model.extra_descriptions):
            raise api_error(404, "rooms.extra_not_found")
        if room.vnum != room_id:
            raise conflict("rooms.extra_not_in_room")
        return room, index

    def _extra_out(self, room_id: int, index: int) -> ExtraDescriptionOut:
        """DTO dell'extra `index` della stanza (dall'archivio aggiornato)."""
        room = self.find_or_404("room", room_id, "rooms.not_found")
        return mapping.extra_desc_out(room_id, index, room.model.extra_descriptions[index])

    async def create_extra_description(self, room_id: int, data: ExtraDescriptionIn) -> ExtraDescriptionOut:
        """Aggiunge un'extra description in coda."""
        self.ensure_writable()
        async with self.writing():
            room = self.find_or_404("room", room_id, "rooms.not_found")
            seq = room.raw.get("extra_descriptions")
            if seq is None:
                seq = room.raw["extra_descriptions"] = CommentedSeq()
            seq.append(mapping.new_map({"keywords": data.keywords, "text": data.text}))
            room.revalidate()
            self.store.save(room.file)
            return self._extra_out(room_id, len(seq) - 1)

    async def update_extra_description(self, room_id: int, extra_id: int, data: ExtraDescriptionPatch) -> ExtraDescriptionOut:
        """Aggiornamento parziale di un'extra description."""
        self.ensure_writable()
        changes: dict[str, Any] = data.model_dump(by_alias=False, exclude_unset=True)
        async with self.writing():
            room, index = self._extra_or_404(room_id, extra_id)
            for key, value in changes.items():
                mapping.put(room.raw["extra_descriptions"][index], key, value, required=True)
            room.revalidate()
            self.store.save(room.file)
            return self._extra_out(room_id, index)

    async def delete_extra_description(self, room_id: int, extra_id: int) -> None:
        """Elimina un'extra description (le successive scalano di una posizione)."""
        self.ensure_writable()
        async with self.writing():
            room, index = self._extra_or_404(room_id, extra_id)
            del room.raw["extra_descriptions"][index]
            if not room.raw["extra_descriptions"]:
                del room.raw["extra_descriptions"]
            room.revalidate()
            self.store.save(room.file)
