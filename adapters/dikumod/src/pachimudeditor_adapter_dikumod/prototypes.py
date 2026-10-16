"""Mob e oggetti prototipo (mixin di `DikumodAdapter`).

Negozio (`dikumoddata.shp`, per `keeper`) e script (`scripts.dat` + `scripts/<Nome>`) di un mob stanno nel suo `extra`
(`shop`, `script`) ma vivono in altri file: seguono il mob quando cambia vnum e vanno via quando viene eliminato.
I record corrotti (`extra.corrupted`) sono visibili ma non modificabili (409 `dikumod.record_corrupted`). Mob e oggetti
nuovi vanno nel file principale **in ordine di vnum** (il gioco li cerca in modo binario).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pachimudeditor_adapter_dikumod.dikumod_lib import RecordFile, ScriptEntry, Shop, insert_sorted
from pachifast.i18n import api_error
from pachifast.schemas.responses import PaginatedResponse

from pachimudeditor_adapter_dikumod import mapping
from pachimudeditor_adapter_dikumod.base import DikumodSupport
from pachimudeditor_adapter_dikumod.rooms import _drop
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


class PrototypesMixin(DikumodSupport):
    """Operazioni su mob e oggetti prototipo."""

    # ------------------------------------------------------------------ negozio e script

    def _script_of(self, vnum: int) -> dict[str, Any] | None:
        """`{name, text}` dello script del mob (testo del file `scripts/<Nome>`, `None` se il file manca)."""
        entry = self.store.script_by_vnum.get(vnum)
        if entry is None:
            return None
        try:
            text = self.store.text_of(self.store.paths.script_file(entry.name))
        except ValueError:
            text = None
        return {"name": entry.name, "text": text}

    def _mob_out(self, vnum: int) -> MobOut:
        """DTO del mob (sano o corrotto) dall'archivio aggiornato."""
        store = self.store
        ref = store.mobs.get(vnum)
        if ref is None:
            raw = store.raw_mobs[vnum]
            return mapping.corrupted_mob_out(vnum, raw.src, raw.error, raw.line, self.zone_id_of(vnum))
        return mapping.mob_out(
            ref.item, self.zone_id_of(vnum), store.shops.get(vnum), self._script_of(vnum), duplicate=vnum in store.duplicates["mob"]
        )

    def _healthy_mob(self, mob_id: int) -> Any:
        """`Ref` di un mob sano: 404 se non esiste, 409 `dikumod.record_corrupted` se e' corrotto."""
        store = self.sync()
        if mob_id in store.mobs:
            return store.mobs[mob_id]
        raw = store.raw_mobs.get(mob_id)
        if raw is None:
            raise api_error(404, "mobs.not_found")
        raise api_error(409, "dikumod.record_corrupted", vnum=mob_id, reason=raw.error)

    def _mob_callbacks(self, vnum: int, touched: set[RecordFile]) -> tuple[Callable[[Any], None], Callable[[Any], None]]:
        """Handler di `extra.shop` ed `extra.script`: toccano `dikumoddata.shp`, `scripts.dat` e `scripts/<Nome>`."""
        store = self.store

        def shop(value: Any) -> None:
            """Crea/aggiorna/toglie il negozio del mob."""
            current = store.shops.get(vnum)
            if value == mapping.shop_out(current):
                return
            if store.shp is None:
                raise api_error(422, "dikumod.no_shop_file", file=store.paths.named("shp").name)
            touched.add(store.shp)
            if value is None:
                _drop(store.shp, current)
                return
            if not isinstance(value, dict):
                raise mapping.bad("dikumod.extra_invalid", key="shop")
            if current is None:
                numbers = [int(i.tag[1:]) for i in store.shp.items if isinstance(i, Shop) and i.tag[1:].isdigit()]
                current = Shop(tag=f"#{max(numbers, default=-1) + 1}", keeper=vnum)
                insert_at = len(store.shp.items)
                store.shp.items.insert(insert_at, current)
            mapping.shop_apply(current, value)

        def script(value: Any) -> None:
            """Imposta/toglie lo script del mob (`null` toglie solo la riga di `scripts.dat`, il file resta)."""
            current = self._script_of(vnum)
            if value == current:
                return
            rf = store.scripts or RecordFile("scripts", store.paths.scripts_dat)
            touched.add(rf)
            entry = store.script_by_vnum.get(vnum)
            if value is None:
                _drop(rf, entry)
                return
            if not isinstance(value, dict) or not isinstance(value.get("name"), str):
                raise mapping.bad("dikumod.extra_invalid", key="script")
            name = value["name"]
            try:
                path = store.paths.script_file(name)
            except ValueError as error:
                raise mapping.bad("dikumod.extra_invalid", key="script.name") from error
            text = value.get("text")
            if isinstance(text, str):
                if text != store.text_of(path):
                    store.write_text_file(path, text.replace("\r", ""))
            elif store.text_of(path) is None:
                raise mapping.bad("dikumod.extra_invalid", key="script.text")
            if entry is None:
                rf.items.append(ScriptEntry(name, vnum))
            elif entry.name != name:
                entry.name = name

        return shop, script

    def _save_mob(self, touched: set[RecordFile]) -> None:
        """Salva i file toccati."""
        self.store.save(*touched)

    # ------------------------------------------------------------------ mob

    async def list_mobs(self, params: MobPageParams) -> PaginatedResponse[MobOut]:
        """Mob paginati (ordine di default per vnum, corrotti compresi), filtro `zoneId`, ricerca su descrizione/keywords/vnum."""
        store = self.sync()
        vnums = sorted({*store.mobs, *store.raw_mobs})
        if params.zone_id is not None:
            vnums = [v for v in vnums if self.zone_id_of(v) == params.zone_id]

        def mob_of(v: int) -> Any:
            """Il mob sano o, in mancanza, il corrotto."""
            return store.mobs[v].item if v in store.mobs else None

        def text(v: int) -> tuple[Any, ...]:
            """Testi su cui cerca."""
            m = mob_of(v)
            return (m.short, m.name, v) if m else (self._mob_out(v).short_description, self._mob_out(v).keywords, v)

        keys = {"id": lambda v: v, "vnum": lambda v: v, "level": lambda v: mob_of(v).level if mob_of(v) else 0}
        items, total = paginate_list(vnums, params, text, lambda v, f: keys[f](v), MobPageParams.order_fields or [])
        return make_page(MobOut, [self._mob_out(v) for v in items], total, params)

    async def get_mob(self, mob_id: int) -> MobOut:
        """Un mob prototype (se e' corrotto: segnaposto con `extra.corrupted`)."""
        store = self.sync()
        if mob_id not in store.mobs and mob_id not in store.raw_mobs:
            raise api_error(404, "mobs.not_found")
        return self._mob_out(mob_id)

    async def create_mob(self, data: MobIn) -> MobOut:
        """Crea un mob in `dikumoddata.mob` (vnum libero e nella zona indicata)."""
        values = data.model_dump(by_alias=False, exclude={"extra"})
        if not data.model_fields_set & {"hp_dice_count", "hp_die_size"}:
            values.pop("hp_dice_count"), values.pop("hp_die_size")  # non indicati: hp = level d8 + bonus (mob `N`)
        async with self.writing() as store:
            if data.vnum in store.mobs or data.vnum in store.raw_mobs:
                raise conflict("mobs.vnum_taken", vnum=data.vnum)
            self.zone_or_404(data.zone_id)
            self.check_vnum_in_zone(data.zone_id, data.vnum)
            touched: set[RecordFile] = {store.mob}  # type: ignore[arg-type]
            mob = mapping.new_mob(data.vnum, values)
            mapping.apply_extra(data.extra, mapping.mob_extra_handlers(mob, *self._mob_callbacks(data.vnum, touched)))
            insert_sorted(store.mob, mob)  # type: ignore[arg-type]
            self._save_mob(touched)
            return self._mob_out(data.vnum)

    async def update_mob(self, mob_id: int, data: MobPatch) -> MobOut:
        """Aggiornamento parziale. Cambiare il vnum e' 409 `mobs.vnum_in_use` se un reset lo usa (negozio e script
        seguono il mob); `zoneId` deve essere la zona del vnum (derivata)."""
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude={"extra"})
        async with self.writing() as store:
            ref = self._healthy_mob(mob_id)
            mob = ref.item
            new = changes.get("vnum", mob.vnum)
            touched: set[RecordFile] = set()
            before = repr(mob)
            if new != mob.vnum:
                if new in store.mobs or new in store.raw_mobs:
                    raise conflict("mobs.vnum_taken", vnum=new)
                self.ensure_unused("mob", mob.vnum, "mobs.vnum_in_use")
                if store.zone_of(new) is None:
                    raise api_error(422, "dikumod.vnum_out_of_range", vnum=new, bottom="-", top=store.tops[-1] if store.tops else "-")
            if changes.get("zone_id") is not None and changes["zone_id"] != self.zone_id_of(new):
                raise api_error(422, "dikumod.zone_derived", vnum=new, expected=self.zone_id_of(new))
            old = mob.vnum
            mapping.apply_mob_fields(mob, changes)
            mapping.apply_extra(data.extra or {}, mapping.mob_extra_handlers(mob, *self._mob_callbacks(old, touched)))
            if repr(mob) != before:
                touched.add(store.mob)  # type: ignore[arg-type]
            if new != old:
                touched.add(store.mob)  # type: ignore[arg-type]
                shop, entry = store.shops.get(old), store.script_by_vnum.get(old)
                mob.vnum = new
                _drop(store.mob, mob)  # type: ignore[arg-type]
                insert_sorted(store.mob, mob)  # type: ignore[arg-type]
                if shop is not None and store.shp is not None:
                    shop.keeper = new
                    touched.add(store.shp)
                if entry is not None and store.scripts is not None:
                    entry.vnum = new
                    touched.add(store.scripts)
            if touched:
                self._save_mob(touched)
            return self._mob_out(new)

    async def delete_mob(self, mob_id: int) -> None:
        """Elimina il mob (con negozio e riga di script): 409 `mobs.in_reset_usage` se un reset lo usa."""
        async with self.writing() as store:
            self._healthy_mob(mob_id)
            self.ensure_unused("mob", mob_id, "mobs.in_reset_usage")
            touched: set[RecordFile] = {store.mob}  # type: ignore[arg-type]
            store.mob.items[:] = [i for i in store.mob.items if getattr(i, "vnum", None) != mob_id or not hasattr(i, "kind")]  # type: ignore[union-attr]
            shop, entry = store.shops.get(mob_id), store.script_by_vnum.get(mob_id)
            if shop is not None and store.shp is not None:
                _drop(store.shp, shop)
                touched.add(store.shp)
            if entry is not None and store.scripts is not None:
                _drop(store.scripts, entry)
                touched.add(store.scripts)
            self._save_mob(touched)

    async def mob_usage(self, mob_id: int) -> list[ResetUsage]:
        """I comandi che referenziano il mob per vnum (`M`, `C`, `H`/`F` di tipo 7)."""
        store = self.sync()
        if mob_id not in store.mobs and mob_id not in store.raw_mobs:
            raise api_error(404, "mobs.not_found")
        return self.find_usage("mob", mob_id)

    # ------------------------------------------------------------------ oggetti

    def _object_out(self, vnum: int) -> ObjectOut:
        """DTO dell'oggetto dall'archivio aggiornato."""
        ref = self.store.objs[vnum]
        return mapping.object_out(ref.item, self.zone_id_of(vnum), override=ref.override, duplicate=vnum in self.store.duplicates["object"])

    async def list_objects(self, params: ObjectPageParams) -> PaginatedResponse[ObjectOut]:
        """Oggetti paginati (ordine di default per vnum), filtro `zoneId`, ricerca su descrizione/keywords/vnum."""
        store = self.sync()
        refs = sorted(store.objs.values(), key=lambda r: r.vnum)
        if params.zone_id is not None:
            refs = [r for r in refs if self.zone_id_of(r.vnum) == params.zone_id]
        keys = {
            "id": lambda r: r.vnum,
            "vnum": lambda r: r.vnum,
            "object_type": lambda r: int(mapping.ITEM_TO_DTO.get(r.item.type, mapping.ObjectType.OTHER)),
        }
        items, total = paginate_list(
            refs, params, lambda r: (r.item.short, r.item.name, r.vnum), lambda r, f: keys[f](r), ObjectPageParams.order_fields or []
        )
        dup = store.duplicates["object"]
        out = [mapping.object_out(r.item, self.zone_id_of(r.vnum), override=r.override, duplicate=r.vnum in dup) for r in items]
        return make_page(ObjectOut, out, total, params)

    async def get_object(self, object_id: int) -> ObjectOut:
        """Un object prototype."""
        self.find_or_404("object", object_id, "objects.not_found")
        return self._object_out(object_id)

    async def create_object(self, data: ObjectIn) -> ObjectOut:
        """Crea un oggetto in `dikumoddata.obj` (vnum libero e nella zona indicata)."""
        values = data.model_dump(by_alias=False, exclude={"extra"})
        async with self.writing() as store:
            if data.vnum in store.objs:
                raise conflict("objects.vnum_taken", vnum=data.vnum)
            self.zone_or_404(data.zone_id)
            self.check_vnum_in_zone(data.zone_id, data.vnum)
            obj = mapping.new_object(data.vnum, values)
            mapping.apply_extra(data.extra, mapping.object_extra_handlers(obj))
            insert_sorted(store.obj, obj)  # type: ignore[arg-type]
            store.save(store.obj)  # type: ignore[arg-type]
            return self._object_out(data.vnum)

    async def update_object(self, object_id: int, data: ObjectPatch) -> ObjectOut:
        """Aggiornamento parziale (scritto in `objects/<vnum>` se esiste). Cambiare il vnum e' 409 `objects.vnum_in_use`
        se un reset o la chiave di un'uscita lo referenzia, 422 `dikumod.override_vnum_locked` per un file per-vnum."""
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude={"extra"})
        async with self.writing() as store:
            ref = self.find_or_404("object", object_id, "objects.not_found")
            obj = ref.item
            new = changes.get("vnum", obj.vnum)
            if new != obj.vnum:
                if ref.override:
                    raise api_error(422, "dikumod.override_vnum_locked", vnum=obj.vnum)
                if new in store.objs:
                    raise conflict("objects.vnum_taken", vnum=new)
                self.ensure_unused("object", obj.vnum, "objects.vnum_in_use")
                if store.zone_of(new) is None:
                    raise api_error(422, "dikumod.vnum_out_of_range", vnum=new, bottom="-", top=store.tops[-1] if store.tops else "-")
            if changes.get("zone_id") is not None and changes["zone_id"] != self.zone_id_of(new):
                raise api_error(422, "dikumod.zone_derived", vnum=new, expected=self.zone_id_of(new))
            before = repr(obj)
            mapping.apply_object_fields(obj, changes)
            mapping.apply_extra(data.extra or {}, mapping.object_extra_handlers(obj))
            if new != obj.vnum:
                obj.vnum = new
                _drop(ref.rf, obj)
                insert_sorted(ref.rf, obj)
            if new != ref.vnum or repr(obj) != before:
                store.save(ref.rf)
            return self._object_out(new)

    async def delete_object(self, object_id: int) -> None:
        """Elimina l'oggetto (e il suo `objects/<vnum>`): 409 `objects.in_reset_usage` o `objects.in_exit_key_usage`."""
        async with self.writing() as store:
            ref = self.find_or_404("object", object_id, "objects.not_found")
            self.ensure_unused("object", object_id, "objects.in_reset_usage", include_exit_keys=False)
            self.ensure_unused("object", object_id, "objects.in_exit_key_usage")
            override_path = store.obj_overrides.get(object_id)
            store.obj.items[:] = [i for i in store.obj.items if getattr(i, "vnum", None) != object_id]  # type: ignore[union-attr]
            store.save(store.obj)  # type: ignore[arg-type]
            if override_path is not None:
                store.delete_file(override_path)
            del ref

    async def object_usage(self, object_id: int) -> list[ResetUsage]:
        """I comandi (e le chiavi di uscite) che referenziano l'oggetto per vnum."""
        self.find_or_404("object", object_id, "objects.not_found")
        return self.find_usage("object", object_id)
