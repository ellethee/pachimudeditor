"""Mob e oggetti prototipo (mixin di `BasedMudAdapter`).

Negozio (`#SHOPS`) e spec_fun (`#SPECIALS`) di un mob stanno nel suo `extra` (`shop`, `special`) ma vivono in sezioni
separate del file: seguono il mob quando cambia vnum o zona e vanno via quando il mob viene eliminato.
"""

from typing import Any, Callable

from pachimudeditor_adapter_basedmud.rom_lib import Mobile, Shop, Special
from pachifast.schemas.responses import PaginatedResponse

from pachimudeditor_adapter_basedmud import mapping
from pachimudeditor_adapter_basedmud.base import BasedMudSupport, make_page, paginate_list
from pachimudeditor_adapter_basedmud.store import AreaEntry
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
from pachimudeditor.sdk import conflict


def _section_items(entry: AreaEntry, kind: str) -> list[Any]:
    """Gli elementi della sezione `kind` (SHOPS/SPECIALS) senza crearla."""
    section = entry.area.section(kind, create=False)
    return section.items if section is not None else []


def shop_of(entry: AreaEntry, vnum: int) -> Shop | None:
    """Il negozio il cui keeper e' `vnum`."""
    return next((s for s in _section_items(entry, "SHOPS") if isinstance(s, Shop) and s.keeper == vnum), None)


def special_of(entry: AreaEntry, vnum: int) -> Special | None:
    """La special procedure del mob `vnum`."""
    return next((s for s in _section_items(entry, "SPECIALS") if isinstance(s, Special) and s.mob_vnum == vnum), None)


def _drop(entry: AreaEntry, kind: str, item: Any) -> None:
    """Toglie `item` (per identita') dalla sezione `kind`."""
    items = _section_items(entry, kind)
    items[:] = [i for i in items if i is not item]


