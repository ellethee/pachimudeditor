"""Zone (`dikumoddata.zon`) e script di reset (mixin di `DikumodAdapter`).

Una zona e' identificata dalla sua **posizione** nel file (`id == vnum ==` indice): il numero `#N` non e' univoco. Una zona
ha solo `top`; `bottomVnum` e' derivato da `top` della precedente (`top + 1`). Una zona che non possiede vnum (suo `top`
uguale a quello della precedente, come la zona 0 di `top 0` dopo il primo vnum) mostra il range `0-0`.
"""

from __future__ import annotations

import copy
from typing import Any

from pachimudeditor_adapter_dikumod.dikumod_lib import Zone, is_unchanged
from pachifast.i18n import api_error
from pachifast.schemas.responses import PaginatedResponse
from pachimudeditor.common.enums import ZoneResetMode

from pachimudeditor_adapter_dikumod import mapping
from pachimudeditor_adapter_dikumod.base import DikumodResetLookup, DikumodSupport
from pachimudeditor_adapter_dikumod.store import ZoneRef
from pachimudeditor.sdk import rules
from pachimudeditor.common.adapters.models import (
    EntityKind,
    NextZoneVnum,
    ResetCommandDraft,
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


class ZonesMixin(DikumodSupport):
    """Operazioni su zone e script di reset."""

    # ------------------------------------------------------------------ utilita'

    def _zone_out(self, ref: ZoneRef) -> ZoneOut:
        """DTO neutro di una zona (le zone illeggibili compaiono con nome segnaposto e `extra.corrupted`)."""
        store = self.store
        bottom, top = store.bounds(ref.index)
        item = ref.item
        if not isinstance(item, Zone):
            return ZoneOut(
                id=ref.index, vnum=ref.index, name=f"[zona illeggibile #{item.vnum}]", builder="", bottom_vnum=bottom,
                top_vnum=top, min_level=1, max_level=1, lifespan_minutes=0, reset_mode=ZoneResetMode.NEVER, enabled=True,
                extra={"corrupted": True, "warning": item.error, "line": item.line, "raw": item.src},
            )  # fmt: skip
        return ZoneOut(
            id=ref.index, vnum=ref.index, name=item.name, builder="", bottom_vnum=bottom, top_vnum=top, min_level=1,
            max_level=1, lifespan_minutes=item.lifespan, reset_mode=mapping.reset_mode_out(item.reset_mode), enabled=True,
            extra={
                "numRaw": item.num, "resetModeRaw": item.reset_mode, "index": ref.index, "topRaw": item.top,
                "hasEnd": item.has_end, "override": ref.override_path.name if ref.override_path else None,
            },
        )  # fmt: skip

    def _count_in(self, lo: int, hi: int) -> int:
        """Quante stanze/mob/oggetti hanno un vnum in `lo..hi`."""
        s = self.store
        return sum(1 for v in (*s.rooms, *s.mobs, *s.raw_mobs, *s.objs) if lo <= v <= hi)

    def _zone_range(self, zone_id: int, kind: EntityKind) -> list[int]:
        """I vnum di `kind` posseduti dalla zona."""
        lo, hi = self.store.bounds(zone_id)
        s = self.store
        index = {"room": s.rooms, "mob": {**s.raw_mobs, **s.mobs}, "object": s.objs}[kind]
        return [v for v in index if lo <= v <= hi and s.zone_of(v) == zone_id]

    def _check_new_range(self, bottom: int, top: int, vnum: int) -> int:
        """Controlla una zona nuova in coda (409 `zones.range_overlap`/`zones.vnum_taken`, 422 range) e ne dà il `top` vero."""
        store = self.store
        last = store.tops[-1] if store.tops else -1
        ranged = (bottom, top) != (0, 0)
        if ranged:
            clash = rules.range_clash(((getattr(z.item, "name", "?"), z.index, *store.bounds(z.index)) for z in store.zones), bottom, top)
            if clash is not None:
                raise conflict("zones.range_overlap", zone=clash[0], zone_vnum=clash[1])
        if vnum < len(store.zones):
            raise conflict("zones.vnum_taken", vnum=vnum)
        if not ranged:
            return last
        if bottom != last + 1:
            raise api_error(422, "dikumod.zone_bottom_derived", expected=last + 1, bottom=bottom)
        return top

    def _append_zone(self, store: Any, zone: Zone) -> ZoneOut:
        """Aggiunge la zona in coda a `dikumoddata.zon` e la rilegge."""
        store.zon.items.append(zone)
        store.save(store.zon)
        return self._zone_out(store.zone(len(store.zones) - 1))

    # ------------------------------------------------------------------ zone

    async def list_zones(self, params: ZonePageParams) -> PaginatedResponse[ZoneOut]:
        """Zone paginate (ordine di default: posizione), cercabili per nome/builder/vnum."""
        self.sync()
        zones = [self._zone_out(z) for z in self.store.zones]
        items, total = paginate_list(
            zones, params, lambda z: (z.name, z.builder, z.vnum), lambda z, f: getattr(z, f), ZonePageParams.order_fields or []
        )
        return make_page(ZoneOut, items, total, params)

    async def get_zone(self, zone_id: int) -> ZoneOut:
        """Una zona (404 `zones.not_found`)."""
        return self._zone_out(self.zone_or_404(zone_id))

    async def create_zone(self, data: ZoneIn) -> ZoneOut:
        """Aggiunge una zona **in coda** a `dikumoddata.zon`.

        L'`id` e' la sua posizione (il `vnum` della richiesta conta solo per il controllo `zones.vnum_taken`). Con un range,
        `bottomVnum` deve essere `top` dell'ultima zona + 1 (422 `dikumod.zone_bottom_derived`); senza range la zona e' vuota
        (`top` uguale a quello dell'ultima: non possiede vnum finche' non le si da un range)."""
        async with self.writing() as store:
            top = self._check_new_range(data.bottom_vnum, data.top_vnum, data.vnum)
            num = max((z.item.num for z in store.zones if isinstance(z.item, Zone)), default=0) + 1
            raw = int(data.reset_mode) if data.reset_mode else 0
            return self._append_zone(store, Zone(num, data.name, top, data.lifespan_minutes, raw))

    async def update_zone(self, zone_id: int, data: ZonePatch) -> ZoneOut:
        """Aggiornamento parziale: nome, `lifespanMinutes`, `resetMode` (bit 1-2), `topVnum` (non deve spostare contenuto).

        `bottomVnum` e' derivato (deve restare `top` precedente + 1); `builder`, livelli e `enabled` non esistono in Diku Modificato
        (valori neutri: il patch e' ignorato)."""
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude={"extra"})
        async with self.writing() as store:
            ref = self.editable_zone(zone_id)
            zone: Zone = ref.item  # type: ignore[assignment]
            bounds = store.bounds(zone_id)
            derived = store.tops[zone_id - 1] + 1 if zone_id > 0 else 0
            top = changes.get("top_vnum", zone.top)
            low, high = changes.get("min_level", 1), changes.get("max_level", 1)
            if "bottom_vnum" in changes or "top_vnum" in changes:
                rules.check_zone_ranges(changes.get("bottom_vnum", derived), top, low, high)
            else:
                rules.check_zone_ranges(0, 0, low, high)
            if "vnum" in changes and changes["vnum"] != zone_id:
                raise api_error(422, "dikumod.zone_derived", vnum=changes["vnum"], expected=zone_id)
            given = changes.get("bottom_vnum")
            if given is not None and given not in (derived, bounds[0]):
                raise api_error(422, "dikumod.zone_bottom_derived", expected=derived, bottom=given)
            if top != zone.top:
                prev = store.tops[zone_id - 1] if zone_id > 0 else 0
                nxt = store.tops[zone_id + 1] if zone_id + 1 < len(store.tops) else None
                if top < prev or (nxt is not None and top > nxt):
                    raise api_error(422, "dikumod.zone_top_order", prev=prev, next=nxt if nxt is not None else "-")
                lo, hi = sorted((zone.top, top))
                moved = self._count_in(lo + 1, hi)
                if moved:
                    raise conflict("dikumod.zone_range_has_content", count=moved)
                zone.top = top
            if "name" in changes:
                zone.name = mapping.clean_text(changes["name"], lstrip=False)
            if "lifespan_minutes" in changes:
                zone.lifespan = changes["lifespan_minutes"]
            if "reset_mode" in changes:
                zone.reset_mode = mapping.reset_mode_in(zone.reset_mode, changes["reset_mode"])
            self._apply_zone_extra(zone, data.extra or {})
            if not is_unchanged(zone):
                store.save(store.zon)  # type: ignore[arg-type]
            return self._zone_out(store.zone(zone_id))  # type: ignore[arg-type]

    @staticmethod
    def _apply_zone_extra(zone: Zone, extra: dict[str, Any]) -> None:
        """Chiavi di `extra` di una zona: `numRaw` (il `#N`) e `resetModeRaw` (bit grezzi) sono scrivibili, il resto e' informativo."""

        def num(value: Any) -> None:
            """Il numero `#N` scritto nel file."""
            zone.num = mapping._int("numRaw", value)

        def mode(value: Any) -> None:
            """I bit di `reset_mode` (0 mai, 1 vuota, 2 sempre, 4/8/16/32 modificatori)."""
            zone.reset_mode = mapping._int("resetModeRaw", value, 0)

        mapping.apply_extra(
            extra,
            {"numRaw": num, "resetModeRaw": mode, "index": lambda v: None, "topRaw": lambda v: None, "hasEnd": lambda v: None,
             "override": lambda v: None},
        )  # fmt: skip

    async def delete_zone(self, zone_id: int) -> None:
        """Elimina la zona dal file: solo se non possiede contenuto (409 `zones.not_empty`) e se non ci sono file
        `zones/<n>.zon` con indice maggiore (si sposterebbero, 409 `dikumod.zone_index_in_use`). Gli id successivi scalano."""
        async with self.writing() as store:
            ref = self.zone_or_404(zone_id)
            lo, hi = store.bounds(zone_id)
            counts = [len(self._zone_range(zone_id, k)) for k in ("room", "mob", "object")]  # type: ignore[arg-type]
            if any(counts):
                raise conflict("zones.not_empty", rooms=counts[0], mobs=counts[1], objects=counts[2])
            if ref.override is not None or any(z.override is not None and z.index > zone_id for z in store.zones):
                raise conflict("dikumod.zone_index_in_use")
            store.zon.items[:] = [i for i in store.zon.items if i is not ref.item]  # type: ignore[union-attr]
            store.save(store.zon)  # type: ignore[arg-type]

    @staticmethod
    def _summary_counts(store: Any, zone_id: int) -> ZoneSummary:
        """Conteggi del contenuto posseduto da una zona."""
        pools = (store.rooms, {**store.raw_mobs, **store.mobs}, store.objs)
        counts = [sum(1 for v in pool if store.zone_of(v) == zone_id) for pool in pools]
        return ZoneSummary(room_count=counts[0], mob_count=counts[1], object_count=counts[2])

    async def zone_summary(self, zone_id: int) -> ZoneSummary:
        """Conteggi di stanze, mob e oggetti."""
        self.zone_or_404(zone_id)
        return self._summary_counts(self.store, zone_id)

    async def next_zone_vnum(self, span: int) -> NextZoneVnum:
        """Id (= posizione) della prossima zona e un range `span` ampio che inizia dopo il `top` dell'ultima."""
        store = self.sync()
        bottom = (store.tops[-1] + 1) if store.tops else 0
        return NextZoneVnum(vnum=len(store.zones), bottom_vnum=bottom, top_vnum=bottom + span)

    async def next_content_vnum(self, zone_id: int, kind: EntityKind) -> int:
        """Un vnum libero: uno oltre il piu' alto della zona (o il `bottom` se vuota), saltando i vnum occupati."""
        self.zone_or_404(zone_id)
        store = self.store
        low, _ = store.bounds(zone_id)
        mine = self._zone_range(zone_id, kind)
        candidate = max(mine) + 1 if mine else low
        pool = {"room": store.rooms, "mob": {**store.raw_mobs, **store.mobs}, "object": store.objs}[kind]
        return rules.first_free_vnum(candidate, {v for v in pool if v >= candidate})

    async def clone_zone(self, zone_id: int, data: ZoneCloneIn) -> ZoneOut:
        """Duplica la zona in coda al file (non il contenuto); opzionalmente copia lo script di reset. Range da
        `bottomVnum`/`topVnum` (409 `zones.range_overlap`) oppure zona vuota."""
        async with self.writing() as store:
            source = self.editable_zone(zone_id)
            top = self._check_new_range(data.bottom_vnum or 0, data.top_vnum or 0, data.vnum)
            src: Zone = source.item  # type: ignore[assignment]
            num = max((z.item.num for z in store.zones if isinstance(z.item, Zone)), default=0) + 1
            zone = Zone(num, data.name, top, src.lifespan, src.reset_mode)
            if data.copy_reset_commands:
                zone.items = [copy.deepcopy(c) for c in source.commands()]
            return self._append_zone(store, zone)

    # ------------------------------------------------------------------ reset

    async def list_reset_commands(self, zone_id: int) -> list[ResetCommandOut]:
        """Lo script di reset della zona (`id` = `orderIndex` = posizione, commenti e righe vuote esclusi)."""
        zone = self.zone_or_404(zone_id)
        return [mapping.reset_out(zone.index, i, c) for i, c in enumerate(zone.commands())]

    async def replace_reset_commands(self, zone_id: int, data: ResetScriptIn) -> list[ResetCommandOut]:
        """Sostituisce lo script. I comandi invariati riusano l'originale (stessi byte e commento); righe di commento e
        righe vuote si perdono solo se lo script cambia davvero. Se esiste `zones/<n>.zon` la scrittura va li'."""
        async with self.writing() as store:
            zone = self.editable_zone(zone_id)
            drafts = [ResetCommandDraft.model_validate(c.model_dump(by_alias=False)) for c in data.commands]
            rules.raise_script_errors(await rules.validate_script(DikumodResetLookup(store), drafts))
            old = zone.commands()
            pool: dict[Any, list[Any]] = {}
            for cmd in old:
                pool.setdefault(mapping.reset_key(mapping.reset_out(zone_id, 0, cmd)), []).append(cmd)
            new = []
            for index, draft in enumerate(drafts):
                built = mapping.reset_from(draft, index)
                same = pool.get(mapping.reset_key(mapping.reset_out(zone_id, 0, built)))
                new.append(same.pop(0) if same else built)
            if len(new) != len(old) or any(a is not b for a, b in zip(new, old)):
                if zone.override is not None:
                    zone.override.items[:] = new
                    store.save_zone_override(zone)
                else:
                    zone.item.items[:] = new  # type: ignore[union-attr]
                    store.save(store.zon)  # type: ignore[arg-type]
            return await self.list_reset_commands(zone_id)

    async def validate_reset_commands(self, zone_id: int, data: ResetDraftScriptIn) -> ResetValidation:
        """Controlla uno script senza salvarlo (errori e avvertimenti per passo)."""
        self.zone_or_404(zone_id)
        issues = rules.to_issues(await rules.validate_script(DikumodResetLookup(self.store), data.commands))
        return ResetValidation(ok=not any(i.severity == "error" for i in issues), issues=issues)
