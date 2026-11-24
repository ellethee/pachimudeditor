"""Mob e oggetti prototipo (mixin di `PachimudAdapter`): voci di `mobs*.yaml` e `objects*.yaml`.

`id == vnum`. Il mob ha i dadi `hp_dice`/`damage_dice` (`XdY+Z`) spezzati nei tre campi del DTO e le sei statistiche in
`extra`; l'oggetto ha i campi del suo tipo in `extra.typeFields` (e, per i soli campi numerici, in `value_0..3`).
"""

from typing import Any

from pachifast.schemas.responses import PaginatedResponse
from ruamel.yaml.comments import CommentedMap

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
from pachimudeditor.common.enums import ObjectType
from pachimudeditor.sdk import conflict, mob_query, object_query
from pachimudeditor_adapter_pachimud import mapping
from pachimudeditor_adapter_pachimud.base import PachimudSupport
from pachimudeditor_adapter_pachimud.loaders import LoaderMob, type_fields
from pachimudeditor_adapter_pachimud.rooms import check_extra, move_raw, norm_area
from pachimudeditor_adapter_pachimud.store import Item, plain

MOB_EXTRA = frozenset(
    {
        "area",
        "name",
        "attacks",
        "persona",
        "postmaster",
        "receptionist",
        "weaponImmunity",
        "breath",
        "breathCost",
        "shop",
        "triggers",
        *mapping.STATS,
    }
)
OBJECT_EXTRA = frozenset({"area", "typeFields", "extraDescriptions"})


