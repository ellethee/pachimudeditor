"""Zone e script di reset (mixin di `MappingAdapter`)."""

import copy
import re
from typing import Any

from pachifast.i18n import api_error
from pachifast.schemas.responses import PaginatedResponse

from pachimudeditor_adapter_mapping.base import MappingSupport
from pachimudeditor_adapter_mapping.grammar import Document, Record, Section
from pachimudeditor_adapter_mapping.model import Binding
from pachimudeditor_adapter_mapping.store import ZoneUnit
from pachimudeditor.sdk import rules
from pachimudeditor.common.adapters.models import (
    EntityKind,
    NextZoneVnum,
    ResetCommandOut,
    ResetDraftScriptIn,
    ResetScriptIn,
    ResetValidation,
    ZoneCloneIn,
    ZoneIn,
    ZoneOut,
    ZonePageParams,
    ZonePatch,
    ZoneSummary,
)
from pachimudeditor.sdk import make_page, paginate_list
from pachimudeditor.sdk import conflict

_STRUCTURAL = frozenset({"vnum", "bottom_vnum", "top_vnum", "enabled", "extra"})
_VIRTUAL_EXTRA = ("file", "style")


def _slug(name: str) -> str:
    """Base del nome di file da un nome di zona (`Foresta Nera` -> `forestanera`)."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())[:20] or "zona"


class ZonesMixin(MappingSupport):
    """Operazioni su zone e script di reset."""

    # ------------------------------------------------------------------ utilita'

    def _zone_out(self, unit: ZoneUnit) -> ZoneOut:
        """DTO di una zona. `extra` ha `file` e `style` (layout `zone_files`) piu' i campi non mappati dell'intestazione."""
        values = self.zone_map.read(unit.header.fields)
        extra = values.pop("extra")
        if self.spec.layout.mode == "zone_files":
            extra = {"file": unit.file.name, "style": unit.header.style, **extra}
        return ZoneOut(
            id=unit.zone_id, vnum=unit.zone_id, bottom_vnum=unit.bottom, top_vnum=unit.top, enabled=unit.listed, extra=extra, **values
        )  # fmt: skip

    def _range_bindings(self) -> dict[str, Binding]:
        """Binding di scrittura degli estremi del range (`bottom` solo con `mode: fields`)."""
        zr = self.spec.layout.zone_range
        steps: dict[str, Any] = {}
        return {
            name: Binding(f"{name}_vnum", fm, int, False, steps, self.tables)
            for name, fm in (("bottom", zr.bottom), ("top", zr.top))
            if fm is not None and (name == "top" or zr.mode == "fields")
        }

    def _write_range(self, fields: dict[str, Any], bottom: int, top: int) -> None:
        """Scrive entrambi gli estremi del range nei campi dell'intestazione (insieme: un solo estremo lascerebbe incoerente)."""
        binds = self._range_bindings()
        for name, value in (("bottom", bottom), ("top", top)):
            if name in binds:
                binds[name].write(fields, value, None)

    def _check_new_zone(self, vnum: int, bottom: int, top: int, *, skip: ZoneUnit | None = None) -> None:
        """409 `zones.vnum_taken` / `zones.range_overlap` per una zona con questo vnum e range."""
        ranged = (bottom, top) != (0, 0)
        others = [z for z in self.store.zones if z is not skip]
        if ranged:
            clash = rules.range_clash(((self.zone_name(z), z.zone_id, z.bottom, z.top) for z in others), bottom, top)
            if clash is not None:
                raise conflict("zones.range_overlap", zone=clash[0], zone_vnum=clash[1])
        rule = self.spec.model.zone.id
        key = {"bottom": bottom, "top": top, "position": None}[rule]
        key = key if ranged and key is not None else vnum
        if rule != "position" and key in {z.zone_id for z in others}:
            raise conflict("zones.vnum_taken", vnum=key)

    def _new_file_name(self, requested: Any, name: str) -> str:
        """Nome del nuovo file: `extra.file` (validato, 409 se esiste) oppure uno derivato da `name` col modello di `new_zone.file`."""
        if requested:
            self.store.safe_path(str(requested))
            if (self.store.root / str(requested)).exists():
                raise conflict("mapping.file_exists", name=str(requested))
            return str(requested)
        template, n = self.spec.layout.new_zone.file, 1
        while (self.store.root / template.format(slug=f"{_slug(name)}{'' if n == 1 else n}")).exists():
            n += 1
        return template.format(slug=f"{_slug(name)}{'' if n == 1 else n}")

    def _header_spec(self, style: str | None) -> Any:
        """Sezione di intestazione della zona con quello stile (default: `new_zone.style` o la prima)."""
        style = style or self.spec.layout.new_zone.style
        spec = self.store.spec_for(self.spec.layout.zone_file or "", self.spec.model.zone.entity, style)
        if spec is None:
            raise api_error(422, "mapping.unknown_style", style=str(style))
        return spec

    def _check_extra_readonly(self, unit: ZoneUnit, extra: dict[str, Any]) -> dict[str, Any]:
        """Toglie da `extra` le chiavi virtuali (`file`, `style`): ammesse solo col valore corrente (422 altrimenti)."""
        rest = dict(extra)
        current = {"file": unit.file.name, "style": unit.header.style}
        for key in _VIRTUAL_EXTRA:
            if key in rest and rest.pop(key) != current[key]:
                raise api_error(422, "mapping.extra_readonly", key=key)
        return rest

    # ------------------------------------------------------------------ zone

    async def list_zones(self, params: ZonePageParams) -> PaginatedResponse[ZoneOut]:
        """Zone paginate (ordine di default per vnum), cercabili per nome/builder/vnum."""
        self.sync()
        zones = sorted((self._zone_out(u) for u in self.store.zones), key=lambda z: z.id)
        items, total = paginate_list(
            zones, params, lambda z: (z.name, z.builder, z.vnum), lambda z, f: getattr(z, f), ZonePageParams.order_fields or []
        )
        return make_page(ZoneOut, items, total, params)

    async def get_zone(self, zone_id: int) -> ZoneOut:
        """Una zona (404 `zones.not_found`)."""
        return self._zone_out(self.zone_or_404(zone_id))

    async def create_zone(self, data: ZoneIn) -> ZoneOut:
        """Crea una zona: un nuovo file (layout `zone_files`, elencato nell'indice se `enabled`) oppure un record nel file
        di zona (`type_files`, solo in coda: `topVnum` oltre l'ultima zona e `bottomVnum` = ultimo `top` + 1).

        `extra` ammette `file` e `style` (solo `zone_files`) e le chiavi dei campi non mappati dell'intestazione.
        """
        self.ensure_writable()
        values = data.model_dump(by_alias=False, exclude=_STRUCTURAL)
        async with self.writing():
            self.sync()
            lay = self.spec.layout
            self._check_new_zone(data.vnum, data.bottom_vnum, data.top_vnum)
            extra = dict(data.extra)
            style, file_name = extra.pop("style", None), extra.pop("file", None)
            if lay.mode == "type_files":
                last = max((z.top for z in self.store.zones), default=-1)
                if data.top_vnum <= last:
                    raise api_error(422, "mapping.zone_top_not_last", top=data.top_vnum, last=last)
                if data.bottom_vnum != last + 1:
                    raise api_error(422, "mapping.zone_bottom_derived", bottom=last + 1)
            spec = self._header_spec(style) if lay.mode == "zone_files" else self.store.target_file(None, self.spec.model.zone.entity)[1]
            fields = self.zone_map.new_fields(self.spec, spec.record)
            self.zone_map.apply(fields, values, extra)
            self._write_range(fields, data.bottom_vnum, data.top_vnum)
            rec = Record(spec.entity, fields, spec.record, spec.header or "")
            if lay.mode == "type_files":
                entry = self.store.insert_record(None, rec, sort_key=lambda r: self.store.range_of(lay.zone_range.top, r.fields))  # type: ignore[arg-type]
                self.store.save(entry)
                return self._zone_out(next(z for z in self.store.zones if z.top == data.top_vnum))
            name = self._new_file_name(file_name, data.name)
            fg = self.spec.grammar.files[lay.zone_file or ""]
            doc = Document(sections=[Section(spec, spec.header or spec.entity, [rec])], has_end=bool(fg.end))
            return self._zone_out(self._unit_of(self.store.new_file(name, lay.zone_file or "", doc, listed=data.enabled)))

    def _unit_of(self, entry: Any) -> ZoneUnit:
        """La zona definita dal file `entry` (`zone_files`)."""
        return next(z for z in self.store.zones if z.file.name == entry.name)

    async def update_zone(self, zone_id: int, data: ZonePatch) -> ZoneOut:
        """Aggiornamento parziale dell'intestazione.

        `vnum` coincide con l'estremo del range da cui deriva l'id e non si cambia da solo; `enabled` aggiunge/toglie il
        file dall'indice (solo se il layout ne ha uno); con `zone_range.mode: top` il `bottomVnum` e' derivato.
        """
        self.ensure_writable()
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude={"extra"})
        async with self.writing():
            unit = self.zone_or_404(zone_id)
            lay, current = self.spec.layout, self._zone_out(unit)
            bottom, top = changes.get("bottom_vnum", unit.bottom), changes.get("top_vnum", unit.top)
            low, high = changes.get("min_level", current.min_level), changes.get("max_level", current.max_level)
            rules.check_zone_ranges(bottom, top, low, high)
            rule = self.spec.model.zone.id
            if "vnum" in changes and changes["vnum"] not in (unit.zone_id, {"bottom": bottom, "top": top}.get(rule)):
                raise api_error(422, "mapping.zone_vnum_is_range", vnum=changes["vnum"])
            fields = copy.deepcopy(unit.header.fields)
            if (bottom, top) != (unit.bottom, unit.top):
                if lay.zone_range.mode == "fields":
                    self._check_new_zone(unit.zone_id, bottom, top, skip=unit)
                else:
                    self._check_top_change(unit, bottom, top)
                self._write_range(fields, bottom, top)
            self.zone_map.apply(
                fields, {k: v for k, v in changes.items() if k not in _STRUCTURAL}, self._check_extra_readonly(unit, data.extra or {})
            )
            if "enabled" in changes and changes["enabled"] != unit.listed and not lay.index:
                raise api_error(422, "mapping.field_unsupported", field="enabled")
            name = unit.file.name
            if fields != unit.header.fields:
                unit.header.fields.clear()
                unit.header.fields.update(fields)
                self.store.save(unit.file)
            if "enabled" in changes and lay.index and changes["enabled"] != unit.listed:
                self.store.set_listed(name, changes["enabled"])
            self.store.refresh()
            if lay.mode == "zone_files":
                return self._zone_out(self._unit_of(self.store.entries[name]))
            return self._zone_out(next(z for z in self.store.zones if z.top == top))

    def _check_top_change(self, unit: ZoneUnit, bottom: int, top: int) -> None:
        """Layout a catena (`mode: top`): `bottom` e' derivato, `top` non puo' scavalcare le zone vicine ne' spostare entita'."""
        if bottom != unit.bottom:
            raise api_error(422, "mapping.zone_bottom_derived", bottom=unit.bottom)
        zones = self.store.zones
        i = zones.index(unit)
        lower, upper = (zones[i - 1].top if i else -1), (zones[i + 1].top if i + 1 < len(zones) else None)
        if top <= lower or (upper is not None and top >= upper):
            raise api_error(422, "mapping.zone_top_order", top=top)
        lo, hi = sorted((unit.top, top))
        for kind in ("room", "mob", "object"):
            if any(lo < v <= hi for v in self.store.vnums(kind)):
                raise api_error(422, "mapping.zone_range_has_items", top=top)

    async def delete_zone(self, zone_id: int) -> None:
        """Elimina la zona (file + riga dell'indice, oppure il record di zona); 409 `zones.not_empty` se ha contenuto."""
        self.ensure_writable()
        async with self.writing():
            unit = self.zone_or_404(zone_id)
            summary = self._summary(unit)
            if summary.room_count or summary.mob_count or summary.object_count:
                raise conflict("zones.not_empty", rooms=summary.room_count, mobs=summary.mob_count, objects=summary.object_count)
            if self.spec.layout.mode == "zone_files":
                self.store.delete_file(unit.file)
            else:
                self.store.remove_record(unit.header)
                self.store.save(unit.file)

    @staticmethod
    def _summary(unit: ZoneUnit) -> ZoneSummary:
        """Conteggi del contenuto di una zona."""
        return ZoneSummary(room_count=len(unit.items["room"]), mob_count=len(unit.items["mob"]), object_count=len(unit.items["object"]))

    async def zone_summary(self, zone_id: int) -> ZoneSummary:
        """Conteggi di stanze, mob e oggetti."""
        return self._summary(self.zone_or_404(zone_id))

    async def next_zone_vnum(self, span: int) -> NextZoneVnum:
        """Un range libero di ampiezza `span` oltre l'ultima zona (partenza arrotondata a `zone_alignment`; con
        `mode: top` subito dopo l'ultimo `top`) e il vnum di zona che ne deriva."""
        self.sync()
        tops = [z.top for z in self.store.zones if (z.bottom, z.top) != (0, 0)]
        if self.spec.layout.zone_range.mode == "top":
            bottom = max(tops, default=-1) + 1
        else:
            align = self.rules.zone_alignment
            bottom = max(align, -(-(max(tops, default=0) + 1) // align) * align)
        top = bottom + span
        rule = self.spec.model.zone.id
        return NextZoneVnum(
            vnum={"bottom": bottom, "top": top, "position": len(self.store.zones) + 1}[rule], bottom_vnum=bottom, top_vnum=top
        )

    async def next_content_vnum(self, zone_id: int, kind: EntityKind) -> int:
        """Un vnum libero: uno oltre il piu' alto della zona (o il vnum minimo se vuota), saltando i vnum occupati; se
        cosi' si esce dal range della zona torna il primo buco libero dentro il range (se esiste)."""
        unit = self.zone_or_404(zone_id)
        taken = self.store.vnums(kind)
        highest = max((self.vnum(r) for r in unit.items[kind]), default=None)
        candidate = highest + 1 if highest is not None else unit.bottom
        free = rules.first_free_vnum(candidate, {v for v in taken if v >= candidate})
        if (unit.bottom, unit.top) != (0, 0) and free > unit.top:
            gap = rules.first_free_vnum(unit.bottom, {v for v in taken if v >= unit.bottom})
            if gap <= unit.top:
                return gap
        return free

    async def clone_zone(self, zone_id: int, data: ZoneCloneIn) -> ZoneOut:
        """Duplica l'intestazione in un nuovo file (non il contenuto); opzionalmente copia lo script di reset.
        Range della copia da `bottomVnum`/`topVnum` (409 `zones.range_overlap`) oppure 0-0. Solo layout `zone_files`."""
        self.ensure_writable()
        if self.spec.layout.mode != "zone_files":
            raise api_error(422, "mapping.clone_unsupported")
        async with self.writing():
            source = self.zone_or_404(zone_id)
            bottom, top = data.bottom_vnum or 0, data.top_vnum or 0
            self._check_new_zone(data.vnum, bottom, top)
            fields = copy.deepcopy(source.header.fields)
            self.zone_map.apply(fields, {"name": data.name})
            self._write_range(fields, bottom, top)
            spec = self.store.spec_for(source.file.kind, self.spec.model.zone.entity, source.header.style)
            sections = [Section(spec, spec.header or spec.entity, [Record(spec.entity, fields, spec.record, spec.header or "")])]
            resets = self.spec.model.zone.resets
            if resets and resets.field and not data.copy_reset_commands:
                fields[resets.field] = []
            if resets and resets.section and data.copy_reset_commands:
                rspec = self._reset_section(source)
                sections.append(
                    Section(
                        rspec,
                        rspec.header or rspec.entity,
                        [Record(r.entity, copy.deepcopy(r.fields), r.rname, r.style, r.src, r.fp) for r in self._reset_records(source)],
                    )
                )
            fg = self.spec.grammar.files[source.file.kind]
            doc = Document(sections=sections, has_end=bool(fg.end))
            name = self._new_file_name(None, data.name)
            return self._zone_out(self._unit_of(self.store.new_file(name, source.file.kind, doc, listed=True)))

    def _reset_records(self, unit: ZoneUnit) -> list[Record]:
        """I `Record` dello script di una zona con resets in sezione."""
        spec = self._reset_section(unit)
        section = next((s for s in unit.file.doc.sections if s.spec is spec), None)
        return list(section.records) if section else []

    # ------------------------------------------------------------------ reset

    async def list_reset_commands(self, zone_id: int) -> list[ResetCommandOut]:
        """Lo script di reset della zona (`id` = `orderIndex` = posizione, commenti e comandi ignoti esclusi)."""
        unit = self.zone_or_404(zone_id)
        return [self.reset_map.out(unit.zone_id, i, f) for i, f in enumerate(self.commands(unit))]

    async def replace_reset_commands(self, zone_id: int, data: ResetScriptIn) -> list[ResetCommandOut]:
        """Sostituisce lo script. I comandi invariati riusano il record originale (stessi byte e commento); i commenti
        si perdono solo se lo script cambia. 422 `mapping.reset_unmapped_commands` se la zona ha comandi che il modello
        non conosce (sostituire lo script li cancellerebbe)."""
        self.ensure_writable()
        if self.spec.model.zone.resets is None:
            raise api_error(409, "world.capability_missing", capability="supports_reset_scripts")
        async with self.writing():
            unit = self.zone_or_404(zone_id)
            drafts = self.drafts_of(data.commands)
            rules.raise_script_errors(await rules.validate_script(self.reset_lookup(), drafts))
            if hidden := self.unmapped_commands(unit):
                raise api_error(422, "mapping.reset_unmapped_commands", count=hidden)
            old = self.commands(unit)
            pool: dict[Any, list[dict[str, Any]]] = {}
            for f in old:
                pool.setdefault(self.reset_map.key(unit.zone_id, f), []).append(f)
            new: list[dict[str, Any]] = []
            for command in drafts:
                built = self.reset_map.build(command, {})
                same = pool.get(self.reset_map.key(unit.zone_id, built))
                new.append(same.pop(0) if same else built)
            if len(new) != len(old) or any(a is not b for a, b in zip(new, old, strict=True)):
                self.set_reset_fields(unit, new)
                self.store.save(unit.file)
            return await self.list_reset_commands(zone_id)

    async def validate_reset_commands(self, zone_id: int, data: ResetDraftScriptIn) -> ResetValidation:
        """Controlla uno script senza salvarlo (errori e avvertimenti per passo)."""
        self.zone_or_404(zone_id)
        issues = rules.to_issues(await rules.validate_script(self.reset_lookup(), data.commands))
        return ResetValidation(ok=not any(i.severity == "error" for i in issues), issues=issues)
