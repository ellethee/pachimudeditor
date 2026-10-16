"""Mob e oggetti prototipo (mixin di `MappingAdapter`): stesso codice per i due tipi, parametrizzato da `kind`."""

from typing import Any

from pachifast.schemas.responses import PaginatedResponse

from pachimudeditor_adapter_mapping.base import MappingSupport
from pachimudeditor_adapter_mapping.grammar import Record
from pachimudeditor_adapter_mapping.model import EntityMapper
from pachimudeditor_adapter_mapping.rooms import RoomsMixin, mutate
from pachimudeditor_adapter_mapping.store import ZoneUnit
from pachimudeditor.common.adapters.models import (
    MobIn,
    MobOut,
    MobPageParams,
    MobPatch,
    ObjectIn,
    ObjectOut,
    ObjectPageParams,
    ObjectPatch,
    ResetUsage,
)
from pachimudeditor.sdk import make_page, paginate_list
from pachimudeditor.sdk import conflict

_STRUCTURAL = frozenset({"vnum", "zone_id", "extra"})
_CODES = {"mob": "mobs", "object": "objects"}
"""Tipo -> prefisso dei codici di errore (`mobs.not_found`, ...)."""


class PrototypesMixin(RoomsMixin, MappingSupport):
    """Operazioni su mob e oggetti prototipo."""

    def _mapper(self, kind: str) -> EntityMapper:
        """Il mapper di `mob` o `object`."""
        return self.mob_map if kind == "mob" else self.object_map

    def _proto_out(self, kind: str, unit: ZoneUnit, rec: Record) -> Any:
        """DTO di un mob/oggetto."""
        values = self._mapper(kind).read(rec.fields)
        extra = values.pop("extra")
        vnum = self.vnum(rec)
        cls = MobOut if kind == "mob" else ObjectOut
        return cls(id=vnum, vnum=vnum, zone_id=unit.zone_id, extra=extra, **values)

    def _list(self, kind: str, params: Any, dto: type) -> PaginatedResponse[Any]:
        """Elenco paginato (ordine di default per vnum, filtro `zoneId`, ricerca su descrizione/keywords/vnum)."""
        self.sync()
        pairs = self.store.all_items(kind)
        if params.zone_id is not None:
            pairs = [p for p in pairs if p[0].zone_id == params.zone_id]
        mapper = self._mapper(kind)
        items, total = paginate_list(
            pairs, params, lambda p: self._text(mapper, p[1], ("short_description", "keywords", "vnum")),
            lambda p, f: self._key(mapper, p[1], f), params.order_fields or [],
        )  # fmt: skip
        return make_page(dto, [self._proto_out(kind, u, r) for u, r in items], total, params)

    async def _create(self, kind: str, data: Any) -> Any:
        """Crea un prototipo nella zona (vnum libero e dentro il range)."""
        self.ensure_writable()
        code = _CODES[kind]
        values = data.model_dump(by_alias=False, exclude=_STRUCTURAL)
        async with self.lock:
            self.sync()
            if self.store.find(kind, data.vnum) is not None:
                raise conflict(f"{code}.vnum_taken", vnum=data.vnum)
            unit = self.zone_or_404(data.zone_id)
            self.check_vnum_in_range(unit, data.vnum)
            mapper = self._mapper(kind)
            fields = mapper.new_fields(self.spec, self.entity_record[kind])
            fields[self.key_name(kind)] = data.vnum
            mapper.apply(fields, values, data.extra)
            _, entry = self.store.add_record(unit, kind, fields)
            self.store.save(entry)
            return self._proto_out(kind, *self.find_or_404(kind, data.vnum, f"{code}.not_found"))

    async def _update(self, kind: str, vnum: int, data: Any) -> Any:
        """Aggiornamento parziale; cambiare il vnum e' 409 `*.vnum_in_use` se un reset lo usa; `zoneId` sposta il record."""
        self.ensure_writable()
        code = _CODES[kind]
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude=_STRUCTURAL)
        async with self.lock:
            unit, rec = self.find_or_404(kind, vnum, f"{code}.not_found")
            new_vnum = data.vnum if data.vnum is not None else vnum
            if new_vnum != vnum:
                if self.store.find(kind, new_vnum) is not None:
                    raise conflict(f"{code}.vnum_taken", vnum=new_vnum)
                self.ensure_unused(kind, vnum, f"{code}.vnum_in_use")
            target = self.zone_or_404(data.zone_id) if data.zone_id not in (None, unit.zone_id) else unit
            if new_vnum != vnum or target is not unit:
                self.check_vnum_in_range(target, new_vnum)
            mapper = self._mapper(kind)
            mutate(rec.fields, lambda f: (mapper.apply(f, changes, data.extra), f.__setitem__(self.key_name(kind), new_vnum)))
            touched = {self.store.file_of(rec)}
            if target is not unit or new_vnum != vnum:
                self.store.remove_record(rec)
                touched.add(self.store.insert_record(target, rec))
            self.store.save(*touched)
            return self._proto_out(kind, *self.find_or_404(kind, new_vnum, f"{code}.not_found"))

    async def _delete(self, kind: str, vnum: int) -> None:
        """Elimina; 409 `*.in_reset_usage` (e `objects.in_exit_key_usage`) se referenziato."""
        self.ensure_writable()
        code = _CODES[kind]
        async with self.lock:
            _, rec = self.find_or_404(kind, vnum, f"{code}.not_found")
            self.ensure_unused(kind, vnum, f"{code}.in_reset_usage", include_exit_keys=False)
            if kind == "object":
                self.ensure_unused("object", vnum, "objects.in_exit_key_usage")
            self.store.save(self.store.remove_record(rec))

    # ------------------------------------------------------------------ mob

    async def list_mobs(self, params: MobPageParams) -> PaginatedResponse[MobOut]:
        """Mob paginati (filtro `zoneId`)."""
        return self._list("mob", params, MobOut)

    async def get_mob(self, mob_id: int) -> MobOut:
        """Un mob prototype."""
        return self._proto_out("mob", *self.find_or_404("mob", mob_id, "mobs.not_found"))

    async def create_mob(self, data: MobIn) -> MobOut:
        """Crea un mob prototype (409 `mobs.vnum_taken`)."""
        return await self._create("mob", data)

    async def update_mob(self, mob_id: int, data: MobPatch) -> MobOut:
        """Aggiornamento parziale."""
        return await self._update("mob", mob_id, data)

    async def delete_mob(self, mob_id: int) -> None:
        """Elimina il mob (409 `mobs.in_reset_usage` se usato)."""
        await self._delete("mob", mob_id)

    async def mob_usage(self, mob_id: int) -> list[ResetUsage]:
        """I reset che referenziano il mob per vnum."""
        self.find_or_404("mob", mob_id, "mobs.not_found")
        return self.find_usage("mob", mob_id)

    # ------------------------------------------------------------------ oggetti

    async def list_objects(self, params: ObjectPageParams) -> PaginatedResponse[ObjectOut]:
        """Oggetti paginati (filtro `zoneId`)."""
        return self._list("object", params, ObjectOut)

    async def get_object(self, object_id: int) -> ObjectOut:
        """Un object prototype."""
        return self._proto_out("object", *self.find_or_404("object", object_id, "objects.not_found"))

    async def create_object(self, data: ObjectIn) -> ObjectOut:
        """Crea un object prototype (409 `objects.vnum_taken`)."""
        return await self._create("object", data)

    async def update_object(self, object_id: int, data: ObjectPatch) -> ObjectOut:
        """Aggiornamento parziale."""
        return await self._update("object", object_id, data)

    async def delete_object(self, object_id: int) -> None:
        """Elimina l'oggetto (409 se usato da un reset o come chiave di un'uscita)."""
        await self._delete("object", object_id)

    async def object_usage(self, object_id: int) -> list[ResetUsage]:
        """I reset (e le chiavi di uscite) che referenziano l'oggetto per vnum."""
        self.find_or_404("object", object_id, "objects.not_found")
        return self.find_usage("object", object_id)