class PrototypesMixin(BasedMudSupport):
    """Operazioni su mob e oggetti prototipo."""

    # ------------------------------------------------------------------ mob

    def _mob_out(self, entry: AreaEntry, mob: Mobile) -> MobOut:
        """DTO di un mob (con negozio e spec_fun del suo keeper)."""
        return mapping.mob_out(mob, entry.zone_id, shop_of(entry, mob.vnum), special_of(entry, mob.vnum))

    def _mob_callbacks(self, entry: AreaEntry, vnum: int) -> tuple[Callable[[Any], None], Callable[[Any], None]]:
        """Handler di `extra.shop` ed `extra.special`: toccano `#SHOPS` e `#SPECIALS` dell'area."""

        def shop(value: Any) -> None:
            """Crea/aggiorna/toglie il negozio del mob."""
            current = shop_of(entry, vnum)
            if value == mapping.shop_out(current):
                return
            if value is None:
                _drop(entry, "SHOPS", current)
                return
            if current is None:
                current = Shop(keeper=vnum)
                entry.area.shops.append(current)
            mapping.shop_apply(current, value)

        def special(value: Any) -> None:
            """Imposta/toglie la spec_fun del mob."""
            current = special_of(entry, vnum)
            if current is not None and value == current.function or current is None and value is None:
                return
            if value is None:
                _drop(entry, "SPECIALS", current)
            elif current is None:
                entry.area.specials.append(Special(mob_vnum=vnum, function=str(value)))
            else:
                current.function = str(value)

        return shop, special

    async def list_mobs(self, params: MobPageParams) -> PaginatedResponse[MobOut]:
        """Mob paginati (ordine di default per vnum), filtro `zoneId`, ricerca su descrizione/keywords/vnum."""
        self.sync()
        pairs = self.store.all_items("mob")
        if params.zone_id is not None:
            pairs = [p for p in pairs if p[0].zone_id == params.zone_id]
        keys = {"id": lambda m: m.vnum, "vnum": lambda m: m.vnum, "level": lambda m: m.level}
        items, total = paginate_list(
            pairs, params, lambda p: (p[1].short_descr, p[1].name, p[1].vnum), lambda p, f: keys[f](p[1]),
            MobPageParams.order_fields or [],
        )  # fmt: skip
        return make_page(MobOut, [self._mob_out(e, m) for e, m in items], total, params)

    async def get_mob(self, mob_id: int) -> MobOut:
        """Un mob prototype."""
        entry, mob = self.find_or_404("mob", mob_id, "mobs.not_found")
        return self._mob_out(entry, mob)

    async def create_mob(self, data: MobIn) -> MobOut:
        """Crea un mob (vnum libero e dentro il range della zona)."""
        self.ensure_writable()
        values = data.model_dump(by_alias=False, exclude={"extra"})
        async with self.writing():
            self.sync()
            if self.store.find("mob", data.vnum) is not None:
                raise conflict("mobs.vnum_taken", vnum=data.vnum)
            entry = self.zone_or_404(data.zone_id)
            self.check_vnum_in_range(entry, data.vnum)
            mob = mapping.new_mobile(data.vnum, values)
            mapping.apply_extra(data.extra, mapping.mob_extra_handlers(mob, *self._mob_callbacks(entry, data.vnum)))
            entry.writable_items("mob").append(mob)
            self.store.save(entry)
            return await self.get_mob(data.vnum)

    async def update_mob(self, mob_id: int, data: MobPatch) -> MobOut:
        """Aggiornamento parziale. Cambiare il vnum e' 409 `mobs.vnum_in_use` se un reset lo usa (negozio e spec_fun
        seguono il mob); `zoneId` sposta il mob in un altro file."""
        self.ensure_writable()
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude={"extra"})
        async with self.writing():
            entry, mob = self.find_or_404("mob", mob_id, "mobs.not_found")
            new_vnum = changes.get("vnum", mob.vnum)
            if new_vnum != mob.vnum:
                if self.store.find("mob", new_vnum) is not None:
                    raise conflict("mobs.vnum_taken", vnum=new_vnum)
                self.ensure_unused("mob", mob.vnum, "mobs.vnum_in_use")
            target = self.zone_or_404(changes["zone_id"]) if changes.get("zone_id", entry.zone_id) != entry.zone_id else entry
            if new_vnum != mob.vnum or target is not entry:
                self.check_vnum_in_range(target, new_vnum)
            mapping.apply_mob_fields(mob, changes)
            mapping.apply_extra(data.extra or {}, mapping.mob_extra_handlers(mob, *self._mob_callbacks(entry, mob.vnum)))
            shop, special = shop_of(entry, mob.vnum), special_of(entry, mob.vnum)
            if new_vnum != mob.vnum:
                mob.vnum = new_vnum
                if shop:
                    shop.keeper = new_vnum
                if special:
                    special.mob_vnum = new_vnum
            if target is not entry:
                entry.remove("mob", mob)
                target.writable_items("mob").append(mob)
                for item, kind, section in ((shop, "SHOPS", target.area.shops), (special, "SPECIALS", target.area.specials)):
                    if item is not None:
                        _drop(entry, kind, item)
                        section.append(item)
            self.store.save(*{entry, target})
            return await self.get_mob(new_vnum)

    async def delete_mob(self, mob_id: int) -> None:
        """Elimina il mob (con il suo negozio e la sua spec_fun): 409 `mobs.in_reset_usage` se un reset lo usa."""
        self.ensure_writable()
        async with self.writing():
            entry, mob = self.find_or_404("mob", mob_id, "mobs.not_found")
            self.ensure_unused("mob", mob_id, "mobs.in_reset_usage")
            for item, kind in ((shop_of(entry, mob_id), "SHOPS"), (special_of(entry, mob_id), "SPECIALS")):
                if item is not None:
                    _drop(entry, kind, item)
            entry.remove("mob", mob)
            self.store.save(entry)

    async def mob_usage(self, mob_id: int) -> list[ResetUsage]:
        """I reset che referenziano il mob per vnum."""
        self.find_or_404("mob", mob_id, "mobs.not_found")
        return self.find_usage("mob", mob_id)

    # ------------------------------------------------------------------ oggetti

    async def list_objects(self, params: ObjectPageParams) -> PaginatedResponse[ObjectOut]:
        """Oggetti paginati (ordine di default per vnum), filtro `zoneId`, ricerca su descrizione/keywords/vnum."""
        self.sync()
        pairs = self.store.all_items("object")
        if params.zone_id is not None:
            pairs = [p for p in pairs if p[0].zone_id == params.zone_id]
        keys = {
            "id": lambda o: o.vnum, "vnum": lambda o: o.vnum,
            "object_type": lambda o: int(mapping.ITEM_TO_DTO.get(o.item_type, mapping.ObjectType.OTHER)),
        }  # fmt: skip
        items, total = paginate_list(
            pairs, params, lambda p: (p[1].short_descr, p[1].name, p[1].vnum), lambda p, f: keys[f](p[1]),
            ObjectPageParams.order_fields or [],
        )  # fmt: skip
        return make_page(ObjectOut, [mapping.object_out(o, e.zone_id) for e, o in items], total, params)

    async def get_object(self, object_id: int) -> ObjectOut:
        """Un object prototype."""
        entry, obj = self.find_or_404("object", object_id, "objects.not_found")
        return mapping.object_out(obj, entry.zone_id)

    async def create_object(self, data: ObjectIn) -> ObjectOut:
        """Crea un oggetto (vnum libero e dentro il range della zona)."""
        self.ensure_writable()
        values = data.model_dump(by_alias=False, exclude={"extra"})
        async with self.writing():
            self.sync()
            if self.store.find("object", data.vnum) is not None:
                raise conflict("objects.vnum_taken", vnum=data.vnum)
            entry = self.zone_or_404(data.zone_id)
            self.check_vnum_in_range(entry, data.vnum)
            obj = mapping.new_object(data.vnum, values)
            mapping.apply_extra(data.extra, mapping.object_extra_handlers(obj))
            entry.writable_items("object").append(obj)
            self.store.save(entry)
            return await self.get_object(data.vnum)

    async def update_object(self, object_id: int, data: ObjectPatch) -> ObjectOut:
        """Aggiornamento parziale. Cambiare il vnum e' 409 `objects.vnum_in_use` se un reset o la chiave di un'uscita
        lo referenzia; `zoneId` sposta l'oggetto in un altro file."""
        self.ensure_writable()
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude={"extra"})
        async with self.writing():
            entry, obj = self.find_or_404("object", object_id, "objects.not_found")
            new_vnum = changes.get("vnum", obj.vnum)
            if new_vnum != obj.vnum:
                if self.store.find("object", new_vnum) is not None:
                    raise conflict("objects.vnum_taken", vnum=new_vnum)
                self.ensure_unused("object", obj.vnum, "objects.vnum_in_use")
            target = self.zone_or_404(changes["zone_id"]) if changes.get("zone_id", entry.zone_id) != entry.zone_id else entry
            if new_vnum != obj.vnum or target is not entry:
                self.check_vnum_in_range(target, new_vnum)
            mapping.apply_object_fields(obj, changes)
            mapping.apply_extra(data.extra or {}, mapping.object_extra_handlers(obj))
            obj.vnum = new_vnum
            if target is not entry:
                entry.remove("object", obj)
                target.writable_items("object").append(obj)
            self.store.save(*{entry, target})
            return await self.get_object(new_vnum)

    async def delete_object(self, object_id: int) -> None:
        """Elimina l'oggetto: 409 `objects.in_reset_usage` o `objects.in_exit_key_usage`."""
        self.ensure_writable()
        async with self.writing():
            entry, obj = self.find_or_404("object", object_id, "objects.not_found")
            self.ensure_unused("object", object_id, "objects.in_reset_usage", include_exit_keys=False)
            self.ensure_unused("object", object_id, "objects.in_exit_key_usage")
            entry.remove("object", obj)
            self.store.save(entry)

    async def object_usage(self, object_id: int) -> list[ResetUsage]:
        """I reset (e le chiavi di uscite) che referenziano l'oggetto per vnum."""
        self.find_or_404("object", object_id, "objects.not_found")
        return self.find_usage("object", object_id)