class PrototypesMixin(PachimudSupport):
    """Operazioni su mob e oggetti prototipo."""

    # ------------------------------------------------------------------ mob

    def _mob_extra(self, raw: Any, extra: dict[str, Any]) -> Any:
        """Applica le statistiche di `extra` alla voce; restituisce l'area richiesta (`...` se non indicata)."""
        check_extra(extra, MOB_EXTRA)
        for stat in mapping.STATS:
            if stat in extra:
                mapping.put(raw, stat, int(extra[stat]), default=0)
        if "name" in extra:
            mapping.put(raw, "name", str(extra["name"] or ""), default="")
        if "attacks" in extra:
            mapping.put(raw, "attacks", int(extra["attacks"]), default=1)
        if "persona" in extra:
            mapping.put(raw, "persona", str(extra["persona"] or ""), default="")
        for key, name in (("postmaster", "postmaster"), ("receptionist", "receptionist")):
            if key in extra:
                mapping.put(raw, name, bool(extra[key]), default=False)
        if "weaponImmunity" in extra:
            value = extra["weaponImmunity"]
            mapping.put(raw, "weapon_immunity", None if value in (None, "") else int(value))
        if "breath" in extra:
            mapping.put(raw, "breath", [str(b) for b in extra["breath"] or []], default=[])
        if "breathCost" in extra:
            mapping.put(raw, "breath_cost", int(extra["breathCost"]), default=30)
        if "shop" in extra:
            mapping.put(raw, "shop", mapping.shop_value(extra["shop"]))
        if "triggers" in extra:
            value = mapping.triggers_value(extra["triggers"], raw.get("triggers"))
            if not value and raw.get("triggers"):  # svuotati davvero: la chiave sparisce dal file
                del raw["triggers"]
            else:
                mapping.put(raw, "triggers", value, default=[])
        return norm_area(extra["area"]) if "area" in extra else ...

    async def list_mobs(self, params: MobPageParams) -> PaginatedResponse[MobOut]:
        """Mob paginati (ordine di default per vnum), filtro `zoneId`, ricerca su descrizione/keywords/vnum."""
        self.sync()
        mobs = self.store.all_items("mob")
        if params.zone_id is not None:
            mobs = [m for m in mobs if m.zone.vnum == params.zone_id]
        return mob_query.page_mobs([mapping.mob_out(m, m.zone.vnum) for m in mobs], params)

    async def get_mob(self, mob_id: int) -> MobOut:
        """Un mob prototype."""
        mob = self.find_or_404("mob", mob_id, "mobs.not_found")
        return mapping.mob_out(mob, mob.zone.vnum)

    async def create_mob(self, data: MobIn) -> MobOut:
        """Crea un mob nel file `mobs.yaml` della zona (o in quello dell'area `extra.area`)."""
        self.ensure_writable()
        values = data.model_dump(by_alias=False, exclude={"extra", "zone_id"})
        check_extra(data.extra, MOB_EXTRA)
        async with self.writing():
            self.sync()
            if self.store.find("mob", data.vnum) is not None:
                raise conflict("mobs.vnum_taken", vnum=data.vnum)
            zone = self.zone_or_404(data.zone_id)
            file = self.store.file_for(zone, "mob", norm_area(data.extra.get("area")))
            raw = CommentedMap()
            mapping.mob_apply(raw, values)
            self._mob_extra(raw, {k: v for k, v in data.extra.items() if k != "area"})
            raw = _ordered(raw, mapping.MOB_ORDER)
            LoaderMob.model_validate(plain(raw))
            file.list_of(create=True).append(raw)
            self.store.save(file)
            return await self.get_mob(data.vnum)

    async def update_mob(self, mob_id: int, data: MobPatch) -> MobOut:
        """Aggiornamento parziale. Cambiare il vnum e' 409 `mobs.vnum_in_use` se un reset lo usa; `zoneId` (o
        `extra.area`) sposta il mob in un altro file."""
        self.ensure_writable()
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude={"extra"})
        async with self.writing():
            mob = self.find_or_404("mob", mob_id, "mobs.not_found")
            new_vnum = changes.get("vnum", mob.vnum)
            if new_vnum != mob.vnum:
                if self.store.find("mob", new_vnum) is not None:
                    raise conflict("mobs.vnum_taken", vnum=new_vnum)
                self.ensure_unused("mob", mob.vnum, "mobs.vnum_in_use")
            area = self._mob_extra(mob.raw, data.extra or {})
            mapping.mob_apply(mob.raw, {k: v for k, v in changes.items() if k != "zone_id"}, mob.model)
            self._relocate(mob, changes.get("zone_id"), area)
            return await self._after_save(mob, "mob")

    def _relocate(self, item: Item, zone_id: int | None, area: Any) -> None:
        """Sposta la voce nel file della zona/area di destinazione (se diversa) e rinfresca il suo modello."""
        item.revalidate()
        target_zone = self.zone_or_404(zone_id) if zone_id is not None and zone_id != item.zone.vnum else item.zone
        target_area = item.area if area is ... else area
        touched = {item.file}
        if target_zone is not item.zone or target_area != item.area:
            target_file = self.store.file_for(target_zone, item.kind, target_area)
            if target_file is not item.file:
                move_raw(item, target_file)
                touched.add(target_file)
        self.store.save(*touched)

    async def _after_save(self, item: Item, kind: str) -> Any:
        """Il DTO aggiornato dell'entita' (riletta dopo il salvataggio, che ha ricostruito gli indici)."""
        return await (self.get_mob if kind == "mob" else self.get_object)(item.vnum)

    async def delete_mob(self, mob_id: int) -> None:
        """Elimina il mob: 409 `mobs.in_reset_usage` se un reset lo referenzia."""
        self.ensure_writable()
        async with self.writing():
            mob = self.find_or_404("mob", mob_id, "mobs.not_found")
            self.ensure_unused("mob", mob_id, "mobs.in_reset_usage")
            _remove(mob)
            self.store.save(mob.file)

    async def mob_usage(self, mob_id: int) -> list[ResetUsage]:
        """I reset che referenziano il mob per vnum."""
        self.find_or_404("mob", mob_id, "mobs.not_found")
        return self.find_usage("mob", mob_id)

    # ------------------------------------------------------------------ oggetti

    @staticmethod
    def _object_fields(object_type: str, data_values: list[int | None], extra: dict[str, Any], *, lenient: bool = False) -> dict[str, Any]:
        """I campi del tipo da scrivere: prima i `value_N` numerici dati, poi `extra.typeFields` (che prevale); con
        `lenient` (cambio di tipo) le chiavi del vecchio tipo che il nuovo non ha sono ignorate."""
        fields = mapping.values_to_fields(object_type, {i: v for i, v in enumerate(data_values) if v is not None})
        given = extra.get("typeFields") or {}
        fields.update({k: v for k, v in given.items() if not lenient or k in type_fields(object_type)})
        return fields

    async def list_objects(self, params: ObjectPageParams) -> PaginatedResponse[ObjectOut]:
        """Oggetti paginati (ordine di default per vnum), filtro `zoneId`, ricerca su descrizione/keywords/vnum."""
        self.sync()
        objects = self.store.all_items("object")
        if params.zone_id is not None:
            objects = [o for o in objects if o.zone.vnum == params.zone_id]
        return object_query.page_objects([mapping.object_out(o, o.zone.vnum) for o in objects], params)

    async def get_object(self, object_id: int) -> ObjectOut:
        """Un object prototype."""
        obj = self.find_or_404("object", object_id, "objects.not_found")
        return mapping.object_out(obj, obj.zone.vnum)

    async def create_object(self, data: ObjectIn) -> ObjectOut:
        """Crea un oggetto nel file `objects.yaml` della zona (o in quello dell'area `extra.area`)."""
        self.ensure_writable()
        values = data.model_dump(by_alias=False, exclude={"extra", "zone_id"})
        check_extra(data.extra, OBJECT_EXTRA)
        async with self.writing():
            self.sync()
            if self.store.find("object", data.vnum) is not None:
                raise conflict("objects.vnum_taken", vnum=data.vnum)
            zone = self.zone_or_404(data.zone_id)
            file = self.store.file_for(zone, "object", norm_area(data.extra.get("area")))
            raw = CommentedMap()
            type_name = mapping.type_name(data.object_type)
            fields = self._object_fields(type_name, [data.value_0, data.value_1, data.value_2, data.value_3], data.extra)
            mapping.object_apply(raw, values, fields)
            mapping.apply_object_extra_descriptions(raw, data.extra)
            mapping.check_object(raw)
            file.list_of(create=True).append(raw)
            self.store.save(file)
            return await self.get_object(data.vnum)

    async def update_object(self, object_id: int, data: ObjectPatch) -> ObjectOut:
        """Aggiornamento parziale. Cambiare il vnum e' 409 `objects.vnum_in_use` se un reset o la chiave di un'uscita
        lo referenzia; `zoneId` (o `extra.area`) sposta l'oggetto in un altro file."""
        self.ensure_writable()
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude={"extra"})
        extra = data.extra or {}
        check_extra(extra, OBJECT_EXTRA)
        async with self.writing():
            obj = self.find_or_404("object", object_id, "objects.not_found")
            new_vnum = changes.get("vnum", obj.vnum)
            if new_vnum != obj.vnum:
                if self.store.find("object", new_vnum) is not None:
                    raise conflict("objects.vnum_taken", vnum=new_vnum)
                self.ensure_unused("object", obj.vnum, "objects.vnum_in_use")
            new_type = mapping.type_name(ObjectType(changes["object_type"])) if "object_type" in changes else obj.model.object_type
            values = [changes.get(f"value_{i}") for i in range(4)]
            fields = self._object_fields(new_type, values, extra, lenient="object_type" in changes)
            mapping.object_apply(obj.raw, {k: v for k, v in changes.items() if k != "zone_id"}, fields)
            mapping.apply_object_extra_descriptions(obj.raw, extra)
            mapping.check_object(obj.raw)
            self._relocate(obj, changes.get("zone_id"), norm_area(extra["area"]) if "area" in extra else ...)
            return await self._after_save(obj, "object")

    async def delete_object(self, object_id: int) -> None:
        """Elimina l'oggetto: 409 `objects.in_reset_usage` o `objects.in_exit_key_usage`."""
        self.ensure_writable()
        async with self.writing():
            obj = self.find_or_404("object", object_id, "objects.not_found")
            self.ensure_unused("object", object_id, "objects.in_reset_usage", include_exit_keys=False)
            self.ensure_unused("object", object_id, "objects.in_exit_key_usage")
            _remove(obj)
            self.store.save(obj.file)

    async def object_usage(self, object_id: int) -> list[ResetUsage]:
        """I reset (e le chiavi di uscite) che referenziano l'oggetto per vnum."""
        self.find_or_404("object", object_id, "objects.not_found")
        return self.find_usage("object", object_id)


def _remove(item: Item) -> None:
    """Toglie la voce (per identita') dalla lista del suo file."""
    seq = item.file.list_of()
    assert seq is not None
    for index, candidate in enumerate(seq):
        if candidate is item.raw:
            del seq[index]
            return


def _ordered(raw: Any, order: tuple[str, ...]) -> Any:
    """Un `CommentedMap` con le chiavi nell'ordine dei file del gioco (le altre in coda)."""
    out = CommentedMap()
    for key in order:
        if key in raw:
            out[key] = raw[key]
    for key in raw:
        if key not in out:
            out[key] = raw[key]
    return out
